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
        sample_rows = eda_data.get("type_inference_sample_rows")
        if sample_rows is not None:
            parts.append(f"语义类型由前 {sample_rows} 行样本推断。")
        distinct_methods = sorted({
            str(v.get("distinct_count_method"))
            for v in cols.values()
            if v.get("distinct_count_method")
        })
        quantile_methods = sorted({
            str(v.get("quantile_method"))
            for v in cols.values()
            if v.get("quantile_method")
        })
        if distinct_methods or quantile_methods:
            parts.append(
                "计数方法："
                + (", ".join(distinct_methods) if distinct_methods else "未标注")
                + "；分位数方法："
                + (", ".join(quantile_methods) if quantile_methods else "未标注")
                + "。"
            )
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
        method = driver_data.get("method")
        if method:
            parts.append(f"分解方法为 {method}。")
        sun = driver_data.get("sun_shapley")
        if sun is None:
            parts.append("结果中的 sun_shapley 为空。")
        elif isinstance(sun, dict):
            parts.append(f"Sun-Shapley 记录了 {sun.get('orderings_used')} 种顺序。")
        unclosed = [
            str(layer.get("dimension_level"))
            for layer in hierarchy
            if layer.get("closes") is False
        ]
        if unclosed:
            parts.append(f"维度 {', '.join(unclosed)} 的子项差值未闭合到总差值。")

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
            verdict = f"【SPSS 统计推断 - 拒绝原假设】{test_name} 判定显著 (p={p_val:.4e})。"
        else:
            verdict = (
                f"【SPSS 统计推断 - 未拒绝原假设】{test_name} 未判定显著 (p={p_val:.4e})。"
                "显著标志同时要求 p 值过线与效应量门槛。"
            )

        return f"{verdict} {conclusion}"

    @classmethod
    def generate_regression_narrative(cls, reg_data: Dict[str, Any]) -> str:
        coefs = reg_data.get("coefficients", [])
        sig_vars = [c["variable"] for c in coefs if c.get("significant") and c["variable"] != "const"]
        model_type = str(reg_data.get("model_type") or "")
        is_logistic = "logistic" in model_type.lower() or (
            "pseudo_r_squared" in reg_data and "r_squared" not in reg_data
        )
        if is_logistic:
            pseudo = reg_data.get("pseudo_r_squared", 0.0)
            llr_p = reg_data.get("llr_p_value", 1.0)
            parts = [
                f"【二元 Logistic 回归】Pseudo R²={pseudo:.4f}，似然比检验 p={llr_p:.4e} "
                f"(模型{'显著有效' if llr_p < 0.05 else '不显著'})。"
            ]
            if sig_vars:
                parts.append(f"其中显著自变量包含：{', '.join(sig_vars)}。")
            return " ".join(parts)

        r2 = reg_data.get("r_squared", 0.0)
        f_p = reg_data.get("f_p_value", 1.0)
        vifs = reg_data.get("multicollinearity_vif", [])
        vif_warns = [v["variable"] for v in vifs if v.get("multicollinearity_warning")]

        parts = [
            f"【多元线性回归模型诊断】模型拟合优度 R²={r2:.4f}，全局显著性 F 检验 p={f_p:.4e} (模型{'显著有效' if f_p<0.05 else '不显著'})。"
        ]
        if sig_vars:
            parts.append(f"其中对因变量产生显著影响的核心自变量包含：{', '.join(sig_vars)}。")
        if vif_warns:
            parts.append(f"⚠️ 计量预警：变量 {', '.join(vif_warns)} 的 VIF 因子超过 10，存在严重多重共线性，建议进行变量剔除或岭回归。")
        return " ".join(parts)
