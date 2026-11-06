# APIM publisher diagnostics — November 4 implementation only

## Latest release attempt — blocked, not deployed (14:45UTC)

The authorized API-only release stopped at Linux no-push run **cm7g**:
266 passed,8 failed,83 setup errors. All73 diagnostic-specific tests passed,
but required test fixtures/function files/nested migration config were omitted
from the curated context. No production build, plan, official workflow or apply.
Missing-only full46 protected postguards passed root166/child206/all4pins exact.
No guard relaxation or validation replay; controls not activated;502 unproven.
See [actual final report](../.deployment/poc-publisher-release-20261104-01/FINAL.md).
All preceding phase-specific claims below remain historical, not release proof.

## Later continuation — new bounded reads and local diagnostic correction

The preceding182-test phase below is retained as history. A later authorized
GET-only investigation observed both fragment representations returning
HTTP200/Succeeded with ETags, current published revision13, unchanged root166/
child206 and all four deployed pins. Missing/null readiness acceptance was **not**
implemented. A new local correction separates observed `response_status` from
existing (possibly synthetic) `error_status`, and explicitly labels null state.
**209 tests passed,9 existing warnings; not deployed.** Historical502 cause
remains unproven. See [current evidence and implementation](poc-publisher-response-shape-20261104.md)
for exact receipts, contract references, timing, topology and limitations. The
original single diagnostic `status` vocabulary documented below is superseded;
the public `ApimError.status_code` property is unchanged.

## Scope and outcome

Implemented local source instrumentation and synthetic Python tests only.
**No live defect is claimed fixed.** The October28/29 content-changing initial
HTTP502 failures still lack proof of the exact caught branch. Healthy later
readback/reconcile does not establish that missing state, a signed header,
permissions, transport, or readiness was their original cause.

No cloud request/build/deployment, live save/reconcile/activation, production
task, historical controller replay, Terraform command, or inference occurred.
The supplied root166/child206 and pricing API0c01/admin4a6 checkpoint identifiers
are unchanged by this work and were not independently refreshed. Feature2 stays
paused. Existing unrelated working-tree content and historical evidence were
preserved. The actual resume document is
[poc-controls-resume-20261028.md](poc-controls-resume-20261028.md), not a newly
invented October29 checkpoint.

## Changes

- [APIM client](../services/control-plane/src/aiflux/apim.py):
  `safe_apim_diagnostics()` is a closed key/value allowlist. It rejects generic
  strings, unknown keys, non-exact primitive types, out-of-range integers, and
  string subclasses. It never stringifies arbitrary objects. `ApimError` keeps
  its existing positional `status_code, pending_operation` contract and generic
  message; optional diagnostic arguments are keyword-only. Existing request and
  exception-cause behavior is retained. Malformed URL parser errors in response
  header validation become fixed `invalid_header` errors without raw text.
- [POC publisher](../services/control-plane/src/aiflux/gateway_settings.py):
  the existing broad stage log carries a separately re-filtered dictionary in
  `LogRecord.apim_diagnostics`, also rendered through the fixed message template.
  No exception/traceback logging is added. Outer CAS drift has reason
  `drift_conflict`; strict readback mismatch has `readback_mismatch`.
- [New APIM diagnostic tests](../tests/unit/test_apim_publisher_diagnostics.py)
  and [POC API regressions](../tests/unit/test_poc_controls.py): exercise actual
  client branches and public API behavior using synthetic responses/in-memory DB.

### Diagnostic vocabulary

Substages: `fragment_get`, `conditional_put`, `header_validation`,
`operation_poll`, `resource_readiness`, `baseline_read`, `strict_readback`.
The original broad `conditional_put_and_readiness` stage remains in the POC
message; it is not an arbitrary caller-supplied diagnostic string.

Reasons: `operation_failed`, `authentication_error`, `transport_error`,
`http_error`, `invalid_json`, `invalid_fragment`, `invalid_input`,
`invalid_header`, `invalid_properties`, `missing_state`, `terminal_failure`,
`unknown_state`, `malformed_xml`, `readiness_timeout`, `operation_timeout`,
`drift_conflict`, `readback_mismatch`.

Optional metadata (only where observed/appropriate):

| Field | Restriction |
| --- | --- |
| `status` | Exact integer 100–599; existing error status if supplied, otherwise the response status at the failing stage. Synthetic existing 409/504 error statuses are not claimed to be ARM HTTP responses. |
| `elapsed_ms` | Exact integer 0–3,600,000, monotonic stage duration, clamped. |
| `poll_count` | Exact integer 0–12. |
| `state_present` | Exact boolean: field present, independently of null value. |
| `state` | `missing`, `unknown`, or one of Succeeded/Failed/Canceled/Cancelled/InProgress/Running/Accepted/Updating. No raw unknown value. |
| `etag_present`, `canonical_match` | Exact booleans; no ETag or hash/XML bytes. Match omitted when not evaluated. |
| `operation_present`, `location_present` | Exact booleans; no raw header or URL. |
| `operation_path` | `absent`, `exact_resource`, `service_operation`, `invalid`. |
| `location_path` | `absent`, `exact_resource`, `invalid`. |

Polls discard earlier state/match/status facts before another request. A later
transport/auth failure cannot inherit an earlier poll's successful HTTP status,
ETag, state, or canonical match. Outer request facts do not override inner-stage
facts. No ARM request ID/error-code capture or generic exception strings are
added. Signed URLs, query parameters, headers, subscription keys, tokens, XML,
configuration, request bodies and exception messages never enter these logs.
The retained internal `pending_operation` contract is not included in diagnostics.

## Publication semantics deliberately unchanged

