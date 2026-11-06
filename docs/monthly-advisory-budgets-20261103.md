# Monthly advisory budgets — deployed, acceptance BLOCKED

## Live checkpoint — 2026-11-03 15:51 UTC

The original authorized release16 apply completed once with native exit0:
API/admin/customer image pins changed; root151→154 and child206 unchanged.
Original process absence and full protected read-only guards are verified.
Explicit migration0006 committed earlier: **45 legacy true hard-stops audited
then OFF**, zero new allocations. Runtime DML/CAS/read rollback proof and private
runner cleanup passed. **Never rerun the migration or consumed release stages.**

**End-to-end acceptance FAILED/BLOCKED; do not describe the feature as complete.**
Fresh admin load shows “Portal not configured” because the sealed production
build omitted required public Vite configuration. Customer root still loads the
inherited bundle without the monthly endpoint: new dist was copied under a
subdirectory rather than the site's nginx document root. Its nested HTML points
to a root asset returning404. The customer session also reports “Invalid access
token”; its cause is not established.

Immutable selected-asset equality passed, but the customer proof selected
inherited files. It does **not** prove new monthly UI delivery or authenticated
usability. Protected infrastructure guards passed independently of these defects.
Authenticated monthly summaries/list/history and customer-role acceptance remain
unverified. Unconfigured is expected from retained zero-policy/revision counts;
no authenticated live summary is claimed and no allocation was fabricated.
Anonymous customer-origin GETs returned403 for admin budgets and401 for own
budgets; these are perimeter checks, not authenticated acceptance.

Retained Linux no-push validation passed: admin cm64 **40**, customer cm65 **40**,
API cm68 **58** cases, zero failures. No tests/builds/plans/applies were replayed
to resolve the browser defects. No paid inference or corrective cloud mutation
was performed during final reconciliation. A separately authorized frontend-only
successor is required; preserve sealed contexts and the current API/database.

See [final report](../.deployment/monthly-budget-20261103-01/FINAL.md),
[browser evidence](../.deployment/monthly-budget-20261103-01/verification17/ACCEPTANCE-BLOCKED.json)
and [protected guards](../.deployment/monthly-budget-20261103-01/verification17/GUARDS.json).

## Historical source implementation checkpoint

The source-only observations below describe the earlier implementation phase;
their no-deployment and pending-integration statements are superseded by the
live checkpoint above, not erased. Component tests did not detect the final
production configuration/document-root defects.

## Scope

Implemented recurring organization USD budgets for UTC calendar months, without
rollover. Admins configure a positive allocation and an on-screen advisory
threshold (default 80%). Customer views show allocation, known external-price
estimated usage and utilization, period, freshness and pricing coverage.
Utilization may exceed 100%; budgets never authorize a traffic hard-stop.

No email adapter, ACS configuration, recipient lookup, delivery tables, worker,
notification backlog or email permissions are required. Organization model-access
Feature 2 remains paused. This source implementation is not a deployment receipt.

## Contracts and accounting

- `GET /api/admin/monthly-budgets`: paginated organization summaries.
- `PUT /api/admin/monthly-budgets/{organization_id}`: positive decimal-string
  `allocated_usd`, integer `advisory_threshold_pct`, `expected_version`, and
  audit `reason`. Concurrent updates return 409 rather than overwrite changes.
- `GET /api/admin/monthly-budgets/{organization_id}/history`: revision audit.
- `GET /api/budget/monthly`: current authenticated organization's summary.

Reads do not create an allocation. Changes apply immediately to the current and
future months; historical observations select the policy revision then in force.
Usage includes all organization subscriptions in `[UTC month start, next UTC
month start)`, through the response's as-of timestamp. Historical usage is neither
reset nor deleted. External prices effective at event time are used; recorded
internal costs and internal tariff fallbacks are not budget prices.

Production Decision-1 scoring telemetry is not fully persisted in the SQL usage
ledger. Consequently, observed completion estimates are conservatively reported
as incomplete: known usage and utilization remain visible as lower bounds, but
remaining allocation and reassuring below-threshold status are withheld. Zero
unestimated observed rows is not proof of complete billable-stage coverage.
Persisted, attributable scoring rows use external input-only pricing when known.
Full scoring-telemetry ingestion remains a separately reviewed follow-up.

## Budget enforcement safety

Legacy budget hard-stop defaults are OFF. Legacy update payloads cannot enable
budget stopping, local playground admission no longer rejects for budget
exhaustion, and the legacy generated policy preview has no financial admission
gate. Independent authentication, model restrictions and safety remain intact.
This does not assert anything about a newly inspected live APIM policy.

The additive migration records existing true hard-stop values in a remediation
audit table before disabling them. Downgrade retains that audit and the OFF
default rather than silently restoring blocking behavior.

## Migration and release cautions

Migration `0006_monthly_advisory_budgets` branches directly from
`0004_external_pricing`, independently of paused `0005_organization_model_access`.
Only the explicit budget target is appropriate for a separately approved release;
upgrading all heads would also apply Feature 2. Verify the actual applied revision,
private PostgreSQL migration access and runtime DML grants first.

Historical initial migration imports live metadata. Empty-database bootstrap is
therefore not Feature-2-isolated; do not treat fresh bootstrap as a validated
production migration procedure. PostgreSQL execution and concurrent-session CAS
still need approved integration validation. Do not deploy the dirty workspace as
a whole: compose a narrow delta against the exact deployed parent.

## Local verification

- New budget backend tests: **58 passed** (including UTC boundaries, external
  tariffs, organization isolation, CAS conflicts, migration remediation and
  no-budget-blocking contracts).
- Related backend regressions: **160 passed** across FinOps repair, external
  pricing/API/privacy, model-access compatibility, gateway settings, managed
  controls and Turnstile exchange.
- Deployment offline subset after test-fixture isolation: **66 passed**,
  **8 deselected** (PowerShell/real Terraform cases). The fixture uses temporary
  source copies and leaves real operator overrides and production guards intact.
- Direct TypeScript checks: shared UI, admin portal and customer portal all
  exited 0.
- Frontend tests are authored but not executed: native esbuild/Vitest are blocked
  by corporate policy. No bypass attempted. An approved Linux test environment
  and UI runtime acceptance remain required before release.

No production database migration, image build/push, cloud mutation, paid inference
or deployment was performed for this implementation.