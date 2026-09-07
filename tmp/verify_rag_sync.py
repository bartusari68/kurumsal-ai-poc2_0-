import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models import Course
from app.services import retrieve


async def run():
    with SessionLocal() as db:
        results = await retrieve(db, "C++ concurrency atomics memory model lock-free paralel programlama", "")
        print(json.dumps([
            {"file": Path(db.get(Course, row["chunk"].course_id).pdf_path).name,
             "page": row["chunk"].page_number, "score": round(row["score"], 4)}
            for row in results
        ], ensure_ascii=False))


asyncio.run(run())
