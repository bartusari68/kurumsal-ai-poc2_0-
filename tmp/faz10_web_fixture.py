"""Isolated synthetic learning design UI verification; external AI disabled."""
import os
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
folder=Path(tempfile.mkdtemp(prefix='faz10-browser-',dir=Path(__file__).parent))
os.environ['DATABASE_URL']='sqlite:///'+(folder/'test.db').as_posix()
os.environ['PDF_DIR']=str(folder/'pdfs')
from app import main,portal_auth,services
from app.database import SessionLocal
from app.models import PortalUser,RequestRecord,RequestWorkflow,RequestReferral,Course,DocumentIndex
from app.workflow import record_analysis
from sqlalchemy import select
from app.ai import AIUnavailableError
portal_auth.AUTH_PATH=folder/'admin-auth.json';portal_auth.ACCESS_PATH=folder/'admin-access.txt';portal_auth.ACCOUNTS_PATH=folder/'portal-accounts.txt'
base_lifespan=main.lifespan
@asynccontextmanager
async def lifespan(app):
    portal_auth.ensure_admin_credentials()
    with SessionLocal() as db:
        analyst=db.scalar(select(PortalUser).where(PortalUser.username=='ihtiyac_admin'))
        employee=db.scalar(select(PortalUser).where(PortalUser.username=='calisan'))
        course=Course(code='SYNTHETIC',name='Sentetik üretim süreçleri',pdf_path='synthetic.pdf');db.add(course);db.flush()
        db.add(DocumentIndex(path_key='synthetic.pdf',course_id=course.id,content_hash='a'*64))
        db.flush()
        from app.publishing_migration import ensure_legacy
        from app.models import CourseVersion,CourseCatalog
        from app.utils import json_dumps
        version=CourseVersion(course_id=course.id,version_number=1,title=course.name,state='PUBLISHED',legacy=True,outcomes_json=json_dumps([{'id':'1','text':'Üretim adımlarını uygulamak ve sonuçları doğrulamak'}]))
        db.add(version);db.flush();db.add(CourseCatalog(course_id=course.id,current_version_id=version.id,responsible_unit='TECHNICAL_DESIGN'))
        for enrichment in (False,True):
            record=RequestRecord(text='Sentetik üretim işlem adımlarını doğru uygulamak ve sonuçları doğrulamak için eğitim ihtiyacı.',topic='Üretim adımları '+('zenginleştirme' if enrichment else 'yeni eğitim'))
            db.add(record);db.flush();record_analysis(db,record,{'request_id':record.id,
                'classification':{'subcategory_id':'OTHER.REVIEW','risk_level':'NORMAL','topic':record.topic,'requirements':[{'id':'N1','label':'Üretim adımlarını uygulayabilir'}]},
                'coverage':{'status':'KISMEN_VAR' if enrichment else 'YOK','fit_percent':60 if enrichment else 0,'missing_topics':['Sonuç doğrulama uygulaması']},
                'courses':[{'course_id':course.id,'course_name':course.name,'fit':{'percent':60,'requirements':[{'label':'Üretim adımları','status':'FULL'},{'label':'Doğrulama','status':'PARTIAL'}]}}] if enrichment else []},f'user:{employee.id}')
            db.flush();db.get(RequestWorkflow,record.id).status='REFERRED'
            db.add(RequestReferral(request_id=record.id,department='TECHNICAL_DESIGN',analysis_summary='Doğrulanmış sentetik eğitim ihtiyacı',training_need_confirmed=True,active=True,analyst_id=analyst.id))
        db.commit()
    async with base_lifespan(app):yield
async def health(*args,**kwargs):return {'ai_status':'error','detail':'Sentetik çevrimdışı servis','components':{}}
async def analyze(*args,**kwargs):raise AIUnavailableError('Synthetic outage')
main.ai_client.healthcheck=health;services.compute_analysis=analyze
main.app.router.lifespan_context=lifespan
app=main.app
