from datetime import datetime, timezone
from decimal import Decimal

from bson import Decimal128, Int64, ObjectId
import pyarrow as pa
import pytest

from app.config import settings
from app.connectors.factory import ConnectorFactory, read_source
from app.connectors.mongodb import MongoDBConnector, _parse_filter, _read_table


def test_mongo_schemes_and_catalog_label():
    for scheme in ("mongodb", "mongodb+srv"):
        connector = ConnectorFactory.get_connector(f"{scheme}://user:secret@example.org/shop?authSource=private")
        assert isinstance(connector, MongoDBConnector)
        assert connector.source_label == f"{scheme}://example.org/shop"
    with pytest.raises(ValueError, match="only supported for MongoDB"):
        read_source("unopened.csv", "orders", mongo_filter={})


def test_mongo_union_and_exact_types():
    oid = ObjectId()
    date = datetime(2026, 11, 16, tzinfo=timezone.utc)
    table = _read_table([
        {"_id": oid, "n": 2, "amount": Decimal128("9007199254740993.10"), "sub": {"k": oid}},
        {"n": Int64(3), "amount": Decimal128("0.001"), "date": date, "arr": [1, "x"]},
    ], None)
    assert table.column_names == ["_id", "n", "amount", "sub", "date", "arr"]
    assert table["amount"].to_pylist() == [Decimal("9007199254740993.100"), Decimal("0.001")]
    assert table["date"].type == pa.timestamp("ms", tz="UTC")
    assert table["_id"].to_pylist() == [str(oid), None]
    assert table["sub"][0].as_py() == '{"k":{"$oid":"' + str(oid) + '"}}'
    assert table["arr"][1].as_py() == '[1,"x"]'
    assert _read_table([], ["z", "a"]).column_names == ["z", "a"]
    assert _read_table([], None).column_names == ["_id"]


@pytest.mark.parametrize("docs,message", [
    ([{"x": 1}] * 512 + [{"x": "1"}], "field 'x' has mixed types"),
    ([{"x": Decimal128("1e38")}], "field 'x'"),
    ([{"x": Decimal128("NaN")}], "field 'x'"),
    ([{"Name": 1}, {"name": 2}], "unique ignoring case"),
])
def test_mongo_rejects_lossy_fields(docs, message):
    with pytest.raises(ValueError, match=message):
        _read_table(docs, None)


@pytest.mark.parametrize("setting,docs", [
    ("MONGO_MAX_ROWS", [{"x": 1}, {"x": 2}]),
    ("MONGO_MAX_CELLS", [{"x": 1}, {"y": 1}]),
    ("MONGO_MAX_BSON_MB", [{"x": "a" * 1024**2}]),
])
def test_mongo_import_budgets(monkeypatch, setting, docs):
    monkeypatch.setattr(settings, setting, 1)
    with pytest.raises(ValueError, match=setting):
        _read_table(docs, None)


@pytest.mark.parametrize("options", [
    {"mode": "scanner"}, {"filter_sql": "x > 0"}, {"num_partitions": 2},
    {"partition_col": "_id"}, {"limit": -1}, {"select_cols": ["sub.x"]},
    {"mongo_filter": {"$or": [{"$where": "unsupported"}]}},
    {"mongo_filter": {"x": 2**80}}, {"mongo_filter": [{"$out": "dest"}]}, {"mongo_filter": {"x": {"$oid": "invalid"}}},
])
def test_mongo_rejects_invalid_options_before_connection(options):
    with pytest.raises(ValueError):
        MongoDBConnector("mongodb://unused.invalid/shop").fetch_to_arrow("orders", **options)


def test_mongo_filter_bson_literals():
    oid = ObjectId()
    predicate = {"$and": [{"_id": {"$oid": str(oid)}}, {"total": {"$gt": {"$numberDecimal": "1.20"}}}]}
    clauses = _parse_filter(predicate)["$and"]
    assert clauses == [{"_id": oid}, {"total": {"$gt": Decimal128("1.20")}}]
