"""Synchronize the on-disk PDF corpus with its derived search index.

Single-process POC: one async lock serializes uploads and folder syncs. Source
files are never deleted. Old requests/reviews retain course IDs and evidence.
"""
from __future__ import annotations
from .time_policy import utc_now, as_utc, utc_stamp

import asyncio
import hashlib
import logging
import math
import os
from datetime import datetime
from pathlib import Path

import fitz
import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .ai import AIResponseError, AIUnavailableError, ai_client
from .ai_errors import AIServiceError
from .config import PROJECT_ROOT, settings
from .database import SessionLocal
from .models import Course, CourseChunk, DocumentIndex, LearnedMapping
from .utils import canonicalize, chunk_page_text, json_dumps

sync_lock = asyncio.Lock()
_task: asyncio.Task | None = None
_progress = {"running": False, "file": "", "completed_chunks": 0, "total_chunks": 0, "error": ""}
logger = logging.getLogger(__name__)


def pipeline_version() -> str:
    return f"page-chunks-v2:{getattr(settings, 'chunk_size', 1800)}:{getattr(settings, 'chunk_overlap', 220)}"


class IndexNotReadyError(RuntimeError):
    def __init__(self, report: dict, message: str = "PDF dizini tamamlanamadı. Dosya durumlarını kontrol edip yeniden eşitleyin."):
        self.report = report
        super().__init__(message)


def source_path(value: str | Path) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def disk_files() -> dict[str, Path]:
    root = settings.pdf_dir.resolve()
    if not root.is_dir():
        raise OSError("PDF klasörüne erişilemiyor.")
    found = {}
    def fail(error):
        raise error
    for folder, _, filenames in os.walk(root, followlinks=False, onerror=fail):
        for name in filenames:
            path = Path(folder) / name
            if path.suffix.lower() != ".pdf":
                continue
            resolved = path.resolve()
            # Never index files reached through a link outside the corpus.
            if resolved.is_relative_to(root) and resolved.is_file():
                found[path_key(resolved)] = resolved
    return dict(sorted(found.items()))


def index_status(db: Session) -> dict:
    """Read-only comparison against disk, including files not yet registered."""
    files = disk_files()
    entries = {row.path_key: row for row in db.scalars(select(DocumentIndex)).all()}
    courses = {path_key(source_path(row.pdf_path)): row for row in db.scalars(select(Course)).all() if row.pdf_path}
    counts = dict(db.execute(select(CourseChunk.course_id, func.count()).group_by(CourseChunk.course_id)).all())
    documents = []
    for key in sorted(files.keys() | courses.keys()):
        course, entry, path = courses.get(key), entries.get(key), files.get(key)
        digest, error, status = "", "", "missing"
        if path is not None:
            status = "pending"
            try:
                digest = fingerprint(path)
                if (entry and entry.status == "ready" and entry.content_hash == digest
                        and entry.embedding_provider == ai_client.provider_name
                        and entry.pipeline_version == pipeline_version()
                        and entry.chunk_count > 0 and counts.get(entry.course_id, 0) == entry.chunk_count):
                    status = "ready"
                elif entry and entry.status == "error":
                    status, error = "error", entry.error
            except OSError:
                status, error = "error", "Dosya okunamıyor veya kopyalama henüz tamamlanmadı."
        filename = path.relative_to(settings.pdf_dir.resolve()).as_posix() if path else Path(course.pdf_path).name
        documents.append({
            "file": filename, "course_id": course.id if course else None,
            "code": course.code if course else None, "name": course.name if course else Path(filename).stem,
            "status": status, "error": error, "pages": entry.page_count if entry else 0,
            "chunks": entry.chunk_count if entry and status == "ready" else 0,
            # Internal fields are stripped at the API boundary.
            "_key": key, "_hash": digest, "_path": str(path) if path else course.pdf_path,
        })
    return {
        "directory": str(settings.pdf_dir), "files_on_disk": len(files),
        "ready_count": sum(d["status"] == "ready" for d in documents),
        "pending_count": sum(d["status"] == "pending" for d in documents),
        "error_count": sum(d["status"] == "error" for d in documents),
        "missing_count": sum(d["status"] == "missing" for d in documents),
        "complete": all(d["status"] in ("ready", "missing") for d in documents),
        "documents": documents,
    }


