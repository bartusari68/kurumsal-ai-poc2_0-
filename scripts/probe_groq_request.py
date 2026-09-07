"""Synthetic Groq diagnostic; print only safe limit numbers, never raw errors/keys."""
import asyncio
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.ai import AIClient
from app.ai_errors import AIServiceError
from app.config import PROJECT_ROOT
from app.utils import compact_text

OriginalClient = httpx.AsyncClient


class ObservedClient(OriginalClient):
    async def post(self, *args, **kwargs):
        response = await super().post(*args, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = {}
        message = str(body.get("error", {}).get("message", "")) if isinstance(body.get("error", {}), dict) else ""
        limits = {key.lower(): value for key, value in re.findall(r"\b(Limit|Used|Requested)\s*[: ]\s*([\d,.]+)", message, flags=re.I)}
        units = [unit for unit in ("TPM", "TPD", "RPM", "RPD", "ITPM", "OTPM") if re.search(r"\b" + unit + r"\b", message)]
        print(json.dumps({"http_status": response.status_code, "message_limits": limits, "units": units,
                          "rate_headers": {key: value for key, value in response.headers.items() if key.startswith("x-ratelimit-") or key == "retry-after"},
                          "usage": {key: body.get("usage", {}).get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}}, ensure_ascii=True), flush=True)
        return response


async def main():
    import app.ai
    app.ai.httpx.AsyncClient = ObservedClient
    client = AIClient()
    request = "Sentetik test: Excel pivot tablolar, Power Query ile veri birlestirme ve rapor yenileme egitimi ariyorum."
    try:
        classification = await client.classify_request(request)
        print(json.dumps({"classification_ok": True, "category": classification["category"]}, ensure_ascii=True), flush=True)
        # Only the explicitly synthetic Excel fixture; no catalogue-wide data export.
        with sqlite3.connect((PROJECT_ROOT / "data/app.db").as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("select c.code,c.name,k.page_number,k.content from course_chunks k join courses c on c.id=k.course_id where c.pdf_path like ? order by k.chunk_index limit 6", ("%Excel_Ileri_Seviye_Sentetik_Ders.pdf",)).fetchall()
        evidence = [{"course_code": code, "course_name": name, "page_number": page, "content": compact_text(content, 650), "score": 0.8} for code, name, page, content in rows]
        if evidence:
            result = await client.coverage_analysis(request, classification, evidence)
            print(json.dumps({"coverage_ok": True, "coverage": result["coverage"]}), flush=True)
    except AIServiceError as error:
        print(json.dumps({"error_code": error.payload["error_code"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
