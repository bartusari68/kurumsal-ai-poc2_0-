import unittest

import test_positions as position_fixtures
from app.models import Course, CourseCatalog, CourseVersion, TrainingSession, Enrollment
from app.time_policy import utc_now
from datetime import timedelta


class GovernanceAuthorizationTests(position_fixtures.PositionFixture, unittest.TestCase):
    """The governance surface must keep employee and manager payloads apart."""

    def test_employee_sees_only_personal_requirement_view(self):
        self.actor = self.people['employee']
        self.assertEqual(self.client.get('/api/governance').status_code, 403)
        response = self.client.get('/api/governance/requirements/mine')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['items'], [])

    def test_needs_analyst_can_open_governance_dashboard(self):
        self.actor = self.people['analyst']
        response = self.client.get('/api/governance')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['counts']['review_due'], 0)

    def test_other_design_manager_cannot_mutate_governance(self):
        self.actor = self.people['tech']
        response = self.client.patch('/api/governance/courses/1', json={'owner_unit': 'TECHNICAL_DESIGN'})
        self.assertEqual(response.status_code, 403)

    def test_review_retire_and_restore_keep_course_history(self):
        self.actor = self.people['analyst']
        course = Course(code='GOV-1', name='Yönetişim dersi', description='Test', pdf_path='')
        self.db.add(course)
        self.db.flush()
        version = CourseVersion(course_id=course.id, version_number=1, proposed_code='GOV-1',
                                title='Yönetişim dersi', description='Test', state='PUBLISHED')
        self.db.add(version)
        self.db.flush()
        self.db.add(CourseCatalog(course_id=course.id, current_version_id=version.id))
        self.db.commit()

        started = self.client.post(f'/api/governance/courses/{course.id}/reviews',
                                   json={'reason': 'Periyodik kontrol'})
        self.assertEqual(started.status_code, 201, started.text)
        review_id = started.json()['id']
        self.assertEqual(started.json()['snapshot']['current_version_id'], version.id)
        decided = self.client.post(f'/api/governance/reviews/{review_id}/decision',
                                   json={'decision': 'KEEP_CURRENT', 'reason': 'Mevcut içerik kurum ihtiyacını karşılıyor.'})
        self.assertEqual(decided.status_code, 200, decided.text)
        retired = self.client.post(f'/api/governance/courses/{course.id}/retire',
                                   json={'reason': 'İçerik yaşam döngüsü tamamlandı.'})
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json()['lifecycle_state'], 'RETIRED')
        restored = self.client.post(f'/api/governance/courses/{course.id}/restore',
                                    json={'reason': 'Güncel kullanım planı yeniden onaylandı.'})
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()['lifecycle_state'], 'ACTIVE')
        self.assertGreaterEqual(len(restored.json()['history']), 3)

    def test_policy_creates_position_scoped_requirement_without_enrollment(self):
        skill = self.skill()
        profile = self.profile(skill)
        self.assign(profile)
        course = Course(code='GOV-2', name='Zorunlu eğitim', description='Test', pdf_path='')
        self.db.add(course)
        self.db.flush()
        version = CourseVersion(course_id=course.id, version_number=1, proposed_code='GOV-2',
                                title='Zorunlu eğitim', description='Test', state='PUBLISHED')
        self.db.add(version)
        self.db.flush()
        self.db.add(CourseCatalog(course_id=course.id, current_version_id=version.id))
        self.db.commit()
        self.actor = self.people['analyst']
        response = self.client.post('/api/governance/policies', json={
            'policy_key': 'PROFILE-COURSE-2', 'position_profile_id': profile['id'],
            'course_id': course.id, 'rationale': 'Yeni pozisyon zorunluluğu'})
        self.assertEqual(response.status_code, 201, response.text)
        self.actor = self.people['employee']
        mine = self.client.get('/api/governance/requirements/mine')
        self.assertEqual(mine.status_code, 200, mine.text)
        self.assertEqual(len(mine.json()['items']), 1)
        self.assertEqual(mine.json()['items'][0]['status'], 'PENDING')

    def test_requirement_fulfills_only_completed_non_cancelled_matching_session(self):
        skill = self.skill()
        profile = self.profile(skill)
        self.assign(profile)
        course = Course(code='GOV-3', name='Tamamlama eğitimi', description='Test', pdf_path='')
        self.db.add(course); self.db.flush()
        version = CourseVersion(course_id=course.id, version_number=1, proposed_code='GOV-3',
                                title='Tamamlama eğitimi', description='Test', state='PUBLISHED')
        self.db.add(version); self.db.flush()
        self.db.add(CourseCatalog(course_id=course.id, current_version_id=version.id)); self.db.commit()
        self.actor = self.people['analyst']
        policy_response = self.client.post('/api/governance/policies', json={
            'policy_key': 'PROFILE-COURSE-3', 'position_profile_id': profile['id'],
            'course_id': course.id, 'rationale': 'Pozisyon için tamamlanması gereken eğitim'})
        self.assertEqual(policy_response.status_code, 201, policy_response.text)
        self.actor = self.people['employee']
        self.assertEqual(self.client.get('/api/governance/requirements/mine').json()['items'][0]['status'], 'PENDING')
        now = utc_now()
        session = TrainingSession(course_version_id=version.id, title='Tamamlanan oturum',
                                  responsible_unit='TECHNICAL_DESIGN', delivery_mode='ONLINE', status='COMPLETED',
                                  start_at=now - timedelta(days=2), end_at=now - timedelta(days=1), created_by=self.people['analyst'].user_id)
        self.db.add(session); self.db.flush()
        self.db.add(Enrollment(session_id=session.id, user_id=self.people['employee'].user_id,
                               status='ENROLLED', completion='COMPLETED', completed_at=now - timedelta(days=1)))
        self.db.commit()
        self.assertEqual(self.client.get('/api/governance/requirements/mine').json()['items'][0]['status'], 'FULFILLED')
        session.status = 'CANCELLED'; self.db.commit()
        self.assertEqual(self.client.get('/api/governance/requirements/mine').json()['items'][0]['status'], 'PENDING')
