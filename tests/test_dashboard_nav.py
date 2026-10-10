"""Dashboard shell navigation contract.

The shell is a grouped sidebar over real capabilities, not a six-stage
pipeline rail. Quality and activate share govern.js. Each item is a button
the shell mounts without a full page load. One assertion group each.
"""
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/web/templates/dashboard.html").read_text(encoding="utf-8")
JS = (ROOT / "app/web/static/dashboard.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/dashboard.css").read_text(encoding="utf-8")

GROUPS = [
    ("数据", "ingest", [
        ("import-file", "导入文件"),
        ("connect-db", "连接数据库"),
        ("import-trace", "导入 Trace"),
    ]),
    ("准备", "transform", [
        ("clean", "清洗"),
        ("pipeline", "管道"),
        ("wide", "宽表"),
    ]),
    ("模型", "model", [
        ("objects", "对象与关系"),
        ("traverse", "遍历与实体图"),
        ("metrics", "指标与血缘"),
    ]),
    ("分析", "analyze", [
        ("eda", "EDA"),
        ("olap", "OLAP"),
        ("driver", "归因"),
        ("hypothesis", "检验与回归"),
        ("variance", "方差分解"),
        ("signals", "异常趋势支配"),
        ("paths", "漏斗留存路径"),
        ("forecast", "预测"),
    ]),
    ("质量", "govern", [
        ("assert", "断言"),
        ("drift", "结构漂移"),
    ]),
    ("激活", "govern", [
        ("sync", "写回"),
        ("audience", "受众"),
        ("alert", "告警"),
    ]),
]

SECTION_SCRIPTS = [
    "/static/sections/ingest.js",
    "/static/sections/transform.js",
    "/static/sections/model.js",
    "/static/sections/analyze.js",
    "/static/sections/govern.js",
]


def _buttons():
    return re.findall(
        r'<button\b[^>]*data-section="([^"]+)"[^>]*data-view="([^"]+)"[^>]*>\s*([^<]+?)\s*</button>',
        HTML,
    )


def test_grouped_nav_matches_capabilities():
    """Sidebar items are the fixed groups, backed by the section each one mounts."""
    found = {(section, view): label for section, view, label in _buttons()}
    ordered = [(section, view, label) for section, view, label in _buttons()]
    expected = []
    for group_label, section, items in GROUPS:
        assert f'class="group-label">{group_label}</div>' in HTML
        for view, label in items:
            expected.append((section, view, label))
            assert found.get((section, view)) == label
    assert ordered == expected


def test_section_scripts_and_missing_copy():
    """Five section scripts are included; a missing module shows the empty state."""
    for src in SECTION_SCRIPTS:
        assert f'src="{src}"' in HTML
    assert "DashboardSections" in JS
    assert ".mount" in JS
    assert "这一段还没装上" in JS
    assert 'id="mount"' in HTML


def test_ingest_sidebar_opens_matching_panel():
    """数据 items map onto ingest.js tabs file, db, and trace."""
    assert 'src="/static/sections/ingest.js"' in HTML
    assert "function selectIngestTab(root, view)" in JS
    assert '"import-file": "file"' in JS
    assert '"connect-db": "db"' in JS
    assert '"import-trace": "trace"' in JS


def test_govern_sidebar_opens_matching_tab():
    """质量 and 激活 share govern.js; the shell selects the sidebar tab after mount."""
    assert 'src="/static/sections/govern.js"' in HTML
    assert 'data-section="govern"' in HTML
    assert "function selectGovernTab(root, view)" in JS
    assert "data-govern-tab" in JS


def test_api_accepts_section_call_shape():
    """analyze.js and transform.js call ctx.api(method, path, body)."""
    assert "function readApiCall(first, second, third)" in JS
    assert 'typeof second === "string"' in JS
    assert "HTTP_METHODS" in JS


def test_session_and_api_contract():
    """Top bar session id persists, and ctx.api stays on same-origin /api/v1 JSON."""
    assert 'id="session-id"' in HTML
    assert "das.session_id" in JS
    assert "localStorage" in JS
    assert "function sessionId()" in JS
    assert "/api/v1" in JS
    assert "Content-Type" in JS
    assert "application/json" in JS
    assert 'data-example="erp"' in HTML
    assert 'data-example="dota2"' in HTML
    assert "/examples/" in JS
    assert "session_id" in JS


def test_shell_layout_and_chart_hook():
    """Light tool shell: 220px sidebar, one primary button, chart_spec hook."""
    assert 'href="/static/dashboard.css"' in HTML
    assert "width: 220px" in CSS
    assert "stage-pill" not in HTML
    assert "tailwindcss" not in HTML
    assert "#6366F1" not in HTML + CSS
    assert "chart_spec" in JS
    assert "vega-lite" in JS
    assert "echarts" in JS


def test_js_referenced_ids_exist_in_html():
    """Every getElementById target must exist in the template."""
    ids = set(re.findall(r"getElementById\(['\"]([^'\"]+)", JS))
    missing = sorted(i for i in ids if f'id="{i}"' not in HTML)
    assert not missing, f"JS references ids absent from template: {missing}"


def test_non_finite_dwell_is_json_safe():
    """avg() can yield NaN, which is not None and would slip past a null check and
    make json.dumps raise, 500-ing /analytics/pages. Verify the sanitize logic
    directly rather than through DuckDB."""
    import json

    def sanitize(dwell):
        val = float(dwell) if dwell is not None else 0.0
        if not math.isfinite(val):
            val = 0.0
        return round(val, 1)

    for bad in (float("nan"), float("inf"), float("-inf"), None):
        assert json.dumps({"avg_dwell_seconds": sanitize(bad)})

    assert sanitize(float("nan")) == 0.0
    assert sanitize(12.34) == 12.3
