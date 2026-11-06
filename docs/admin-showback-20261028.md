# Admin showback: subscription filters and token rankings

## Status — 2026-10-28

**Applied once; independent image/protected-baseline readback passed. Full
acceptance remains blocked, not claimed complete.** The original apply started
at 11:40:36 UTC and completed at **11:42:20.213618 UTC**: **0 added, 2 changed,
0 destroyed**. The original task output and exclusive applied marker agree.
No apply/build/plan/validation was replayed during reconciliation.

Independent protected readback passed at **11:44:13.064882 UTC**, allowing only
the API/admin image changes against the complete 11:14:59 UTC baseline. All four
settings hashes, customer/ingestion pins, private PostgreSQL (public access
Disabled; zero firewall rules), all 79 RBAC assignments, identities, network/state
ACLs, FinOps, gateway policy/catalog and captured fragment were preserved.
Remote Terraform state read at 11:45:36 UTC has serial **108**, lineage
`b05cbf70-2d31-0e6e-34b7-c97e8f617ed6`, and both approved image pins.

**Historical-default discrepancy:** additional live rawxml/xml reads at
11:46:18–11:46:49 UTC show the fragment is Succeeded and detached, but is **not
the earlier revision-8 zero-override defaults**. Root limits remain
60/2048/10000/1000 and thresholds 1/1/1/1; an additional safety branch contains
self-harm threshold 0 (other branch thresholds 1). Its byte hash
`09c8c268d63490daeff42d8fbd414fd564743c325c32f72d7c553197f3b0896f`
already appears in the pre-release baseline and equals the post-release hash.
Canonical fingerprint is
`36af0cecf7ed9482ff8807f44474862c15dfa363918fc6d35e455b0ec6ae9edc`,
not the earlier defaults fingerprint. Both exports agree. Thus this release
preserved its captured baseline, but the requested historical-default invariant
is **not satisfied**. No attribution, current revision number, or settings
restoration is inferred; no settings save/reconcile/fragment write was attempted.
Active policy remains detached and hash
`e45b6de7b61b29a4085b4569609da48314d9c144306a9c02211d1ce58ce5b456`.

Evidence: local ignored .deployment/admin-showback-release-20261028, including
apply-intent, applied, verified, reconciliation and deploy-result records.
The paused publisher HTTP 502 task was not retried. Customer personal
usage/identity attribution remains out of scope.

- Retained UI run `cm2t` source/context/remote no-push provenance matches current
  source exactly. It is UI verification, **not backend verification**.
- Fresh production API Linux no-push `cm2u` passed **309 tests**, with two known
  migration tests deselected; package uses Python 3.11. PostgreSQL/SQL Server SQL
  compilation and SQLite execution are covered; no live PostgreSQL load claim.
- One source-bound build per image: API `cm2v` finished 11:20:27 UTC,
  digest `b489df53815f0d0242eda4c28b2c471bca2ce53344abc6733220c67c87bc0e09`;
  admin `cm2w` finished 11:22:10 UTC,
  digest `2846f1ff04244f20cb6612cca62c348b6a79a2fff7245dfc609347564becbfe5`.
  Combined release source SHA256:
  `74e2f1c15b4e18d45e5835bea8d6958142ee11f71493fd0c5b13fb778746e8c3`.
- API source delta against the actually deployed publisher-fix predecessor is
  exactly app/finops/schemas Showback changes. Publisher apim/gateway_settings
  runtime files are unchanged. Existing local Fireworks/Terraform compatibility
  edits are not part of the target runtime deployment.
- Fresh exact two-image target saved at 11:27:52 UTC, SHA256
  `eede40a0218ab59bc7f8579b74caca5b018a203cb6abf837d26ea68644225f92`.
  Full identical-input companion is **NEVER APPLY**: it includes unrelated
  proposed writes and exists only to resolve excluded preconditions. Those
  writes are neither approved nor part of the exact API/admin target.
