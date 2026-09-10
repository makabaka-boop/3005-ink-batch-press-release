from contextlib import asynccontextmanager
from datetime import date,datetime,timedelta
from fastapi import Depends,FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session,joinedload
from .database import Base,SessionLocal,engine,get_db,migrate
from .models import InkBatch,Issue,PressJob
from .schemas import BatchIn,BatchOut,BatchUpdate,IssueAction,JobComplete,JobIn,JobSwitch
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
 # 入库重量调整时可用重量按差额同步增减，已预占部分不受影响；按业务精度保留 3 位小数
 delta=round(data.received_weight-x.received_weight,3)
 for k,v in data.model_dump().items():setattr(x,k,v)
 if delta:x.available_weight=round(x.available_weight+delta,3)
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
 rows=db.scalars(select(PressJob).options(joinedload(PressJob.batch),joinedload(PressJob.previous_batch)).order_by(PressJob.created_at.desc())).all()
 return [{"id":x.id,"job_code":x.job_code,"batch_id":x.batch_id,"batch_code":x.batch.code,"batch_color":x.batch.color,"press":x.press,"substrate":x.substrate,"planned_date":x.planned_date,"operator":x.operator,"description":x.description,"planned_usage":x.planned_usage,"actual_usage":x.actual_usage,"settled_weight":round(x.planned_usage-x.actual_usage,3) if x.actual_usage is not None else None,"status":x.status,"cancelled_at":x.cancelled_at,"completed_at":x.completed_at,"created_at":x.created_at,"previous_batch_id":x.previous_batch_id,"previous_batch_code":x.previous_batch.code if x.previous_batch else None,"switched_at":x.switched_at} for x in rows]
@app.post("/api/jobs",status_code=201)
def create_job(data:JobIn,db:Session=Depends(get_db)):
 batch=db.get(InkBatch,data.batch_id)
 if not batch:raise HTTPException(404,"油墨批次不存在")
 if not batch.active:raise HTTPException(409,"已停用批次不能创建上机记录")
 if db.scalar(select(PressJob).where(PressJob.job_code==data.job_code)):raise HTTPException(409,"工单号已存在")
 # 单条 UPDATE 原子完成「校验余额并扣减」，并发预占时只有余额足够的请求能命中；结果按业务精度保留 3 位小数，避免浮点尾数
 r=db.execute(update(InkBatch).where(InkBatch.id==batch.id,InkBatch.available_weight>=data.planned_usage).values(available_weight=func.round(InkBatch.available_weight-data.planned_usage,3)))
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
 # 仅当状态仍为计划中时原子翻转为已取消，已完成工单不得取消；并发取消只有一个请求能命中并进入返还逻辑
 r=db.execute(update(PressJob).where(PressJob.id==item_id,PressJob.status=="planned").values(status="cancelled",cancelled_at=datetime.now()))
 if r.rowcount!=1:
  db.rollback();cur=db.scalar(select(PressJob.status).where(PressJob.id==item_id))
  raise HTTPException(409,"工单已取消，不能重复取消" if cur=="cancelled" else "工单已完成，不能取消")
 db.execute(update(InkBatch).where(InkBatch.id==job.batch_id).values(available_weight=func.round(InkBatch.available_weight+job.planned_usage,3)))
 db.commit();left=db.scalar(select(InkBatch.available_weight).where(InkBatch.id==job.batch_id))
 return {"id":job.id,"status":"cancelled","returned_weight":job.planned_usage,"available_weight":left}
