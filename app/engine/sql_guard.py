"""SQL identifier / predicate validation for LLM-supplied query fragments."""
import re
from typing import List

import duckdb

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_FORBIDDEN_RE = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|ATTACH|COPY|CREATE|GRANT"
    r"|PRAGMA|CALL|EXPORT|INSTALL|LOAD)\b",
    re.IGNORECASE,
)


def safe_ident(name: str) -> str:
    """Validate a bare identifier and return it double-quoted."""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(
            f"Invalid SQL identifier {name!r}: must match ^[A-Za-z_][A-Za-z0-9_]*$"
        )
    return f'"{name}"'


def safe_table_ref(ref: str) -> str:
    """Validate an optionally schema-qualified table reference -> "schema"."table"."""
    if not isinstance(ref, str) or not ref:
        raise ValueError(f"Invalid table reference {ref!r}: must be a non-empty string")
    parts = ref.split(".")
    if len(parts) > 3:
        raise ValueError(
            f"Invalid table reference {ref!r}: at most catalog.schema.table is allowed"
        )
    return ".".join(safe_ident(p) for p in parts)


def safe_predicate(pred: str) -> str:
    """Validate a free-form WHERE fragment, blocking statement injection."""
    if not isinstance(pred, str) or not pred.strip():
        raise ValueError("Invalid SQL predicate: must be a non-empty string")
    if ";" in pred:
        raise ValueError(f"Invalid SQL predicate {pred!r}: statement terminator ';'")
    if "--" in pred or "/*" in pred or "*/" in pred:
        raise ValueError(f"Invalid SQL predicate {pred!r}: SQL comments are not allowed")
    match = _FORBIDDEN_RE.search(pred)
    if match:
        raise ValueError(
            f"Invalid SQL predicate {pred!r}: forbidden keyword '{match.group(0)}'"
        )
    extract = getattr(duckdb, "extract_statements", None)
    if extract is not None:
        # ponytail: real parser beats the blacklist; regex above stays as the fallback
        try:
            statements = extract(f"SELECT 1 WHERE {pred}")
        except Exception as exc:
            raise ValueError(f"Invalid SQL predicate {pred!r}: {exc}") from exc
        if len(statements) != 1:
            raise ValueError(
                f"Invalid SQL predicate {pred!r}: expands to {len(statements)} statements"
            )
    return pred


def safe_columns(names: List[str]) -> str:
    """Validate each column name and return them comma-joined."""
    if not names:
        raise ValueError("Invalid column list: must contain at least one column")
    return ", ".join(safe_ident(n) for n in names)


def safe_model_sql(sql: str) -> str:
    """Validate a DAG model body: exactly one read-only statement.

    Model SQL is arbitrary SELECT by design (dbt-style), so keyword blacklisting
    is not applicable -- but it is wrapped into CREATE TABLE AS, where a chained
    statement would execute with full privileges.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Invalid model SQL: must be a non-empty string")
    extract = getattr(duckdb, "extract_statements", None)
    if extract is None:
        raise ValueError("Cannot validate model SQL: duckdb.extract_statements unavailable")
    try:
        statements = extract(sql)
    except Exception as exc:
        raise ValueError(f"Invalid model SQL: {exc}") from exc
    if len(statements) != 1:
        raise ValueError(f"Invalid model SQL: expected 1 statement, got {len(statements)}")
    stmt_type = str(getattr(statements[0], "type", ""))
    if not stmt_type.endswith(("SELECT", "EXPLAIN")):
        raise ValueError(f"Invalid model SQL: must be a read-only query, got {stmt_type}")
    return sql
