import hashlib
import json
import threading
import time
import uuid
from typing import Dict, List, Any, Optional
import duckdb

from app.ontology.object_type import ObjectType, PropertyMeta
from app.ontology.link_type import LinkType
from app.ontology.action_type import ActionType, ActionExecutionAudit
from app.catalog.metadata_db import MetadataDB
from app.engine.sql_guard import safe_ident, safe_table_ref, safe_predicate, safe_columns
from app.retl.webhook_pusher import WebhookPusher
from app.retl.destination_sync import DestinationSync

class OntologyEngine:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.db = MetadataDB.get_instance()
        self._object_types: Dict[str, ObjectType] = {}
        self._link_types: Dict[str, LinkType] = {}
        self._action_types: Dict[str, ActionType] = {}
        self._restore_from_db()

    @classmethod
    def get_instance(cls) -> "OntologyEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _restore_from_db(self):
        saved_objs = self.db.list_ontology_objects()
        for o in saved_objs:
            self._object_types[o["name"]] = ObjectType(**o)

        saved_links = self.db.list_ontology_links()
        for l in saved_links:
            self._link_types[l["name"]] = LinkType(**l)

        saved_actions = self.db.list_ontology_actions()
        for a in saved_actions:
            self._action_types[a["name"]] = ActionType(**a)

    # --- Schema Management ---
    def register_object_type(self, obj: ObjectType) -> ObjectType:
        with self._lock:
            self._object_types[obj.name] = obj
            self.db.save_ontology_object(obj.model_dump())
            return obj

    def get_object_type(self, name: str) -> Optional[ObjectType]:
        with self._lock:
            return self._object_types.get(name)

    def list_object_types(self) -> List[ObjectType]:
        with self._lock:
            return list(self._object_types.values())

    def register_link_type(self, link: LinkType) -> LinkType:
        with self._lock:
            self._link_types[link.name] = link
            self.db.save_ontology_link(link.model_dump())
            return link

    def list_link_types(self) -> List[LinkType]:
        with self._lock:
            return list(self._link_types.values())

    def register_action_type(self, action: ActionType) -> ActionType:
        with self._lock:
            self._action_types[action.name] = action
            self.db.save_ontology_action(action.model_dump())
            return action

    def list_action_types(self, target_object_type: Optional[str] = None) -> List[ActionType]:
        with self._lock:
            actions = list(self._action_types.values())
            if target_object_type:
                actions = [a for a in actions if a.target_object_type == target_object_type]
            return actions

    def get_ontology_schema_summary(self) -> Dict[str, Any]:
        """Return high-level schema of objects, links, and actions for AI Agent prompt context."""
        with self._lock:
            return {
                "object_types": [
                    {
                        "name": o.name,
                        "display_name": o.display_name or o.name,
                        "description": o.description,
                        "primary_key": o.primary_key,
                        "properties": [p.name for p in o.properties],
                        "available_actions": [a.name for a in self._action_types.values() if a.target_object_type == o.name]
                    }
                    for o in self._object_types.values()
                ],
                "link_types": [
                    {
                        "name": l.name,
                        "source": l.source_object_type,
                        "target": l.target_object_type,
                        "cardinality": l.cardinality
                    }
                    for l in self._link_types.values()
                ]
            }

    # --- Runtime Entity Instances & Graph Traversal ---
    def query_object_instances(
        self,
        con: duckdb.DuckDBPyConnection,
        object_type_name: str,
        filters: Optional[str] = None,
        properties: Optional[List[str]] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Query real entity instances backed by DuckDB tables."""
        with self._lock:
            obj = self._object_types.get(object_type_name)
            if not obj:
                raise ValueError(f"ObjectType '{object_type_name}' is not registered in Ontology.")

            table = safe_table_ref(obj.backed_by_table)
            select_cols = safe_columns(properties) if properties else "*"
            sql = f"SELECT {select_cols} FROM {table}"
            if filters:
                sql += f" WHERE {safe_predicate(filters)}"
            sql += " LIMIT ?"

            df = con.execute(sql, [limit]).df()
            instances = df.to_dict(orient="records")

            return {
                "object_type": object_type_name,
                "primary_key": obj.primary_key,
                "total_instances": len(instances),
                "instances": instances
            }

    def traverse_links(
        self,
        con: duckdb.DuckDBPyConnection,
        source_object_type: str,
        source_instance_id: Any,
        link_name: str,
        limit: int = 50,
        link_path: Optional[List[str]] = None,
        max_hops: int = 4,
    ) -> Dict[str, Any]:
        """
        Graph Multi-Hop Traversal:
        Traverse from a source entity instance (e.g. Customer 'C01') along a link (e.g. 'customer_orders')
        to fetch all linked target entity instances (e.g. Orders).
        """
        with self._lock:
            link = self._link_types.get(link_name)
            if not link:
                raise ValueError(f"LinkType '{link_name}' not found.")
            if link.source_object_type != source_object_type:
                raise ValueError(f"Link '{link_name}' expects source '{link.source_object_type}', got '{source_object_type}'")

            src_obj = self._object_types.get(link.source_object_type)
            tgt_obj = self._object_types.get(link.target_object_type)
            if not src_obj or not tgt_obj:
                raise ValueError("Source or Target ObjectType definition missing.")

            # Perform graph hop via DuckDB join
            hops = link_path or [link_name]
            if len(hops) > max_hops:
                raise ValueError(f"Traversal length {len(hops)} exceeds max_hops={max_hops}")
            if len(hops) == 1:
                sql = f"""
                SELECT tgt.*
                FROM {self._from_clause(link, src_obj, tgt_obj)}
                WHERE src.{safe_ident(src_obj.primary_key)} = ?
                LIMIT ?
                """
                df = con.execute(sql, [source_instance_id, limit]).df()
                linked_instances = df.to_dict(orient="records")
                return {
                    "source_object_type": source_object_type,
                    "source_instance_id": source_instance_id,
                    "link_name": link_name,
                    "target_object_type": tgt_obj.name,
                    "hops": 1,
                    "path": [source_object_type, tgt_obj.name],
                    "hop_counts": [len(linked_instances)],
                    "linked_count": len(linked_instances),
                    "linked_instances": linked_instances
                }

            current_ids = [source_instance_id]
            current_type = source_object_type
            path = [source_object_type]
            seen = {source_object_type}
            hop_counts: List[int] = []
            last = None
            for hop_name in hops:
                hop = self._link_types.get(hop_name)
                if hop is None:
                    raise ValueError(f"LinkType '{hop_name}' not found.")
                if hop.source_object_type != current_type:
                    raise ValueError(
                        f"Link '{hop_name}' expects source '{hop.source_object_type}', got '{current_type}'"
                    )
                if hop.target_object_type in seen:
                    raise ValueError(f"Cycle detected at '{hop.target_object_type}'")
                src_obj = self._object_types[hop.source_object_type]
                tgt_obj = self._object_types[hop.target_object_type]
                placeholders = ", ".join(["?"] * len(current_ids))
                sql = f"""
                SELECT tgt.*
                FROM {self._from_clause(hop, src_obj, tgt_obj)}
                WHERE src.{safe_ident(src_obj.primary_key)} IN ({placeholders})
                LIMIT ?
                """
                df = con.execute(sql, [*current_ids, limit]).df()
                last = df.to_dict(orient="records")
                hop_counts.append(len(last))
                pk = tgt_obj.primary_key
                current_ids = [row[pk] for row in last]
                current_type = tgt_obj.name
                path.append(current_type)
                seen.add(current_type)
                if not current_ids:
                    break
            return {
                "source_object_type": source_object_type,
                "source_instance_id": source_instance_id,
                "link_name": hops[-1],
                "target_object_type": current_type,
                "hops": len(path) - 1,
                "path": path,
                "hop_counts": hop_counts,
                "linked_count": len(last or []),
                "linked_instances": last or [],
            }

    def _from_clause(self, link: LinkType, src_obj, tgt_obj) -> str:
        """FROM/JOIN fragment. MANY_TO_MANY goes through the junction table."""
        src_table = safe_table_ref(src_obj.backed_by_table)
        tgt_table = safe_table_ref(tgt_obj.backed_by_table)
        if link.cardinality == "MANY_TO_MANY":
            if not (link.junction_table and link.junction_source_key and link.junction_target_key):
                raise ValueError(
                    f"MANY_TO_MANY link '{link.name}' requires junction_table, "
                    "junction_source_key, and junction_target_key"
                )
            junction = safe_table_ref(link.junction_table)
            return (
                f"{tgt_table} tgt "
                f"JOIN {junction} j "
                f"ON j.{safe_ident(link.junction_target_key)} = tgt.{safe_ident(link.target_join_key)} "
                f"JOIN {src_table} src "
                f"ON src.{safe_ident(link.source_join_key)} = j.{safe_ident(link.junction_source_key)}"
            )
        return (
            f"{tgt_table} tgt "
            f"JOIN {src_table} src "
            f"ON src.{safe_ident(link.source_join_key)} = tgt.{safe_ident(link.target_join_key)}"
        )

    # --- Action Execution & Audit Trail ---
    def execute_action(
        self,
        con: duckdb.DuckDBPyConnection,
        action_name: str,
        instance_id: Any,
        parameter_values: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute an atomic business action on an object instance with validation and audit trail.
        """
        with self._lock:
            action = self._action_types.get(action_name)
            if not action:
                raise ValueError(f"ActionType '{action_name}' is not registered in Ontology.")

            # 1. Parameter Validation
            for p in action.parameters:
                if p.required and p.name not in parameter_values:
                    if p.default_value is not None:
                        parameter_values[p.name] = p.default_value
                    else:
                        raise ValueError(f"Required parameter '{p.name}' missing for action '{action_name}'")

            audit_id = f"aud_{uuid.uuid4().hex[:10]}"
            exec_result = {}
            status = "SUCCESS"

            if not dry_run:
                # 2. Execution Routing
                if action.handler_type == "WEBHOOK":
                    cfg = action.handler_config
                    webhook_url = cfg.get("webhook_url", "http://127.0.0.1:8000/api/v1/mock_webhook")
                    platform = cfg.get("platform", "generic")
                    title = f"【Ontology 动作触发】{action.display_name or action.name}"
                    msg = f"针对实体对象 [{action.target_object_type}#{instance_id}] 触发了动作：{action.name}"
                    exec_result = WebhookPusher.send_alert(webhook_url, title, msg, platform, extra_metrics=parameter_values)
                    if exec_result.get("status") == "FAILED" and "simulated_payload" not in exec_result:
                        status = "FAILED"

                elif action.handler_type == "SQL_MUTATION":
                    cfg = action.handler_config
                    before = self._snapshot_instance(con, action.target_object_type, instance_id)
                    if cfg.get("writeback_table"):
                        wb = safe_table_ref(cfg["writeback_table"])
                        value_param = cfg.get("value_param", "value")
                        column_name = cfg.get("set_column", value_param)
                        statement = (
                            f"INSERT INTO {wb} (instance_id, column_name, new_value, executed_at) "
                            "VALUES (?, ?, ?, current_timestamp)"
                        )
                        con.execute(
                            f"CREATE TABLE IF NOT EXISTS {wb} ("
                            "instance_id VARCHAR, column_name VARCHAR, new_value VARCHAR, executed_at TIMESTAMP)"
                        )
                        bound = [str(instance_id), str(column_name), str(parameter_values.get(value_param))]
                        con.execute(statement, bound)
                        after = {
                            "writeback_table": cfg["writeback_table"],
                            "column_name": column_name,
                            "new_value": bound[2],
                            "note": "Edit stored beside the source table. The backing table was not updated.",
                        }
                        exec_result = {
                            "status": "SUCCESS",
                            "writeback_table": cfg["writeback_table"],
                            "note": after["note"],
                            "before": before,
                            "after": after,
                            "statement_hash": _statement_hash(statement, bound),
                        }
                    template = cfg.get("sql_template")
                    if template and not cfg.get("writeback_table"):
                        # Simple parameter substitution
                        # sql_template is a .format() string, so values cannot be bound as real
                        # parameters without an API change: reject anything that could close a
                        # literal or chain a statement.
                        subs = {"instance_id": instance_id, **parameter_values}
                        for k, v in subs.items():
                            if isinstance(v, str) and any(t in v for t in ("'", '"', ";", "--", "/*")):
                                raise ValueError(
                                    f"Unsafe character in SQL_MUTATION parameter '{k}': {v!r}"
                                )
                        formatted_sql = template.format(**subs)
                        con.execute(formatted_sql)
                        after = self._snapshot_instance(con, action.target_object_type, instance_id)
                        exec_result = {
                            "status": "SUCCESS",
                            "executed_sql": formatted_sql,
                            "before": before,
                            "after": after,
                            "statement_hash": _statement_hash(formatted_sql),
                        }

                elif action.handler_type == "REVERSE_ETL_SYNC":
                    cfg = action.handler_config
                    dest = cfg.get("dest_conn_str")
                    dest_table = cfg.get("dest_table_name")
                    source = cfg.get("source_table")
                    if not (dest and dest_table and source):
                        status = "FAILED"
                        exec_result = {
                            "status": "FAILED",
                            "message": "REVERSE_ETL_SYNC needs handler_config dest_conn_str, dest_table_name, and source_table. Nothing was synced.",
                        }
                    else:
                        try:
                            synced = DestinationSync.sync_table_to_destination(
                                con, source, dest, dest_table, cfg.get("mode", "replace")
                            )
                            exec_result = {"status": "SUCCESS", "sync": synced}
                        except Exception as exc:
                            status = "FAILED"
                            exec_result = {"status": "FAILED", "message": str(exc)}
            else:
                status = "SIMULATED"
                exec_result = {"status": "SIMULATED", "params": parameter_values}

            # 3. Write Audit Trail
            audit_record = ActionExecutionAudit(
                audit_id=audit_id,
                action_name=action_name,
                target_object_type=action.target_object_type,
                target_instance_id=str(instance_id),
                parameters=parameter_values,
                status=status,
                execution_result=exec_result
            )
            self.db.save_action_audit(audit_record.model_dump())

            return audit_record.model_dump()

    def _snapshot_instance(self, con: duckdb.DuckDBPyConnection, object_type_name: str, instance_id: Any):
        obj = self._object_types.get(object_type_name)
        if obj is None:
            return None
        try:
            df = con.execute(
                f"SELECT * FROM {safe_table_ref(obj.backed_by_table)} WHERE {safe_ident(obj.primary_key)} = ?",
                [instance_id],
            ).df()
        except duckdb.Error:
            return None
        if df.empty:
            return None
        return json.loads(df.head(1).to_json(orient="records", date_format="iso"))[0]

    def list_action_audits(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return self.db.list_action_audits(limit=limit)

def _statement_hash(statement: str, bound: Optional[List[Any]] = None) -> str:
    payload = statement if not bound else statement + "|" + json.dumps(bound, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_ontology_engine() -> OntologyEngine:
    return OntologyEngine.get_instance()
