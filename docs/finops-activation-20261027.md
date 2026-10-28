# FinOps forward-only activation — actual gate result, 2026-10-27

## FINAL bounded live acceptance — both portals, 2026-10-27 09:22 UTC

**LIVE DATA ACCEPTED: scheduled ingestion and both dashboards are working.**
This supersedes every older paused/blocked/unverified status below without
erasing the audit or the existing ARM-versus-Terraform Always On disclosure.

For the identical **2026-10-26T09:20:00Z–2026-10-27T09:20:00Z** half-open
window, actual authenticated API responses and rendered summaries reconcile:

| Scope | Requests | Input | Output | Total tokens | Missing token measurements |
|---|---:|---:|---:|---:|---:|
| Admin, all organizations |22|1,080|1,727|2,807|0|
| Customer, Caldova |20|1,080|1,727|2,807|0|
| Admin, Caldova filter |20|1,080|1,727|2,807|0|

Native admin/customer usage, models, timeseries and model-token endpoints
returned **HTTP200**, including the proper **/api/admin/usage/model-tokens**
route with structured chart data. Admin's two extra failed requests have an
unknown model and zero measured tokens; no organization attribution is inferred.
All22/admin and20/customer rows fit the returned page; row sums match API and
chart aggregates. Customer has no organization selector; source review confirms
principal-bound organization filtering. This was not a new adversarial tenant test.

**Hourly and Daily were selected and verified in each portal.** Exact chart
tables and rendered stacks show UTC06h **103**,07h **1,158**,08h **1,546**,
and2026-10-27 daily **2,807**. Nine nonzero models include **glm-5.3:1,524**.
The admin Caldova UI resets its viewport by one minute when the organization
changes; a separate same-origin authenticated GET reconciled its totals against
the exact customer start/end above. Its native hourly/daily tables also sum2,807.
Final full page reloads at **09:22:33 UTC**, with temporary observation wrappers
removed, reconfirmed admin22/customer20 and nine nonzero daily segments each.
No authentication storage, credentials, headers, individual row IDs or raw traffic
were exported. Existing authenticated client flows were reused only in-browser.

The two scheduled09:10/09:15 successes below remain proven; additionally admin
Caldova HTTP200 at **09:20:26.706 UTC** reports healthy, `last_query_success_at`
**09:20:00.411048 UTC**, watermark **09:15:00.411048 UTC**, last row ingested
**09:20:04.593966 UTC**, lag327seconds versus900second threshold. These are
persisted database-backed health fields, not host status or stale console logs.

**Remaining financial data quality:** cost/currency remain Unknown/null, not
zero. Caldova has19 `price_missing` and1 `status_missing`; the generic UI
pricing/attribution warning does not prove every row lacks backend attribution.
Approved catalog/routing does not supply approved effective-dated prices or all
request metadata. This limits cost/showback completeness, not token acceptance.

Full protected baseline and four app-settings hashes were verified **09:14:24 UTC**;
timer remains enabled, Always On true, host Running and current d2bdae image
unchanged. Fresh security-only readback **09:21:27.146396 UTC** confirms
PostgreSQL publicDisabled/0rules and state defaultDeny/exact3approvedIPs.
Cutoff **2026-10-27T06:06:02.045288+00:00** is preserved;156oldrequests remain
deferred. No inference/manual timer, cloud configuration or manual DB writes,
new runner/build/deployment, historical replay or watermark reset. Normal real
scheduled-worker writes are the observed success, not prohibited manual writes.
Previous temporary-resource cleanup evidence is retained, not freshly re-queried.
Existing164-test evidence is referenced, **not rerun** in this UI-only acceptance.

Evidence: [final sanitized aggregate report](../gateway/validation/finops-live-final-acceptance-20261027.json).

## Actual scheduled ingestion and customer charts verified — 2026-10-27 09:15 UTC

