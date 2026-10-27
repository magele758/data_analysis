import pytest
from app.cluster.session_manager import SessionManager
from app.schemas.requests import OrderInvestigationRequest
from app.operators.order_investigation import investigate_orders

@pytest.fixture
def request_data():
    s=SessionManager().get_or_create_session();c=s.get_duckdb_conn()
    c.execute('CREATE TABLE orders(dt VARCHAR,id VARCHAR,sku VARCHAR,q DOUBLE,p DOUBLE,d DOUBLE,s DOUBLE,c DOUBLE,profit DOUBLE)')
    rows=[('2024-01-01',str(i),'A',1,100,0,100,60,40) for i in range(6)]
    rows += [('2024-01-02','large','A',100,100,0,10000,6000,4000),('2024-02-01','discount','A',1,100,.5,50,60,-10),('2024-02-02','bad','A',1,100,.5,500,60,440),('2024-02-03','unknown','B',1,100,0,100,60,40)]
    c.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)',rows)
    req=dict(session_id=s.session_id,dataset_name='orders',metric={'kind':'sum','column':'profit'},time=dict(column='dt',base_start='2024-01-01',base_end='2024-02-01',current_start='2024-02-01',current_end='2024-03-01',complete_until='2024-03-01'),anomaly_column='profit',mapping=dict(order='id',product='sku',quantity='q',price='p',discount='d',sales='s',cost='c'))
    yield req,c
    SessionManager().drop_session(s.session_id)

def test_classification_and_conservation(request_data):
    req,_=request_data;r=investigate_orders(OrderInvestigationRequest(**req))['result'];o={x['oid']:x for x in r['orders']}
    assert o['bad']['category']=='amount_mismatch' and o['bad']['discount_issue']
    assert o['discount']['category']=='discount_outlier'
    assert o['large']['category']=='large_order_checks_passed'
    assert o['unknown']['category']=='insufficient_evidence'
    assert sum(x['contribution'] for x in r['categories'])==pytest.approx(r['comparison']['delta'])
    assert r['reconciliation']['error']==pytest.approx(0)
    assert r['reconciliation']['overlapping_issues']==1

def test_detail_keeps_reference_and_injection_safe(request_data):
    req,_=request_data;a=investigate_orders(OrderInvestigationRequest(**req));b=investigate_orders(OrderInvestigationRequest(**req,order_ids=['discount']))
    assert a['result']['categories']==b['result']['categories']
    assert b['result']['line_evidence'][0]['discount_limit']==0
    assert len(b['result']['orders'])==1
    assert not investigate_orders(OrderInvestigationRequest(**req,order_ids=["' OR 1=1 --"]))['result']['orders']

def test_offsetting_mismatches_do_not_cancel(request_data):
    req,c=request_data
    c.execute("INSERT INTO orders VALUES ('2024-02-02','offset','A',1,100,0,110,60,50),('2024-02-02','offset','A',1,100,0,90,60,30)")
    r=investigate_orders(OrderInvestigationRequest(**req,order_ids=['offset']))['result']['orders'][0]
    assert r['amount_gap']==0 and r['absolute_amount_gap']==20 and r['amount_issue']

def test_invalid_mapping_and_truncation(request_data):
    req,c=request_data;r=investigate_orders(OrderInvestigationRequest(**req,limit=1))
    assert r['evidence']['truncation']['truncated']
    c.execute('UPDATE orders SET q=-1')
    with pytest.raises(ValueError,match='invalid order'):investigate_orders(OrderInvestigationRequest(**req))

def test_rest_mcp_parity(request_data,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.mcp_server import investigate_orders_tool
    from app.config import settings
    monkeypatch.setattr(settings,'API_KEYS','test-order-key')
    req,_=request_data
    a=TestClient(app,headers={'X-API-Key':'test-order-key'}).post('/api/v1/tools/investigate_orders',json=req)
    assert a.status_code==200,a.text
    assert a.json()['result']==investigate_orders_tool(OrderInvestigationRequest(**req))['result']

def test_discount_scale_and_benchmark(request_data):
    req,c=request_data
    c.execute('UPDATE orders SET d=d*100')
    req['mapping']['discount_scale']=100
    result=investigate_orders(OrderInvestigationRequest(**req,order_ids=['discount']))['result']
    assert result['line_evidence'][0]['discount']==.5
    row=next(x for x in result['categories'] if x['category']=='discount_outlier')
    assert row['current_excess_discount_amount']==50
    assert '不能证明订单正常' in investigate_orders(OrderInvestigationRequest(**req))['summary']

def test_mcp_transport(request_data):
    import asyncio
    from fastmcp import Client
    from app.mcp_server import mcp
    req,_=request_data
    async def run():
        async with Client(mcp) as client:
            result=await client.call_tool('investigate_orders',{'request':req})
            assert not result.is_error
            import json
            payload=json.loads(result.content[0].text)
            assert payload['evidence']['schema_version']=='2.0'
            assert payload['result']['reconciliation']['overlapping_issues']==1
    asyncio.run(run())
