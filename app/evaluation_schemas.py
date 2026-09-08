from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator


class EvaluationCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enrollment_id:int=Field(gt=0)
    evaluation_type:Literal['FEEDBACK','LEARNING','APPLICATION']
    evaluator_source:Literal['PARTICIPANT','AUTHORIZED_REVIEWER']='PARTICIPANT'
    evaluator_id:int|None=Field(default=None,gt=0)
    available_at:AwareDatetime|None=None
    due_at:AwareDatetime|None=None


class EvaluationSubmit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)
    answers:dict[str,Any]
