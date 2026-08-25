import math
from typing import Dict, Any, List, Optional
import numpy as np
import scipy.stats as stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from app.cluster.session_manager import SessionManager

def run_spss_hypothesis_test(
    session_id: str,
    dataset_name: str,
    test_type: str,
    dependent_var: str,
    group_var: str,
    alpha: float = 0.05
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()

    df = con.execute(f'SELECT "{dependent_var}", "{group_var}" FROM {dataset_name}').df().dropna()
    test_t = test_type.lower()

    if test_t == "independent_t_test":
        unique_groups = df[group_var].unique()
        if len(unique_groups) != 2:
            raise ValueError(f"Independent t-test requires exactly 2 distinct groups, got: {unique_groups}")

        g1_data = df[df[group_var] == unique_groups[0]][dependent_var].values
        g2_data = df[df[group_var] == unique_groups[1]][dependent_var].values

        n1, n2 = len(g1_data), len(g2_data)
        m1, m2 = float(np.mean(g1_data)), float(np.mean(g2_data))
        s1, s2 = float(np.std(g1_data, ddof=1)), float(np.std(g2_data, ddof=1))

        levene_stat, levene_p = stats.levene(g1_data, g2_data)
        equal_var = bool(levene_p > 0.05)

        t_stat, p_val = stats.ttest_ind(g1_data, g2_data, equal_var=equal_var)
        
        pooled_std = math.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2)) if equal_var else math.sqrt((s1**2 + s2**2) / 2)
        cohens_d = (m1 - m2) / pooled_std if pooled_std > 0 else 0.0

        df_val = (n1 + n2 - 2) if equal_var else ((s1**2/n1 + s2**2/n2)**2 / ((s1**2/n1)**2/(n1-1) + (s2**2/n2)**2/(n2-1)))

        sig = bool(p_val < alpha)
        conclusion = (
            f"Independent Samples T-Test: Group '{unique_groups[0]}' (Mean={m1:.2f}, SD={s1:.2f}) vs "
            f"Group '{unique_groups[1]}' (Mean={m2:.2f}, SD={s2:.2f}). "
            f"Levene's Test (F={levene_stat:.3f}, p={levene_p:.4f}) indicates variances are {'equal' if equal_var else 'unequal'}. "
            f"t({df_val:.1f}) = {t_stat:.3f}, p = {p_val:.4f}, Cohen's d = {cohens_d:.3f}. "
            f"The difference between groups is {'statistically significant (Reject H0)' if sig else 'not statistically significant (Fail to reject H0)'} at alpha={alpha}."
        )

        return {
            "test_name": "Independent Samples T-Test",
            "levene_test": {"statistic": round(float(levene_stat), 4), "p_value": round(float(levene_p), 6), "equal_variance": equal_var},
            "t_statistic": round(float(t_stat), 4),
            "degrees_of_freedom": round(float(df_val), 2),
            "p_value": round(float(p_val), 6),
            "significant": sig,
            "effect_size_cohens_d": round(float(cohens_d), 4),
            "group_descriptives": {
                str(unique_groups[0]): {"count": n1, "mean": round(m1, 4), "std": round(s1, 4)},
                str(unique_groups[1]): {"count": n2, "mean": round(m2, 4), "std": round(s2, 4)},
            },
            "formal_conclusion": conclusion
        }

    elif test_t == "one_way_anova":
        groups = [group[dependent_var].values for _, group in df.groupby(group_var)]
        
        if len(groups) < 2:
            raise ValueError("One-way ANOVA requires at least 2 groups")

        f_stat, p_val = stats.f_oneway(*groups)
        
        all_vals = np.concatenate(groups)
        grand_mean = np.mean(all_vals)
        ss_total = np.sum((all_vals - grand_mean)**2)
        ss_between = np.sum([len(g) * (np.mean(g) - grand_mean)**2 for g in groups])
        eta_squared = (ss_between / ss_total) if ss_total > 0 else 0.0

        tukey_results = []
        if p_val < alpha and len(groups) > 2:
            tukey = pairwise_tukeyhsd(endog=df[dependent_var], groups=df[group_var], alpha=alpha)
            for row in tukey.summary().data[1:]:
                tukey_results.append({
                    "group1": str(row[0]),
                    "group2": str(row[1]),
                    "meandiff": round(float(row[2]), 4),
                    "p_adj": round(float(row[3]), 4),
                    "reject_h0": bool(row[5])
                })

        sig = bool(p_val < alpha)
        conclusion = (
            f"One-Way ANOVA across {len(groups)} levels of '{group_var}': "
            f"F({len(groups)-1}, {len(all_vals)-len(groups)}) = {f_stat:.3f}, p = {p_val:.6f}, eta_squared = {eta_squared:.3f}. "
            f"The effect of '{group_var}' on '{dependent_var}' is {'statistically significant' if sig else 'not significant'}."
        )

        return {
            "test_name": "One-Way ANOVA",
            "f_statistic": round(float(f_stat), 4),
            "df_between": len(groups) - 1,
            "df_within": len(all_vals) - len(groups),
            "p_value": round(float(p_val), 6),
            "significant": sig,
            "effect_size_eta_squared": round(float(eta_squared), 4),
            "post_hoc_tukey_hsd": tukey_results,
            "formal_conclusion": conclusion
        }

    elif test_t == "chi_square":
        contingency_table = df.groupby([dependent_var, group_var]).size().unstack(fill_value=0)
        chi2_stat, p_val, dof, expected = stats.chi2_contingency(contingency_table)
        
        n = contingency_table.values.sum()
        min_dim = min(contingency_table.shape) - 1
        cramers_v = math.sqrt(chi2_stat / (n * max(1, min_dim))) if n > 0 else 0.0

        sig = bool(p_val < alpha)
        conclusion = (
            f"Pearson's Chi-Square Test of Independence: chi2({dof}) = {chi2_stat:.3f}, p = {p_val:.6f}, "
            f"Cramér's V = {cramers_v:.3f}. There is {'a significant' if sig else 'no significant'} association "
            f"between '{dependent_var}' and '{group_var}'."
        )

        return {
            "test_name": "Chi-Square Test of Independence",
            "chi2_statistic": round(float(chi2_stat), 4),
            "degrees_of_freedom": int(dof),
            "p_value": round(float(p_val), 6),
            "significant": sig,
            "effect_size_cramers_v": round(float(cramers_v), 4),
            "formal_conclusion": conclusion
        }

    elif test_t == "mann_whitney":
        unique_groups = df[group_var].unique()
        g1 = df[df[group_var] == unique_groups[0]][dependent_var].values
        g2 = df[df[group_var] == unique_groups[1]][dependent_var].values
        stat_val, p_val = stats.mannwhitneyu(g1, g2, alternative='two-sided')
        sig = bool(p_val < alpha)

        return {
            "test_name": "Mann-Whitney U Test (Non-parametric)",
            "u_statistic": round(float(stat_val), 4),
            "p_value": round(float(p_val), 6),
            "significant": sig,
            "formal_conclusion": f"Mann-Whitney U = {stat_val:.2f}, p = {p_val:.6f}. Differences are {'significant' if sig else 'not significant'}."
        }

    raise ValueError(f"Unsupported test_type: '{test_type}'")
