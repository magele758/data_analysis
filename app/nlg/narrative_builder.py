from typing import Dict, Any, List
import jinja2

class NarrativeBuilder:
    """
    Deterministic, rule-based & template-driven Natural Language Generator (NLG).
    100% self-contained local synthesis of mathematical & statistical results into professional analyst insights.
    NO external LLM API needed!
    """

    @classmethod
    def generate_eda_narrative(cls, eda_data: Dict[str, Any]) -> str:
        total_rows = eda_data.get("total_rows", 0)
        total_cols = eda_data.get("total_columns", 0)
        q_score = eda_data.get("quality_score", 100)
        cols = eda_data.get("columns", {})
        
        measures = [k for k, v in cols.items() if v.get("semantic_type") == "MEASURE"]
        categoricals = [k for k, v in cols.items() if v.get("semantic_type") == "DIMENSION_CATEGORICAL"]
        null_issues = [f"{k} ({v.get('null_percentage')}% 缺失)" for k, v in cols.items() if v.get("null_percentage", 0) > 5]

        parts = [
            f"【数据资产画像】数据集共包含 {total_rows:,} 行、{total_cols} 列，综合数据质量评分为 {q_score}/100 分。",
            f"识别出连续度量指标 {len(measures)} 个（{', '.join(measures[:4])}{'等' if len(measures)>4 else ''}），"
            f"离散分类维度 {len(categoricals)} 个（{', '.join(categoricals[:4])}{'等' if len(categoricals)>4 else ''}）。"
        ]
        if null_issues:
            parts.append(f"⚠️ 质量警示：发现明显数据缺失列 {', '.join(null_issues)}。")
        else:
            parts.append("✅ 数据完整性良好，未发现异常缺失字段。")
        return " ".join(parts)

    @classmethod
    def generate_driver_narrative(cls, driver_data: Dict[str, Any]) -> str:
        metric = driver_data.get("target_metric", "Target")
        diff = driver_data.get("diff_total", 0.0)
        rate = driver_data.get("growth_rate_pct", 0.0)
        hierarchy = driver_data.get("hierarchy", [])
        
        direction_word = "增长" if diff > 0 else "下滑"
        parts = [
            f"【异动归因分析】目标指标 '{metric}' 整体发生波动：{direction_word} {abs(diff):,.2f} ({rate:+.2f}%)。"
        ]

        for layer in hierarchy:
            dim = layer.get("dimension_level")
            top_pos = layer.get("top_positive_drivers", [])
            top_neg = layer.get("top_negative_drivers", [])
            
            layer_strs = []
            if diff < 0 and top_neg:
                lead = top_neg[0]
                layer_strs.append(f"主导负向拖累项为 '{lead['dimension_value']}' (变动 {lead['diff_value']:,.2f}, 贡献率 {lead['contribution_percentage']}%)")
            elif diff > 0 and top_pos:
                lead = top_pos[0]
                layer_strs.append(f"主导正向拉动项为 '{lead['dimension_value']}' (变动 +{lead['diff_value']:,.2f}, 贡献率 {lead['contribution_percentage']}%)")

            if layer_strs:
                parts.append(f"在维度 '{dim}' 层级：{'; '.join(layer_strs)}。")

        return " ".join(parts)

    @classmethod
    def generate_spss_narrative(cls, spss_data: Dict[str, Any]) -> str:
        test_name = spss_data.get("test_name", "Statistical Test")
        p_val = spss_data.get("p_value", 1.0)
        sig = spss_data.get("significant", False)
        conclusion = spss_data.get("formal_conclusion", "")
        
        if sig:
            verdict = f"【SPSS 统计推断 - 拒绝原假设】{test_name} 结果具有极显著统计学差异 (p={p_val:.4e} < 0.05)。"
        else:
            verdict = f"【SPSS 统计推断 - 接受原假设】{test_name} 结果未达到统计学显著性差异 (p={p_val:.4f} >= 0.05)。"

        return f"{verdict} {conclusion}"

    @classmethod
    def generate_regression_narrative(cls, reg_data: Dict[str, Any]) -> str:
        r2 = reg_data.get("r_squared", 0.0)
        f_p = reg_data.get("f_p_value", 1.0)
        coefs = reg_data.get("coefficients", [])
        vifs = reg_data.get("multicollinearity_vif", [])

        sig_vars = [c["variable"] for c in coefs if c.get("significant") and c["variable"] != "const"]
        vif_warns = [v["variable"] for v in vifs if v.get("multicollinearity_warning")]

        parts = [
            f"【多元线性回归模型诊断】模型拟合优度 R²={r2:.4f}，全局显著性 F 检验 p={f_p:.4e} (模型{'显著有效' if f_p<0.05 else '不显著'})。"
        ]
        if sig_vars:
            parts.append(f"其中对因变量产生显著影响的核心自变量包含：{', '.join(sig_vars)}。")
        if vif_warns:
            parts.append(f"⚠️ 计量预警：变量 {', '.join(vif_warns)} 的 VIF 因子超过 10，存在严重多重共线性，建议进行变量剔除或岭回归。")
        return " ".join(parts)
