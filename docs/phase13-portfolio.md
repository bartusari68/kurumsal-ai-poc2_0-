# Faz 13 — L&D portfolio decision support

The organization-wide portfolio is restricted to the existing NEEDS_ANALYST role,
matching Faz 12 stewardship. Department managers and employees receive only their
explicitly addressed preparation handoffs; those never include aggregate evidence
or private evaluation text. Existing creation/referral/assignment permissions apply.

## Facts and rules

`portfolio_query.py` uses 13 batch aggregate queries independent of skill count.
Planned demand counts active profiles' current sealed REQUIRED requirements.
Observed demand counts active, human-verified request skill needs linked to named
accounts. Open and resolved use RequestWorkflow; outcome answers remain separate.
No course-count metric claims complete coverage. The table includes inactive skills
for retained history, but new planning topics require an active skill.

Only current PUBLISHED catalog pointers count as available coverage. Historical
published/archived CourseVersions retain their separate outcomes. Evaluation
eligibility requires the current active completion timestamp. Mapping duplicates
do not multiply enrollment/evaluation counts. Participant APPLICATION, authorized
APPLICATION and per-mapped-outcome LEARNING distributions remain separate.

`portfolio_policy.py` centralizes lifecycle and deterministic signal explanations.
Existing evaluation minimum sample (5 people) and repeated observation count (2)
are reused. Privacy also uses Faz 12's minimum 5 distinct people, including small
complementary cells: if a nonempty cell is too small, the entire partition and
its derived signals are hidden. A true zero is disclosed; hidden is `null`, never
zero. No employee names, response comments, employee evidence IDs or employee
rankings enter portfolio evidence snapshots. Operational record IDs link only to
routes that retain their original authorization checks.

Capacity signal means visible open demand + published content + no future SCHEDULED
session. No invented high-demand threshold, request-to-person ratio, budget or class
count is used. Numeric and unbounded capacities remain separate. Repeated need
requires a new same-user/same-skill request strictly after a current completion and
is an investigation signal, never a training-failure claim.

## Human lifecycle and reuse

Four additive tables: portfolio_items, portfolio_events, portfolio_handoffs,
portfolio_links. SQLite after-create/install triggers preserve immutable history;
existing tables/records need no destructive migration or data backfill.

One active item per skill + organization scope. OPEN → UNDER_REVIEW → DECIDED →
CLOSED, with optimistic version checks and optional named analyst ownership.
Creation and decision each capture fresh, disclosure-safe evidence, source catalog
version IDs and position revision IDs. Decisions cannot silently overwrite history.
Closing a topic does not resolve a request or cancel a downstream operation.

Saving a decision creates no downstream entity. An explicit second action addresses
a preparation handoff to a real account. The recipient opens the existing intake,
request-based enrichment action, or session form. Actual creation passes an optional
portfolio_handoff_id and records a receipt inside the original transaction. Invalid,
closed, mismatched or already-consumed sources roll back creation. Request retries
must retain the same source. Original API behavior remains unchanged when omitted.
Existing unsent request text and dirty session drafts are preserved by the shortcut.

No new model provider, LLM call, scheduling automation or dependencies are added.
Optional evaluation revision, historical employee-gap snapshots, trend reporting
and CSV export are deliberately outside this phase's core implementation.

## Verification and publication

Regression: `python -m unittest discover -s tests -p 'test_*.py'` and
`node --test tests/*.test.cjs`. The portfolio suite includes 1,000 synthetic requests,
1,000 enrollments and 3,000 evaluations plus a constant query-count check across
additional skills. Browser verification uses an isolated synthetic database.

As explicitly requested in Faz 13, stage source, source tests, documentation and
assets only. Exclude generated/temp/test-run artifacts, live SQLite and backups.
The old comparison repository's already-tracked artifacts remain in history.
The staging helper now requires explicit individual `--paths`; it does not take a
live database snapshot or stage all files. Push only after test and preservation
checks pass, and verify local HEAD equals origin/main afterwards.

Verified result: 416 Python tests + 121 frontend tests = 537 tests, including the
502-test baseline. The synthetic relational benchmark used 13 SQL statements and
approximately 1.4 seconds on the verification host. All three handoffs were exercised
through the existing desktop browser forms. All 57 previous business tables and
8 PDF hashes matched the pre-phase backup; SQLite integrity and foreign-key checks
passed. SQL aggregate timestamps are emitted as explicit UTC for correct display.
