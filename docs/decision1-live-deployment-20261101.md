# Decision-1 live deployment — final release report

## Final status

**Deployed and verified, with remaining manual portal-session acceptance.**
The compatible API and corrected admin/customer images are applied. This finalization
read retained evidence and performed local hash/snapshot assertions only: no further
build, deployment, cloud read, inference, credential request or production feature edit.
The platform Auto pool configurator remains deferred.

Machine-readable final report:
[final-release-report.json](../.deployment/decision1-release-20261101-01/final-release-report.json).
All times below are UTC. This is an audit of timestamped evidence, not a fresh cloud observation.

## Final immutable pins and consumed plans

Registry: pocidstokenexacr.azurecr.io. Digests below identify the respective aiflux image.

| Component | Run | Final SHA-256 digest | Applied at |
|---|---|---|---|
| API | cm4m | f04f1d1095a6bd7e87e50a9fbc6428782d600dacc37644d26bf70fa65b3df1a3 | 01:02:19 |
| Admin | cm4s | 878c4138f9389d0b20191449e88e48a6381fa21ae53fba6d64c0f20f3b4923a2 | 05:11:52 |
| Customer | cm4t | 098af49eedd50539a71327ba5b0ecf74560e363814faf9fba0477a6552b3037e | 05:16:56 |
| Ingestion, unchanged | retained | 995c8137be0c555a7f23c4f3778958881f9a959f83c6a20a4e62b8148909e196 | no release change |

Consumed saved-plan hashes, each independently reviewed and official-validation
completed, with retained native apply exit 0:

- API: 858f4640719f99aa83a3950a3ffe5601abf4e14f7ad373beb6b853e04d426ac2 —
  [apply receipt](../.deployment/decision1-release-20261101-01/api-APPLIED.json),
  [official proof](../.deployment/decision1-release-20261101-01/official-api/REPORT.json),
  [separate audit](../.deployment/decision1-release-20261101-01/api-independent-review.json).
- Corrected admin: a1f73631ed4e957282b88b7896e4b1ad61eba7cd2e39ec7009fd07bad0f1916f —
  [apply receipt](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/admin-APPLIED.json),
  [official proof](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/official-admin/REPORT.json),
  [separate audit](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/admin-independent-review.json).
- Corrected customer: 9b93bc81970387d987189bdd2afeea79c4dd814728607b46d9bbbd2dc834760b —
  [apply receipt](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/customer-APPLIED.json),
  [official proof](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/official-customer/REPORT.json),
  [separate audit](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/customer-independent-review.json).

The separate auditors are structural/offline implementations, **not a newly invoked
native subagent**. Their actual receipt descriptions are retained without inflation.

## Source-overlay defects disclosed and corrected

The intermediate cm4p admin and cm4r customer images built and applied successfully,
but did not satisfy the intended portal feature acceptance:

- Admin composition excluded the validated entrypoint containing Model catalog
  navigation and its route.
- Customer successor composition deliberately reinserted the removed legacy keyword
  Routing simulator.

[Retained diagnosis](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/diagnosis.json)
binds the then-served assets to those builds. Browser cache, wrong Docker COPY path,
or rollout delay did not explain the defects. Corrective cm4s/cm4t contexts restore
the validated admin entrypoint and remove only the simulator blocks, retaining
accepted Auto, Playground, auth, other routes and network configuration.
[Separate source review](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/independent-source-review.json)
passed. Failed original builds, intermediate successful applies, and earlier failed
guards remain preserved; none are rewritten as successful final acceptance or replayable.

## Global protected-state audit

Local comparison of the original full protected snapshot with the final full
snapshot passes after substituting **only API, admin and customer image strings**.
Original API d7ead48f… becomes f04f1d10…; original admin 4dc0f03e… becomes 878c4138…;
original customer 9c2b6ec1… becomes 098af49e…. Ingestion remains exactly unchanged.
Arrays are not reordered and no protection fields are omitted or waived.

The [final 05:17:25 report](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/customer-postapply/REPORT.json)
and [stage guard](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/customer-postapply/protected-pass.json)
retain exact all-22 membership, all four settings hashes, policy/backends, roles,
identities, network/security and ingestion configuration protections. Current live
Auto is preserved; Decision-1 does not become a chat/Playground/Auto completion candidate.

