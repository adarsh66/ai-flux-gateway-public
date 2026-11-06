# Auto gateway: source-only, default off

## Fresh pending-send UI validation — 2026-10-29 10:43 UTC

**Actual Linux ACR run `cm37` succeeded at 10:42:24.100179 UTC.** This is one
fresh submission for changed UI source, not a replay of `cm36`. This section
supersedes older statements that `cm36` is the only applicable UI validation;
it makes no new claim about live Auto enablement or deployment acceptance.

- Existing curated `scripts.validate_auto_routing --no-push` ran through the
  existing VS Code task, using configured Python 3.13 and the existing UTF-8
  Azure CLI/corporate CA. Azure MCP general best-practice retrieval returned 200.
- **160 UI tests / 17 files passed**, including deferred-reveal duplicate-send
  prevention, cancel/reset/unmount late-result rejection, 15-second credential
  timeout, newer-operation ownership and reveal cancellation during token acquisition.
- All **three TypeScript checks** and **both production portal builds** passed.
- Existing offline curation/no-push/no-resubmission guards: **7 passed**;
  [JUnit](../.deployment/auto-ui-pendingsend-validation-guards-20261029.xml).
- Exactly four curated files differ from `cm36`:
  [client](../packages/ui/src/client.ts),
  [client tests](../packages/ui/src/client.test.ts),
  [component tests](../packages/ui/src/components.test.tsx), and
  [Playground](../packages/ui/src/pages/PlaygroundPage.tsx).
- All 77 current-source and frozen-context hashes match the manifest; all four
  launcher hashes remain unchanged. Aggregate SHA256:
  `18341f9ac56523fdd1af41dab2b0bcbff653657abf4d5165b98162e795268a48`.
- Original command exit **0**, `no_push=true`, `outputImages=[null]`,
  `deployed=false`. The original worker completed before PID reconciliation;
  local process inspection at 10:42:35 and 10:43:18 UTC found no matching
  validation/ACR-build Python worker. No silent-terminal resubmission occurred.

Durable original evidence:
[intent](../.deployment/auto-routing-native-20261029T104010824145Z/build-intent.json),
[source snapshot](../.deployment/auto-routing-native-20261029T104010824145Z/sources.json),
[launcher binding](../.deployment/auto-routing-native-20261029T104010824145Z/launcher-sources.json),
[command exit](../.deployment/auto-routing-native-20261029T104010824145Z/command-result.json),
[actual log](../.deployment/auto-routing-native-20261029T104010824145Z/validation.log),
[result](../.deployment/auto-routing-native-20261029T104010824145Z/result.json).
The log's raw file-byte SHA256 is
`2656f479f399d843a7104521c436ba6417ba7bba68107bd3127cbb23baeca363`;
its normalized-text hash in the result differs due to Windows newline encoding.
Result file SHA256:
`0f4f61a7dea61a0204120ebd97ec11f39c37d3eb63c92995a502ccdd786bd061`.

Retained warnings: four npm audit vulnerabilities (one moderate, one high,
two critical), large production bundles, and an existing React act warning.
No local esbuild/Vite/Vitest, new runner, image push, application deployment,
RBAC/network/configuration change, DDL, browser Send or live inference occurred.
Browser E2E, gateway-MI scoring and APIM runtime compilation are **not** proven
by this UI run. Live enablement is outside this bounded validation.

## Actual create/readback — 2026-10-29 06:20 UTC

The original exact create was validated and **applied once**06:15:59–06:16:10 UTC,
exit0,1added/0changed/0destroyed. Original native Explore review was valid review,
not blocked by the optional CLI; its offline guarantee was nevertheless wrong.
The API GET omitted offline/current flags. Independent-process full13 protected
and supplemental comparisons passed, owner nonce matched, state lineage held,
serial183->185; the verifier failed closed rather than defaulting null to false.
Actual flat revision list subsequently explicitly reports revision2
**isCurrent=false, isOnline=true** and revision1 current/online. The copy PUT's
isOnline=false was not honored. This is NOT a successful offline-stage result.

Zero scoring/completion requests or diagnostic-policy publication. Current Auto
remains off, protected images/settings/current policies/roles/FinOps unchanged.
No original create retry, historical replay, broad apply, or cleanup/delete.
A fresh exact existing-revision take-offline PATCH successor is being prepared;
it requires its own review/validation and actual offline readback before any
diagnostic stage. Original create review is not review of the successor.

Evidence: [actual apply](../.deployment/auto-offline-revision-20261029T060302997824Z/execution01/apply-result.json),
[failed-closed readback](../.deployment/auto-offline-revision-20261029T060302997824Z/readback01/verification.json),
[actual revision flags](../.deployment/auto-offline-revision-20261029T060302997824Z/revision-list-readback01/summary.json).
The older preparation-only and permission-blocker paragraphs below are historical,
not the current status.

