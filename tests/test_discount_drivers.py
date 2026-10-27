import pytest
from app.cluster.session_manager import SessionManager
from app.schemas.requests import DiscountDriversRequest
from app.operators.discount_drivers import analyze_discount_drivers

@pytest.fixture
def sample():
    s=SessionManager().get_or_create_session();c=s.get_duckdb_conn()
    c.execute('CREATE TABLE t(dt VARCHAR,id VARCHAR,sku VARCHAR,customer VARCHAR,q DOUBLE,p DOUBLE,d DOUBLE,s DOUBLE,c DOUBLE,profit DOUBLE)')
    yield s,c
    SessionManager().drop_session(s.session_id)

def request(s,**kwargs):
    return DiscountDriversRequest(session_id=s.session_id,dataset_name='t',metric={'kind':'sum','column':'profit'},time=dict(column='dt',base_start='2024-01-01',base_end='2024-02-01',current_start='2024-02-01',current_end='2024-03-01',complete_until='2024-03-01'),mapping=dict(order='id',product='sku',quantity='q',price='p',discount='d',sales='s',cost='c'),dimensions=['customer'],**kwargs)

def put(c,period,oid,customer,q,d,sku='X',price=100):
    sales=q*price*(1-d);cost=q*50
    c.execute('INSERT INTO t VALUES (?,?,?,?,?,?,?,?,?,?)',[f'2024-0{period}-01',oid,sku,customer,q,price,d,sales,cost,sales-cost])

def view(r,name):return next(x for x in r['result']['views'] if x['dimension']==name)

def test_pure_rate_change(sample):
    s,c=sample;put(c,1,'a','A',10,.1);put(c,2,'b','A',10,.2)
    r=analyze_discount_drivers(request(s));v=view(r,'customer')['totals']
    assert v['rate_effect']==pytest.approx(-100)
    assert v['structure_effect']==0
    assert v['reconciliation_error']==pytest.approx(0)

def test_pure_mix_change_with_unchanged_rates(sample):
    s,c=sample
    for period,qa,qb in [(1,8,2),(2,2,8)]:
        put(c,period,f'{period}a','A',qa,.1);put(c,period,f'{period}b','B',qb,.3)
    r=analyze_discount_drivers(request(s));v=view(r,'customer')['totals']
    assert v['rate_effect']==pytest.approx(0)
    assert v['structure_effect']==pytest.approx(-120)
    assert v['contribution']==pytest.approx(r['result']['profit_bridge']['discount_effect'])

def test_new_member_and_zero_price_closure(sample):
    s,c=sample;put(c,1,'a','A',10,.1);put(c,2,'b','B',10,.3)
    put(c,1,'z','Z',2,.2,sku='Z',price=0);put(c,2,'zz','Z',2,.4,sku='Z',price=100)
    put(c,2,'new','C',3,.2,sku='NEW')
    r=analyze_discount_drivers(request(s))
    for v in r['result']['views']:assert v['totals']['reconciliation_error']==pytest.approx(0,abs=1e-8)

def test_exclusion_topk_focus_preserve_context(sample):
    s,c=sample;put(c,1,'a','A',10,.1);put(c,2,'b','A',10,.2);put(c,2,'c','B',5,.3)
    put(c,1,'bad','A',3,.1);c.execute("UPDATE t SET s=s+1000,profit=profit+1000 WHERE id='bad'")
    req=request(s,top_k=1);r=analyze_discount_drivers(req)
    assert r['result']['excluded_order_ids']==['bad']
    v=view(r,'customer');assert v['truncated']
    assert v['rows'][0]['contribution']+v['totals']['omitted_contribution']==pytest.approx(v['totals']['contribution'])
    focus=analyze_discount_drivers(DiscountDriversRequest(**v['rows'][0]['drilldown']['request']))
    assert focus['result']['profit_bridge']==r['result']['profit_bridge']
    assert [x['totals'] for x in focus['result']['views']]==[x['totals'] for x in r['result']['views']]
    assert sum(x['contribution'] for x in focus['result']['focus']['cells'])==pytest.approx(v['rows'][0]['contribution'])
    assert focus['result']['focus']['cells']
    assert all(o['oid']!='bad' for o in focus['result']['focus']['orders'])
    q=req.model_dump();q.update(focus_dimension='customer',focus_member="x' OR 1=1 --")
    assert not analyze_discount_drivers(DiscountDriversRequest(**q))['result']['focus']['cells']

def test_empty_after_exclusion_fails(sample):
    s,c=sample;put(c,1,'a','A',10,.1);put(c,2,'b','A',10,.2)
    with pytest.raises(ValueError,match='retained'):analyze_discount_drivers(request(s,exclude_order_ids=['b']))

def test_rest_mcp(sample,monkeypatch):
    import asyncio,json
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from app.main import app
    from app.mcp_server import mcp
    from app.config import settings
    s,c=sample;put(c,1,'a','A',10,.1);put(c,2,'b','A',10,.2)
    monkeypatch.setattr(settings,'API_KEYS','discount-test')
    req=request(s).model_dump(mode='json');http=TestClient(app,headers={'X-API-Key':'discount-test'}).post('/api/v1/tools/analyze_discount_drivers',json=req)
    assert http.status_code==200,http.text
    async def run():
        async with Client(mcp) as client:
            r=await client.call_tool('analyze_discount_drivers',{'request':req})
            assert json.loads(r.content[0].text)['result']==http.json()['result']
    asyncio.run(run())
