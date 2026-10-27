import asyncio,json
import pytest
from tests.test_discount_drivers import sample,put
from tests.test_discount_order_audit import req
from app.schemas.requests import DiscountScenarioRequest
from app.operators.discount_scenarios import simulate_discount_scenarios


def run(s,**kw):
    return simulate_discount_scenarios(DiscountScenarioRequest(**req(s).model_dump(),**kw))


def seed(c):
    for i in range(3):put(c,1,str(i),'A',10,.1)
    put(c,2,'loss','A',10,.6)


def test_break_even_restore_and_demand(sample):
    s,c=sample;seed(c)
    r=run(s,discount_caps=[.2],volume_reductions=[.5],variable_cost_share=1)['result']
    o=r['scenario_orders'][0]
    assert o['target_break_even_discount']==.5
    assert o['restore_uplift']==pytest.approx(500)
    assert o['restored_whole_profit']==pytest.approx(400)
    assert r['scenarios'][0]['uplift']==pytest.approx(400)
    assert r['scenarios'][1]['scenario_profit']==pytest.approx(150)
    assert r['scenarios'][1]['uplift']==pytest.approx(250)
    assert r['scenarios'][0]['volume_loss_tolerance']==pytest.approx(4/3)
    fixed=run(s,discount_caps=[.2],volume_reductions=[.5],variable_cost_share=0)['result']['scenarios'][1]
    assert fixed['scenario_profit']==pytest.approx(-100)
    assert fixed['uplift']==pytest.approx(0)


def test_detail_not_population_and_missing_reference(sample):
    s,c=sample;put(c,1,'a','A',10,.1);put(c,2,'b','A',10,.6);put(c,2,'c','A',10,.2)
    a=run(s)['result'];b=run(s,order_ids=['b'])['result']
    assert a['scenarios']==b['scenarios']
    assert b['scenario_orders'][0]['restore_uplift'] is None
    assert b['scenario_orders'][0]['restored_whole_profit'] is None
    assert run(s,order_ids=["' OR TRUE --"])['result']['scenario_orders']==[]


def test_caps_never_raise_discount_and_rounding(sample):
    s,c=sample;seed(c)
    c.execute("UPDATE t SET s=s+.001,profit=profit+.001 WHERE id='loss'")
    r=run(s,discount_caps=[.8],volume_reductions=[0])['result']
    assert r['scenarios'][0]['uplift']==pytest.approx(0)
    assert r['scenarios'][0]['versus_actual']==pytest.approx(-.001)
    assert r['scenario_selection']['ledger_residual']==pytest.approx(.001)


def test_other_products_and_zero_price(sample):
    s,c=sample;seed(c);put(c,2,'loss','A',10,0,sku='Y')
    data=req(s,product_ids=['X']).model_dump()
    r=simulate_discount_scenarios(DiscountScenarioRequest(**data))['result']
    assert r['scenario_orders'][0]['whole_break_even_discount']==1
    assert r['scenario_orders'][0]['target_break_even_discount']==.5
    put(c,2,'zero','A',10,0,price=0)
    r=run(s,order_ids=['zero'])['result'];assert r['scenario_orders'][0]['target_break_even_discount'] is None


@pytest.mark.parametrize('field,value',[('discount_caps',[float('nan')]),('volume_reductions',[-.1]),('discount_caps',[]),('variable_cost_share',2)])
def test_validation(sample,field,value):
    s,c=sample
    with pytest.raises(ValueError):run(s,**{field:value})


def test_rest_mcp(sample,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings
    from app.mcp_server import mcp
    from fastmcp import Client
    s,c=sample;seed(c);monkeypatch.setattr(settings,'API_KEYS','scenario-test')
    request=DiscountScenarioRequest(**req(s).model_dump()).model_dump(mode='json')
    response=TestClient(app,headers={'X-API-Key':'scenario-test'}).post('/api/v1/tools/simulate_discount_scenarios',json=request)
    assert response.status_code==200,response.text
    async def call():
        async with Client(mcp) as client:
            response=await client.call_tool('simulate_discount_scenarios',{'request':request})
            return json.loads(response.content[0].text)
    result=asyncio.run(call())
    assert result['result']==response.json()['result']
    assert result['evidence']['causal_claim'] is False


def test_cost_frontiers_and_robustness(sample):
    s,c=sample
    for i in range(3):put(c,1,str(i),'A',10,.1)
    put(c,2,'current','A',10,.2)
    r=run(s,discount_caps=[.1],cost_share_cases=[0,.5,1],robustness_volume_drop=.2)['result']
    rows=[x for x in r['risk_frontiers'] if x['is_total']==1]
    assert [float(x['cost_share']) for x in rows]==[0,.5,1]
    assert [x['preserve_profit_max_drop'] for x in rows]==pytest.approx([100/900,100/650,100/400])
    assert [x['nonloss_max_drop'] for x in rows]==pytest.approx([400/900,400/650,1])
    assert [x['stress_profit'] for x in rows]==pytest.approx([220,270,320])
    assert r['robustness'][0]['robustness']=='profit_erodes'
    for row in rows:
        assert row['initial_profit']-row['loss_slope']*row['preserve_profit_root']==pytest.approx(row['baseline_profit'])
        assert row['initial_profit']-row['loss_slope']*row['zero_profit_root']==pytest.approx(0)


def test_frontier_initial_loss_zero_slope_and_all_cases(sample):
    s,c=sample;put(c,1,'base','A',10,.1);put(c,2,'loss','A',10,.6)
    r=run(s,discount_caps=[.6],cost_share_cases=[1])['result']
    row=next(x for x in r['risk_frontiers'] if x['is_total']==1)
    assert row['break_even_status']=='initial_loss'
    assert row['nonloss_max_drop'] is None
    assert row['zero_profit_root']==pytest.approx(1)
    assert row['preserve_profit_max_drop']==1
    c.execute("UPDATE t SET d=.5,s=500,profit=0 WHERE id='loss'")
    row=next(x for x in run(s,discount_caps=[.5],cost_share_cases=[1])['result']['risk_frontiers'] if x['is_total']==1)
    assert row['zero_profit_root'] is None
    assert row['nonloss_max_drop']==1
    assert row['break_even_status']=='all_feasible'


def test_cost_cases_validation_and_drilldown_compatibility(sample):
    from app.schemas.requests import DiscountOrderAuditRequest
    s,c=sample;seed(c)
    with pytest.raises(ValueError):run(s,cost_share_cases=[float('inf')])
    with pytest.raises(ValueError):run(s,robustness_volume_drop=-.1)
    r=run(s)['result']
    DiscountOrderAuditRequest(**r['scenario_orders'][0]['drilldown']['request'])
