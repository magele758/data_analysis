"""Read a bounded MongoDB find result into a session-compatible Arrow table."""
from contextlib import contextmanager
from datetime import datetime
import json
from urllib.parse import parse_qsl, urlsplit

import pyarrow as pa
from bson import BSON, Decimal128, Int64, ObjectId, json_util
from bson.errors import BSONError
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError

from app.config import settings
from app.connectors.base import BaseConnector, ColumnInfo, TableSchema


# Only read predicates and BSON literal wrappers can appear in a find filter.
_FILTER_KEYS = {
    "$and", "$or", "$nor", "$not", "$eq", "$ne", "$lt", "$lte", "$gt", "$gte",
    "$in", "$nin", "$exists", "$elemMatch", "$oid", "$date", "$numberDecimal",
    "$numberLong", "$numberInt", "$numberDouble",
}
_URI_OPTIONS = {
    "authsource", "authmechanism", "replicaset", "directconnection", "tls", "ssl",
    "readpreference", "readpreferencetags", "retryreads", "retrywrites",
    "w", "appname", "maxstalenessseconds",
}


def _check_filter_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.startswith("$") and key not in _FILTER_KEYS:
                raise ValueError(f"Unsupported MongoDB filter operator {key!r}")
            _check_filter_keys(child)
    elif isinstance(value, list):
        for child in value:
            _check_filter_keys(child)


