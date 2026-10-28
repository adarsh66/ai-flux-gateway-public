# FinOps implementation and live diagnosis — 2026-10-27

## Status

### FINAL: LIVE DATA — scheduled ingestion and both portals accepted, 09:22 UTC

**The bounded forward-only live-data task is complete.** This status supersedes
all paused, disabled, blocked and runtime-unverified statuses below; those remain
historical audit records, not instructions to restart, redeploy or reapply.

- Actual scheduled checkpoint successes at **09:10:00.191316** and
  **09:15:00.834012 UTC** advanced the watermark by **300.642696 seconds**.
  A further database-backed healthy checkpoint at **09:20:00.411048 UTC**
  was observed, with last scoped row ingested **09:20:04.593966 UTC**.
- Authenticated **admin and customer** APIs and rendered charts are nonempty.
  Same fixed UTC window: admin all-organizations **22 requests / 2,807 tokens**;
  customer Caldova **20 / 2,807**; admin filtered to Caldova **20 / 2,807**.
  All returned rows fit one page and their input/output sums reconcile:
  **1,080 + 1,727 = 2,807**, including **GLM 1,524 tokens**, across nine
  nonzero models. Two extra admin-only requests have unknown model/zero tokens.
- **Hourly and Daily controls actually exercised in both portals**, not inferred
  from source. Exact table/stack totals: UTC06h **103**,07h **1,158**,08h
  **1,546**; daily2026-10-27 **2,807**. Final uninstrumented full reloads at
  **09:22:33 UTC** reconfirmed admin22/customer20,2,807tokens and nine nonzero
  chart segments each. Customer has no organization selector; backend source
  binds its usage queries to the authenticated principal's organization.
- **Financial data quality remains incomplete, not billing-ready:** cost is
  **Unknown**, not zero. Caldova labels are19 `price_missing` and1
  `status_missing`; do not invent prices or claim every row lacks backend
  attribution. Catalog approval does not establish effective-dated prices or
  complete per-request metadata. All20 have measured token components.
- Timer enabled, Always On true, host Running, current d2bdae image and cutoff
  **2026-10-27T06:06:02.045288+00:00** remain protected. Full baseline/all four
  settings hashes were verified **09:14:24 UTC**. Fresh **09:21:27 UTC**
  security readback confirms PostgreSQL publicDisabled/0firewall rules and
  state storage defaultDeny/exactly3approvedIPs. No manual inference, timer
  invocation, build, deployment, configuration/DB write, new runner, reset or
  backfill; normal scheduled worker writes continue. Historical156requests
  remain deferred. Prior cleanup proof is retained, not claimed freshly queried.
- Existing164-test regression evidence is retained; no suite rerun or new test
  framework in this read-only UI acceptance. Existing Always On ARM-versus-
  Terraform provenance deviation remains disclosed in the activation audit.

Evidence: [final aggregate acceptance](../gateway/validation/finops-live-final-acceptance-20261027.json),
[scheduled checkpoint proof](../gateway/validation/finops-scheduled-checkpoint-acceptance-20261027.json),
and [activation audit](finops-activation-20261027.md).

### Current resumed diagnosis — 07:24 UTC