**FinOps ingestion is working, not merely enabled.** Authenticated customer
`GET /api/usage/health` returned HTTP200, **healthy**, at09:10:29UTC:

- Global native checkpoint `last_query_success_at` **09:10:00.191316UTC**,
  watermark **09:05:00.191316UTC**, actual last customer row ingested
  **09:10:03.936714UTC**. Lag330seconds is within the900second stale threshold
  and includes the configured300second ingestion delay.
- **Second independent HTTP200 healthy checkpoint at09:15:16UTC:**
  `last_query_success_at` **09:15:00.834012UTC**, watermark
  **09:10:00.834012UTC**, last customer row ingested **09:15:11.131357UTC**,
  lag315seconds. Both checkpoint fields advanced **300.642696seconds** across
  consecutive five-minute boundaries, without manual invocation. This proves
  scheduled Monitor-to-PostgreSQL operation and normal host database writes;
  it is not merely the earlier read-only connectivity proof.
- The earlier rendered customer page already showed last-success-derived
  "Last ingested" **17:05:00 local /09:05:00UTC**. That is display precision,
  not an exact microsecond API checkpoint. The API now proves a later success.
- Authenticated usage HTTP200 reconfirmed at09:15:23UTC: **20 requests,1,080 input tokens,
  1,727 output tokens,2,807 measured total tokens**,20 fully measured,0 missing
  token measurements,1 failed request and0 throttled. All20 records fit the
  returned page. Customer-scoped first/last occurrence **06:23:48.351824UTC /
  08:39:20.508650UTC**, with **0 records before the preserved cutoff**.
- Rendered charts are nonempty across9models, including **glm-5.3:1,524tokens**.
  The chart model subtotals sum to2,807 and match the API totals. The apparent
  initial zero was the selected empty start-of-viewport bucket, not total usage.
- **Pricing remains incomplete:** known estimated cost is **Unknown**, not zero;
  all20 requests retain incomplete pricing/attribution status. Measured tokens
  are complete. No prices or billing values were fabricated or changed.
- No timer/manual invocation, inference, new runner/build/deployment, setting,
  role/network change, replay or reset was needed. Cutoff remains
  **2026-10-27T06:06:02.045288+00:00**. These are database-backed API/UI proofs,
  not stale console output or substitution of the earlier read-only MI probes.
  Existing ARM-versus-Terraform Always On deviation remains disclosed below.
- Fresh protected reconciliation **09:14:24UTC** passed: full protected baseline,
  exact ingestion settings and all four application settings hashes unchanged.
  Existing focused verification passed **164 tests**, one existing warning;
  scoped whitespace audit passed. No repair or reapply was performed.

Evidence: [live API/checkpoint and chart aggregates](../gateway/validation/finops-scheduled-checkpoint-acceptance-20261027.json).
This section supersedes the older **scheduled acceptance unverified** status below;
older observations remain historical, not instructions to reapply or restart.

## Current Always On repair reconciliation — 2026-10-27 09:04 UTC

**Always On is enabled on the existing B1 Basic plan. Timer is already enabled;
do not apply either change again. Scheduled ingestion acceptance remains unverified.**
This section supersedes all older disabled-timer/pause/runtime-blocked statuses below.

- Existing one-shot ingestion web-configuration repair completed **08:36:45 UTC**,
  HTTP200. It used an **ARM PUT**, not a saved Terraform plan. Its recorded plan
  SHA256 **de9dfe306fb177c8d1fb8030d17314ae782f4fbe33a8f7febdaee9aaeee0de13**
  binds a JSON intent, **not Terraform plan bytes or an azure-validate completion**.
  Do not retroactively label this a validated Terraform deployment. Existing
  intent/applied markers were discovered before any attempted write this turn;
  no second apply, timer reapply, restart or live configuration write was made.