- Existing Checkov 3.2.495 offline Dockerfile scan: API **53 passed**, admin
  **117 passed**, zero failures/skips/parsing errors. This is not a dependency
  CVE scan. Existing npm findings (1 moderate, 1 high, 2 critical) remain.
- Live admin HTML/health and the new hashed JS asset returned HTTP200; the bundle
  contains the subscription selector, both rankings and the ranking API route.
  Anonymous `/api/me` and ranking requests return HTTP401, as required.
  `/api/healthz` returns 404 (not a defined API route); portal `/healthz` is 200.
  Authenticated existing customer session returns HTTP200 for `/api/me`,
  `/api/models` (all13 exact identities) and organization usage: 11 records,
  input474/output1602/total2076 tokens. Offset0/1 with limit1 retain full totals;
  admin ranking through the customer origin returns HTTP403. No inference/key call.
- Authenticated **admin** acceptance remains blocked: requested browser tab
  `41a157b5-811f-44b1-88e3-ff6dceeddd2b` shows sign-in and has no admin session.
  Subscription selection, global/within-org ranking values, time/model scope and
  admin pagination/record totals are **not live-verified**. The user must sign in
  directly; credentials are not inspected, extracted, or handled by the agent.

## Behavior

- Admin Usage adds **All subscriptions** and an ID-disambiguated subscription
  selector, scoped to the selected organization (or all organizations). Metadata
  comes from the existing safe `adminSubscriptions` API, reading every 100-row
  page before local name/organization/ID search. There is no first-100 truncation
  and no subscription-key request. Loading/error/retry states are explicit.
- Organization selection clears the selected subscription and detail offset in
  the same state update. Old metadata, model options, detail and ranking results
  cannot populate a new scope. Ranking selections apply organization/subscription
  filters without altering the UTC viewport.
- Request rows, summary, minute series, model-token series, admin model options
  and CSV share the same explicit UTC half-open interval `[start,end)`. Detail
  subscription/model filters propagate to every applicable surface. CSV retains
  its full filtered-window behavior and existing 10,000-record cap.
- **Organizations by token usage (global)** always compares all organizations
  for the selected window/model, independent of the detail org/subscription.
- Selecting an organization also shows **Subscriptions by token usage** for all
  subscriptions in that organization, independent of the detail subscription.
  With All organizations selected, a hint replaces this second table.
- Both accessible tables paginate 10 groups, ordered by measured total descending
  then ID ascending. Matching-request groups only are included (not invented
  zero-usage organizations/subscriptions). Rows show stable IDs as well as names,
  requests, input/output/total tokens, scope share, missing measurements and
  incomplete usage/pricing/attribution counts. Refresh, window, zoom/pan and model
  changes update rankings; request-table pagination does not affect their totals.
- Customer selectors, requests and relative-period model discovery retain their
  previous behavior; no new ranking endpoint is accessible to customers.

## API and measurement contract

`GET /api/admin/usage/rankings` requires the existing Admin dependency.

Parameters: `dimension=organizations|subscriptions`, `days`, optional timezone-aware
`start`/`end` pair, optional `model`, `offset >= 0`, and `limit=1..100` (default 10).
Subscription rankings require an existing `organization_id` (422 when missing,
404 when unknown). Organization rankings ignore detail organization selection.
There is deliberately no subscription filter for this comparison API. Existing
detail APIs continue to reject org/subscription mismatches with 404.

The response contains `items`, full matching-group `total`, full-scope `totals`,
`dimension`, `organization_id`, `start` and `end`. Each row includes `id`, `name`,
`requests`, nullable `input_tokens`, `output_tokens`, `total_tokens`, nullable
`share`, `missing_token_requests`, and `incomplete_requests`.

- Known component sums include partial records. A total includes **only requests
  with both input and output measurements**, consistent with existing usage and
  model-token totals. A partially measured request is not treated as fully known.
- Cache hit/write counts are already subsets of input; they are not added again.
  Failed/throttled records are included when matching telemetry reports tokens.
