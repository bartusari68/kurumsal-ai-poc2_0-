import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
import test_development as fixtures
from app.models import (Course, CourseCatalog, CourseVersion, CourseVersionDocument, PublicationEvent,
    DevelopmentItem, DevelopmentEvent, RequestWorkflow, RequestEvent, Notification, OperationOutbox, DocumentIndex)
from app import publishing, operations
from app.publishing_migration import backfill
from app.utils import json_loads


class PublishingTests(unittest.TestCase):
    setUp=fixtures.DevelopmentTests.setUp
    tearDown=fixtures.DevelopmentTests.tearDown
    case=fixtures.DevelopmentTests.case
    count=fixtures.DevelopmentTests.count
    delegate=fixtures.DevelopmentTests.delegate
    source=fixtures.DevelopmentTests.source
    create=fixtures.DevelopmentTests.create
    edit_payload=fixtures.DevelopmentTests.edit_payload
    edit=fixtures.DevelopmentTests.edit
    action=fixtures.DevelopmentTests.action

    def ready(self,enrichment=False):
        data,record,flow,payload=self.create(enrichment)
        data=self.finish(data)
        return data,record,flow,payload

    def finish(self,data):
        data=self.edit(data)
        for code in ('START_ANALYSIS','START_DESIGN','SUBMIT_REVIEW','APPROVE'):
            data=self.action(data,code)
        return data

    def draft(self,enrichment=False):
        development,record,flow,request_payload=self.ready(enrichment)
        if enrichment:backfill(self.factory)
        payload={'development_id':development['id'],'expected_development_version':development['version']}
        response=self.client.post('/api/catalog/versions',json=payload)
        self.assertEqual(response.status_code,201,response.text)
        return response.json(),development,record,flow,request_payload

    def metadata(self,row,code='SYNTHETIC-NEW',**extra):
        payload={'expected_version':row['revision'],'code':row['code'] or code,
            'title':'Yayımlanacak sentetik eğitim','description':'Yayın için doğrulanan sentetik katalog açıklaması.',**extra}
        result=self.client.patch(f"/api/catalog/versions/{row['id']}",json=payload)
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def publish_action(self,row,code,expected=200):
        result=self.client.post(f"/api/catalog/versions/{row['id']}/actions",json={'expected_version':row['revision'],'action':code})
        self.assertEqual(result.status_code,expected,result.text)
        return result.json()

    def published(self,enrichment=False):
        row,development,record,flow,payload=self.draft(enrichment)
        row=self.metadata(row);row=self.publish_action(row,'PREPARE');row=self.publish_action(row,'PUBLISH')
        return row,development,record,flow,payload

    def test_new_course_requires_explicit_prepare_and_publish(self):
        row,development,_,_,_=self.draft()
        self.assertIsNone(row['course_id']);self.assertEqual(self.count(Course),0)
        self.publish_action(row,'PUBLISH',422)
        self.publish_action(row,'PREPARE',422)
        row=self.metadata(row);row=self.publish_action(row,'PREPARE')
        self.assertEqual(self.count(Course),0)
        row=self.publish_action(row,'PUBLISH');self.assertEqual(self.count(Course),1)
        self.assertEqual(row['state'],'PUBLISHED');self.assertEqual(row['knowledge']['status'],'no_document')

    def test_duplicate_draft_and_course_are_prevented(self):
        row,development,_,_,_=self.draft()
        payload={'development_id':development['id'],'expected_development_version':development['version']}
        again=self.client.post('/api/catalog/versions',json=payload)
        self.assertEqual(again.json()['id'],row['id']);self.assertEqual(self.count(CourseVersion),1)
        row=self.metadata(row);row=self.publish_action(row,'PREPARE');row=self.publish_action(row,'PUBLISH')
        self.assertEqual(self.client.post('/api/catalog/versions',json=payload).json()['id'],row['id'])
        self.assertEqual(self.count(Course),1)

    def test_not_ready_development_cannot_create_catalog_draft(self):
        data,_,_,_=self.create()
        result=self.client.post('/api/catalog/versions',json={'development_id':data['id'],'expected_development_version':data['version']})
        self.assertEqual(result.status_code,422)

    def test_wrong_unit_analyst_employee_and_guest_cannot_publish(self):
        row,_,_,_,_=self.draft();row=self.metadata(row);row=self.publish_action(row,'PREPARE')
        for who,code in [('engineering',404),('analyst',403),('employee',404)]:
            self.actor=self.people[who];self.publish_action(row,'PUBLISH',code)
        self.actor=None;self.assertEqual(self.client.get('/api/catalog').status_code,401)

    def test_published_catalog_public_but_private_source_chain_hidden(self):
        row,_,_,_,_=self.published();self.actor=self.people['employee']
        result=self.client.get(f"/api/catalog/versions/{row['id']}")
        self.assertEqual(result.status_code,200);self.assertIsNone(result.json()['trace']);self.assertEqual(result.json()['actions'],[])

    def test_enrichment_archives_previous_and_preserves_course_pdf(self):
        row,_,record,flow,_=self.draft(True)
        original=self.db.get(Course,row['course_id']);before=(original.code,original.name,original.description,original.pdf_path)
        self.assertEqual(row['version_number'],2)
        legacy=self.db.get(CourseVersion,row['base_version_id']);hash_before=self.db.get(CourseVersionDocument,legacy.id).content_hash
        row=self.metadata(row);row=self.publish_action(row,'PREPARE');row=self.publish_action(row,'PUBLISH')
        self.db.expire_all();course=self.db.get(Course,row['course_id'])
        self.assertEqual(before,(course.code,course.name,course.description,course.pdf_path))
        self.assertEqual(self.db.get(CourseVersion,legacy.id).state,'ARCHIVED')
        self.assertEqual(self.db.get(CourseVersionDocument,legacy.id).content_hash,hash_before)
        self.assertEqual(self.db.get(CourseCatalog,course.id).current_version_id,row['id'])
        self.assertEqual(self.db.get(RequestWorkflow,record.id).status,'REFERRED')

    def test_published_metadata_and_snapshot_blocked_in_api_and_sql(self):
        row,_,_,_,_=self.published()
        result=self.client.patch(f"/api/catalog/versions/{row['id']}",json={'expected_version':row['revision'],'code':row['code'],'title':'Değişiklik','description':'Yayın sonrası değişiklik'})
        self.assertEqual(result.status_code,422)
        for field,value in [('title','tamper'),('outcomes_json','[]'),('source_ready_id',None)]:
            with self.assertRaises(IntegrityError):self.db.execute(update(CourseVersion).where(CourseVersion.id==row['id']).values(**{field:value}))
            self.db.rollback()
        with self.assertRaises(IntegrityError):self.db.execute(text('DELETE FROM course_versions WHERE id=:id'),{'id':row['id']})
        self.db.rollback()

    def test_database_rejects_two_published_versions(self):
        row,_,_,_,_=self.published()
        with self.assertRaises(IntegrityError):
            self.db.add(CourseVersion(course_id=row['course_id'],version_number=2,title='İkinci aktif',state='PUBLISHED'));self.db.flush()
        self.db.rollback()

    def test_publish_failure_rolls_back_archival(self):
        row,_,_,_,_=self.draft(True);row=self.metadata(row);row=self.publish_action(row,'PREPARE')
        old_id=row['base_version_id'];original=publishing.record_event
        def fail(db,version,actor,code):
            if code=='PUBLISH':raise RuntimeError('synthetic transaction failure')
            return original(db,version,actor,code)
        with patch('app.publishing.record_event',side_effect=fail):
            with self.assertRaises(RuntimeError):self.publish_action(row,'PUBLISH')
        self.db.expire_all();self.assertEqual(self.db.get(CourseVersion,old_id).state,'PUBLISHED')
        self.assertEqual(self.db.get(CourseCatalog,row['course_id']).current_version_id,old_id)

    def test_traceability_references_exact_approved_review(self):
        row,development,record,_,_=self.published()
        trace=row['trace'];self.assertEqual(trace['development_id'],development['id']);self.assertEqual(trace['request_id'],record.id)
        review=self.db.get(DevelopmentEvent,trace['review_id']);ready=self.db.get(DevelopmentEvent,trace['ready_id'])
        self.assertEqual(review.action,'SUBMIT_REVIEW');self.assertEqual(ready.action,'APPROVE')
        self.assertEqual(review.snapshot_json,ready.snapshot_json)
        actual=self.client.get(f"/api/development/{development['id']}").json()
        self.assertEqual(actual['state'],'READY');self.assertEqual(actual['publication']['version']['id'],row['id'])

    def test_missing_and_stale_design_content_cannot_prepare(self):
        row,development,_,_,_=self.draft();row=self.metadata(row)
        self.db.execute(update(CourseVersion).where(CourseVersion.id==row['id']).values(outcomes_json='[]'));self.db.commit()
        self.publish_action(row,'PREPARE',422)

    def test_stale_metadata_and_prepare_conflict(self):
        row,_,_,_,_=self.draft();updated=self.metadata(row)
        response=self.client.patch(f"/api/catalog/versions/{row['id']}",json={'expected_version':row['revision'],'code':'SECOND','title':'Eski taslak','description':'Eski katalog açıklaması'})
        self.assertEqual(response.status_code,409);self.publish_action(row,'PREPARE',409)

    def test_concurrent_metadata_only_one_writer(self):
        row,_,_,_,_=self.draft()
        def write(index):
            return self.client.patch(f"/api/catalog/versions/{row['id']}",json={'expected_version':row['revision'],
                'code':'SYNTHETIC','title':f'Tasarım {index}','description':'Eşzamanlı düzenleme denemesi'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(write,range(2)))
        self.assertEqual(sorted(codes),[200,409])

    def test_legacy_backfill_idempotent_and_never_fabricates_publisher(self):
        for i in range(8):self.db.add(Course(code=f'ORIGINAL-{i}',name=f'Eski ders {i}',pdf_path=f'old-{i}.pdf'))
        self.db.commit();before=[(c.id,c.code,c.pdf_path) for c in self.db.scalars(select(Course))]
        backfill(self.factory);backfill(self.factory)
        self.assertEqual(self.count(CourseVersion),8)
        self.db.expire_all();self.assertEqual(before,[(c.id,c.code,c.pdf_path) for c in self.db.scalars(select(Course))])
        self.assertTrue(all(row.published_at is None and row.published_by is None for row in self.db.scalars(select(CourseVersion))))

    def test_code_conflict_existing_code_cannot_be_overwritten(self):
        row,_,_,_,_=self.draft();self.db.add(Course(code='TAKEN',name='Mevcut ders',pdf_path='taken.pdf'));self.db.commit()
        row=self.metadata(row,code='TAKEN');self.publish_action(row,'PREPARE',422)

    def test_existing_course_code_is_readonly(self):
        row,_,_,_,_=self.draft(True)
        response=self.client.patch(f"/api/catalog/versions/{row['id']}",json={'expected_version':row['revision'],'code':'NEWCODE','title':row['title'],'description':row['description']})
        self.assertEqual(response.status_code,422)

    def test_published_without_version_pdf_is_not_retrieval_source(self):
        row,_,_,_,_=self.published(True)
        self.assertFalse(publishing.retrieval_allowed(self.db,row['course_id'],'a'*64))
        self.assertEqual(self.db.get(CourseVersionDocument,row['base_version_id']).content_hash,'a'*64)

    def test_notifications_reuse_outbox_and_existing_inbox(self):
        row,_,_,_,_=self.draft();row=self.metadata(row);row=self.publish_action(row,'PREPARE')
        operations.dispatch_events(self.factory)
        notification=self.client.get('/api/operations/notifications').json()['items'][0]
        self.assertEqual(notification['publication_id'],row['id'])
        before=self.count(Notification);self.db.execute(update(OperationOutbox).values(processed_at=None));self.db.commit();operations.dispatch_events(self.factory)
        self.assertEqual(before,self.count(Notification))
        self.assertTrue(any(x.get('publication_id')==row['id'] for x in self.client.get('/api/operations/inbox').json()['items']))
        row=self.publish_action(row,'PUBLISH')
        self.assertFalse(any(x.get('publication_id')==row['id'] for x in self.client.get('/api/operations/inbox').json()['items']))

    def test_delegate_only_assigned_publication_and_real_actor(self):
        row,development,_,_,_=self.draft();item=self.db.get(DevelopmentItem,development['id']);item.assignee_id=self.people['tech'].user_id;self.db.commit()
        delegation=self.delegate('tech','tech2');self.actor=self.people['tech2'];headers={'X-Delegation-ID':str(delegation['id'])}
        payload={'expected_version':row['revision'],'code':'DELEGATED','title':row['title'],'description':row['description']}
        self.assertEqual(self.client.patch(f"/api/catalog/versions/{row['id']}",json=payload).status_code,403)
        result=self.client.patch(f"/api/catalog/versions/{row['id']}",json=payload,headers=headers)
        self.assertEqual(result.status_code,200,result.text)
        event=self.db.scalar(select(PublicationEvent).where(PublicationEvent.action=='EDIT'))
        self.assertEqual(event.actor_id,self.people['tech2'].user_id)

    def test_comparison_reports_added_removed_and_changed(self):
        a=CourseVersion(id=1,version_number=1,title='Eski',description='Açıklama',state='PUBLISHED',revision=1,
            outcomes_json='[{"text":"A"},{"text":"B"},{"text":"C"}]',outline_json='[]')
        b=CourseVersion(id=2,version_number=2,title='Yeni',description='Açıklama',state='DRAFT',revision=1,
            outcomes_json='[{"text":"B"},{"text":"C değişti"},{"text":"D"}]',outline_json='[]')
        result=publishing.compare(a,b)
        self.assertEqual(result['outcomes']['removed'],['A']);self.assertEqual(result['outcomes']['added'],['D'])
        self.assertEqual(result['outcomes']['changed'][0]['after'],'C değişti')

    def test_catalog_search_and_course_history(self):
        row,_,_,_,_=self.published(True)
        result=self.client.get('/api/catalog',params={'search':row['title']}).json()
        self.assertEqual(result['total'],1)
        detail=self.client.get(f"/api/catalog/courses/{row['course_id']}").json()
        self.assertEqual(len(detail['versions']),2)
        self.assertEqual(self.client.get(f"/api/catalog/versions/{row['id']}/compare/{row['base_version_id']}").status_code,200)

    def test_backfill_does_not_auto_publish_later_pdf_imports(self):
        backfill(self.factory)
        self.db.add(Course(code='LATER-PDF',name='Sonradan eklenen PDF',pdf_path='later.pdf'));self.db.commit()
        backfill(self.factory)
        self.assertEqual(self.count(CourseVersion),0);self.assertEqual(self.count(CourseCatalog),0)

    def test_two_prepared_enrichments_cannot_overwrite_newer_publication(self):
        first,development,_,_,payload=self.draft(True);first=self.metadata(first);first=self.publish_action(first,'PREPARE')
        second_dev=self.client.post('/api/development',json=payload).json();second_dev=self.finish(second_dev)
        second=self.client.post('/api/catalog/versions',json={'development_id':second_dev['id'],'expected_development_version':second_dev['version']}).json()
        second=self.metadata(second);second=self.publish_action(second,'PREPARE')
        first=self.publish_action(first,'PUBLISH');self.publish_action(second,'PUBLISH',409)
        self.db.expire_all();self.assertEqual(self.db.get(CourseCatalog,first['course_id']).current_version_id,first['id'])

    def test_later_imported_source_becomes_published_only_explicitly(self):
        backfill(self.factory)
        development,_,_,_=self.ready(True)
        row=self.client.post('/api/catalog/versions',json={'development_id':development['id'],'expected_development_version':development['version']}).json()
        self.assertEqual(row['version_number'],1);self.assertIsNone(row['base_version_id'])
        self.assertEqual(self.client.get('/api/catalog').json()['total'],0)
        row=self.metadata(row);row=self.publish_action(row,'PREPARE');row=self.publish_action(row,'PUBLISH')
        self.assertEqual(self.client.get('/api/catalog').json()['total'],1)

    def test_mismatched_current_version_pointer_rejected_by_database(self):
        row,_,_,_,_=self.published()
        self.db.add(Course(code='ANOTHER',name='Başka ders',pdf_path=''));self.db.flush()
        other=self.db.scalar(select(Course).where(Course.code=='ANOTHER'))
        with self.assertRaises(IntegrityError):
            self.db.add(CourseCatalog(course_id=other.id,current_version_id=row['id']));self.db.flush()
        self.db.rollback()

    def test_pdf_link_is_version_specific_and_cannot_overwrite_history(self):
        import hashlib
        from pathlib import Path
        row,_,_,_,_=self.published(True)
        path=Path(self.folder.name)/'reviewed-source.pdf';path.write_bytes(b'synthetic indexed PDF fixture')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        self.db.get(Course,row['course_id']).pdf_path=str(path)
        index=self.db.scalar(select(DocumentIndex).where(DocumentIndex.course_id==row['course_id']))
        index.content_hash=digest;index.status='ready';self.db.commit()
        payload={'expected_version':row['revision'],'content_hash':digest}
        result=self.client.post(f"/api/catalog/versions/{row['id']}/document",json=payload)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['revision'],row['revision'])
        self.assertTrue(publishing.retrieval_allowed(self.db,row['course_id'],digest))
        self.assertFalse(publishing.retrieval_allowed(self.db,row['course_id'],'b'*64))
        self.assertEqual(self.client.post(f"/api/catalog/versions/{row['id']}/document",json=payload).status_code,422)
        self.assertEqual(self.db.get(CourseVersionDocument,row['base_version_id']).content_hash,'a'*64)

    def test_changed_pdf_cannot_be_linked_as_old_indexed_fingerprint(self):
        from pathlib import Path
        row,_,_,_,_=self.published(True)
        path=Path(self.folder.name)/'changed.pdf';path.write_bytes(b'changed content')
        self.db.get(Course,row['course_id']).pdf_path=str(path)
        index=self.db.scalar(select(DocumentIndex).where(DocumentIndex.course_id==row['course_id']))
        index.status='ready';self.db.commit()
        response=self.client.post(f"/api/catalog/versions/{row['id']}/document",json={'expected_version':row['revision'],'content_hash':'a'*64})
        self.assertEqual(response.status_code,422);self.assertIsNone(self.db.get(CourseVersionDocument,row['id']))

    def test_publication_change_during_ai_latency_invalidates_old_pdf_evidence(self):
        from app.models import CourseChunk
        from app.services import assert_sources_current
        from app.indexing import IndexNotReadyError
        row,_,_,_,_=self.published(True)
        item={'chunk':CourseChunk(course_id=row['course_id']), 'source_hash':'a'*64}
        with patch('app.services.fingerprint',return_value='a'*64), patch('app.services.index_status',return_value={}), patch('app.services.public_status',return_value={}):
            with self.assertRaises(IndexNotReadyError):assert_sources_current(self.db,[item])
