"""Opt-in real provider + local PDF test; only authored synthetic data leaves this machine.

Uses a separate database and corpus. Never writes to the application's real records.
Pass --serve to retain this isolated environment for browser validation on port 8011.
"""
import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def verify(folder, resume=False):
    import fitz
    from sqlalchemy import func, select
    from app.database import Base, SessionLocal, engine
    from app.models import RequestRecord, RequestWorkflow, PortalUser
    from app.portal_auth import create_user, Principal
    from app.services import analyze_request
    from app.schemas import DecisionRequest
    from app.learning import record_decision, review_report
    from app.workflow import owned_request, refer_request
    from app.indexing import sync_pdf_directory
    from app.main import app
    from app.utils import json_loads

    Base.metadata.create_all(engine)
    for name, text in ([] if resume else [
        ("Synthetic Excel", "Synthetic training course. Excel pivot tables: create a pivot table from a data table, select rows and columns, calculate sums, group by month, filter and refresh the pivot table. Hands-on exercises create monthly summary reports using pivot tables."),
        ("Synthetic Python", "Synthetic training course. Python fundamentals: variables, loops, dictionaries and file reading. Exercises process text files with Python. This course does not cover Excel pivot tables, engineering or medical topics."),
    ]):
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_textbox(fitz.Rect(40, 40, 550, 770), text, fontsize=12)
            pdf.save(folder / "pdfs" / (name + ".pdf"))
    with SessionLocal() as db:
        principals = {}
        for username, role in [("preview_employee", "EMPLOYEE"), ("preview_analyst", "NEEDS_ANALYST"),
                               ("preview_technical", "TECHNICAL_DESIGN"), ("preview_engineering", "ENGINEERING_DESIGN")]:
            user = db.scalar(select(PortalUser).where(PortalUser.username == username)) if resume else None
            user = user or create_user(db, username, "1234", role, "SENTETİK TEST " + username)
            principals[role] = Principal(user.id, username, user.display_name, role)
        db.commit()
        inventory = await sync_pdf_directory(db)
        assert inventory["complete"], "Synthetic PDF index not ready"
        report = {"synthetic_only": True, "isolated_directory": str(folder), "cases": []}
        cases = [
            ("matching", "Sentetik yazılım testi: Excel'de pivot tablo oluşturup aylık özet rapor hazırlamayı öğrenmek istiyorum."),
            ("partial", "Sentetik yazılım testi: Excel'de pivot tablo oluşturmayı ve sonlu elemanlar yöntemiyle yapısal gerilme analizi yapmayı öğrenmek istiyorum."),
            ("missing", "Sentetik yazılım testi: Seramik sır hazırlama ve seramik fırını pişirme programı konusunda eğitim istiyorum."),
        ]
        for name, text in cases:
            print(json.dumps({"stage": name, "status": "running"}), flush=True)
            existing = db.scalar(select(RequestRecord).where(RequestRecord.text == text)) if resume else None
            result = json_loads(db.get(RequestWorkflow, existing.id).result_json, {}) if existing else await analyze_request(db, text, owner_hash=principals["EMPLOYEE"].token_hash)
            coverage = result["coverage"]
            item = {"case": name, "request_id": result["request_id"], "coverage": coverage["status"],
                    "fit_percent": coverage["fit_percent"], "missing_topics": coverage["missing_topics"]}
            if name == "matching":
                assert coverage["fit_percent"] > 40, item
            elif name == "partial":
                assert coverage["status"] == "KISMEN_VAR" and coverage["missing_topics"], item
            else:
                assert coverage["fit_percent"] <= 40 and coverage["status"] == "YOK", item
            report["cases"].append(item)
            print(json.dumps(item, ensure_ascii=True), flush=True)
        request_id = report["cases"][-1]["request_id"]
        analyst = principals["NEEDS_ANALYST"]
        record, flow = owned_request(db, request_id, analyst.token_hash, True, analyst.role)
        baseline = json_loads(flow.result_json, {}).get("decision_support", {}).get("suggested_department", {}).get("id")
        decided = record_decision(db, record, flow, analyst, DecisionRequest(
            outcome="APPROVED" if baseline == "TECHNICAL_DESIGN" else "MODIFIED", expected_version=flow.version,
            reason="Sentetik doğrulama: ihtiyaç onaylandı ve sorumlu teknik eğitim birimi belirlendi.",
            actual_department="TECHNICAL_DESIGN", training_need_confirmed=True))
        routed = refer_request(db, record, flow, analyst, "TECHNICAL_DESIGN",
                               "Sentetik doğrulama: seramik eğitim ihtiyacı için teknik tasarım planı hazırlanacak.",
                               True, decided["version"])
        technical = principals["TECHNICAL_DESIGN"]
        record, flow = owned_request(db, request_id, technical.token_hash, True, technical.role)
        record_decision(db, record, flow, technical, DecisionRequest(
            outcome="MODIFIED", expected_version=routed["version"],
            reason="Sentetik doğrulama: teknik birim kapsamı incelendi ve hedef seviye bilgisi istendi.",
            actual_department="TECHNICAL_DESIGN", training_need_confirmed=True,
            missing_topics=["Hedef seviye ve uygulama ortamı"]))
        report["review_report"] = review_report(db, analyst)
        report["saved_requests"] = db.scalar(select(func.count(RequestRecord.id)))
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "passed", "saved_requests": report["saved_requests"], "report": str(folder / "report.json")}), flush=True)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--resume", type=Path, help="Reuse only an existing synthetic validation directory under tmp.")
    args = parser.parse_args()
    folder = args.resume.resolve() if args.resume else ROOT / "tmp" / ("e2e-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    if args.resume and (not folder.is_relative_to((ROOT / "tmp").resolve()) or not folder.name.startswith("e2e-") or not (folder / "validation.db").is_file()):
        parser.error("--resume requires an existing synthetic e2e directory under this project's tmp directory")
    (folder / "pdfs").mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = "sqlite:///" + (folder / "validation.db").as_posix()
    os.environ["PDF_DIR"] = str(folder / "pdfs")
    try:
        app = asyncio.run(verify(folder, resume=bool(args.resume)))
        if args.serve:
            import uvicorn
            uvicorn.run(app, host="127.0.0.1", port=8011)
    except Exception as error:
        # Provider errors are already sanitized; never print raw provider responses.
        print(json.dumps({"status": "failed", "type": type(error).__name__,
                          "detail": str(error) if type(error).__name__ in ("AIServiceError", "AIResponseError", "AssertionError", "HTTPException") else "See local validation stage", "folder": str(folder)}, ensure_ascii=True), flush=True)
        raise SystemExit(1)