The cm1v/d2bdae image is applied and observed running; older built/not-applied
statuses below are historical. Timer remains disabled with the original cutoff.
Two diagnostic-controller defects are fixed: Storage authorization was mislabeled
as Monitor failure, and the HTTP readiness trigger was invoked through an
incompatible non-HTTP admin-input route. Existing-private SCM execution is403;
actual MI Monitor/PG readiness and storage remediation remain unverified. No new
images, runners, roles, network openings, DB writes or timer activation.
Fresh roles/workspace/identity metadata and all six preparation2be1b356c1dd
GET404s verified. See [current evidence and next gate](finops-activation-20261027.md#current-resumed-diagnosis--2026-10-27-0724-utc).
Final102tests pass; temporary logging baseline restored07:27:13UTC; full protected
applied-release baseline/complete settings readback passes07:28:23UTC. No guard
relaxation or live application configuration change remains from this diagnosis.

### Latest: corrected image built; exact image-only apply blocked — 06:17 UTC

Actual ingestion-only ACR **cm1u Succeeded**, tag finops-20261027t060657z,
digest8d331a31ddfd32d25eff2665ce3f2c08380c43ed411e0a8a75819a591bda07e5;
native Linux catalog/import/settings checks passed.155 focused tests pass.
Source fixed/new immutable image exists, **not applied and not live healthy**.
Fresh saved plan d1c27329e9932e4da601eddcc7e9870f1c749665d1c73d9b8f2f6264c924a1f8
contains one Function update but strict guard exit2: actual host already enabled,
catalog=true/cutoff present from the05:57:58 applied host plan. Current bounded
task demands disabled/catalog=false/no cutoff and prohibits settings rollback.
Checkov also reports78pass/2findings (HEALTHCHECK/explicit user), exit1; no bypass.
No apply intent, settings/DB/RBAC/network writes, activation or old-plan replay.
Fresh06:17:45 readback verifies all pins/full settings hashes/security unchanged,
timer disabled=true, PostgreSQL publicDisabled/0rules and stateDeny/exact3IPs.
See [current exact evidence and parent handoff](finops-activation-20261027.md#latest-bounded-execution--061745-utc-built-not-applied).
The following older statuses are historical, not the current live baseline.

### Latest: activation gate executed; immutable catalog mismatch — 05:09 UTC

**This is an actual package-content blocker, not missing timer approval or an
unresolved historical cutoff.** The current user delegates **forward-only**
activation; the 156 historical requests / 11,143 tokens remain deferred. A new
UTC boundary must be persisted after acceptance and before host startup, then
preserved through timer activation. No historical boundary is approved, no
watermark reset is allowed, and no boundary was prematurely selected while
the package gate fails.

Fresh read-only preflight at **2026-10-27T05:09:08 UTC** reverified all four
successful ACR run/digest/source bindings, every application-settings hash and
the complete applied protected baseline. **The ingester's packaged static
catalog does not match the live gateway:** only gpt-5.6-luna and DeepSeek-V4-Pro
overlap; nine approved aliases, including GLM, are missing. Both sides contain
11 models, so a count-only check would falsely pass. Packaged catalog SHA256
9b0605b95ed77b6d119e34947177a9e886f4fe1ba154fca08196a394189d3615;
live unified-policy SHA256
3f3ded3ec635482f4e8e61c46aa998dbb6a0d551efc8d2e47858741e423b1314.
Setting catalog=true would assert acceptance of the wrong package and cause
missing/misleading backend attribution. The current immutable image cannot be
corrected by changing that Boolean. **Configured images were preserved.**

Function remains **Disabled**, timer disabled=true, catalog=false, start absent;
ARM discovery400. No disabled-stage reapply, host start, timer enable, builds,
runner resources, SQL writes, role/network changes, provider secret reads or
new inference calls were performed. PostgreSQL public Disabled/0firewall rules,
state defaultDeny/exact3existingIPs, identity/SCM/TLS and all settings preserved.
82 initial focused tests pass; final expanded **178 tests pass, 0 failures,
0 errors, 0 skips**, one existing warning; no editor errors. Runtime health
and scheduled successes remain **unproved**, not passed by source tests.

Importantly, the **03:56/03:58 UTC** private probes supersede the older failed
grant diagnostics below: both MIs passed; ingestion has SELECT on all five
tables, INSERT+UPDATE on usage/checkpoint, INSERT on safety, no DDL/ownership;
checkpoint absent and usage0 at those historical read times. No grants needed.
Fresh portal reloads displayed the new hourly/daily controls and explicitly
unverified telemetry/no last success/unknown cost, not healthy zero traffic.
The original customer tab subsequently changed through independent activity;
no request was sent by this continuation. A separate fresh tab required login;
no credentials/session material were extracted or copied.

See [exact activation blocker and recovery boundary](finops-activation-20261027.md),
[actual metadata proof](../gateway/validation/finops-activation-preflight-20261027T050908517678Z.json)
and [final 178-test results](../gateway/validation/finops-activation-final-tests-20261027.xml).
The required next artifact is a **corrected immutable ingestion package** bound
to the existing approved 10 Foundry + GLM aliases and actual backend routing;
that image replacement is outside the requested finite settings-only/image-
preserving activation. No replacement was silently built or deployed.

### Previous: disabled runtime stage applied; activation not performed — 04:58 UTC

Exact four-update saved plan applied once at 04:53:24 UTC; all four immutable
pins and protected baseline verified. Function host/timer remain disabled,
catalog remains false, cutoff absent. No rebuild/probe/network/RBAC/database
writes. Terraform apply exited0; encompassing task exited2 during initial
provider-registry readback only. Corrected read-only verification exited0 with
70 focused tests passing. All three web-app settings hashes unchanged. Function
discovery HTTP400; runtime/ingestion/API/UI acceptance not claimed. Historical
sections below are retained, not current deployment status. See the
[completed disabled-stage report and activation handoff](finops-disabled-stage-20261027.md)
and [bound actual evidence](../gateway/validation/finops-disabled-stage-applied-20261027t0457z.json).

### Offline session-proof follow-up — source defect confirmed, no live retry

Startup sets `search_path=public,pg_catalog`; the previous exact tuple demanded
`public, pg_catalog`. Real psycopg/libpq offline contracts reproduce the false
rejection and the retained corrected image's exact 189-byte failure. The source
now accepts **only these two equivalent spellings** and emits finite per-field
session reasons through both sanitizers. Identity/schema/read-only/no-DDL/grant
requirements are not relaxed. Existing test and Linux synthetic cursors masked
the bug by inventing the spaced value; the Linux contract source is corrected,
but no rebuild ran. Actual historical returned values remain unknown; a second
distinct failed invariant reproduces the same old output. **No new cloud call,
DB connection/write, build, provisioning or retry. This fix is source-only.**
Stop the costly runner loop. FinOps remains unverified until the required MI
database-role mapping, schema access and effective least-privilege grants are
verified using an existing approved DB path, followed by actual ingestion/API/UI
acceptance. This is not a request for fresh generic runner approval or a proposal
to broaden grants. See the [exact invariant/type table and actionable DB review](finops-probe-offline-rootcause-20261027.md#follow-up-confirmed-session-predicate-defect-source-only-fix).

### Corrected immutable probe executed once per MI — readiness blocked, cleanup verified

**2026-10-27 03:11 UTC:** the newer scoped approval was executed. Probe-only ACR
build `cm1j` passed exact pinned Linux native/CA/MI/JWT/numeric/two-sanitizer
validation (2CPU,37.956779s,80,929,306 compressed bytes). Fresh scanner passed
3ARM+64Dockerfile checks; 397 final regressions passed. New isolated runtime
`3788be5dd201` ran both MIs once, sequentially, with zero restarts. Both returned
189-byte finite JSON: `database_session` / `ProbeBlocked` /
`database_session_proof` / null SQLSTATE. No permission-denial inference:
individual failed session invariant and all later grants/aggregates remain
unknown. All six temporary resources were deleted and independently GET404
verified, both old sessions also absent; all old watchdogs preserved. PG public
Disabled/0rules and state defaultDeny/existing3IPs preserved. No retry, DB write,
timer, replay, config or application deployment. Observed-duration retail
subtotal USD0.01311135 is not an invoice; USD1.778895 planning scenario is not a
cap. **FinOps is not repaired.** See the
[latest corrected outcome and finite next steps](finops-probe-offline-rootcause-20261027.md)
and [bound outcome evidence](../gateway/validation/finops-corrected-outcome-05a9ff859f48.json).

### Historical offline probe defects reproduced and fixed — 02:52 UTC

**2026-10-27 02:52 UTC:** offline review of session `9461fb0c1a35` reproduced a
definite driver/serialization defect: PostgreSQL `SUM(bigint)` becomes psycopg
`Decimal`, serialized as strings and rejected by the integer-only supervisor.
The retained old source reproduces the exact **130-byte / same SHA-256** result
seen for both MIs. An unrelated swallowed exception produces the same output;
**the actual historical stage/root cause remains unknown, not SQL success**.
Source now converts integral numeric aggregates losslessly and preserves only
finite stage/exception/guard labels across both sanitizer boundaries. Exact
retained pure-wheel identity/MSAL/PyJWT contracts pass with sockets forbidden.
**390 offline tests pass; four changed Python files compile; no editor errors.**
No image build/push/remote validation or new runner/provisioning occurred. The
source fix is **not deployed**; the old digest does not contain it. Main review
and verified updated immutable image are required before considering any new
runner. Existing final evidence still records **no outstanding IDs**. See the
[offline investigation and remaining gates](finops-probe-offline-rootcause-20261027.md)
and [bound evidence](../gateway/validation/finops-probe-offline-rootcause-20261027.json).

### Current fresh session — probes executed; readiness blocked; cleanup verified

**2026-10-27 02:40 UTC:** fresh nonce `9461fb0c1a35` actually created and
deleted **six resources**: the four dedicated network objects and two strictly
sequential, single-identity ACI groups. **No resources remain outstanding.**
This is not a repaired-ingestion or successful database-acceptance claim.

- Every name/ARM ID, **including subnet
  `poc-ids-token-ex-finops-probe-9461fb0c1a35-subnet`**, is disjoint from the
  original session below. The same approved `10.240.5.0/24` purpose was used only
  after independent GET404 of all six original IDs and fresh CIDR checks.
- [Fresh preparation](../gateway/validation/finops-fresh-preparation-9461fb0c1a35.json)
  verified the exact subscription/tenant/region/account, quota/provider, both MI
  client/object/tenant bindings and existing registry `AcrPull`. ARM validation
  passed; network what-if was **exactly four Creates**, no existing Modify/Delete.
  Both single-MI group validations/what-ifs also passed. Checkov: 3 ARM and 47
  Dockerfile checks passed, no failed/skipped/parsing errors.
- Reused the existing `cm1h` Linux-validated image, digest
  `fdf8e46ed2f91f3614a456e7261fb5cd77332e65b526dbec08430041bd100cef`.
  Current entrypoint/probe/dependency context and live manifest/build digest
  bindings were verified before execution and again afterward. **No rebuild.**
  The existing conservative USD **0.778895 + 1 contingency = 1.778895** scenario
  was retained; it includes an already-built image allowance and is neither a
  fresh billing quote nor a hard cap.
- New detached watchdog PID **2608**, session hash
  `9350a426a8a8aa945f257e1d885c1c3b4c0fc215297253fd2804560a90718cbf`,
  attested exact fresh IDs and controller/guard hashes before the first PUT.
  Deadline **03:35:11 UTC**, cleanup trigger **03:27:11 UTC**. A fresh actual
  detached-process synthetic cleanup test passed before provisioning; this is
  not proof against workstation power/network loss. Original PID **10156** was
  preserved, still bound only to old IDs, with no overlapping subnet name.

| Actual runtime result captured before deletion | Ingestion MI | API MI |
| --- | --- | --- |
| Sanitized ARM log collection UTC | 02:37:17 | 02:38:28 |
| State / OS exit / restart count | Terminated / 0 / 0 | Terminated / 0 / 0 |
| Nonempty parseable log JSON | 130 bytes | 130 bytes |
| Probe acceptance / status | 2 / blocked | 2 / blocked |
| Exact exposed reason / SQLSTATE | unverified_runtime_failure / null | unverified_runtime_failure / null |
| Deleted; independently GET404 UTC | 02:37:18 | 02:38:29 |

The ingestion group was GET404 **before API creation**. Each probe ran once,
under a ten-minute bound; neither was retried. The JSON, byte length, hash,
image/source/session bindings were persisted and printed **before each DELETE**
in [execution evidence](../gateway/validation/finops-fresh-execution-9461fb0c1a35.json).
Unlike the original failure, result collection completed for both identities.
**OS exit 0 is not SQL proof.** The supervisor intentionally hides internal error
details; these logs expose neither a specific finite SQL guard nor SQLSTATE.
It is therefore not possible to classify this as a permission/grant failure or
to assert DNS/TLS/MI/database-session success. No grant was attempted.

Finally cleanup deleted subnet → NSG → NAT → public IP, then independently
GET404-checked all six fresh IDs by **02:38:35 UTC**. A separate
[final GET-only verification](../gateway/validation/finops-fresh-final-9461fb0c1a35.json)
reconfirmed all six fresh IDs absent at **02:40:16 UTC** and all six original IDs
absent at **02:40:22–23 UTC**. Both watchdogs remained active; the fresh cleanup
marker prevents replay. PostgreSQL public access Disabled/rules 0 and state
default Deny/all three approved IPs were read back unchanged at **02:40:33 UTC**.
The original deletion proof below was not overwritten.

**Readiness remains unaccepted; database aggregates/checkpoints/grants are unknown,
not zero.** The ingestion destination was constructed inside the reviewed probe;
it is not evidence that the disabled production Function is configured. Current
API/ingestion/admin/customer source hashes still match the earlier offline
manifest. No DDL/DML, recovery, inference, timer enablement, Function settings,
app release, new RBAC or existing network expansion was performed. Any production
Function configuration requires a precise explanation and separate consent before
editing. No image was promoted automatically.

Validation: **145 focused tests passed** before provisioning; **309 expanded
backend/contract tests passed** after cleanup (one existing deprecation warning),
retaining legacy regressions. [Focused JUnit](../gateway/validation/finops-fresh-focused-tests-20261027.xml),
[expanded JUnit](../gateway/validation/finops-fresh-expanded-tests-20261027.xml).
No live database acceptance or UI validation is implied by these tests.

### Historical original session cleanup — evidence preserved

**URGENT owned cleanup completed at 02:25–02:26 UTC.** The later approved live
execution really created **five resources**, nonce `2f75015b55d1`; the earlier
zero-create paragraphs below are historical, not the current resource state.
Only the ingestion ACI was created; the API ACI was never created.

| Actually created and deleted, in dependency order | Exact name | Final independent ARM GET404 UTC |
| --- | --- | --- |
| ACI | poc-ids-token-ex-finops-probe-2f75015b55d1-ingestion | 02:26:17.095765 |
| Subnet under existing poc-ids-token-ex-vnet | poc-ids-token-ex-finops-probe | 02:26:17.272774 |
| NSG | poc-ids-token-ex-finops-probe-2f75015b55d1-nsg | 02:26:17.356978 |
| NAT gateway | poc-ids-token-ex-finops-probe-2f75015b55d1-nat | 02:26:17.453073 |
| Public IP | poc-ids-token-ex-finops-probe-2f75015b55d1-pip | 02:26:17.560106 |

Full exact IDs, nonempty observed first deletion proof and original OS exit are
in [deletion evidence](../gateway/validation/finops-owned-deletion-proof-20261027.json).
The [subsequent absence-only reconciliation](../gateway/validation/finops-owned-cleanup-20261027.json)
contains actual ARM GET events for all six IDs including the never-created API
group. **Outstanding IDs: none.** No owned NAT/public-IP resource remains to incur
ongoing resource charges; historical usage charges are not claimed zero.
First deletion finished 02:25:50 UTC; all-six GET404 proof was repeated at 02:26:17 UTC.

Original execution/cleanup exited **2 / published_ports**: an exact dictionary
comparison rejected legitimate ARM private-IP readback fields. The guard now
accepts null/omitted metadata or Private/no-ports metadata with an optional valid
IPv4 inside only `10.240.5.0/24`; public addresses, IPv6, foreign CIDRs, listeners
and unknown fields remain rejected. Nonce/tags, baseline/write-intent journal,
exact IDs, single MI, immutable image and reviewed command/source hash checks
were not bypassed. All 94 focused tests passed before deletion; the final suite
passed **95 tests**, including the subsequent evidence-retention regression, in
[the focused test artifact](../gateway/validation/finops-owned-cleanup-tests-20261027.xml).
The current terminal ARM readback had **no ipAddress field** after termination;
the earlier rejected private-IP object itself was not persisted, so its exact
contents must not be invented.

Actual ingestion container: **Terminated, OS exit 0**, restart count 0, ran
02:22:35.495–02:22:40.488 UTC. This is **not** validated private SQL/probe acceptance:
the original controller never collected a sanitized probe result; API phase did
not run. No probe retried and no new resources provisioned during cleanup.
The applied rule was TCP 19390 from `10.240.0.0/16` to `10.240.5.0/24`, priority
100, followed by deny-all priority 200; it disappeared with the owned NSG.

Watchdog PID **10156** remains active, not killed or replaced; its original
cleanup trigger is 03:12:09 UTC before the 03:20:09 UTC deadline. It only targets
the same six hash-bound IDs, now absent. No provision/controller process remains.
The cleanup marker prevents the original session from creating anything later.
At 02:26:31 UTC preservation readback confirmed PostgreSQL public access Disabled,
zero firewall rules, state default Deny and all three existing approved IPs intact.
No parent VNet, DNS, MI, registry artifact, app, state-IP rule, database data,
timer or image/app release was modified. Do not resume provisioning in this
cleanup continuation; any later probe execution needs fresh collision/preview,
source/image and independent watchdog gates, not a replay of the failed session.

### Historical preprovision attempt

**Latest approved runner execution attempt (01:25–01:29 UTC):** the dedicated
network and both distinct MI attachments were explicitly approved. Fresh scope,
CIDR/no-collision, subnet-purpose, ACI provider/region/quota and existing security
reads completed. **No resources were provisioned:** approved deny-all ingress has
not been established compatible with ACI's documented platform management port
19390 requirement. The missing Standard NAT price was found under the public-cloud
Global meter (USD 0.045/hour and 0.045/GB); one-hour ACI+NAT+IP fixed subtotal is
USD 0.108895, not all-in or a billing cap. The later collector pricing step failed;
a focused diagnostic returned HTTP 429, without automatic retries. All-in
build/storage/transfer estimation remains incomplete. Neither a platform-port
exception nor another service/topology was silently authorized or created.

Independent exact ARM GETs confirmed **all six reserved IDs HTTP 404 at 01:29
UTC**, not an inventory-only cleanup assertion. Created/deleted 0/0; no identity
attachment, image build, SQL snapshot, replay, timer or app release. Actual **238
backend/contract tests passed**, including 31 new runner guards; cleanup tests are
synthetic, **not an installed/tested independent cleanup deadline**. Prior 103 UI
results remain historical. Both MI database proof/aggregates and activation cutoff
remain unverified/null. See the [approved proposal execution result](finops-private-runner-proposal-20261027.md)
and [exact sanitized evidence](../gateway/validation/finops-runner-preflight-20261027.json).

**Latest storage-access continuation:** one explicitly approved cloud change was
made: add only `167.103.65.36` to the state backend account. Exact ACL readback and
Entra container-existence metadata both succeeded at **01:00 UTC**, reconfirmed
at **01:09 UTC**. No state was downloaded or planned/applied. Current focused
backend suite: **207 passed** (205 retained plus two narrow reconciliation tests);
103 UI tests remain prior evidence, not rerun. No runner was created: the
[exact private-runner proposal](finops-private-runner-proposal-20261027.md) records
the network/identity/cost/lifetime scope and concrete separate network-change gate.
Runtime MI database evidence, cutoff and production remediation remain blocked.
[Current sanitized execution evidence](../gateway/validation/finops-state-access-20261027.json).

The following implementation/private-execution sections describe the earlier
zero-cloud-write continuations; their two-IP/denied-state observations are
historical, superseded only for state access by the executed approval above.

Source implementation and focused validation completed; **not deployed**.
Latest continuation: **205 backend/contract tests pass**, including the original
142 plus 63 new private-diagnostic/release-guard cases. Previous Linux validation
of 103 UI tests, all three TypeScript workspaces and two portal builds remains
historical evidence for the unchanged UI source; it was not rerun in this continuation.
Production ingestion/recovery and end-to-end dashboard acceptance remain blocked
by unverified private PostgreSQL readiness, subscription ownership and activation
cutoff. No Terraform apply, app-setting write, timer enablement, policy change,
database write, backfill, inference request, network expansion or RBAC change was
performed in this continuation. Existing concurrent GLM/deployment changes were
preserved. Never replay a previous release/apply to resume this work.

## Fresh live evidence (00:13–00:27 UTC)

| Stage | Actual evidence | Interpretation |
| --- | --- | --- |
| Gateway → Log Analytics | Last-30-day query succeeds, no partial result. 150 `aiflux` / `chat` requests, all within 48 hours; 97 contain traces. Matching retained data is dated October 26. | Real source traffic exists. No claim of 30 days of recoverable usage. |
| Usage metadata | Both gateway and LLM table schemas exist. 96 usage events have `finops-v1` and both counters, including 7 GLM events; known input 3,070 and output 2,326. | Existing provider-neutral metadata contract works. These source-event aggregates are **not** reconciled billing or deduplicated database totals. |
| Ingestion runtime | App state `Disabled`, timer disabled, image `PYTHON\u007c3.11` rather than verified ingestion container; database/workspace/APIM/product/cutoff settings absent. Function discovery returns HTTP 400. | **First proven pipeline break:** no configured/enabled native ingestion service. Available Azure resource health does not imply a functioning timer. |
| API runtime | Running, private public-network setting, PostgreSQL destination `turnstile`, product `aiflux`, catalog-configured false. | Suspected deployed product mismatch is **not proven**: current API product matches retained traffic. API catalog acceptance must not be blindly enabled. |
| PostgreSQL | Workstation DNS does not establish a private route; collector refuses public destination and never authenticates. | Actual row/checkpoint/ownership aggregates and API↔ingester schema equality remain **unverified**, not zero. Missing ingester destination is not proof of two different live databases. |
| Existing private API path | Admin SCM initially timed out; later command transport returned HTTP 200 / exit 0 but no validated three-digit health response. | Neither private `/health` success nor authenticated dashboard acceptance is established. No raw SCM output is published. |
| State storage | ACL default Deny; exactly the existing authorized 167.103.66.248 and 167.103.66.93 rules. HTTPS egress discovery returned HTTP error. | No firewall change. Current egress/backend readability is not asserted. |

Installed image pins remain:

- API: `b123162c32f24c5d565d8472c3777c293b93d218ba3d483c95bc6b73760c1171`
- Admin: `36a78667cbbc2c57a41c93181184c4a94cd7178673b6ce868abf2d281a67ae30`
- Customer: `e77a533672eaecd4936818d1c764e051ca30310027146e942c2029d075ce6560`

## Source changes audited and completed

- [finops.py](../services/control-plane/src/aiflux/finops.py): explicit UTC hour/day
  model aggregation, half-open windows, 744-bucket rejection rather than silent
  downsampling, known input/output components, fully measured totals and missing
  coverage; read-only checkpoint/scoped-ingestion freshness.
- [app.py](../services/control-plane/src/aiflux/app.py),
  [schemas.py](../services/control-plane/src/aiflux/schemas.py): admin model-token
  endpoint with optional organization/subscription scope; customer scope remains
  principal-derived. Customer/admin read-only usage health endpoints. Summary,
  CSV and chart use the same validated explicit window.
- [UsagePage.tsx](../packages/ui/src/pages/UsagePage.tsx),
  [ModelTokenChart.tsx](../packages/ui/src/components/ModelTokenChart.tsx),
  [client.ts](../packages/ui/src/client.ts), [types.ts](../packages/ui/src/types.ts):
  shared admin/customer stacked model chart, explicit Hourly/Daily UTC selector,
  manual refresh, stable range anchor, stale request keys, scoped admin fetch,
  accessible keyboard/data table, known input/output split, selected bucket total,
  partial edge labels. Unverified or wholly unmeasured buckets are not described
  as measured zero; healthy idle buckets may be zero. All eleven models remain
  separate; 744 hourly buckets are tested.
- [turnstile_exchange.py](../services/control-plane/src/aiflux/turnstile_exchange.py)
  and [TokenExchangePages.tsx](../packages/ui/src/pages/TokenExchangePages.tsx):
  credit/showback displays use recorded USD prices rather than fabricated fallback
  rates. Unpriced or non-USD coverage makes remaining credits/utilization unknown;
  known cost is a lower bound. **Legacy enforcement economics intentionally remain
  separate and unchanged**, pending business approval. Budget and credit-summary
  periods retain their existing semantics (all-time budget versus selected-days
  summary); full accounting-period harmonization is not claimed.
- [finops_diagnose.py](../scripts/deployment/finops_diagnose.py): allowlisted settings,
  schemas/aggregate traces, bounded existing-private-path probes, image/ACL metadata;
  no raw DSNs, settings dumps, tokens, prompts, headers or trace rows persisted.
- [finops_replay.py](../scripts/deployment/finops_replay.py): **dry-run only**, last-30-day
  and activation-cutoff guards, delay bound, deterministic overflow subdivision,
  partial-result failure, canonical resource/correlation dedup, unresolved ownership
  reporting, no forward watermark rewind and no write mode. Live dry run returned
  expected blocked exit 2: verified cutoff/source configuration required. It did
  not query recoverable request rows or invent an activation timestamp.

No speculative product/filter/parser/policy repair was applied: live product and
typed trace evidence did not justify one. No Functions configuration was edited.

## Verified tests

- **142 Python/unit/contract tests passed** (23.01 seconds), including existing
  ingestion/usage/filter/model-token/credit/control-plane/publication/policy tests
  and new replay/health/partial-total/currency/provider-neutral dedup regressions.
  [JUnit evidence](../gateway/validation/finops-focused-tests-20261027.xml).
- SQL Server and PostgreSQL query-compilation regressions pass; SQLite exercises
  real API/query behavior. **No live PostgreSQL integration test ran.**
- Python compilation passed for the implementation and diagnostic/replay modules;
  editor diagnostics report no errors on checked changed files.
- Approved ACR **validation-only**, no-push Linux run `cm1g` succeeded at
  00:23:14 UTC: all three workspace TypeScript checks, **103 UI tests in 12 files**,
  both portal production builds. Source manifest hash:
  `6d4c6d4082d408bf4c383c150780a6861462f5086b72a46607b6beac843db075`.
  Earlier pre-disconnect run `cm1f` failed one stale warning-text assertion;
  that failure was reproduced from its log and corrected before `cm1g`.
- Scoped whitespace checks pass. Build reports existing >500 kB chunk warnings
  and npm audit findings (1 moderate, 1 high, 2 critical); no blind dependency
  upgrade or claim of vulnerability remediation.

Local generic terminals repeatedly produced no output; VS Code task terminals
provided verified command exits. New tasks were appended after reading concurrent
task contents. Initial process inspection found old provider child processes but
no active Python/Node/Terraform command parent; none were killed. Final nonpaged
audit found no active Python/Node/Terraform/Functions process. An earlier diff
display opened a pager; a separate nonpaged diff/whitespace audit completed.

## Remaining release gates (do not skip)

1. Establish an **existing approved private execution path** to `turnstile` and
   collect read-only schema/search-path, row/checkpoint, ownership and price
   aggregates. Do not enable public PostgreSQL, widen SCM/storage ACLs or add RBAC.
2. Verify ingester MI database DML/no-DDL, Monitor and host-storage permissions,
   accepted catalog and exact image packaging. A resource-health Available result
   is insufficient. Determine approved activation cutoff from actual ownership
   history, not the current time or arbitrary 30-day start.
3. Explain/review the precise Functions configuration plan before editing:
   verified same database/workspace, active product, accepted catalog, private
   ingress preserved, immutable image, initially disabled timer. No generic
   Terraform plan may accidentally restore public ingress or unrelated drift.
4. Fresh release validation workflow and exact saved-plan image/config guards
   are mandatory. Do not reuse the completed GLM validation status or pins as a
   FinOps approval. No new FinOps applyable plan was generated here.
5. Execute bounded metadata-only replay dry run after these prerequisites, review
   ownership/cutoff/retention totals, then implement separately gated transactionally
   safe write recovery with independent cursor/worker coordination. Current tooling
   deliberately cannot perform production writes.
6. Only after guarded release: bounded authorized Foundry/GLM acceptance, one
   subsequent real timer pass, exactly-once DB→API→customer/admin reconciliation,
   authentic browser sessions and reload. No live repaired-dashboard claim until
   those checks succeed. Auto-polling and authoritative disabled/error health need
   verified ingester evidence; current runtime DTO conservatively reports
   healthy/stale/unverified from persisted checkpoints, not guessed settings.

  ## Private-execution continuation — 2026-10-27

  Latest collection started **00:48:48.280709 UTC**. The subscription and tenant were
  checked against the requested values. Azure best-practice guidance and AppLens
  were consulted; AppLens returned diagnostic categories but no specific root-cause
  insight, so its response is not represented as a repair or successful timer test.

  ### Existing paths actually investigated

  - Live resource inventory contains **zero VMs, ACI container groups or Container
    Apps jobs** in the requested resource group. [The operator design](operator-runner.md)
    is explicitly undeployed/unapproved and refers to a different historical
    subscription. [The SQL runner](private-sql-runner-execution.md) was deleted
    after its earlier SQL Server task; it is not an existing PostgreSQL execution host.
    No runner was created, started, registered or recreated.
  - API, admin, customer and ingestion apps have the existing App Service VNet
    integration. The API remains Running/private and the ingester Disabled/private
    with `PYTHON|3.11`. All three installed API/admin/customer digest pins above were
    **read back unchanged**, rather than assumed from the old report.
  - API and ingester SCM remain Deny/use-main with no explicit Allow rule. Customer
    SCM remains Deny. **Admin SCM actually has default Allow, use-main false and one
    explicit Allow rule**; this preexisting configuration was observed, not changed
    or attested as a secure deny-all baseline. A future release must preserve/review
    the actual baseline, not silently rewrite it.
  - Fixed `/health` and `/ready` GET commands through existing admin SCM returned
    command transport HTTP 200 / exit 0 **without a valid HTTP status in output**.
    Both are explicitly **unverified**, not successful application/DB readiness.
    No arbitrary commands, environment dumps, files, logs, MI tokens or credentials
    were retrieved from the host. The disabled Function's existing function-key
    protected ingestion-readiness route is not a usable approved bypass; it was not
    enabled, invoked with retrieved keys or exposed publicly.
  - PostgreSQL remains **publicNetworkAccess Disabled with zero firewall rules**.
    Workstation DNS is outside the approved private endpoint subnet, so no database
    authentication was attempted. VNet integration metadata alone is not DB proof.
  - An authentic customer Usage-page reload completed with the existing session:
    last-30-day selection shows 0 requests, 0 input/output, no token usage and no
    last-ingested timestamp. This is tenant-scoped displayed evidence, **not an
    independent database aggregate, ingester-health or repaired-dashboard result**.
    Admin Usage redirects to sign-in; no password or authentication-state extraction
    was attempted. A preexisting inline-style CSP warning was observed; no CSP
    weakening or unrelated UI repair was made.

  ### New factual retention and permission evidence

  - API workspace GUID matches `poc-ids-token-ex-logs`. Workspace retention is
    **30 days**; both `ApiManagementGatewayLogs` and `ApiManagementGatewayLlmLog`
    report **30-day interactive and total retention**, Analytics plan. This confirms
    retention configuration, not 30 days of traffic or an approved recovery cutoff.
  - Current attached API MI: client `f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1`, object
    `4e7b70ed-9868-47ba-9b61-304f1e1fdd89`. Current attached ingester MI: client
    `e1d25c87-9df1-4225-9744-ce22121cf462`, object
    `edbfc3e2-a8e5-4652-9bb0-311233756d42`.
  - Ingester role-assignment metadata at the target account/workspace or ancestor
    scopes includes Log Analytics Reader, Storage Blob Data Owner, Storage Queue
    Data Contributor and Storage Table Data Contributor. API has Log Analytics
    Reader and Storage Table Data Contributor at the checked scopes. These are
    **existing assignments, not new grants or successful MI data-plane probes**;
    PostgreSQL table grants and ingester runtime authentication remain unverified.
  - State storage `projpoctokenex` remains default **Deny**, with exactly the two
    original IP rules. An Entra-authenticated **container-existence metadata read**
    of `tfstate` actually failed, CLI exit 1, classified `network_rule_denial`.
    No state blob content was fetched/listed, no plan was generated and no lease
    was acquired. The error does not establish a PostgreSQL routing or RBAC fault.
    The Azure troubleshooting guide was consulted; subscription/tenant were already
    correct, and no new login, firewall or role change was used as a workaround.

  ### Source tooling completed (not remotely installed or executed)

  1. [finops_private_probe.py](../scripts/deployment/finops_private_probe.py) is an
     independent existing-host probe. It requires the already-attached MI, verifies
     selected token tenant/object/audience in memory, then lets PostgreSQL validate
     that token. It rejects operator/password fallback, unknown destinations/options,
     non-private addresses and unverified TLS. Connections pin a validated address
     in `10.240.3.0/24` while retaining hostname certificate verification.
  2. Its snapshot is repeatable/read-only with statement/lock timeouts and unconditional
     rollback. It checks actual database/session/schema/search path, effective table
     SELECT/DML flags, runtime elevation/DDL/ownership, row/known-token/measured-token/
     unpriced aggregates, checkpoint, subscription-binding dates, misattributed stored
     rows and price coverage. It exports no DSN, role/user identity values, subscription
     IDs, trace rows or exception messages. Finite guard labels/SQLSTATE are safe.
     No permission check attempts INSERT/UPDATE/DELETE/DDL, even with rollback.
  3. Subscription creation dates remain facts only: **approved activation cutoff is
     null**, source-subscription matching remains false, and replay authorization is
     always false. Default snapshot boundaries are `[now-30 days, now-5 minutes)`;
     source retention/activation approval is not inferred from that window. This
     probe is **not packaged in currently deployed images** and no remote execution
     path has yet been established for it.
  4. [finops_diagnose.py](../scripts/deployment/finops_diagnose.py) now has a
     `--private-paths` mode with the above inventory, MI/retention/ACL metadata and
     fixed read-only SCM commands. Empty SCM output cannot pass. The workstation
     check is transport-only: the earlier human-operator DB-token fallback was
     removed so operator success can never masquerade as runtime-MI proof.
  5. [finops_release.py](../scripts/deployment/finops_release.py) creates an **offline
     four-component source inventory**, including shared API code in both API and
     ingester, actual ingestion Dockerfile, migrations and both portals. It neither
     builds nor uploads images. Its pure saved-plan structural guard requires exactly
     four immutable image updates, rejects unknown values, settings/timer/cutoff,
     identity/network/security/registry changes, other resources and replacements.
     Native-Python-to-container conversion is explicitly rejected as requiring a
     separate reviewed Functions configuration plan. A pass **never authorizes apply**;
     fresh build/validation/source-to-image/baseline/plan-byte bindings still must be
     implemented and proven before release. It does not reuse GLM approval.

  Expanded validation: **205 passed, 1 preexisting deprecation warning, 25.67 seconds**;
  [current JUnit evidence](../gateway/validation/finops-private-probe-tests-20261027.xml).
  The original 142-test evidence remains intact. No live PostgreSQL test ran.
  New cases cover MI-only fail-closed CLI behavior, exact private subnet/TLS settings,
  read-only rollback/effective-grant checks, missing/partial SCM evidence, redacted
  state-access failures, retention/role evidence and four-image rejection guards.
  Checked source/editor diagnostics are clean. A full tracked whitespace check still
  finds the preexisting unrelated blank line at EOF in the disabled Terraform test;
  it was not fixed as part of this task.

  ### Exact next prerequisite, not broad authorization

  Provide an **already authorized private-connected execution channel into the API
  or ingester host using its existing attached MI**, sufficient to run the reviewed
  read-only probe. Admin SCM transport did not establish that capability, and its
  different identity must not impersonate the API/ingester. Then verify source-owner
  matches and review a factual UTC activation cutoff before any recovery dry run.
  No available channel was found here that can safely complete those proofs.

  Separately, workstation Terraform is blocked by the actual state-container network
  denial. If a workstation path is chosen instead of an existing approved private
  state path, **explicit storage-only approval** is required for its independently
  verified destination egress (user-reported IP `167.103.65.36` is informational, not
  permission). That approval must be restricted to `projpoctokenex`, preserve Deny
  and existing rules, and **does not authorize PostgreSQL, SCM, VNet or RBAC changes**.
  No new firewall rule is proposed/applied by this continuation. No activation,
  production DB write, replay, watermark reset, new inference or cloud configuration
  write occurred.