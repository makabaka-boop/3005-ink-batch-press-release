from __future__ import annotations
from datetime import date,datetime
from typing import Optional
from sqlalchemy import Boolean,Date,DateTime,Float,ForeignKey,String,Text
from sqlalchemy.orm import Mapped,mapped_column,relationship
from .database import Base
class InkBatch(Base):
 __tablename__="ink_batches"
 id:Mapped[int]=mapped_column(primary_key=True); code:Mapped[str]=mapped_column(String(64),unique=True,index=True)
 color:Mapped[str]=mapped_column(String(80),index=True); supplier:Mapped[str]=mapped_column(String(120),index=True)
 received_date:Mapped[date]=mapped_column(Date); expiry_date:Mapped[date]=mapped_column(Date,index=True)
 viscosity:Mapped[float]=mapped_column(Float); quality_status:Mapped[str]=mapped_column(String(20),index=True)
 notes:Mapped[str]=mapped_column(Text,default=""); active:Mapped[bool]=mapped_column(Boolean,default=True)
 received_weight:Mapped[float]=mapped_column(Float,default=0.0); available_weight:Mapped[float]=mapped_column(Float,default=0.0)
 jobs:Mapped[list[PressJob]]=relationship(back_populates="batch",foreign_keys="PressJob.batch_id")
 inspections:Mapped[list[ViscosityInspection]]=relationship(back_populates="batch")
class PressJob(Base):
 __tablename__="press_jobs"
 id:Mapped[int]=mapped_column(primary_key=True); job_code:Mapped[str]=mapped_column(String(64),unique=True,index=True)
 batch_id:Mapped[int]=mapped_column(ForeignKey("ink_batches.id")); press:Mapped[str]=mapped_column(String(80)); substrate:Mapped[str]=mapped_column(String(120))
 planned_date:Mapped[date]=mapped_column(Date); operator:Mapped[str]=mapped_column(String(80)); description:Mapped[str]=mapped_column(Text,default="")
 planned_usage:Mapped[float]=mapped_column(Float,default=0.0); status:Mapped[str]=mapped_column(String(20),default="planned",index=True)
 actual_usage:Mapped[Optional[float]]=mapped_column(Float,nullable=True)
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now); cancelled_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
 completed_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
 previous_batch_id:Mapped[Optional[int]]=mapped_column(ForeignKey("ink_batches.id"),nullable=True)
 # 换料前批次编号在换料时快照保存，后续批次改编号不影响历史换料记录
 previous_batch_code:Mapped[Optional[str]]=mapped_column(String(64),nullable=True)
 switched_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
 batch:Mapped[InkBatch]=relationship(back_populates="jobs",foreign_keys=[batch_id])
 previous_batch:Mapped[Optional[InkBatch]]=relationship(foreign_keys=[previous_batch_id])
class Issue(Base):
 __tablename__="issues"
 # 巡检产生的黏度漂移问题不依赖工单，job_id 可空；旧库的 NOT NULL 约束由 migrate 重建表放宽
 id:Mapped[int]=mapped_column(primary_key=True); job_id:Mapped[Optional[int]]=mapped_column(ForeignKey("press_jobs.id"),nullable=True); batch_id:Mapped[int]=mapped_column(ForeignKey("ink_batches.id"))
 issue_type:Mapped[str]=mapped_column(String(40)); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now); reason:Mapped[str]=mapped_column(Text)
 status:Mapped[str]=mapped_column(String(20),default="pending"); resolution_note:Mapped[str]=mapped_column(Text,default="")
 job:Mapped[Optional[PressJob]]=relationship(); batch:Mapped[InkBatch]=relationship()
class ViscosityInspection(Base):
 __tablename__="viscosity_inspections"
 id:Mapped[int]=mapped_column(primary_key=True); batch_id:Mapped[int]=mapped_column(ForeignKey("ink_batches.id"),index=True)
 measured_at:Mapped[datetime]=mapped_column(DateTime); viscosity:Mapped[float]=mapped_column(Float)
 operator:Mapped[str]=mapped_column(String(80)); notes:Mapped[str]=mapped_column(Text,default="")
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now)
 batch:Mapped[InkBatch]=relationship(back_populates="inspections")