### Corrective saved-plan checkpoint — 06:23 UTC

The separate fresh take-offline PATCH target was generated, but validation
stopped at unknown_patch_input: azapi_update_resource computes name/parent_id
from its exact resource_id, and the guard currently rejects those unknowns.
The writable body is exactly isOnline=false. This finding does not authorize a
bypass or apply. Full/narrow plans and failure remain retained in the second
correction package; the first package's unsupported-argument preflight failure
also remains retained. 32 focused offline tests pass; actual successor roles/
final-baseline/workflow and independent review have not completed. No correction
apply, diagnostic publication, scoring, completion, or image build/push occurred.
Actual revision2 remains noncurrent/online, not offline verified. See the
[current correction checkpoint](../.azure/deployment-plan.md) before resuming;
never replay original create or full companions.

## Authorized revision staging and isolation review — 2026-10-29

**Live deployment is authorized; the absence of an existing spare revision is
NOT an authorization blocker.** This supersedes that implication in the older
05:54 record. Auto must nevertheless remain off on current until runtime proof
and the exact release validations succeed.

### Actual fresh preparation result — 06:05 UTC

[Preparation evidence](../.deployment/auto-offline-revision-20261029T060302997824Z/result.json)
completed at 06:05:03.530359 UTC, with **zero cloud configuration writes and zero
applies**. Revision2 was absent at both discovery and final check. The narrow
saved target creates only azapi_resource.auto_stage_revision[0], with
isOnline=false/isCurrent=false. Terraform init/fmt/validate succeeded; validate
reported zero errors and the existing provider-development-override warning.
Both fresh plans were inspected; the full companion additionally proposes only
a semantically unchanged current-policy representation update and is NEVER APPLY.

- Target SHA256: 6675631640d48342ad5a55d38613e56c3393aaed67ae4889e98cdfbb1f400998.
- Source binding: 9c678b621b3ae289d7ca9906560a3ee59b0dcacd24b1661391cd3b03b78246c1.
- Complete protected baseline remained
  90c0e4a501cd5d2c3256b4777e7699d517cb5d8ec5c47186973858001e32e9b7;
  all13 components, all4 settings/image sets and state bytes unchanged.
- Existing default state retained lineage and serial183. No competing mutation
  worker at final collection; retained historical intents unchanged.
- 45 focused tests passed (35 new preparation negatives plus10 gate tests);
  all3 new source/test files have no editor diagnostics. Existing cm36 retained
  without rerun; broader backend failures below remain unchanged.

**Not independently Validated and not applied.** No revision actually exists yet,
no gateway-MI scoring occurred, and Auto remains OFF. Independent reviewer
execution remains blocked by Windows group policy as documented below. Future
application requires fresh exact binding/ownership checks and actual independent
review plus recipe/Section7 completion, not replay based only on this report.

### Staging ownership and sequence

1. Use the existing infra/project-route root/default state owner, not a new
  stack. Select the next actually unused revision of aiflux-dev-unified after
  fresh discovery and exclusive worker/intent checks. Bind a random 128-bit
  ownership nonce, exact resource ID, source hash, state lineage/serial and full
  current 13-component baseline in durable evidence before any attempted write.
2. The first saved target may create ONLY that noncurrent revision with
  **isCurrent=false AND isOnline=false**. Copying the current API initially
  retains its existing auth, product, safety and 13 explicit routes; Auto is not
  in the copied policy. Creating offline prevents a revision-URL probe before
  isolation. An actual GET must subsequently prove offline/noncurrent, exact
  nonce and product/subscription settings before any successor action.
3. A separately validated offline-policy stage must retain CORS, product-scoped
  active subscription authentication, existing shared quota/safety/redaction,
  and reject all non-probe operations before any scoring or forward. Restrict
  the probe to the existing authorized subscription, approved exact source IP,
  exact benign fixed request and short absolute deadline. Neither a revision
  URL, random ownership nonce nor a new header alone is authorization. Do not
  forward a scorer token/body to callers or put it in trace output.
4. Only after independent exact policy/operation/product readback, actual APIM
  policy compilation and full protected comparison may a separate reviewed
  online transition be considered. Current remains unchanged. No general Auto
  capability is exposed by this diagnostic stage. Existing global/product
  inheritance must also be assessed; never alter protected global policy just
  to make a probe reachable.
5. Before invocation persist a **total budget of one benign SystemOne scoring
  request, zero retries and zero completion requests**. Failures consume the
  attempt: no resubmission or operator-token substitute. Use fixed request data
  and a restrictive gate, not a body supplied by arbitrary callers. APIM quota
  policies are distributed and cannot alone prove an exactly-once budget; an
  exclusive controller/browser intent plus a single Send is also required.
  Record only actual status, bounded schema/key/type summaries, validated
  candidate/probability facts and nullable measured usage/latency; never raw
  model body, prompt, auth header, subscription key or MI token. Unknown usage
  or cost remains unknown. Actual gateway-MI proof is still required before
  enabling Auto or producing any trusted publication receipt.
