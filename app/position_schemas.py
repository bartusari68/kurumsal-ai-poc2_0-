from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class RequirementWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    skill_id: int = Field(gt=0)
    requirement_type: Literal['REQUIRED','RECOMMENDED'] = 'REQUIRED'
    rationale: str = Field(default='', max_length=2000)

class PositionWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=180)
    code: str | None = Field(default=None, max_length=64)
    description: str = Field(default='', max_length=3000)
    organization: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=255)
    status: Literal['ACTIVE','INACTIVE'] = 'ACTIVE'
    expected_version: int | None = Field(default=None, ge=1)
    requirements: list[RequirementWrite] = Field(default_factory=list, max_length=100)

class PositionAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_id: int | None = Field(default=None, gt=0)
    expected_version: int = Field(ge=0)
