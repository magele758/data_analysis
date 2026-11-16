"""Set MONGOD_TEST_BINARY to an installed mongod to run the isolated live test."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from bson import Decimal128
import httpx
import pytest
from pymongo import MongoClient


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _process(command, directory, env=None):
    with (directory / (Path(command[0]).name + ".log")).open("ab") as log:
        proc = subprocess.Popen(command, cwd=directory, env=env, stdout=log, stderr=log)
        try:
            yield proc
        finally:
            proc.terminate()
            proc.wait(timeout=30)


@pytest.fixture
def live_directory():
    with TemporaryDirectory(prefix="data-agent-mongodb-test-") as directory:
        yield Path(directory)


@pytest.mark.full
@pytest.mark.skipif(not os.getenv("MONGOD_TEST_BINARY"), reason="requires an isolated local mongod")
def test_readonly_mongo_http_and_stdio(live_directory):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    mongo_port = _port()
    data = live_directory / "mongo"
    data.mkdir()
    host = f"127.0.0.1:{mongo_port}"
    password = secrets.token_hex(16)
    command = [os.environ["MONGOD_TEST_BINARY"], "--auth", "--bind_ip", "127.0.0.1",
               "--port", str(mongo_port), "--dbpath", str(data), "--nounixsocket"]
    with _process(command, live_directory):
        with MongoClient(host, serverSelectionTimeoutMS=15000) as bootstrap:
            bootstrap.admin.command("createUser", "setup", pwd=password, roles=["root"])
        with MongoClient(host, username="setup", password=password) as setup:
            db = setup.shop
            db.command("createUser", "reader", pwd=password, roles=["read"])
            orders = db.orders
            for day, status, amount in [(15, "paid", "9007199254740993.10"), (15, "paid", "0.02"),
                                        (16, "paid", "17.15"), (16, "open", "10.00")]:
                orders.insert_one({"status": status, "amount": Decimal128(amount),
                                   "paid_at": datetime(2026, 11, day, 12, tzinfo=timezone.utc)})
            expected = [
                {"day": row["_id"], "n": row["n"], "amount": str(row["amount"])}
                for row in orders.aggregate([
                    {"$match": {"status": "paid"}},
                    {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$paid_at"}},
                                "n": {"$sum": 1}, "amount": {"$sum": "$amount"}}}, {"$sort": {"_id": 1}},
                ])
            ]
        uri = f"mongodb://reader:{password}@{host}/shop?authSource=shop"
        request = {"conn_str": uri, "query_or_table": "orders", "dataset_name": "paid_orders",
                   "mongo_filter": {"status": "paid", "paid_at": {"$gte": {"$date": "2026-11-15T00:00:00Z"}}},
                   "select_cols": ["paid_at", "amount"], "limit": 10}
        query = ("SELECT CAST(CAST(paid_at AT TIME ZONE 'UTC' AS DATE) AS VARCHAR) AS day, "
                 "count(*) AS n, CAST(sum(amount) AS VARCHAR) AS amount "
                 "FROM paid_orders GROUP BY 1 ORDER BY 1")
        api_key = secrets.token_hex(16)
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "DATA_AGENT_API_KEYS": api_key}
        port = _port()
        with _process([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                       "--port", str(port)], live_directory, env) as service:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers={"X-API-Key": api_key},
                              trust_env=False, timeout=20) as http:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline and service.poll() is None:
                    try:
                        if http.get("/health").is_success:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail("HTTP service failed to start")
                imported = http.post("/api/v1/connect", json=request).raise_for_status().json()
                assert imported["metadata"]["columns"] == ["paid_at", "amount"]
                assert imported["metadata"]["row_count"] == 3
                sid = imported["session_id"]
                catalog = http.get("/api/v1/catalog/tables", params={"session_id": sid}).raise_for_status()
                assert catalog.json()["tables"][0]["description"] == "Loaded from mongodb://127.0.0.1/shop"
                # A failed re-import must preserve the previously registered table.
                bad = http.post("/api/v1/connect", json={**request, "session_id": sid, "filter_sql": "x=1"})
                assert bad.status_code == 400
                result = http.post("/api/v1/tools/sql", json={"session_id": sid, "sql_query": query})
                assert result.raise_for_status().json()["data_preview"] == expected
                for overrides, count in [({"limit": 1}, 1), ({"limit": 0}, 0), ({"mongo_filter": {"status": "missing"}}, 0)]:
                    imported = http.post("/api/v1/connect", json={**request, "session_id": sid, **overrides})
                    assert imported.raise_for_status().json()["metadata"]["row_count"] == count

        async def check_mcp():
            transport = StdioTransport(command=sys.executable, args=["-m", "app.mcp_server"],
                                       env=env, cwd=str(live_directory))
            async with Client(transport) as client:
                result = await client.call_tool("connect_and_load_db", request)
                imported = json.loads(result.content[0].text)
                assert imported["columns"] == ["paid_at", "amount"]
                assert imported["row_count"] == 3
                listed = await client.call_tool("list_session_datasets", {"session_id": imported["session_id"]})
                assert password not in listed.content[0].text
                result = await client.call_tool("duckdb_sql_sandbox",
                                                {"session_id": imported["session_id"], "sql_query": query})
                assert json.loads(result.content[0].text)["result"]["data"] == expected

        asyncio.run(check_mcp())
