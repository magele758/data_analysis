import pytest
from tests.test_order_investigation import request_data
from app.schemas.requests import OrderReconciliationRequest
from app.operators.order_reconciliation import reconcile_order_amounts


def args(data,**kw):
    req,_=data
    return OrderReconciliationRequest(**{k:v for k,v in req.items() if k!='anomaly_column'},**kw)


def test_auto_selection_and_exact_exclusion(request_data):
    r=reconcile_order_amounts(args(request_data))
    d=r['result']
    assert d['selection']['selected_orders']==1
    assert d['orders'][0]['oid']=='bad'
    assert d['tax_fee_status']=='unknown_missing_fields'
    assert d['duplicate_id_status']=='unknown_missing_line_id'
    assert d['line_evidence'][0]['observed_multiplier']==10
    assert d['line_evidence'][0]['matching_multipliers']==[10]
    original,review=d['profit_bridges']
    assert review['delta']-original['delta']==pytest.approx(-440)
    assert review['reconciliation_error']==pytest.approx(0,abs=1e-8)
    assert r['evidence']['causal_claim'] is False


def test_duplicate_and_tax_evidence(request_data):
    req,c=request_data
    c.execute('ALTER TABLE orders ADD COLUMN tax DOUBLE DEFAULT 0')
    c.execute("UPDATE orders SET tax=450 WHERE id='bad'")
    c.execute("INSERT INTO orders SELECT * FROM orders WHERE id='bad'")
    d=reconcile_order_amounts(args(request_data,line_id='id',adjustments=['tax']))['result']
    assert d['line_evidence'][0]['same_business_values']==2
    assert d['line_evidence'][0]['same_line_id']==2
    assert d['line_evidence'][0]['unexplained_after_adjustments']==0
    assert d['selection']['adjustment_covered_lines']==2
    assert d['tax_fee_status']=='mapped_line_adjustments'


def test_truncation_does_not_change_excluded_orders(request_data):
    _,c=request_data
    c.execute("INSERT INTO orders VALUES ('2024-02-03','bad2','A',1,100,0,200,60,140)")
    a=reconcile_order_amounts(args(request_data,limit=1));b=reconcile_order_amounts(args(request_data,limit=100))
    assert a['evidence']['truncation']['truncated']
    assert a['result']['selection']['selected_orders']==2
    assert a['result']['profit_bridges']==b['result']['profit_bridges']


def test_unknown_adjustment_and_missing_order(request_data):
    _,c=request_data;c.execute('ALTER TABLE orders ADD COLUMN tax DOUBLE')
    d=reconcile_order_amounts(args(request_data,adjustments=['tax']))['result']
    assert d['line_evidence'][0]['unexplained_after_adjustments'] is None
    assert not reconcile_order_amounts(args(request_data,order_ids=["x' OR 1=1 --"]))['result']['orders']


def test_zero_expected_and_invalid_multiplier(request_data):
    from pydantic import ValidationError
    _,c=request_data;c.execute("UPDATE orders SET d=1 WHERE id='bad'")
    row=reconcile_order_amounts(args(request_data))['result']['line_evidence'][0]
    assert row['observed_multiplier'] is None and row['matching_multipliers'] is None
    with pytest.raises(ValidationError):args(request_data,multipliers=[float('inf')])


def test_rest_and_mcp(request_data,monkeypatch):
    import asyncio,json
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from app.main import app
    from app.config import settings
    from app.mcp_server import mcp
    monkeypatch.setattr(settings,'API_KEYS','test-reconcile')
    req=args(request_data)
    r=TestClient(app,headers={'X-API-Key':'test-reconcile'}).post('/api/v1/tools/reconcile_order_amounts',json=req.model_dump(mode='json'))
    assert r.status_code==200,r.text
    async def run():
        async with Client(mcp) as client:
            result=await client.call_tool('reconcile_order_amounts',{'request':req.model_dump(mode='json')})
            assert json.loads(result.content[0].text)['result']==r.json()['result']
    asyncio.run(run())

def test_empty_review_period_not_zero_and_ledger_skip(request_data):
    _,c=request_data
    d=reconcile_order_amounts(args(request_data,order_ids=['discount','bad','unknown']))['result']
    review=next(x for x in d['profit_bridges'] if x['scenario']=='excluding_selected')
    assert not review['comparable'] and review['delta'] is None
    assert not d['effect_changes']
    c.execute("UPDATE orders SET profit=profit+1 WHERE id='bad'")
    d=reconcile_order_amounts(args(request_data))['result']
    assert d['skipped'] and not any(x['scenario']=='original' for x in d['profit_bridges'])
    assert d['line_evidence'][0]['ledger_gap']==1
