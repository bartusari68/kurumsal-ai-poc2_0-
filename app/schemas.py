from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, AwareDatetime
from typing import Literal
from datetime import date


class AnalyzeRequest(BaseModel):
    position_requirement_id: int | None = Field(default=None, gt=0)
    intake_token: str | None = Field(default=None, max_length=120000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=80)
    text: str = Field(min_length=3, max_length=5000)

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Talep en az 3 anlamlı karakter içermelidir.")
        return value


class ReviewRequest(BaseModel):
    request_id: int
    approved: bool
    correct_course_id: int | None = None
    comment: str = Field(default="", max_length=3000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=5000)
    request_id: int | None = None
    course_id: int | None = None


class IntakeRequest(BaseModel):
    message: str = Field(default='', max_length=5000)
    token: str | None = Field(default=None, max_length=120000)
    edited_draft: str | None = Field(default=None, max_length=5000)
    finish: bool = False


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class StatusChange(BaseModel):
    status: Literal["IN_REVIEW", "ACTION_PLANNED", "NEEDS_INFO", "RESOLVED"]
    note: str = Field(min_length=3, max_length=1500)
    expected_version: int = Field(ge=0)


class ReferralRequest(BaseModel):
    department: Literal["TECHNICAL_DESIGN", "ENGINEERING_DESIGN"]
    training_need_confirmed: bool
    analysis_summary: str = Field(min_length=10, max_length=3000)
    expected_version: int = Field(ge=0)


class DecisionRequest(BaseModel):
    outcome: Literal["APPROVED", "MODIFIED", "REJECTED"]
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=10, max_length=3000)
    actual_subcategory_id: str | None = Field(default=None, max_length=80)
    actual_department: Literal["TECHNICAL_DESIGN", "ENGINEERING_DESIGN"] | None = None
    actual_course_id: int | None = Field(default=None, gt=0)
    # Approving the recommendation is sufficient intent; old explicit clients work.
    training_need_confirmed: bool | None = None
    missing_topics: list[str] | None = Field(default=None, max_length=20)
    excess_topics: list[str] | None = Field(default=None, max_length=20)


class DecisionAdvanceRequest(DecisionRequest):
    # Operational destination is distinct from correcting the AI judgement.
    routing_department: Literal["TECHNICAL_DESIGN", "ENGINEERING_DESIGN"] | None = None


class WorkflowActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    expected_version: int = Field(ge=0)
    note: str = Field(default="", max_length=3000)
    summary: str | None = Field(default=None, min_length=10, max_length=3000)
    responsible_unit: str | None = Field(default=None, max_length=40)
    assignee_id: int | None = Field(default=None, gt=0)
    target_date: date | None = None


class AnalysisRetryRequest(BaseModel):
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=80)


class DelegationRequest(BaseModel):
    delegate_id: int = Field(gt=0)
    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: str = Field(default='', max_length=600)


class DevelopmentBase(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}


class DevelopmentCreate(DevelopmentBase):
    source_request_id: int = Field(gt=0)
    expected_request_version: int = Field(ge=0)
    work_type: Literal['NEW_COURSE', 'COURSE_ENRICHMENT']
    source_course_id: int | None = Field(default=None, gt=0)


class DevelopmentBrief(DevelopmentBase):
    target_output: str = Field(default='', max_length=3000)
    missing_topics: list[str] = Field(default_factory=list, max_length=40)
    change_notes: str = Field(default='', max_length=3000)
    excess_notes: str = Field(default='', max_length=3000)

    @field_validator('missing_topics')
    @classmethod
    def valid_topics(cls, values):
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError('Başlıklar boş olamaz ve 500 karakteri aşamaz.')
        return [value.strip() for value in values]


class DevelopmentOutcomeInput(DevelopmentBase):
    id: int | None = Field(default=None, gt=0)
    text: str = Field(min_length=3, max_length=1000)


class DevelopmentTopicInput(DevelopmentBase):
    id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(default='', max_length=2000)


class DevelopmentModuleInput(DevelopmentTopicInput):
    topics: list[DevelopmentTopicInput] = Field(default_factory=list, max_length=40)


class DevelopmentEdit(DevelopmentBase):
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=255)
    summary: str = Field(min_length=10, max_length=5000)
    brief: DevelopmentBrief
    outcomes: list[DevelopmentOutcomeInput] = Field(default_factory=list, max_length=60)
    modules: list[DevelopmentModuleInput] = Field(default_factory=list, max_length=30)


class DevelopmentAction(DevelopmentBase):
    expected_version: int = Field(ge=1)
    action: str = Field(min_length=2, max_length=32)
    note: str = Field(default='', max_length=3000)
    assignee_id: int | None = Field(default=None, gt=0)
    target_date: date | None = None


class PublicationCreate(DevelopmentBase):
    development_id: int = Field(gt=0)
    expected_development_version: int = Field(ge=1)


class PublicationEdit(DevelopmentBase):
    expected_version: int = Field(ge=1)
    code: str = Field(default='', max_length=64)
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=5000)


class PublicationAction(DevelopmentBase):
    expected_version: int = Field(ge=1)
    action: Literal['PREPARE', 'RETURN_DRAFT', 'PUBLISH']


class PublicationDocument(DevelopmentBase):
    expected_version: int = Field(ge=1)
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