6. Make the staged revision offline immediately after the bounded diagnostic
  using its own fresh exact validated plan. No automatic retry or promotion.
  Any compilation/protocol failure requires an explicitly source-bound successor
  plan; no failed plan replay. Build minimal curated API/portal images only
  after these runtime gates and the remaining acceptance requirements are ready.

### Ownership-safe cleanup

The new Terraform resource is default-off and has prevent_destroy. Deletion is
never implied by a failed probe, elapsed deadline or lack of a local worker.
Before a separately validated cleanup plan, an independent reader must prove:
the exact owned resource ID/nonce and creation receipt, unchanged source/state
ownership, **isCurrent=false**, **isOnline=false**, and no intervening release
or foreign revision adoption. Removal of prevent_destroy would be an explicit
source-reviewed cleanup change; the saved delete target may contain ONLY that
owned revision and its owned diagnostic children. Never delete current, invoke
delete-all-revisions, remove the original API, restore an old state, or delete
an unrelated pre-existing revision. If ownership or current state is ambiguous,
retain offline and report it, rather than deleting. The present preparation
controller deliberately has NO apply, online, scoring or cleanup entrypoint.

### Actual normal invocation-path and reviewer assessment

The existing authenticated Caldova customer Playground was loaded through its
ordinary UI. It has the active Caldova-AI subscription selected, all 13 explicit
models, an enabled Send button and an empty conversation. No key reveal,
credential/storage inspection or Send occurred. This identifies a normal
credential-handling UI path, NOT proof that a future revision is reachable or
that gateway MI scoring works. A bounded browser test could redirect only the
outgoing request URL to the exact reviewed revision without reading or changing
credentials; that must first pass the stages above.

Independent-agent review was attempted rather than invented. The VS Code CLI
launcher found no installed CLI. Under the user's delegated autonomous decision,
the first-party CLI was installed into an isolated ignored tooling directory,
with no application dependency change or install scripts. Actual execution then
failed with **“This program is blocked by group policy” (exit1)**. No alternate
runtime, cloud runner or security-policy bypass was attempted. Consequently the
required actual independent agent review is unavailable in this environment;
parent review or tests cannot be mislabeled as that approval. No cloud apply is
permitted until this explicit review gate is met.

### Source FinOps persistence review

Source inspection found that Auto currently attaches decision_overhead only to
the client routing response in
[auto-resolve.xml.tftpl](../gateway/policies/auto-resolve.xml.tftpl) and
[auto-metadata.xml](../gateway/policies/auto-metadata.xml). The existing
[provider usage trace](../gateway/policies/dev-openai.xml.tftpl) emits finops-v1
for the selected completion only. [extract_usage/ingest_rows](../services/control-plane/src/aiflux/ingestion.py)
consume one unique usage event and persist one completion row; the existing
[UsageRecord](../services/control-plane/src/aiflux/models.py) has no separate
Decision overhead fields. Thus **Decision overhead is not currently persisted**
by either a routing trace or the SQL ingester. No Decision cost/coverage claim is
valid, and no completion-token merging or second fake completion row is allowed.

Before full promotion, define/test a separate bounded correlated routing event in
the existing approved telemetry path (nullable actual scoring usage/latency/cost,
no prompts/tokens), verify retention and ingestion/display semantics without
DDL, and prove no double-counting of selected completion usage. Do not invent a
SQL field or run migrations to force acceptance. Actual wire/schema proof comes
first; no speculative usage mapping was published in this preparation. The two
legacy duplicate-0003 migration failures and PortalUser collection error remain
disclosed, unchanged; no DDL or claim of a fully green backend regression.

## Authorized live release attempt — 2026-10-29 05:54 UTC

**Auto remains OFF. The authorized release reached fresh live preflight, not
deployment.** No scoring, image build/push, saved plan, apply or cloud
configuration write was performed. No historical release was replayed.

Implemented a dedicated [GET-only release gate](../scripts/deployment/auto_live_gate.py)
and [10 passing guard tests](../tests/unit/test_auto_live_gate.py). The gate checks
existing revision/operation identities, excludes protected production paths,
captures complete before/after protected state, and never treats metadata as
runtime scoring proof. The actual task completed at **05:54:48.489897 UTC**;
[result and immutable image pins](../.deployment/auto-live-gate-20261029T055337893294Z/result.json).

Actual existing-resource discovery found:

- Development API `aiflux-dev-unified` has **only current revision 1**; there is
  no existing noncurrent development revision to use for isolated scoring.
- The only API named validation, `aiflux-native-validation-pending`, is current
  and serves protected **/v1**, not a spare isolated endpoint. Its existing
  POST chat and GET models operations were enumerated but not modified or used.