- Independent ARM/settings reconciliation at **09:04:10 UTC** verifies
  `alwaysOn=true`, complete protected baseline and all four settings hashes.
  Fresh09:00:52 metadata confirms **B1/Basic/capacity1**, host **Running**,
  timer Disabled setting **false**, cutoff **2026-10-27T06:06:02.045288+00:00**.
  Current configured ingester remains **d2bdae4edbd2faf0f6c5a5b28c83882e36222767f88de9625071b251d4114c0b**.
  No SKU upgrade, new image/runner/build/scanner, role/network/ingress/identity
  change, historical156-request backfill or watermark reset.
- The existing PUT also returned two platform metadata changes:
  `remoteDebuggingVersion` null→VS2022 while debugging stays disabled, and default
  root `virtualApplications.preloadEnabled` false→true. Full prior web-object
  hash reconstruction authenticates the exact old metadata and excludes other
  web-field differences; these are disclosed, not hidden behind a broad waiver.
- **Two real scheduled successes are not proven.** Fresh bounded console zip
  HTTP200 still has host execution output ending **07:31:55 UTC**; container
  lifecycle output reaches **08:41:54 UTC** and contains the expected digest,
  but has no paired scheduled start/success records. The old storage denial is
  historical, not evidence of a current post-repair permission failure.
  Ingestion settings have neither Application Insights connection/key nor its
  authentication setting; no App Insights resource-link tag was found. No
  unrelated APIM workspace query is substituted as function-runtime proof.
- Schedule remains **0 */5 * * * *** UTC, `runOnStartup=false`; next boundary
  at the latest observation is **09:05:00 UTC**, then **09:10:00 UTC**. These
  are expected boundaries, not observed successful runs. Manual invocations0.
  Obtain current same-customer **/api/usage/health** checkpoint evidence or
  matching current scheduled invocation/success records; do not infer success
  from host Running, metadata, stale logs, or the earlier read-only MI probe.
- Final focused verification: **164 tests passed**, one existing Starlette warning;
  guard coverage rejects other protected fields and every app's settings drift,
  plus stale/manual/unmatched/duplicate schedule evidence. Source already has
  ingestion `site_config.always_on=true`; no main-stack or replacement plan needed.
  Existing-intent regression proves a repeat repair fails before any cloud call;
  final exact plan/intent/applied hash checks and scoped whitespace audit pass.

