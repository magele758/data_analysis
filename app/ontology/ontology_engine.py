import hashlib
import json
import math
import re
import threading
import uuid
from typing import Dict, List, Any, Optional, Tuple, Set
import duckdb

from app.ontology.object_type import ObjectType, PropertyMeta
from app.ontology.interface_type import InterfaceType
from app.ontology.link_type import LinkType
from app.ontology.action_type import (
    ActionType,
    ActionParameter,
    ActionPrecondition,
    ActionExecutionAudit,
    FunctionType,
)
from app.catalog.metadata_db import MetadataDB
from app.catalog.meta_registry import TableAsset
from app.engine.sql_guard import safe_ident, safe_predicate, safe_table_ref
from app.retl.webhook_pusher import WebhookPusher
from app.retl.destination_sync import DestinationSync

_CARDINALITIES = {"ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY"}
_HANDLERS = {"WEBHOOK", "SQL_MUTATION", "REVERSE_ETL_SYNC", "FUNCTION"}
_STRING_TYPES = {"string", "str", "varchar", "text"}
_INT_TYPES = {"integer", "int", "bigint"}
_FLOAT_TYPES = {"float", "double", "number", "numeric"}
_BOOL_TYPES = {"boolean", "bool"}
_JSON_TYPES = {"json", "object", "any"}
_TIMESTAMP_TYPES = {"timestamp", "datetime", "date", "temporal"}
_SINGLE_TARGET = {"ONE_TO_ONE", "MANY_TO_ONE"}
_REDACTED_MASK = "***REDACTED***"


