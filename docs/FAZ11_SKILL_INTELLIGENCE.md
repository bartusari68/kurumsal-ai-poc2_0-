# Faz 11 — Skill and competency intelligence

## Domain and migration

Seven additive tables: `skill_groups`, `skills`, `skill_terms`,
`course_skill_mappings`, `request_skill_needs`, `skill_evidence`, `skill_audit`.
Startup creates missing tables and installs idempotent SQLite guards. Eleven skill
groups reuse the existing category identifiers as references; request classification
taxonomy is unchanged. No canonical skills or historical relations are inferred or
backfilled. Existing published courses remain without mappings until a new version
is deliberately mapped. Backup: `backups/faz11-before.db`.

## Vocabulary and verification

The needs analyst stewards the shared vocabulary. Other manager roles can read it
and map their authorized course drafts. Canonical names and aliases share one unique
normalized namespace: NFKC, Turkish i normalization, case folding and whitespace
collapse. Rename retains historical names; collisions return 409. No fuzzy merge,
hard delete or automatic skill creation. Inactivation blocks new relationships.

Existing structured analysis requirement labels provide deterministic candidates
through known names/aliases. These are explicitly unverified AI suggestions, not a
new model prediction. No additional provider request is made. One confirmation
records the original analysis provenance and human verifier. Manual mapping,
withdrawal, replacement and candidate dismissal are audited. A dismissed candidate
stays suppressed for that analysis; a later analysis may propose it again. The
request workflow and its decision form are not advanced or reset by these actions.

## Version and evidence contract

Mappings belong to CourseVersion and optionally an exact outcome index/text snapshot.
Each outcome can support multiple skills. Only authorized DRAFT versions are editable;
published, archived and prepared mappings are protected by DB triggers. Existing
publication revision checks serialize mapping edits with other publication changes.

Evidence is append-only and source-deduplicated in SQLite. Sources are verified request
needs, completed enrollments, participant learning self-evaluations, application
outcomes and authorized application reviewers. General course feedback ratings do not
produce skill evidence. Completion creates one observation per skill and completion
timestamp; learning evidence refers to a mapped outcome; application evidence is once
per skill/evaluation. Generation participates in the source transaction. Retrying does
not duplicate evidence. Withdrawn needs and corrected completion records retain their
historical evidence with a changed-source label.

Completion does not imply proficiency. There are no employee scores, percentages,
levels, rankings or HR decisions. Evaluation outcomes do not close source requests or
automatically create development work. Course coverage does not imply need resolution.

## UI and access

`Yetkinliklerim` and its paginated evidence detail are strictly own-account APIs.
Trace links reuse existing request/course/training permissions. Reviewer response
text remains private; the participant can see the resulting signal in their own
evidence without receiving access to the reviewer's response endpoint.

Managers use `Yetkinlik Kataloğu` with canonical/alias search, coverage, active and
historical demand, evidence counts and outcome signals. Needs analysts see their
existing institution-wide scope; design units only see verified referrals and
training evidence in their authorized unit. Reports expose no employee roster or
individual comments. Faz 10 improvement signals are linked through the exact version
and mapped outcome. Existing source APIs remain responsible for further access checks.

## Verification

Run `.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'`
and `node --test tests/*.test.cjs`. `tests/test_skills.py` covers vocabulary collisions,
scope, human verification, dismissal, append-only evidence, version isolation,
evaluation integration, deduplication and improvement signals. `tests/skills.test.cjs`
covers rendering, escaping, account reset, search races and draft preservation.

Isolated browser fixture and report: `tmp/faz11_web_fixture.py`,
`tmp/faz11-browser.cjs`, `tmp/faz11-browser-report.json`. Real data preservation:
`tmp/faz11-preservation.json`, `tmp/faz11-preservation-report.json`.

Controlled evaluation revisions remain deferred: submitted responses are immutable.
The new domain deliberately does not invent a corporate proficiency framework.

Verified on 2026-09-08: full Python suite 365 passed; after the final three added
cases, all 28 skill tests passed again. Unique coverage is 368 Python + 103 JavaScript
tests = 471 (435 baseline + 36 new). Python compilation, every browser-script syntax
check and whitespace checks passed. The isolated browser flow verified four evidence
types, persistent candidate dismissal, both unsent drafts, and no JavaScript errors.
The real-server smoke check confirmed the employee boundary and both new menu entries.
All 44 pre-existing tables were compared with the backup and are unchanged after
the smoke-test accounts logged out. All eight source PDF hashes match.