def _parse_filter(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("mongo_filter must be a JSON object")
    _check_filter_keys(value)
    try:
        result = json_util.loads(json.dumps(value))
        BSON.encode(result)  # Validate BSON integer range, field names and root type.
    except (ValueError, TypeError, KeyError, ArithmeticError, BSONError) as exc:
        raise ValueError("Invalid MongoDB Extended JSON filter literal") from exc
    return result


def _normalize(value, field):
    if isinstance(value, ObjectId):
        return "ObjectId", str(value)
    if isinstance(value, Decimal128):
        number = value.to_decimal()
        if not number.is_finite():
            raise ValueError(f"MongoDB field {field!r} contains a non-finite Decimal128")
        return "decimal", number
    if isinstance(value, (dict, list)):
        return type(value).__name__, json_util.dumps(value, separators=(",", ":"))
    if isinstance(value, Int64):
        return "int", int(value)
    if type(value) in (bool, int, float, str, bytes, datetime):
        return type(value).__name__, value
    raise ValueError(f"Unsupported BSON type {type(value).__name__} in MongoDB field {field!r}")


def _read_table(cursor, columns):
    # Discover the union of keys across every batch. Arrow's from_pylist infers
    # keys from the first row and would silently discard fields added later.
    kinds = dict.fromkeys(columns or [])
    rows = []
    byte_count = 0
    for doc in cursor:
        if len(rows) >= settings.MONGO_MAX_ROWS:
            raise ValueError("MongoDB import exceeds MONGO_MAX_ROWS. Narrow mongo_filter or limit.")
        byte_count += len(BSON.encode(doc))
        if byte_count > settings.MONGO_MAX_BSON_MB * 1024 * 1024:
            raise ValueError("MongoDB import exceeds MONGO_MAX_BSON_MB. Narrow the projection or filter.")
        row = {}
        for field, value in doc.items():
            previous = kinds.setdefault(field, None)
            if value is None:
                continue
            kind, row[field] = _normalize(value, field)
            if previous is not None and kind != previous:
                raise ValueError(f"MongoDB field {field!r} has mixed types {previous} and {kind}")
            kinds[field] = kind
        rows.append(row)
        if len(rows) * len(kinds) > settings.MONGO_MAX_CELLS:
            raise ValueError("MongoDB import exceeds MONGO_MAX_CELLS. Narrow the projection or filter.")

    # A schemaless empty result still needs a column to register in DuckDB.
    names = list(kinds) or ["_id"]
    if len({name.lower() for name in names}) != len(names) or any(not n or "\x00" in n for n in names):
        raise ValueError("MongoDB field names must be nonempty and unique ignoring case for DuckDB")
    arrays = []
    for field in names:
        dtype = pa.timestamp("ms", tz="UTC") if kinds.get(field) == "datetime" else None
        try:
            array = pa.array([row.get(field) for row in rows], type=dtype)
        except (pa.ArrowException, ValueError, OverflowError) as exc:
            raise ValueError(f"MongoDB field {field!r} cannot be represented exactly in Arrow") from exc
        if pa.types.is_decimal(array.type) and array.type.precision > 38:
            raise ValueError(f"MongoDB field {field!r} exceeds DuckDB DECIMAL precision 38")
        arrays.append(array)
    return pa.Table.from_arrays(arrays, names=names)


class MongoDBConnector(BaseConnector):
    """Materialize a collection using PyMongo's read-only find API."""

    @property
    def source_label(self):
        return super().source_label + urlsplit(self.conn_str).path

    @contextmanager
    def _database(self):
        try:
            parts = urlsplit(self.conn_str)
        except ValueError:
            raise ValueError("Invalid MongoDB URI") from None
        if "#" in self.conn_str:
            raise ValueError("MongoDB URI fragments are unsupported")
        if not parts.path.strip("/"):
            raise ValueError("MongoDB URI must include the database name")
        options = parse_qsl(parts.query.replace(";", "&"), keep_blank_values=True)
        for key, value in options:
            if key.lower() not in _URI_OPTIONS:
                raise ValueError("Unsupported MongoDB URI option")
            if key.lower() == "authmechanism" and value not in ("SCRAM-SHA-1", "SCRAM-SHA-256"):
                raise ValueError("MongoDB imports support password (SCRAM) authentication")
        try:
            client = MongoClient(self.conn_str, tz_aware=True, serverSelectionTimeoutMS=5000,
                                 connectTimeoutMS=5000, timeoutMS=60000)
        except (PyMongoError, OSError, ValueError):
            raise ValueError("Invalid MongoDB connection. Check the database name, URI options and DNS.") from None
        try:
            with client:
                yield client.get_default_database()
        except OperationFailure as exc:
            raise ValueError(f"MongoDB read failed (server code {exc.code}). Check permissions and filter.") from None
        except (PyMongoError, BSONError) as exc:
            raise ValueError(f"MongoDB read failed ({type(exc).__name__}). Check the connection and BSON types.") from None

    def test_connection(self):
        try:
            with self._database() as db:
                db.command("ping")
            return True
        except ValueError:
            return False

    def list_tables(self):
        with self._database() as db:
            return sorted(db.list_collection_names())

    def introspect_schema(self, table_name):
        sample = self.fetch_to_arrow(table_name, limit=min(100, settings.MONGO_MAX_ROWS))
        return TableSchema(table_name=table_name, columns=[
            ColumnInfo(name=field.name, physical_type=str(field.type)) for field in sample.schema
        ])

    def fetch_to_arrow(self, query_or_table, filter_sql=None, select_cols=None, partition_col=None,
                       num_partitions=1, limit=None, mode="materialize", *, mongo_filter=None):
        if filter_sql is not None or partition_col is not None or num_partitions != 1 or mode != "materialize":
            raise ValueError("MongoDB uses materialize mode and a single unpartitioned read. Use mongo_filter for predicates.")
        if not query_or_table or not query_or_table.strip() or query_or_table.lstrip().upper().startswith("SELECT "):
            raise ValueError("MongoDB query_or_table must be a collection name")
        if limit is not None and not 0 <= limit <= settings.MONGO_MAX_ROWS:
            raise ValueError(f"MongoDB limit must be between 0 and {settings.MONGO_MAX_ROWS}")
        if select_cols and (len(set(select_cols)) != len(select_cols) or any(
                not col or "." in col or col.startswith("$") or "\x00" in col for col in select_cols)):
            raise ValueError("MongoDB select_cols requires distinct top-level field names")
        projection = None
        if select_cols:
            projection = dict.fromkeys(select_cols, 1)
            projection.setdefault("_id", 0)
        predicate = _parse_filter(mongo_filter)
        if limit == 0:
            # MongoDB interprets limit(0) as unlimited. Still validate the read.
            predicate = {"$and": [predicate, {"$expr": {"$eq": [1, 0]}}]}
        with self._database() as db:
            with db[query_or_table].find(predicate, projection, batch_size=512,
                                         limit=limit or settings.MONGO_MAX_ROWS + 1) as cursor:
                return _read_table(cursor, select_cols)
