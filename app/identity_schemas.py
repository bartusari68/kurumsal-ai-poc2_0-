"""Small, strict request schemas for integration administration."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class DirectoryRecordInput(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    external_subject_id: str | None = Field(default=None, max_length=255)
    external_id: str | None = Field(default=None, max_length=255)
    employee_id: str | None = Field(default=None, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    email: str = Field(default="", max_length=320)
    active: bool = True
    organization: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=255)
    organization_external_id: str | None = Field(default=None, max_length=255)
    organization_parent_external_id: str | None = Field(default=None, max_length=255)
    organization_name: str | None = Field(default=None, max_length=255)
    manager_external_id: str | None = Field(default=None, max_length=255)
    position_key: str | None = Field(default=None, max_length=255)
    groups: list[str] = Field(default_factory=list, max_length=40)
    metadata: dict = Field(default_factory=dict)

    @field_validator("external_subject_id", "external_id", "employee_id", mode="before")
    @classmethod
    def clean_optional(cls, value):
        return str(value).strip() if value is not None and str(value).strip() else None


class DirectorySyncRequest(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    provider: str = Field(default="fake", min_length=1, max_length=80)
    records: list[DirectoryRecordInput] | None = Field(default=None, max_length=5000)
    dry_run: bool = True
    apply: bool = False


class OrganizationUnitCreate(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = Field(default=None, max_length=255)
    parent_id: int | None = Field(default=None, gt=0)
    source: str = Field(default="LOCAL", max_length=40)


class OrganizationUnitUpdate(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: int | None = Field(default=None, gt=0)
    status: str | None = Field(default=None, max_length=16)


class RoleMappingRequest(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    provider: str = Field(min_length=1, max_length=80)
    external_key: str = Field(min_length=1, max_length=255)
    application_role: str = Field(min_length=1, max_length=40)
    enabled: bool = True


class PositionMappingRequest(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    provider: str = Field(min_length=1, max_length=80)
    external_position_key: str = Field(min_length=1, max_length=255)
    position_profile_id: int | None = Field(default=None, gt=0)


class ConflictResolutionRequest(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    resolution: str = Field(min_length=3, max_length=32)


class OIDCSimulationRequest(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    subject: str = Field(min_length=1, max_length=255)
    claims: dict = Field(default_factory=dict)
    provider: str | None = Field(default=None, max_length=80)


class NotificationPreferenceRequest(BaseModel):
    model_config = {"extra": "forbid"}

    in_app: bool | None = None
    email: bool | None = None
    teams: bool | None = None