- All-unobserved component/total sums remain null. Empty scopes have zero requests
  and groups but null token totals; this does not assert healthy zero traffic.
  Reported measured zero is distinct from unobserved usage.
- Shares use the measured total across **all** matching groups, never the current
  page. A null numerator or nonpositive/unknown denominator yields null share.
  Missing-token and financial/attribution incompleteness remain separately visible;
  a non-null measured total does not imply complete telemetry or pricing.

Implementation uses two parameterized grouped SQL reads for aggregates and page,
not an organization loop or request-row materialization. Grouping includes IDs
and labels, so duplicate names do not merge. Tokens are cast to BIGINT before
summing. The existing org/time and subscription indexes are retained; no schema
migration or speculative index change is made. SQLite execution and PostgreSQL/
SQL Server SQL compilation are tested; a live PostgreSQL query-plan/load test was
not performed.

## Verification

- Local Python 3.13 with existing repository environment packages:
  **138 passed**, one existing Starlette/AnyIO deprecation warning. Includes usage
  rankings/filters/series/model tokens, control-plane, admin subscriptions, display
  pricing and FinOps ingestion suites. JUnit: local ignored evidence
  `.deployment/admin-showback-backend.xml`.
- Ranking fixtures cover multi-org/subscription duplicate labels, half-open UTC
  boundaries, exact admin model-option windows, deterministic ties, pagination,
  full-scope shares, all-null/partial/zero measurements, cache non-double-counting,
  failed/throttled records, 3,000 additional rows, two-query bound and customer
  401/403/foreign-scope protections. No live DB or inference calls are used.
- Local direct-Node strict TypeScript: **all three workspaces passed**.
- Standard local Vitest was blocked **before test collection** by Windows policy
  (`esbuild` spawn UNKNOWN). No policy was disabled.
- Fresh existing-ACR Linux/amd64 **no-push** validation `cm2t` succeeded at
  `2026-10-28T11:00:31.024260+00:00`: **123 tests passed across 16 files**, including
  seven new admin-showback UI tests; all three typechecks and both portal production
  builds passed in the ephemeral validator. No image was published (`outputImages`
  was `[null]`), and source/context hashes matched.
- Successful native source SHA-256:
  `d2c3cf5e830c52e63b93b8ee3b0b2b9d2e33b12ea79f3a9ab18adced8f283525`.
  Local ignored evidence folder:
  `.deployment/admin-showback-native-20261028T105813526933Z`.
- Prior no-push run `cm2s` is retained: 119 passed / 3 failed due to test assumptions
  about the new endpoint/region/pagination and admin viewport discovery. Those
  fixtures/assertions were corrected before fresh source-bound run `cm2t`.
- Existing npm audit findings remain: 1 moderate, 1 high, 2 critical; existing large
  bundle warnings remain. No dependency or security-policy changes were made.

## Source entry points

- [Usage page](../packages/ui/src/pages/UsagePage.tsx),
  [admin-only selector/ranking components](../packages/ui/src/components/AdminUsage.tsx),
  [typed client](../packages/ui/src/client.ts), [types](../packages/ui/src/types.ts).
- [Admin routes](../services/control-plane/src/aiflux/app.py),
  [SQL aggregation](../services/control-plane/src/aiflux/finops.py),
  [response schemas](../services/control-plane/src/aiflux/schemas.py).
- [Backend ranking tests](../tests/unit/test_usage_rankings.py),
  [admin UI tests](../packages/ui/src/admin-showback.test.tsx).
- [Fresh no-push validator](../scripts/validate_admin_showback.py) reuses the
  existing curated source collector and validation Dockerfile; it has no release,
  push, settings-publication, resource-provisioning or apply path.

API/admin deployment and independent captured-baseline preservation are proved.
Full admin feature acceptance and historical revision-8/default preservation are
not claimed. Never retry this apply; the full companion remains NEVER APPLY.