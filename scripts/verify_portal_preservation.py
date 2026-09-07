"""Verify original records and source PDFs against the pre-portal backup, read-only."""
import hashlib
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup', default='backups/20260904-portal-workflow-app.db')
    args = parser.parse_args()
    before_path = ROOT / args.backup
    current_path = ROOT / "data/app.db"
    with sqlite3.connect(before_path.as_uri() + "?mode=ro", uri=True) as before, sqlite3.connect(current_path.as_uri() + "?mode=ro", uri=True) as current:
        counts = {}
        for table, key in (("requests", "id"), ("request_matches", "id"), ("human_reviews", "id"),
                           ("learned_mappings", "id"), ("courses", "id"), ("course_chunks", "id"), ("document_index", "path_key"),
                           ("request_workflows", "request_id"), ("request_events", "id"),
                           ("request_decisions", "id"), ("request_referrals", "request_id"), ("request_event_identities", "event_id"),
                           ("portal_users", "id"), ("user_organizations", "user_id"),
                           ("request_assignments", "request_id"), ("request_solution_plans", "request_id"),
                           ("request_event_actions", "event_id"), ("analysis_runs", "id"),
                           ("request_submissions", "id"), ("decision_analysis_links", "decision_id"),
                           ("notifications", "id"), ("operation_outbox", "event_id"),
                           ("delegations", "id"), ("delegation_audit", "id"), ("escalations", "id"),
                           ("development_items", "id"), ("development_outcomes", "id"), ("development_modules", "id"),
                           ("development_topics", "id"), ("development_events", "id"),
                           ("course_catalog", "course_id"), ("course_versions", "id"),
                           ("course_version_documents", "version_id"), ("publication_events", "id"), ("catalog_migrations", "name")):
            columns = [row[1] for row in before.execute(f"PRAGMA table_info({table})")]
            if not columns:
                continue
            key_index = columns.index(key)
            original = before.execute(f"SELECT * FROM {table}").fetchall()
            for row in original:
                retained = current.execute(f"SELECT * FROM {table} WHERE {key} = ?", (row[key_index],)).fetchone()
                assert retained == row, f"Original record changed: {table}"
            counts[table] = len(original)
        pdfs = 0
        for path, expected in current.execute("SELECT c.pdf_path, d.content_hash FROM courses c JOIN document_index d ON d.course_id = c.id WHERE d.status = 'ready'"):
            source = Path(path)
            if not source.is_absolute():
                source = ROOT / source
            with source.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            assert digest == expected, "Source PDF differs from indexed original"
            pdfs += 1
        print(json.dumps({"original_rows_unchanged": counts, "source_pdfs_verified": pdfs}, ensure_ascii=True))


if __name__ == "__main__":
    main()
