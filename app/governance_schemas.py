from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, AwareDatetime, ConfigDict


class GovernanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int | None = Field(default=None, ge=1)
    owner_unit: str | None = Field(default=None, max_length=120)
    owner_user_id: int | None = Field(default=None, gt=0)
    review_enabled: bool | None = None
    review_interval_days: int | None = Field(default=None, gt=0)
    review_scope: str | None = Field(default=None, max_length=500)
    next_review_at: AwareDatetime | None = None
    rationale: str | None = Field(default=None, max_length=3000)


class ReviewStart(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(default="", max_length=3000)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Literal["KEEP_CURRENT", "UPDATE_REQUIRED", "RETIREMENT_REVIEW"]
    reason: str = Field(min_length=10, max_length=3000)


class ReviewHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=10, max_length=3000)


class RetirementAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=10, max_length=3000)
    acknowledge_warnings: bool = False


class RestoreAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=10, max_length=3000)


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    policy_key: str | None = Field(default=None, max_length=120)
    position_profile_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    course_version_id: int | None = Field(default=None, gt=0)
    organization: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=255)
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None
    recurrence_days: int | None = Field(default=None, gt=0)
    version_semantics: Literal["ANY_CURRENT_VERSION", "SPECIFIC_VERSION"] = "ANY_CURRENT_VERSION"
    rationale: str = Field(default="", max_length=3000)


class PolicyRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    rationale: str | None = Field(default=None, max_length=3000)
    organization: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=255)
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None
    recurrence_days: int | None = Field(default=None, gt=0)
    version_semantics: Literal["ANY_CURRENT_VERSION", "SPECIFIC_VERSION"] | None = None
    course_version_id: int | None = Field(default=None, gt=0)


class PolicyInactivate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=10, max_length=3000)


class RequirementWaive(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=10, max_length=3000)
