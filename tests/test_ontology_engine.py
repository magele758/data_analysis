import pytest
import duckdb
from fastapi.testclient import TestClient

from app.config import settings

settings.API_KEYS = "test-api-key"

from app.main import app
from app.cluster.session_manager import SessionManager
from app.ontology.object_type import ObjectType, PropertyMeta
from app.ontology.interface_type import InterfaceType
from app.ontology.link_type import LinkType
from app.ontology.action_type import ActionType, ActionParameter, ActionPrecondition, FunctionType
from app.ontology.ontology_engine import get_ontology_engine
from app.mcp_server import (
    ontology_list_schema,
    ontology_query_objects,
    ontology_query_interfaces,
    ontology_traverse_links,
    ontology_execute_action,
    ontology_evaluate_function,
    ontology_validate_commitment,
)

client = TestClient(app, headers={"X-API-Key": "test-api-key"})

@pytest.fixture
def ontology_session():
    mgr = SessionManager()
    sess = mgr.get_or_create_session("ontology_test_session")
    con = sess.get_duckdb_conn()
    con.execute("""
    CREATE TABLE IF NOT EXISTS dim_customers (
        customer_id VARCHAR PRIMARY KEY,
        name VARCHAR,
        tier VARCHAR,
        balance DOUBLE
    );
    DELETE FROM dim_customers;
    INSERT INTO dim_customers VALUES
    ('C01', 'Alice', 'VIP', 1000.0),
    ('C02', 'Bob', 'STANDARD', 250.0);

    CREATE TABLE IF NOT EXISTS fct_orders (
        order_id VARCHAR PRIMARY KEY,
        customer_id VARCHAR,
        amount DOUBLE,
        status VARCHAR
    );
    DELETE FROM fct_orders;
    INSERT INTO fct_orders VALUES
    ('O101', 'C01', 300.0, 'DELIVERED'),
    ('O102', 'C01', 700.0, 'PENDING'),
    ('O103', 'C02', 150.0, 'DELIVERED');
    """)
    return con

def test_ontology_schema_registration():
    engine = get_ontology_engine()

    # 1. Register Customer Object
    customer_obj = ObjectType(
        name="Customer",
        display_name="客户实体",
        description="企业客户核心实体",
        primary_key="customer_id",
        title_property="name",
        backed_by_table="dim_customers",
        properties=[
            PropertyMeta(name="customer_id", data_type="string", is_primary_key=True),
            PropertyMeta(name="name", data_type="string", is_title=True),
            PropertyMeta(name="tier", data_type="string"),
            PropertyMeta(name="balance", data_type="float")
        ],
        tags=["core", "crm"]
    )
    engine.register_object_type(customer_obj)

    # 2. Register Order Object
    order_obj = ObjectType(
        name="Order",
        display_name="订单实体",
        primary_key="order_id",
        backed_by_table="fct_orders",
        properties=[
            PropertyMeta(name="order_id", data_type="string", is_primary_key=True),
            PropertyMeta(name="customer_id", data_type="string"),
            PropertyMeta(name="amount", data_type="float"),
            PropertyMeta(name="status", data_type="string")
        ]
    )
    engine.register_object_type(order_obj)

    # 3. Register Link Type: Customer -> Orders
    link = LinkType(
        name="customer_orders",
        display_name="客户名下订单",
        source_object_type="Customer",
        target_object_type="Order",
        cardinality="ONE_TO_MANY",
        source_join_key="customer_id",
        target_join_key="customer_id"
    )
    engine.register_link_type(link)

    # 4. Register Action Type
    action = ActionType(
        name="UpgradeCustomerTierAction",
        display_name="升级客户会员等级",
        target_object_type="Customer",
        parameters=[
            ActionParameter(name="new_tier", data_type="string", required=True),
            ActionParameter(name="reason", data_type="string", required=False, default_value="Agent Retention Campaign")
        ],
        handler_type="SQL_MUTATION",
        handler_config={"sql_template": "UPDATE dim_customers SET tier = '{new_tier}' WHERE customer_id = '{instance_id}'"}
    )
    engine.register_action_type(action)

    schema_summary = engine.get_ontology_schema_summary()
    assert len(schema_summary["object_types"]) >= 2
    assert len(schema_summary["link_types"]) >= 1

