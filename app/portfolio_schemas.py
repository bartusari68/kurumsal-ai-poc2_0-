from typing import Literal
from pydantic import BaseModel, Field

class Strict(BaseModel):
    model_config = {'extra':'forbid','str_strip_whitespace':True}

class ItemCreate(Strict):
    skill_id: int = Field(gt=0)
    title: str = Field(min_length=3,max_length=255)
    rationale: str = Field(min_length=3,max_length=3000)
    assignee_id: int | None = Field(default=None,gt=0)

class ItemAction(Strict):
    expected_version: int = Field(ge=1)
    action: Literal['REVIEW','DECIDE','CLOSE']
    decision: Literal['NO_ACTION','MONITOR','CREATE_NEW_LEARNING_NEED','START_COURSE_ENRICHMENT','PLAN_ADDITIONAL_SESSIONS'] | None = None
    note: str = Field(min_length=3,max_length=3000)

class HandoffCreate(Strict):
    expected_version: int = Field(ge=1)
    recipient_id: int = Field(gt=0)
    target_id: int | None = Field(default=None,gt=0)

