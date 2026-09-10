import sqlite3
import threading
from datetime import date,timedelta
from sqlalchemy import create_engine,text
from fastapi.testclient import TestClient
from app.database import migrate
from app.main import app
def job(code,batch):return {"job_code":code,"batch_id":batch,"press":"P1","substrate":"纸","planned_date":date.today().isoformat(),"operator":"测试员","description":""}
def batch(code,**kw):
 p={"code":code,"color":"红","supplier":"供应商","received_date":"2026-01-01","expiry_date":"2027-06-01","viscosity":20,"quality_status":"passed"};p.update(kw);return p
def available(client,bid):return [x for x in client.get('/api/batches').json() if x['id']==bid][0]['available_weight']
def _race(fn,n=5):
 barrier=threading.Barrier(n);out=[]
 def run(i):
  c=TestClient(app);barrier.wait();out.append(fn(c,i))
 ts=[threading.Thread(target=run,args=(i,)) for i in range(n)]
 for t in ts:t.start()
 for t in ts:t.join()
 return out
def test_concurrent_reservation_only_sufficient_balance_wins(client):
 bid=client.post('/api/batches',json=batch('C-1',received_weight=50)).json()['id']
 codes=_race(lambda c,i:c.post('/api/jobs',json={**job(f'C-J{i}',bid),'planned_usage':30}).status_code)
 assert sorted(codes)==[201,409,409,409,409]
 assert available(client,bid)==20
 assert len([x for x in client.get('/api/jobs').json() if x['job_code'].startswith('C-J')])==1
def test_concurrent_cancel_only_first_returns_weight(client):
 bid=client.post('/api/batches',json=batch('C-2',received_weight=40)).json()['id']
 jid=client.post('/api/jobs',json={**job('C-JX',bid),'planned_usage':25}).json()['id'];assert available(client,bid)==15
 codes=_race(lambda c,i:c.patch(f'/api/jobs/{jid}/cancel').status_code)
 assert sorted(codes)==[200,409,409,409,409]
 assert available(client,bid)==40
def test_seed_health_duplicate_and_validation(client):
 assert client.get('/health').json()=={'status':'ok'};assert len(client.get('/api/batches').json())==4
 p={"code":"INK-2026-001","color":"红","supplier":"供应商","received_date":"2026-01-01","expiry_date":"2027-01-01","viscosity":20,"quality_status":"passed"}
 assert client.post('/api/batches',json=p).status_code==409;assert client.post('/api/batches',json={"code":"X"}).status_code==422
def test_three_issue_rules(client):
 pending={"code":"PENDING","color":"蓝","supplier":"S","received_date":str(date.today()),"expiry_date":str(date.today()+timedelta(days=5)),"viscosity":20,"quality_status":"pending"}
 pid=client.post('/api/batches',json=pending).json()['id'];assert client.post('/api/jobs',json=job('J-P',pid)).json()['issues_created']==1
 quarantined={**pending,"code":"ISO","quality_status":"quarantined"};qid=client.post('/api/batches',json=quarantined).json()['id'];assert client.post('/api/jobs',json=job('J-I',qid)).json()['issues_created']==1
 expired={**pending,"code":"OLD","quality_status":"passed","received_date":str(date.today()-timedelta(days=10)),"expiry_date":str(date.today()-timedelta(days=1))};eid=client.post('/api/batches',json=expired).json()['id'];assert client.post('/api/jobs',json=job('J-E',eid)).json()['issues_created']==1
 types={x['issue_type'] for x in client.get('/api/issues').json()};assert {'quality_pending','quarantined','expired'}<=types
def test_failed_issue_duplicate_job_and_inactive(client):
 assert client.post('/api/jobs',json=job('FAIL',3)).json()['issues_created']==2
 assert client.post('/api/jobs',json=job('FAIL',3)).status_code==409
 client.patch('/api/batches/2/deactivate');assert client.post('/api/jobs',json=job('OFF',2)).status_code==409
 assert client.post('/api/jobs',json=job('MISS',999)).status_code==404