- Service-operation URLs already use **exact-fragment resource readiness**. They
  are not followed, and no wider ARM permission or operation-scope GET is added.
- Exact-resource operation headers still use their existing status-poll branch;
  success remains exactly `Succeeded`. Location retains its existing allowlist.
- Resource readiness still requires `Succeeded`, exact canonical desired XML,
  and a valid non-wildcard ETag. Missing/null/unknown state and known terminal
  failures remain rejected; malformed XML is not accepted speculatively.
- Polling remains at most 12 requests, a 60-second deadline, and existing
  2-second sleeps. Request timeout remains 30 seconds. No extra GET/PUT, automatic
  retry, blind PUT replay, rollback, activation or write scope was introduced.
- Existing ETag/CAS, canonical fingerprint, and independent final readback
  safeguards remain. Public failures remain HTTP502 with the same generic
  optional-publication message, failed desired revision, and preserved published
  version. Explicit same-version reconcile still avoids PUT when desired content
  is already stored, using the existing baseline and independent readback.

## Local validation

Tooling limitation: Azure management discovery was activated before edits, but
the dedicated best-practices callable was not exposed in the available toolset.
Guidance-only routing attempts returned unavailable; none executed a resource
operation. The local Azure diagnostics and Python fact-grounded coding skill
instructions were reviewed instead. No successful best-practices response is
claimed.

Configured existing interpreter: Python 3.13.1 at
`C:/Program Files/Python313/python.exe`. No installation was needed. Reviewed
the existing unit conftest: synthetic configured catalog/inventory, in-memory
SQLite, synthetic JWT identity, and fake APIM. No production or accepted-model
guard was weakened; no conftest modification or accepted22 evidence fabrication
was needed. Dedicated APIM client fixtures use `Settings(_env_file=None, ...)`.

The final run blocked real `DefaultAzureCredential.get_token`, external socket
connections, and external DNS; only local TestClient loopback/socketpair support
was allowed. This is a process-local test harness, not a production setting.
The worker suite exercised synthetic unit functions only, not a deployment
controller or live publication worker. Terraform-render/controller guard suites
were intentionally excluded. No esbuild, Vite, Vitest or Ruff was run.

| Suite | Passed |
| --- | ---: |
| [APIM diagnostic regressions](../tests/unit/test_apim_publisher_diagnostics.py) | 49 |
| [Existing fragment encoding/signed operation regressions](../tests/unit/test_fragment_encoding.py) | 6 |
| [POC controls and public API regressions](../tests/unit/test_poc_controls.py) | 37 |
| [Gateway settings](../tests/unit/test_gateway_settings.py) | 35 |
| [Managed controls](../tests/unit/test_managed_controls.py) | 32 |
| [APIM and watermarks](../tests/unit/test_apim_and_watermarks.py) | 5 |
| [Synthetic publication worker](../tests/unit/test_publication_worker.py) | 5 |
| [Default limits](../tests/unit/test_default_limits.py) | 13 |
| **Total** | **182** |

Final result: **182 passed, 9 warnings in 27.19s**. Warnings are one existing
Starlette/AnyIO deprecation and eight existing Alembic `path_separator`
deprecations. Editor error checks on all changed Python files report no errors.

Earlier local attempts are not silently relabeled: a PowerShell native `-c`
quoting failure ran no tests; the first stdin harness reported 49 passed and
20 setup errors because this Windows socket module lacks `AF_UNIX`. Using
`getattr(socket, 'AF_UNIX', -1)` fixed only the test harness. The corrected
focused run passed 69 tests; the expanded intermediate run passed 174; final
additional request-count/redaction tests bring the complete selection to 182.
No cloud operation or historical controller was retried.

### Exact final command (PowerShell, repository root)

```powershell
@'
import sys
import socket
from collections import Counter
sys.path.insert(0, 'services/control-plane/src')
import azure.identity

def deny(*args, **kwargs):
    raise AssertionError('Offline tests forbid real credentials/external network')

azure.identity.DefaultAzureCredential.get_token = deny
connect = socket.socket.connect
getaddrinfo = socket.getaddrinfo
socket.socket.connect = lambda sock, address: connect(sock, address) if sock.family == getattr(socket, 'AF_UNIX', -1) or (isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')) else deny()
socket.getaddrinfo = lambda host, *args, **kwargs: getaddrinfo(host, *args, **kwargs) if host in ('127.0.0.1', '::1', 'localhost') else deny()
class Counts:
    def pytest_collection_finish(self, session):
        print('\nCollected per suite:', dict(Counter(item.path.name for item in session.items)))
import pytest
sys.exit(pytest.main(['-q', '--tb=short', 'tests/unit/test_apim_publisher_diagnostics.py', 'tests/unit/test_fragment_encoding.py', 'tests/unit/test_poc_controls.py', 'tests/unit/test_gateway_settings.py', 'tests/unit/test_managed_controls.py', 'tests/unit/test_apim_and_watermarks.py', 'tests/unit/test_publication_worker.py', 'tests/unit/test_default_limits.py'], plugins=[Counts()]))
'@ | & 'C:/Program Files/Python313/python.exe' -B -X utf8 -
```

## Remaining work — not authorized or performed here

Any cloud release, live diagnostic capture, content-changing acceptance,
save/reconcile, exact restoration, or activation requires separate approval and
its own protected-baseline plan. Do not replay old controllers. If a future
approved runtime emits these diagnostics, use its actual fixed reason/substage
and bounded facts to investigate the observed branch; do not infer a live cause
from synthetic tests. Initial-save HTTP200 reliability and separately scoped
activation remain unproven. Missing provisioningState must not be accepted as
a speculative repair. See retained
[October29 evidence](poc-controls-recheck-20261029.md).