def test_ontology_query_and_traversal(ontology_session):
    engine = get_ontology_engine()

    # Query Customer instances
    res = engine.query_object_instances(
        con=ontology_session,
        object_type_name="Customer",
        filters="tier = 'VIP'"
    )
    assert res["total_instances"] == 1
    assert res["instances"][0]["customer_id"] == "C01"

    # Traverse Link: Customer C01 -> Orders
    trav_res = engine.traverse_links(
        con=ontology_session,
        source_object_type="Customer",
        source_instance_id="C01",
        link_name="customer_orders"
    )
    assert trav_res["target_object_type"] == "Order"
    assert trav_res["linked_count"] == 2
    order_ids = [o["order_id"] for o in trav_res["linked_instances"]]
    assert "O101" in order_ids and "O102" in order_ids

def test_ontology_action_execution_and_audit(ontology_session):
    engine = get_ontology_engine()

    # Execute Action: Upgrade Customer C02 tier to 'GOLD'
    audit = engine.execute_action(
        con=ontology_session,
        action_name="UpgradeCustomerTierAction",
        instance_id="C02",
        parameter_values={"new_tier": "GOLD", "reason": "High LTV growth"}
    )
    assert audit["status"] == "SUCCESS"
    assert audit["action_name"] == "UpgradeCustomerTierAction"
    assert audit["target_instance_id"] == "C02"

    # Verify DuckDB mutation executed
    new_tier = ontology_session.execute("SELECT tier FROM dim_customers WHERE customer_id = 'C02'").fetchone()[0]
    assert new_tier == "GOLD"

    # Verify persistent audit trail
    audits = engine.list_action_audits(limit=10)
    assert len(audits) >= 1
    assert audits[0]["action_name"] == "UpgradeCustomerTierAction"

def test_ontology_mcp_and_api(ontology_session):
    # MCP schema
    schema_json = ontology_list_schema()
    assert "Customer" in schema_json

    # MCP query
    query_json = ontology_query_objects(
        session_id="ontology_test_session",
        object_type="Customer",
        filters="customer_id = 'C01'"
    )
    assert "Alice" in query_json

    # MCP traverse
    trav_json = ontology_traverse_links(
        session_id="ontology_test_session",
        source_object_type="Customer",
        source_instance_id="C01",
        link_name="customer_orders"
    )
    assert "O101" in trav_json

    # REST endpoint
    resp = client.get("/api/v1/ontology/schema")
    assert resp.status_code == 200
    assert "object_types" in resp.json()