- The legacy API serves protected **/dev/v1**. Neither protected path may be
  opened or repurposed as an Auto probe. A validation name is not authorization.
- [Revision evidence](../.deployment/auto-live-gate-20261029T055337893294Z/existing-revisions.json),
  [API paths](../.deployment/auto-live-gate-20261029T055337893294Z/existing-apis.json),
  [operations](../.deployment/auto-live-gate-20261029T055337893294Z/existing-operations.json),
  and [explicit isolation gate](../.deployment/auto-live-gate-20261029T055337893294Z/isolation-gate.json).

**Concrete activation gate:** actual gateway-MI SystemOne invocation and its
response contract are still unproven, and no existing safe isolated target was
found. Continuing requires review of a narrowly scoped *new noncurrent revision
on the existing APIM API*, its exact ownership/plan, access isolation and cleanup,
or a separately identified existing safe execution target. This is not a request
for roles, identities, network access, a private resolver or per-customer approval.
The current release did not silently create that revision or test on live customer
operations. It also did not substitute another operator-token probe for MI proof.
Any later scoring run must first persist its own finite budget (one benign score,
zero retries, no completion in the contract gate), not reuse this zero-score read
intent. A passing contract gate would still not clear the remaining release and
telemetry acceptance requirements below.

Fresh protection evidence:

- All **13 protected components equal before and after**;
  SHA256 `90c0e4a501cd5d2c3256b4777e7699d517cb5d8ec5c47186973858001e32e9b7`.
  All four full settings sets were hashed without persisting secret values;
  all four image pins are unchanged, including API inventory fix `29b67faa…`.
- Exact 13 explicit aliases remain in the current policy. Auto policy nodes are
  **zero**; the three Auto enable/readiness/contract settings are absent. No
  fresh inference success is claimed for any alias.
- Current supplemental reads cover **31 role definitions, 3 RAI policies, all
  13 deployment safety bindings**, and network collections. These are current
  metadata baselines, not runtime inference authorization proof or a claim that
  no unrelated external changes could occur after collection.
- Existing project-route state ownership was read: lineage
  `8b19b704-7224-db80-7600-ef2a0cbeef10`, serial **183**. The existing remote runtime
  state HEAD was read without init, lease acquisition, plan or state write.
- Historical mutation intents were unchanged. Final worker capture found no
  competing mutation/Terraform worker; the collector and its read-only CLI child
  subsequently exited with task status 0.

Retained `cm36` remains the only applicable native UI validation (149 tests,
17 files, three typechecks, both builds); it was **not rerun**. No production
backend package was built because the earlier runtime gate blocks promotion.
The broader known result remains **506 passed, 2 legacy migration failures and
1 legacy portal-user collection error**; these were not hidden or fixed by
running production migrations. Decision-overhead FinOps persistence remains
outstanding; no persisted overhead coverage is claimed.

Preserved failed local attempts: the first GET-only collector stopped on an
APIM revision-envelope parsing error before baseline collection; the parser now
uses the documented flat revision contract and accepts the observed exact
relative API ID. Two later test collections stopped before cloud execution on
an indentation error; the corrected run passed all 10 tests. Original evidence
was not overwritten, and neither failure triggered a build/apply retry.

## Authoritative gateway-direct reconciliation — 2026-10-29 05:42 UTC

**Implementation is in source and focused validation is complete; Auto is NOT
deployed or enabled.** This section supersedes the older API-mediated architecture,
mandatory seed/tenant approval, API-audience and API-MI grant requirements below.
Those sections are historical records, not the current implementation contract.
The broader regression selection is **not green**; its exact defects are below.

### Current implementation and eligibility

- APIM obtains a token with the existing gateway user-assigned MI, client
  `5792b72e-1605-4dce-a594-4c430a5af619`, for the documented resource
  `https://cognitiveservices.azure.com` (not a scope ending in `/.default`, an API
  audience, or `https://ai.azure.com`). It calls the fixed existing SystemOne
  endpoint directly. The token is placed only on that new-mode subrequest.
  Existing explicit provider-authentication policies are unchanged.
- The control plane supplies readiness/admin views, not request-time scoring.
  [Shared snapshot loader](../services/control-plane/src/aiflux/auto_snapshot.py)
  and [release defaults](../services/control-plane/src/aiflux/pricing/auto-routing-defaults.json)
  bind the exact inventory and pricing hashes. Terraform renders the same six
  descriptors and Balanced/Cost/Quality profiles; equality is tested. Omitted
  `routing_profile` means Balanced. Unknown prices are excluded from Cost, not
  silently priced at zero. No quality benchmark ranking is claimed.
