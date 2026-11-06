# Auto router — ON HOLD, explicit resume required

## Authoritative checkpoint — 2026-10-30

**The user explicitly put Auto deployment on hold. STOP.** This supersedes older
continuation instructions and pending-firewall language. Preserve the existing
work; do not start from scratch. Reading this checkpoint is not authorization
to run tests, install dependencies, prepare, release, send traffic or change Azure.

This checkpoint reconciles local source and retained evidence only. No fresh
cloud/browser verification was performed. Auto remains **OFF / not accepted**:
there is no actual successful gateway-managed-identity scoring/schema proof,
production Auto policy acceptance, persisted decision-overhead proof or actual
Auto API/publication release receipt. Customer **cm38 is the live Send repair
only**; API inventory-persistence image **29b67** is an earlier separate release.
Project state **185** and runtime state **111** are historical evidence, not
fresh live state or interchangeable serials. Do not replay either release.

## Current source, not a live package

- Entry point: [scripts/deployment/auto_path_oct30_successor_r5.py](../scripts/deployment/auto_path_oct30_successor_r5.py).
  Its current literal admission IP is **167.103.66.248**, not 167.103.67.80.
- Private inventory collector: [scripts/deployment/auto_path_oct30_successor_r5_reads.py](../scripts/deployment/auto_path_oct30_successor_r5_reads.py).
  Native/browser IP bridge: [scripts/deployment/auto_path_oct30_r5_bridge.mjs](../scripts/deployment/auto_path_oct30_r5_bridge.mjs).
  Specification: [docs/auto-path-oct30-successor-r5.md](auto-path-oct30-successor-r5.md).
- R5 retains the existing parent prepare/localcheck/run-reviewed-window and
  finally-cleanup interface, all six stages, actual ETags, exclusive intents,
  full protected reads and no retry. R4's launch reserve is **inclusive 22 minutes**;
  the frozen window is **30 minutes**, never extended. No alternate executor.
- The account collection is **22 = exact original 13 + exact known 9 additions**.
  The complete original13 projection feeds both model-metadata and supplemental
  RAI/count guards; full22/page/addition evidence must be retained and identical
  across each attempt's reads. No count-only waiver, silent rebase or routing promotion.
- The latest retained r5 result records **prepare=0, Send=0, cloud_writes=0,
  independent_review=false**, readiness `SOURCE_ONLY_PENDING_INDEPENDENT_AGENT_REVIEW`.
  No r5 live package/manifest directory was found in the inspected deployment
  directory listing. The offline source freeze is **not** a prepared live package,
  approval or execution receipt. A future fresh package must be independently reviewed.

### Retained exact hashes — not freshly recomputed at this checkpoint

The [post-test source freeze](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-source-freeze.json)
is timestamped **10:08:08.223539 UTC** and records source-set SHA256
`611eb1a7836896556cfc2001e8accb6fd49c9f5abef7c1f26c03d1293e18362c`.
Its source entries include:

| Source | Retained SHA256 |
| --- | --- |
| [r5 controller](../scripts/deployment/auto_path_oct30_successor_r5.py) | `38880ea068f26d4a1ab17058a8f3cfd7237f23f1a29a4c1742a84789bae23411` |
| [r5 collector](../scripts/deployment/auto_path_oct30_successor_r5_reads.py) | `42ca1f5475e4eee3d14b2c64405ec138524bdbf21b436c55beb90885bc94f5fd` |
| [r5 bridge](../scripts/deployment/auto_path_oct30_r5_bridge.mjs) | `35b8bf1102b2ac220e72c13fbecb4ffe4a0eab38badfa9c5124e0c14d602f444` |
| [r5 tests](../tests/unit/test_auto_path_oct30_successor_r5.py) | `25025cfd64850358191045922a4a731bfabe8cd6d28034c45b534a7379f2633e` |
| [r5 specification](auto-path-oct30-successor-r5.md) | `42b1f588305b24d5094da3c09bbd54e2ddf64f0c23ac2cd9dda70dcb9a8168e3` |

The attempted fresh local hash comparison failed under PowerShell constrained
language (`Get-FileHash`/object conversion errors). Any zero-mismatch counter from
that failed command is **invalid evidence**. Current byte equality must be
re-established on explicit resume; do not present these retained hashes as a new audit.

## Actual retained validation after the IP/bridge change

The [completed result](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-result.json)
at **10:08:08.065468 UTC**, following the [09:55:50 start, PID20508](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-start.json),
records the following completed suites, not a mid-run dot count:

