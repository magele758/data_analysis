"""ERP enterprise data analysis using the data-analysis-service, end to end.

Loads the ERP tables into an in-memory analytical session, builds a denormalized
sales fact, then drives the service's operators (EDA, OLAP, quality, correlation,
ANOVA, RFM, driver attribution) and the Insight Copilot to produce a Markdown
business report. Runs fully in-process — no server, no auth.

Usage:
    python analyze_erp.py                 # auto-generates sample data, writes report.md
    run_erp_analysis(data_dir, out_path)  # importable entry point (used by tests)
"""

import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.cluster.session_manager import SessionManager
from app.operators.eda import run_eda_profile
from app.operators.olap import run_olap_query
from app.operators.correlation import run_correlation_analysis
from app.operators.spss.hypothesis import run_spss_hypothesis_test
from app.operators.mining.clustering import run_rfm_segmentation
from app.distributed_ops.dist_driver import DistributedDriverAnalysis
from app.observability.assertions import DataQualityAssertions
from app.copilot import discover_insights
from app.nlg.narrative_builder import NarrativeBuilder

FACT = "erp_sales"


def _load_generator():
    """Load the sibling generator by path under a unique module name (avoids
    sys.modules collision with the dota2 example's same-named generator)."""
    import importlib.util
    gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_sample_data.py")
    spec = importlib.util.spec_from_file_location("erp_generate_sample_data", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_session(data_dir: str, session_id: str = "erp_demo"):
    sess = SessionManager().get_or_create_session(session_id)
    con = sess.get_duckdb_conn()
    for tbl in ("customers", "products", "sales_orders", "sales_order_lines"):
        path = os.path.join(data_dir, f"{tbl}.csv").replace("'", "''")
        con.execute(f"CREATE OR REPLACE TABLE {tbl} AS SELECT * FROM read_csv_auto('{path}', header=true)")
    con.execute(f"""
        CREATE OR REPLACE TABLE {FACT} AS
        SELECT l.line_id, o.order_id, o.order_date, o.region, o.channel,
               c.customer_id, c.segment, c.industry,
               p.product_id, p.category,
               l.quantity, l.unit_price, l.discount,
               l.line_total AS sales, l.cogs, l.profit
        FROM sales_order_lines l
        JOIN sales_orders o ON l.order_id = o.order_id
        JOIN customers c ON o.customer_id = c.customer_id
        JOIN products p ON l.product_id = p.product_id
        WHERE o.status = 'Completed'
    """)
    return sess.session_id, con


def run_erp_analysis(data_dir: str, out_path: str) -> dict:
    if not os.path.exists(os.path.join(data_dir, "sales_order_lines.csv")):
        _load_generator().generate(data_dir)

    sid, con = _load_session(data_dir)
    total_rows = con.execute(f"SELECT count(*) FROM {FACT}").fetchone()[0]

    eda = run_eda_profile(sid, FACT)
    olap = run_olap_query(sid, FACT, dimensions=["region", "category"],
                          metrics=["sales", "profit"], agg_funcs=["sum", "sum"], limit=50)
    quality = DataQualityAssertions.run_suite(con, FACT, rules=[
        {"type": "not_null", "column": "order_id"},
        {"type": "not_null", "column": "profit"},
        {"type": "between", "column": "discount", "min_val": 0, "max_val": 1},
        {"type": "row_count", "min_rows": 1, "max_rows": 10_000_000},
    ])
    corr = run_correlation_analysis(sid, FACT, columns=["quantity", "discount", "sales", "profit"])
    anova = run_spss_hypothesis_test(sid, FACT, test_type="one_way_anova",
                                     dependent_var="profit", group_var="region")
    rfm = run_rfm_segmentation(sid, FACT, user_col="customer_id",
                               date_col="order_date", amount_col="sales")
    driver = DistributedDriverAnalysis.analyze_driver(
        con=con, table_name=FACT, target_metric="profit",
        dimension_path=["region", "category"],
        base_filter="order_date < '2025-01-01'",
        current_filter="order_date >= '2025-01-01'",
        agg_func="SUM", top_k=5)
    insights = discover_insights(sid, FACT, target_metric="profit",
                                 category_col="region", time_col="order_date")

    report = _build_report(total_rows, eda, olap, quality, corr, anova, rfm, driver, insights)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    return {"rows": total_rows, "report": out_path, "insights": insights["total_insights"]}


def _fmt(n):
    try:
        return f"{float(n):,.2f}"
    except (TypeError, ValueError):
        return str(n)


def _build_report(rows, eda, olap, quality, corr, anova, rfm, driver, insights) -> str:
    L = []
    L.append("# ERP 企业数据分析报告\n")
    L.append("> 由 data-analysis-service 端到端生成（EDA · OLAP · 质量 · 相关 · ANOVA · RFM · 归因 · Insight Copilot）。\n")

    L.append("## 1. 数据概览与质量")
    L.append(f"- 有效销售明细行：**{rows:,}**（已过滤取消订单）")
    L.append(f"- 数据质量健康分：**{quality.get('data_health_score')}/100**，断言 {quality.get('passed_assertions')}/{quality.get('total_assertions')} 通过")
    L.append(f"- EDA 画像：{NarrativeBuilder.generate_eda_narrative(eda)}\n")

    L.append("## 2. 区域 × 品类 销售与利润 (OLAP)")
    recs = olap.get("records", [])[:10]
    if recs:
        cols = list(recs[0].keys())
        L.append("| " + " | ".join(cols) + " |")
        L.append("|" + "|".join(["---"] * len(cols)) + "|")
        for r in recs:
            L.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")
    L.append("")

    L.append("## 3. 关键相关性")
    pairs = corr.get("high_correlation_pairs", [])
    if pairs:
        for p in pairs:
            L.append(f"- **{p['col1']} ↔ {p['col2']}**：r={p['r']}（{p['strength']}）")
    else:
        L.append("- 未发现强相关列对。")
    L.append("")

    L.append("## 4. 区域利润差异检验 (One-way ANOVA)")
    L.append(f"- {NarrativeBuilder.generate_spss_narrative(anova)}\n")

    L.append("## 5. 客户价值分群 (RFM)")
    segs = rfm.get("segment_distribution") or rfm.get("segments") or {}
    if isinstance(segs, dict) and segs:
        for k, v in list(segs.items())[:8]:
            L.append(f"- {k}: {v}")
    else:
        L.append(f"- RFM 计算完成，覆盖客户数：{rfm.get('total_customers', 'N/A')}")
    L.append("")

    L.append("## 6. 利润环比归因 (2024 → 2025，Driver Attribution)")
    hier = driver.get("hierarchy") or []
    if hier:
        for b in hier[0].get("branches", [])[:5]:
            L.append(f"- {b.get('dimension_value')}: 贡献差异 {_fmt(b.get('diff_value'))}")
    L.append(f"- 叙述：{NarrativeBuilder.generate_driver_narrative(driver)}\n")

    L.append("## 7. 自动洞察 (Insight Copilot)")
    nar = insights.get("narrative", {})
    L.append(f"**{nar.get('headline','')}**\n")
    for s in nar.get("sections", []):
        L.append(f"- {s}")
    g = insights.get("insight_graph", {})
    L.append(f"\n- 洞察图谱：{len(g.get('nodes', []))} 节点 / {len(g.get('edges', []))} 关系")
    if nar.get("recommendation"):
        L.append(f"- **建议**：{nar['recommendation']}")
    L.append("")

    L.append("---")
    L.append("### 附：Insight Copilot 结构化洞察 (Top)")
    for i in insights.get("insights", [])[:6]:
        L.append(f"- `[{i['type']}]` {i['title']} — severity {i['severity']}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    res = run_erp_analysis(os.path.join(here, "data"), os.path.join(here, "report.md"))
    print("ERP analysis done:", json.dumps(res, ensure_ascii=False))
