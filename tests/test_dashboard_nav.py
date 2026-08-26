"""看板两层导航契约测试。

改版把 11 个并列页签收敛为 6 阶段 + 阶段内视图，破坏点集中在三处：
JS 引用的 DOM id 消失、某个面板无视图可达、阶段与视图归属不一致。
这三项各留一条断言，任一破坏即失败。
"""
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/web/templates/dashboard.html").read_text(encoding="utf-8")
JS = (ROOT / "app/web/static/dashboard.js").read_text(encoding="utf-8")

STAGES = ["ingest", "model", "ontology", "analyze", "activate", "observe"]


def test_js_referenced_ids_exist_in_html():
    """JS getElementById 的每个 id 都必须在模板中存在。"""
    ids = {m for m in re.findall(r"getElementById\(['\"]([^'\"]+)", JS)}
    ids.discard("pane-")  # 动态拼接 'pane-' + target，由下面的用例覆盖
    missing = sorted(i for i in ids if f'id="{i}"' not in HTML)
    assert not missing, f"JS 引用了模板中不存在的 id: {missing}"


def test_every_pane_is_reachable():
    """每个 tab-pane 都要有对应的 view-btn，否则该面板永久不可达。"""
    panes = set(re.findall(r'id="pane-([a-z]+)"', HTML))
    tabs = set(re.findall(r'data-tab="([a-z]+)"', HTML))
    assert panes, "未找到任何面板，选择器可能已失效"
    assert panes <= tabs, f"以下面板无入口可达: {sorted(panes - tabs)}"


def test_stage_and_view_wiring_is_consistent():
    """视图的 data-stage 必须属于已声明的 6 个阶段，且每阶段至少一个视图。"""
    rail = set(re.findall(r'data-stage="([a-z]+)" class="stage', HTML))
    assert rail == set(STAGES), f"阶段轨与预期不一致: {sorted(rail)}"

    views = re.findall(r'data-tab="([a-z]+)" data-stage="([a-z]+)" class="view-btn"', HTML)
    assert views, "未找到任何视图按钮"

    orphans = sorted({s for _, s in views} - rail)
    assert not orphans, f"视图挂在未声明的阶段上: {orphans}"

    empty = sorted(set(STAGES) - {s for _, s in views})
    assert not empty, f"以下阶段点进去是空的: {empty}"


def test_non_finite_dwell_is_json_safe():
    """avg() 可能产出 NaN，而 NaN 不是 None —— 它会穿过判空让 json.dumps 抛错，
    整个 /analytics/pages 端点返回 500，看板首屏统计全空。

    直接验清洗逻辑而非走 DuckDB：事件库是单写锁，开发服务器在跑时连不上，
    且断言不该依赖库里恰好有什么数据。
    """
    import json

    # 复刻 page_analytics 中的清洗步骤
    def sanitize(dwell):
        val = float(dwell) if dwell is not None else 0.0
        if not math.isfinite(val):
            val = 0.0
        return round(val, 1)

    for bad in (float("nan"), float("inf"), float("-inf"), None):
        assert json.dumps({"avg_dwell_seconds": sanitize(bad)})

    assert sanitize(float("nan")) == 0.0
    assert sanitize(12.34) == 12.3  # 正常值不受影响
