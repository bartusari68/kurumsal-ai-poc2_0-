from datetime import date
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, AwareDatetime, model_validator, field_validator


class Strict(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}


class SessionFields(Strict):
    title: str = Field(default='', max_length=255)
    responsible_unit: str = Field(min_length=1, max_length=40)
    coordinator_id: int | None = Field(default=None, gt=0)
    trainer_user_id: int | None = Field(default=None, gt=0)
    external_trainer: str = Field(default='', max_length=255)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    capacity: int | None = Field(default=None, gt=0, strict=True)
    delivery_mode: Literal['IN_PERSON','ONLINE','HYBRID']
    location: str = Field(default='', max_length=500)
    online_url: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def validate_fields(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError('Bitiş başlangıçtan sonra olmalıdır.')
        if self.trainer_user_id and self.external_trainer:
            raise ValueError('İç eğitmen veya dış eğitmen seçeneklerinden birini kullanın.')
        if self.online_url:
            url = urlsplit(self.online_url)
            if url.scheme not in ('https','http') or not url.hostname or url.username or url.password:
                raise ValueError('Geçerli bir http/https bağlantısı girin.')
        if self.delivery_mode == 'IN_PERSON' and self.online_url:
            raise ValueError('Yüz yüze oturumda çevrim içi bağlantı kullanılmaz.')
        if self.delivery_mode == 'ONLINE' and self.location:
            raise ValueError('Çevrim içi oturumda fiziksel konum kullanılmaz.')
        return self


class SessionCreate(SessionFields):
    portfolio_handoff_id: int | None = Field(default=None, gt=0)
    course_version_id: int = Field(gt=0)


class Versioned(Strict):
    expected_version: int = Field(ge=1)


class SessionEdit(SessionFields, Versioned):
    pass


class SessionAction(Versioned):
    action: Literal['SCHEDULE','START','COMPLETE','CANCEL','FINALIZE_ATTENDANCE']
    reason: str = Field(default='', max_length=2000)


class EnrollmentCreate(Versioned):
    user_id: int = Field(gt=0)
    source_request_id: int | None = Field(default=None, gt=0)


class EnrollmentRemove(Versioned):
    enrollment_version: int = Field(ge=1)


class ResultRow(Strict):
    id: int = Field(gt=0)
    version: int = Field(ge=1)
    attendance: Literal['UNKNOWN','ATTENDED','ABSENT','EXCUSED'] | None = None
    completion: Literal['PENDING','COMPLETED','NOT_COMPLETED'] | None = None


class Results(Versioned):
    rows: list[ResultRow] = Field(min_length=1, max_length=500)

    @field_validator('rows')
    @classmethod
    def unique_rows(cls, values):
        if len({row.id for row in values}) != len(values):
            raise ValueError('Aynı katılımcı birden fazla kez gönderilemez.')
        return values
