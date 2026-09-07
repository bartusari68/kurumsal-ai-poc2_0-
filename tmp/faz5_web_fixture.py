"""Synthetic-only desktop QA with a separate database and no provider access."""
import asyncio
import json
import os
import tempfile
from pathlib import Path

folder = Path(tempfile.mkdtemp(prefix='faz5-browser-', dir=Path(__file__).parent))
os.environ['DATABASE_URL'] = 'sqlite:///' + (folder / 'test.db').as_posix()
os.environ['PDF_DIR'] = str(folder / 'pdfs')
from app import main, portal_auth, services, intake
from app.ai import AIUnavailableError
portal_auth.AUTH_PATH = folder / 'admin-auth.json'
portal_auth.ACCESS_PATH = folder / 'admin-access.txt'
portal_auth.ACCOUNTS_PATH = folder / 'portal-accounts.txt'

async def fake_intake(system, user, **kwargs):
    await asyncio.sleep(.2)
    payload = json.loads(user)
    text = payload['user_data'][-1]['text']
    if 'OFFLINE' in text:
        raise AIUnavailableError('Synthetic outage')
    question = len(payload['user_data']) == 1 and not payload['force_ready']
    return {'status': 'needs_more_info' if question else 'ready',
        'question': 'Excel ile hangi işte güçlük yaşıyorsunuz?' if question else None,
        'question_field': 'clarified_problem' if question else None,
        'question_reason': 'İşinizi anlamak uygun talep kapsamını belirlemeye yardımcı olur.' if question else '',
        'suggestions': [], 'missing_fields': ['clarified_problem'] if question else [], 'confidence': .8,
        'context': {'clarified_problem': '' if question else 'Raporlar elle birleştiriliyor.',
            'desired_outcome': '' if question else 'Raporları otomatik birleştirmek.', 'current_context': '',
            'scope': '', 'urgency_signal': '', 'impact_signal': '', 'suspected_need_type': 'education_possible'}}

async def fake_analysis(db, text):
    raise AIUnavailableError('Synthetic analysis outage')

async def fake_health(*args, **kwargs):
    return {'ai_status': 'error', 'detail': 'Sentetik çevrimdışı servis', 'components': {}}

intake.ai.chat_json = fake_intake
services.compute_analysis = fake_analysis
main.ai_client.healthcheck = fake_health
app = main.app
