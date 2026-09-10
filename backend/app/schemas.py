from datetime import date
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .database import default_received_weight
Quality=Literal["pending","passed","failed","quarantined"]
IssueStatus=Literal["pending","confirmed","approved","closed"]
class BatchIn(BaseModel):
 code:str=Field(min_length=1,max_length=64); color:str=Field(min_length=1,max_length=80); supplier:str=Field(min_length=1,max_length=120)
 received_date:date; expiry_date:date; viscosity:float=Field(gt=0); quality_status:Quality; notes:str=""
 received_weight:float=Field(default_factory=default_received_weight,gt=0)
 @model_validator(mode="after")
 def dates(self):
  if self.expiry_date<self.received_date: raise ValueError("有效期不能早于入库日期")
  return self
class BatchUpdate(BatchIn): active:bool=True
class BatchOut(BatchUpdate): model_config=ConfigDict(from_attributes=True); id:int; available_weight:float=0
class JobIn(BaseModel):
 job_code:str=Field(min_length=1,max_length=64); batch_id:int; press:str=Field(min_length=1,max_length=80); substrate:str=Field(min_length=1,max_length=120)
 planned_date:date; operator:str=Field(min_length=1,max_length=80); description:str=""; planned_usage:float=Field(default=0,ge=0)
 @model_validator(mode="after")
 def usage(self):
  # 旧请求可不填计划用量（默认 0、不扣减）；但明确填 0 属于无实际用量，拒绝创建
  if "planned_usage" in self.model_fields_set and self.planned_usage==0: raise ValueError("计划用量必须大于 0")
  return self
class JobComplete(BaseModel):
 actual_usage:float=Field(gt=0)
class JobSwitch(BaseModel):
 batch_id:int
class IssueAction(BaseModel):
 status:IssueStatus; resolution_note:str=""
 @model_validator(mode="after")
 def approval_reason(self):
  if self.status=="approved" and not self.resolution_note.strip(): raise ValueError("特批放行必须填写理由")
  return self