Evidence: [applied repair](../gateway/validation/finops-always-on-applied-20261027.json),
[protected reconciliation](../gateway/validation/finops-always-on-reconciliation-20261027.json),
[fresh runtime observation](../gateway/validation/finops-scheduled-diagnosis-20261027T090113Z.json),
[focused tests](../gateway/validation/finops-always-on-readback-tests-20261027.xml).
Official requirement: [Dedicated Functions Always On](https://learn.microsoft.com/en-us/azure/azure-functions/dedicated-plan#always-on).

## Current resumed diagnosis — 2026-10-27 07:24 UTC

**Timer activation remains blocked on actual runtime proofs, not on approval.**
This resumed observation supersedes the older pause and built/not-applied statuses
below. No build, deployment, new runner, role/network change or timer invocation
was performed in this continuation.

- The deployed cm1v/d2bdae image is seen in actual container logs; host status is
  **Running**, version4.1055.150.0. Host enabled/catalog=true and timer disabled
  remain the preserved baseline. Cutoff stays **2026-10-27T06:06:02.045288+00:00**;
  no reset or historical156-request backfill.
- **Proven diagnostic bug fixed:** the old parser classified Storage's
  **AuthorizationPermissionMismatch** as `monitor_access_error`. The code now
  emits `storage_access_error` separately. Actual logs contain host table-logging
  context and this repeating storage code, not `InsufficientAccessError` or
  `UnauthorizedClient`. The underlying storage denial is **not yet remediated**;
  a successful Monitor query has not been observed.
- **Proven invocation bug blocked:** the07:12 readiness invocation failed in
  HTTP-request binding before Python readiness ran. The readiness handler contains
  SELECT-only PostgreSQL checks and **does not query Monitor**. Posting a serialized
  HTTP request to the non-HTTP admin-input API returned202 but did not prove
  readiness. The controller now fails before repeating this incompatible call.
  See [official trigger guidance](https://learn.microsoft.com/azure/azure-functions/functions-manually-run-non-http).
- Fresh metadata verifies the workspace GUID matches, workspace query public
  network is Enabled, the selected UAMI is attached, host-storage UAMI matches,
  all three service URIs match the intended existing account, and the credential
  is managedidentity. Existing unconditional roles are Log Analytics Reader at
  the workspace and Blob Data Owner/Queue Data Contributor/Table Data Contributor
  at host storage. No missing role or workspace/endpoint mismatch was proven;
  no grants, endpoint changes, bypasses or replacement images are justified.
- One existing-ingestion SCM attempt for the actual MI/exact usage KQL and
  PostgreSQL SELECTs was rejected at ingress: **HTTP403/HTTPError**. No command
  execution or MI data-plane success is claimed. No retries or public opening.
- Fresh exact-six-ID GET404 checks cover preparation **2be1b356c1dd**: neither
  ACI, subnet, NSG, NAT nor public IP exists. Its preparation created0resources;
  no owned temporary resource requires deletion. PostgreSQL publicDisabled,
  0firewall rules; state defaultDeny, exact original3IPs and container metadata
  access verified. No credentials/raw errors/headers/DSNs/logs were exported.
- **102 focused tests passed**, one existing Starlette warning. Added finite
  service/error/status/SQLSTATE/stage classification and regressions for the two
  diagnostic bugs; application/image sources were not changed.
- At07:27:13UTC the exact pre-capture logging baseline was restored and read back.
  The first full protected-baseline check correctly rejected the temporary logging
  difference; no guard was weakened. At07:28:23UTC, after restoration, **full
  protected baseline and complete settings verification passed** against the
  applied34cfcd48 image plan: host=true, catalog=true, timer=false, exact cutoff,
  all other pins/settings/network/RBAC baseline preserved. No reapply occurred.

Evidence: [finite current host logs](../gateway/validation/finops-live-runtime-20261027T072429Z.json),
[identity/roles/protected-state/absence](../gateway/validation/finops-authorization-metadata-20261027T072425Z.json),
[existing private-channel403](../gateway/validation/finops-existing-private-query-20261027T072329Z.json),
[tests](../gateway/validation/finops-authorization-diagnosis-tests-20261027.xml).

Next specific gate: obtain a **valid existing-private HTTP/runtime execution
channel** for the SELECT-only readiness and exact MI KQL, without keys, public
opening or new roles. The blocked SCM route and non-HTTP admin input are not that
channel. Diagnose the host table-logging storage denial using that identity's
actual finite data-plane response. Only after Monitor, host storage and PG pass
may the already-approved timer-only fresh exact plan be validated/applied.

## PAUSE checkpoint — 2026-10-27 06:44:32 UTC (supersedes older status below)

User requested immediate pause/disconnect. No new build, apply, activation,
inference, cloud query or cleanup deletion was started for this checkpoint.
Production host/timer/container configuration was not changed for the pause.

- At06:44:03UTC existing owned image-only apply was active: Python PID9740,
  Terraform PID33420, PowerShell parent26092. It was **not interrupted**.
  The retained applied marker subsequently records **applied=true at
  06:44:19.604498UTC**, exact plan SHA256
  **34cfcd4883bbfe6848b6a35c443bf56189d2770241149597ea5e3d95e753e6b3**.
  This is the ingestion-only correction, not a timer activation.
- Bound tag **finops-20261027t062458z**, ACR **cm1v Succeeded**;
  ingester digest **d2bdae4edbd2faf0f6c5a5b28c83882e36222767f88de9625071b251d4114c0b**;
  source SHA256 **05295bc8a95dc0425d0f92458dc52d4b7abaf41843a7ddb9ddf0bd60020d7a38**;
  manifest SHA256 **f68e82e200ee155a3713c551a019e403f33d0f6d15a63f2da7e66769d911cb37**.
  Retained evidence is in that tag's ingestion-image-only-applied-host folder.
- At06:44:32UTC Terraform PID33420 was absent; Python9740 and parent26092
  remained in the existing apply controller's **read-only postapply verification**.
  Inspection of that controller confirms no subsequent apply/timer action.
  No verification marker existed at the last directory inspection: successful
  postapply ARM/settings readback and running-image readiness remain **unverified**.
  No active FinOps build, timer controller or runner watchdog was found in the
  matching process metadata. Historical test shell7896 remains; its command has
  tests/diffs only, no queued cloud writes. No processes were killed.
- The exact reviewed/applied plan preserves host enabled=true, timer disabled=true,
  catalog=true and cutoff **2026-10-27T06:06:02.045288+00:00**, authenticated against
  prior host plan **ea9b870207abadb7efa6dcaf7e6b71bf762cf7cc90979bd56fb60fde9355e31c**.
  These are bound plan facts, **not a fresh completed postapply live read**.
  No timer-applied evidence was found; do not infer scheduled ingestion success.
- Bound security review: state defaultDeny/exact167.103.65.36,167.103.66.248,
  167.103.66.93; PostgreSQL publicDisabled/0firewall rules; other three app pins
  and complete settings preserved. Latest scanner exit0:96passed/0failed/1
  documented CKV_DOCKER_3 compatibility exception, not an exception-free scan.
- **Temporary resources:** newest discovered journal nonce **b2b8ad1f981b**;
  exact six IDs are in its ownership journal and the linked final evidence.
  [Last known cleanup proof](../gateway/validation/finops-fresh-final-b2b8ad1f981b.json)
  records all six GET404 at03:59:13UTC, legacy six GET404 at03:59:21UTC,
  outstanding_resource_ids=[]; no newer journal was found. This is historical
  ARM proof, **not a fresh ARM inventory**. No known outstanding deadline or
  laptop-dependent cleanup obligation remains in that proof; no watchdog was
  stopped and no arbitrary deletion was attempted.
- Source/task state preserved: existing modified Terraform apps/dev-unified/
  variables/disabled-test and ingestion Dockerfile; existing untracked FinOps
  controllers/catalog/security artifacts retained. No task file edit in pause.
  The controller and Dockerfile remain source-bound to the reviewed artifacts;
  no source fix or live-blocker remediation attempted.

**Resume only after explicit resume instruction:** first reconcile the existing
controller's final output/verification marker and fresh read-only live state.
Do not replay this applied plan, prior host/catalog stages or builds. Any later
timer-only action requires fresh sequential validation and exact saved-plan
binding under the applicable approval; pause supplies no new CLI/write approval.
Do not disable a running service for pause. Pipeline acceptance, scheduled passes,
DB/API/UI reconciliation and the overall FinOps task remain incomplete.

## Latest bounded execution — 06:17:45 UTC: built, NOT applied

**Source fixed and a new immutable ingester published. Image repair apply is
blocked, not completed; live ingestion is not healthy/accepted.** Historical
sections below describe earlier states, not the current disabled-host baseline.

- Actual ingestion-only ACR run **cm1u Succeeded**, CLI/build exit **0**, native
  Linux start06:07:10UTC/finish06:08:46UTC; tag **finops-20261027t060657z**.
  Digest **8d331a31ddfd32d25eff2665ce3f2c08380c43ed411e0a8a75819a591bda07e5**.
  Image is pocidstokenexacr.azurecr.io/aiflux-ingestion at that SHA256 digest.
  No API/admin/customer builds. No blind dependency or base-image upgrades.
- Current source SHA256 **9ec52d9535da86d02cbbbc94b24732a66fb0befa09f735e60ccb6f51dfeee6d2**;
  full manifest SHA256 **b320b7779fba5259b2565368015808111ce2ba1ea87dc824f079f5e803377f81**.
  Retained context and remote ACR run/output/manifest bindings reverified.
  Other three source manifests match the original four-image build exactly.
- Native Docker build actually ran catalog verification, Azure/psycopg imports,
  ODBC and settings checks. Exact11 enabled inventory-backed aliases and actual
  backend/provider/regions verified; Decision-1 disabled; GLM cost remains null
  in tests. Catalog SHA256 **67f1b9e218375ab2c2070014a630322458ae36d49516ddc0305dea931c86c988**.
- **133 initial /155 final tests passed**, pytest exit0, one existing Starlette
  warning. Final suite includes22 new strict single-image guard cases.
- Existing isolated Checkov3.2.495 actually ran, exit **1**:78passed/2failed,
  0skipped/parsing errors. Findings **CKV_DOCKER_2** (HEALTHCHECK) and
  **CKV_DOCKER_3** (explicit container user). No suppression, scanner bypass,
  source alteration or unvalidated replacement rebuild was performed.
- Terraform init/validate/default workspace and fresh saved plan ran. Plan
  SHA256 **d1c27329e9932e4da601eddcc7e9870f1c749665d1c73d9b8f2f6264c924a1f8**,
  one in-place Function update. Independent finite guard exited **2** with
  **requested_host_disabled_baseline_not_true**. No validation-complete marker,
  apply intent or apply exists; workflow stopped at AddValidationSteps.

**Actual conflicting baseline:** previous host plan was applied once at
05:57:58UTC, hash **ea9b870207abadb7efa6dcaf7e6b71bf762cf7cc90979bd56fb60fde9355e31c**.
Fresh readback proves host enabled=true, timer disabled=true, catalog=true and
cutoff present (existing2026-10-27T06:06:02.045288+00:00). The current task instead
requires host disabled/catalog=false/no cutoff while forbidding settings changes.
These requirements cannot all hold on this actual baseline. The guard was not
weakened; no earlier applied stage was replayed or rolled back. Current ingester
still uses the prior91c40730377a7b3bf83efe1b52e28eb84dab41ceb6adc76aac9735f1d5e03296
digest, not cm1u.

Final read-only checkpoint exited **0** and independently matches all four full
settings hashes and the protected baseline. All pins unchanged; API/admin/customer
unchanged. State defaultDeny/exact3existingIPs; PostgreSQL publicDisabled/0firewall
rules. No app configuration/DB/RBAC/network writes, runners, activation, host keys,
public API/SCM opening or manual invocation occurred in this continuation.

Evidence: [fresh checkpoint](../gateway/validation/finops-ingestion-image-only-checkpoint-20261027T061745Z.json),
[155-test JUnit](../gateway/validation/finops-ingestion-image-only-final-tests-20261027.xml),
[safe prebuild inspection](../gateway/validation/finops-catalog-inspection-20261027T060651Z.json).
Protected source/build/plan evidence is retained in the new tag's deployment
folder; existing build/applied markers were not overwritten.

The separate [single-image controller](../scripts/deployment/finops_ingestion_image_repair.py)
supports `plan`, `validate`, `apply`, `verify` with `--tag`; it does not relax the
four-image guard. Parent must reconcile the conflicting actual baseline and
scanner findings before any deployment. Existing
[activation controller](../scripts/deployment/finops_catalog_repair.py) exposes
`plan`/`validate`/`apply`/`verify` with `--stage host` or `--stage timer`, but the
already-applied host/catalog stages must not be replayed and timer must not run
from this handoff. No new boundary was selected or existing watermark reset.

## Bounded source repair (no deployment)

The ingestion package now copies the checked-in
[ingestion-specific catalog](../services/usage-ingestion/ingestion-approved.json)
to both existing ingestion catalog paths. It is checked against the reviewed
10 Foundry routes/deployments plus GLM inventory by
[the packaging verifier](../services/usage-ingestion/approved_catalog.py), not
accepted by row count. Decision-1 remains disabled; no prices are invented.
Provider/backend/region bindings retain the existing approved inventory and
[read-only APIM/account inspection](../gateway/validation/finops-catalog-inspection-20261027T051631Z.json).
The shared dev catalog and API/admin/customer Dockerfiles/source are untouched
by this repair. No activation setting, cutoff, deployed pin or cloud resource
is changed by these source edits.

The existing [build helper](../scripts/deployment/finops_live_build.py) now
supports `--component ingestion`: a fresh source-bound native Linux ingester
build only, without rebuilding other applications or applying anything. Its
default remains the prior four-component mode. The catalog release proof hashes
the actual checked-in catalog bytes, rather than a reserialized approximation.
Existing immutable build/validation artifacts are not updated into proof for
the changed source; the parent must build and validate the new package.

## Result at 05:09 UTC

**Blocked by wrong immutable ingester catalog. Not blocked by missing timer
approval or a historical-cutoff decision.** No production write was performed.
The previously applied disabled-stage plan was not reapplied.

[Actual fresh preflight](../gateway/validation/finops-activation-preflight-20261027T050908517678Z.json)
binds the configured four immutable images to successful ACR runs cm1p/q/r/s,
their current source manifests and retained build context. It independently
matches all application-settings hashes and the entire protected applied
baseline. Retained source/context binding is not running-filesystem attestation.

The ingestion Dockerfile copies the **static dev-models catalog**, while the
API's accepted model publication uses separate verified inventory. Successfully
viewing 11 models in the portal therefore does **not** accept the ingester's
11-row static catalog. The package and source are byte-identical; this is not
a stale workstation edit or a setting-path typo.

| Actual artifact | SHA256 |
| --- | --- |
| Configured ingestion image | 81b2c6a96c8a82807eb9bec6098fc305af664b55d97e44e1a3b226e8f3efd56f |
| Packaged catalog | 9b0605b95ed77b6d119e34947177a9e886f4fe1ba154fca08196a394189d3615 |
| Live unified APIM policy | 3f3ded3ec635482f4e8e61c46aa998dbb6a0d551efc8d2e47858741e423b1314 |

Only **gpt-5.6-luna** and **DeepSeek-V4-Pro** overlap.

| Missing from immutable package | Obsolete package-only alias |
| --- | --- |
| DeepSeek-V4-Flash | DeepSeek-V4-Flash-0731 |
| Kimi-K2.7-Code | Kimi-K2.6 |
| glm-5.3 | claude-haiku-5-5 |
| gpt-4o | claude-opus-5-5 |
| gpt-5.4-mini | claude-sonnet-5-5 |
| gpt-6.1-sol | gpt-5.6-sol |
| grok-4-1-fast-reasoning | gpt-6-astra |
| grok-4-20-reasoning | gpt-6-luna |
| grok-4.3 | gpt-6-sol |

Rows are independent lists, **not proposed alias mappings**. Renaming a legacy
model is not backend/provider/region acceptance. The live policy's literal
discovery membership exactly matches the existing 10 Foundry routes plus GLM;
no provider named-value/secret read occurred. Enabling catalog=true on this
package would fabricate acceptance. Ingestion source permits unmatched rows
but marks their attribution missing/cost unknown, so blindly enabling the timer
would also persist avoidably incorrect attribution.

## Authority and prospective boundary

The current user delegates the operational choice of **forward-only** ingestion.
The historical candidate2026-10-26T01:18:34.616157Z is **not** approved and was
not used. Existing156requests/11143tokens remain deferred. No replay/backfill,
watermark rewind, table seed, schema migration or permission grant is authorized.

A single fresh UTC start must be persisted after catalog acceptance and before
the host-start apply, while the timer is still disabled. That exact value must
survive the separate timer-enable stage; normal overlap must be clamped to it.
Any existing watermark must be preserved and reconciled, never reset. The
current failed package prerequisite does not justify choosing an aging boundary
now: no timestamp has been set in cloud configuration or treated as historical
approval. This does not require asking the user generic activation approval again.

## Database proof correctly reconciled

The older23667d8c9b50 outcome failed an over-broad DELETE privilege contract.
It is **not** the latest database result. The newer
[b2b8ad1f981b execution](../gateway/validation/finops-fresh-execution-b2b8ad1f981b.json)
contains successful read-only probes for ingestion03:56:11UTC and API03:58:42UTC.
The corrected contract matches the approved bootstrap minimum:

- Ingestion SELECT on usage_records, safety_events, ingestion_state,
  team_subscriptions, model_prices.
- INSERT+UPDATE on usage_records and ingestion_state; INSERT only on safety.
- No DELETE, subscription/pricing DML, DDL, ownership or elevated role needed.
- At those historical timestamps: usage0, checkpoint absent, eight price rules.

No fresh database connection or expensive temporary runner was made. These
historical snapshots are explicitly labeled, not rewritten as current DB reads.
Fresh host MI/storage/Monitor/DB readiness remains unproved.

## Current live state and security

At05:09:08UTC: FunctionDisabled/enabled=false, timerDisabled=true,
catalogConfigured=false, start absent; ARM functions discovery400. All four
pins and every settings hash unchanged. PostgreSQL publicDisabled/0firewall
rules; state account defaultDeny with exactly167.103.65.36,167.103.66.248,
167.103.66.93. All protected ingress, TLS, SCM, identities, roles and vault
baseline match the applied stage. No new resources or cleanup obligations.

Fresh existing-session customer/admin usage pages rendered updated controls and
explicitly reported **telemetry unverified**, last query success unavailable,
no last-ingested timestamp and unknown cost. This is not a pipeline acceptance
or evidence that source traffic is zero. The customer tab subsequently changed
through independent activity before a network capture; that attempt timed out
and produced no API evidence/inference. A separate fresh tab required login;
no password/session storage/key was extracted and no login was attempted.

## Work performed and exact continuation

- Added a metadata-only [activation gate](../scripts/deployment/finops_activation_preflight.py).
  It rejects duplicate/foreign/placeholder memberships, ambiguous discovery,
  policy/source/image drift and settings/security drift. It has **no write or
  apply entry point**. Membership alone never sets catalog acceptance.
- [82 initial tests passed](../gateway/validation/finops-activation-preflight-tests-20261027.xml);
  [final expanded 178 tests passed](../gateway/validation/finops-activation-final-tests-20261027.xml),
  zero failures/errors/skips, one existing Starlette warning. No editor errors. Existing four application
  manifests still match; no source in any deployed image was edited.
- No Terraform plan/apply, host start, timer enable, manual trigger, inference,
  build/push, role/network change, schema/data write or probe retry occurred.
- Azure MCP helper returned403; official troubleshooting and Functions
  identity/storage/settings documentation were consulted. Existing authenticated
  CLI/ARM with the exact tenant/subscription and strict corporate CA succeeded;
  no transport validation was disabled.

**Required repair:** produce an ingestion-specific accepted catalog with the
existing approved 10 Foundry+GLM alias/backend/provider/region bindings, package
and test it in a new immutable ingester image, then separately validate that
image-only correction. Preserve API/admin/customer pins and all other protected
configuration. Do not invent prices or rename stale entries into acceptance.
The user explicitly authorizes this ingestion container/configuration correction;
this bounded source task does not build, promote or apply it. Once the new
immutable package prerequisite passes, execute
the already-authorized fresh host-only and then timer-only finite saved-plan
stages, preserving the prospective boundary, and observe two **scheduled**
successes plus persisted scoped DB/API/UI reconciliation. No old validated
GLM/disabled-stage proof may authorize those new plans.