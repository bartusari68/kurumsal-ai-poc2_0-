"""Additive legacy backfill and database-enforced publication immutability."""
from sqlalchemy import DDL, event, select, update
from .models import Course, CourseCatalog, CourseVersion, CourseVersionDocument, PublicationEvent, DocumentIndex, CatalogMigration
from .time_policy import utc_now

IMMUTABLE = ('course_id','version_number','base_version_id','proposed_code','title','description','outcomes_json',
    'outline_json','source_development_id','source_review_id','source_ready_id','source_request_id','source_analysis_id',
    'source_decision_id','legacy','created_by','created_at','published_by','published_at')
UNCHANGED = ' AND '.join('NEW.'+field+' IS OLD.'+field for field in IMMUTABLE)
GUARDS = [
    "CREATE TRIGGER IF NOT EXISTS course_version_immutable_update BEFORE UPDATE ON course_versions "
    "WHEN OLD.state IN ('PUBLISHED','ARCHIVED') AND NOT (OLD.state='PUBLISHED' AND NEW.state='ARCHIVED' "
    "AND NEW.revision=OLD.revision+1 AND "+UNCHANGED+") BEGIN SELECT RAISE(ABORT,'Published version is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS course_version_immutable_delete BEFORE DELETE ON course_versions "
    "WHEN OLD.state IN ('PUBLISHED','ARCHIVED') BEGIN SELECT RAISE(ABORT,'Published version is immutable'); END",
]
for table in ('publication_events','course_version_documents'):
    for operation in ('UPDATE','DELETE'):
        GUARDS.append(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
                      "BEGIN SELECT RAISE(ABORT,'Publication history is append-only'); END")
for operation in ('INSERT','UPDATE'):
    GUARDS.append(f"CREATE TRIGGER IF NOT EXISTS catalog_current_{operation.lower()} BEFORE {operation} ON course_catalog "
        "WHEN NEW.current_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM course_versions "
        "WHERE id=NEW.current_version_id AND course_id=NEW.course_id AND state='PUBLISHED') "
        "BEGIN SELECT RAISE(ABORT,'Current version must be published and belong to course'); END")


def install_guards(bind):
    if bind.dialect.name == 'sqlite':
        with bind.begin() as connection:
            for sql in GUARDS:
                connection.exec_driver_sql(sql)


def _after_create(target, connection, **kw):
    if connection.dialect.name == 'sqlite':
        for sql in GUARDS:
            connection.exec_driver_sql(sql)

from .database import Base
event.listen(Base.metadata, 'after_create', _after_create)


def ensure_legacy(db, course):
    catalog = db.get(CourseCatalog, course.id)
    if catalog:
        return catalog
    db.execute(update(Course).where(Course.id == course.id).values(code=Course.code))
    catalog = db.get(CourseCatalog, course.id, populate_existing=True)
    if catalog:
        return catalog
    version = CourseVersion(course_id=course.id, version_number=1, title=course.name, description=course.description,
        proposed_code=course.code, state='PUBLISHED', legacy=True, created_at=course.created_at)
    db.add(version); db.flush()
    index = db.scalar(select(DocumentIndex).where(DocumentIndex.course_id == course.id))
    if index and index.content_hash:
        db.add(CourseVersionDocument(version_id=version.id, source_path=course.pdf_path, content_hash=index.content_hash))
    catalog = CourseCatalog(course_id=course.id, current_version_id=version.id)
    db.add(catalog)
    db.add(PublicationEvent(version_id=version.id, revision=version.revision, action='LEGACY', actor_name='Katalog geçişi'))
    db.flush()
    return catalog


def backfill(factory):
    with factory() as db:
        from sqlalchemy.dialects.sqlite import insert
        marker = db.execute(insert(CatalogMigration).values(name='initial-course-backfill').on_conflict_do_nothing())
        if not marker.rowcount:
            return
        for course in db.scalars(select(Course).where(~select(CourseCatalog.course_id).where(CourseCatalog.course_id == Course.id).exists())):
            ensure_legacy(db, course)
        db.commit()