- Normally provisioned active subscriptions on the existing exact APIM product
  use the shared published defaults. There is no subscriber-ID allowlist,
  per-customer approval, per-organization snapshot or mandatory initialization
  POST. GET never seeds DB rows. Existing onboarding, suspension, reconciliation
  and organization-disable paths remain the authority for product-key access;
  these tests do not establish atomic DB/APIM propagation or runtime enforcement.
- Optional audited admin saves are **desired overrides, not published changes**.
  They neither alter the gateway snapshot nor disable other default profiles.
  The legacy API resolver remains separately default-off and constructs no
  scoring client on the disabled path. No new API-MI grant or Entra application
  registration is needed for this gateway-direct design.
- UI readiness requires feature enablement AND a trusted platform-release
  receipt bound to snapshot version, exact published-policy hash, fixed endpoint,
  gateway identity and reviewed authorization/runtime evidence hashes. Flags or
  role metadata alone are insufficient. Synthetic receipts test parsing only;
  **no real publication receipt was produced here**. This is a platform release
  gate, never a new customer approval step.
- Daily call admission runs once, before Auto-only admission, original safety,
  PII redaction, redacted safety and scoring. Only bounded redacted text is sent.
  The selected alias then receives its original limits, provider normalization,
  backend selection/authentication and completion. Output safety precedes routing
  metadata. Completion `model` and `usage` are not overwritten. Decision overhead
  has nullable measured usage/latency and unknown cost, not a free-cost claim.
- All scoring non-200s (including 401/403/429), malformed/oversize responses,
  invalid choices/probabilities, ineligible aliases and token-limit violations
  fail closed: no inference, fallback, retry or API-resolver substitution. The
  probability response shape is still a **fixture contract**, not a proven live
  Decision-1 response. Existing explicit aliases never enter Auto scoring.

### Reconciled defects and actual checks

The previous agent's phase had not finished: its focused record had 91 passed,
1 failed and 29 setup errors; Terraform had seven passing mocks but failed source
formatting. The native UI phase had already succeeded. No active Python,
Terraform, Node, .NET or Azure CLI worker was observed before successor local
checks or at final reconciliation. No cloud submission was duplicated.

Fixed in this reconciliation:

1. A real thirteen-route composition defect: GLM inserts a final response before
   the outbound closing tag, removing the whitespace anchor and silently omitting
   Auto response metadata. Match the unique closing tag instead; the full
   thirteen-alias render now requires exactly one Auto metadata node.
2. Direct-scoring MI resource now matches the documented Cognitive Services
   resource identifier; Python and Terraform assertions agree. This is a source
   correction, not proof of actual token acquisition.
3. Missing/invalid configured catalogs now become fail-closed snapshot/readiness
   failures rather than escaping as an HTTP exception from eligibility lookup.
   Added production-mode synthetic catalog and disabled-candidate regressions.
4. The request-key regex incorrectly counted equality comparisons as assignments.
   Corrected the assertion without relaxing the scoring wire contract.
5. Applied the actual Terraform formatting diff and missing final newline. The
   regression runner now continues independent suites after collection errors
   but preserves the failing exit status and original error in retained JUnit.

| Check | Actual result and retained evidence |
| --- | --- |
| Focused Python, snapshot, policy, rendered C# and runner guards | **123 passed, 0 failed/errors/skipped**, [result](../.deployment/gateway-direct-focused-20261029T053709380077Z/result.json) |
| Rendered C# subset | **29 tests** included in the 123; offline SDK compilation/execution with stubs, NOT APIM compilation |
| Offline Terraform | Validate and both source-format comparisons pass; **7 mocked tests passed**, [result](../.deployment/gateway-direct-terraform-20261029T053830856676Z/result.json) |
| Broader selected backend regression | **506 passed, 2 failed, 1 collection error, 0 skipped**, [result](../.deployment/gateway-direct-regression-20261029T053943745793Z/result.json) and [JUnit](../.deployment/gateway-direct-regression-20261029T053943745793Z/tests.xml) |
| Existing native Linux run `cm36` | **Succeeded** at 05:20:22.776375 UTC; **149 UI tests / 17 files**, all 3 TypeScript checks and both production portal builds, [result](../.deployment/auto-routing-native-20261029T051807795528Z/result.json), [actual log](../.deployment/auto-routing-native-20261029T051807795528Z/validation.log) |

Counts overlap: the 123 focused cases are included in the 506 passing broader
cases; the 29 C# cases are included in both. Terraform uses mocked `plan`
commands only: no real plan, refresh, apply or cloud initialization occurred.

`cm36` was **not rerun or resubmitted**. Its 77 curated source files and all 77
staged context copies were independently rehashed offline: zero mismatches.
The aggregate source SHA256 is
`8f232214c295bc097300f285da5a88d9e432043b2e6e768ac45c702a5ea1ccbc`.
The log's file-byte SHA256 is
`23c31dd316e9385c3b2af3b2df6bae2e658db5fb15e4f6eb5c7b74c7e19bbfb1`;
the result's normalized-text log hash is different because of Windows newlines.
The retained intent is no-push and `outputImages=[null]`; no image was published
or deployed. Backend/policy/test/doc corrections are outside that UI context;
the existing native pass remains applicable to the unchanged UI. No local
esbuild/Vite/Vitest execution or restriction bypass was attempted.

