import pytest
from tests.test_discount_drivers import sample,put
from app.schemas.requests import DiscountOrderAuditRequest
from app.operators.discount_order_audit import audit_discount_orders


def req(s,**kwargs):
    return DiscountOrderAuditRequest(session_id=s.session_id,dataset_name='t',metric={'kind':'sum','column':'profit'},time=dict(column='dt',base_start='2024-01-01',base_end='2024-02-01',current_start='2024-02-01',current_end='2024-03-01',complete_until='2024-03-01'),mapping=dict(order='id',product='sku',quantity='q',price='p',discount='d',sales='s',cost='c'),customer_column='customer',channel_column='sku',**kwargs)


def seed(c):
    for i in range(3):put(c,1,str(i),'A',10,.1)
    put(c,2,'loss','A',10,.6)
    put(c,2,'safe','B',10,.2)


def test_loss_and_fallback(sample):
    s,c=sample;seed(c);r=audit_discount_orders(req(s))['result'];orders={x['oid']:x for x in r['orders']}
    assert orders['loss']['priority']=='P1_LOSS'
    assert orders['loss']['scoped_order_profit']==-100
    assert orders['loss']['discount_burden']==pytest.approx(500)
    assert orders['loss']['reference_levels']=='same_product_customer_channel'
    assert orders['safe']['reference_levels']=='same_product_channel'
    assert r['audit_summary']['discount_burden']==pytest.approx(600)


def test_target_loss_not_whole_order_loss(sample):
    s,c=sample;seed(c);put(c,2,'loss','A',100,0,sku='OTHER')
    r=audit_discount_orders(req(s,product_ids=['X']))['result'];o=next(x for x in r['orders'] if x['oid']=='loss')
    assert o['selected_profit']==-100 and o['scoped_order_profit']>0
    assert o['priority']=='P2_SELECTED_LOSS'
    drill=audit_discount_orders(DiscountOrderAuditRequest(**o['drilldown']['request']))['result']
    assert drill['audit_summary']==r['audit_summary']
    assert len(drill['focus']['scoped_order_lines'])==2


def test_reference_counts_orders_not_lines(sample):
    s,c=sample
    for i in range(10):put(c,1,'one','A',1,.1)
    put(c,2,'current','A',10,.6)
    r=audit_discount_orders(req(s))['result']
    assert r['audit_summary']['unbenchmarked_lines']==1
    assert r['audit_summary']['discount_burden'] is None
    assert r['orders'][0]['priority']=='P1_LOSS'
    assert '基期参考不足' in r['orders'][0]['reason']


def test_exclusion_and_topk(sample):
    s,c=sample;seed(c);put(c,2,'bad','A',10,.6);c.execute("UPDATE t SET s=s+1000,profit=profit+1000 WHERE id='bad'")
    r=audit_discount_orders(req(s,top_k=1))
    assert r['result']['selection']['excluded_orders']==1
    assert r['result']['audit_summary']['current_orders']==2
    assert r['evidence']['truncation']['truncated']
    assert r['result']['orders'][0]['oid']=='loss'


def test_focus_injection_and_missing_current(sample):
    s,c=sample;seed(c)
    assert not audit_discount_orders(req(s,focus_order_id="' OR 1=1 --"))['result']['focus']['selected_lines']
    with pytest.raises(ValueError,match='No retained'):audit_discount_orders(req(s,product_ids=['missing']))


def test_rest_mcp(sample,monkeypatch):
    import asyncio,json
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from app.main import app
    from app.mcp_server import mcp
    from app.config import settings
    s,c=sample;seed(c);request=req(s).model_dump(mode='json')
    monkeypatch.setattr(settings,'API_KEYS','audit-test')
    response=TestClient(app,headers={'X-API-Key':'audit-test'}).post('/api/v1/tools/audit_discount_orders',json=request)
    assert response.status_code==200,response.text
    async def run():
        async with Client(mcp) as client:
            result=await client.call_tool('audit_discount_orders',{'request':request})
            assert json.loads(result.content[0].text)['result']==response.json()['result']
    asyncio.run(run())

def test_other_product_accounting_issue_precedes_loss(sample):
    s,c=sample;seed(c);put(c,2,'loss','A',1,0,sku='OTHER')
    c.execute("UPDATE t SET s=0,profit=-50 WHERE id='loss' AND sku='OTHER'")
    r=audit_discount_orders(req(s,product_ids=['X'],exclude_amount_mismatches=False))['result']
    order=next(x for x in r['orders'] if x['oid']=='loss')
    assert order['priority']=='P0_ACCOUNTING'
    assert r['orders'][0]['oid']=='loss'

def test_member_drill_preserves_benchmark(sample):
    s,c=sample;seed(c)
    r=audit_discount_orders(req(s))['result']
    row=next(x for x in r['breakdown']['customer'] if x['member']=='A')
    d=audit_discount_orders(DiscountOrderAuditRequest(**row['drilldown']['request']))['result']
    assert d['audit_summary']==r['audit_summary']
    assert d['reference_coverage']==r['reference_coverage']
    assert {x['oid'] for x in d['focus']['selected_lines']}=={'loss'}
    assert {x['oid'] for x in d['focus']['scoped_order_lines']}=={'loss'}