def test_ontology_interfaces_polymorphism_and_inheritance(ontology_session):
    engine = get_ontology_engine("iface_test_session")
    ontology_session.execute("""
    CREATE OR REPLACE TABLE fleet_trucks (
        truck_id VARCHAR PRIMARY KEY,
        max_load DOUBLE,
        status VARCHAR
    );
    INSERT INTO fleet_trucks VALUES
    ('TRK-01', 200.0, 'IDLE'),
    ('TRK-02', 80.0, 'MAINTENANCE');

    CREATE OR REPLACE TABLE warehouse_bays (
        bay_id VARCHAR PRIMARY KEY,
        asset_code VARCHAR,
        capacity DOUBLE,
        status VARCHAR
    );
    INSERT INTO warehouse_bays VALUES
    ('BAY-01', 'B-NORTH', 500.0, 'IDLE'),
    ('BAY-02', 'B-SOUTH', 120.0, 'BUSY');
    """)

    base_iface = engine.register_interface_type(InterfaceType(
        name="IdentifiableAsset",
        required_properties=[
            PropertyMeta(name="asset_code", data_type="string"),
        ],
    ))
    assert base_iface.name == "IdentifiableAsset"

    sched_iface = engine.register_interface_type(InterfaceType(
        name="SchedulableAsset",
        extends=["IdentifiableAsset"],
        required_properties=[
            PropertyMeta(name="capacity", data_type="float"),
            PropertyMeta(name="status", data_type="string"),
        ],
    ))
    eff_names = [p.name for p in engine.effective_interface_properties("SchedulableAsset")]
    assert eff_names == ["asset_code", "capacity", "status"]

    # Reject missing required interface property
    with pytest.raises(ValueError, match="missing required property"):
        engine.register_object_type(ObjectType(
            name="BadTruck",
            primary_key="truck_id",
            backed_by_table="fleet_trucks",
            implements=["SchedulableAsset"],
            properties=[
                PropertyMeta(name="truck_id", data_type="string", is_primary_key=True),
                PropertyMeta(name="status", data_type="string"),
            ],
        ))

    # Register DeliveryTruck with property_mappings
    engine.register_object_type(ObjectType(
        name="DeliveryTruck",
        primary_key="truck_id",
        backed_by_table="fleet_trucks",
        implements=["SchedulableAsset"],
        property_mappings={"asset_code": "truck_id", "capacity": "max_load"},
        properties=[
            PropertyMeta(name="truck_id", data_type="string", is_primary_key=True),
            PropertyMeta(name="max_load", data_type="float"),
            PropertyMeta(name="status", data_type="string"),
        ],
    ))
    # Register WarehouseBay implementing SchedulableAsset directly
    engine.register_object_type(ObjectType(
        name="WarehouseBay",
        primary_key="bay_id",
        backed_by_table="warehouse_bays",
        implements=["SchedulableAsset"],
        properties=[
            PropertyMeta(name="bay_id", data_type="string", is_primary_key=True),
            PropertyMeta(name="asset_code", data_type="string"),
            PropertyMeta(name="capacity", data_type="float"),
            PropertyMeta(name="status", data_type="string"),
        ],
    ))

    # Polymorphic query across both implementing ObjectTypes (including inherited IdentifiableAsset!)
    poly = engine.query_interface_instances(
        ontology_session,
        "IdentifiableAsset",
        filters="asset_code IS NOT NULL",
    )
    assert poly["matched_count"] == 4
    assert sorted(poly["implementing_types"]) == ["DeliveryTruck", "WarehouseBay"]

    idle_sched = engine.query_interface_instances(
        ontology_session,
        "SchedulableAsset",
        filters="status = 'IDLE' AND capacity >= 150",
    )
    assert idle_sched["matched_count"] == 2
    assert {r["_instance_id"] for r in idle_sched["instances"]} == {"TRK-01", "BAY-01"}