### Remaining defects and release limits

- [Legacy portal-auth tests](../tests/unit/test_portal_auth.py) cannot collect:
  they import nonexistent `PortalUser`. This task did not invent an alias or
  remove that suite to make the report green.
- Two existing migration tests fail because both
  [portal-users migration](../services/control-plane/migrations/versions/0003_portal_users.py)
  and [stable-teams migration](../services/control-plane/migrations/versions/0003_stable_teams.py)
  declare revision `0003`, yielding multiple Alembic heads. No migration, DDL or
  unrelated authentication rewrite was performed.
- Actual APIM policy validation/compilation, gateway-MI scoring access and the
  real response schema remain unverified. Historical operator 401 is not MI
  evidence and was not replayed. Role metadata is not invocation proof.
- Browser E2E, live onboarding/suspension propagation, distributed counter
  charging, Decision overhead FinOps persistence and live protected-state
  comparison were not performed. Dependency audit and large-bundle warnings in
  the retained Linux log remain; no unrelated dependency upgrades were made.
- All thirteen explicit aliases are preserved in the full render, and Auto-off
  policy bytes equal the original composition. The protected inventory modules'
  exact predecessor hashes are asserted and their persistence tests pass. No
  stale inventory collector/release was replayed.

Implementation scope is complete enough for source review, **not deployment
acceptance**. This reconciliation made no image push, new cloud build, inference
probe, live configuration/policy/role/network/DB write, new infrastructure or
deployment. See the [updated architecture handoff](auto-routing-central-handoff-20261029.md).

## Historical API-mediated implementation records (superseded)

## Current bounded implementation result — 2026-10-29 04:32 UTC

**Source validation passed; activation remains blocked. Auto is still off and
no runtime change was made.** This section supersedes earlier validation and
authorization statements below; those describe previous source-only work.

- Reproduced and fixed Auto readiness accepting local/scorer audiences. The
  resolver now rejects an invalid service-auth configuration before verification;
  readiness fails closed without querying profile data. An Entra-shaped audience
  is only a shape check, not registration, token acquisition or network proof.
- Reproduced and fixed Decision HTTP 402/405/413/415 falling into degraded
  fallback. All 3xx/4xx are now access/configuration errors, with no fallback or
  retry. Timeouts, transport/server failures and malformed scores retain the
  bounded eligible fallback contract.
- Updated the stale combined router-page UI test: the page now edits audited
  profiles, not the legacy endpoint/policy preview. All real Auto UI tests ran.
- Added isolated [Linux validation runner](../scripts/validate_auto_routing.py),
  [metadata audit](../scripts/deployment/auto_identity_readback.py),
  [runner guards](../tests/unit/test_auto_validation_runner.py) and
  [offline evidence binding](../scripts/audit_auto_implementation.py).
  Historical release entrypoints and immutable evidence were not modified.

### Actual validation

| Check | Actual result |
|---|---|
| Auto/backend, existing turnstile, inventory persistence, rendered policy | 173 passed, 0 failed, 0 skipped; existing Starlette deprecation warning |
| Expanded complete thirteen-route render | 10 passed; includes the preceding 9 policy cases, not 10 additional unique tests |
| New no-push/context/reconciliation guards | 7 passed |
| First Linux ACR run `cm34` | Failed: 145 UI passed, 1 stale router-page expectation failed; all 3 typechecks passed; production builds not reached |
| Corrected fresh Linux ACR run `cm35` | Succeeded 04:26:58.633923 UTC: 146 UI tests / 17 files, all 3 typechecks, both portal production builds |

There were **two distinct one-shot no-push submissions**, not retries of a run.
The silent terminal wrapper was reconciled from its existing evidence before
any successor was submitted. `cm35` has `outputImages=[null]`: no published image.
77 curated source files were uploaded; source/context hashes were rechecked at
04:32 UTC. No credentials, environment files, private settings, Terraform state,
backend source or historical deployment folders were uploaded.

Existing dependency audit warnings remain: 1 moderate, 1 high and 2 critical npm
vulnerabilities, plus large production-bundle chunk warnings. No dependency
upgrade, audit suppression or unrelated legacy rewrite was attempted. Final
worker inspection found no Python validation/build worker still running.

