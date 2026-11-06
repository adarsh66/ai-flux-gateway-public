# Private recovery complete — original118; local closure121

## Outcome and authority

The user-approved **private diagnostic deployment is complete**, not pending another
runner or approval. Original118 created its exact five temporary resources once,
read the authoritative published revision13 with exactly two fixed read-only
SELECTs, completed rollback and close, retained encrypted evidence, then removed
all five resources. No application or portal release occurred. This does **not**
mean the settings publisher, historical HTTP502, or portal Save acceptance is fixed.

Authority remains [APPROVAL16](../.deployment/poc-controls-private-recovery-20261105-01/APPROVAL16.json)
and [APPROVAL57](../.deployment/poc-controls-private-recovery-20261105-01/APPROVAL57.json).
The exact root-start acknowledgement was: **“i approve starting briefly as root.
Proceed with the deployment”**. It covered a brief root launch before verified
privilege drop, exact-pinned private runner, five temporary resources, two fixed
read-only SELECTs, encrypted evidence, bounded parent-finally and independent
local cleanup. It did not waive technical gates or authorize app release, RBAC,
public database/SCM changes, or blind APIM overwrite. No invented separate118
approval is needed or asserted.

## Actual118 evidence

- [CREATED118](../.deployment/poc-controls-private-recovery-20261105-01/CREATED118.json):
  passed 05:15:31UTC, one incremental PUT, exactly the reviewed five IDs.
- [READ118](../.deployment/poc-controls-private-recovery-20261105-01/READ118.json)
  and [FINAL118](../.deployment/poc-controls-private-recovery-20261105-01/FINAL118.json):
  `row13_read_rolled_back`, renderer succeeded, exit0; actual submitted2/completed2,
  connect1, identity request1/HTTP200/verified, `JWT_OK`, rollback-close complete.
  `ATTEMPT_FINISHED` alone is lifecycle status; the nested read receipt proves success.
- [ROW118 encrypted evidence](../.deployment/poc-controls-private-recovery-20261105-01/ROW118.enc.json):
  ciphertext SHA256 `ce0242add9015f3c307872e7d48673472c0904f9ad06e73629c28c0875cd64ee`.
  Operator-only key remains outside the workspace; no plaintext row/XML/token or
  claim values were written by local analysis119/audit120/audit121.
- [CLEANUP118](../.deployment/poc-controls-private-recovery-20261105-01/CLEANUP118.json)
  and [watchdog result](../.deployment/poc-controls-private-recovery-20261105-01/WATCHDOG118-RESULT.json):
  cleanup complete, **five actual final404**, outstanding IDs empty, errors empty;
  ACI, dedicated subnet, NSG, NAT and public IP absent. Standalone SAL DELETE0,
  kills0/waivers0. [Watchdog completion](../.deployment/poc-controls-private-recovery-20261105-01/WATCHDOG118-COMPLETION.json)
  exit0. No temporary resource remains in these actual readbacks; billing may lag.
- [POST118](../.deployment/poc-controls-private-recovery-20261105-01/POST118.json):
  full46 PASS at **05:16:59UTC**, root167/child206, unchanged state hashes,
  settings hashes, all22 routes and all four immutable image pins:
  API `cdc16f8d…6180a7`, admin `4a6a7097…2757fc`, customer `c564c97e…8e1fa8`,
  ingestion `995c8137…09e196`. These are retained post118 observations, not fresh
  cloud reads made during this local-only closure.

## Verified token blocker and minimal correction

[READ110](../.deployment/poc-controls-private-recovery-20261105-01/READ110.json)
retains `JWT_TID`: IMDS returned HTTP200, audience/client/principal/time checks
matched, but the expected tenant pin did not. Actual submitted0/completed0/connect0
are explicit counters, not a legacy initialized SELECT count. Original104's
generic `IMDS_TOKEN` did not preserve the precise failed check, so do not retroactively
claim every historical failure had a separately proven cause.

[IDENTITY116](../.deployment/poc-controls-private-recovery-20261105-01/IDENTITY116.json)
is the retained normal ARM UAMI-resource metadata proof, not an expectation derived
from an untrusted JWT. It confirms the exact attached UAMI client/principal and
tenant. [PREPARED116](../.deployment/poc-controls-private-recovery-20261105-01/PREPARED116.json)
proves that **only the erroneous expected tenant configuration field changed**.
Modules, original verifier, native launcher/transport and RUNTIME75 source/package
pins remained unchanged. No token claim check was removed or made permissive:
audience, tenant, principal, client, expiry and not-before remain bound; the
original verifier remains the final local claim gate. Local parsing is not JWT
signature validation; PostgreSQL authenticates the IMDS-issued token. Original118
then actually passed all checks and read successfully. No token/claim values are
reproduced in this completion document.

## Validation counts — distinct evidence, not an inflated runtime total

