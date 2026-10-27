"""Execute the report's actual SQL through the service, testing financial identities."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.cluster.session_manager import SessionManager
from app.examples.erp import generate_frames, register_frames, build_fact
from app.operators.sandbox import run_duckdb_sql

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def queries():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required to load frontend analytical query templates')
    script = """
    global.window={};require('./app/web/static/erp-profit-queries.js');
    const q=window.ERPProfitQueries;
    console.log(JSON.stringify({bridge:q.bridge(),orders:q.orders(),west_orders:q.orders('westTech'),
      scopes:['all','south','westTech'].map(s=>q.bridge(s)),
      time:['day','week','month','quarter','year'].map(g=>q.time(g))}));
    """
    return json.loads(subprocess.check_output([node, '-e', script], cwd=ROOT))


@pytest.fixture
def session():
    s = SessionManager().get_or_create_session()
    con = s.get_duckdb_conn()
    con.execute('''CREATE TABLE erp_sales (order_id VARCHAR, order_date VARCHAR,
      region VARCHAR, category VARCHAR, product_id VARCHAR, quantity DOUBLE,
      unit_price DOUBLE, discount DOUBLE, cogs DOUBLE, sales DOUBLE, profit DOUBLE)''')
    yield s
    s.close()


def run(s, sql):
    return run_duckdb_sql(s.session_id, sql, limit=800)['data']


def add(s, year, q, p, d, c, residual=0, sku='A', order=None):
    revenue = q*p*(1-d)+residual
    s.get_duckdb_conn().execute('INSERT INTO erp_sales VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        [order or str(year)+sku, f'{year}-03-01', 'South', 'Technology', sku,q,p,d,q*c,revenue,revenue-q*c])


@pytest.mark.parametrize('changed,factor,expected', [
    ((20,10,0,4),'volume_effect',60),
    ((10,12,0,4),'price_effect',20),
    ((10,10,.2,4),'discount_effect',-20),
    ((10,10,0,5),'cost_effect',-10),
])
def test_isolated_factor(session, queries, changed, factor, expected):
    add(session,2024,10,10,0,4)
    add(session,2025,*changed)
    r=next(r for r in run(session,queries['bridge']) if r['scenario']=='reported')
    assert r[factor] == pytest.approx(expected)
    assert r['delta'] == pytest.approx(expected)
    assert abs(r['reconciliation_error']) < 1e-8


def test_mix_entry_exit_and_interactions_close(session,queries):
    add(session,2024,10,10,.1,4)
    add(session,2025,20,12,.2,5)
    add(session,2024,4,20,0,8,sku='exit')
    add(session,2025,8,15,.1,7,sku='entry')
    r=run(session,queries['bridge'])[0]
    assert abs(r['reconciliation_error']) < 1e-8
    assert r['mix_effect'] != 0


def test_whole_order_sensitivity_and_rounding(session,queries):
    add(session,2024,10,10,0,4,residual=100,order='bad')
    add(session,2024,1,10,0,4,order='bad',sku='B')
    add(session,2024,10,10,0,4,residual=.004,order='good')
    add(session,2025,10,10,0,4)
    a,b=run(session,queries['bridge'])
    assert a['residual_effect']==pytest.approx(-100.004)
    assert b['base_profit']==pytest.approx(60.004)
    assert b['delta']==pytest.approx(-.004)
    assert len(run(session,queries['orders']))==1
    assert abs(a['reconciliation_error'])<1e-8


def test_seeded_all_scopes_and_time_grains(session,queries):
    register_frames(session.get_duckdb_conn(),generate_frames())
    build_fact(session.get_duckdb_conn())
    for sql in queries['scopes']:
        rows=run(session,sql)
        assert len(rows)==2
        assert all(abs(r['reconciliation_error'])<1e-6 for r in rows)
    a,b=run(session,queries['bridge'])
    assert a['delta']==pytest.approx(-136537.05)
    assert b['delta']==pytest.approx(-39221.45)
    assert a['price_effect']==pytest.approx(0,abs=1e-7)
    assert a['cost_effect']==pytest.approx(0,abs=1e-7)
    for sql,count in zip(queries['time'],[731,105,24,8,2]):
        rows=run(session,sql)
        assert len(rows)==count
        assert sum(float(r['profit']) for r in rows)==pytest.approx(a['base_profit']+a['current_profit'])
        assert rows[0]['previous_delta'] is None
    months=run(session,queries['time'][2])
    assert months[12]['yoy_delta']==pytest.approx(months[12]['profit']-months[0]['profit'])
    years=run(session,queries['time'][4])
    assert years[1]['yoy_delta']==pytest.approx(a['delta'])


def test_missing_year_not_comparable(session,queries):
    add(session,2024,10,10,0,4)
    r=run(session,queries['bridge'])[0]
    assert not r['comparable']
    assert r['volume_effect'] is None


def test_scoped_review_table_keeps_whole_order(session,queries):
    add(session,2024,10,10,0,4,residual=100,order='mixed')
    add(session,2024,1,10,0,4,order='mixed',sku='B')
    session.get_duckdb_conn().execute("UPDATE erp_sales SET region='West'")
    session.get_duckdb_conn().execute("UPDATE erp_sales SET category='Furniture' WHERE product_id='B'")
    rows=run(session,queries['west_orders'])
    assert len(rows)==1
    assert rows[0]['lines']==2
    assert rows[0]['profit']==pytest.approx(166)
