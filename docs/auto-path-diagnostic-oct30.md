# Oct30 successor — storage-bound preparation and parent handoff

## Oct30 current source pre-review — runnable parent and trusted TLS

The browser-capable parent now reports successful normal sign-in and ordinary
model selection/fill/clear without Send on page
**6eaeffd1-ef07-45bf-bf36-9f3bb0ee32c3**. A new read-only snapshot independently
shows Caldova/Caldova-AI, gpt-5.4-mini, empty draft/system/history. This supersedes
the historical HTTP401 blocker below, but is not a manifest-bound preflight.

The new [explicit parent entrypoint](../scripts/deployment/auto_path_oct30_parent.py)
offers prepare, localcheck and run-reviewed-window. Only the last explicitly
calls `run_reviewed_window()` with `file_browser_handoff()` in a separate process;
it requires the exact manifest, genuine all-six review/preflight and exact page
binding, and rejects any prior stage/window/browser intent or shared owner.
No invocation is authorized merely by this documentation or the CLI's existence.
The browser-capable parent must remain available, observe the actual request and
retain the actual browser result while the bounded callback is alive. No process
kill watchdog is used: killing the process could defeat its finally. Callback
timeout/error enters the existing finally; whole-process/cleanup duration is not
a hard real-time guarantee. Silence requires reconciliation, never rerun.

A real production prerequisite was found: the historically hardcoded temporary
CA bundle no longer exists. The new entrypoint pins the already installed
corporate bundle at SHA256
**e747e9880a4e63c73f55af589941139d0a4f90ceec5df745cfd6fee5bbe257dc** and verifies
hostname checking/CERT_REQUIRED before configuring only its process's existing
transport. This is not a TLS bypass, trust-store edit, certificate download or
fallback. All consumed source files and the Oct30 controller remain unchanged.
New offline tests cover the entrypoint, wrong-page/replay rejection and CA pin.
Actual current test receipts and fresh-package evidence are recorded separately,
after execution; no counts, approval or preflight are asserted in advance here.

## Current checkpoint: no activation, approval or frozen window

The exact storage Allow addition **167.103.67.80** was explicitly authorized and completed. Actual PATCH returned HTTP200 at **2026-10-30T00:44:24.849023Z**; Entra-authenticated state HEAD returned HTTP200 at **00:44:44.863409Z**. The pinned [whole-account audit](../.deployment/storage-firewall-167-103-67-80-20261030/final-offline-audit.json) and [result](../.deployment/storage-firewall-167-103-67-80-20261030/result.json) prove one appended Allow item and every other returned property exact, without metadata exclusions. Never replay that addition. Its authorization did not authorize Auto, Send or deployment.

Actual browser tab **3e424ff6-22a5-40d1-8bf9-b5f04771b4fc**: ordinary Playground navigation produced **Invalid access token**, HTTP401 console events at **02:20:48 UTC**. The signed-in-looking header is not working Playground access. No key/auth inspection, Try again, Send or Enter occurred. Required-model and safe input readiness cannot be proved. **Do not prepare/freeze until the real browser is ready.**

## Actual offline fixture correction — 02:37:02 UTC

Read the complete [retained failure traceback](../.deployment/auto-path-oct30-storage-handoff-final-20261030-python.log): **179 passed /1 failed**. The unchanged original `test_strict_read_context_rejects_all_configuration_write_methods` entered `read_transport()` and failed in `ssl.create_default_context(cafile=rt.CA)` with `FileNotFoundError`, before reaching its configuration-write assertions.

Only the unbound [Oct30 test module](../tests/unit/test_auto_path_diagnostic_oct30.py) supplies the correction. Its autouse fixture is loaded explicitly as a pytest plugin (`-p test_auto_path_diagnostic_oct30`, with the unit-test directory on `PYTHONPATH`) and selects that exact original node ID only. A spec-constrained `SSLContext` mock replaces context construction; the fixture verifies the configured CA argument, no context manipulation, no transport open and no CLI invocation. The original PUT/PATCH/DELETE/POST and CLI-write rejection assertions execute unchanged. All other tests receive no SSL mock. The bound original test, all production TLS code, missing-CA fail-closed behavior and corporate policy remain unchanged. Without this explicit plugin, the original test retains its filesystem-CA dependency; no global pytest or trust configuration was changed.

