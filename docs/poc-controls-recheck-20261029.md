# Gateway publisher quick recheck — 2026-10-29

## Authoritative November5 — normal sign-in succeeded; HTTP409 drift blocks Save

One actual normal gateway Save RPM60→59 expected13 returned409 drift pre-write,
before new revision/publication. Current13/published13/original configuration
unchanged. No restore needed; safety test not attempted; HTTP502 not established
gone. Normal sign-in succeeded this resumed turn: expired auth is not the blocker.
Retained POST27 full46 PASS original fragment Succeeded/ETag unchanged, allpins/
root167child206 hashes/all22/Auto4096/pricing protected. Only authorized exact
storage IP167.103.65.34 rule added/verified14. Strict workers pass kills0waivers0.

Offline31 exact-parent save_poc/render_revision/migrate preserved; old/current
price-only envelope fingerprints identical. Six binding orders yield six
fingerprints but stored row13 binding order/Auto envelope NOT obtained, so no
proven root cause. Retained33 scan10866 files found no authoritative DB row13.
History read-only configuration omits stored bindings/Auto envelope and cannot
prove mismatch. Authorized SCM availability probe403: remotecommands0,
productionwrites0/no database read access established.

Future prerequisite, not authorization: private READONLY exact
GatewaySettingsRevision(scope dev-unified,version13).configuration + base
information/hash/ETag or equivalent authoritative stored render/fingerprint via
existing private-network audited channel. No widening SCM/PG/network/RBAC just
to finish; no drift bypass/direct fragment overwrite/history deletion/rewrite/
reconcile attempt. Preserve consumed scripts/receipts; no replay. Local-only
final documentation update performed no cloud/browser/commands/requests/further
investigation/new tests/publication. Blocked, not complete; no task completion.
See [latest report](../.deployment/poc-settings-live-20261105-01/FINAL.md) and
[latest machine status](../.deployment/poc-settings-live-20261105-01/FINAL.json).

## Historical November5 00:10UTC authentication stop — superseded above

Diagnostic API cdc16 is deployed once; November4 source-only notes below are
historical. User now authorized stricter temporary gateway/safety portal edits
and exact restores, but normal Refresh returned **401 Invalid access token**
at2026-11-05T00:10:08.489Z. Zero Save/Reconcile requests in this continuation;
initial-save502 reliability remains unverified, both pairs unexecuted.
Fresh06 ordinary ARM credential command also failed before full collection;
precise cause unproven, not retried. Latest completed protected proof BASELINE05:
Nov4 23:15UTC full46/root167/child206/allfourpins exact. No whitelist or other
network/security/enforcement/inference changes. Normal admin sign-in required.
See [current checkpoint and safe unconsumed continuation](../.deployment/poc-settings-live-20261105-01/FINAL.md).

## Later continuation — 2026-11-04 bounded reads, no live publication

Current ordinary gateway/safety GETs are200 at version=published_version13;
actual fragment XML/rawxml GETs are200/Succeeded with ETags. Root166/child206
and four deployed pins match the retained checkpoint. Existing active-policy
POC inclusion differs from the detached October29 history; no new activation
occurred. Therefore no speculative missing-state success change was made.
The local logger now separates observed response_status from synthetic-capable
error_status and distinguishes explicit null/absent state. **209 tests passed,
9 warnings; not deployed.** Historical502 branch remains unproven. See
[new receipts, references and validation](poc-publisher-response-shape-20261104.md).
Earlier implementation-only and October reproduction sections remain historical.

## Implementation-only update — 2026-11-04 (local, not live acceptance)

Added closed-vocabulary APIM failure diagnostics and local regression tests;
**the historical HTTP502 cause remains unproven and activation remains blocked**.
The existing exact-resource readiness behavior was retained, including rejection
of missing provisioningState and known terminal failures. No async success
criterion, ETag/CAS/fingerprint protection, retry budget or request scope changed.
The existing POC stage log now includes re-filtered structured safe reason,
substage and bounded metadata, with outer drift/readback failures distinguished.

