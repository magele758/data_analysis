"""Per-session isolation for Catalog / metrics / DAG / lineage.

Real sessions must not see each other's datasets, metrics, or DAG models — a DAG
run in one session must never materialize another session's models.
"""

from app.catalog.meta_registry import get_meta_registry, TableAsset
from app.catalog.semantic_store import get_semantic_store, MetricDefinition
from app.transform.pipeline_dag import get_pipeline_engine, DAGModel
from app.catalog.lineage_tracker import get_lineage_tracker


def test_catalog_is_session_scoped():
    get_meta_registry("sessA").register_table(TableAsset(dataset_name="only_in_A"))
    a = {t.dataset_name for t in get_meta_registry("sessA").list_tables()}
    b = {t.dataset_name for t in get_meta_registry("sessB").list_tables()}
    assert "only_in_A" in a
    assert "only_in_A" not in b


def test_metrics_are_session_scoped():
    get_semantic_store("sessA").register_metric(
        MetricDefinition(name="m_a", table_name="t", formula="SUM(x)"))
    assert any(m.name == "m_a" for m in get_semantic_store("sessA").list_metrics())
    assert not any(m.name == "m_a" for m in get_semantic_store("sessB").list_metrics())


def test_dag_models_are_session_scoped():
    get_pipeline_engine("sessA").register_model(DAGModel(name="mdl_a", sql="SELECT 1"))
    assert any(m.name == "mdl_a" for m in get_pipeline_engine("sessA").list_models())
    # A different session's engine must not carry another session's models.
    assert not any(m.name == "mdl_a" for m in get_pipeline_engine("sessB").list_models())


def test_lineage_is_session_scoped():
    get_lineage_tracker("sessA").record_dependency("src_a", "tgt_a")
    a_nodes = {n["id"] for n in get_lineage_tracker("sessA").get_lineage_graph()["nodes"]}
    b_nodes = {n["id"] for n in get_lineage_tracker("sessB").get_lineage_graph()["nodes"]}
    assert "src_a" in a_nodes
    assert "src_a" not in b_nodes
