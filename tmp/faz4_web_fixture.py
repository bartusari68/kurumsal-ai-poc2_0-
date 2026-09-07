"""Isolated browser fixture: synthetic provider and a separate database/directory."""
import asyncio
import os
import tempfile
from pathlib import Path

folder = Path(tempfile.mkdtemp(prefix="faz4-browser-", dir=Path(__file__).parent))
os.environ["DATABASE_URL"] = "sqlite:///" + (folder / "test.db").as_posix()
os.environ["PDF_DIR"] = str(folder / "pdfs")

from app import main, portal_auth, services
from app.ai import AIUnavailableError

portal_auth.AUTH_PATH = folder / "admin-auth.json"
portal_auth.ACCESS_PATH = folder / "admin-access.txt"
portal_auth.ACCOUNTS_PATH = folder / "portal-accounts.txt"
calls = 0

async def fake_analysis(db, source):
    global calls
    calls += 1
    await asyncio.sleep(.4)
    if calls == 1:
        raise AIUnavailableError("Synthetic provider outage")
    return {"classification": {"category": "Yazılım", "subcategory_id": "SOFTWARE.WEB", "topic": "Sentetik analiz " + str(calls),
        "need_type": "EGITIM", "risk_level": "NORMAL", "canonical_intent": "synthetic-api", "requirements": [{"id": "N1", "label": "API testi"}]},
        "coverage": {"status": "YOK", "fit_percent": 0, "missing_topics": ["API testi"]}, "courses": []}

async def fake_health(*args, **kwargs):
    return {"ai_status": "error", "detail": "Sentetik çevrimdışı servis", "components": {}}

services.compute_analysis = fake_analysis
main.ai_client.healthcheck = fake_health
app = main.app
