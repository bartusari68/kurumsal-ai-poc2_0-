# Faz 12 — Position requirements and evidence-based development signals

## Domain

Six additive tables: `position_profiles`, `position_revisions`,
`position_requirements`, `user_positions`, `position_audit`,
`request_position_sources`. Startup creates the schema and idempotent SQLite guards.
No profile, requirement or user association is seeded. Authentication roles and
the existing optional organization metadata are unchanged.

Profiles store a name, optional code/organization/unit, description, status and
optimistic version. Each edit creates an immutable sealed revision with its exact
requirements and skill-name snapshots. Requirements are REQUIRED or RECOMMENDED,
with a rationale and source actor/time. There is no invented proficiency framework.
Duplicate skills and inactive new requirements are rejected; unchanged historical
requirements can be retained when a skill has subsequently become inactive.

UserPosition is optional and separately versioned. Assignment, reassignment and
unassignment are audited and do not update auth roles or skill evidence. Inactive
profiles cannot receive new assignments. Existing holders retain the informative
view of the profile's latest requirements.

## Gap semantics

The own-account API returns the exact requirement version and calculation time.
Each skill independently reports NO_EVIDENCE, EVIDENCE_PRESENT,
DEVELOPMENT_EVIDENCE or OUTCOME_EVIDENCE. Open needs and partial/unresolved outcomes
are separate development signals, not precedence-based judgments about the user.
Historical records are counted and remain accessible; current-source evidence
types are distinguished from withdrawn needs and corrected completions.

Explanations use actual source types/counts, open requests and observation dates.
The UI links to the existing own-skill evidence detail for full source traces.
Participant and authorized-reviewer outcomes remain distinct. There are no
scores, ranks, expiry assumptions, mandatory training decisions or HR conclusions.

## Request shortcut

The user's role view lists only published CourseVersions mapped to the skill.
Draft and archived versions are excluded. An explicit shortcut fills the existing
request form and preserves its unsent text. It makes no request-creation call.
The user can edit, use the existing intake interaction, remove the source link or
explicitly submit. Busy form/intake/PDF operations are not interrupted.

The existing `/api/requests/analyze` accepts an optional `position_requirement_id`.
Final submission validates actual ownership/current profile version, then creates
the source relation and normal durable analysis run in one transaction. The
immutable relation preserves profile ID, version, requirement ID and captured
context. Retry keys cannot change this source. Later profile edits/assignment
changes do not rewrite old requests or become dependencies of request processing.

## Access and reporting

Central permissions live in `position_policy.py`: the existing NEEDS_ANALYST is
the temporary position steward; no HR role is fabricated. Users can read only
their own position view. The personal menu appears only when a position is assigned.
The management user list contains identity/association metadata for assignment,
never individual evidence or a comparison score.

Organizational evidence aggregates use a five-person disclosure threshold and
complementary suppression of small cells. Multiple needs from one person cannot
satisfy the privacy threshold. This is a disclosure control, not a corporate skill
standard. Small groups return null counts instead of revealing individual results.

The planning view reuses Faz 11 observed demand and catalog coverage, and adds
counts of active profiles that currently require each skill. Planned and observed
demand are separate. A deterministic signal identifies planned + observed demand
without published coverage. It never starts course development automatically.

## Verification and deployment

Run `.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'`
and `node --test tests/*.test.cjs`. Focused cases live in `tests/test_positions.py`
and `tests/positions.test.cjs`. Synthetic browser verification:
`tmp/faz12-browser.cjs` and `tmp/faz12-browser-report.json`.
Before/after preservation: `backups/faz12-before.db`,
`tmp/faz12-preservation.json`, `tmp/faz12-preservation-report.json`.

Optional evaluation revisions and stored historical gap snapshots remain deferred.
Submitted evaluations and evidence remain immutable. Future phase-end GitHub
publishing is documented in the root `AGENTS.md`; this phase also synchronizes
the accumulated Faz 9–11 changes.

Verified 2026-09-08: 391 Python tests and 111 JavaScript tests passed (502 total,
including the 471 baseline cases and 31 additions). Compilation and JavaScript
syntax checks passed. The synthetic browser flow verified profile creation,
assignment, neutral no-evidence display, preserved unsent text, explicit request
submission and a version-1 source surviving profile version 2. The real server
showed no fake positions/assignments. All 51 pre-existing tables and eight source
PDF hashes remained unchanged; foreign-key checks passed.
