# Owner Performance/Calibration Dashboard Audit (CONT Phase 11)

## Scope

Hardens the OWNER-only `/owner/personal-performance` dashboard against
the mandate's checklist: accuracy, best/worst decision types,
confidence-band calibration, failure modes, weak market conditions,
target/stop realism, expected-duration realism, systematic confidence
over/underestimation -- using only real stored outcome data, explicit
"insufficient sample" disclosure, and re-verified OWNER-only access.

## Checklist result

| Requirement | Where it's answered | Evidence |
|---|---|---|
| Accuracy | `target_1/2/3_hit_rate`, `stop_loss_hit_rate`, `average_realized_return_pct`, `status_counts` | Real `RecommendationOutcome` flags/returns, never recomputed from current prices |
| Best/worst decision types | `calibration_by_type` (breakdown by `RecommendationLabel`) | `breakdown_by(evaluation_outcomes, lambda o: o.recommendation)` |
| Confidence-band calibration | `calibration_by_bucket` | `calibration_error()` -- real predicted-confidence-vs-actual-win-rate buckets (ECE-style) |
| Failure modes | `status_counts` (FAILED/EXPIRED/PARTIAL/CANCELLED all counted, never hidden), `stop_loss_hit_rate` | Every terminal status tallied; no default filter excludes failures |
| Weak market conditions | `weakest_groups` (sector breakdown, ranked ascending by win rate) | `_rank_groups()` reversed |
| Target/stop realism | `target_1/2/3_hit_rate`, `stop_loss_hit_rate` | Real per-target touch flags from `outcome_evaluation.py`'s price-path replay |
| Expected-duration realism | **was missing before this phase; now added** | see "Fix applied" below |
| Systematic confidence over/underestimation | `calibration_by_bucket` | Same ECE-style bucket comparison answers this directly: a bucket where actual win rate is well below stated confidence is overconfidence, and vice versa |

## Fix applied: expected-duration realism was absent

**Before this phase**, nothing in the dashboard let the owner compare
Basirah's stated holding-period expectation against what actually
happened. `RecommendationOutcome.time_to_target_days` (the real elapsed
days from issuance to the first target actually touched, computed by
`outcome_evaluation.py`'s own forward price-path replay) was persisted
but never surfaced anywhere in `personal_performance.py`.

**Fix**: added `average_time_to_target_days` to
`PersonalPerformanceDashboard`/`PersonalPerformanceDashboardOut`,
computed the same way every other average in this module already is
(`_average([...])`, which returns `None` -- not `0` -- when nothing
qualifies, so an outcome where no target was ever reached is correctly
excluded rather than counted as an instant hit). Threaded through the
API route (`src/api/routes/admin/ai_evolution.py`), the frontend type
(`admin-types.ts`), and a new row in the "النتائج الفعلية" card on
`/owner/personal-performance`. Two new regression tests
(`test_average_time_to_target_days_reflects_real_realized_duration`,
`test_average_time_to_target_days_is_none_not_zero_when_no_target_was_ever_reached`,
`tests/unit/ai_evolution/test_personal_performance.py`) lock in both
the averaging behavior and the null-not-zero honesty rule.

## RBAC re-verified

`GET /api/v1/admin/ai-evolution/personal-performance`
(`src/api/routes/admin/ai_evolution.py:126-129`) depends on
`require_staff_role(StaffRole.OWNER)` specifically -- not
`require_any_staff_role`, which every other admin dashboard in this
file (including the broader `/decision-intelligence` route) correctly
uses instead. Re-confirmed via the existing integration tests
`test_personal_performance_rejects_unauthenticated_requests` and
`test_personal_performance_rejects_admin_staff_who_is_not_owner` (both
still passing), which prove an authenticated ADMIN-role staff account
-- not just an anonymous request -- is correctly denied. The frontend
page wraps its content in `RequireStaff`, matching every other owner
page in this codebase.

## No fabricated/demo data

`compute_personal_performance_dashboard()` reads exclusively from
`DecisionV2Snapshot` (scan-originated rows) and
`RecommendationOutcome`/`RecommendationSnapshot`
(`source="live_scan"`, `is_paper_trade=False`) -- both real, persisted,
immutable tables (see `FORWARD_TESTING_AND_OUTCOME_INTEGRITY_AUDIT.md`
for the immutability proof). `small_sample_warning` and
`insufficient_data_message_ar` are wired from real sample-size
thresholds (`_MIN_GROUP_SAMPLE_SIZE = 10` for group ranking, empty-
sample check for the top-level message), not cosmetic placeholders --
re-verified by the existing
`test_reports_insufficient_data_message_when_nothing_exists` and
`test_strongest_and_weakest_groups_require_minimum_sample_size` tests.

## Verdict

Every checklist item now has a real, evidence-based answer sourced from
immutable historical data, with the one genuine gap (expected-duration
realism) closed by surfacing an already-computed, already-persisted
field rather than inventing a new metric. RBAC is confirmed correctly
OWNER-only, distinct from the broader staff-accessible dashboards
elsewhere in the admin surface. No demo/fake data exists anywhere in
this pipeline.