def test_special_approval_requires_reason(client):
 issue=client.get('/api/issues').json()[0]
 assert client.patch(f"/api/issues/{issue['id']}",json={"status":"approved","resolution_note":""}).status_code==422
 r=client.patch(f"/api/issues/{issue['id']}",json={"status":"approved","resolution_note":"客户书面批准，仅限试印"});assert r.status_code==200
def test_reserve_deducts_and_visible_in_lists(client):
 b=client.post('/api/batches',json=batch('W-1',received_weight=50)).json();assert b['received_weight']==50 and b['available_weight']==50
 r=client.post('/api/jobs',json={**job('J-W1',b['id']),'planned_usage':20});assert r.status_code==201 and r.json()['available_weight']==30
 row=[x for x in client.get('/api/batches').json() if x['id']==b['id']][0];assert row['received_weight']==50 and row['available_weight']==30
 j=[x for x in client.get('/api/jobs').json() if x['job_code']=='J-W1'][0];assert j['planned_usage']==20 and j['status']=='planned'
def test_insufficient_balance_and_duplicate_code_keep_stock(client):
 bid=client.post('/api/batches',json=batch('W-2',received_weight=10)).json()['id']
 r=client.post('/api/jobs',json={**job('J-W2',bid),'planned_usage':11})
 assert r.status_code==409 and '可用重量不足' in r.json()['detail']
 assert available(client,bid)==10 and not [x for x in client.get('/api/jobs').json() if x['job_code']=='J-W2']
 assert client.post('/api/jobs',json={**job('J-W3',bid),'planned_usage':6}).status_code==201;assert available(client,bid)==4
 assert client.post('/api/jobs',json={**job('J-W3',bid),'planned_usage':3}).status_code==409
 assert available(client,bid)==4
def test_issues_still_raised_with_deduction(client):
 bid=client.post('/api/batches',json=batch('W-4',received_weight=30,quality_status='failed',received_date='2026-01-01',expiry_date='2026-02-01')).json()['id']
 r=client.post('/api/jobs',json={**job('J-W4',bid),'planned_usage':12,'planned_date':str(date.today()+timedelta(days=30))})
 assert r.status_code==201 and r.json()['issues_created']==2 and available(client,bid)==18
 types={x['issue_type'] for x in client.get('/api/issues').json() if x['job_code']=='J-W4'};assert types=={'expired','quality_failed'}
def test_cancel_returns_weight_only_once(client):
 bid=client.post('/api/batches',json=batch('W-5',received_weight=40)).json()['id']
 jid=client.post('/api/jobs',json={**job('J-W5',bid),'planned_usage':15}).json()['id'];assert available(client,bid)==25
 r=client.patch(f'/api/jobs/{jid}/cancel');assert r.status_code==200 and r.json()['returned_weight']==15
 assert available(client,bid)==40
 j=[x for x in client.get('/api/jobs').json() if x['id']==jid][0];assert j['status']=='cancelled' and j['cancelled_at']
 again=client.patch(f'/api/jobs/{jid}/cancel');assert again.status_code==409 and '重复' in again.json()['detail']
 assert available(client,bid)==40
 assert client.patch('/api/jobs/999/cancel').status_code==404
def test_compatible_defaults_without_new_fields(client):
 b=client.post('/api/batches',json=batch('W-6')).json();assert b['received_weight']==100 and b['available_weight']==100
 r=client.post('/api/jobs',json=job('J-W6',b['id']));assert r.status_code==201
 assert available(client,b['id'])==100
 j=[x for x in client.get('/api/jobs').json() if x['job_code']=='J-W6'][0];assert j['planned_usage']==0 and j['status']=='planned'
def test_deactivated_batch_blocked_and_stock_untouched(client):
 bid=client.post('/api/batches',json=batch('W-7',received_weight=25)).json()['id']
 client.patch(f'/api/batches/{bid}/deactivate')
 assert client.post('/api/jobs',json={**job('J-W7',bid),'planned_usage':5}).status_code==409
 assert available(client,bid)==25