- Root serial: 132 → 137 across the API and intermediate/corrected portal applies.
  Final raw hash: eb3047513e65a537276863f905b2fec6a753a61e2643695a5ba0727c9e86e256.
- Child serial: 193 unchanged; raw hash:
  eadfb0f95123e093b1845bd0e1d8598b72e10783608a33597abd5738febcd4d4.
- Final capture: 46 ARM reads, zero writes/paid calls. Closing storage HEAD 200,
  lease unlocked. These are retained observations, not a current worker census.

This proves configuration preservation, not fresh inference of every provider or
independent raw production database equality. Source tests protect completion
accounting/history; no production ledger/backfill/DDL operation was part of this release.

## Live packaged assets and API proof

Both portals' HTML, JavaScript and CSS returned GET 200 and exactly matched the
packaged SHA-256 hashes in their corrective production build proofs:

- [Admin live proof, 05:12:31](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/admin-live-packaged-proof.json):
  JavaScript d9059c14a67dbe7afaa07bbfd47b655115839a9f52807d163b594f0901b26779.
- [Customer live proof, 05:17:34](../.deployment/decision1-release-20261101-01/portal-runtime-correction02/customer-live-packaged-proof.json):
  JavaScript 4ccc27fc5c4f760464a3d970e6a10532cd6162e0b2e5657a983033a7a88ce1ba;
  simulator absent in the live hash-bound assets.

[Earlier authenticated browser API proof](../.deployment/decision1-release-20261101-01/api-browser-runtime-proof.json)
at 01:04:09 customer / 01:04:35 admin records identity and scoring GET **200**,
telemetry available, **6 scoring invocations / 25,551 input tokens** per observed
scope, and pricing revision `decision1-scoring-20261031-v1+rate-card-v2`.
Customer catalog returned 23 identities: 22 chat plus Decision-1 with
`enabled=false`, capability `scoring`. These are retained real traces, not six
new test calls. The proof predates corrected portal deployment and is not relabelled
as current acceptance of every rendered page.

Endpoints: https://poc-ids-token-ex-admin.azurewebsites.net/admin/ and
https://poc-ids-token-ex-customer.azurewebsites.net/.

## Acceptance limitation — manual session check, not code blocked

The parent's latest browser observations, supplied for this documentation audit,
verify the new admin Model catalog navigation/route. Customer simulator absence
is proven by the live public asset hashes. The shared customer browser now shows
sign-in and admin reports **Invalid access token**: portal sessions expired.
Azure CLI sign-in is separate and does not authenticate these portal sessions.

**Current authenticated acceptance of all catalog, pricing/rate-card, usage,
showback, filters/charts and export rendering is not claimed.** Remaining work is
normal fresh portal login followed by read-only interactive checks, not an
undeployed feature, a new authorization gate, or a requirement for another build,
deployment, price save or paid model call. No credentials were requested, extracted
or reused by this final audit. The live deployment task is complete with this caveat.

## Retained validation and accounting cautions

- [Backend final source verification](../.deployment/decision1-visibility01/backend-validation-final03.md):
  **230 passed** (36 + 57 + 11 + 40 + 86), no failures/errors/skips.
- [Frontend cm4k completion](../.deployment/decision1-visibility01/frontend-validation03/completion.json):
  **233 tests / 22 files**, three TypeScript checks, two validation portal builds;
  no push. These retained source-validation counts are not a rerun against the
  final corrected source overlays and not a whole-repository pass. The unrelated
  PortalUser collection issue and earlier failed receipts remain disclosed.
- Input-only public showback basis USD **0.042 / 1M input tokens**; output/cache
  N/A, not zero. Recorded null scoring cost remains unknown. Scoring invocations
  are separate from completion requests/ledger counts.
- Reader bounds: 10,000 events / 10,000 chart buckets; partial, overflow or invalid
  attribution returns unavailable. Independent page/export observations can vary
  as traces arrive; no frozen snapshot or complete-retention guarantee is claimed.

**Rollback warning:** retain the scoring-aware API reader. An old reader rejects
input-only scoring revisions and falls back for the entire rate card. After an
admin scoring override save, rollback to that reader requires explicit compatibility
reconciliation without deleting revisions or rewriting financial history. Never
replay consumed builds/plans/applies; any rollback needs a fresh reviewed narrow
plan and current protected guards.