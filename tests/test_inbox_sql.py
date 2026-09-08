"""Frozen Faz 9 behavior versus the bounded SQL queue, using synthetic records."""
import unittest
from unittest.mock import patch
from datetime import timedelta
from sqlalchemy import event
import test_training as fixtures
from inbox_reference import legacy_inbox
from app import operations
from app.models import AnalysisRun, RequestRecord, RequestWorkflow, UserOrganization, DevelopmentItem, CourseVersion, RequestReferral, RequestAssignment, PortalUser
from app.time_policy import utc_now


class InboxSQLTests(unittest.TestCase):
    setUp = fixtures.TrainingTests.setUp
    tearDown = fixtures.TrainingTests.tearDown
    case = fixtures.TrainingTests.case
    delegate = fixtures.TrainingTests.delegate
    count = fixtures.TrainingTests.count
    catalog = fixtures.TrainingTests.catalog
    make = fixtures.TrainingTests.make

    def freeze_comparison_clock(self):
        # Per-row rendering formerly read the wall clock repeatedly. Compare both
        # implementations at one instant so a second boundary is not a rule change.
        instant=(utc_now()+timedelta(minutes=1)).replace(microsecond=0)
        for module in ('operations','development','publishing','training','workflow_core','inbox_query'):
            clock=patch('app.'+module+'.utc_now',return_value=instant);clock.start();self.addCleanup(clock.stop)
        import inbox_reference
        for scope in (vars(inbox_reference),inbox_reference._development_scope,inbox_reference._publishing_scope,inbox_reference._training_scope):
            clock=patch.dict(scope,{'utc_now':lambda:instant});clock.start();self.addCleanup(clock.stop)

    def seed(self):
        for state in ('IN_REVIEW','REFERRED','ACTION_PLANNED','NEEDS_INFO','RESOLVED'):
            self.case(state)
            self.case(state, 'TECHNICAL_DESIGN', 'tech')
            self.case(state, 'ENGINEERING_DESIGN', 'engineering')
        self.db.add(RequestRecord(text='Legacy synthetic',topic='Legacy'))
        for status in ('PENDING','PROCESSING','FAILED','COMPLETED'):
            for state in ('IN_REVIEW','NEEDS_INFO','ACTION_PLANNED'):
                r,f=self.case(state)
                self.db.add(AnalysisRun(request_id=r.id,sequence=1,status=status,active_request_id=r.id if status in ('PENDING','PROCESSING') else None,trigger='IMPORTED',input_json='{}',result_json='{}'))
        self.db.commit()
        self.delegate('tech','tech2')
        self.delegate('employee','employee2')
        self.make(coordinator_id=self.people['tech'].user_id)
        self.make()
        for state in ('DRAFT','REVIEW','READY','CANCELLED'):
            for assignee in (None,'tech','tech2'):
                record,flow=self.case('REFERRED','TECHNICAL_DESIGN')
                item=DevelopmentItem(source_request_id=record.id,work_type='NEW_COURSE',state=state,
                    title='Frozen development',summary='Synthetic scope',responsible_unit='TECHNICAL_DESIGN',
                    assignee_id=self.people[assignee].user_id if assignee else None,created_by=self.people['tech'].user_id,
                    stage_started_at=utc_now()-timedelta(days=2))
                self.db.add(item);self.db.flush()
                self.db.add(CourseVersion(source_development_id=item.id,version_number=1,title='Frozen publication',
                    state='READY_FOR_PUBLISH' if state=='READY' else 'DRAFT',updated_at=utc_now()-timedelta(days=1)))
        self.db.commit()
        self.freeze_comparison_clock()

    def signature(self, result):
        return [(r.get('kind','request'), r.get('session_id') or r.get('publication_id') or r.get('development_id') or r['request_id'],
                 (r.get('delegation') or {}).get('id'), r['action_required']) for r in result['items']]

    def test_frozen_authorization_and_pagination(self):
        self.seed()
        for actor in self.people.values():
            old=legacy_inbox(self.db,actor,0,100)
            new=operations.inbox(self.db,actor,0,100)
            self.assertEqual(self.signature(new),self.signature(old),actor.username)
            self.assertEqual(new['total'],old['total'])
            for offset in (0,2,7,90):
                page=operations.inbox(self.db,actor,offset,2)
                self.assertEqual(self.signature(page),self.signature(old)[offset:offset+2])

    def test_incompatible_and_expired_delegation(self):
        self.seed()
        self.db.add(UserOrganization(user_id=self.people['tech2'].user_id,unit='Different'))
        self.db.commit()
        for actor in self.people.values():
            self.assertEqual(self.signature(operations.inbox(self.db,actor,0,100)),self.signature(legacy_inbox(self.db,actor,0,100)))

    def test_database_pagination_and_bounded_hydration(self):
        self.seed()
        statements=[]
        def capture(conn,cursor,statement,parameters,context,many): statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try: operations.inbox(self.db,self.people['analyst'],2,2)
        finally: event.remove(self.engine,'before_cursor_execute',capture)
        self.assertTrue(any('UNION ALL' in q and 'LIMIT' in q and 'OFFSET' in q for q in statements))

    def test_stale_assignment_and_revoked_referral(self):
        self.seed()
        self.db.query(RequestAssignment).filter(RequestAssignment.assignee_id==self.people['tech'].user_id).update({'responsible_scope':'NEEDS_ANALYST'})
        self.db.query(RequestReferral).filter(RequestReferral.department=='ENGINEERING_DESIGN').update({'active':False})
        self.db.commit()
        for actor in self.people.values():
            self.assertEqual(self.signature(operations.inbox(self.db,actor,0,100)),self.signature(legacy_inbox(self.db,actor,0,100)),actor.username)

    def test_unknown_stage_start_sorts_as_zero_and_critical_owner_has_no_close_action(self):
        r,f=self.case('ACTION_PLANNED');f.result_json='{"classification":{"risk_level":"KRITIK"}}'
        r2,f2=self.case();f2.status='REFERRED'  # Legacy status without a transition event.
        self.db.commit()
        self.freeze_comparison_clock()
        for actor in self.people.values():
            self.assertEqual(self.signature(operations.inbox(self.db,actor,0,100)),self.signature(legacy_inbox(self.db,actor,0,100)))
