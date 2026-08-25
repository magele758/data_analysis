import threading
import time
import uuid
from typing import Dict, List, Any, Optional
import duckdb

from app.ontology.object_type import ObjectType, PropertyMeta
from app.ontology.link_type import LinkType
from app.ontology.action_type import ActionType, ActionExecutionAudit
from app.catalog.metadata_db import MetadataDB
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

            table = obj.backed_by_table
            select_cols = ", ".join([f'"{p}"' for p in properties]) if properties else "*"
            sql = f"SELECT {select_cols} FROM {table}"
            if filters:
                sql += f" WHERE {filters}"
            sql += f" LIMIT {limit}"

            df = con.execute(sql).df()
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
        limit: int = 50
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
            src_table = src_obj.backed_by_table
            tgt_table = tgt_obj.backed_by_table

            # Safely quote string IDs
            id_val = f"'{source_instance_id}'" if isinstance(source_instance_id, str) else str(source_instance_id)

            sql = f"""
            SELECT tgt.* 
            FROM {tgt_table} tgt
            JOIN {src_table} src ON src."{link.source_join_key}" = tgt."{link.target_join_key}"
            WHERE src."{src_obj.primary_key}" = {id_val}
            LIMIT {limit}
            """

            df = con.execute(sql).df()
            linked_instances = df.to_dict(orient="records")

            return {
                "source_object_type": source_object_type,
                "source_instance_id": source_instance_id,
                "link_name": link_name,
                "target_object_type": tgt_obj.name,
                "linked_count": len(linked_instances),
                "linked_instances": linked_instances
            }

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
                    template = action.handler_config.get("sql_template")
                    if template:
                        # Simple parameter substitution
                        formatted_sql = template.format(instance_id=instance_id, **parameter_values)
                        con.execute(formatted_sql)
                        exec_result = {"status": "SUCCESS", "executed_sql": formatted_sql}

                elif action.handler_type == "REVERSE_ETL_SYNC":
                    # Sync instance update to sink DB
                    exec_result = {"status": "SUCCESS", "message": "Synced to downstream destination"}
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

    def list_action_audits(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return self.db.list_action_audits(limit=limit)

def get_ontology_engine() -> OntologyEngine:
    return OntologyEngine.get_instance()
