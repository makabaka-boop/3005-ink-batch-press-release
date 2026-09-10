from datetime import date,timedelta
def job(code,batch):return {"job_code":code,"batch_id":batch,"press":"P1","substrate":"纸","planned_date":date.today().isoformat(),"operator":"测试员","description":""}
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