Final guarded local Python regression run: **182 passed, 9 deprecation warnings**
across eight suites. No cloud requests/build/deployment, live save/reconcile,
activation, production task or historical controller replay occurred. Existing
root166/child206 and pricing API0c01/admin4a6 checkpoint identifiers are carried
forward without a fresh live read; Feature2 remains paused. These tests are not
initial-save HTTP200 reliability acceptance or proof of a repaired live defect.
See [implementation, exact test command and limitations](poc-publisher-diagnostics-20261104.md).
All October evidence below is retained unchanged as historical evidence.

## Completed content-changing test — 01:26 UTC (supersedes initial preflight below)

**HTTP502 reproduced twice. Publisher reliability remains a blocker to safe
activation. Exact pre-test configuration is restored and published as revision12.**

After the user identified revision10 as their failed test and authorized recovery,
the existing revision was retained in audit history, not deleted. Fresh GETs
confirmed revisions9/10 have identical visible settings. Independent readback
confirmed the detached fragment matches those settings with its current bindings;
historical stored binding equality was not assumed. The existing version-locked
reconcile was authorized recovery, not claimed to be a PUT-free operation.

| UTC timestamp | Operation | Actual result |
| --- | --- | --- |
| 01:14:05.875 | Reconcile existing revision10 | HTTP200; version=published_version10, published, errornull |
| 01:14:28.590 | Initial content-changing save: default RPM60→59, preserving all other settings | **HTTP502**, 2698ms; revision11 failed, published10 |
| 01:15:30–01:17:19 | Independent APIM readback | Exact intended RPM59 render stored, Succeeded; only RPM changed, all other protected fields unchanged |
| 01:18:01.842 | Reconcile verified revision11 | HTTP200; version=published_version11, published |
| 01:18:09.454 | Initial restoration save: RPM59→60 | **HTTP502**, 1223ms; revision12 failed, published11 |
| 01:19:44–01:22:55 | Independent restoration readback | Fragment byte-identical to exact pre-test baseline; all13 protected components equal original |
| 01:24:07.217 | Reconcile verified restoration revision12 | HTTP200; version=published_version12, published, errornull |
| 01:24:14.008 | Fresh ordinary authenticated settings GET | HTTP200, desired=published exact original configuration; enforcementfalse |
| 01:25:19–01:26:41 | Independent final post-reconcile readback | Original raw/XML bytes and all13 protected components match; detached, Succeeded; final audit passed01:26:44 |

The original captured configuration—not revision8 defaults—was restored: global
RPM60/TPM2048/daily tokens10000/calls1000; global thresholds1/1/1/1, mandatory
scans; existing organization self-harm0 override and all ordered bindings retained.
Final canonical fragment hash is
`36af0cecf7ed9482ff8807f44474862c15dfa363918fc6d35e455b0ec6ae9edc`;
raw bytes hash `09c8c268d63490daeff42d8fbd414fd564743c325c32f72d7c553197f3b0896f`.

Both failures used the normal portal gateway form and version-locked API. APIM
stored the intended content despite initial502; later reconciliation returned200.
This reproduces the earlier shared publisher failure pattern. No additional
content-safety save was needed or performed after reproducing the common failure;
that page's content-changing save is not separately reverified. Exact caught
exception stage/status remains unknown: optional read-only log collection returned
HTTP504, with no logging changes or retry. This is not a proven permissions,
async-header, readiness or transport root cause.

Evidence:
- [Revision11 readback](../.deployment/poc-revision11-readonly-20261029-0115280360287-21404/readiness.json)
- [Exact restoration audit](../.deployment/poc-restoration-readonly-20261029-0119418708893-21404/independent-exact-response-audit.json)
- [Final post-reconcile readback](../.deployment/poc-final-postreconcile-readonly-20261029-0125167247328-26844/readiness.json)
- [Final independent audit](../.deployment/poc-final-postreconcile-readonly-20261029-0125167247328-26844/independent-completion-audit.json)

