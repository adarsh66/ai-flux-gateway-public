# APIM publisher — bounded response-shape investigation and local correction

## Subsequent release attempt — blocked, not deployed

Linux no-push validation **cm7g failed** (266passed/8failed/83setup errors)
because the expanded curated context omitted required fixtures/function files
and the nested Alembic config path. Diagnostic73 and exact-parent composition
passed, not the overall release gate. Production build/plan/official9/apply not
started. Fresh full46 postguards14:45UTC root166/child206/allpins unchanged;
ordinary GET current/published13/history13 across both pages. No activation,
guard weakening or replay. [Actual release report](../.deployment/poc-publisher-release-20261104-01/FINAL.md).
The investigation outcome below describes its earlier phase only.

## Result (2026-11-04)

Completed a **new GET-only current investigation**, followed by a narrow local
diagnostic correction. **No readiness relaxation, deployment, build, push,
Terraform plan/apply, live save/reconcile, inference, controls activation,
configuration/DB/network/RBAC/logging change, or old controller replay occurred.**
The original October28/29 initial-save HTTP502 cause remains **unproven**.
The earlier [instrumentation-only report](poc-publisher-diagnostics-20261104.md)
describes the preceding local182-test phase, not this new live observation.

## Actual current observations

Exclusive evidence directory:
[.deployment/poc-publisher-shape-20261104-01/intent.json](../.deployment/poc-publisher-shape-20261104-01/intent.json).
The new [read-only controller](../.deployment/poc-publisher-shape-20261104-01/read01.py)
ran once. It made **10 finite GETs** (one storage state GET and nine ARM GETs),
with no request retry or operation-scope GET. Receipts omit credentials, raw
headers, ETag values, XML, settings payloads and exception text. Normal existing
CLI Profile acquisition verified tenant/audience and remaining TTL >=600 seconds;
TLS used the supplied corporate CA and redirects were denied. Start/completion
worker checks passed, with no kills or waivers.

| Observation | Actual evidence |
| --- | --- |
| 14:19:58 UTC root baseline | Root **166**, entire parsed state equals retained finalread34; raw SHA256 `ddd5f6f4e1d7eab577d17270629e4d04fa1d32ecb63773fc6e7a78d05791c78d`. Local child **206**, exact retained hash. [Baseline receipt](../.deployment/poc-publisher-shape-20261104-01/baseline.json). |
| 14:19:58.756 UTC fragment `format=xml` | HTTP200; `properties.provisioningState` **present**, type string, **Succeeded**; ETag present; value7411 UTF-8 bytes; canonical XML hash recorded. `properties.format` absent. [XML shape](../.deployment/poc-publisher-shape-20261104-01/fragment-xml.json). |
| 14:19:59.073 UTC fragment `format=rawxml` | HTTP200; state **present**, string, **Succeeded**; ETag present; format rawxml;4675 bytes. Non-XML-encoded representation is not required to parse as XML. [Raw shape](../.deployment/poc-publisher-shape-20261104-01/fragment-rawxml.json). |
| Current policy topology | Active API policy contains **one existing POC fragment include**, Auto marker and4096 marker. Global policy contains no POC include. This is **not the detached October29 topology**. Include presence is not traffic/enforcement proof. [Active](../.deployment/poc-publisher-shape-20261104-01/policy-active.json), [global](../.deployment/poc-publisher-shape-20261104-01/policy-global.json). |
| 14:20:05 UTC deployed runtime | API0c01/admin4a6/customerc564/ingestion995c immutable pins exactly match retained checkpoint. API ARM state Running, user-assigned identity attached at the expected identity resource. Running is not application health acceptance. [Runtime](../.deployment/poc-publisher-shape-20261104-01/runtime.json). |
| 14:20:57 UTC ordinary safety collection GET | HTTP200, one scope dev-unified, version=published_version13. `poc_controls_enabled=true`, `managed_controls_enabled=false`, `enforcement_enabled=false`, safety relaxation false. |
| 14:21:14 UTC ordinary gateway collection/history GET | Both HTTP200. Current desired and published state **published**, version=published_version**13**, desired error absent. History total13; first page13 through4 all currently published/no errors; latest revision occurred2026-11-01T16:34:00.069299Z. Pagination not exhausted; no old reason/config/bindings printed. [Browser evidence](../.deployment/poc-publisher-shape-20261104-01/browser01.json). |