def public_status(report: dict, *, offset: int = 0, limit: int = 20) -> dict:
    # Missing sources are internal history, never a deleted-file catalogue.
    documents = [item for item in report["documents"] if item["status"] != "missing"]
    documents.sort(key=lambda item: (item["status"] == "ready", item["file"].casefold()))
    limit = min(100, max(1, limit))
    offset = min(max(0, offset), max(0, (len(documents) - 1) // limit * limit))
    progress = dict(_progress)
    if not progress["running"] or progress["file"] not in {Path(d["file"]).name for d in documents}:
        progress.update(file="", completed_chunks=0, total_chunks=0)
    return {**{k: v for k, v in report.items() if k not in ("documents", "missing_count")},
            "documents": [{k: v for k, v in item.items() if not k.startswith("_")}
                          for item in documents[offset:offset + limit]],
            "documents_total": len(documents), "offset": offset, "limit": limit, "progress": progress}


def active_course_ids(db: Session) -> set[int]:
    from .publishing import retrieval_allowed
    return {d["course_id"] for d in index_status(db)["documents"] if d["status"] == "ready" and retrieval_allowed(db,d['course_id'],d['_hash'])}


def safe_error(error: Exception) -> str:
    if isinstance(error, AIServiceError):
        return str(error)
    if isinstance(error, AIUnavailableError):
        return "Yapay zekâ bağlantısı kapalı; dosya indekslenemedi."
    if isinstance(error, httpx.HTTPStatusError):
        return f"Vektör servisi isteği tamamlayamadı (HTTP {error.response.status_code}). Yeniden deneyin."
    if isinstance(error, httpx.HTTPError):
        return "Vektör servisine ulaşılamadı veya işlem zaman aşımına uğradı."
    if isinstance(error, (ValueError, AIResponseError)):
        return str(error)
    if isinstance(error, (OSError, RuntimeError)):
        return "PDF okunamadı, şifreli/bozuk olabilir veya işlem sırasında değişmiş olabilir."
    return "Dosya indekslenirken beklenmeyen bir hata oluştu."


async def index_one(db: Session, course: Course, entry: DocumentIndex, path: Path, digest: str) -> None:
    """Build vectors first, then atomically replace derived chunks on success."""
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("Şifreli PDF okunamadı. Şifresiz bir kopya gerekir.")
        page_count = len(doc)
        pending = [(page + 1, idx, text) for page in range(page_count)
                   for idx, text in enumerate(chunk_page_text(doc[page].get_text("text") or "",
                                               max_chars=getattr(settings, "chunk_size", 1800),
                                               overlap=getattr(settings, "chunk_overlap", 220)))]
    if not pending:
        raise ValueError("PDF'de okunabilir metin bulunamadı. Taranmış belge için OCR gerekir.")
    _progress.update(file=path.name, completed_chunks=0, total_chunks=len(pending))
    rows = []
    for start in range(0, len(pending), 24):
        batch = pending[start:start + 24]
        vectors = await ai_client.embed([item[2] for item in batch], is_query=False)
        if len(vectors) != len(batch):
            raise AIResponseError("Vektör sayısı metin parçası sayısıyla uyuşmuyor.")
        for (page, idx, text), vector in zip(batch, vectors):
            if not vector or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector):
                raise AIResponseError("Vektör servisi geçersiz bir sonuç üretti.")
            rows.append(CourseChunk(course_id=course.id, page_number=page, chunk_index=idx,
                                    content=text, embedding_json=json_dumps(vector),
                                    embedding_provider=ai_client.provider_name))
        _progress["completed_chunks"] = len(rows)
    if fingerprint(path) != digest:
        raise ValueError("PDF işlem sırasında değişti. Kopyalama bitince yeniden eşitleyin.")
    db.execute(delete(CourseChunk).where(CourseChunk.course_id == course.id))
    db.add_all(rows)
    entry.content_hash, entry.embedding_provider = digest, ai_client.provider_name
    entry.pipeline_version, entry.status, entry.error = pipeline_version(), "ready", ""
    entry.page_count, entry.chunk_count, entry.indexed_at = page_count, len(rows), utc_now()
    db.commit()


async def _sync_locked(db: Session) -> dict:
    report = index_status(db)
    # Invalidate missing/changed content before the first provider call.
    for item in report["documents"]:
        key = item["_key"]
        course = db.get(Course, item["course_id"]) if item["course_id"] else None
        if item["status"] == "missing":
            # Remove derived source content; historical request evidence/reviews
            # retain their course reference and are not part of the source list.
            db.execute(delete(CourseChunk).where(CourseChunk.course_id == course.id))
            db.execute(delete(LearnedMapping).where(LearnedMapping.course_id == course.id))
            db.execute(delete(DocumentIndex).where(DocumentIndex.path_key == key))
            continue
        if course is None:
            path = Path(item["_path"])
            relative = path.relative_to(settings.pdf_dir.resolve()).as_posix()
            code = "DOC-" + canonicalize(path.stem).upper()[:32] + "-" + hashlib.sha256(relative.encode()).hexdigest()[:12].upper()
            course = Course(code=code, name=path.stem.replace("_", " "), description="Klasörden otomatik alınan PDF", pdf_path=str(path))
            db.add(course)
            db.flush()
            item["course_id"] = course.id
        entry = db.get(DocumentIndex, key)
        if entry is None:
            entry = DocumentIndex(path_key=key, course_id=course.id)
            db.add(entry)
        entry.status = item["status"] if item["status"] in ("ready", "missing") else "pending"
        entry.error = ""
    db.commit()
    for item in report["documents"]:
        if item["status"] in ("ready", "missing"):
            continue
        course = db.get(Course, item["course_id"])
        entry = db.get(DocumentIndex, item["_key"])
        try:
            await index_one(db, course, entry, source_path(course.pdf_path), item["_hash"])
        except Exception as error:
            db.rollback()
            entry = db.get(DocumentIndex, item["_key"])
            entry.status, entry.error = "error", safe_error(error)
            db.commit()
            logger.warning("PDF index failed: %s (%s)", Path(course.pdf_path).name, type(error).__name__)
    db.expire_all()
    return index_status(db)


async def sync_pdf_directory(db: Session) -> dict:
    async with sync_lock:
        _progress.update(running=True, error="", file="", completed_chunks=0, total_chunks=0)
        try:
            db.expire_all()
            return await _sync_locked(db)
        finally:
            _progress["running"] = False


def start_sync() -> dict:
    """Return immediately; an index status endpoint exposes per-batch progress."""
    global _task
    if _task is None or _task.done():
        async def run():
            try:
                with SessionLocal() as db:
                    await sync_pdf_directory(db)
            except Exception as error:
                _progress.update(running=False, error=safe_error(error))
                logger.exception("PDF directory synchronization failed")
        _progress.update(running=True, error="")
        _task = asyncio.create_task(run())
    return dict(_progress)
