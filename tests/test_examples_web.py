"""Tests for the built-in runnable examples (in-app module + REST endpoints)."""

from fastapi.testclient import TestClient
from app.config import settings

settings.API_KEYS = "test-api-key"

from app.main import app
from app import examples

client = TestClient(app, headers={"X-API-Key": "test-api-key"})


def test_list_examples_has_both_domains():
    ids = {e["id"] for e in examples.list_examples()}
    assert {"erp", "dota2"} <= ids


def test_run_erp_example_in_memory():
    r = examples.run_example("erp", session_id="erp_web_test")
    assert r["rows"] > 100
    assert r["dataset_name"] == "erp_sales"
    assert r["insights"]["total_insights"] >= 1
    assert "ERP 企业数据分析报告" in r["report_markdown"]
    assert "%%" not in r["report_markdown"]


def test_run_dota2_example_in_memory():
    # Uses REAL OpenDota data bundled in examples/dota2-analysis/real_data.
    r = examples.run_example("dota2", session_id="dota2_web_test")
    assert r["teams"] >= 5 and r["players"] >= 20
    assert "Xtreme Gaming" in r["report_markdown"]  # real XG data
    assert "数据获取日期" in r["report_markdown"]  # acquisition date is cited
    assert r.get("data_note")
    assert "战术指导" in r["report_markdown"]
    assert "ban" in r["report_markdown"].lower()


def test_unknown_example_raises():
    import pytest
    with pytest.raises(ValueError):
        examples.run_example("nope")


def test_rest_list_and_run():
    resp = client.get("/api/v1/examples")
    assert resp.status_code == 200
    assert len(resp.json()["examples"]) >= 2

    run = client.post("/api/v1/examples/erp/run", json={"session_id": "erp_rest_test"})
    assert run.status_code == 200
    body = run.json()
    assert body["dataset_name"] == "erp_sales"
    assert "report_markdown" in body and body["report_markdown"]


def test_rest_unknown_example_404():
    assert client.post("/api/v1/examples/nope/run", json={}).status_code == 404


def test_example_dataset_is_explorable_after_run():
    # Data must land in the given session so the user can keep analyzing it.
    examples.run_example("erp", session_id="erp_explore")
    resp = client.post("/api/v1/tools/eda", json={"session_id": "erp_explore", "dataset_name": "erp_sales"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
