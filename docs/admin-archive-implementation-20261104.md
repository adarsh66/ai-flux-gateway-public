# Safe admin archive actions — source implementation complete, release gated

## Authorization and reconciliation

This resumes the user's paused **local source implementation only**. No cloud or
external network operation, build, deployment, firewall change, production SQL,
production archive, APIM management request or paid inference was performed.
Public IP 167.103.67.102 was not needed or used. No consumed APIM4096, monthly
budget, image-build, Terraform, migration or runner stage was replayed.

The silent prior backend work was reconciled before editing: the archive service,
archive metadata, migration, API routes, auth/lifecycle filters and two test
modules already existed. Its initial offline verification passed 24 tests with
five PostgreSQL tests skipped. It was extended, not duplicated. Existing dirty
unrelated work was retained; this is **not a clean deployment context**.

## Implemented behavior

- Delete means **terminal archive and revoke access**, never hard delete. Metadata
  records actor, time and reason; usage, teams, pricing, budgets and audits remain.
  Existing identifiers, tenant IDs, member identities, idempotency keys and emails
  stay reserved. Archived identity cannot be enabled, restored or reprovisioned.
- Admin-only preview and DELETE contracts exist for organizations, subscriptions
  and local users. Confirmation exactly matches the current server label and a
  nonblank reason is required. Missing/forbidden/blocked/invalid input remains a
  distinct 404/403/409/422 response. Repeating terminal DELETE is idempotent.
- Independent memberships have the same preview/DELETE action on the existing
  Members page. This is necessary to make organization blockers actionable:
  disabling an independent Member does not remove its dependency. A Member linked
  to a nonarchived LocalUser is blocked until that LocalUser is archived instead.
  The original three entity contracts retain their original entity-type values;
  the additional Member contract uses `member`.
- Organization archival requires **zero nonarchived subscriptions, local users
  and members**, including disabled, pending and failed children. No silent
  cascade. The IDS home organization, own account and own membership are protected.
- LocalUser and its exact `(organization_id, object_id)` Member are archived in
  one transaction. Both local JWT and Entra authorization consult DB tombstones
  on every request. No Entra directory account is deleted. Last viable platform
  administrator checks use enabled approved home-tenant Member identities across
  supported auth paths, serialized on the existing home organization row.
- Interactive child/create/key/state/reconcile/archive operations share fresh
  PostgreSQL organization `FOR UPDATE` locks, held through APIM I/O and final
  transaction. Tombstone-aware publication readiness uses an atomic SQL predicate,
  not stale ORM read-then-write. No long-running deletion worker was added.
- Subscription deletion commits local denial before external work, then reacquires
  the common lock. It operates only on a DB-linked canonical nonzero UUID at the
  configured APIM product scope. It never deletes an APIM object, operates on
  master/unmanaged subscriptions, retrieves secrets or infers ownership.
- APIM suspension is followed by exact readback. Already suspended or exact 404
  resources are safe, without creation. Unverified asynchronous state stays
  pending; errors stay failed. Admin lists retain pending/failed deletions with
  retry; customer/access/creation paths exclude them. All reveal/rotate/activate/
  reconcile actions deny deletion intents immediately.
- An earlier asynchronous/uncertain PUT cannot be forgotten when its request's
  DB lock ends. A persisted APIM operation barrier must reach a validated terminal
  status before subsequent lifecycle writes or archive certification. Only one
  operation-status GET occurs per retry; arbitrary/foreign URLs are never followed.
  Unknown transport/server outcomes stay blocked and require operator reconciliation.
  Current resource state alone is **not** a waiver for a potentially late activation.
- UI uses a shared dialog with modal semantics, inert background, keyboard focus
  trap/return, exact-label confirmation, reason, dependency counts/links, safe
  cancel, busy/double-submit protection, preview reload, visible errors and same-
  endpoint retry. Disable/Suspend remain distinct reversible actions. Revealed
  subscription keys clear before opening/attempting deletion, and late values are
  rejected. Outcome notices and page-count recovery survive row removal.
- Disabled organizations remain available as admin management filters, but not
  creation targets. The existing local-users page is reused, not replaced.

## Contract

GET `/api/admin/{organizations|subscriptions|local-users}/{id}/deletion-preview`
returns `{entity_type, entity_id, label, can_delete, blockers, dependencies, effect}`.
Dependencies contain integer `subscriptions`, `users`, `members` counts.

DELETE the same entity URL with JSON `{confirmation, reason}` returns
`{entity_id, status: archived|pending|failed, message}`. A durable failed APIM
revocation is returned with HTTP502 and its structured result preserved by the
client; generic unrelated 502 errors are not treated as deletion results. Retry
uses DELETE on exactly the same record, without creation or a new endpoint.

The same GET/DELETE shape is available under `/api/admin/members/{id}` for
independent memberships, using the exact object ID as its confirmation label.

## Persistence

[0007_admin_archival](../services/control-plane/migrations/versions/0007_admin_archival.py)
has **only** `0006_monthly_advisory_budgets` as its parent. Paused migration0005 is
not an ancestor of this explicit target. New nullable archive metadata, durable
subscription deletion intent/status, APIM operation barrier and audit reason
columns are additive. Existing rows remain unarchived; no financial update or
purge occurs. Downgrade deliberately refuses to drop terminal tombstones.

No production migration was applied. Never use `upgrade heads` for this change.

## Exact implementation paths

Backend service and lifecycle:

