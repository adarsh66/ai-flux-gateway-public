# Decision-1 portal implementation

## Status

**Deployed and verified — 2026-11-01**, with remaining manual portal-session
acceptance. API cm4m and corrected admin cm4s/customer cm4t are applied; final
protected readbacks and both portals' live packaged HTML/JS/CSS hashes pass.
The intermediate portal source-overlay defects and their corrections are disclosed
in the [final live deployment report](decision1-live-deployment-20261101.md).
Current authenticated data rendering across every page is not claimed: the shared
portal sessions expired and require normal fresh login for remaining read-only checks.
No new credentials, access gate, deployment or paid inference is required by this caveat.
The Auto pool configurator remains deferred.

## Changes

- Removed the customer catalog Routing simulator and obsolete Auto-disabled copy.
- Added a presentation-only Microsoft Decision-1 scoring identity to both catalogs.
  Chat eligibility remains false; no Playground or Auto completion candidate was added.
  Deployment evidence is distinct from successful live inference authorization.
- Added a dedicated admin Model catalog navigation entry; retained the router page.
- Added an input-only Decision-1 row to the existing versioned platform rate card.
  Output and cache dimensions are N/A, not zero. Chat input/output validation and
  effective-dated historical overrides remain intact.
- Added authenticated customer/admin read-only scoring telemetry and page CSV
  endpoints, backed by the existing Log Analytics traces. Subscription ownership
  comes from SQL and the authenticated principal, not caller-supplied attribution.
- Added Decision-1 selection, token/latency metrics, SGT intervals, scoring
  organization/subscription showback and invocation details in both portals.
  All-model pages display scoring separately from explicitly completion-only totals.

## Pricing

Public source: https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/microsoft/

Microsoft lists Decision-1 at USD 0.042; cached and output dimensions are N/A.
The Azure Retail Prices API corroborates USD 0.042 per 1M metered tokens, effective
2026-10-01. The source artifact retains the eastus meter
3340205e-23e1-59c4-9be6-0e158131ec64. This tariff scope does not prove deployment
location or a customer's negotiated invoice rate.

Showback uses the explicitly disclosed input-token basis:
`measured input tokens * effective USD input rate / 1,000,000`.
Missing input means unestimated. Missing output does not prevent an input-only
estimate, but total-token coverage remains incomplete. Recorded scoring cost stays
null when the source cost is null. No legacy ModelPrice seed, recorded-cost rewrite,
budget/enforcement change or historical backfill is performed.

## Accounting and limitations

One Auto request remains one customer request, with a separate scoring invocation
and completion invocation. Scoring tokens never fill missing completion counters.
Existing completion UsageRecord ingestion/storage is unchanged.

The reader validates the trusted APIM resource, subscription owner, schema,
correlation, unique event, profile/configuration, timestamps and producer bounds.
Partial Monitor results, row overflow and invalid attribution return unavailable
with unknown totals rather than truncated or fabricated zero usage.

Log Analytics retention and collection coverage apply. A successful empty query
does not prove that no scoring occurred. Each page/export is an independent source
observation; late-arriving traces can shift rows between pages. Queries are bounded
to 10,000 events and 10,000 chart buckets; narrow busy viewports as required.
Deployed Monitor read acceptance is retained in the
[authenticated browser API proof](../.deployment/decision1-release-20261101-01/api-browser-runtime-proof.json):
both scoped scorer GETs returned 200 with 6 invocations and 25,551 input tokens.
This earlier proof does not establish current authenticated rendering of every
corrected portal page or complete historical collection coverage.

## Verification

- Final backend: **230 passed**, no failures/errors/skips across scoring, telemetry,
  completion accounting, rate-card/history and catalog inventory suites.
- Final native Linux frontend ACR run **cm4k**: **233 tests / 22 files passed**,
  three workspace TypeScript checks and both portal builds passed. No image push.
- Existing unrelated portal-auth test collection failure (missing PortalUser in
  HEAD) was documented and not included in these passing counts.
- Those source-validation runs made no paid scoring/chat requests, production DB
  changes or deployments. The subsequent scoped live release changed only the
  API/admin/customer image leaves; gateway, roles, identities, network and ingestion
  remained protected and unchanged. No tests or model calls were repeated for final documentation.

Evidence: [backend verification](../.deployment/decision1-visibility01/backend-validation-final03.md),
[source audit](../.deployment/decision1-visibility01/final-source-audit03.result.json),
[frontend completion](../.deployment/decision1-visibility01/frontend-validation03/completion.json),
and [final release report](../.deployment/decision1-release-20261101-01/final-release-report.json).

## Release and rollback constraints (deployment completed)

The completed release composed exact deployed contexts plus reviewed deltas,
not the entire dirty workspace. Corrective cm4s/cm4t fixed the disclosed portal
overlay defects. Retain all original failed and consumed receipts; existing
historical plans and applies must not be replayed. Any future rollback requires
fresh image/configuration guards and a new reviewed narrow plan.

Activate the scoring-aware API reader before exposing input-only rate-card saves;
no old reader may serve those revisions. The older reader treats an input-only
entry as malformed and falls back for the entire rate-card revision. After an
administrator saves a scoring override, rollback to that old reader requires
explicit compatibility reconciliation, not deleting or rewriting financial history.

Compatible API and portals are deployed. Remaining manual session acceptance uses
normal fresh portal login and read-only catalog, rate-card and telemetry rendering
checks; no new model calls are necessary. All 22 explicit chat routes and current
live Auto remain unchanged. Any separately requested paid inference still requires
a fresh allowance.