import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.identity import (sync_directory, resolve_oidc_identity, oidc_authorization,
                          oidc_state_store, update_organization_unit, backfill_legacy_organizations)
from app.identity_models import (ExternalIdentityLink, IntegrationAuditEvent, SyncRun,
                                  Identity, OrganizationUnit, OrganizationMembership, UserManagerRelation)
from app.communication_models import CommunicationDelivery
import app.communication as communication
import app.identity as identity
from app.main import app
from app.models import PortalUser, UserOrganization
from app.position_models import PositionProfile, UserPosition
from app.portal_auth import Principal, create_user, current_account
from app.config import settings


class IdentityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.factory()
        self.people = {}
        for name, role in (("employee", "EMPLOYEE"), ("analyst", "NEEDS_ANALYST"),
                           ("tech", "TECHNICAL_DESIGN")):
            user = create_user(self.db, name, "ignored", role, name.title())
            self.people[name] = Principal(user.id, name, user.display_name, role)
        self.db.commit()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[current_account] = lambda: self.people["analyst"]
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_dry_run_never_writes_users_or_sync_runs(self):
        before_users = self.db.query(PortalUser).count()
        result = sync_directory(self.db, [{"external_subject_id": "dir-1", "username": "dir.one",
                                           "display_name": "Dizin Bir", "organization": "Org"}],
                                provider="fake", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["summary"]["created"], 1)
        self.assertEqual(self.db.query(PortalUser).count(), before_users)
        self.assertEqual(self.db.query(SyncRun).count(), 0)
        # Explicit apply is the only mutation switch, even if a malformed
        # caller sends dry_run=false.
        forced_dry = sync_directory(self.db, [{"external_subject_id": "dir-2", "username": "dir.two",
                                               "display_name": "Dizin İki"}], provider="fake",
                                    dry_run=False, apply=False)
        self.assertTrue(forced_dry["dry_run"])
        self.assertFalse(forced_dry["applied"])
        self.assertEqual(self.db.query(PortalUser).count(), before_users)

    def test_apply_update_and_safe_deactivation_keep_identity_history(self):
        first = sync_directory(self.db, [{"external_subject_id": "dir-1", "username": "dir.one",
                                          "display_name": "Dizin Bir", "email": "one@example.test", "organization": "Org"}],
                               provider="fake", dry_run=False, apply=True)
        self.assertEqual(first["summary"]["created"], 1)
        user = self.db.scalar(select(PortalUser).where(PortalUser.username == "dir.one"))
        second = sync_directory(self.db, [{"external_subject_id": "dir-1", "username": "dir.one",
                                           "display_name": "Dizin Güncel", "email": "one@example.test"}],
                                provider="fake", dry_run=False, apply=True)
        self.assertEqual(second["summary"]["updated"], 1)
        self.assertEqual(self.db.get(PortalUser, user.id).display_name, "Dizin Güncel")
        third = sync_directory(self.db, [], provider="fake", dry_run=False, apply=True)
        self.assertEqual(third["summary"]["deactivated"], 1)
        self.assertFalse(self.db.get(PortalUser, user.id).active)
        self.assertGreaterEqual(self.db.query(IntegrationAuditEvent).count(), 2)
        self.assertEqual(self.db.query(ExternalIdentityLink).count(), 1)
        self.assertEqual(self.db.query(OrganizationMembership).count(), 1)
        self.assertEqual(self.db.query(OrganizationMembership).filter(OrganizationMembership.is_current.is_(True)).count(), 0)

    def test_duplicate_subject_is_rejected_before_writes(self):
        with self.assertRaises(Exception):
            sync_directory(self.db, [{"external_subject_id": "same", "username": "one", "display_name": "Bir"},
                                      {"external_subject_id": "same", "username": "two", "display_name": "İki"}],
                           provider="fake", dry_run=False, apply=True)
        self.assertEqual(self.db.query(PortalUser).count(), 3)

    def test_external_subject_database_constraint_is_unique(self):
        first = ExternalIdentityLink(user_id=self.people["employee"].user_id, provider="directory",
                                     external_subject_id="unique", username_snapshot="e")
        self.db.add(first)
        self.db.commit()
        second = ExternalIdentityLink(user_id=self.people["analyst"].user_id, provider="directory",
                                      external_subject_id="unique", username_snapshot="a")
        self.db.add(second)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_unknown_group_keeps_safe_employee_role_and_explicit_mapping_can_be_used(self):
        result = sync_directory(self.db, [{"external_subject_id": "dir-1", "username": "safe.user",
                                           "display_name": "Güvenli Kullanıcı", "groups": ["unknown-admin"]}],
                                provider="fake", dry_run=False, apply=True)
        self.assertEqual(result["summary"]["created"], 1)
        user = self.db.scalar(select(PortalUser).where(PortalUser.username == "safe.user"))
        self.assertEqual(user.role, "EMPLOYEE")
        response = self.client.post("/api/integrations/role-mappings", json={
            "provider": "fake", "external_key": "known-analyst", "application_role": "NEEDS_ANALYST"})
        self.assertEqual(response.status_code, 201, response.text)
        sync_directory(self.db, [{"external_subject_id": "dir-1", "username": "safe.user",
                                  "display_name": "Güvenli Kullanıcı", "groups": ["known-analyst"]}],
                       provider="fake", dry_run=False, apply=True)
        self.assertEqual(self.db.get(PortalUser, user.id).role, "NEEDS_ANALYST")

    def test_removed_external_group_downgrades_external_only_account(self):
        self.client.post("/api/integrations/role-mappings", json={
            "provider": "fake", "external_key": "known-admin", "application_role": "NEEDS_ANALYST"})
        sync_directory(self.db, [{"external_subject_id": "dir-role", "username": "role.user",
                                  "display_name": "Role User", "groups": ["known-admin"]}],
                       provider="fake", dry_run=False, apply=True)
        user = self.db.scalar(select(PortalUser).where(PortalUser.username == "role.user"))
        self.assertEqual(user.role, "NEEDS_ANALYST")
        sync_directory(self.db, [{"external_subject_id": "dir-role", "username": "role.user",
                                  "display_name": "Role User", "groups": ["unknown-now"]}],
                       provider="fake", dry_run=False, apply=True)
        self.assertEqual(self.db.get(PortalUser, user.id).role, "EMPLOYEE")

    def test_organization_cycle_is_rejected(self):
        a = self.client.post("/api/integrations/organization/units", json={"name": "A"}).json()
        b = self.client.post("/api/integrations/organization/units", json={"name": "B", "parent_id": a["id"]}).json()
        response = self.client.patch(f"/api/integrations/organization/units/{a['id']}", json={"parent_id": b["id"]})
        self.assertEqual(response.status_code, 422, response.text)

    def test_organization_unit_can_be_moved_back_to_root(self):
        a = self.client.post("/api/integrations/organization/units", json={"name": "Root A"}).json()
        b = self.client.post("/api/integrations/organization/units", json={"name": "Child B", "parent_id": a["id"]}).json()
        response = self.client.patch(f"/api/integrations/organization/units/{b['id']}", json={"parent_id": None})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["parent_id"])

    def test_legacy_organization_metadata_is_backfilled_additively(self):
        manager = self.db.get(PortalUser, self.people["analyst"].user_id)
        employee = self.db.get(PortalUser, self.people["employee"].user_id)
        legacy = UserOrganization(user_id=employee.id, organization="Başkanlık", unit="Ekip",
                                  manager_user_id=manager.id, source="LOCAL")
        self.db.add(legacy)
        self.db.commit()
        self.assertEqual(backfill_legacy_organizations(self.db), 2)
        self.assertEqual(self.db.get(UserOrganization, employee.id).unit, "Ekip")
        self.assertEqual(self.db.query(OrganizationUnit).count(), 2)
        self.assertEqual(self.db.query(UserManagerRelation).count(), 1)
        self.assertIsNotNone(self.db.scalar(select(OrganizationUnit).where(OrganizationUnit.name == "Ekip")))
        # Re-running the migration must not duplicate current snapshots.
        self.assertEqual(backfill_legacy_organizations(self.db), 0)

    def test_unknown_position_stays_pending_until_explicit_mapping(self):
        first = sync_directory(self.db, [{"external_subject_id": "dir-2", "username": "position.user",
                                          "display_name": "Pozisyon Kullanıcısı", "position_key": "JOB-UNKNOWN"}],
                               provider="fake", dry_run=False, apply=True, actor_id=self.people["analyst"].user_id)
        self.assertEqual(first["summary"]["conflicts"][0]["field"], "position")
        self.assertEqual(self.client.get("/api/integrations/position-mappings").json()["items"][0]["status"], "PENDING")

    def test_explicit_position_mapping_assigns_existing_profile_without_creating_one(self):
        profile = PositionProfile(name="Teknik Analist", normalized_name="teknik-analist",
                                  code="TA-01", created_by=self.people["analyst"].user_id)
        self.db.add(profile)
        self.db.commit()
        sync_directory(self.db, [{"external_subject_id": "dir-position", "username": "mapped.user",
                                  "display_name": "Mapped User", "position_key": "JOB-TA"}],
                       provider="fake", dry_run=False, apply=True)
        result = self.client.post("/api/integrations/position-mappings", json={
            "provider": "fake", "external_position_key": "JOB-TA", "position_profile_id": profile.id})
        self.assertEqual(result.status_code, 201, result.text)
        sync_directory(self.db, [{"external_subject_id": "dir-position", "username": "mapped.user",
                                  "display_name": "Mapped User", "position_key": "JOB-TA"}],
                       provider="fake", dry_run=False, apply=True)
        user = self.db.scalar(select(PortalUser).where(PortalUser.username == "mapped.user"))
        self.assertEqual(self.db.get(UserPosition, user.id).profile_id, profile.id)
        self.assertEqual(self.db.query(PositionProfile).count(), 1)

    def test_directory_org_parent_and_manager_are_resolved_without_fake_people(self):
        records = [
            {"external_subject_id": "child", "username": "child.user", "display_name": "Child",
             "organization_external_id": "unit-child", "organization_name": "Child Unit",
             "organization_parent_external_id": "unit-parent", "manager_external_id": "manager"},
            {"external_subject_id": "manager", "username": "manager.user", "display_name": "Manager",
             "organization_external_id": "unit-parent", "organization_name": "Parent Unit"},
        ]
        sync_directory(self.db, records, provider="fake", dry_run=False, apply=True)
        tree = {row["external_id"]: row for row in self.client.get("/api/integrations/organization/tree").json()["items"]}
        self.assertEqual(tree["unit-child"]["parent_id"], tree["unit-parent"]["id"])
        self.assertEqual(self.db.query(PortalUser).count(), 5)

    def test_disabled_oidc_is_not_exposed_and_config_payload_has_no_secrets(self):
        response = self.client.get("/api/auth/oidc/start")
        self.assertEqual(response.status_code, 404)
        payload = self.client.get("/api/integrations").json()
        serialized = str(payload)
        for secret in ("OIDC_CLIENT_SECRET", "SMTP_PASSWORD", "TEAMS_WEBHOOK_URL"):
            self.assertNotIn(secret, serialized)

    def test_configured_oidc_validates_claims_and_resolves_safe_jit_identity(self):
        cfg = replace(settings, oidc_enabled=True, oidc_issuer="https://issuer.example",
                      oidc_client_id="client-id", oidc_redirect_uri="https://portal.example/auth/callback",
                      oidc_jit_enabled=True, oidc_client_secret="do-not-return")
        with patch.object(identity, "settings", cfg):
            authorization = oidc_authorization()
            self.assertIn("client-id", authorization["authorization_url"])
            self.assertNotIn("do-not-return", str(authorization))
            state, nonce = oidc_state_store.create()
            self.assertFalse(oidc_state_store.consume(state, "wrong-nonce"))
            valid_claims = {"iss": "https://issuer.example", "aud": "client-id", "exp": 4102444800,
                            "sub": "oidc-user", "preferred_username": "oidc.user", "name": "OIDC User",
                            "access_token": "must-not-persist"}
            user = resolve_oidc_identity(self.db, subject="oidc-user", claims=valid_claims, jit=True)
            self.assertEqual(user.role, "EMPLOYEE")
            self.assertIsNone(self.db.scalar(select(Identity.id).where(
                Identity.user_id == user.id, Identity.identity_type == "LOCAL")))
            self.assertEqual(self.db.query(ExternalIdentityLink).count(), 1)
            self.assertNotIn("access_token", self.db.scalar(select(ExternalIdentityLink).where(
                ExternalIdentityLink.user_id == user.id)).provider_metadata_json)
            with self.assertRaises(Exception):
                resolve_oidc_identity(self.db, subject="other", claims={"sub": "other"}, jit=True)

    def test_inline_records_cannot_apply_as_real_directory_without_configuration(self):
        with self.assertRaises(Exception):
            sync_directory(self.db, [{"external_subject_id": "inline", "username": "inline.user",
                                      "display_name": "Inline User"}], provider="directory",
                           dry_run=False, apply=True)

    def test_unconfigured_directory_apply_is_rejected_without_a_sync_run(self):
        with self.assertRaises(Exception):
            sync_directory(self.db, None, provider="directory", dry_run=False, apply=True)
        self.assertEqual(self.db.query(SyncRun).count(), 0)

    def test_external_delivery_is_idempotent_and_failure_does_not_raise(self):
        cfg = replace(settings, email_enabled=True, email_from="from@example.test", smtp_host="smtp.example.test")
        with patch.object(communication, "settings", cfg), patch.object(communication, "adapter") as adapter:
            adapter.return_value.enabled.return_value = True
            adapter.return_value.deliver.side_effect = RuntimeError("synthetic")
            self.assertEqual(communication.enqueue_external_deliveries(self.db, event_id=11,
                event_type="REQUEST_INFO", recipient_ids={self.people["employee"].user_id}), 2)
            self.db.commit()
            self.assertEqual(communication.enqueue_external_deliveries(self.db, event_id=11,
                event_type="REQUEST_INFO", recipient_ids={self.people["employee"].user_id}), 0)
            self.db.commit()
            communication.dispatch_deliveries(self.factory)
        row = self.db.scalar(select(CommunicationDelivery))
        self.assertEqual(row.status, "FAILED")
        self.assertEqual(self.db.query(CommunicationDelivery).count(), 2)
