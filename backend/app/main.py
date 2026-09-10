from contextlib import asynccontextmanager
from datetime import date,datetime,timedelta
from fastapi import Depends,FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session,joinedload
from .database import Base,SessionLocal,engine,get_db,migrate
from .models import InkBatch,Issue,PressJob
from .schemas import BatchIn,BatchOut,BatchUpdate,IssueAction,JobIn
QUALITY_REASON={"pending":("quality_pending","质检状态为待检，未经检验不得上机"),"failed":("quality_failed","质检结果不合格，不得上机"),"quarantined":("quarantined","该批次处于隔离状态，不得上机")}
def seed(db:Session):
 if db.scalar(select(func.count(InkBatch.id))): return
 today=date.today(); rows=[
  InkBatch(code="INK-2026-001",color="潘通 186C 红",supplier="华彩油墨",received_date=today-timedelta(days=40),expiry_date=today+timedelta(days=140),viscosity=24.5,quality_status="passed",notes="食品包装用",received_weight=200,available_weight=200),
  InkBatch(code="INK-2026-002",color="深海蓝",supplier="恒印材料",received_date=today-timedelta(days=60),expiry_date=today+timedelta(days=12),viscosity=27.0,quality_status="passed",notes="即将到期",received_weight=50,available_weight=50),
  InkBatch(code="INK-2026-003",color="哑光黑",supplier="华彩油墨",received_date=today-timedelta(days=190),expiry_date=today-timedelta(days=5),viscosity=31.2,quality_status="failed",notes="复检不合格",received_weight=80,available_weight=80),
  InkBatch(code="INK-2026-004",color="暖金",supplier="金点特墨",received_date=today-timedelta(days=8),expiry_date=today+timedelta(days=300),viscosity=22.8,quality_status="quarantined",notes="等待供应商确认",received_weight=120,available_weight=120)]
 db.add_all(rows);db.flush(); job=PressJob(job_code="JOB-2026-001",batch_id=rows[2].id,press="海德堡 XL75",substrate="250g 白卡纸",planned_date=today,operator="王工",description="包装盒试印",planned_usage=12);db.add(job);db.flush()
 rows[2].available_weight-=job.planned_usage
 db.add_all([Issue(job_id=job.id,batch_id=rows[2].id,issue_type="expired",reason="批次已过有效期"),Issue(job_id=job.id,batch_id=rows[2].id,issue_type="quality_failed",reason="质检结果不合格，不得上机")]);db.commit()
@asynccontextmanager
async def lifespan(app:FastAPI):
 Base.metadata.create_all(engine);migrate()
 with SessionLocal() as db:seed(db)
 yield