class OntologyEngine:
    _instance = None
    _lock = threading.RLock()
    _session_instances: Dict[str, "OntologyEngine"] = {}

    def __init__(self, persistent: bool = True, session_id: str = "_global"):
        self.persistent = persistent
        self.session_id = session_id
        self.db = MetadataDB.get_instance() if persistent else None
        self._interface_types: Dict[str, InterfaceType] = {}
        self._object_types: Dict[str, ObjectType] = {}
        self._link_types: Dict[str, LinkType] = {}
        self._action_types: Dict[str, ActionType] = {}
        self._function_types: Dict[str, FunctionType] = {}
        self._memory_audits: List[Dict[str, Any]] = []
        if self.persistent and self.db is not None:
            self._restore_from_db()

    @classmethod
    def get_instance(cls) -> "OntologyEngine":
        return get_ontology_engine("_global")

    def _restore_from_db(self):
        if not self.db:
            return
        for iface in self.db.list_ontology_interfaces():
            self._interface_types[iface["name"]] = InterfaceType(**iface)

        for o in self.db.list_ontology_objects():
            self._object_types[o["name"]] = ObjectType(**o)

        for l in self.db.list_ontology_links():
            self._link_types[l["name"]] = LinkType(**l)

        for a in self.db.list_ontology_actions():
            self._action_types[a["name"]] = ActionType(**a)

        for fn in self.db.list_ontology_functions():
            self._function_types[fn["name"]] = FunctionType(**fn)

    def _fallback_global(self) -> Optional["OntologyEngine"]:
        if self.session_id == "_global":
            return None
        return get_ontology_engine("_global")

    def _resolve_interface_type(self, name: str) -> Optional[InterfaceType]:
        iface = self._interface_types.get(name)
        if iface is not None:
            return iface
        g = self._fallback_global()
        return g._interface_types.get(name) if g else None

    def _resolve_object_type(self, name: str) -> Optional[ObjectType]:
        obj = self._object_types.get(name)
        if obj is not None:
            return obj
        g = self._fallback_global()
        return g._object_types.get(name) if g else None

    def _resolve_link_type(self, name: str) -> Optional[LinkType]:
        link = self._link_types.get(name)
        if link is not None:
            return link
        g = self._fallback_global()
        return g._link_types.get(name) if g else None

    def _resolve_action_type(self, name: str) -> Optional[ActionType]:
        act = self._action_types.get(name)
        if act is not None:
            return act
        g = self._fallback_global()
        return g._action_types.get(name) if g else None

    def _resolve_function_type(self, name: str) -> Optional[FunctionType]:
        fn = self._function_types.get(name)
        if fn is not None:
            return fn
        g = self._fallback_global()
        return g._function_types.get(name) if g else None

    # --- Interface Management (Polymorphism & Inheritance) ---
    def register_interface_type(self, iface: InterfaceType) -> InterfaceType:
        with self._lock:
            self._validate_interface_type(iface)
            self._interface_types[iface.name] = iface
            if self.persistent and self.db:
                self.db.save_ontology_interface(iface.model_dump())
            return iface

    def get_interface_type(self, name: str) -> Optional[InterfaceType]:
        with self._lock:
            return self._interface_types.get(name)

    def list_interface_types(self) -> List[InterfaceType]:
        with self._lock:
            return list(self._interface_types.values())

    def unregister_interface_type(self, name: str) -> bool:
        with self._lock:
            if name not in self._interface_types:
                return False
            child_ifaces = [
                i.name for i in self._interface_types.values()
                if name in (i.extends or [])
            ]
            if child_ifaces:
                raise ValueError(
                    f"InterfaceType '{name}' is extended by interfaces {child_ifaces}. "
                    "Unregister those interfaces first."
                )
            impl_objs = [
                o.name for o in self._object_types.values()
                if name in (o.implements or [])
            ]
            if impl_objs:
                raise ValueError(
                    f"InterfaceType '{name}' is still implemented by ObjectTypes {impl_objs}. "
                    "Unregister or update those ObjectTypes first."
                )
            used_actions = [
                a.name for a in self._action_types.values()
                if a.target_object_type == name or a.target_interface == name
            ]
            if used_actions:
                raise ValueError(
                    f"InterfaceType '{name}' is still targeted by actions {used_actions}. "
                    "Unregister those actions first."
                )
            used_fns = [
                f.name for f in self._function_types.values()
                if f.target_object_type == name
            ]
            if used_fns:
                raise ValueError(
                    f"InterfaceType '{name}' is still targeted by functions {used_fns}. "
                    "Unregister those functions first."
                )
            if self.persistent and self.db:
                self.db.delete_ontology_interface(name)
            self._interface_types.pop(name, None)
            return True

    def effective_interface_properties(self, interface_name: str) -> List[PropertyMeta]:
        """Resolve all required properties of an interface, including inherited ones via `extends`."""
        with self._lock:
            iface = self._resolve_interface_type(interface_name)
            if iface is None:
                raise ValueError(f"InterfaceType '{interface_name}' is not registered in Ontology.")
            resolved: Dict[str, PropertyMeta] = {}
            visited: List[str] = []

            def _walk(curr_name: str, stack: Set[str]):
                if curr_name in stack:
                    raise ValueError(f"Interface inheritance cycle detected at '{curr_name}'")
                curr = self._resolve_interface_type(curr_name)
                if curr is None:
                    raise ValueError(f"Parent InterfaceType '{curr_name}' is not registered.")
                for parent in curr.extends or []:
                    _walk(parent, stack | {curr_name})
                if curr_name not in visited:
                    visited.append(curr_name)
                    for prop in curr.required_properties:
                        if prop.name in resolved:
                            prev_type = _normalize_property_type(resolved[prop.name].data_type)
                            curr_type = _normalize_property_type(prop.data_type)
                            if prev_type != curr_type:
                                raise ValueError(
                                    f"Interface '{interface_name}' has conflicting types for property "
                                    f"'{prop.name}': {prev_type} vs {curr_type}"
                                )
                        resolved[prop.name] = prop

            _walk(interface_name, set())
            return list(resolved.values())

    def implementing_object_types(self, interface_name: str) -> List[ObjectType]:
        """Return all ObjectTypes that implement `interface_name` directly or via sub-interfaces."""
        with self._lock:
            if self._resolve_interface_type(interface_name) is None:
                raise ValueError(f"InterfaceType '{interface_name}' is not registered in Ontology.")
            all_ifaces = dict(self._interface_types)
            g = self._fallback_global()
            if g:
                for k, v in g._interface_types.items():
                    all_ifaces.setdefault(k, v)

            matching_ifaces: Set[str] = {interface_name}
            changed = True
            while changed:
                changed = False
                for iname, iface in all_ifaces.items():
                    if iname not in matching_ifaces and any(p in matching_ifaces for p in (iface.extends or [])):
                        matching_ifaces.add(iname)
                        changed = True

            all_objs = dict(self._object_types)
            if g:
                for k, v in g._object_types.items():
                    all_objs.setdefault(k, v)

            return [
                obj for obj in all_objs.values()
                if any(impl in matching_ifaces for impl in (obj.implements or []))
            ]

    # --- Object, Link, Action & Function Schema Management ---
    def register_object_type(self, obj: ObjectType) -> ObjectType:
        with self._lock:
            self._validate_object_type(obj)
            self._object_types[obj.name] = obj
            if self.persistent and self.db:
                self.db.save_ontology_object(obj.model_dump())
            return obj

    def get_object_type(self, name: str) -> Optional[ObjectType]:
        with self._lock:
            return self._object_types.get(name)

    def list_object_types(self) -> List[ObjectType]:
        with self._lock:
            return list(self._object_types.values())

    def unregister_object_type(self, name: str) -> bool:
        """Drop an object type that nothing still points at."""
        with self._lock:
            if name not in self._object_types:
                return False
            used_links = [
                link.name for link in self._link_types.values()
                if link.source_object_type == name or link.target_object_type == name
            ]
            if used_links:
                raise ValueError(
                    f"ObjectType '{name}' is still referenced by links {used_links}. "
                    "Unregister those links first."
                )
            used_actions = [
                action.name for action in self._action_types.values()
                if action.target_object_type == name
            ]
            if used_actions:
                raise ValueError(
                    f"ObjectType '{name}' is still referenced by actions {used_actions}. "
                    "Unregister those actions first."
                )
            used_fns = [
                fn.name for fn in self._function_types.values()
                if fn.target_object_type == name
            ]
            if used_fns:
                raise ValueError(
                    f"ObjectType '{name}' is still referenced by functions {used_fns}. "
                    "Unregister those functions first."
                )
            if self.persistent and self.db:
                self.db.delete_ontology_object(name)
            self._object_types.pop(name, None)
            return True

    def register_from_catalog_asset(
        self,
        asset: TableAsset,
        *,
        name: Optional[str] = None,
        primary_key: Optional[str] = None,
    ) -> ObjectType:
        """Turn a catalog table asset into a registered object type."""
        obj = build_object_type_from_asset(asset, name=name, primary_key=primary_key)
        return self.register_object_type(obj)

    def register_link_type(self, link: LinkType) -> LinkType:
        with self._lock:
            link = self._validate_link_type(link)
            self._link_types[link.name] = link
            if self.persistent and self.db:
                self.db.save_ontology_link(link.model_dump())
            return link

    def get_link_type(self, name: str) -> Optional[LinkType]:
        with self._lock:
            return self._link_types.get(name)

    def list_link_types(self) -> List[LinkType]:
        with self._lock:
            return list(self._link_types.values())

    def unregister_link_type(self, name: str) -> bool:
        with self._lock:
            if name not in self._link_types:
                return False
            if self.persistent and self.db:
                self.db.delete_ontology_link(name)
            self._link_types.pop(name, None)
            return True

    def register_action_type(self, action: ActionType) -> ActionType:
        with self._lock:
            action = self._validate_action_type(action)
            self._action_types[action.name] = action
            if self.persistent and self.db:
                self.db.save_ontology_action(action.model_dump())
            return action

    def get_action_type(self, name: str) -> Optional[ActionType]:
        with self._lock:
            return self._action_types.get(name)

    def list_action_types(self, target_object_type: Optional[str] = None) -> List[ActionType]:
        with self._lock:
            actions = list(self._action_types.values())
            if target_object_type:
                obj = self._resolve_object_type(target_object_type)
                impl_ifaces = set(obj.implements or []) if obj else set()
                # Include ancestor interfaces implemented by obj
                expanded_ifaces: Set[str] = set()
                for iname in impl_ifaces:
                    expanded_ifaces.add(iname)
                    iface_obj = self._resolve_interface_type(iname)
                    if iface_obj:
                        expanded_ifaces.update(iface_obj.extends or [])
                actions = [
                    a for a in actions
                    if a.target_object_type == target_object_type
                    or a.target_interface == target_object_type
                    or a.target_object_type in expanded_ifaces
                    or (a.target_interface and a.target_interface in expanded_ifaces)
                ]
            return actions

    def unregister_action_type(self, name: str) -> bool:
        with self._lock:
            if name not in self._action_types:
                return False
            if self.persistent and self.db:
                self.db.delete_ontology_action(name)
            self._action_types.pop(name, None)
            return True

    def register_function_type(self, fn: FunctionType) -> FunctionType:
        with self._lock:
            fn = self._validate_function_type(fn)
            self._function_types[fn.name] = fn
            if self.persistent and self.db:
                self.db.save_ontology_function(fn.model_dump())
            return fn

    def get_function_type(self, name: str) -> Optional[FunctionType]:
        with self._lock:
            return self._function_types.get(name)

    def list_function_types(self, target_object_type: Optional[str] = None) -> List[FunctionType]:
        with self._lock:
            fns = list(self._function_types.values())
            if target_object_type:
                obj = self._resolve_object_type(target_object_type)
                impl_ifaces = set(obj.implements or []) if obj else set()
                fns = [
                    f for f in fns
                    if f.target_object_type == target_object_type
                    or f.target_object_type in impl_ifaces
                ]
            return fns

    def unregister_function_type(self, name: str) -> bool:
        with self._lock:
            if name not in self._function_types:
                return False
            used_actions = [
                a.name for a in self._action_types.values()
                if (a.handler_type or "").upper() == "FUNCTION"
                and (a.handler_config or {}).get("function_name") == name
            ]
            if used_actions:
                raise ValueError(
                    f"FunctionType '{name}' is still referenced by actions {used_actions}. "
                    "Unregister those actions first."
                )
            if self.persistent and self.db:
                self.db.delete_ontology_function(name)
            self._function_types.pop(name, None)
            return True

    def links_from(self, object_type_name: str) -> List[LinkType]:
        """Outgoing links used to plan the next drill-down hop."""
        with self._lock:
            if self._resolve_object_type(object_type_name) is None:
                raise ValueError(f"ObjectType '{object_type_name}' is not registered in Ontology.")
            return [
                link for link in self._link_types.values()
                if link.source_object_type == object_type_name
            ]

    def entity_graph(self) -> Dict[str, Any]:
        """Adjacency of object types and interfaces. Links whose endpoints are missing stay in broken_edges."""
        with self._lock:
            if not self._object_types and not self._link_types and not self._interface_types:
                g = self._fallback_global()
                if g is not None:
                    return g.entity_graph()
            known = set(self._object_types)
            nodes = []
            for obj in self._object_types.values():
                nodes.append({
                    "id": obj.name,
                    "display_name": obj.display_name or obj.name,
                    "backed_by_table": obj.backed_by_table,
                    "primary_key": obj.primary_key,
                    "implements": list(obj.implements or []),
                    "disjoint_with": list(obj.disjoint_with or []),
                    "outgoing": [
                        link.name for link in self._link_types.values()
                        if link.source_object_type == obj.name
                    ],
                    "incoming": [
                        link.name for link in self._link_types.values()
                        if link.target_object_type == obj.name
                    ],
                })
            edges = []
            broken = []
            for link in self._link_types.values():
                edge = {
                    "id": link.name,
                    "source": link.source_object_type,
                    "target": link.target_object_type,
                    "cardinality": link.cardinality,
                    "source_join_key": link.source_join_key,
                    "target_join_key": link.target_join_key,
                    "inverse_of": link.inverse_of,
                    "is_symmetric": link.is_symmetric,
                    "is_transitive": link.is_transitive,
                }
                if link.source_object_type not in known or link.target_object_type not in known:
                    broken.append(edge)
                else:
                    edges.append(edge)
            interfaces = [
                {
                    "id": iface.name,
                    "display_name": iface.display_name or iface.name,
                    "extends": list(iface.extends or []),
                    "required_properties": [p.name for p in iface.required_properties],
                    "implemented_by": [
                        o.name for o in self._object_types.values()
                        if iface.name in (o.implements or [])
                    ],
                }
                for iface in self._interface_types.values()
            ]
            return {
                "nodes": nodes,
                "edges": edges,
                "broken_edges": broken,
                "interfaces": interfaces,
            }

    def get_ontology_schema_summary(self) -> Dict[str, Any]:
        """Return high-level schema of interfaces, objects, links, actions, and functions for AI Agent prompt context."""
        with self._lock:
            if (
                not self._object_types
                and not self._interface_types
                and not self._link_types
                and not self._action_types
                and not self._function_types
            ):
                g = self._fallback_global()
                if g is not None:
                    return g.get_ontology_schema_summary()
            return {
                "interface_types": [
                    {
                        "name": i.name,
                        "display_name": i.display_name or i.name,
                        "description": i.description,
                        "extends": list(i.extends or []),
                        "required_properties": [p.name for p in i.required_properties],
                        "implemented_by": [
                            o.name for o in self._object_types.values()
                            if i.name in (o.implements or [])
                        ],
                    }
                    for i in self._interface_types.values()
                ],
                "object_types": [
                    {
                        "name": o.name,
                        "display_name": o.display_name or o.name,
                        "description": o.description,
                        "primary_key": o.primary_key,
                        "implements": list(o.implements or []),
                        "disjoint_with": list(o.disjoint_with or []),
                        "writeback_table": o.writeback_table,
                        "properties": [p.name for p in o.properties],
                        "available_actions": [
                            a.name for a in self.list_action_types(target_object_type=o.name)
                        ],
                        "available_functions": [
                            f.name for f in self.list_function_types(target_object_type=o.name)
                        ],
                    }
                    for o in self._object_types.values()
                ],
                "link_types": [
                    {
                        "name": l.name,
                        "source": l.source_object_type,
                        "target": l.target_object_type,
                        "cardinality": l.cardinality,
                        "inverse_of": l.inverse_of,
                        "is_symmetric": l.is_symmetric,
                        "is_transitive": l.is_transitive,
                    }
                    for l in self._link_types.values()
                ],
                "function_types": [
                    {
                        "name": f.name,
                        "display_name": f.display_name or f.name,
                        "target_object_type": f.target_object_type,
                        "parameters": [p.name for p in f.parameters],
                        "return_type": f.return_type,
                    }
                    for f in self._function_types.values()
                ],
            }

    # --- Writeback Overlay & RBAC Helpers ---
    def _candidate_writeback_tables(self, obj: ObjectType) -> List[str]:
        tables: List[str] = []
        if obj.writeback_table:
            tables.append(obj.writeback_table)
        all_actions = list(self._action_types.values())
        g = self._fallback_global()
        if g:
            for a in g._action_types.values():
                if a.name not in self._action_types:
                    all_actions.append(a)
        for act in all_actions:
            if (act.handler_type or "").upper() in ("SQL_MUTATION", "FUNCTION"):
                wb = (act.handler_config or {}).get("writeback_table")
                if wb and (
                    act.target_object_type == obj.name
                    or act.target_object_type in (obj.implements or [])
                    or (act.target_interface and act.target_interface in (obj.implements or []))
                ):
                    if wb not in tables:
                        tables.append(wb)
        return tables

    def _table_source_sql(
        self,
        con: duckdb.DuckDBPyConnection,
        obj: ObjectType,
        include_writeback: bool = True,
    ) -> Tuple[str, List[str]]:
        """
        Return the SQL FROM relation for `obj`. When `include_writeback=True` and one or more
        writeback tables exist in `con` with edits for columns of `obj.backed_by_table`, builds
        an inline overlay relation that merges the latest writeback value per (instance_id, column_name)
        without mutating the underlying backing table.
        """
        base_table = safe_table_ref(obj.backed_by_table)
        if not include_writeback:
            return base_table, []
        candidates = self._candidate_writeback_tables(obj)
        if not candidates:
            return base_table, []
        try:
            col_info = con.execute(f"DESCRIBE {base_table}").fetchall()
        except duckdb.Error:
            return base_table, []
        if not col_info:
            return base_table, []

        active_wbs: List[str] = []
        edited_cols: Set[str] = set()
        for wb in candidates:
            wb_ref = safe_table_ref(wb)
            try:
                rows = con.execute(f"SELECT DISTINCT column_name FROM {wb_ref}").fetchall()
            except duckdb.Error:
                continue
            cols = {str(r[0]) for r in rows if r and r[0] is not None}
            if cols:
                active_wbs.append(wb)
                edited_cols.update(cols)

        if not active_wbs or not edited_cols:
            return base_table, []

        wb_parts = [
            f"SELECT CAST(instance_id AS VARCHAR) AS instance_id, "
            f"CAST(column_name AS VARCHAR) AS column_name, "
            f"CAST(new_value AS VARCHAR) AS new_value, "
            f"executed_at, rowid AS _wb_seq FROM {safe_table_ref(wb)}"
            for wb in active_wbs
        ]
        wb_union = " UNION ALL ".join(wb_parts)
        pk_ident = safe_ident(obj.primary_key)
        select_exprs = []
        for row in col_info:
            col_name = str(row[0])
            col_type = str(row[1])
            col_ident = safe_ident(col_name)
            if col_name in edited_cols and col_name != obj.primary_key:
                escaped_col = col_name.replace("'", "''")
                select_exprs.append(
                    f"COALESCE(TRY_CAST((SELECT _w.new_value FROM ({wb_union}) _w "
                    f"WHERE _w.instance_id = CAST(_base.{pk_ident} AS VARCHAR) "
                    f"AND _w.column_name = '{escaped_col}' "
                    f"ORDER BY _w.executed_at DESC, _w._wb_seq DESC LIMIT 1) AS {col_type}), "
                    f"_base.{col_ident}) AS {col_ident}"
                )
            else:
                select_exprs.append(f"_base.{col_ident} AS {col_ident}")
        overlay_sql = f"(SELECT {', '.join(select_exprs)} FROM {base_table} _base)"
        return overlay_sql, active_wbs

    def _check_object_access(self, obj: ObjectType, actor_role: Optional[str]) -> None:
        if obj.allowed_roles:
            if not actor_role or actor_role not in obj.allowed_roles:
                raise PermissionError(
                    f"Role '{actor_role or 'anonymous'}' is not permitted to access ObjectType '{obj.name}'. "
                    f"Allowed roles: {obj.allowed_roles}"
                )

    def _mask_sensitive_rows(
        self,
        obj: ObjectType,
        rows: List[Dict[str, Any]],
        actor_role: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        masked_props: List[str] = []
        for prop in obj.properties:
            if prop.sensitive or prop.allowed_roles:
                allowed = prop.allowed_roles or obj.allowed_roles
                if not actor_role or (allowed and actor_role not in allowed) or (not allowed and prop.sensitive):
                    masked_props.append(prop.name)
        if not masked_props or not rows:
            return rows, []
        out = []
        for r in rows:
            copy_row = dict(r)
            for mp in masked_props:
                if mp in copy_row and copy_row[mp] is not None:
                    copy_row[mp] = _REDACTED_MASK
            out.append(copy_row)
        return out, masked_props

    # --- Runtime Entity Instances, Polymorphic Interface Queries & Graph Traversal ---
    def query_object_instances(
        self,
        con: duckdb.DuckDBPyConnection,
        object_type_name: str,
        filters: Optional[str] = None,
        properties: Optional[List[str]] = None,
        limit: int = 50,
        include_writeback: bool = True,
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query real entity instances backed by DuckDB tables (or polymorphic InterfaceType)."""
        _require_positive_int(limit, "limit")
        with self._lock:
            obj = self._resolve_object_type(object_type_name)
            if not obj:
                if self._resolve_interface_type(object_type_name) is not None:
                    return self.query_interface_instances(
                        con,
                        object_type_name,
                        filters=filters,
                        properties=properties,
                        limit=limit,
                        include_writeback=include_writeback,
                        actor_role=actor_role,
                    )
                raise ValueError(f"ObjectType '{object_type_name}' is not registered in Ontology.")
            self._check_object_access(obj, actor_role)
            select_cols = _query_select(obj, properties)
            table_rel, active_wbs = self._table_source_sql(con, obj, include_writeback=include_writeback)
            where = f" WHERE {safe_predicate(filters)}" if filters else ""
            count_sql = f"SELECT COUNT(*) FROM {table_rel} _q{where}"
            sql = f"SELECT {select_cols} FROM {table_rel} _q{where} LIMIT ?"
            try:
                matched = con.execute(count_sql).fetchone()[0]
                df = con.execute(sql, [limit]).df()
            except duckdb.Error as exc:
                raise ValueError(
                    f"Failed to read ObjectType '{object_type_name}' from '{obj.backed_by_table}': {exc}"
                ) from exc
            instances = df.to_dict(orient="records")
            instances, masked_cols = self._mask_sensitive_rows(obj, instances, actor_role)
            res: Dict[str, Any] = {
                "object_type": object_type_name,
                "primary_key": obj.primary_key,
                "total_instances": len(instances),
                "matched_count": int(matched),
                "limit": limit,
                "instances": instances,
            }
            if active_wbs:
                res["writeback_applied"] = True
                res["writeback_tables"] = active_wbs
            if masked_cols:
                res["masked_properties"] = masked_cols
            return res

    def query_interface_instances(
        self,
        con: duckdb.DuckDBPyConnection,
        interface_name: str,
        filters: Optional[str] = None,
        properties: Optional[List[str]] = None,
        limit: int = 50,
        include_writeback: bool = True,
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Polymorphic query across all ObjectTypes implementing `interface_name` (including via sub-interfaces).
        Projects each implementing ObjectType's mapped properties into the canonical interface schema.
        """
        _require_positive_int(limit, "limit")
        with self._lock:
            eff_props = self.effective_interface_properties(interface_name)
            eff_map = {p.name: p for p in eff_props}
            if properties:
                unknown = [p for p in properties if p not in eff_map]
                if unknown:
                    raise ValueError(
                        f"InterfaceType '{interface_name}' has no property {unknown}. "
                        f"Declared: {list(eff_map)}"
                    )
                selected_props = [eff_map[p] for p in properties]
            else:
                selected_props = eff_props

            impl_objs = self.implementing_object_types(interface_name)
            accessible_objs = []
            for obj in impl_objs:
                if obj.allowed_roles and (not actor_role or actor_role not in obj.allowed_roles):
                    continue
                accessible_objs.append(obj)

            if not accessible_objs:
                return {
                    "interface_type": interface_name,
                    "implementing_types": [o.name for o in impl_objs],
                    "total_instances": 0,
                    "matched_count": 0,
                    "per_type_counts": {},
                    "limit": limit,
                    "instances": [],
                }

            union_parts: List[str] = []
            per_type_counts: Dict[str, int] = {}
            where_clause = f" WHERE {safe_predicate(filters)}" if filters else ""

            for obj in accessible_objs:
                obj_props = {p.name: p for p in obj.properties}
                table_rel, _ = self._table_source_sql(con, obj, include_writeback=include_writeback)
                pk_ident = safe_ident(obj.primary_key)
                escaped_obj_name = obj.name.replace("'", "''")
                proj_items = [
                    f"'{escaped_obj_name}' AS _object_type",
                    f"CAST({pk_ident} AS VARCHAR) AS _instance_id",
                ]
                for iprop in selected_props:
                    src_col = (obj.property_mappings or {}).get(iprop.name, iprop.name)
                    oprop = obj_props.get(src_col)
                    alias_ident = safe_ident(iprop.name)
                    if oprop is not None and oprop.formula:
                        proj_items.append(f"({safe_predicate(oprop.formula)}) AS {alias_ident}")
                    else:
                        proj_items.append(f"{safe_ident(src_col)} AS {alias_ident}")
                sub_sql = f"SELECT {', '.join(proj_items)} FROM {table_rel} _src"
                try:
                    cnt = con.execute(f"SELECT COUNT(*) FROM ({sub_sql}) _u{where_clause}").fetchone()[0]
                except duckdb.Error as exc:
                    raise ValueError(
                        f"Failed to query implementing ObjectType '{obj.name}' for interface '{interface_name}': {exc}"
                    ) from exc
                per_type_counts[obj.name] = int(cnt)
                union_parts.append(sub_sql)

            full_union = " UNION ALL ".join(union_parts)
            total_matched = sum(per_type_counts.values())
            final_sql = (
                f"SELECT * FROM ({full_union}) _poly{where_clause} "
                f"ORDER BY _object_type, _instance_id LIMIT ?"
            )
            df = con.execute(final_sql, [limit]).df()
            instances = df.to_dict(orient="records")
            return {
                "interface_type": interface_name,
                "implementing_types": [o.name for o in accessible_objs],
                "total_instances": len(instances),
                "matched_count": int(total_matched),
                "per_type_counts": per_type_counts,
                "limit": limit,
                "instances": instances,
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
        include_transitive: bool = False,
        include_writeback: bool = True,
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Graph Multi-Hop Traversal:
        Traverse from a source entity instance (e.g. Customer 'C01') along a link (e.g. 'customer_orders')
        to fetch all linked target entity instances (e.g. Orders).
        Supports symmetric links, transitive closure (`include_transitive=True`), and writeback overlays.
        """
        _require_positive_int(limit, "limit")
        _require_positive_int(max_hops, "max_hops")
        hops = list(link_path) if link_path else [link_name]
        if not hops:
            raise ValueError("link_path is empty")
        if hops[0] != link_name:
            raise ValueError(
                f"link_path must start with link_name '{link_name}', got '{hops[0]}'"
            )
        if len(hops) > max_hops:
            raise ValueError(f"Traversal length {len(hops)} exceeds max_hops={max_hops}")

        with self._lock:
            if include_transitive:
                if len(hops) != 1:
                    raise ValueError("include_transitive=True requires a single transitive link_name")
                t_link = self._resolve_link_type(hops[0])
                if t_link is None:
                    raise ValueError(f"LinkType '{hops[0]}' not found.")
                if not t_link.is_transitive:
                    raise ValueError(f"LinkType '{hops[0]}' is not declared is_transitive=True.")
                return self._traverse_transitive_closure(
                    con,
                    source_object_type,
                    source_instance_id,
                    t_link,
                    limit=limit,
                    max_hops=max_hops,
                    include_writeback=include_writeback,
                    actor_role=actor_role,
                )

            current_ids = [_plain(source_instance_id)]
            current_type = source_object_type
            path = [source_object_type]
            seen_types = {source_object_type}
            visited_instances = {(source_object_type, current_ids[0])}
            hop_counts: List[int] = []
            hop_details: List[Dict[str, Any]] = []
            executed: List[str] = []
            last: List[Dict[str, Any]] = []
            truncated = False
            warnings: List[str] = []
            for hop_name in hops:
                hop = self._resolve_link_type(hop_name)
                if hop is None:
                    raise ValueError(f"LinkType '{hop_name}' not found.")
                if hop.source_object_type != current_type:
                    raise ValueError(
                        f"Link '{hop_name}' expects source '{hop.source_object_type}', got '{current_type}'"
                    )
                reflexive = hop.target_object_type == hop.source_object_type
                if hop.target_object_type in seen_types and not reflexive:
                    raise ValueError(f"Cycle detected at '{hop.target_object_type}'")
                src_obj = self._resolve_object_type(hop.source_object_type)
                tgt_obj = self._resolve_object_type(hop.target_object_type)
                if src_obj is None or tgt_obj is None:
                    missing = hop.source_object_type if src_obj is None else hop.target_object_type
                    raise ValueError(
                        f"ObjectType '{missing}' referenced by link '{hop_name}' is not registered."
                    )
                self._check_object_access(src_obj, actor_role)
                self._check_object_access(tgt_obj, actor_role)
                rows, hit_limit = self._linked_rows(
                    con, hop, src_obj, tgt_obj, current_ids, limit, include_writeback=include_writeback
                )
                rows, _ = self._mask_sensitive_rows(tgt_obj, rows, actor_role)
                if reflexive:
                    kept = []
                    for row in rows:
                        pk_value = _pk_of(row, tgt_obj.primary_key, tgt_obj.name)
                        marker = (tgt_obj.name, pk_value)
                        if marker in visited_instances:
                            continue
                        kept.append(row)
                    rows = kept
                last = rows
                hop_counts.append(len(last))
                pk_values: List[Any] = []
                seen_pk = set()
                for row in last:
                    pk_value = _pk_of(row, tgt_obj.primary_key, tgt_obj.name)
                    visited_instances.add((tgt_obj.name, pk_value))
                    if pk_value in seen_pk:
                        continue
                    seen_pk.add(pk_value)
                    pk_values.append(pk_value)
                warning = None
                if hop.cardinality in _SINGLE_TARGET and len(last) > 1:
                    warning = (
                        f"{hop.cardinality} link '{hop.name}' returned {len(last)} targets "
                        f"for one hop; the backing rows are not unique on the join."
                    )
                    warnings.append(warning)
                current_ids = pk_values
                current_type = tgt_obj.name
                path.append(current_type)
                seen_types.add(current_type)
                executed.append(hop_name)
                hop_details.append({
                    "link_name": hop_name,
                    "source_object_type": hop.source_object_type,
                    "target_object_type": tgt_obj.name,
                    "cardinality": hop.cardinality,
                    "count": len(last),
                    "instance_ids": list(pk_values),
                    "truncated": hit_limit,
                    "cardinality_warning": warning,
                })
                if hit_limit:
                    truncated = True
                if not current_ids:
                    break
            return {
                "source_object_type": source_object_type,
                "source_instance_id": source_instance_id,
                "link_name": executed[-1] if executed else link_name,
                "target_object_type": current_type,
                "hops": len(path) - 1,
                "requested_hops": len(hops),
                "path": path,
                "hop_counts": hop_counts,
                "hop_details": hop_details,
                "truncated": truncated,
                "cardinality_warnings": warnings,
                "linked_count": len(last),
                "linked_instances": last,
            }

    def _traverse_transitive_closure(
        self,
        con: duckdb.DuckDBPyConnection,
        source_object_type: str,
        source_instance_id: Any,
        link: LinkType,
        limit: int,
        max_hops: int,
        include_writeback: bool,
        actor_role: Optional[str],
    ) -> Dict[str, Any]:
        if link.source_object_type != source_object_type:
            raise ValueError(
                f"Link '{link.name}' expects source '{link.source_object_type}', got '{source_object_type}'"
            )
        obj = self._resolve_object_type(source_object_type)
        if obj is None:
            raise ValueError(f"ObjectType '{source_object_type}' is not registered.")
        self._check_object_access(obj, actor_role)

        frontier = [_plain(source_instance_id)]
        visited = {(obj.name, frontier[0])}
        all_reachable: List[Dict[str, Any]] = []
        hop_counts: List[int] = []
        hop_details: List[Dict[str, Any]] = []
        path = [source_object_type]
        truncated = False

        for depth in range(1, max_hops + 1):
            if not frontier:
                break
            rows, hit_limit = self._linked_rows(
                con, link, obj, obj, frontier, limit, include_writeback=include_writeback
            )
            rows, _ = self._mask_sensitive_rows(obj, rows, actor_role)
            new_rows = []
            next_frontier = []
            for row in rows:
                pk_val = _pk_of(row, obj.primary_key, obj.name)
                marker = (obj.name, pk_val)
                if marker in visited:
                    continue
                visited.add(marker)
                enriched = dict(row)
                enriched["_hop_distance"] = depth
                new_rows.append(enriched)
                next_frontier.append(pk_val)
            if not new_rows and depth > 1:
                break
            path.append(obj.name)
            hop_counts.append(len(new_rows))
            hop_details.append({
                "link_name": link.name,
                "hop_depth": depth,
                "source_object_type": obj.name,
                "target_object_type": obj.name,
                "cardinality": link.cardinality,
                "count": len(new_rows),
                "instance_ids": list(next_frontier),
                "truncated": hit_limit,
                "cardinality_warning": None,
            })
            all_reachable.extend(new_rows)
            if hit_limit or len(all_reachable) >= limit:
                truncated = hit_limit or (len(all_reachable) > limit)
                all_reachable = all_reachable[:limit]
                break
            frontier = next_frontier

        return {
            "source_object_type": source_object_type,
            "source_instance_id": source_instance_id,
            "link_name": link.name,
            "target_object_type": obj.name,
            "transitive_closure": True,
            "hops": len(hop_counts),
            "requested_hops": max_hops,
            "path": path,
            "hop_counts": hop_counts,
            "hop_details": hop_details,
            "truncated": truncated,
            "cardinality_warnings": [],
            "linked_count": len(all_reachable),
            "linked_instances": all_reachable,
        }

    def _linked_rows(
        self,
        con: duckdb.DuckDBPyConnection,
        link: LinkType,
        src_obj: ObjectType,
        tgt_obj: ObjectType,
        source_ids: List[Any],
        limit: int,
        include_writeback: bool = True,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        if not source_ids:
            return [], False
        projection = _outer_projection(tgt_obj)
        placeholders = ", ".join(["?"] * len(source_ids))
        pk = safe_ident(tgt_obj.primary_key)
        from_clause = self._from_clause(con, link, src_obj, tgt_obj, include_writeback=include_writeback)
        inner = (
            f"SELECT tgt.* FROM {from_clause} "
            f"WHERE src.{safe_ident(src_obj.primary_key)} IN ({placeholders})"
        )
        sql = f"SELECT DISTINCT {projection} FROM ({inner}) q ORDER BY {pk} LIMIT ?"
        try:
            df = con.execute(sql, [*source_ids, limit + 1]).df()
        except duckdb.Error as exc:
            raise ValueError(f"Traversal along '{link.name}' failed: {exc}") from exc
        rows = df.to_dict(orient="records")
        hit_limit = len(rows) > limit
        if hit_limit:
            rows = rows[:limit]
        return rows, hit_limit

    def _from_clause(
        self,
        con: duckdb.DuckDBPyConnection,
        link: LinkType,
        src_obj: ObjectType,
        tgt_obj: ObjectType,
        include_writeback: bool = True,
    ) -> str:
        """FROM/JOIN fragment. MANY_TO_MANY goes through the junction table; symmetric links match both ways."""
        src_table, _ = self._table_source_sql(con, src_obj, include_writeback=include_writeback)
        tgt_table, _ = self._table_source_sql(con, tgt_obj, include_writeback=include_writeback)
        s_key = safe_ident(link.source_join_key)
        t_key = safe_ident(link.target_join_key)
        if link.cardinality == "MANY_TO_MANY":
            if not (link.junction_table and link.junction_source_key and link.junction_target_key):
                raise ValueError(
                    f"MANY_TO_MANY link '{link.name}' requires junction_table, "
                    "junction_source_key, and junction_target_key"
                )
            junction = safe_table_ref(link.junction_table)
            j_src = safe_ident(link.junction_source_key)
            j_tgt = safe_ident(link.junction_target_key)
            if link.is_symmetric:
                return (
                    f"{tgt_table} tgt "
                    f"JOIN {junction} j "
                    f"ON (j.{j_tgt} = tgt.{t_key} OR j.{j_src} = tgt.{t_key}) "
                    f"JOIN {src_table} src "
                    f"ON ((src.{s_key} = j.{j_src} AND tgt.{t_key} = j.{j_tgt}) "
                    f"OR (src.{s_key} = j.{j_tgt} AND tgt.{t_key} = j.{j_src}))"
                )
            return (
                f"{tgt_table} tgt "
                f"JOIN {junction} j "
                f"ON j.{j_tgt} = tgt.{t_key} "
                f"JOIN {src_table} src "
                f"ON src.{s_key} = j.{j_src}"
            )
        if link.is_symmetric:
            return (
                f"{tgt_table} tgt "
                f"JOIN {src_table} src "
                f"ON (src.{s_key} = tgt.{t_key} OR src.{t_key} = tgt.{s_key})"
            )
        return (
            f"{tgt_table} tgt "
            f"JOIN {src_table} src "
            f"ON src.{s_key} = tgt.{t_key}"
        )

    # --- Functions on Objects (FoO) Evaluation ---
    def evaluate_function(
        self,
        con: duckdb.DuckDBPyConnection,
        function_name: str,
        instance_id: Optional[Any] = None,
        parameter_values: Optional[Dict[str, Any]] = None,
        filters: Optional[str] = None,
        target_object_type: Optional[str] = None,
        limit: int = 50,
        include_writeback: bool = True,
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a registered FunctionType ('Function on Objects') over a single instance or filtered set
        of instances in DuckDB. Supports polymorphic functions bound to an InterfaceType.
        """
        _require_positive_int(limit, "limit")
        with self._lock:
            fn = self._resolve_function_type(function_name)
            if not fn:
                raise ValueError(f"FunctionType '{function_name}' is not registered in Ontology.")
            params = _prepare_parameters(fn, parameter_values)
            target_objs = self._resolve_target_objects(
                con, fn.target_object_type, None, instance_id, target_object_type
            )
            for obj in target_objs:
                self._check_object_access(obj, actor_role)

            formatted_expr = _bind_sql_expression(fn.sql_expression, params)
            safe_predicate(formatted_expr)

            results: List[Dict[str, Any]] = []
            for obj in target_objs:
                table_rel, _ = self._table_source_sql(con, obj, include_writeback=include_writeback)
                pk_ident = safe_ident(obj.primary_key)
                expr_for_obj = self._rewrite_interface_expr(formatted_expr, fn.target_object_type, obj)
                where_parts: List[str] = []
                bound_args: List[Any] = []
                if instance_id is not None:
                    where_parts.append(f"{pk_ident} = ?")
                    bound_args.append(_plain(instance_id))
                if filters:
                    where_parts.append(f"({safe_predicate(filters)})")
                where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
                sql = (
                    f"SELECT {pk_ident} AS _instance_id, ({expr_for_obj}) AS _fn_val "
                    f"FROM {table_rel} _src{where_sql} ORDER BY {pk_ident} LIMIT ?"
                )
                try:
                    rows = con.execute(sql, [*bound_args, limit]).fetchall()
                except duckdb.Error as exc:
                    raise ValueError(
                        f"Function '{function_name}' execution failed on '{obj.name}': {exc}"
                    ) from exc
                for r in rows:
                    coerced = _coerce_return_value(r[1], fn.return_type)
                    results.append({
                        "object_type": obj.name,
                        "instance_id": _plain(r[0]),
                        "result": coerced,
                    })
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break

            if instance_id is not None and not results:
                raise ValueError(
                    f"Instance '{instance_id}' not found on '{fn.target_object_type}' for function '{function_name}'."
                )

            payload: Dict[str, Any] = {
                "function_name": fn.name,
                "target_object_type": fn.target_object_type,
                "return_type": fn.return_type,
                "parameters": params,
                "results": results,
            }
            if instance_id is not None and results:
                payload["result"] = results[0]["result"]
            return payload

    def _rewrite_interface_expr(self, expr: str, target_name: str, obj: ObjectType) -> str:
        """If `target_name` is an InterfaceType and `obj` defines `property_mappings`, rewrite interface column names."""
        if self._resolve_interface_type(target_name) is None or not obj.property_mappings:
            return expr
        rewritten = expr
        for iface_col, obj_col in obj.property_mappings.items():
            if iface_col != obj_col:
                rewritten = re.sub(rf"\b{re.escape(iface_col)}\b", obj_col, rewritten)
        return rewritten

    def _resolve_target_objects(
        self,
        con: duckdb.DuckDBPyConnection,
        declared_target: str,
        declared_interface: Optional[str],
        instance_id: Optional[Any],
        explicit_object_type: Optional[str] = None,
    ) -> List[ObjectType]:
        iface_name = declared_interface
        if not iface_name and self._resolve_interface_type(declared_target) is not None:
            iface_name = declared_target

        if iface_name:
            impl_objs = self.implementing_object_types(iface_name)
            if not impl_objs:
                raise ValueError(
                    f"InterfaceType '{iface_name}' has no implementing ObjectTypes registered."
                )
            if explicit_object_type:
                matched = [o for o in impl_objs if o.name == explicit_object_type]
                if not matched:
                    raise ValueError(
                        f"ObjectType '{explicit_object_type}' does not implement InterfaceType '{iface_name}'."
                    )
                return matched
            if instance_id is not None:
                found_objs = []
                for o in impl_objs:
                    if self._snapshot_instance(con, o.name, instance_id) is not None:
                        found_objs.append(o)
                if len(found_objs) == 1:
                    return found_objs
                if len(found_objs) > 1:
                    raise ValueError(
                        f"Instance '{instance_id}' matches multiple ObjectTypes {[o.name for o in found_objs]} "
                        f"implementing '{iface_name}'. Pass target_object_type explicitly."
                    )
            return impl_objs

        obj = self._resolve_object_type(declared_target)
        if obj is None:
            raise ValueError(f"ObjectType '{declared_target}' is not registered in Ontology.")
        return [obj]

    # --- Action Execution, Preconditions, RBAC & Audit Trail ---
    def execute_action(
        self,
        con: duckdb.DuckDBPyConnection,
        action_name: str,
        instance_id: Any,
        parameter_values: Dict[str, Any],
        dry_run: bool = False,
        target_object_type: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an atomic business action on an object instance with parameter validation,
        RBAC checks, closed-world precondition verification, and immutable audit trail.
        """
        with self._lock:
            action = self._resolve_action_type(action_name)
            if not action:
                raise ValueError(f"ActionType '{action_name}' is not registered in Ontology.")
            params = _prepare_parameters(action, parameter_values)
            resolved_objs = self._resolve_target_objects(
                con, action.target_object_type, action.target_interface, instance_id, target_object_type
            )
            target_obj = resolved_objs[0]
            target_type = target_obj.name
            handler = (action.handler_type or "").upper()
            config = dict(action.handler_config or {})
            display = action.display_name or action.name

            # 1. Governance / RBAC check (Fail-Closed)
            required_roles = action.allowed_roles or target_obj.allowed_roles
            if required_roles and (not actor_role or actor_role not in required_roles):
                return self._record_audit(
                    action_name=action_name,
                    target_type=target_type,
                    instance_id=instance_id,
                    params=params,
                    status="FAILED",
                    actor_role=actor_role,
                    precondition_results=[],
                    exec_result={
                        "status": "FAILED",
                        "reason": "PERMISSION_DENIED",
                        "message": (
                            f"Role '{actor_role or 'anonymous'}' is not authorized to execute "
                            f"action '{action_name}'. Required roles: {required_roles}"
                        ),
                    },
                )

            # 2. Closed-World Precondition Verification (CWA Guardrails)
            precond_results: List[Dict[str, Any]] = []
            if action.preconditions:
                all_passed, precond_results, fail_msg = self._evaluate_preconditions(
                    con, target_obj, action, instance_id, params
                )
                if not all_passed:
                    before = self._snapshot_instance(con, target_type, instance_id, include_writeback=True)
                    return self._record_audit(
                        action_name=action_name,
                        target_type=target_type,
                        instance_id=instance_id,
                        params=params,
                        status="FAILED",
                        actor_role=actor_role,
                        precondition_results=precond_results,
                        exec_result={
                            "status": "FAILED",
                            "reason": "PRECONDITION_FAILED",
                            "message": fail_msg,
                            "failed_preconditions": [
                                p["name"] for p in precond_results if not p["passed"]
                            ],
                            "before": before,
                        },
                    )

        if dry_run:
            status = "SIMULATED"
            exec_result: Dict[str, Any] = {"status": "SIMULATED", "params": params}
            if precond_results:
                exec_result["preconditions_passed"] = True
        else:
            status, exec_result = self._run_handler(
                con, action_name, target_type, handler, config, display, instance_id, params
            )

        return self._record_audit(
            action_name=action_name,
            target_type=target_type,
            instance_id=instance_id,
            params=params,
            status=status,
            actor_role=actor_role,
            precondition_results=precond_results,
            exec_result=exec_result,
        )

    def _record_audit(
        self,
        *,
        action_name: str,
        target_type: str,
        instance_id: Any,
        params: Dict[str, Any],
        status: str,
        actor_role: Optional[str],
        precondition_results: List[Dict[str, Any]],
        exec_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        audit_id = f"aud_{uuid.uuid4().hex[:10]}"
        audit_record = ActionExecutionAudit(
            audit_id=audit_id,
            action_name=action_name,
            target_object_type=target_type,
            target_instance_id=str(instance_id),
            parameters=params,
            status=status,
            actor_role=actor_role,
            precondition_results=precondition_results,
            execution_result=exec_result,
        )
        dumped = audit_record.model_dump()
        with self._lock:
            if self.persistent and self.db:
                self.db.save_action_audit(dumped)
            else:
                self._memory_audits.insert(0, dumped)
                if action_name not in self._action_types:
                    g = self._fallback_global()
                    if g is not None and g.db is not None:
                        g.db.save_action_audit(dumped)
        return dumped

    def _evaluate_preconditions(
        self,
        con: duckdb.DuckDBPyConnection,
        target_obj: ObjectType,
        action: ActionType,
        instance_id: Any,
        params: Dict[str, Any],
    ) -> Tuple[bool, List[Dict[str, Any]], str]:
        table_rel, _ = self._table_source_sql(con, target_obj, include_writeback=True)
        pk_ident = safe_ident(target_obj.primary_key)
        try:
            exists_cnt = con.execute(
                f"SELECT COUNT(*) FROM {table_rel} _src WHERE {pk_ident} = ?",
                [_plain(instance_id)],
            ).fetchone()[0]
        except duckdb.Error as exc:
            return False, [{
                "name": "_instance_exists",
                "sql_predicate": f"{target_obj.primary_key} = ?",
                "passed": False,
                "description": f"Database error reading target '{target_obj.name}': {exc}",
            }], f"Precondition check failed to read '{target_obj.name}': {exc}"

        if not exists_cnt:
            return False, [{
                "name": "_instance_exists",
                "sql_predicate": f"{target_obj.primary_key} = {instance_id!r}",
                "passed": False,
                "description": f"Target instance '{instance_id}' does not exist in '{target_obj.name}'.",
            }], f"Target instance '{instance_id}' does not exist in '{target_obj.name}'."

        results: List[Dict[str, Any]] = []
        failed_names: List[str] = []
        iface_target = action.target_interface or (
            action.target_object_type if self._resolve_interface_type(action.target_object_type) else None
        )
        for pre in action.preconditions:
            bound_pred = _bind_sql_expression(pre.sql_predicate, {"instance_id": instance_id, **params})
            if iface_target:
                bound_pred = self._rewrite_interface_expr(bound_pred, iface_target, target_obj)
            safe_predicate(bound_pred)
            sql = f"SELECT COUNT(*) FROM {table_rel} _src WHERE {pk_ident} = ? AND ({bound_pred})"
            try:
                matched = con.execute(sql, [_plain(instance_id)]).fetchone()[0]
                passed = bool(matched > 0)
            except duckdb.Error as exc:
                passed = False
            results.append({
                "name": pre.name,
                "sql_predicate": pre.sql_predicate,
                "passed": passed,
                "description": pre.description or "",
            })
            if not passed:
                failed_names.append(pre.name)

        if failed_names:
            return (
                False,
                results,
                f"Action '{action.name}' blocked by failed preconditions: {failed_names}",
            )
        return True, results, ""

    def _run_handler(
        self,
        con: duckdb.DuckDBPyConnection,
        action_name: str,
        target_type: str,
        handler: str,
        config: Dict[str, Any],
        display: str,
        instance_id: Any,
        params: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        if handler == "WEBHOOK":
            return _run_webhook(action_name, target_type, config, display, instance_id, params)
        if handler == "SQL_MUTATION":
            return self._run_sql_mutation(con, target_type, config, instance_id, params)
        if handler == "REVERSE_ETL_SYNC":
            return _run_reverse_etl(con, config)
        if handler == "FUNCTION":
            return self._run_function_handler(con, target_type, config, instance_id, params)
        return "FAILED", {
            "status": "FAILED",
            "message": f"Unsupported handler_type '{handler}'. Nothing was executed.",
        }

    def _run_function_handler(
        self,
        con: duckdb.DuckDBPyConnection,
        target_type: str,
        cfg: Dict[str, Any],
        instance_id: Any,
        params: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        fn_name = cfg.get("function_name")
        if not fn_name:
            return "FAILED", {
                "status": "FAILED",
                "message": "FUNCTION handler requires 'function_name' in handler_config.",
            }
        before = self._snapshot_instance(con, target_type, instance_id)
        try:
            eval_res = self.evaluate_function(
                con,
                fn_name,
                instance_id=instance_id,
                parameter_values=params,
                target_object_type=target_type,
            )
            computed_val = eval_res.get("result")
            result_payload: Dict[str, Any] = {
                "status": "SUCCESS",
                "function_name": fn_name,
                "computed_value": computed_val,
                "before": before,
            }
            if cfg.get("writeback_table"):
                wb = safe_table_ref(cfg["writeback_table"])
                col_name = cfg.get("set_column", fn_name)
                safe_ident(col_name)
                statement = (
                    f"INSERT INTO {wb} (instance_id, column_name, new_value, executed_at) "
                    "VALUES (?, ?, ?, current_timestamp)"
                )
                con.execute(
                    f"CREATE TABLE IF NOT EXISTS {wb} ("
                    "instance_id VARCHAR, column_name VARCHAR, new_value VARCHAR, executed_at TIMESTAMP)"
                )
                bound = [str(instance_id), str(col_name), str(computed_val)]
                con.execute(statement, bound)
                result_payload["writeback_table"] = cfg["writeback_table"]
                result_payload["after"] = {
                    "writeback_table": cfg["writeback_table"],
                    "column_name": col_name,
                    "new_value": str(computed_val),
                }
                result_payload["statement_hash"] = _statement_hash(statement, bound)
            else:
                result_payload["statement_hash"] = _statement_hash(f"FUNCTION:{fn_name}", [instance_id, params])
            return "SUCCESS", result_payload
        except Exception as exc:
            return "FAILED", {"status": "FAILED", "message": str(exc), "before": before}

    def _run_sql_mutation(
        self,
        con: duckdb.DuckDBPyConnection,
        target_type: str,
        cfg: Dict[str, Any],
        instance_id: Any,
        params: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        has_writeback = bool(cfg.get("writeback_table"))
        template = cfg.get("sql_template") or ""
        if has_writeback and template:
            return "FAILED", {
                "status": "FAILED",
                "message": "SQL_MUTATION cannot set both writeback_table and sql_template. Nothing was written.",
            }
        if not has_writeback and not template:
            return "FAILED", {
                "status": "FAILED",
                "message": "SQL_MUTATION needs writeback_table or sql_template. Nothing was written.",
            }
        before = self._snapshot_instance(con, target_type, instance_id)
        try:
            if has_writeback:
                wb = safe_table_ref(cfg["writeback_table"])
                value_param = cfg.get("value_param", "value")
                column_name = cfg.get("set_column", value_param)
                safe_ident(column_name)
                statement = (
                    f"INSERT INTO {wb} (instance_id, column_name, new_value, executed_at) "
                    "VALUES (?, ?, ?, current_timestamp)"
                )
                con.execute(
                    f"CREATE TABLE IF NOT EXISTS {wb} ("
                    "instance_id VARCHAR, column_name VARCHAR, new_value VARCHAR, executed_at TIMESTAMP)"
                )
                bound = [str(instance_id), str(column_name), str(params.get(value_param))]
                con.execute(statement, bound)
                after = {
                    "writeback_table": cfg["writeback_table"],
                    "column_name": column_name,
                    "new_value": bound[2],
                    "note": "Edit stored beside the source table. The backing table was not updated.",
                }
                return "SUCCESS", {
                    "status": "SUCCESS",
                    "writeback_table": cfg["writeback_table"],
                    "note": after["note"],
                    "before": before,
                    "after": after,
                    "statement_hash": _statement_hash(statement, bound),
                }
            subs = {"instance_id": instance_id, **params}
            for key, value in subs.items():
                if isinstance(value, str) and any(token in value for token in ("'", '"', ";", "--", "/*")):
                    raise ValueError(f"Unsafe character in SQL_MUTATION parameter '{key}': {value!r}")
            obj = self._resolve_object_type(target_type)
            raw_template = template
            if obj is not None and "{backed_by_table}" in raw_template:
                raw_template = raw_template.replace("{backed_by_table}", safe_table_ref(obj.backed_by_table))
            if obj is not None and "{primary_key}" in raw_template:
                raw_template = raw_template.replace("{primary_key}", safe_ident(obj.primary_key))
            formatted_sql = raw_template.format(**subs)
            con.execute(formatted_sql)
            after = self._snapshot_instance(con, target_type, instance_id)
            return "SUCCESS", {
                "status": "SUCCESS",
                "executed_sql": formatted_sql,
                "before": before,
                "after": after,
                "statement_hash": _statement_hash(formatted_sql),
            }
        except duckdb.Error as exc:
            return "FAILED", {"status": "FAILED", "message": str(exc), "before": before}

    def _snapshot_instance(
        self,
        con: duckdb.DuckDBPyConnection,
        object_type_name: str,
        instance_id: Any,
        include_writeback: bool = False,
    ):
        with self._lock:
            obj = self._resolve_object_type(object_type_name)
        if obj is None:
            return None
        try:
            table_rel, _ = self._table_source_sql(con, obj, include_writeback=include_writeback)
            df = con.execute(
                f"SELECT * FROM {table_rel} _snap WHERE {safe_ident(obj.primary_key)} = ?",
                [_plain(instance_id)],
            ).df()
        except duckdb.Error:
            return None
        if df.empty:
            return None
        return json.loads(df.head(1).to_json(orient="records", date_format="iso"))[0]

    def list_action_audits(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            if self.persistent and self.db:
                return self.db.list_action_audits(limit=limit)
            return self._memory_audits[:limit]

    # --- Formal Ontological Commitment & Closed-World Consistency Validator ---
    def validate_ontological_commitment(
        self,
        con: duckdb.DuckDBPyConnection,
        object_type_name: Optional[str] = None,
        include_writeback: bool = True,
    ) -> Dict[str, Any]:
        """
        SHACL-style & Guarino Ontological Commitment validator over live DuckDB tables:
        Verifies primary key uniqueness/non-null, property constraints (`required`, `unique`,
        `min_value`, `max_value`, `allowed_values`), mutual exclusion (`disjoint_with`),
        interface implementation conformance, and link cardinality / referential integrity.
        """
        with self._lock:
            violations: List[Dict[str, Any]] = []
            if object_type_name:
                target = self._resolve_object_type(object_type_name)
                if not target:
                    raise ValueError(f"ObjectType '{object_type_name}' is not registered in Ontology.")
                objects_to_check = [target]
                links_source = self._link_types if self._link_types else (
                    self._fallback_global()._link_types if self._fallback_global() else {}
                )
            else:
                if self._object_types:
                    objects_to_check = list(self._object_types.values())
                    links_source = self._link_types
                elif self._fallback_global() is not None:
                    objects_to_check = list(self._fallback_global()._object_types.values())
                    links_source = self._fallback_global()._link_types
                else:
                    objects_to_check = []
                    links_source = {}

            checked_objects: List[str] = []
            checked_links: List[str] = []

            for obj in objects_to_check:
                checked_objects.append(obj.name)
                table_rel, _ = self._table_source_sql(con, obj, include_writeback=include_writeback)
                pk = safe_ident(obj.primary_key)
                try:
                    null_pks = con.execute(
                        f"SELECT COUNT(*) FROM {table_rel} _t WHERE {pk} IS NULL"
                    ).fetchone()[0]
                    if null_pks > 0:
                        violations.append({
                            "rule": "PK_NON_NULL",
                            "object_type": obj.name,
                            "property": obj.primary_key,
                            "violation_count": int(null_pks),
                            "message": f"ObjectType '{obj.name}' has {null_pks} rows with NULL primary key '{obj.primary_key}'.",
                        })
                    dup_pks = con.execute(
                        f"SELECT COUNT(*) FROM (SELECT {pk} FROM {table_rel} _t WHERE {pk} IS NOT NULL GROUP BY {pk} HAVING COUNT(*) > 1)"
                    ).fetchone()[0]
                    if dup_pks > 0:
                        violations.append({
                            "rule": "PK_UNIQUE",
                            "object_type": obj.name,
                            "property": obj.primary_key,
                            "violation_count": int(dup_pks),
                            "message": f"ObjectType '{obj.name}' has {dup_pks} duplicate primary key values on '{obj.primary_key}'.",
                        })
                except duckdb.Error as exc:
                    violations.append({
                        "rule": "BACKING_TABLE_EXISTS",
                        "object_type": obj.name,
                        "violation_count": 1,
                        "message": f"Failed to inspect backing table '{obj.backed_by_table}': {exc}",
                    })
                    continue

                # Property-level closed-world constraints
                for prop in obj.properties:
                    if prop.formula:
                        continue
                    col = safe_ident(prop.name)
                    if prop.required:
                        cnt = con.execute(
                            f"SELECT COUNT(*) FROM {table_rel} _t WHERE {col} IS NULL"
                        ).fetchone()[0]
                        if cnt > 0:
                            violations.append({
                                "rule": "PROPERTY_REQUIRED",
                                "object_type": obj.name,
                                "property": prop.name,
                                "violation_count": int(cnt),
                                "message": f"Required property '{obj.name}.{prop.name}' has {cnt} NULL values.",
                            })
                    if prop.unique:
                        cnt = con.execute(
                            f"SELECT COUNT(*) FROM (SELECT {col} FROM {table_rel} _t WHERE {col} IS NOT NULL GROUP BY {col} HAVING COUNT(*) > 1)"
                        ).fetchone()[0]
                        if cnt > 0:
                            violations.append({
                                "rule": "PROPERTY_UNIQUE",
                                "object_type": obj.name,
                                "property": prop.name,
                                "violation_count": int(cnt),
                                "message": f"Unique property '{obj.name}.{prop.name}' has {cnt} duplicate values.",
                            })
                    if prop.min_value is not None:
                        cnt = con.execute(
                            f"SELECT COUNT(*) FROM {table_rel} _t WHERE {col} IS NOT NULL AND {col} < ?",
                            [prop.min_value],
                        ).fetchone()[0]
                        if cnt > 0:
                            violations.append({
                                "rule": "PROPERTY_MIN_VALUE",
                                "object_type": obj.name,
                                "property": prop.name,
                                "violation_count": int(cnt),
                                "message": f"Property '{obj.name}.{prop.name}' has {cnt} values below min_value={prop.min_value}.",
                            })
                    if prop.max_value is not None:
                        cnt = con.execute(
                            f"SELECT COUNT(*) FROM {table_rel} _t WHERE {col} IS NOT NULL AND {col} > ?",
                            [prop.max_value],
                        ).fetchone()[0]
                        if cnt > 0:
                            violations.append({
                                "rule": "PROPERTY_MAX_VALUE",
                                "object_type": obj.name,
                                "property": prop.name,
                                "violation_count": int(cnt),
                                "message": f"Property '{obj.name}.{prop.name}' has {cnt} values above max_value={prop.max_value}.",
                            })
                    if prop.allowed_values:
                        placeholders = ", ".join(["?"] * len(prop.allowed_values))
                        cnt = con.execute(
                            f"SELECT COUNT(*) FROM {table_rel} _t WHERE {col} IS NOT NULL AND {col} NOT IN ({placeholders})",
                            list(prop.allowed_values),
                        ).fetchone()[0]
                        if cnt > 0:
                            violations.append({
                                "rule": "PROPERTY_ALLOWED_VALUES",
                                "object_type": obj.name,
                                "property": prop.name,
                                "violation_count": int(cnt),
                                "message": f"Property '{obj.name}.{prop.name}' has {cnt} values outside allowed_values={prop.allowed_values}.",
                            })

                # Disjointness axiom check (Guarino ontological commitment)
                for other_name in obj.disjoint_with or []:
                    other_obj = self._resolve_object_type(other_name)
                    if other_obj is None:
                        continue
                    other_rel, _ = self._table_source_sql(con, other_obj, include_writeback=include_writeback)
                    other_pk = safe_ident(other_obj.primary_key)
                    try:
                        overlap = con.execute(
                            f"SELECT COUNT(*) FROM (SELECT DISTINCT CAST({pk} AS VARCHAR) AS k FROM {table_rel} _a) a "
                            f"JOIN (SELECT DISTINCT CAST({other_pk} AS VARCHAR) AS k FROM {other_rel} _b) b ON a.k = b.k"
                        ).fetchone()[0]
                        if overlap > 0:
                            violations.append({
                                "rule": "DISJOINT_WITH",
                                "object_type": obj.name,
                                "disjoint_object_type": other_name,
                                "violation_count": int(overlap),
                                "message": (
                                    f"Disjoint ObjectTypes '{obj.name}' and '{other_name}' share "
                                    f"{overlap} overlapping primary key instance(s)."
                                ),
                            })
                    except duckdb.Error:
                        pass

            # Link cardinality & referential integrity checks
            checked_set = set(checked_objects)
            for link in links_source.values():
                if object_type_name and link.source_object_type not in checked_set and link.target_object_type not in checked_set:
                    continue
                src_obj = self._resolve_object_type(link.source_object_type)
                tgt_obj = self._resolve_object_type(link.target_object_type)
                if not src_obj or not tgt_obj:
                    continue
                checked_links.append(link.name)
                try:
                    src_rel, _ = self._table_source_sql(con, src_obj, include_writeback=include_writeback)
                    tgt_rel, _ = self._table_source_sql(con, tgt_obj, include_writeback=include_writeback)
                    s_key = safe_ident(link.source_join_key)
                    t_key = safe_ident(link.target_join_key)
                    if link.cardinality in _SINGLE_TARGET:
                        multi_targets = con.execute(
                            f"SELECT COUNT(*) FROM ("
                            f"SELECT src.{safe_ident(src_obj.primary_key)} FROM {src_rel} src "
                            f"JOIN {tgt_rel} tgt ON src.{s_key} = tgt.{t_key} "
                            f"GROUP BY src.{safe_ident(src_obj.primary_key)} HAVING COUNT(DISTINCT tgt.{safe_ident(tgt_obj.primary_key)}) > 1)"
                        ).fetchone()[0]
                        if multi_targets > 0:
                            violations.append({
                                "rule": "LINK_CARDINALITY",
                                "link_name": link.name,
                                "cardinality": link.cardinality,
                                "violation_count": int(multi_targets),
                                "message": (
                                    f"{link.cardinality} link '{link.name}' has {multi_targets} source instance(s) "
                                    "pointing to multiple target instances."
                                ),
                            })
                except duckdb.Error:
                    pass

            return {
                "conforms": len(violations) == 0,
                "violation_count": len(violations),
                "violations": violations,
                "checked_objects": checked_objects,
                "checked_links": checked_links,
            }

    # --- Schema Validation Helpers ---
    def _validate_interface_type(self, iface: InterfaceType) -> None:
        if not (iface.name or "").strip():
            raise ValueError("InterfaceType name is required")
        if iface.name in self._interface_cycle_parents(iface.name, iface.extends or []):
            raise ValueError(f"InterfaceType '{iface.name}' has an inheritance cycle in extends={iface.extends}")
        prop_names = [p.name for p in iface.required_properties]
        if len(prop_names) != len(set(prop_names)):
            raise ValueError(f"InterfaceType '{iface.name}' has duplicate required_properties")
        for p in iface.required_properties:
            safe_ident(p.name)
            _normalize_property_type(p.data_type)
        # Validate parent property compatibility
        inherited: Dict[str, str] = {}
        for parent_name in iface.extends or []:
            parent_props = self.effective_interface_properties(parent_name)
            for pp in parent_props:
                p_norm = _normalize_property_type(pp.data_type)
                if pp.name in inherited and inherited[pp.name] != p_norm:
                    raise ValueError(
                        f"InterfaceType '{iface.name}' inherits conflicting types for '{pp.name}'"
                    )
                inherited[pp.name] = p_norm
        for p in iface.required_properties:
            p_norm = _normalize_property_type(p.data_type)
            if p.name in inherited and inherited[p.name] != p_norm:
                raise ValueError(
                    f"InterfaceType '{iface.name}' property '{p.name}' ({p_norm}) conflicts with "
                    f"inherited property type ({inherited[p.name]})"
                )

    def _interface_cycle_parents(self, root_name: str, extends: List[str]) -> Set[str]:
        visited: Set[str] = set()
        stack = list(extends)
        while stack:
            curr = stack.pop()
            if curr == root_name:
                visited.add(curr)
                return visited
            parent = self._resolve_interface_type(curr)
            if parent is None:
                raise ValueError(
                    f"InterfaceType '{root_name}' extends unregistered InterfaceType '{curr}'"
                )
            if curr not in visited:
                visited.add(curr)
                stack.extend(parent.extends or [])
        return visited

    def _validate_object_type(self, obj: ObjectType) -> None:
        if not (obj.name or "").strip():
            raise ValueError("ObjectType name is required")
        if not (obj.primary_key or "").strip():
            raise ValueError(f"ObjectType '{obj.name}' requires a primary_key")
        if not (obj.backed_by_table or "").strip():
            raise ValueError(f"ObjectType '{obj.name}' requires backed_by_table")
        safe_ident(obj.primary_key)
        safe_table_ref(obj.backed_by_table)
        if obj.writeback_table:
            safe_table_ref(obj.writeback_table)
        if obj.name in (obj.disjoint_with or []):
            raise ValueError(f"ObjectType '{obj.name}' cannot be disjoint_with itself")
        names = [prop.name for prop in obj.properties]
        if len(names) != len(set(names)):
            raise ValueError(f"ObjectType '{obj.name}' has duplicate properties")
        prop_by_name = {prop.name: prop for prop in obj.properties}
        for prop in obj.properties:
            safe_ident(prop.name)
            if prop.formula:
                safe_predicate(prop.formula)
            if prop.min_value is not None and prop.max_value is not None and prop.min_value > prop.max_value:
                raise ValueError(
                    f"Property '{obj.name}.{prop.name}' min_value ({prop.min_value}) > max_value ({prop.max_value})"
                )
        flagged = [prop.name for prop in obj.properties if prop.is_primary_key]
        if flagged and flagged != [obj.primary_key]:
            raise ValueError(
                f"ObjectType '{obj.name}' primary_key is '{obj.primary_key}', "
                f"but is_primary_key is set on {flagged}"
            )
        if obj.title_property and obj.properties and obj.title_property not in names:
            raise ValueError(
                f"ObjectType '{obj.name}' title_property '{obj.title_property}' is not a declared property"
            )
        for iface_col, obj_col in (obj.property_mappings or {}).items():
            safe_ident(iface_col)
            safe_ident(obj_col)
        for iface_name in obj.implements or []:
            req_props = self.effective_interface_properties(iface_name)
            for rprop in req_props:
                mapped_col = (obj.property_mappings or {}).get(rprop.name, rprop.name)
                safe_ident(mapped_col)
                if obj.properties:
                    if mapped_col not in prop_by_name:
                        raise ValueError(
                            f"ObjectType '{obj.name}' implements InterfaceType '{iface_name}' "
                            f"but is missing required property '{rprop.name}' (mapped to '{mapped_col}')"
                        )
                    obj_ptype = _normalize_property_type(prop_by_name[mapped_col].data_type)
                    req_ptype = _normalize_property_type(rprop.data_type)
                    if obj_ptype != req_ptype:
                        raise ValueError(
                            f"ObjectType '{obj.name}' property '{mapped_col}' has type '{obj_ptype}', "
                            f"but InterfaceType '{iface_name}.{rprop.name}' requires '{req_ptype}'"
                        )

    def _validate_link_type(self, link: LinkType) -> LinkType:
        if not (link.name or "").strip():
            raise ValueError("LinkType name is required")
        cardinality = (link.cardinality or "").upper()
        if cardinality not in _CARDINALITIES:
            raise ValueError(
                f"Link '{link.name}' cardinality '{link.cardinality}' is not one of "
                f"{sorted(_CARDINALITIES)}"
            )
        if self._resolve_object_type(link.source_object_type) is None:
            raise ValueError(
                f"Link '{link.name}' source '{link.source_object_type}' is not a registered ObjectType"
            )
        if self._resolve_object_type(link.target_object_type) is None:
            raise ValueError(
                f"Link '{link.name}' target '{link.target_object_type}' is not a registered ObjectType"
            )
        if (link.is_symmetric or link.is_transitive) and link.source_object_type != link.target_object_type:
            raise ValueError(
                f"Link '{link.name}' with is_symmetric or is_transitive must be reflexive "
                f"(source_object_type == target_object_type)"
            )
        if link.inverse_of:
            inv = self._resolve_link_type(link.inverse_of)
            if inv is not None and (
                inv.source_object_type != link.target_object_type
                or inv.target_object_type != link.source_object_type
            ):
                raise ValueError(
                    f"Link '{link.name}' inverse_of '{link.inverse_of}' has incompatible endpoints "
                    f"({inv.source_object_type} -> {inv.target_object_type})"
                )
        safe_ident(link.source_join_key)
        safe_ident(link.target_join_key)
        if cardinality == "MANY_TO_MANY":
            if not (link.junction_table and link.junction_source_key and link.junction_target_key):
                raise ValueError(
                    f"MANY_TO_MANY link '{link.name}' requires junction_table, "
                    "junction_source_key, and junction_target_key"
                )
            safe_table_ref(link.junction_table)
            safe_ident(link.junction_source_key)
            safe_ident(link.junction_target_key)
        if cardinality != link.cardinality:
            return link.model_copy(update={"cardinality": cardinality})
        return link

    def _validate_action_type(self, action: ActionType) -> ActionType:
        if not (action.name or "").strip():
            raise ValueError("ActionType name is required")
        handler = (action.handler_type or "").upper()
        if handler not in _HANDLERS:
            raise ValueError(
                f"Action '{action.name}' handler_type '{action.handler_type}' is not one of {sorted(_HANDLERS)}"
            )
        if action.target_interface:
            if self._resolve_interface_type(action.target_interface) is None:
                raise ValueError(
                    f"Action '{action.name}' target_interface '{action.target_interface}' is not a registered InterfaceType"
                )
        elif (
            self._resolve_object_type(action.target_object_type) is None
            and self._resolve_interface_type(action.target_object_type) is None
        ):
            raise ValueError(
                f"Action '{action.name}' target '{action.target_object_type}' is not a registered ObjectType or InterfaceType"
            )
        param_names = [param.name for param in action.parameters]
        if len(param_names) != len(set(param_names)):
            raise ValueError(f"Action '{action.name}' has duplicate parameters")
        for param in action.parameters:
            _normalize_param_type(param.data_type)
            if param.min_value is not None and param.max_value is not None and param.min_value > param.max_value:
                raise ValueError(
                    f"Action '{action.name}' parameter '{param.name}' has min_value > max_value"
                )
        for pre in action.preconditions or []:
            if not (pre.sql_predicate or "").strip():
                raise ValueError(f"Action '{action.name}' precondition '{pre.name}' requires sql_predicate")
            dummy_pred = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", "1", pre.sql_predicate)
            safe_predicate(dummy_pred)
        cfg = action.handler_config or {}
        if handler == "SQL_MUTATION":
            has_writeback = bool(cfg.get("writeback_table"))
            has_template = bool(cfg.get("sql_template"))
            if has_writeback and has_template:
                raise ValueError(
                    f"Action '{action.name}' cannot set both writeback_table and sql_template"
                )
            if not has_writeback and not has_template:
                raise ValueError(
                    f"Action '{action.name}' SQL_MUTATION needs writeback_table or sql_template"
                )
            if has_writeback:
                safe_table_ref(cfg["writeback_table"])
                if cfg.get("set_column"):
                    safe_ident(cfg["set_column"])
        elif handler == "FUNCTION":
            fn_name = cfg.get("function_name")
            if not fn_name or self._resolve_function_type(fn_name) is None:
                raise ValueError(
                    f"Action '{action.name}' FUNCTION handler requires a registered 'function_name' in handler_config"
                )
            if cfg.get("writeback_table"):
                safe_table_ref(cfg["writeback_table"])
                if cfg.get("set_column"):
                    safe_ident(cfg["set_column"])
        if handler != action.handler_type:
            return action.model_copy(update={"handler_type": handler})
        return action

    def _validate_function_type(self, fn: FunctionType) -> FunctionType:
        if not (fn.name or "").strip():
            raise ValueError("FunctionType name is required")
        if (
            self._resolve_object_type(fn.target_object_type) is None
            and self._resolve_interface_type(fn.target_object_type) is None
        ):
            raise ValueError(
                f"FunctionType '{fn.name}' target '{fn.target_object_type}' is not a registered ObjectType or InterfaceType"
            )
        if not (fn.sql_expression or "").strip():
            raise ValueError(f"FunctionType '{fn.name}' requires a non-empty sql_expression")
        dummy_expr = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", "1", fn.sql_expression)
        safe_predicate(dummy_expr)
        param_names = [p.name for p in fn.parameters]
        if len(param_names) != len(set(param_names)):
            raise ValueError(f"FunctionType '{fn.name}' has duplicate parameters")
        for p in fn.parameters:
            _normalize_param_type(p.data_type)
        norm_ret = _normalize_param_type(fn.return_type)
        if norm_ret != fn.return_type:
            return fn.model_copy(update={"return_type": norm_ret})
        return fn


def build_object_type_from_asset(
    asset: TableAsset,
    *,
    name: Optional[str] = None,
    primary_key: Optional[str] = None,
) -> ObjectType:
    """Map a catalog table asset onto an object type. Does not register it."""
    dataset = (asset.dataset_name or "").strip()
    if not dataset:
        raise ValueError("Catalog asset dataset_name is required")
    columns = list(asset.columns or [])
    if not columns:
        raise ValueError(f"Catalog asset '{dataset}' has no columns to model")
    names = [col.name for col in columns]
    if len(names) != len(set(names)):
        raise ValueError(f"Catalog asset '{dataset}' has duplicate columns")
    flagged = [col.name for col in columns if col.is_primary_key]
    if primary_key:
        pk = primary_key
    elif len(flagged) == 1:
        pk = flagged[0]
    else:
        identifiers = [
            col.name for col in columns
            if (col.semantic_type or "").upper() == "IDENTIFIER" and not col.is_primary_key
        ]
        if len(flagged) == 0 and len(identifiers) == 1:
            pk = identifiers[0]
        else:
            raise ValueError(
                f"Cannot infer primary key for catalog asset '{dataset}'. "
                "Pass primary_key= or mark exactly one column is_primary_key."
            )
    if pk not in names:
        raise ValueError(f"Primary key '{pk}' is not a column of catalog asset '{dataset}'")
    properties = [
        PropertyMeta(
            name=col.name,
            data_type=col.data_type,
            description=col.description or "",
            is_primary_key=(col.name == pk),
        )
        for col in columns
    ]
    return ObjectType(
        name=name or dataset,
        display_name=asset.display_name or name or dataset,
        description=asset.description or "",
        primary_key=pk,
        backed_by_table=dataset,
        properties=properties,
        tags=list(asset.tags or []),
    )


def _query_select(obj: ObjectType, properties: Optional[List[str]]) -> str:
    declared = {prop.name: prop for prop in obj.properties}
    if properties:
        if declared:
            unknown = [name for name in properties if name not in declared]
            if unknown:
                raise ValueError(
                    f"ObjectType '{obj.name}' has no property {unknown}. Declared: {list(declared)}"
                )
        parts = []
        for name in properties:
            prop = declared.get(name)
            if prop is not None and prop.formula:
                parts.append(f"({safe_predicate(prop.formula)}) AS {safe_ident(name)}")
            else:
                parts.append(safe_ident(name))
        return ", ".join(parts)
    formulas = [prop for prop in obj.properties if prop.formula]
    if not formulas:
        return "*"
    extra = ", ".join(
        f"({safe_predicate(prop.formula)}) AS {safe_ident(prop.name)}" for prop in formulas
    )
    return f"*, {extra}"


def _outer_projection(obj: ObjectType) -> str:
    """Project the target after the join, so formulas are not ambiguous with the source table."""
    if not obj.properties:
        return "*"
    parts = []
    names = {prop.name for prop in obj.properties}
    if obj.primary_key not in names:
        parts.append(safe_ident(obj.primary_key))
    for prop in obj.properties:
        if prop.formula:
            parts.append(f"({safe_predicate(prop.formula)}) AS {safe_ident(prop.name)}")
        else:
            parts.append(safe_ident(prop.name))
    return ", ".join(parts)


def _prepare_parameters(action_or_fn: Any, parameter_values: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    params = dict(parameter_values or {})
    for param in action_or_fn.parameters:
        if param.name not in params:
            if param.default_value is not None:
                params[param.name] = param.default_value
            elif param.required:
                raise ValueError(
                    f"Required parameter '{param.name}' missing for '{action_or_fn.name}'"
                )
        if param.name in params and params[param.name] is not None:
            _check_param_type(action_or_fn.name, param, params[param.name])
            _check_param_constraints(action_or_fn.name, param, params[param.name])
    return params


def _normalize_property_type(data_type: str) -> str:
    kind = (data_type or "").strip().lower()
    if kind in _STRING_TYPES or kind.startswith("varchar"):
        return "string"
    if kind in _INT_TYPES:
        return "integer"
    if kind in _FLOAT_TYPES or kind.startswith("decimal"):
        return "float"
    if kind in _BOOL_TYPES:
        return "boolean"
    if kind in _TIMESTAMP_TYPES:
        return "timestamp"
    if kind in _JSON_TYPES:
        return "json"
    raise ValueError(f"Unsupported property data_type '{data_type}'")


def _normalize_param_type(data_type: str) -> str:
    kind = (data_type or "").strip().lower()
    if kind in _STRING_TYPES:
        return "string"
    if kind in _INT_TYPES:
        return "integer"
    if kind in _FLOAT_TYPES:
        return "float"
    if kind in _BOOL_TYPES:
        return "boolean"
    if kind in _JSON_TYPES:
        return "json"
    raise ValueError(f"Unsupported parameter data_type '{data_type}'")


def _check_param_type(action_name: str, param: ActionParameter, value: Any) -> None:
    kind = _normalize_param_type(param.data_type)
    ok = True
    if kind == "string":
        ok = isinstance(value, str)
    elif kind == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "float":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif kind == "boolean":
        ok = isinstance(value, bool)
    if not ok:
        raise ValueError(
            f"Parameter '{param.name}' for action '{action_name}' expects {kind}, got {type(value).__name__}"
        )


def _check_param_constraints(action_name: str, param: ActionParameter, value: Any) -> None:
    if param.min_value is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < param.min_value:
            raise ValueError(
                f"Parameter '{param.name}' for '{action_name}' value {value} is below min_value={param.min_value}"
            )
    if param.max_value is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
        if value > param.max_value:
            raise ValueError(
                f"Parameter '{param.name}' for '{action_name}' value {value} exceeds max_value={param.max_value}"
            )
    if param.allowed_values is not None and value not in param.allowed_values:
        raise ValueError(
            f"Parameter '{param.name}' for '{action_name}' value {value!r} is not in allowed_values={param.allowed_values}"
        )
    if param.regex_pattern and isinstance(value, str):
        if not re.fullmatch(param.regex_pattern, value):
            raise ValueError(
                f"Parameter '{param.name}' for '{action_name}' value {value!r} does not match regex '{param.regex_pattern}'"
            )


def _bind_sql_expression(expr: str, params: Dict[str, Any]) -> str:
    safe_subs: Dict[str, Any] = {}
    for key, val in params.items():
        if isinstance(val, str):
            if any(tok in val for tok in ("'", '"', ";", "--", "/*")):
                raise ValueError(f"Unsafe character in SQL expression parameter '{key}': {val!r}")
            safe_subs[key] = val
        elif isinstance(val, bool):
            safe_subs[key] = "TRUE" if val else "FALSE"
        elif val is None:
            safe_subs[key] = "NULL"
        else:
            safe_subs[key] = val
    return expr.format(**safe_subs) if safe_subs else expr


def _coerce_return_value(val: Any, return_type: str) -> Any:
    plain = _plain(val)
    if plain is None:
        return None
    kind = _normalize_param_type(return_type)
    if kind == "float":
        return float(plain)
    if kind == "integer":
        return int(plain)
    if kind == "string":
        return str(plain)
    if kind == "boolean":
        return bool(plain)
    return plain


def _run_webhook(
    action_name: str,
    target_type: str,
    cfg: Dict[str, Any],
    display: str,
    instance_id: Any,
    params: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    webhook_url = cfg.get("webhook_url", "http://127.0.0.1:8000/api/v1/mock_webhook")
    platform = cfg.get("platform", "generic")
    title = f"【Ontology 动作触发】{display}"
    message = f"针对实体对象 [{target_type}#{instance_id}] 触发了动作：{action_name}"
    try:
        exec_result = WebhookPusher.send_alert(
            webhook_url, title, message, platform, extra_metrics=params
        )
    except Exception as exc:
        return "FAILED", {"status": "FAILED", "message": str(exc)}
    # Failure responses still carry simulated_payload for debugging.
    # That field does not mean the webhook was delivered.
    if exec_result.get("status") == "FAILED":
        return "FAILED", exec_result
    return "SUCCESS", exec_result


def _run_reverse_etl(con: duckdb.DuckDBPyConnection, cfg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    dest = cfg.get("dest_conn_str")
    dest_table = cfg.get("dest_table_name")
    source = cfg.get("source_table")
    if not (dest and dest_table and source):
        return "FAILED", {
            "status": "FAILED",
            "message": "REVERSE_ETL_SYNC needs handler_config dest_conn_str, dest_table_name, and source_table. Nothing was synced.",
        }
    try:
        synced = DestinationSync.sync_table_to_destination(
            con, source, dest, dest_table, cfg.get("mode", "replace")
        )
    except Exception as exc:
        return "FAILED", {"status": "FAILED", "message": str(exc)}
    return "SUCCESS", {"status": "SUCCESS", "sync": synced}


def _require_positive_int(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")


def _plain(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            return value
    return value


def _pk_of(row: Dict[str, Any], primary_key: str, type_name: str) -> Any:
    if primary_key not in row:
        raise ValueError(
            f"ObjectType '{type_name}' row has no primary key column '{primary_key}'"
        )
    value = _plain(row[primary_key])
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError(f"ObjectType '{type_name}' row is missing primary key '{primary_key}'")
    return value


def _statement_hash(statement: str, bound: Optional[List[Any]] = None) -> str:
    payload = statement if not bound else statement + "|" + json.dumps(bound, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_ontology_engine(session_id: str = "_global") -> OntologyEngine:
    norm_id = (session_id or "_global").strip() or "_global"
    with OntologyEngine._lock:
        inst = OntologyEngine._session_instances.get(norm_id)
        if inst is None:
            inst = OntologyEngine(persistent=(norm_id == "_global"), session_id=norm_id)
            OntologyEngine._session_instances[norm_id] = inst
        if norm_id == "_global":
            OntologyEngine._instance = inst
        return inst
