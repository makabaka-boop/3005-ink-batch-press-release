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
 jobs:Mapped[list[PressJob]]=relationship(back_populates="batch")
class PressJob(Base):
 __tablename__="press_jobs"
 id:Mapped[int]=mapped_column(primary_key=True); job_code:Mapped[str]=mapped_column(String(64),unique=True,index=True)
 batch_id:Mapped[int]=mapped_column(ForeignKey("ink_batches.id")); press:Mapped[str]=mapped_column(String(80)); substrate:Mapped[str]=mapped_column(String(120))
 planned_date:Mapped[date]=mapped_column(Date); operator:Mapped[str]=mapped_column(String(80)); description:Mapped[str]=mapped_column(Text,default="")
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now); batch:Mapped[InkBatch]=relationship(back_populates="jobs")
class Issue(Base):
 __tablename__="issues"
 id:Mapped[int]=mapped_column(primary_key=True); job_id:Mapped[int]=mapped_column(ForeignKey("press_jobs.id")); batch_id:Mapped[int]=mapped_column(ForeignKey("ink_batches.id"))
 issue_type:Mapped[str]=mapped_column(String(40)); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now); reason:Mapped[str]=mapped_column(Text)
 status:Mapped[str]=mapped_column(String(20),default="pending"); resolution_note:Mapped[str]=mapped_column(Text,default="")
 job:Mapped[PressJob]=relationship(); batch:Mapped[InkBatch]=relationship()
