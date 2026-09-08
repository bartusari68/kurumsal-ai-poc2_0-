# Faz 10 — Learning effectiveness

Three additive SQLite tables: `learning_evaluations`, `evaluation_events`, and
`evaluation_deliveries`. Startup installs idempotent guards and creates missing
tables. No existing requests, enrollments, decisions or published versions are
backfilled or rewritten. Backup: `backups/faz10-before.db`; preservation manifest:
`tmp/faz10-preservation.json`.

## Contract

- Completed active enrollment creates immediate participant feedback in the same
  completion transaction. Learning self-assessment is created only when the fixed
  CourseVersion contains real outcomes. No fabricated outcomes for legacy courses.
- APPLICATION follow-ups are manual unless `evaluation_policy.FOLLOW_UP_DELAYS`
  explicitly configures a timedelta. Opening time controls action availability;
  optional due time is a deadline, not an invented expiry or escalation rule.
- Unique enrollment/type/evaluator-source prevents duplicate phases and notices.
  Named operational users can explicitly designate a real authorized reviewer for
  APPLICATION. Participant feedback and learning self-assessment remain participant-only.
- Pending → completed uses optimistic version checks. The submitted response and
  context are immutable, with actor/time events. Corrections are not silently
  accepted; no response revision UI is included in this phase.
- Completion corrections retain prior evaluation history and the original completion
  timestamp, block pending responses while ineligible, and exclude the corrected
  enrollment from active aggregates. They never erase submitted observations.
- No evaluation updates RequestWorkflow or creates DevelopmentItem. Outcome values
  are independent of request status even when both use the word RESOLVED.

## Access and notifications

Individual responses and free text are evaluator-only, including after submission.
Session operators receive only aggregates and scheduling controls. Request detail
exposes phase status/outcome, never response text. Reporting is role scoped; course
versions are reported separately. Reviewer authority is rechecked at access and submit.
Delegation allows the authorized session coordinator's planning operations; it does
not grant permission to answer for a participant.

The delivery table is a durable local outbox and receipt. Completion/planning inserts
it transactionally; the existing operations worker publishes due notices idempotently.
Notification APIs merge all sources using SQL pagination. Evaluation notification IDs
use `evaluation:<id>` to avoid collision with existing request and training IDs.

## Measurements

Feedback means the participant's 1–5 overall rating, with its response count. Learning
progress is explicitly self-reported, never an exam/competency result. Application
outcomes separate participant and authorized-reviewer counts. The response denominator
includes evaluation phases that have opened, not future scheduled phases; it is not a
unique-participant rate. Percentages are withheld below five eligible phases.

Two or more recorded low-progress observations or partial/unresolved outcomes produce
descriptive content-improvement signals with counts and source. This is an observation
threshold, not an institutional approval rule. No NLP, LLM calls, automatic enrichment,
ROI or AI-accuracy claims are introduced.

## Merged queue

`inbox_query.py` uses SQL CTEs and UNION ALL for request, development, publication,
training and evaluation candidates. It resolves compatible active delegations,
assignment, role/referral boundaries, actionable states and stage ages before counting,
ordering and paging. Only selected page records are hydrated. Missing historical stage
starts retain the prior zero-sort treatment. Timestamp ties now have explicit stable
IDs. The SQL implementation targets this repository's SQLite deployment.

`tests/inbox_reference.py` freezes the previous implementation for differential
fixtures; it is not imported by application code. Clock-controlled comparisons prevent
render-time second boundaries from masquerading as workflow changes.

Synthetic checks: `python -m unittest discover -s tests -p 'test_*.py'`,
`node --test tests/*.test.cjs`, `python scripts/benchmark_inbox.py`.
The benchmark uses a temporary database, 1,000/5,000/10,000 mixed items and a 20-item
first/middle/last page. It makes no external calls and never opens production data.