The [new exclusive result](../.deployment/auto-path-oct30-fixture-fix-20261030-result.json) records the sole complete three-file Python invocation (original release + successor + Oct30), native Oct30 suite and browser **offline fixtures**:

| Actual new receipt | Result | SHA256 |
|---|---|---|
| [Python](../.deployment/auto-path-oct30-fixture-fix-20261030-python.xml) | **180 passed**, 0 failures/errors/skips | f480925fae49cc02f3e448241db4ea56861a71445e082709a4067be644df4108 |
| [Native](../.deployment/auto-path-oct30-fixture-fix-20261030-native.xml) | **50 passed**, 0 failures/errors/skips | 1864f3576169fe32488234d552806df6c7ea0b3e8306e34796df6b46dbb8510c |
| [Browser offline](../.deployment/auto-path-oct30-fixture-fix-20261030-browser.xml) | **67 passed**, 0 failures/errors/skips | ba08b1e42ae20532c618854d41e62c6ea19a3c8cff2e9d3b1bbed4a4ef2ff976 |

The Python run retains one Starlette deprecation warning. The controller remains the unchanged current `108db727…` version. All **206** dependency hashes were stable throughout tests; the test-time source-set SHA256 is `d1cefdbf347ac90c70bdb0c71ba8b6817066bc51bc7229013f931deee8f7ee92`. This documentation is updated **after** those tests; that digest is not misrepresented as the final documentation-inclusive digest. The separate final local binding audit records the final 206-entry set and permits only this documentation change after tests.

The new run re-proved all **173 consumed source bindings**, the consumed predecessor's five actual HTTP200 chains, all pinned storage evidence and the exact whole-account appended-IP transition. Adapter verification used an explicitly labelled **TEST_ONLY local projection of retained capture**, retaining all13 guarded fields and leaving the retained capture unchanged. It is not a fresh collector, live preflight, release package, independent review or browser-readiness proof.

The [retained full unfiltered native result](../.deployment/auto-path-oct30-storage-handoff-final-20261030-native-full.xml) is **185 PASS /1 historical binding FAIL**, SHA256 `96c2e458f2fab5d0f2fb077bba1971ca019ba92b40c236e9eafb8337fe139acd`. Its failing assertion is “existing diagnostic06 source bindings and customer retained input bindings unchanged”. This receipt was hash-verified, **not rerun, edited or waived**. Focused success is not clean full-suite acceptance or independent review. Earlier 150/49/67 and 184/1 receipts remain historical, not current acceptance.

No cloud calls, prepare/window/activation/Send, build, Terraform, browser interaction or old source-bound edits occurred in this correction. The actual **Invalid access token** gate remains; parent handles normal login and genuine browser readiness. No preflight was manufactured.

## Narrow storage-only predecessor adapter

Only the new unbound Oct30 controller/test/doc change. All old173 bindings, original controller, old successor, consumed141022 manifests/artifacts and intent receipts stay unchanged. Local predecessor proof retains five actual HTTP200 stage chains, restored original global, offline revision2 candidate, customer cm38/API29b67, project185/runtime111 and exact full13. This is retained evidence, not a new cloud observation.

`storage_transition()` pins audit SHA256 `92f2b40369ce793e6f6b3f490e6bf244b1c2415f90f36d332fc16bfc22d777d8`, verifies its21 evidence hashes, authorization, exact result, one-wire intent/response and HEAD200. It constructs after from the entire original raw account by appending only the fixed Allow item; independent/final accounts must equal it. No property, list order or metadata is ignored.

`initial()` first proves the before account canonical hash and network projection match consumed cleanup. Fresh `storage_sha256` and `baseline.state_network` must match the complete approved after account. Only those two fields in a **private copy** project back for strict old validation; the actual capture is never rewritten. **Supplemental contains no storage projection and stays entirely exact**, as do every other baseline field, role definition, deployment, settings hash, both policy formats, inheritance, API metadata and state field. No generic exclusion/adoption exists. During stages the inherited full guard compares the real new baseline directly, rejecting further storage drift. New manifests also bind the audit and all21 evidence files.

## Fixed-IP render/browser delta unchanged