The [source manifest](../.deployment/auto-routing-native-20261029T042445894316Z/sources.json)
has source SHA256 `feb3269e1e3190f4f51a6fd9bacf58c9d5ae4d3d1d85c3f2915cdb2b3acc59e9`.
The [final audit](../.deployment/auto-implementation-audit-20261029T043233815135Z/audit.json)
binds backend sources, inventory modules, JUnit, identity readback and native
evidence. The validation-log **file-byte** SHA256 is
`b5016e8a109e05c773d203800de7ca94d0db46902da6f0795a8395e3e916f40c`;
the native result's `log_sha256` hashes normalized text instead (Windows newline
representation), not different test results.

Exact executed commands are retained in the new VS Code tasks and native
[build intent](../.deployment/auto-routing-native-20261029T042445894316Z/build-intent.json).
The native CLI arguments were `acr build --registry pocidstokenexacr --subscription
aa28274d-fea0-46d4-b9c8-30f3ef0a0e52 --platform linux/amd64 --timeout 1800 --no-push
--file infra/image-build/FinOpsValidation.Dockerfile .`, using the existing native
CLI interpreter and corporate CA. Its Dockerfile executed `npm run typecheck`,
`npm test -- --reporter=verbose`, and `npm run build`. Python used the configured
3.13 interpreter, repository and existing virtualenv package paths. No local
esbuild/Vite/Vitest ran. The Foundry dependency check stopped because `azd` is
absent; no install or azd/Foundry subworkflow was attempted. Azure CLI guidance
MCP returned 403; its troubleshooting guide was consulted before native CLI use.

Not run/claimed: full backend suite, historical .NET harness, browser E2E,
live scoring, actual runtime MI tokens, APIM C# compilation, complete live
protected-baseline comparison, Decision FinOps persistence or rollout review.
Earlier broad legacy failures are not erased by these focused passes.

### Fresh identity and remaining gates

The [04:29 readback](../.deployment/auto-identity-readback-20261029T042927919100Z/readback.json)
completed without read errors: exact Decision deployment/account/inherited
assignments and role definitions (including custom definitions) were read.
Transitive group memberships were readable: operator 20 groups; gateway/API
zero. No matching group grants were observed. Deny enumeration at subscription,
resource group, account and Decision deployment returned empty; this is metadata
visibility, not a private data-plane test or a universal policy exemption.

- Operator: subscription Contributor and resource-group Storage Blob Data
  Contributor; no observed Foundry inference grant. No operator grant is needed
  for the runtime architecture.
- Gateway MI: existing unconditional Cognitive Services User at the Foundry
  account. API MI: **no matching direct, inherited or transitive-group assignment
  at Decision scope**. Gateway permissions do not transfer to the API's own MI.
- Decision-1: Microsoft-Decision-1 version 1, DataZoneStandard capacity 250,
  Succeeded, `decision=true`, `chatCompletion=false`. Not invocation proof.
- Existing API: audience `local://turnstile-postgres-auth`, empty Entra client ID;
  no Easy Auth Entra issuer/client/audiences observed. No verified existing Entra
  API resource was found through these configured IDs; this does not prove no
  registration exists anywhere in the tenant.

See the exact [central-team handoff](auto-routing-central-handoff-20261029.md).
Remaining gates: central scoped API-MI inference authorization (separate
approval, no grant performed), reconciliation of an **existing** Entra API
audience and token version with exact gateway identity, actual private gateway
to API authentication, approved bounded actual API-MI scoring/response proof,
remaining release regressions/telemetry and independent source-bound rollout
review. If an existing Entra resource/path cannot be identified, activation is
blocked under the no-new-registration constraint, not bypassed by local JWTs.

The readback still pins the API to inventory-fix digest
`29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64`.
Inventory code was not edited; persistence regressions passed. The complete
13-alias source render with Auto off is byte-identical to its original policy.
No image push/deploy, Terraform plan/apply, grants, new identities/registrations,
network/config/database writes, fragment publication, feature enablement,
FinOps changes or inference occurred. No old probe/build/release task was replayed.

## Integrated implementation checkpoint

Implementation has started but **Auto is not deployed or live**. Backend profile
configuration, a bounded SystemOne adapter, exact-gateway JWT authentication,
admin pool/fallback editing, customer readiness gating and request examples are
implemented in source. Profiles reuse the existing router table and require an
explicit audited initialization POST; GET never seeds data. All three profiles
start disabled. No database migration or runner was created.

The initial profile-save test failures were reproduced and fixed: SQLite removes
the UTC timezone on timestamp round-trip, changing the optimistic version hash.
Version hashing now normalizes the UTC instant and has a regression test.

Latest integrated validation: **60 passed** across the Auto unit tests, existing
turnstile tests and rendered Auto gateway contracts. All three TypeScript checks
(shared UI, admin, customer) pass. UI test cases have been added, but local Vitest
cannot collect because corporate Windows execution restrictions cause esbuild
`spawn UNKNOWN`; those cases are **not reported as passing**. The broader legacy
regression failures described below remain unresolved and prevent release.