def test_ontology_preconditions_functions_and_writeback_overlay(ontology_session):
    engine = get_ontology_engine("kinetic_test_session")
    ontology_session.execute("""
    CREATE OR REPLACE TABLE kinetic_orders (
        order_id VARCHAR PRIMARY KEY,
        amount DOUBLE,
        discount_rate DOUBLE,
        status VARCHAR
    );
    INSERT INTO kinetic_orders VALUES
    ('KO-1', 1000.0, 0.05, 'PENDING'),
    ('KO-2', 500.0, 0.10, 'SHIPPED');
    """)

    engine.register_object_type(ObjectType(
        name="KineticOrder",
        primary_key="order_id",
        backed_by_table="kinetic_orders",
        writeback_table="kinetic_order_wb",
        properties=[
            PropertyMeta(name="order_id", data_type="string", is_primary_key=True),
            PropertyMeta(name="amount", data_type="float"),
            PropertyMeta(name="discount_rate", data_type="float"),
            PropertyMeta(name="status", data_type="string"),
            PropertyMeta(name="net_amount", data_type="float", formula="amount * (1.0 - discount_rate)"),
        ],
    ))

    # Register Function on Objects (FoO)
    engine.register_function_type(FunctionType(
        name="ComputeCapDiscount",
        target_object_type="KineticOrder",
        parameters=[
            ActionParameter(name="bonus_rate", data_type="float", required=False, default_value=0.05, min_value=0.0, max_value=0.3),
        ],
        sql_expression="LEAST(0.30, discount_rate + {bonus_rate})",
        return_type="float",
    ))

    fn_eval = engine.evaluate_function(
        ontology_session,
        "ComputeCapDiscount",
        instance_id="KO-1",
        parameter_values={"bonus_rate": 0.10},
    )
    assert pytest.approx(fn_eval["result"], rel=1e-6) == 0.15

    # Register Action with closed-world preconditions and parameter constraints + writeback_table
    engine.register_action_type(ActionType(
        name="ApproveSpecialDiscount",
        target_object_type="KineticOrder",
        parameters=[
            ActionParameter(name="new_discount", data_type="float", required=True, min_value=0.0, max_value=0.40),
            ActionParameter(name="ticket_code", data_type="string", required=True, regex_pattern=r"^TCK-\d+$"),
        ],
        preconditions=[
            ActionPrecondition(
                name="must_be_pending",
                sql_predicate="status = 'PENDING'",
                description="Only PENDING orders can be discounted.",
            ),
            ActionPrecondition(
                name="min_order_amount",
                sql_predicate="amount >= 600",
                description="Order amount must be at least 600.",
            ),
        ],
        handler_type="SQL_MUTATION",
        handler_config={
            "writeback_table": "kinetic_order_wb",
            "set_column": "discount_rate",
            "value_param": "new_discount",
        },
    ))

    # 1. Parameter constraint violations fail-closed
    with pytest.raises(ValueError, match="exceeds max_value"):
        engine.execute_action(
            ontology_session,
            "ApproveSpecialDiscount",
            "KO-1",
            {"new_discount": 0.65, "ticket_code": "TCK-100"},
        )
    with pytest.raises(ValueError, match="does not match regex"):
        engine.execute_action(
            ontology_session,
            "ApproveSpecialDiscount",
            "KO-1",
            {"new_discount": 0.20, "ticket_code": "BAD_CODE"},
        )

    # 2. Precondition failure on KO-2 (SHIPPED and amount < 600) is audited as FAILED
    blocked = engine.execute_action(
        ontology_session,
        "ApproveSpecialDiscount",
        "KO-2",
        {"new_discount": 0.20, "ticket_code": "TCK-100"},
    )
    assert blocked["status"] == "FAILED"
    assert blocked["execution_result"]["reason"] == "PRECONDITION_FAILED"
    assert set(blocked["execution_result"]["failed_preconditions"]) == {"must_be_pending", "min_order_amount"}

    # 3. Valid execution on KO-1 writes to writeback_table and overlays on subsequent reads!
    ok_audit = engine.execute_action(
        ontology_session,
        "ApproveSpecialDiscount",
        "KO-1",
        {"new_discount": 0.25, "ticket_code": "TCK-101"},
        dry_run=False,
    )
    assert ok_audit["status"] == "SUCCESS"
    assert all(p["passed"] for p in ok_audit["precondition_results"])

    # Raw backing table is untouched (0.05)
    raw_disc = ontology_session.execute("SELECT discount_rate FROM kinetic_orders WHERE order_id = 'KO-1'").fetchone()[0]
    assert pytest.approx(raw_disc, rel=1e-6) == 0.05

    # Overlay read (include_writeback=True) reflects 0.25 AND recomputes virtual formula `net_amount` (750.0)!
    overlaid = engine.query_object_instances(
        ontology_session,
        "KineticOrder",
        filters="order_id = 'KO-1'",
        include_writeback=True,
    )
    assert overlaid["writeback_applied"] is True
    row_overlaid = overlaid["instances"][0]
    assert pytest.approx(row_overlaid["discount_rate"], rel=1e-6) == 0.25
    assert pytest.approx(row_overlaid["net_amount"], rel=1e-6) == 750.0

    # Raw read via include_writeback=False still sees 0.05 and net_amount 950.0
    unoverlaid = engine.query_object_instances(
        ontology_session,
        "KineticOrder",
        filters="order_id = 'KO-1'",
        include_writeback=False,
    )
    assert unoverlaid["instances"][0]["discount_rate"] == pytest.approx(0.05)
    assert unoverlaid["instances"][0]["net_amount"] == pytest.approx(950.0)


