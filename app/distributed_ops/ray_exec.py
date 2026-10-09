"""Partition a numeric scan and merge the sums.

Ray is optional. When `DATA_AGENT_RAY_ENABLED` is on and the `ray` package
imports, each partition runs as a Ray task. Otherwise the same worker function
runs in this process. Either way the merged sums match one DuckDB scan.
Remote workers have to see the spill parquet; a local Ray on this machine does.
"""

import os
import shutil
import tempfile
from typing import Any, Dict, List, Tuple

import duckdb

from app.config import settings
from app.engine.sql_guard import safe_ident


def merge_sum_rows(pieces: List[Dict[str, Any]]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for piece in pieces:
        for key, value in piece.items():
            merged[key] = merged.get(key, 0.0) + float(value or 0.0)
    if "__n" in merged:
        merged["__n"] = float(int(merged["__n"]))
    return merged


def _sum_select(columns: List[str]) -> Tuple[str, str]:
    quoted = [safe_ident(name) for name in columns]
    select_parts = ["COUNT(*) AS __n"]
    for i, column in enumerate(quoted):
        select_parts.append(f"SUM({column}) AS __s{i}")
        select_parts.append(f"SUM({column} * {column}) AS __ss{i}")
        for j in range(i + 1, len(quoted)):
            select_parts.append(f"SUM({column} * {quoted[j]}) AS __sp{i}_{j}")
    return ", ".join(select_parts), quoted[0]


def pearson_partition(task: Dict[str, Any]) -> Dict[str, float]:
    """Sufficient statistics for one hash slice of a parquet file."""
    columns = list(task["columns"])
    select_list, first = _sum_select(columns)
    parts = int(task["parts"])
    part = int(task["part"])
    path = str(task["parquet"]).replace("'", "''")
    sql = (
        f"SELECT {select_list} FROM read_parquet('{path}') "
        f"WHERE (hash(CAST({first} AS VARCHAR)) % {parts}) = {part}"
    )
    con = duckdb.connect(database=":memory:")
    try:
        rel = con.execute(sql)
        row = rel.fetchone()
        names = [item[0] for item in rel.description]
    finally:
        con.close()
    return {name: float(value or 0.0) for name, value in zip(names, row)}


def _import_ray():
    try:
        import ray
    except ImportError:
        return None
    return ray


def _ray_map(ray_mod, tasks: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    if not ray_mod.is_initialized():
        kwargs = {"ignore_reinit_error": True, "include_dashboard": False}
        if settings.RAY_ADDRESS:
            ray_mod.init(address=settings.RAY_ADDRESS, **kwargs)
        else:
            ray_mod.init(num_cpus=min(4, os.cpu_count() or 2), **kwargs)
    remote = ray_mod.remote(pearson_partition)
    return ray_mod.get([remote.remote(task) for task in tasks])


def run_partition_tasks(tasks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, float]], str]:
    ray_mod = _import_ray()
    if ray_mod is not None:
        try:
            return _ray_map(ray_mod, tasks), "ray"
        except Exception:
            pass
    return [pearson_partition(task) for task in tasks], "local"


def partition_count() -> int:
    configured = int(settings.RAY_PARTITIONS or 0)
    if configured > 0:
        return max(2, min(16, configured))
    return max(2, min(8, os.cpu_count() or 2))


def _session_hash_merge(con, select_sql: str, columns: List[str], parts: int) -> Tuple[Dict[str, float], str]:
    """Same merge when this connection can no longer write a spill file.

    DuckDB refuses to turn enable_external_access back on after the sandbox
    has turned it off, so COPY is unavailable for the rest of that connection.
    """
    select_list, first = _sum_select(columns)
    pieces = []
    for part in range(parts):
        sql = (
            f"SELECT {select_list} FROM ({select_sql}) AS _slice "
            f"WHERE (hash(CAST({first} AS VARCHAR)) % {parts}) = {part}"
        )
        rel = con.execute(sql)
        row = rel.fetchone()
        names = [item[0] for item in rel.description]
        pieces.append({name: float(value or 0.0) for name, value in zip(names, row)})
    note = (
        f"Pearson sufficient statistics were merged from {parts} partitions "
        "(backend=session). External access is off on this connection, so the slices stayed here."
    )
    return merge_sum_rows(pieces), note


def partitioned_pearson_sums(con, select_sql: str, columns: List[str], parts: int) -> Tuple[Dict[str, float], str]:
    directory = tempfile.mkdtemp(prefix="ray-scan-")
    path = os.path.join(directory, "cols.parquet")
    try:
        escaped = path.replace("'", "''")
        try:
            con.execute(f"COPY ({select_sql}) TO '{escaped}' (FORMAT PARQUET)")
        except duckdb.Error:
            return _session_hash_merge(con, select_sql, columns, parts)
        tasks = [
            {"parquet": path, "part": index, "parts": parts, "columns": list(columns)}
            for index in range(parts)
        ]
        pieces, backend = run_partition_tasks(tasks)
        note = (
            f"Pearson sufficient statistics were merged from {parts} partitions "
            f"(backend={backend})."
        )
        return merge_sum_rows(pieces), note
    finally:
        shutil.rmtree(directory, ignore_errors=True)