The one retained bounded operator scoring probe returned **401 PermissionDenied**.
It did not establish the response probability schema or runtime MI access. The
documented SystemOne request contract is verified against Microsoft Learn; the
probability mapping is still a synthetic fixture contract. Existing metadata
records a Foundry Cognitive Services User assignment for the gateway principal;
it does not record that assignment for the API principal. Neither an assignment
listing nor an ARM site read proves private data-plane connectivity or inference.
Do not treat the local-login API audience as an Entra MI audience, or substitute
a Cognitive Services token for an API-scoped token.

No images were pushed and no Auto plan, apply, gateway policy publication,
configuration initialization or feature enablement was performed. No identity,
permission, network or infrastructure additions were made. Current explicit
model routes remain untouched. Remaining activation gates are the secure
existing-identity gateway/API/scorer path, real scoring response validation,
complete regression validation and independent exact-release review. No new
permissions or infrastructure are being requested as a workaround.

No deployment, cloud access, inference, build, real Terraform plan/apply, task
changes, backend/UI edits, roles, keys, identities or resources are authorized by
this change. Existing parent/backend work is not modified.

## Source implementation

- The shared development policy template is untouched. The isolated
  project-route composition returns its original `glm_policy` exactly when
  `auto_routing_enabled=false`; it does not interpolate an empty XML fragment.
- Auto accepts only bounded text and `routing_profile` balanced (default), cost
  or quality. Explicit aliases cannot supply that field. Existing tools, image,
  streaming, message count, body size and completion limits remain enforced.
- The existing daily call quota runs **once**, then Auto-only admission (6/min
  per trusted subscription), original safety, batched PII, redacted safety,
  selection, original selected-alias RPM/TPM/daily token limits, then inference.
  Explicit calls retain their original per-model limit location and keys.
- Selection sends only redacted messages, bounded output, profile and
  `context.Subscription.Id` to the fixed existing private API resolver. A fresh
  gateway-MI token targets the existing API audience, not Cognitive Services.
  Client routing headers are removed; the new-mode subrequest copies none.
- A resolver error, non-200, malformed/oversize response, unknown alias, alias
  absent from the current route manifest, or invalid limits/metadata fails 503.
  APIM implements no fallback. A validated API-owned fallback flag may be
  disclosed; it is not an APIM fallback decision.
- The resolved alias replaces `model`; `routing_profile` is removed. Existing
  provider token normalization, backend auth, output safety and completion
  usage/FinOps retain the resolved alias. Successful responses add bounded
  `routing` metadata with separate `decision_overhead` (nullable latency/usage,
  unknown cost). **No Decision FinOps/ledger telemetry is implemented or claimed.**
- Both legacy admin settings and scoped POC fragment activation are incompatible
  and rejected with Auto. The existing detached fragment is not changed.

## Deliberate activation blocker

The checked-in existing API configuration defaults to
`local://turnstile-postgres-auth`. That is a local-login audience, **not an Entra
resource for a managed-identity token**. There is no independently verified
existing Entra API audience in this delegation. Accordingly the source pins that
existing value but requires an Entra-shaped audience for enablement: **Auto
cannot currently be enabled**. No arbitrary audience, external host or Cognitive
Services scope can be substituted through variables. Independently reconcile the
actual existing API audience, then review the source pin before any activation.
This is intentional fail-closed behavior, not a claim that the API needs new
resources or permissions.

The SystemOne scoring wire contract is known; runtime API-MI inference remains
unproven (operator probe returned 401). Gateway-MI → private API connectivity and
exact JWT authentication also require independent actual validation. Metadata or
an existing role assignment does not establish either path works.

## Validation boundary

Offline Python contracts evaluate the actual Terraform policy locals, check XML,
order, byte identity off, mutually exclusive counters, fixed authentication,
redaction boundary, candidate/manifest checks, and metadata placement. The new
Terraform suite uses mocked providers only and tests defaults, source rendering
and invalid modes. These do not compile C# expressions on APIM, demonstrate
runtime counter charging, verify network reachability, obtain MI tokens or prove
scoring. Deployment requires independent actual validation and separate approval;
none is authorized here.

## Local results

- New Auto Python contracts plus existing development-policy/model-spec source
  contracts: **32 passed** (including 9 new Auto tests).
- New Terraform mocked-provider suite: **7 passed, 0 failed**.
- Local Terraform validation and formatting of the new Terraform sources pass.
  The existing provider-development-override warning remains; no initialization
  or backend/cloud call was needed.
- A broader legacy selection was inadvertently run before its helper was
  inspected: it invoked a **temporary local .NET harness build**, outside the
  requested no-build boundary. No further build-capable tests were run. That
  selection reported 33 passed, 8 failed and 55 errors: seven legacy settings
  assertions target untouched source/template expectations, and the remaining
  failure plus 55 errors require the missing .NET 8 runtime. This is not a
  passing full regression suite and is not APIM validation.