This was intentionally **not another full46 collector**. Root/pins were freshly
checked; prior full46 all22+Auto/4096, pricing, safety, quotas, settings, network
and role evidence remains retained. Only the scoped policy bodies were freshly
hashed; no claim that every deployed resource/configuration was re-read here.
No direct private health request was repeated: the retained403 remains **not
health success**. Successful authenticated settings GETs prove those read routes
work, not content-changing publication, worker health or paid inference.

## Contract assessment and decision

Official references reviewed this turn:

- [Policy Fragment GET,2024-05-01](https://learn.microsoft.com/en-us/rest/api/apimanagement/policy-fragment/get?view=rest-apimanagement-2024-05-01): HTTP200 successfully returns a fragment with ETag. The contract lists provisioningState, while successful200 examples omit it.
- [Policy Fragment Create Or Update,2024-05-01](https://learn.microsoft.com/en-us/rest/api/apimanagement/policy-fragment/create-or-update?view=rest-apimanagement-2024-05-01): update/create200/201 samples have service-operation/location headers and **InProgress**. Matching content or initial HTTP200 alone cannot prove completion.
- [ARM asynchronous operations](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/async-operations): describes Succeeded/Failed/Canceled as terminal and says no provisioningState value means finished/succeeded. This is general ARM guidance, not proof of this runtime's historical response.

**Both actual current fragment GETs return Succeeded**, not absent/null state.
Therefore this investigation does **not** justify implementing terminal-absence
handling or multiple stable-read acceptance. Existing missing/null rejection is
unchanged. Current Succeeded also does not prove that the October failures could
never have involved absent state. Historical source reasoning, mock tests and a
currently cleared revision history cannot identify their original caught branch.

No change to the already resource-only signed-operation handling; no service
operation GET or broader grant. Fireworks13-alias compatibility guard is untouched;
activation review remains separate. Current API policy inclusion and the API's
`enforcement_enabled=false` capability are reported separately, not flattened into
a claim of detached or traffic-proven controls. The optional form's output1024
disclosure was observed but no production4096 limit was edited or reinterpreted.

## Implemented local correction

Source inspection established a specific **diagnostic ambiguity**: the prior
single diagnostic `status` held either a response HTTP status or an `ApimError`
classification. A successful GET200 followed by synthetic readiness409/504 could
therefore be mislabeled if interpreted as the ARM response.

- [APIM client](../services/control-plane/src/aiflux/apim.py): closed typed integer
  fields **`response_status`** (only an observed HTTP response) and
  **`error_status`** (existing `ApimError.status_code`, possibly synthetic).
  The ambiguous diagnostic `status` key is no longer emitted/accepted. Existing
  positional exception properties and public error contracts are unchanged.
  HTTP rejection/JSON errors retain actual response status explicitly. Nested
  stages and later polls discard stale response facts as before.
- State vocabulary now distinguishes `state="missing",state_present=false`
  from `state="null",state_present=true`. Both still fail with the existing
  `missing_state` reason. Unknown values remain fixed `unknown`, never raw text.
- [Publisher log sink](../services/control-plane/src/aiflux/gateway_settings.py)
  re-filters the new fields. Synthetic outer drift/readback failures carry
  error_status412/409, without inventing a response status from the tuple-only
  fragment getter. No live logging configuration was changed.
- **No change** to success criteria, exact canonical match, valid ETag,
  independent final readback, conditional PUT/current-version CAS, append-only
  audit, failed desired versus published head,12-read/60-second bound, sleeps,
  timeouts, HTTP502, safe public message or explicit reconcile semantics.

Examples are diagnostic classifications, not live failures: a GET200 followed
by missing state yields response_status200/error_status409; a pending-state
timeout yields response_status200/error_status504. Authentication/transport
failure before a response carries **no response_status**, including later polls.

## Final local validation — one execution

Configured interpreter: Python3.13.1 at C:/Program Files/Python313/python.exe.
The [new offline runner](../.deployment/poc-publisher-shape-20261104-01/test02.py)
ran the following **final chosen scope once**, denying real DefaultAzureCredential,
AzureCliCredential and ManagedIdentityCredential token acquisition, external DNS
and external socket connections. Local TestClient loopback/socketpair support
was retained. No dependency installation, production DB, esbuild/Vite/Vitest or
blocked Ruff execution. No historical test/deployment controller was executed.

| Suite | Passed |
| --- | ---: |
| [Publisher diagnostics](../tests/unit/test_apim_publisher_diagnostics.py) | 73 |
| [Fragment encoding](../tests/unit/test_fragment_encoding.py) | 6 |
| [POC controls/API](../tests/unit/test_poc_controls.py) | 40 |
| [Gateway settings](../tests/unit/test_gateway_settings.py) | 35 |
| [Managed controls](../tests/unit/test_managed_controls.py) | 32 |
| [APIM/watermarks](../tests/unit/test_apim_and_watermarks.py) | 5 |
| [Synthetic publication worker](../tests/unit/test_publication_worker.py) | 5 |
| [Default limits](../tests/unit/test_default_limits.py) | 13 |
| **Total** | **209** |

**209 passed,9 existing deprecation warnings in29.61s**, native test result0,
zero failures/errors/skips. Runner duration34.66s includes local worker checks.
[Result/hashes](../.deployment/poc-publisher-shape-20261104-01/tests02-result.json),
[actual output](../.deployment/poc-publisher-shape-20261104-01/tests02.log),
[JUnit](../.deployment/poc-publisher-shape-20261104-01/tests02.xml).
Editor diagnostics report no errors on the four changed Python source/test files.
New cases cover delayed pending→Succeeded, exact content during pending/failure,
missing/null distinction, ETag bounds, status allowlist/redaction,200 versus
synthetic409/504, stale202/transport facts, independent final readback, stale CAS
and unchanged request/failure/publication audit counts. These are **synthetic
regressions**, not live response-shape proof; live shape evidence is above.

## Tooling observations preserved

The CLI-guidance request returned MCP403. Consulted the prescribed
[MCP troubleshooting guide](https://aka.ms/azmcp/troubleshooting); no credential,
policy, tenant or network bypass/change was attempted. The installed guidance-only
best-practices callable **succeeded200**, unlike the preceding phase's unavailable
callable. Used secure TLS, normal existing credentials, least scope and bounded
reads. AppLens capabilities were discovered; no broad diagnostic/log/metric
collector was needed for this specific response-field investigation.

Two terminal launch attempts (one capture, one test) failed at shell parsing
before Python execution. Each was checked for **absent intent and no worker**
before executing its unconsumed script. Successful launches returned silently;
durable completion/result receipts were inspected, **not replayed**. A later
ad hoc process query reported Get-CimInstance unavailable in that terminal;
the actual controllers' explicit PowerShell start/completion worker checks
succeeded. No cloud requests or tests were duplicated by these shell failures.
Browser initial /settings navigation omitted the /admin basename and returned404;
corrected normal route worked. Native refresh pointer click timed out; normal
GET refresh dispatched through the existing button handler. One observer used
an unavailable URL global; corrected predicate read only the URL string.
No tokens/storage/headers inspected and no Save/Retry/Reconcile invoked.

The first local-only finalizer passed original test/source/policy hash checks,
then failed because it mislabeled the supplied API UAMI GUID as a **client ID**.
Retained exact root evidence proves `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` is the
**principal ID**; client ID is `f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1`. The freshly
observed attached identity resource matches that retained root identity. The
failed finalizer was preserved and **not rerun**; a separately named local-only
finalizer verifies correct ID categories and remaining completion. No runtime
identity/config/RBAC or source/test change resulted. See
[preserved local failure](../.deployment/poc-publisher-shape-20261104-01/STOP03.json)
and [final integrity receipt](../.deployment/poc-publisher-shape-20261104-01/FINAL04.json).

## Next gate

No deployment or activation was performed or implicitly authorized. This local
diagnostic improvement is ready for separately authorized API-only release
validation against a fresh protected baseline. Original initial-save reliability
still requires actual instrumented evidence and separately approved bounded
content-changing acceptance. Because the current API policy includes this
fragment, **do not assume any future test is detached/non-enforcing**. Prefer an
isolated fixture unless explicit live authorization and current policy review
establish a safe scope. Never replay these consumed receipts/controllers.