app=FastAPI(title="油墨批次上机放行台 API",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
@app.get("/health")
def health():return {"status":"ok"}
@app.get("/api/batches")
def batches(code:str="",color:str="",supplier:str="",quality_status:str="",db:Session=Depends(get_db)):
 q=select(InkBatch).order_by(InkBatch.code)
 if code:q=q.where(InkBatch.code.contains(code))
 if color:q=q.where(InkBatch.color.contains(color))
 if supplier:q=q.where(InkBatch.supplier.contains(supplier))
 if quality_status:q=q.where(InkBatch.quality_status==quality_status)
 return db.scalars(q).all()
@app.post("/api/batches",response_model=BatchOut,status_code=201)
def create_batch(data:BatchIn,db:Session=Depends(get_db)):
 x=InkBatch(**data.model_dump(),available_weight=data.received_weight);db.add(x)
 try:db.commit()
 except IntegrityError:db.rollback();raise HTTPException(409,"批次编号已存在")
 db.refresh(x);return x
@app.put("/api/batches/{item_id}",response_model=BatchOut)
def update_batch(item_id:int,data:BatchUpdate,db:Session=Depends(get_db)):
 x=db.get(InkBatch,item_id)
 if not x:raise HTTPException(404,"油墨批次不存在")
 for k,v in data.model_dump().items():setattr(x,k,v)
 try:db.commit()
 except IntegrityError:db.rollback();raise HTTPException(409,"批次编号已存在")
 return x
@app.patch("/api/batches/{item_id}/deactivate")
def deactivate(item_id:int,db:Session=Depends(get_db)):
 x=db.get(InkBatch,item_id)
 if not x:raise HTTPException(404,"油墨批次不存在")
 x.active=False;db.commit();return {"id":x.id,"active":False}
@app.get("/api/jobs")
def jobs(db:Session=Depends(get_db)):
 rows=db.scalars(select(PressJob).options(joinedload(PressJob.batch)).order_by(PressJob.created_at.desc())).all()
 return [{"id":x.id,"job_code":x.job_code,"batch_id":x.batch_id,"batch_code":x.batch.code,"batch_color":x.batch.color,"press":x.press,"substrate":x.substrate,"planned_date":x.planned_date,"operator":x.operator,"description":x.description,"planned_usage":x.planned_usage,"status":x.status,"cancelled_at":x.cancelled_at,"created_at":x.created_at} for x in rows]
@app.post("/api/jobs",status_code=201)
def create_job(data:JobIn,db:Session=Depends(get_db)):
 batch=db.get(InkBatch,data.batch_id)
 if not batch:raise HTTPException(404,"油墨批次不存在")
 if not batch.active:raise HTTPException(409,"已停用批次不能创建上机记录")
 if db.scalar(select(PressJob).where(PressJob.job_code==data.job_code)):raise HTTPException(409,"工单号已存在")
 # 单条 UPDATE 原子完成「校验余额并扣减」，并发预占时只有余额足够的请求能命中
 r=db.execute(update(InkBatch).where(InkBatch.id==batch.id,InkBatch.available_weight>=data.planned_usage).values(available_weight=InkBatch.available_weight-data.planned_usage))
 if r.rowcount!=1:
  db.rollback();left=db.scalar(select(InkBatch.available_weight).where(InkBatch.id==data.batch_id))
  raise HTTPException(409,f"可用重量不足：批次剩余 {left} kg，计划用量 {data.planned_usage} kg")
 db.refresh(batch)
 job=PressJob(**data.model_dump());db.add(job)
 try:db.flush()
 except IntegrityError:db.rollback();raise HTTPException(409,"工单号已存在")
 issues=[]
 if batch.expiry_date<data.planned_date:issues.append(("expired","计划上机日已超过批次有效期"))
 if batch.quality_status in QUALITY_REASON:issues.append(QUALITY_REASON[batch.quality_status])
 for typ,reason in issues:db.add(Issue(job_id=job.id,batch_id=batch.id,issue_type=typ,reason=reason))
 db.commit();return {"id":job.id,**data.model_dump(),"issues_created":len(issues),"available_weight":batch.available_weight}
@app.patch("/api/jobs/{item_id}/cancel")
def cancel_job(item_id:int,db:Session=Depends(get_db)):
 job=db.get(PressJob,item_id)
 if not job:raise HTTPException(404,"工单不存在")
 # 仅当状态仍为未取消时原子翻转为已取消，并发取消只有一个请求能命中并进入返还逻辑
 r=db.execute(update(PressJob).where(PressJob.id==item_id,PressJob.status!="cancelled").values(status="cancelled",cancelled_at=datetime.now()))
 if r.rowcount!=1:db.rollback();raise HTTPException(409,"工单已取消，不能重复取消")
 db.execute(update(InkBatch).where(InkBatch.id==job.batch_id).values(available_weight=InkBatch.available_weight+job.planned_usage))
 db.commit();left=db.scalar(select(InkBatch.available_weight).where(InkBatch.id==job.batch_id))
 return {"id":job.id,"status":"cancelled","returned_weight":job.planned_usage,"available_weight":left}
@app.get("/api/issues")
def issues(status:str="",db:Session=Depends(get_db)):
 q=select(Issue).options(joinedload(Issue.job),joinedload(Issue.batch)).order_by(Issue.created_at.desc(),Issue.id.desc())
 if status:q=q.where(Issue.status==status)
 return [{"id":x.id,"job_code":x.job.job_code,"batch_code":x.batch.code,"batch_color":x.batch.color,"issue_type":x.issue_type,"created_at":x.created_at,"reason":x.reason,"status":x.status,"resolution_note":x.resolution_note} for x in db.scalars(q).all()]
@app.patch("/api/issues/{item_id}")
def action(item_id:int,data:IssueAction,db:Session=Depends(get_db)):
 x=db.get(Issue,item_id)
 if not x:raise HTTPException(404,"问题不存在")
 x.status=data.status;x.resolution_note=data.resolution_note;db.commit();return {"id":x.id,"status":x.status,"resolution_note":x.resolution_note}
@app.get("/api/stats")
def stats(db:Session=Depends(get_db)):
 today=date.today();soon=today+timedelta(days=30)
 return {"batches":db.scalar(select(func.count(InkBatch.id))),"passed":db.scalar(select(func.count(InkBatch.id)).where(InkBatch.quality_status=="passed",InkBatch.active==True)),"expiring_soon":db.scalar(select(func.count(InkBatch.id)).where(InkBatch.expiry_date>=today,InkBatch.expiry_date<=soon,InkBatch.active==True)),"jobs":db.scalar(select(func.count(PressJob.id))),"pending_issues":db.scalar(select(func.count(Issue.id)).where(Issue.status=="pending"))}