def test_update_received_weight_syncs_available_by_delta(client):
 bid=client.post('/api/batches',json=batch('D-1',received_weight=50)).json()['id']
 client.post('/api/jobs',json={**job('J-D1',bid),'planned_usage':20});assert available(client,bid)==30
 r=client.put(f'/api/batches/{bid}',json={**batch('D-1',received_weight=40),'active':True})
 assert r.status_code==200 and r.json()['received_weight']==40 and r.json()['available_weight']==20
 assert available(client,bid)==20
 r=client.put(f'/api/batches/{bid}',json={**batch('D-1',received_weight=65),'active':True})
 assert r.status_code==200 and r.json()['available_weight']==45 and available(client,bid)==45
 r=client.put(f'/api/batches/{bid}',json={**batch('D-1',received_weight=65,color='深蓝'),'active':True})
 assert r.status_code==200 and r.json()['available_weight']==45
def test_explicit_zero_planned_usage_rejected(client):
 bid=client.post('/api/batches',json=batch('Z-1',received_weight=10)).json()['id']
 r=client.post('/api/jobs',json={**job('J-Z1',bid),'planned_usage':0})
 assert r.status_code==422
 assert available(client,bid)==10 and not [x for x in client.get('/api/jobs').json() if x['job_code']=='J-Z1']
 r=client.post('/api/jobs',json=job('J-Z2',bid));assert r.status_code==201 and r.json()['available_weight']==10
def test_decimal_reservation_rounds_to_business_precision(client):
 bid=client.post('/api/batches',json=batch('F-1',received_weight=50.3)).json()['id']
 r=client.post('/api/jobs',json={**job('J-F1',bid),'planned_usage':0.1})
 assert r.status_code==201 and r.json()['available_weight']==50.2
 assert available(client,bid)==50.2
 r=client.patch(f"/api/jobs/{r.json()['id']}/cancel")
 assert r.status_code==200 and r.json()['available_weight']==50.3
 assert available(client,bid)==50.3
def _legacy_db(path):
 conn=sqlite3.connect(path)
 conn.executescript("""CREATE TABLE ink_batches(id INTEGER PRIMARY KEY,code VARCHAR(64),color VARCHAR(80),supplier VARCHAR(120),received_date DATE,expiry_date DATE,viscosity FLOAT,quality_status VARCHAR(20),notes TEXT,active BOOLEAN);
 CREATE TABLE press_jobs(id INTEGER PRIMARY KEY,job_code VARCHAR(64),batch_id INTEGER,press VARCHAR(80),substrate VARCHAR(120),planned_date DATE,operator VARCHAR(80),description TEXT,created_at DATETIME);
 INSERT INTO ink_batches VALUES(1,'LEG-1','红','供应商','2026-01-01','2027-01-01',20,'passed','',1);
 INSERT INTO press_jobs VALUES(1,'LEG-J1',1,'P1','纸','2026-02-01','op','','2026-01-01 00:00:00');""")
 conn.commit();conn.close()
def test_migrate_backfills_legacy_rows(tmp_path,monkeypatch):
 db=tmp_path/'legacy.db';_legacy_db(db);eng=create_engine(f'sqlite:///{db}')
 monkeypatch.setenv('DEFAULT_RECEIVED_WEIGHT','66');migrate(eng);migrate(eng)
 with eng.connect() as c:
  assert c.execute(text('SELECT received_weight,available_weight FROM ink_batches WHERE id=1')).one()==(66.0,66.0)
  assert c.execute(text('SELECT planned_usage,status,cancelled_at FROM press_jobs WHERE id=1')).one()==(0.0,'planned',None)
def test_migrate_explicit_default_weight(tmp_path,monkeypatch):
 db=tmp_path/'legacy2.db';_legacy_db(db);eng=create_engine(f'sqlite:///{db}')
 monkeypatch.setenv('DEFAULT_RECEIVED_WEIGHT','66');migrate(eng,default_weight=33)
 with eng.connect() as c:assert c.execute(text('SELECT received_weight FROM ink_batches WHERE id=1')).scalar()==33.0
