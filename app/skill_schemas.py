from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillWrite(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    canonical_name:str=Field(min_length=1,max_length=160)
    description:str=Field(default='',max_length=3000)
    group_id:int=Field(gt=0)
    aliases:list[str]=Field(default_factory=list,max_length=30)
    status:Literal['ACTIVE','INACTIVE']='ACTIVE'
    expected_version:int|None=Field(default=None,ge=1)
    @field_validator('aliases')
    @classmethod
    def alias_lengths(cls,values):
        if any(not v.strip() or len(v)>160 for v in values):raise ValueError('Eş adlar 1–160 karakter olmalıdır.')
        return [v.strip() for v in values]


class MappingRow(BaseModel):
    model_config=ConfigDict(extra='forbid')
    skill_id:int=Field(gt=0)
    outcome_index:int=Field(default=-1,ge=-1)


class CourseSkillWrite(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)
    mappings:list[MappingRow]=Field(max_length=200)


class NeedCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    skill_id:int=Field(gt=0)
    source:Literal['MANUAL','AI_SUGGESTED']='MANUAL'
    analysis_run_id:int|None=Field(default=None,gt=0)
    confirm:bool=False
    dismiss:bool=False


class NeedAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)
    action:Literal['CONFIRM','WITHDRAW','REPLACE']
    replacement_skill_id:int|None=Field(default=None,gt=0)