| Retained receipt | Actual result | Receipt SHA256 recorded by result |
| --- | --- | --- |
| [Focused r4+r5](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-focused.xml) | **103 passed** = r4 43 + r5 **60**; exit0 | `1978c108b4bb1bc96a1379e4587b789fe5a8ac1c5dd7d8db12b12073b3ef8767` |
| [Broader Python](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-broader-ONCE.xml) | **455 passed**, 0 failures/errors/skips; exit0 | `4e16be05a0508d58db14acea4572fa0f83705a2d934beb526c20332733ea2710` |
| [Native selected suite](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-native.xml) | **50 passed**; exit0 | `7a6969ef3f918120e26ed4048c4f7a9266c975e9af2504de4ecc905cdf3b0b3e` |
| [Browser-helper offline suite](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-browser.xml) | **67 passed**; exit0 | `1907759ae785d21c85b52f60828e472716e0bf82685f49edf0beb95e43de4537` |
| [Historical unfiltered suite](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-historical-UNFILTERED.xml) | **68 passed / 1 failed**, 69 total; exit1 | `d14a0d73c3ee05e8176268ef0123a3cc5df84f66ecd2e03a3548310a8a0603a0` |

The [historical failure detail](../.deployment/oct30-r5-IP-final-20261030T095549831141Z-historical-UNFILTERED-result.json)
reports diagnostic06 source drift in [gateway/policies/auto-resolve.xml.tftpl](../gateway/policies/auto-resolve.xml.tftpl)
and [packages/ui/src/pages/PlaygroundPage.tsx](../packages/ui/src/pages/PlaygroundPage.tsx).
It is **not waived**: overall `all_suites_green=false`. Selected-suite success
does not convert this into full historical compatibility or independent review.

[.tmp/r5_test_results.txt](../.tmp/r5_test_results.txt) separately ends with
**60 passed, 1 Starlette/AnyIO deprecation warning in 70.92s**. It is not a
source-bound release receipt. The new r5 Python count is **60**, not the earlier
pre-IP-change 50; native50 is a different suite. Overlapping suites must not be
added together as unique test coverage. No tests were run for this checkpoint.
The completed result records historical268 and six artifacts exact at that time;
this is retained evidence, not a successful fresh hash check now.

## Worker/dependency state — do not assume quiescence

The previous agent installed user-level Python dependencies and repeated test
invocations, including quoting failures. Do not repeat, repair, uninstall or
continue those operations while on hold. The retained test warning resolves
Starlette from the user's Python313 site-packages, corroborating user-site use;
it is not a complete list/version audit of the installation.

One local read-only process inspection was attempted for this checkpoint. Its
combined terminal output was dominated/truncated by constrained-language/object
and hash errors, and no reliable process snapshot was recovered. Therefore
**remaining pip/pytest/parent workers are UNKNOWN**, not proven absent or stopped.
The completed PID20508 result does not prove all earlier repeated workers exited.
No worker was killed or cancelled; no process inspection was repeated. Silent
terminals are not proof that a command never ran. Reconcile original workers and
durable results before considering another invocation, only after explicit resume.

## Storage/IP correction — no pending authorization to add either IP

The [actual exact-add result](../.deployment/storage-firewall-167-103-67-80-20261030/result.json)
records the approved **167.103.67.80** addition: ARM write **HTTP200 at
00:44:24.849023 UTC**, followed by Entra blob **HEAD200 at 00:44:44.863409 UTC**,
unlocked/available, length314338. Full account comparison passed; all other
account properties exact. The prior four IPs **167.103.66.93, 167.103.66.248,
167.103.65.36, 167.103.63.12** were preserved. The CLI merge was not atomic CAS;
the result reports no concurrent delta, not a general concurrency guarantee.

The user's current FYI IP **167.103.66.248** was **already historically allowed**.
It now also matches r5's diagnostic admission literal; changing that literal did
not perform or authorize a firewall change. The old pending-firewall paragraph
in [docs/auto-live-release-preparation-20261029.md](auto-live-release-preparation-20261029.md)
is historical and superseded. No fresh network or HEAD check was made here.
Do not add/remove/rewrite firewall rules on the strength of an IP notification.

## Consumed attempts and cleanup — preserve, never replay/restamp

The [consumed Oct30 package](../.deployment/auto-path-oct30-bounded-native-20261030T045805020273Z/manifest.json)
has manifest SHA256 `28878b99397dbd60a7c72c74dcbca2f262475ac6766f591bb22ec075ba162dfa`.
Online returned HTTP200, but its original postread timed out: execution outcome
remains **UNKNOWN for scoring**, not a successful scoring/schema receipt.
Parent finally cleanup is retained: [offline verified 05:12:59.138749 UTC](../.deployment/auto-path-oct30-bounded-native-20261030T045805020273Z/offline-verified.json)
and [original global verified 05:16:01.068475 UTC](../.deployment/auto-path-oct30-bounded-native-20261030T045805020273Z/restore-global-verified.json),
both all13 exact. The earlier activation-cleanup marker is not a later
verification timestamp. [Independent read-only investigation](../.deployment/oct30-consumed-investigation-readonly-20261030/result.json)
at **06:13:23 UTC** verified rev2 offline/noncurrent, rev1 online/current,
both formats/full13 exact, owner absent and project185/runtime111.
These are historical observations, not current live confirmation.