def test_ontology_symmetric_transitive_links_commitment_and_rbac(ontology_session):
    engine = get_ontology_engine("axiom_test_session")
    ontology_session.execute("""
    CREATE OR REPLACE TABLE org_nodes (
        emp_id VARCHAR PRIMARY KEY,
        manager_id VARCHAR,
        partner_id VARCHAR,
        salary DOUBLE,
        level VARCHAR
    );
    INSERT INTO org_nodes VALUES
    ('M1', NULL, 'M2', 50000.0, 'L5'),
    ('M2', 'M1', NULL, 40000.0, 'L4'),
    ('M3', 'M2', NULL, 30000.0, 'L3'),
    ('M4', 'M3', NULL, 20000.0, 'L2');

    CREATE OR REPLACE TABLE contractor_nodes (
        con_id VARCHAR PRIMARY KEY
    );
    INSERT INTO contractor_nodes VALUES ('M4'), ('C99');
    """)

    engine.register_object_type(ObjectType(
        name="OrgEmployee",
        primary_key="emp_id",
        backed_by_table="org_nodes",
        disjoint_with=["ExternalContractor"],
        allowed_roles=["hr", "exec"],
        properties=[
            PropertyMeta(name="emp_id", data_type="string", is_primary_key=True),
            PropertyMeta(name="manager_id", data_type="string"),
            PropertyMeta(name="partner_id", data_type="string"),
            PropertyMeta(name="salary", data_type="float", min_value=25000.0, sensitive=True, allowed_roles=["exec"]),
            PropertyMeta(name="level", data_type="string", allowed_values=["L3", "L4", "L5"]),
        ],
    ))
    engine.register_object_type(ObjectType(
        name="ExternalContractor",
        primary_key="con_id",
        backed_by_table="contractor_nodes",
        properties=[PropertyMeta(name="con_id", data_type="string", is_primary_key=True)],
    ))

    engine.register_link_type(LinkType(
        name="emp_reports_to",
        source_object_type="OrgEmployee",
        target_object_type="OrgEmployee",
        cardinality="MANY_TO_ONE",
        source_join_key="manager_id",
        target_join_key="emp_id",
        is_transitive=True,
    ))
    engine.register_link_type(LinkType(
        name="emp_peer_partner",
        source_object_type="OrgEmployee",
        target_object_type="OrgEmployee",
        cardinality="ONE_TO_ONE",
        source_join_key="partner_id",
        target_join_key="emp_id",
        is_symmetric=True,
    ))

    # 1. RBAC object access check & sensitive property masking
    with pytest.raises(PermissionError, match="not permitted"):
        engine.query_object_instances(ontology_session, "OrgEmployee", actor_role="guest")

    hr_view = engine.query_object_instances(
        ontology_session, "OrgEmployee", filters="emp_id = 'M1'", actor_role="hr"
    )
    assert hr_view["instances"][0]["salary"] == "***REDACTED***"
    assert "salary" in hr_view["masked_properties"]

    exec_view = engine.query_object_instances(
        ontology_session, "OrgEmployee", filters="emp_id = 'M1'", actor_role="exec"
    )
    assert exec_view["instances"][0]["salary"] == 50000.0

    # 2. Symmetric traversal: M1 has partner_id='M2', M2 has partner_id=NULL -> traversing from M2 finds M1!
    sym_res = engine.traverse_links(
        ontology_session, "OrgEmployee", "M2", "emp_peer_partner", actor_role="exec"
    )
    assert [r["emp_id"] for r in sym_res["linked_instances"]] == ["M1"]

    # 3. Transitive closure: M4 -> M3 -> M2 -> M1
    trans_res = engine.traverse_links(
        ontology_session,
        "OrgEmployee",
        "M4",
        "emp_reports_to",
        include_transitive=True,
        max_hops=4,
        actor_role="exec",
    )
    assert trans_res["transitive_closure"] is True
    assert [r["emp_id"] for r in trans_res["linked_instances"]] == ["M3", "M2", "M1"]
    assert [r["_hop_distance"] for r in trans_res["linked_instances"]] == [1, 2, 3]

    # 4. Formal Ontological Commitment Validation (catches min_value, allowed_values, and disjoint_with overlap on 'M4'!)
    report = engine.validate_ontological_commitment(ontology_session)
    assert report["conforms"] is False
    rules_triggered = {v["rule"] for v in report["violations"]}
    assert {"PROPERTY_MIN_VALUE", "PROPERTY_ALLOWED_VALUES", "DISJOINT_WITH"} <= rules_triggered

    # Fix violations in DB and verify conforms == True
    ontology_session.execute("UPDATE org_nodes SET salary = 28000.0, level = 'L3' WHERE emp_id = 'M4'")
    ontology_session.execute("DELETE FROM contractor_nodes WHERE con_id = 'M4'")
    clean_report = engine.validate_ontological_commitment(ontology_session)
    assert clean_report["conforms"] is True
    assert clean_report["violation_count"] == 0