No revision was deleted, no policy activated and no inference sent. All image
pins, settings, policy/counters, role/network/FinOps baselines remain unchanged.
No firewall rule was added for167.103.63.12. Next work is targeted sanitized
publication-stage diagnostics and an evidence-based fix, not activation or
another speculative deployment. Earlier preflight findings below are retained
as history and do not describe the final restored state.

## Result

Fresh read-only checks completed. **The publication blocker remains unresolved;
no new content-changing HTTP502 reproduction was attempted.** The authorized
save-and-restore test stopped at its prerequisite gate because an existing failed
head was discovered. No save, reconcile, retry, restoration or activation occurred.

## Current authenticated portal evidence

At **2026-10-29T01:05:49.911Z**, the ordinary admin UI refresh received HTTP200
from GET `/api/admin/gateway-settings`:

- Scope `dev-unified`: **version 10, published version 9**.
- UI publication status: **failed**; message: “Optional overrides publication
  incomplete; reconcile to retry. Default access is not gated.”
- POC controls enabled; managed V2 disabled; **enforcement_enabled=false**.
- Revision history identifies revision 10 as “Automatic optional organization
  ownership refresh,” displayed at 2026-10-28 18:38:44 in the browser's local
  timezone. Revision 9 is published, reason “testing content safety,” displayed
  at 18:23:08. A published revision alone does not prove its initial save was200;
  earlier successful reconciliation can also publish a previously failed save.

The failed revision prevents `save_poc()` from accepting a new revision: it
requires the existing head to be published and otherwise returns409 before
the conditional fragment PUT/readiness path. Testing a new save here would not
meaningfully test the earlier502. Automatically reconciling revision10 could
publish its ownership changes and would exceed this bounded test's clean-baseline
prerequisite. No such action was taken.

## Independent management-plane evidence

Fresh collection **01:02:14–01:03:49 UTC**, audited at01:04:45:

- Active policy has **zero fragment includes**; fragment remains detached.
- APIM and fragment provisioning are `Succeeded`; rawxml/xml canonical semantics
  agree, with ETag present and matching between exports.
- The current fragment retains an existing conditional self-harm threshold0
  override. Historical revision8 defaults are not the current restoration target.
- Deployed API/admin/customer/ingestion pins match the completed releases.
- No mutation workers observed; all34 recorded historical marker hashes unchanged.
- Active policy SHA256:
  `e45b6de7b61b29a4085b4569609da48314d9c144306a9c02211d1ce58ce5b456`.
- Fragment publisher-canonical SHA256:
  `36af0cecf7ed9482ff8807f44474862c15dfa363918fc6d35e455b0ec6ae9edc`.

Evidence: [.deployment/poc-publisher-recheck-20261029-0102114890616-21892/readiness.json](../.deployment/poc-publisher-recheck-20261029-0102114890616-21892/readiness.json),
[completion audit](../.deployment/poc-publisher-recheck-20261029-0102114890616-21892/completion-audit.json),
[protected snapshot](../.deployment/poc-publisher-recheck-20261029-0102114890616-21892/protected-snapshot.json).

## Interpretation and next step

The last directly observed initial-save502 remains the historical October28
failure; current failure status does not establish its exact HTTP status or cause.
The current failed publisher head is nevertheless a real blocker to a safe new
publication test and subsequent feature activation. Healthy GETs/APIM provisioning
and detached fragment storage do not clear that gate.

Next, review revision10's desired configuration and exact rendered ownership
bindings against current APIM content and revision9. Only after explicit recovery
scope is established should the existing version10 be reconciled or another
audited recovery be undertaken. Then repeat the bounded content-changing
save-and-exact-restore test before considering separately validated activation.

No firewall rule was added for167.103.63.12. No role, image, live configuration,
policy, fragment, database schema, key, counter or FinOps change; no inference.
Existing API/Playground availability was not load-tested or otherwise newly
asserted; the original active policy was confirmed unchanged.