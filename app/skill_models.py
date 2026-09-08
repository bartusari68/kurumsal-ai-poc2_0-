"""Canonical skills and traceable observations, without proficiency scores."""
from datetime import datetime
from sqlalchemy import Integer, String, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index, Boolean, event, DDL, text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .time_policy import UTCDateTime, utc_now


class SkillGroup(Base):
    __tablename__='skill_groups'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    code: Mapped[str]=mapped_column(String(40),unique=True)
    name: Mapped[str]=mapped_column(String(180))
    category_reference: Mapped[str|None]=mapped_column(String(40),nullable=True)
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class Skill(Base):
    __tablename__='skills'
    __table_args__=(CheckConstraint("status IN ('ACTIVE','INACTIVE')"),CheckConstraint('version > 0'))
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    canonical_name: Mapped[str]=mapped_column(String(160))
    normalized_name: Mapped[str]=mapped_column(String(200),unique=True)
    description: Mapped[str]=mapped_column(Text,default='')
    group_id: Mapped[int]=mapped_column(ForeignKey('skill_groups.id'),index=True)
    status: Mapped[str]=mapped_column(String(12),default='ACTIVE',index=True)
    version: Mapped[int]=mapped_column(Integer,default=1)
    created_by: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)
    updated_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class SkillTerm(Base):
    """A shared unique namespace for canonical names AND aliases."""
    __tablename__='skill_terms'
    normalized: Mapped[str]=mapped_column(String(200),primary_key=True)
    skill_id: Mapped[int]=mapped_column(ForeignKey('skills.id'),index=True)
    label: Mapped[str]=mapped_column(String(160))
    created_by: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class CourseSkillMapping(Base):
    __tablename__='course_skill_mappings'
    __table_args__=(UniqueConstraint('course_version_id','skill_id','outcome_index',name='uq_version_skill_outcome'),CheckConstraint('outcome_index >= -1'))
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    course_version_id: Mapped[int]=mapped_column(ForeignKey('course_versions.id'),index=True)
    skill_id: Mapped[int]=mapped_column(ForeignKey('skills.id'),index=True)
    outcome_index: Mapped[int]=mapped_column(Integer,default=-1) # -1 = course-wide relationship
    outcome_text: Mapped[str|None]=mapped_column(Text,nullable=True)
    source: Mapped[str]=mapped_column(String(24),default='MANUAL')
    created_by: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class RequestSkillNeed(Base):
    __tablename__='request_skill_needs'
    __table_args__=(Index('uq_active_request_skill','request_id','skill_id',unique=True,sqlite_where=text('active=1')),
        CheckConstraint("source IN ('AI_SUGGESTED','HUMAN_CONFIRMED','MANUAL')"),
        CheckConstraint("(source='AI_SUGGESTED' AND human_verified=0) OR (source IN ('HUMAN_CONFIRMED','MANUAL') AND human_verified=1)"))
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    request_id: Mapped[int]=mapped_column(ForeignKey('requests.id'),index=True)
    skill_id: Mapped[int]=mapped_column(ForeignKey('skills.id'),index=True)
    source: Mapped[str]=mapped_column(String(24))
    human_verified: Mapped[bool]=mapped_column(Boolean,default=False)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    analysis_run_id: Mapped[int|None]=mapped_column(ForeignKey('analysis_runs.id'),nullable=True)
    provenance_json: Mapped[str]=mapped_column(Text,default='{}')
    version: Mapped[int]=mapped_column(Integer,default=1)
    created_by: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    verified_by: Mapped[int|None]=mapped_column(ForeignKey('portal_users.id'),nullable=True)
    verified_at: Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class SkillEvidence(Base):
    __tablename__='skill_evidence'
    __table_args__=(CheckConstraint("evidence_type IN ('REQUEST_NEED','TRAINING_COMPLETION','SELF_EVALUATION','OUTCOME_EVALUATION','AUTHORIZED_VALIDATION')"),
        Index('ix_skill_evidence_user_skill','user_id','skill_id','observed_at'))
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    dedupe_key: Mapped[str]=mapped_column(String(240),unique=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    skill_id: Mapped[int]=mapped_column(ForeignKey('skills.id'),index=True)
    evidence_type: Mapped[str]=mapped_column(String(32))
    request_need_id: Mapped[int|None]=mapped_column(ForeignKey('request_skill_needs.id'),nullable=True)
    course_version_id: Mapped[int|None]=mapped_column(ForeignKey('course_versions.id'),nullable=True,index=True)
    mapping_id: Mapped[int|None]=mapped_column(ForeignKey('course_skill_mappings.id'),nullable=True)
    enrollment_id: Mapped[int|None]=mapped_column(ForeignKey('training_enrollments.id'),nullable=True,index=True)
    evaluation_id: Mapped[int|None]=mapped_column(ForeignKey('learning_evaluations.id'),nullable=True,index=True)
    signal: Mapped[str|None]=mapped_column(String(40),nullable=True)
    provenance_json: Mapped[str]=mapped_column(Text)
    observed_at: Mapped[datetime]=mapped_column(UTCDateTime)
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class SkillAudit(Base):
    __tablename__='skill_audit'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    skill_id: Mapped[int|None]=mapped_column(ForeignKey('skills.id'),nullable=True)
    course_version_id: Mapped[int|None]=mapped_column(ForeignKey('course_versions.id'),nullable=True)
    request_need_id: Mapped[int|None]=mapped_column(ForeignKey('request_skill_needs.id'),nullable=True)
    actor_id: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    actor_name: Mapped[str]=mapped_column(String(160))
    action: Mapped[str]=mapped_column(String(32))
    details_json: Mapped[str]=mapped_column(Text,default='{}')
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


GUARDS=[
 "CREATE TRIGGER IF NOT EXISTS skill_no_delete BEFORE DELETE ON skills BEGIN SELECT RAISE(ABORT,'Deactivate skills instead of deleting history'); END",
 *[f"CREATE TRIGGER IF NOT EXISTS skill_map_{op.lower()}_draft BEFORE {op} ON course_skill_mappings WHEN (SELECT state FROM course_versions WHERE id={ref}.course_version_id) IS NOT 'DRAFT' BEGIN SELECT RAISE(ABORT,'Published skill mapping is immutable'); END" for op,ref in (('INSERT','NEW'),('UPDATE','OLD'),('DELETE','OLD'))],
 "CREATE TRIGGER IF NOT EXISTS skill_map_update_target BEFORE UPDATE ON course_skill_mappings WHEN NEW.course_version_id<>OLD.course_version_id BEGIN SELECT RAISE(ABORT,'Mapping version cannot change'); END",
 *[f"CREATE TRIGGER IF NOT EXISTS skill_map_outcome_{op.lower()} BEFORE {op} ON course_skill_mappings WHEN (NEW.outcome_index=-1 AND NEW.outcome_text IS NOT NULL) OR (NEW.outcome_index>=0 AND (NEW.outcome_index >= (SELECT json_array_length(outcomes_json) FROM course_versions WHERE id=NEW.course_version_id) OR NEW.outcome_text IS NOT (SELECT json_extract(outcomes_json,'$['||NEW.outcome_index||'].text') FROM course_versions WHERE id=NEW.course_version_id))) BEGIN SELECT RAISE(ABORT,'Outcome must match this version'); END" for op in ('INSERT','UPDATE')],
 *[f"CREATE TRIGGER IF NOT EXISTS skill_map_active_{op.lower()} BEFORE {op} ON course_skill_mappings WHEN (SELECT status FROM skills WHERE id=NEW.skill_id) IS NOT 'ACTIVE' BEGIN SELECT RAISE(ABORT,'Active skill required'); END" for op in ('INSERT','UPDATE')],
 *[f"CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'Skill evidence and audit are append-only'); END" for table in ('skill_evidence','skill_audit') for op in ('UPDATE','DELETE')],
 "CREATE TRIGGER IF NOT EXISTS request_skill_no_delete BEFORE DELETE ON request_skill_needs BEGIN SELECT RAISE(ABORT,'Withdraw request skill needs instead'); END",
 "CREATE TRIGGER IF NOT EXISTS request_skill_context_immutable BEFORE UPDATE ON request_skill_needs WHEN NEW.request_id IS NOT OLD.request_id OR NEW.skill_id IS NOT OLD.skill_id OR NEW.analysis_run_id IS NOT OLD.analysis_run_id OR NEW.provenance_json IS NOT OLD.provenance_json OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT,'Need source context is immutable'); END",
 "CREATE TRIGGER IF NOT EXISTS skill_term_no_reassign BEFORE UPDATE ON skill_terms WHEN NEW.skill_id<>OLD.skill_id BEGIN SELECT RAISE(ABORT,'No automatic skill merge'); END",
]
for statement in GUARDS:event.listen(Base.metadata,'after_create',DDL(statement).execute_if(dialect='sqlite'))


def install(bind,factory):
    if bind.dialect.name=='sqlite':
        with bind.begin() as connection:
            for statement in GUARDS:connection.exec_driver_sql(statement)
    from sqlalchemy.dialects.sqlite import insert
    from .taxonomy import TAXONOMY
    with factory() as db:
        for group in TAXONOMY:
            db.execute(insert(SkillGroup).values(code=group['id'],name=group['name'],category_reference=group['id']).on_conflict_do_nothing(index_elements=['code']))
        db.commit()