- [archival.py](../services/control-plane/src/aiflux/archival.py)
- [models.py](../services/control-plane/src/aiflux/models.py)
- [schemas.py](../services/control-plane/src/aiflux/schemas.py)
- [app.py](../services/control-plane/src/aiflux/app.py)
- [subscriptions.py](../services/control-plane/src/aiflux/subscriptions.py)
- [apim.py](../services/control-plane/src/aiflux/apim.py)
- [auth.py](../services/control-plane/src/aiflux/auth.py)
- [turnstile_exchange.py](../services/control-plane/src/aiflux/turnstile_exchange.py)
- [gateway_settings.py](../services/control-plane/src/aiflux/gateway_settings.py)
- [managed_controls.py](../services/control-plane/src/aiflux/managed_controls.py)
- [poc_controls.py](../services/control-plane/src/aiflux/poc_controls.py)
- [model_access.py](../services/control-plane/src/aiflux/model_access.py)
- [model_access_publisher.py](../services/control-plane/src/aiflux/model_access_publisher.py)

The last two paths only retain defensive archive filtering/finalization guards.
**Feature2 activation/publication was not resumed or tested.** No gateway policy,
model-permission activation, Terraform or runtime release setting was changed in
this continuation. Monthly-budget implementation and production remain intact.

Frontend:

- [DeletionDialog.tsx](../packages/ui/src/components/DeletionDialog.tsx)
- [SubscriptionsPage.tsx](../packages/ui/src/pages/SubscriptionsPage.tsx)
- [admin.tsx](../packages/ui/src/pages/admin.tsx)
- [TokenExchangePages.tsx](../packages/ui/src/pages/TokenExchangePages.tsx)
- [client.ts](../packages/ui/src/client.ts)
- [types.ts](../packages/ui/src/types.ts)
- [styles.css](../packages/ui/src/styles.css)

Tests and offline evidence helpers:

- [test_admin_archival.py](../tests/unit/test_admin_archival.py)
- [test_admin_archival_postgres.py](../tests/unit/test_admin_archival_postgres.py)
- [admin-deletion.test.tsx](../packages/ui/src/admin-deletion.test.tsx)
- [validate_admin_archival.py](../scripts/validate_admin_archival.py)
- [validate_admin_archival_types.mjs](../scripts/validate_admin_archival_types.mjs)
- [report_admin_archival.py](../scripts/report_admin_archival.py)

## Actual validation — final source

Final combined offline suite: **140 passed, 5 skipped, 0 failures, 0 errors**,
145 collected. The five skips are explicitly unconfigured PostgreSQL tests.
No SQLite success is represented as PostgreSQL concurrency evidence.

| Suite | Passed | Skipped |
| --- | ---: | ---: |
| Admin archive safeguards | 47 | 0 |
| Opt-in PostgreSQL concurrency | 0 | 5 |
| Control plane | 13 | 0 |
| Local authentication / Turnstile | 11 | 0 |
| APIM / ingestion watermarks | 5 | 0 |
| Monthly advisory budgets | 58 | 0 |
| External pricing privacy | 6 | 0 |

Archive tests cover permissions, confirmations/reasons, own/home/last-admin
protection, disabled/pending children, exact member linkage, old-token denial,
identifier reservations, nonresurrection, stale reconcile and readiness CAS,
partial APIM/DB failures, async/unknown operation barriers, safe URL/readback,
master protection, retained FK/history/monthly budgets and the actual explicit
Alembic successor target. The offline runner denies external sockets, DNS and
DefaultAzureCredential acquisition; local TestClient loopback is permitted.

Direct installed TypeScript checks passed for **all three projects**: UI,
admin portal and customer portal. **13 new frontend interaction tests authored,
not run.** No esbuild, Vite, Vitest or blocked Ruff executable was invoked or
bypassed; no Linux/cloud frontend build was submitted.

Final evidence (earlier overlapping runs are not summed):

- [Backend final XML](../.validation/admin-archival-20261104/backend-final03.xml)
- [TypeScript final results](../.validation/admin-archival-20261104/typecheck03.json)
- [Final counts, source hashes and release gates](../.validation/admin-archival-20261104/FINAL.json)

PowerShell intermittently emitted a leading-variable/prefix error while still
executing the following command. Completed retained receipts were reconciled,
not assumed missing or replayed. Final XML and all three typecheck exit0 records
are the authority for these counts. Selected editor diagnostics and Python AST
syntax checks were clean.

## Remaining release gates — no approval inferred

1. Separately approved Linux frontend runtime tests and real browser/accessibility
   acceptance. These 13 tests and existing UI regressions are unexecuted locally
   because corporate esbuild policy remains respected.
2. Real PostgreSQL multisession create/disable/archive/activation races, explicit
   migration validation and runtime DML grants. Five opt-in loopback tests exist;
   no server was configured or contacted. Additional real-schema/grant acceptance
   remains required, without enabling public DB access.
3. Approved disposable APIM resource suspension/readback/async-response behavior
   and existing least-privilege read/write/operation-status permissions. No grant
   inventory was queried and no broader role is assumed. A denied/unknown operation
   must stay failed, never be waived into success.
4. Separately approved clean-parent release composition, with the explicit0007
   target only, excluding paused Feature2 and preserving monthly budgets,
   APIM4096, pricing, routes, quotas, identity, network and existing images outside
   the reviewed scope. This dirty workspace must not be deployed wholesale.
5. Separate explicit approval of selected disposable organizations/users/members/
   subscriptions before any real archive acceptance. No production deletion or
   archive is authorized by this source implementation.

**Source implementation is complete with offline validation. Full runtime,
PostgreSQL, APIM and deployment acceptance is not complete or authorized.**