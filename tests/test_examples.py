"""Smoke tests for the end-to-end example analyses.

They generate seeded sample data into a temp dir, run the full service-driven
analysis, and assert the report is produced with the expected sections — so the
examples stay runnable as the service evolves.
"""

import importlib.util
import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(rel_path, mod_name):
    path = os.path.join(_REPO, rel_path)
    d = os.path.dirname(path)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_erp_example_end_to_end(tmp_path):
    m = _load("examples/erp-analysis/analyze_erp.py", "analyze_erp")
    out = tmp_path / "report.md"
    res = m.run_erp_analysis(str(tmp_path / "data"), str(out))
    assert res["rows"] > 100
    assert res["insights"] >= 1
    text = out.read_text(encoding="utf-8")
    assert "ERP 企业数据分析报告" in text
    for section in ("OLAP", "ANOVA", "RFM", "Driver Attribution", "Insight Copilot"):
        assert section in text
    assert "%%" not in text  # narrative percent must render cleanly


def test_dota2_example_end_to_end(tmp_path):
    m = _load("examples/dota2-analysis/analyze_dota2.py", "analyze_dota2")
    out = tmp_path / "report.md"
    # tmp has no real data -> synthesizes sample (9 teams incl. Xtreme Gaming).
    res = m.run_dota2_analysis(str(tmp_path / "data"), str(out))
    assert res["teams"] == 9
    assert res["players"] == 45
    assert res["focus_team"] == "Xtreme Gaming" and res["focus_games"] > 0
    text = out.read_text(encoding="utf-8")
    assert "Dota 2 战队深度分析报告" in text and "Xtreme Gaming" in text
    for section in ("XG 战绩概览", "对阵各对手", "节奏画像", "签名英雄", "制胜因子", "战术指导"):
        assert section in text
    assert "ban" in text.lower()
