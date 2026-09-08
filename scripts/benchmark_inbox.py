"""Small synthetic SQLite benchmark. Never opens the application's data/app.db."""
import sys, tempfile, time, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session
from app.database import Base
from app.models import PortalUser,Course,CourseVersion,CourseCatalog,RequestRecord,RequestWorkflow,RequestReferral,DevelopmentItem,TrainingSession
from app.portal_auth import Principal
from app.inbox_query import inbox
from app.time_policy import utc_now


def run(size):
    with tempfile.TemporaryDirectory(prefix='inbox-bench-') as folder:
        engine=create_engine('sqlite:///'+str(Path(folder)/'benchmark.db'))
        Base.metadata.create_all(engine)
        with Session(engine,expire_on_commit=False) as db:
            for identifier,role in [(1,'TECHNICAL_DESIGN'),(2,'EMPLOYEE'),(3,'ENGINEERING_DESIGN')]:
                db.add(PortalUser(id=identifier,username=f'user{identifier}',display_name=f'Synthetic {identifier}',role=role,password_salt='0'*32,password_hash='0'*64))
            db.add(Course(id=1,code='BENCH',name='Synthetic benchmark',pdf_path='synthetic.pdf'));db.flush()
            db.add(CourseVersion(id=1,course_id=1,title='Synthetic benchmark',state='PUBLISHED',version_number=1,legacy=True));db.flush()
            db.add(CourseCatalog(course_id=1,current_version_id=1,responsible_unit='TECHNICAL_DESIGN'));db.flush()
            n=size//4;ids=range(1,n+1);now=utc_now()
            db.execute(insert(RequestRecord),[dict(id=i,text='Synthetic request',topic=f'Request {i}') for i in ids])
            db.execute(insert(RequestWorkflow),[dict(request_id=i,status='REFERRED',owner_hash='user:2',result_json='{}') for i in ids])
            db.execute(insert(RequestReferral),[dict(request_id=i,department='TECHNICAL_DESIGN',analysis_summary='Synthetic',training_need_confirmed=True,active=True,analyst_id=1) for i in ids])
            db.execute(insert(DevelopmentItem),[dict(id=i,source_request_id=i,work_type='NEW_COURSE',title='Synthetic development',summary='Synthetic',responsible_unit='TECHNICAL_DESIGN',created_by=1,stage_started_at=now) for i in ids])
            db.execute(insert(CourseVersion),[dict(id=i+1,source_development_id=i,version_number=1,title='Synthetic publication',state='DRAFT',updated_at=now) for i in ids])
            db.execute(insert(TrainingSession),[dict(id=i,course_version_id=1,title='Synthetic session',responsible_unit='TECHNICAL_DESIGN',delivery_mode='ONLINE',created_by=1,updated_at=now) for i in ids])
            db.commit()
            actor=Principal(1,'user1','Synthetic 1','TECHNICAL_DESIGN')
            timings=[]
            for offset in (0,20,size-20):
                start=time.perf_counter();page=inbox(db,actor,offset,20);timings.append(round(1000*(time.perf_counter()-start),2))
                assert page['total']==size and len(page['items'])==20
            for uid,role in ((2,'EMPLOYEE'),(3,'ENGINEERING_DESIGN')):
                assert inbox(db,Principal(uid,f'user{uid}','Synthetic',role),0,20)['total']==0
        engine.dispose()
        return {'mixed_items':size,'page_size':20,'page_offsets':[0,20,size-20],'page_ms':timings,'authorization':'passed','database_pagination':True}

if __name__=='__main__':
    result=[run(n) for n in (1000,5000,10000)]
    target=Path(__file__).resolve().parents[1]/'tmp/faz10-inbox-benchmark.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