Native rendering changes one IP occurrence in each finite candidate condition span. Immutable BEFORE spans retain their historical IP. Python independently proves the predicate/full structure, then single byte-replacement reversal; restore wire stays exact. Browser source differs only at its fixed reservation-IP guard. Identity/method/revision/path/time, counter/quota, terminal behavior and one scoring/zero completion/zero retry budgets remain exact. Historical scorer count remains unknown.

## Genuine parent browser orchestration

`run_reviewed_window()` validates genuine all-six review and real preflight, requires at least27 minutes left, then durably arms parent finally **before** activation. Flow: activate → reserve → claim → explicit callback, finally offline → restore-global on success/error/timeout. Consumed cleanup is hash-verified, never repeated; partial/unknown cleanup stops for fresh read-only reconciliation. Import and prepare do not execute cleanup.

`file_browser_handoff(folder, binding)` requires the actual durable claim binding. It exclusively emits parent-browser-request binding manifest/binding hashes, nonce and absolute deadline. It waits only until the original30-second claim deadline, bounded by UTC and monotonic time. The request explicitly says **coordination only, not browser evidence**. No fixture, approval, preflight or browser result is manufactured.

The later parent must launch the reviewed controller as a **separate supervised process**, returning control to the browser-capable parent while it remains alive. A synchronous tool call waiting for controller completion cannot service its callback. The parent must already be watching **before claim**, promptly read the request, verify real page readiness/on-disk bindings, then invoke the reviewed browser source with the actual binding once, **only after separate Send authorization**. No direct HTTP Send or credential inspection substitutes for the browser.

Parent retains the genuine tool result in a package-relative evidence file, then creates parent-browser-response **exclusively and atomically**, after the evidence is fully written. Fields: manifest_sha256, binding_sha256, nonce, at_utc, parent_observed=true, fixture=false, status COMPLETED or FAILED, evidence, evidence_sha256. These flags are parent attestations, not independent browser/scorer proof. Controller checks bindings, evidence containment/hash and original deadline. Failed/malformed/late/missing response raises into finally, without retry. Callback itself never runs a browser. Process termination cannot guarantee finally; retain the reviewed expiry-independent cleanup/reconciliation procedure, never blindly rerun it.

The browser operation can take20 seconds. Tool latency may prevent timely handoff; do not extend/restamp the binding or weaken a gate. STOP/cleanup instead. No real handoff occurred here.

## Timing/review gates before one fresh prepare

1. Finish sources/offline tests and **real independent native review** before freeze: all six stages (install-global, install-revision, online, reserve, offline, restore-global), claim/handoff, storage adapter and no-replay cleanup. Resolve the disclosed historical binding failure before claiming full-suite acceptance. No fabricated transcript/approval.
2. Restore normal Playground access outside this invocation. Select **gpt-5.4-mini**, verify subscription, empty system/history, responsive ordinary input and empty draft, **no Send**. Do not inspect credentials.
3. Confirm an available browser-capable parent and reviewed separate-process supervision/handoff plan. Pre-freeze observations are not manifest-bound preflight; bind honest fresh evidence after freeze.
4. Only then **one fresh read-only prepare**; no old package/stale capture reuse. Keep full13/state reads, four read-only settings-list POSTs, blob HEAD, both policy formats and opaque ETags. The maximum30-minute window freezes only after collection/guards finish. No cloud write.
5. Immediately freeze sources/artifacts and return exact manifest to parent. Genuine manifest-bound review/preflight must finish within about3 minutes so at least27 remain. Prior activation took14 minutes, reserve4 minutes; remaining margin is not a cloud-latency guarantee. If late, no activation or silent reprepare. Separate parent authorization remains required.

Configured system Python3.13.1: C:/Program Files/Python313/python.exe; repository and services/control-plane/src precede .venv/Lib/site-packages. Oct30 CLI exposes prepare/localcheck/cleanup only, no bare activate/reserve/claim. Later prepare takes a new unique package and actual clean final-source Python/browser/proposal receipts. Historical receipts, fixtures and this document are not approval.

This fixture-correction invocation is **source-only and offline**: no cloud calls, prepare, window, activation, reserve, claim, cleanup, Send, Terraform, build, API release or cloud configuration write. Later-stage descriptions above are gates, not permission to execute them now.