The [07:40 accelerated successor stop](../.deployment/oct30-accelerated-final-stop-20261030.md)
is a different attempt: manifest `7d54f350d05e6139dd5d1b871c97a925256a5533b2d7b298ddf7ac38601bb75a`,
all265 bound; it refused before activation after the launch gate expired. No
browser request/reservation/claim existed. R4's sole prepare failed at
`13_deployment_bindings`; it is consumed, not a live r5 package. Preserve old
**265/268** bindings, artifacts, original timestamps, intents and failure receipts.
No restamping safe browser observations, replaying saved plans or retrying UNKNOWN outcomes.

## Preserve the exact model boundary

The **13 explicit customer chat aliases** remain the protected baseline, not a
freshly exercised acceptance matrix:
`gpt-5.6-luna`, `gpt-6.1-sol`, `gpt-5.4-mini`, `gpt-4o`,
`DeepSeek-V4-Flash`, `DeepSeek-V4-Pro`, `Kimi-K2.7-Code`, `grok-4.3`,
`grok-4-20-reasoning`, `grok-4-1-fast-reasoning`, `FW-GLM-5.3`,
`FW-MiniMax-M3`, `glm-5.3`.

The original **13 account deployments** instead mean **12 Foundry chat +
Decision-1**; external `glm-5.3` is not an account deployment. Decision-1 is the
scorer, not a selectable chat candidate. The nine account additions below are
**not accepted routes, catalog promotions or Auto candidates**:
`claude-sonnet-5-5`, `claude-opus-5-5`, `claude-opus-5-5-fast`,
`claude-haiku-5-5`, `gpt-6.1-terra`, `gpt-6-luna`, `claude-opus-4-8`,
`Mistral-Large-3`, `mistral-medium-3-5`.

## Resume recipe — ONLY after a new explicit user instruction

1. Read this checkpoint and retained evidence; reconcile actual workers/tasks,
   all exclusive intents/results, source hashes and ownership first. Do not
   rerun silent/ambiguous commands or kill workers without authorization.
2. Fresh read-only scope/authentication/protected-state reconciliation using
   existing permissions and strict TLS: current IP and existing storage rules,
   Entra blob HEAD, current policies/both formats/revisions/ETags, state locks,
   full settings/pins and protected13/full22 proof. No secrets, key reads,
   credential/browser-storage extraction or stale capture reuse. Stop on drift.
3. Establish current-source clean r5 proof and **actual independent native
   exact-source review**, including the IP bridge, full22 isolation, time gates,
   one scoring/zero completion/zero retry and parent-finally cleanup. Reconcile
   the historical failure rather than claiming an all-green suite. Existing
   receipts are reusable evidence only where byte bindings are verified.
4. Obtain **new actual safe authenticated browser events**, correct model,
   empty draft/system/history, without Send or secrets. Do not restamp old events.
   Only within newly authorized scope: **one fresh prepare**, exact new-package
   independent review, genuinely manifest-bound browser preflight, then at most
   **one reviewed window / one scoring / zero completions / zero retries**.
   Preserve every intent; on ambiguity stop and reconcile. Parent must finally
   verify owned revision offline and exact original global restoration, even
   after expiry/failure. No route/current-revision promotion.
5. Only after real gateway-MI scoring/authentication and actual schema proof,
   separately finish production-policy validation, separate correlated durable
   decision-overhead telemetry, actual API/publication release receipt and
   bounded end-to-end acceptance. Defaults must immediately work for a new
   organization/user/valid active subscription through normal provisioning,
   Playground and direct API, **without per-tenant admin initialization,
   approval, whitelist, seed or policy publication**. Preserve auth/safety/quotas
   and all13 explicit routes; unknown decision costs are not zero/free.

**No new roles/identities, network changes, DDL, main-stack deployment, historical
plan replay or implicit resumption.** Auto is unresolved and paused, not complete.

## Checkpoint edit boundary

Only this checkpoint and minimal HOLD pointers in the two historical entry docs
are documentation edits; the existing session plan is updated separately.
Exact-path searches found neither pointer document in retained manifest JSON
or root freeze JSON source keys. No source-bound r5 specification, controller,
test, source freeze, package, receipt or historical artifact was edited.
No tests/install/cloud/browser/prepare/release/source edit/process cancellation
or task-completion action was performed for this checkpoint.