def test_vertical_slice_db_rest_and_mcp_roundtrip(ontology_session):
    """End-to-end vertical slice: REST registration -> SQLite persistence -> REST/MCP polymorphic query, function eval, action + audit, and commitment validation."""
    import json
    from app.ontology.ontology_engine import OntologyEngine

    # 1. Register Interface via REST
    r_iface = client.post("/api/v1/ontology/interfaces", json={
        "name": "BillableAccount",
        "display_name": "计费账户接口",
        "required_properties": [
            {"name": "account_id", "data_type": "string"},
            {"name": "balance", "data_type": "float"},
        ],
    })
    assert r_iface.status_code == 200
    assert any(i["name"] == "BillableAccount" for i in client.get("/api/v1/ontology/interfaces").json()["interface_types"])

    # 2. Register implementing ObjectType via REST
    r_obj = client.post("/api/v1/ontology/objects", json={
        "name": "BillableCustomer",
        "primary_key": "customer_id",
        "backed_by_table": "dim_customers",
        "implements": ["BillableAccount"],
        "property_mappings": {"account_id": "customer_id"},
        "properties": [
            {"name": "customer_id", "data_type": "string", "is_primary_key": True},
            {"name": "name", "data_type": "string"},
            {"name": "tier", "data_type": "string"},
            {"name": "balance", "data_type": "float", "min_value": 0.0},
        ],
    })
    assert r_obj.status_code == 200

    # 3. Register Function on Objects (FoO) via REST
    r_fn = client.post("/api/v1/ontology/functions", json={
        "name": "CreditLimitProjection",
        "target_object_type": "BillableAccount",
        "parameters": [{"name": "multiplier", "data_type": "float", "default_value": 2.0}],
        "sql_expression": "balance * {multiplier}",
        "return_type": "float",
    })
    assert r_fn.status_code == 200

    # 4. Register Action with FUNCTION handler + writeback_table + precondition via REST
    r_act = client.post("/api/v1/ontology/actions", json={
        "name": "WriteProjectedBalance",
        "target_object_type": "BillableCustomer",
        "parameters": [{"name": "multiplier", "data_type": "float", "default_value": 1.5}],
        "preconditions": [{"name": "positive_balance", "sql_predicate": "balance > 0"}],
        "handler_type": "FUNCTION",
        "handler_config": {
            "function_name": "CreditLimitProjection",
            "writeback_table": "wb_billable_customer",
            "set_column": "balance",
        },
    })
    assert r_act.status_code == 200

    # 5. Verify SQLite persistence roundtrip by constructing a fresh OntologyEngine(persistent=True)
    reloaded = OntologyEngine(persistent=True, session_id="_reloaded_check")
    assert reloaded.get_interface_type("BillableAccount") is not None
    assert reloaded.get_object_type("BillableCustomer").implements == ["BillableAccount"]
    assert reloaded.get_function_type("CreditLimitProjection") is not None
    assert len(reloaded.get_action_type("WriteProjectedBalance").preconditions) == 1

    # 6. Query Interface polymorphically via REST & MCP
    r_poly = client.post("/api/v1/ontology/interfaces/query", json={
        "session_id": "ontology_test_session",
        "interface_name": "BillableAccount",
        "filters": "balance >= 500",
    })
    assert r_poly.status_code == 200
    assert r_poly.json()["matched_count"] == 1
    assert r_poly.json()["instances"][0]["_instance_id"] == "C01"

    mcp_poly = json.loads(ontology_query_interfaces(
        session_id="ontology_test_session",
        interface_name="BillableAccount",
    ))
    assert mcp_poly["status"] == "success"
    assert mcp_poly["data"]["matched_count"] == 2

    # 7. Evaluate Function via REST & MCP
    r_eval = client.post("/api/v1/ontology/functions/evaluate", json={
        "session_id": "ontology_test_session",
        "function_name": "CreditLimitProjection",
        "instance_id": "C01",
        "parameters": {"multiplier": 2.5},
    })
    assert r_eval.status_code == 200
    assert r_eval.json()["result"] == pytest.approx(2500.0)

    mcp_eval = json.loads(ontology_evaluate_function(
        session_id="ontology_test_session",
        function_name="CreditLimitProjection",
        instance_id="C01",
        parameters={"multiplier": 3.0},
    ))
    assert mcp_eval["status"] == "success"
    assert mcp_eval["function_evaluation"]["result"] == pytest.approx(3000.0)

    # 8. Execute FUNCTION Action via REST -> writes to wb_billable_customer -> verify global audit & overlay read!
    r_exec = client.post("/api/v1/ontology/actions/execute", json={
        "session_id": "ontology_test_session",
        "action_name": "WriteProjectedBalance",
        "instance_id": "C01",
        "parameters": {"multiplier": 1.5},
        "dry_run": False,
    })
    assert r_exec.status_code == 200
    audit_id = r_exec.json()["audit_id"]
    assert r_exec.json()["status"] == "SUCCESS"
    assert r_exec.json()["execution_result"]["computed_value"] == pytest.approx(1500.0)

    # Global /api/v1/ontology/audit must contain this audit_id!
    audits = client.get("/api/v1/ontology/audit").json()["audits"]
    assert any(a["audit_id"] == audit_id for a in audits)

    # Overlay read on BillableCustomer returns 1500.0 while raw table still has 1000.0
    r_q = client.post("/api/v1/ontology/instances/query", json={
        "session_id": "ontology_test_session",
        "object_type": "BillableCustomer",
        "filters": "customer_id = 'C01'",
        "include_writeback": True,
    })
    assert r_q.status_code == 200
    assert r_q.json()["instances"][0]["balance"] == pytest.approx(1500.0)

    # 9. Validate Ontological Commitment via REST & MCP
    r_val = client.post("/api/v1/ontology/validate", json={
        "session_id": "ontology_test_session",
        "object_type": "BillableCustomer",
    })
    assert r_val.status_code == 200
    assert r_val.json()["conforms"] is True

    mcp_val = json.loads(ontology_validate_commitment(
        session_id="ontology_test_session",
        object_type="BillableCustomer",
    ))
    assert mcp_val["status"] == "success"
    assert mcp_val["commitment_report"]["conforms"] is True
