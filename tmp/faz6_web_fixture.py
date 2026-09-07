"""Isolated desktop QA: real auth/workflow, synthetic records, no external AI."""
import os
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
folder=Path(tempfile.mkdtemp(prefix='faz6-browser-',dir=Path(__file__).parent))
os.environ['DATABASE_URL']='sqlite:///'+(folder/'test.db').as_posix()
os.environ['PDF_DIR']=str(folder/'pdfs')
from app import main,portal_auth,services
from app.database import SessionLocal
from app.models import PortalUser,RequestRecord,RequestWorkflow,RequestAssignment
from app.workflow import record_analysis
from sqlalchemy import select
from app.ai import AIUnavailableError
portal_auth.AUTH_PATH=folder/'admin-auth.json';portal_auth.ACCESS_PATH=folder/'admin-access.txt';portal_auth.ACCOUNTS_PATH=folder/'portal-accounts.txt'
base_lifespan=main.lifespan
@asynccontextmanager
async def lifespan(app):
    portal_auth.ensure_admin_credentials()
    with SessionLocal() as db:
        other=portal_auth.create_user(db,'vekil','1234','NEEDS_ANALYST','Sentetik Vekil')
        original=db.scalar(select(PortalUser).where(PortalUser.username=='ihtiyac_admin'))
        employee=db.scalar(select(PortalUser).where(PortalUser.username=='calisan'))
        record=RequestRecord(text='Sentetik operasyon ve vekâlet testi',topic='Sentetik operasyon işi')
        db.add(record);db.flush();record_analysis(db,record,{'request_id':record.id,'classification':{'subcategory_id':'OTHER.REVIEW','risk_level':'NORMAL','topic':'Sentetik operasyon işi'},'coverage':{'status':'YOK','fit_percent':0},'courses':[]},f'user:{employee.id}');db.flush()
        db.add(RequestAssignment(request_id=record.id,responsible_scope='NEEDS_ANALYST',assignee_id=original.id,assigned_by=original.id));db.commit()
    async with base_lifespan(app):yield
async def health(*args,**kwargs):return {'ai_status':'error','detail':'Sentetik çevrimdışı servis','components':{}}
async def analyze(db,text):raise AIUnavailableError('Synthetic outage')
main.ai_client.healthcheck=health;services.compute_analysis=analyze
main.app.router.lifespan_context=lifespan
app=main.app