| Retained evidence | Actual coverage/result |
| --- | --- |
| [NATIVE101](../.deployment/poc-controls-private-recovery-20261105-01/NATIVE101.json), original Linux no-push cm7u | **13 tests**, 0 failures/errors/skips; static ELF, hostile-loader negative control, exact retained loader after verified drop; UID/GID1000, empty groups, zero capabilities, NNP1 |
| [OFFLINE100](../.deployment/poc-controls-private-recovery-20261105-01/OFFLINE100.json) / [PREPARED102](../.deployment/poc-controls-private-recovery-20261105-01/PREPARED102.json) | **15 mocked protocol cases**, also embedded after verified native drop; not 15 live identity calls |
| [PREPARED116](../.deployment/poc-controls-private-recovery-20261105-01/PREPARED116.json) | **20 local tests** = 12 claim tests + 8 tenant/cache/cleanup-provenance tests; embedded15 and native13 referenced, not added as new distinct runs |
| [PREPARED102](../.deployment/poc-controls-private-recovery-20261105-01/PREPARED102.json) | **10 offline cleanup regression tests**, not ten live cleanups |
| [VALIDATED117](../.deployment/poc-controls-private-recovery-20261105-01/VALIDATED117.json) | Checkov **3 pass/0 fail/0 skip/0 parse errors**, five resources; ARM validate Succeeded; what-if exact five creates |
| Original118 runtime | **1 identity request, 1 DB connect, exactly 2 SELECT submissions and completions**, rollback-close; five actual cleanup404; full46 postguards |
| [AUDIT121](../.deployment/poc-controls-private-recovery-20261105-01/AUDIT121.json) | **8 parser/type fixture checks**, plus actual retained-value semantic classification; no cloud/native build/SQL |

No native build, SQL or consumed test/analysis/audit entrypoint was replayed here.
Static launcher SHA256 remains
`6bbd8cc8d12cb0758269fa62da101f2323b7960e6283e4c6c45cca57a2463aa9`.

## Exact pre-write409: structural and semantic findings

[ANALYSIS119](../.deployment/poc-controls-private-recovery-20261105-01/ANALYSIS119.json)
authenticated ROW118, verified both immutable image source trees against
RUNTIME75, and reproduced the in-run exact deployed renderer locally. Revision13
is published, with three stored bindings. Its complete rendered XML does **not**
match the retained fresh post118 APIM `format=xml` export. The deployed APIM client
uses that XML contract; rawxml is retained but not parseable without repair, and
was not silently repaired or substituted.

[AUDIT120](../.deployment/poc-controls-private-recovery-20261105-01/AUDIT120.json)
executed the exact deployed `save_poc` pre-write guard AST locally against that
actual row/export: **HTTP409, “APIM settings drift detected; operator review
required”**. All **six binding-order permutations failed to match**. The sole
structural difference is the `value` attribute at
`fragment/0:choose/0:when/0:set-variable`.

New unique [audit121 source](../.deployment/poc-controls-private-recovery-20261105-01/audit121.py)
ran once, only after strict local workers and retained cleanup/post gates passed.
It decrypted ROW118 only in memory through the existing helper, verified encrypted
and clear hashes, reloaded exact image definitions, and used the deployed
`auto_pricing.envelope`/`validate_projection` contract. A strict parser admitted
only the exact C# verbatim-string-literal wrapper and doubled quotes: **no C# eval,
no arbitrary expression execution**, no duplicate JSON keys/nonfinite numbers.
Recursive typed comparison preserves arrays and distinguishes booleans, integers,
decimal numbers, strings and null, rather than relying on Python `True == 1`.

**[AUDIT121](../.deployment/poc-controls-private-recovery-20261105-01/AUDIT121.json) PASS05:22:13UTC:**

- Variable: **`aiflux-auto-price-projection`** — validated Auto **internal-pricing
  JSON projection** in the price-only branch, not model generation settings.
- **Not semantically equal; not mapping-key-order-only.** No mapping-order
  differences were found. The only differing semantic key paths are
  **`$/pool_version`** and **`$/sha256`**, both closed type `str`.
- All other fields, including the complete prices mapping, match under the typed
  comparison. Both projections pass the original deployed shape/hash validator;
  that validator validates internal integrity, **not which pool version should
  currently be authoritative**. Neither projection is declared correct merely
  because it passes this validator.
- First decoded JSON difference: zero-based character17, digit versus digit.
  No raw differing values or surrounding XML/JSON are disclosed.
- Expected rendered fingerprint
  `319a3b77bf5c61b9f0446c0d28dc6ccadb9f3df5da96627915b60a8ea63b4475`;
  retained APIM fingerprint
  `a5119022b806ae955fbc555377acf741ea7c96fa62ad99012f99f13b28efd1d8`.
  Per-value and typed-normalized hashes are retained in AUDIT121.

## What next — candidate, not an authorized blind repair

The observed defect boundary is **stored applied Auto pool-binding metadata versus
the deployed fragment**, not binding order or general JSON serialization. The
exact renderer reads `stored.auto_pricing.applied`; the envelope uses sorted compact
JSON and a projection integrity hash. A serialization-order-only change would
therefore not address this observed mismatch.

Minimal next candidate: review the retained intended gateway pool/capability
version and the corresponding Auto pricing publication lineage against row13's
applied projection, then add a source-bound regression reproducing these exact
two metadata differences and the pre-write409. Determine which producer/publication
transition failed to keep the applied envelope synchronized **before** choosing a
repair. If a repair is justified, use the normal audited, version/CAS/ETag-protected
publication path under a separately reviewed precise scope, preserving equal prices,
controls, all22 routes and append-only history. Do not ignore `pool_version`/hash,
weaken the XML drift guard, rewrite history, blindly reconcile, or directly PUT XML.
This closure neither identifies the drift actor/transition nor proves the older
HTTP502 cause. Initial content-changing Save and exact restore acceptance remains
unexecuted; **no portal Save was attempted here**.

## Local closure safety

New audit121 start/completion strict-worker snapshots passed, blockers empty,
kills0/waivers0; no competing cloud controller was active. Its network audit hook
denied socket/HTTP activity. Local process/ACL checks only; cloud calls0, credentials
acquired0, SQL0, builds0, creates0, DELETE0, app/DB/APIM/history edits0. Existing
analysis119/audit120 and every old consumed stage remain immutable/no replay.
The current handoff supersedes the stale leading original104 status, retaining
historical receipts and limitations below it.