@app.patch("/api/jobs/{item_id}/complete")
def complete_job(item_id:int,data:JobComplete,db:Session=Depends(get_db)):
 job=db.get(PressJob,item_id)
 if not job:raise HTTPException(404,"工单不存在")
 if job.status!="planned":raise HTTPException(409,"工单已完成，不能重复完成" if job.status=="completed" else "工单已取消，不能完成")
 # 以原计划预占为基准结算：少用返还差额，超用从批次可用重量补扣；超用超出可用重量时余额不足，整笔回滚保持原值
 delta=round(data.actual_usage-job.planned_usage,3)
 if delta>0:
  r=db.execute(update(InkBatch).where(InkBatch.id==job.batch_id,InkBatch.available_weight>=delta).values(available_weight=func.round(InkBatch.available_weight-delta,3)))
  if r.rowcount!=1:
   db.rollback();left=db.scalar(select(InkBatch.available_weight).where(InkBatch.id==job.batch_id))
   raise HTTPException(409,f"批次可用重量不足：超用 {delta} kg，批次剩余 {left} kg，工单与库存均未改动")
 else:
  db.execute(update(InkBatch).where(InkBatch.id==job.batch_id).values(available_weight=func.round(InkBatch.available_weight-delta,3)))
 now=datetime.now()
 r=db.execute(update(PressJob).where(PressJob.id==item_id,PressJob.status=="planned").values(status="completed",actual_usage=data.actual_usage,completed_at=now))
 if r.rowcount!=1:
  db.rollback();raise HTTPException(409,"工单已完成或已取消，不能重复完成")
 db.commit();left=db.scalar(select(InkBatch.available_weight).where(InkBatch.id==job.batch_id))
 return {"id":job.id,"status":"completed","actual_usage":data.actual_usage,"settled_weight":round(-delta,3),"available_weight":left,"completed_at":now}
@app.patch("/api/jobs/{item_id}/switch")
def switch_job_batch(item_id:int,data:JobSwitch,db:Session=Depends(get_db)):
 job=db.get(PressJob,item_id)
 if not job:raise HTTPException(404,"工单不存在")
 if job.status!="planned":raise HTTPException(409,"工单已完成，不能换料" if job.status=="completed" else "工单已取消，不能换料")
 target=db.get(InkBatch,data.batch_id)
 if not target:raise HTTPException(404,"油墨批次不存在")
 if target.id==job.batch_id:raise HTTPException(409,"目标批次与当前批次相同，无需换料")
 if not target.active:raise HTTPException(409,"目标批次已停用，不能换料")
 # 同一事务内先按计划用量返还原批次，再原子预占目标批次；目标余额不足时整笔回滚，工单归属与两边余额均保持原值
 db.execute(update(InkBatch).where(InkBatch.id==job.batch_id).values(available_weight=func.round(InkBatch.available_weight+job.planned_usage,3)))
 r=db.execute(update(InkBatch).where(InkBatch.id==target.id,InkBatch.available_weight>=job.planned_usage).values(available_weight=func.round(InkBatch.available_weight-job.planned_usage,3)))
 if r.rowcount!=1:
  db.rollback();left=db.scalar(select(InkBatch.available_weight).where(InkBatch.id==target.id))
  raise HTTPException(409,f"目标批次可用重量不足：批次剩余 {left} kg，计划用量 {job.planned_usage} kg，工单与库存均未改动")
 now=datetime.now();prev_id,prev_code=job.batch_id,job.batch.code
 r=db.execute(update(PressJob).where(PressJob.id==item_id,PressJob.status=="planned").values(batch_id=target.id,previous_batch_id=prev_id,switched_at=now))
 if r.rowcount!=1:
  db.rollback();raise HTTPException(409,"工单已完成或已取消，不能换料")
 # 沿用创建工单的日期与质检规则，为目标批次补充该批次尚不存在的对应问题；相同风险在不同批次各自保留独立检查记录，原问题不改动
 existing={x.issue_type for x in db.scalars(select(Issue).where(Issue.job_id==job.id,Issue.batch_id==target.id))}
 issues=[]
 if target.expiry_date<job.planned_date:issues.append(("expired","计划上机日已超过批次有效期"))
 if target.quality_status in QUALITY_REASON:issues.append(QUALITY_REASON[target.quality_status])
 created=0
 for typ,reason in issues:
  if typ not in existing:db.add(Issue(job_id=job.id,batch_id=target.id,issue_type=typ,reason=reason));created+=1
 db.commit();left=db.scalar(select(InkBatch.available_weight).where(InkBatch.id==target.id))
 return {"id":job.id,"status":"planned","batch_id":target.id,"batch_code":target.code,"previous_batch_id":prev_id,"previous_batch_code":prev_code,"switched_at":now,"issues_created":created,"available_weight":left}
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
