# Both-MI blocked probe: offline investigation — 2026-10-27

## Follow-up: confirmed session predicate defect, source-only fix

**Offline only. No new cloud calls, database connections, builds, provisioning,
grants, writes, or retries. The corrected image `05a9ff859f48` and its retained
execution/cleanup evidence have not been modified. This source fix is not in
that image and is not new live database proof. Stop the costly runner loop.**

The actionable source defect is **search-path string formatting**, not a
read-only boolean conversion, isolation spelling, or demonstrated missing grant:

- Startup options set `search_path=public,pg_catalog` (no comma space).
- The old exact six-column tuple demanded `public, pg_catalog` (comma space).
- PostgreSQL `search_path` is a string GUC. `current_setting()` returns its text,
  not a pretty-printed schema array. The real installed psycopg **3.2.9**
  `TextLoader(25)` preserves the supplied comma spelling; libpq conninfo parsing
  preserves the startup option. It does not insert a space.
- The new offline regression **failed before the fix** with
  `database_session_proof`. Hash-checked retained image source reproduces the
  exact **189 bytes / SHA-256 e371609eebb403db74832defdafdf8d90bfd0595e093f7fdb000860f878ef6e8**
  seen for both MIs using this documented wire value. A different failed database
  field produces identical bytes: **the actual returned row/first failing field
  in the historical attempt is still unknown**. These are synthetic inputs
  decoded by real driver loaders, not a local PostgreSQL server or live query.
- Both the old unit cursor and build-only Linux cursor invented the spaced
  spelling. The Linux contract source now derives the unspaced value from actual
  parsed startup options and decodes it with `TextLoader`; no Linux build ran.

### Exact query and finite invariant results

The query remains unchanged: `SELECT current_database(), session_user,
current_user, current_schema(), current_setting('search_path'),
current_setting('transaction_read_only')`. The preceding command remains
`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`.

| Column / SQL output contract | PostgreSQL type → psycopg type | Required value / equality | New failure reason |
| --- | --- | --- | --- |
| `current_database()` | `name` → `str` | exact configured target | `database_session_database` |
| `session_user` | `name` → `str` | equals selected MI login role, compared in memory | `database_session_session_user` |
| `current_user` | `name` → `str` | equals the same selected role, no role switch allowed | `database_session_current_user` |
| `current_schema()` | `name` → `str`, or SQL NULL → `None` | `public` | `database_session_schema` |
| `current_setting('search_path')` | `text` → `str` | **only** `public,pg_catalog` or `public, pg_catalog` | `database_session_search_path` |
| `current_setting('transaction_read_only')` | `text` → `str` | `on`, **not** Python `True` | `database_session_read_only` |
| Row shape | default psycopg `tuple` | exactly six columns | `database_session_shape` |

These are expected contracts, **not recovered historical SQL outputs**. The
first failed invariant is emitted as the fixed `reason` above with
`stage=database_session`, `exception_type=ProbeBlocked`, `sqlstate=null`,
`database_writes=0`, `replay_authorized=false`. No new output fields, raw rows,
user/host/DSN values or arbitrary exception messages. Both sanitizers allow only
these finite labels and still accept the historical generic label. SQLSTATE is
null because this is a Python assertion after a returned SELECT, not a server
SQL error. A real PostgreSQL boolean (e.g. `pg_is_in_recovery()`) is OID16 →
Python `bool`; it is not interchangeable with a `current_setting()` text value.

`current_setting('transaction_isolation')` / `SHOW transaction_isolation` would
return text `repeatable read`, not `repeatable_read`, after this SET; `serializable`
is a different level. **Neither isolation output nor `pg_is_in_recovery()` is
selected or compared by this six-column predicate**, so neither explains this
specific source rejection. The regression checks actual driver text/bool loader
types, without pretending to execute those SQL functions. TLS is enforced by
libpq `verify-full` plus CA and hostname/private hostaddr; the predicate does not
query `ssl`, `pg_stat_ssl` or TLS metadata. A server SSL-capability setting alone
would not prove this session negotiated TLS. No TLS requirement was weakened.

Only the two fixed equivalent search-path spellings are accepted: no general
string coercion, arbitrary whitespace normalization, `$user`, extra/quoted
schemas, or path reordering. Database, both role identities, schema, transaction,
non-superuser/no-DDL/no-owner and table privilege requirements stay intact.

### Why FinOps remains blocked; actionable database review

The source can falsely reject a normal startup path **before any role/grant or
usage query**. Correcting it does not establish that either MI has the required
effective database privileges, that ingestion ran, or that usage/checkpoints/
prices exist. No rows/token totals should be reported as zero on this evidence.

`current_schema()` is the first usable existing schema on the search path. For
a non-superuser lacking `USAGE` on `public`, PostgreSQL can skip it and return
`pg_catalog` (or return NULL if no usable path). That would be a **real**
`database_session_schema` failure, not grounds to accept another schema or grant
CREATE/superuser. Missing `public` or role mapping has not been observed here.
An Entra display/login role and effective PostgreSQL role need not be assumed
equal: this probe deliberately requires both to match the selected login. Any
different mapping/SET ROLE design must be verified, not silently allowed.

Use the **existing approved database/operator path** for a bounded, read-only
catalog review: verified MI-to-database-role mapping; usable `public` schema;
effective SELECT on all five tables; ingestion INSERT/UPDATE/DELETE on the three
write tables; no superuser/CREATEDB/CREATEROLE/BYPASSRLS, CREATE or ownership.
Check inherited privileges as well as direct grants. Azure role assignments are
not proof of PostgreSQL grants. Restricted metadata/view access may require an
appropriate existing database administrator or a reviewed boolean-only view;
do not grant broad runtime access just to expose diagnostic metadata. **Verify
first; no GRANT/DDL is proposed or executed.** Runner approval already exists;
re-provisioning it cannot resolve an unverified database-role/grant contract.

References for the documented contracts (not fetched or queried during this
offline investigation): PostgreSQL [session information](https://www.postgresql.org/docs/16/functions-info.html),
[current_setting](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SET),
[search_path](https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-SEARCH-PATH),
and [transaction settings](https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-TRANSACTION-ISOLATION).

Source: [strict session verifier](../scripts/deployment/finops_private_probe.py),
[finite sanitizer](../infra/finops-runner/entrypoint.py),
[corrected synthetic Linux contract](../infra/finops-runner/linux_contract.py),
[offline real-loader and main-entrypoint regressions](../tests/unit/test_finops_session_contract.py).

### Actual offline verification

- **422 tests passed**, zero failures/errors/skips, **31.791 seconds**: all
  original **397** plus **25** new regressions. Independent JUnit case-multiplicity
  comparison confirms preservation (only time-dependent synthetic JWT parameter
  labels are normalized for that comparison). The focused suite passed 149 tests.
- Tests execute the actual probe `main()` with explicitly synthetic credential/
  database transports for all six field failures. Each produces nonempty exact
  finite JSON, null SQLSTATE, rollback and no later role/data queries; both
  sanitizer boundaries preserve its precise reason. Real psycopg text/name/bool
  loaders and real libpq parsing are used; no server observations are invented.
- The pre-fix valid-startup regression failed; the fixed regression passes.
  Unsafe/reordered/extra/quoted paths, wrong login/effective role, inaccessible
  schema, boolean-instead-of-text read-only value and malformed row remain blocked.
- Original 397-test JUnit SHA-256 remains
  `d7ef31a6eb9166ad91382b60d3a9bb6dee01f3b51afb706954824c05490eb1b9`;
  corrected outcome SHA-256 remains
  `83c7ab00414d0f3d7c0b25566b6089f34d32ce15fcd14cc663a5d1f826bcd74b`.
  Both retained corrected image source hashes are checked by regression. Existing
  cleanup proof still records zero outstanding IDs; **no fresh cloud GET ran**.
- No editor diagnostics in changed source/tests/docs; scoped whitespace check
  passed. The Linux contract was source-reviewed, not rebuilt or executed here.
- New separate [422-test JUnit](../gateway/validation/finops-session-contract-offline-tests-20261027.xml).
  Existing build/execution/cleanup/test reports were not overwritten.

## Latest authorized corrected attempt — 03:11 UTC

**One corrected attempt per MI completed. Both returned a concrete finite
session-proof blocker; all six temporary resources are deleted and independently
GET404 verified. No rerun, permission expansion or application release.**

The newer explicit user approval superseded the historical no-execution scope
below. Image session `05a9ff859f48`; isolated runtime session `3788be5dd201`.
The old build, both old execution/final proofs and their session files remain
separate. Both old watchdog processes were observed active and were not stopped;
all current IDs, including the subnet, are disjoint from both previous sessions.

### Actual corrected build and validation

- Existing approved ACR, **one** build `cm1j`, Linux/amd64, actual **2 CPUs**,
  900-second timeout. Actual build 03:00:07.663559–03:00:45.620338 UTC,
  **37.956779 seconds**. Immutable probe digest
  `sha256:a481ce88f7562047659756ff932a6a50ed6b5ee5ddfa4029c20a5c12980eedae`;
  compressed size **80,929,306 bytes**, below 1 GB. No application image built.
- Probe hash `4b46a88af661066d68c4a3e3ea3a136862d511c5553c9664daf95e47c7d5730c`;
  supervisor hash `e4cfe0aac2c7b2c67233ae1dd2280875e947b49b7c9b8a488606c25a95186ce0`.
  The base digest, requirements, all 19 wheel hashes and transitive lock are
  unchanged. No dependency or application-source upgrade.
- The exact Dockerfile executes the hash-bound build-only native contract as
  UID 65532: real Linux binary psycopg/libpq imports, readable nonempty CA/trust
  bundle, exact pinned identity/MSAL/PyJWT/SQLAlchemy versions, synthetic selected
  MI transport with sockets/DNS forbidden, libpq options parsing, real numeric
  loader integral conversion, rollback-only synthetic cursor contract, UTC
  serialization and both sanitizer boundaries including bounded failures.
  **No PostgreSQL connection or external SDK request in build validation.**
- Fresh Checkov 3.2.495: **3 ARM + 64 Dockerfile checks passed**, zero failures,
  skipped checks or parsing errors. This is scoped IaC/Dockerfile scanning, not
  an image-CVE or universal security guarantee. The explicit management ingress
  exception is TCP19390 only from 10.240/16 to 10.240.5/24; all other inbound is
  denied, no application listener/public runner. HEALTHCHECK NONE is deliberate
  for a non-retrying one-shot; existing Azure outbound service tags are retained.
- **390 tests passed before build; 397 passed after execution**, zero failures,
  errors or skips; one existing Starlette/AnyIO warning. Added seven coordinator
  isolation/native-contract tests. Final runtime **30.69 seconds**.

### Actual once-only probe results

Both MIs independently returned accepted **failure-schema JSON**, not accepted
database-readiness snapshots: `status=blocked`, `stage=database_session`,
`exception_type=ProbeBlocked`, `reason=database_session_proof`, `sqlstate=null`,
`database_writes=0`, `replay_authorized=false`. Both outputs are **189 bytes**,
SHA-256 `e371609eebb403db74832defdafdf8d90bfd0595e093f7fdb000860f878ef6e8`.
Both containers terminated OS0, supervisor acceptance exit2, **zero restarts**.

- Ingestion result collected **03:05:57.722343 UTC**, persisted before deletion;
  its group independently GET404 **03:05:58.772450**, before API creation
  **03:06:31.169147**. Ingestion observed PUT-response-to-GET404 lifetime
  **80.752940 seconds**; API **61.787738 seconds**.
- API result collected **03:07:32.138704 UTC**, persisted before deletion;
  API group GET404 **03:07:32.956885**.
- This fixed guard is reached only after the private-address check, selected MI
  token/claim check, TLS database connection, read-only session setup and session
  metadata SELECT have returned. **One or more exact session tuple invariants
  failed. The individual failing field is not exported and remains unknown.**
  Do not reinterpret this as a DNS/MI outage, permission denial or a specific
  database/user/schema/search-path mismatch. Role/grant checks and aggregate
  queries were not reached: **grants, ownership dates, rows, token totals,
  checkpoint and prices remain unknown, not zero**. Historical 130-byte failures
  remain unknown independently of this new result.

### Ownership, deadline and cleanup

Fresh subscription/tenant/account/quota/provider, both MI bindings and existing
AcrPull were checked. ARM validate and what-if passed: network **exactly four
Creates**, no existing Modify/Delete; each bound group had its own single-Create
preview. The real detached synthetic watchdog cleanup test survived launcher
exit. The installed real watchdog is 60-minute, exact-session-hash-bound, with
eight minutes reserved for cleanup; each actual probe includes provisioning in
its ten-minute bound. The watchdog survives controller exit, **not workstation
loss**; this limitation remains explicit.

Created and deleted names (full exact ARM IDs and each timestamp are in the
linked outcome): prefix `poc-ids-token-ex-finops-probe-3788be5dd201-`, suffixes
`pip`, `nsg`, `nat`, `subnet`, `ingestion`, `api`. The actual subnet is nested
under the existing VNet; the parent VNet was never PUT. Four network objects
lived approximately **213–234 seconds**. Controller finally completed all-six
GET404 at **03:07:40.602334 UTC**; independent final verification at **03:07:59**,
then a separate GET-only outcome read confirmed all six at **03:10:43 UTC**.
Both old sessions' six IDs also returned GET404 at **03:10:49–03:10:55 UTC**.
**Outstanding IDs: none.** Old watchdog PIDs10156/2608 were not killed; new
watchdog remains installed. Controller and ownership-guard hashes did not change
during this attempt.

At **03:11:08 UTC**, PostgreSQL public access remained **Disabled**, firewall
rules **0**; state storage remained default **Deny** with exactly the existing
three approved IPs. No DB writes/DDL, role grants, manual/operator credentials,
settings/environment changes, timer, replay, app image deployment, inference or
quota reset. Existing model/GLM/auth/CORS/PII controls were not changed; relevant
source/contract regressions passed. Application-source hashes still match the
prior manifest; this does not assert new deployed API/UI FinOps acceptance.

### Actual work and cost — not zero or a billing cap

At retained reviewed retail rates, observed durations price to approximately
**USD0.01311135**: build **0.00759136**, NAT **0.00286244**, IP **0.00032563**,
both ACI creation-to-absence envelopes **0.00233193**. This is **not an invoice
or measured billed total**. Minimum billing increments, storage retention,
actual transfer/NAT bytes, private-link and tax are not measured; retained image
storage continues. The reviewed **USD0.778895 + 1 contingency = 1.778895**
scenario remains a planning scenario, **not a hard cap**.

### Finite next step, not another automatic runner

Retain this diagnostic as the one corrected attempt. Review the exact
session-proof contract offline; the follow-up above confirms a source false
predicate without recovering the historical row. Use finite per-invariant codes
and verified database-role/grant metadata, never raw metadata or broader runtime
permissions/network access. No automatic provisioning/probe retry.
Function configuration requires a precise proposed diff, explanation and separate
consent before edits. Activation cutoff stays **null**, source ownership is
unverified, replay stays dry-run only. Do not enable a timer, replay data or
release application images based on these blocked probes. FinOps remains
**not repaired** until actual deployed source/API/UI acceptance.

Evidence:
- [Corrected outcome, full resource IDs, lifetimes, costs and watchdogs](../gateway/validation/finops-corrected-outcome-05a9ff859f48.json)
- [Immutable image and context hashes](../gateway/validation/finops-corrected-image-05a9ff859f48.json)
- [Fresh validation/scanner/what-if](../gateway/validation/finops-fresh-preparation-3788be5dd201.json)
- [Actual execution and deletion events](../gateway/validation/finops-fresh-execution-3788be5dd201.json)
- [Independent final verification](../gateway/validation/finops-fresh-final-3788be5dd201.json)
- [397-test final JUnit](../gateway/validation/finops-corrected-final-tests-20261027.xml)

## Historical offline decision — 02:52 UTC (preserved scope)

**Source defects reproduced and fixed; historical runtime cause remains unknown.
The fix is not in any deployed or newly verified image. No new runner execution
is authorized by this investigation. Outstanding resource IDs: none in the
retained 02:40 UTC independent final verification.**

Session `9461fb0c1a35` produced identical 130-byte blocked ARM JSON for both MIs.
OS exit 0 is deliberate one-shot supervisor behavior, not SQL success. The
supervisor reduced every child failure and some valid successful snapshots to
`unverified_runtime_failure` / null SQLSTATE. The controller sanitized this
already-sanitized JSON a second time. No stage or exception type survived.

## Reproduced defect, not inferred permissions failure

PostgreSQL `SUM(bigint)` returns `numeric`; the probe explicitly casts token
inputs to `bigint` before summing. The actual psycopg `NumericLoader(1700)` returns
`Decimal`, including for integral values. The previous fake cursor returned
Python integers instead and missed this driver contract.

The historical probe serialized these values using `json.dumps(default=str)`.
Its supervisor required integer counts and therefore rejected the resulting
strings even when the database snapshot itself succeeded. The offline
[driver regression](../tests/unit/test_finops_probe_runtime.py) first failed on
`Decimal('11')` rather than `int`; it passes after the conversion fix.

The [historical reproduction](../tests/unit/test_finops_probe_diagnostics.py)
loads the retained old probe and supervisor only after checking both source
hashes against the existing image manifest. A synthetic snapshot with real
driver-shaped numeric values produces **exactly 130 bytes** and SHA-256
`b4fa436c81cd365dc673b823a466a84420a4311431a2990b521f9ba8e0db6282`, matching
**both** recorded ARM results. An unrelated swallowed `TypeError` yields the
same output. Thus matching bytes **cannot prove the historical probes reached
SQL**, and cannot distinguish aggregate rejection from DNS/MI/TLS/driver/schema
or privilege failure. No grant/RBAC change is justified.

## Dependency and query checks

- Verified all retained wheel SHA-256 values against the historical image
  manifest. An isolated child loads the exact retained **pure Python** wheels,
  including azure-identity **1.23.0**, MSAL **1.39.0**, and PyJWT **2.15.1**.
  The ordinary workstation PyJWT is **2.10.1**, so relying on local imports alone
  would not have tested the image's pinned JWT dependency.
- With socket connect/connect_ex and DNS forbidden, the real credential SDK
  successfully uses the selected client ID, PostgreSQL scope, fixed IMDS request
  shape and synthetic transport. Returned token is a string; the real probe's
  claim decoder accepts the synthetic three-part JWT. **No JWT decode API
  incompatibility was reproduced.** The probe uses base64/JSON, not PyJWT decode.
  This does not establish that actual ACI IMDS returned a token.
- Local psycopg **3.2.9**, SQLAlchemy **2.0.41** and their imports succeed. Real
  libpq accepts the reviewed `sslrootcert`, `verify-full`, hostname plus private
  `hostaddr`, read-only startup options and timeouts without connecting. A missing
  CA path fails before DNS/MI. The exact Linux CA bundle has not been freshly
  inspected, and Windows native libraries are **not Linux binary proof**.
- Existing `cm1h` evidence records Linux `pip check`, imports and libpq checks.
  No new Linux build or remote validation ran. Pinned dependencies and Dockerfile
  are unchanged. Existing image/source contexts were not overwritten.
- The probe uses **psycopg cursors**, `%s` placeholders and positional tuples,
  not SQLAlchemy 2 `Connection.execute()` with plain SQL or dictionary rows.
  SQLAlchemy is only a URL parser. Pydantic and the application are not imported.
  Query columns match the source models for usage, checkpoint, bindings and
  prices. This is source-schema consistency, not live migration/grant proof.
- UTC datetime and aggregate serialization pass through both sanitizers in the
  regression suite. Malformed JWT shapes/types, nonfinite expiry, invalid
  aggregates, missing imports and rollback errors are explicitly tested.

## Source-only corrections

1. [Probe](../scripts/deployment/finops_private_probe.py): losslessly convert finite,
   nonnegative, integral numeric aggregates to integers; reject fractional,
   nonfinite, negative or excessive values instead of rounding/coercing strings.
2. Track finite stages for configuration/imports, DNS, identity construction and
   token acquisition, claim validation, connection/session/role/privileges,
   individual aggregate-query groups, rollback/cleanup and serialization.
3. [Supervisor](../infra/finops-runner/entrypoint.py): preserve **only** the exact
   bounded failure schema through child exit 2 and controller OS-exit-0
   sanitization. Exception names, guard reasons and actual SQLSTATE codes are
   allowlisted. Unknown types become `unknown`; arbitrary messages, DSNs, token
   claims, hosts, usernames, SQL and tracebacks are not emitted. SDK worker
   logging is disabled. Worker import failures also receive a finite stage.
4. Preserve source hashing, exclusive one-shot marker, 590-second child timeout,
   no fallback credential, exact private destination, TLS verification,
   read-only transaction, rollback and zero-write reporting. No network guard,
   watchdog ownership/hash binding, RBAC or protected configuration was changed.

## Actual validation and remaining gate

**390 tests passed; 0 failed/errors/skipped**, 32.255 seconds, one existing
Starlette/AnyIO deprecation warning. This includes the original 309 expanded
regressions plus 81 offline runtime/diagnostic cases. All four changed Python
files compile; editor diagnostics report no errors.

- [JUnit](../gateway/validation/finops-probe-offline-rootcause-tests-20261027.xml)
- [Source hashes, reproduction and safety evidence](../gateway/validation/finops-probe-offline-rootcause-20261027.json)
- [Unmodified historical execution](../gateway/validation/finops-fresh-execution-9461fb0c1a35.json)
- [Unmodified final cleanup/preservation proof](../gateway/validation/finops-fresh-final-9461fb0c1a35.json)

**No cloud build, remote run, image push, provisioning, probe retry, DB write,
timer/config change, new role, public-PG access or application image change.**
Incremental cloud work/cost for this investigation: zero. No image was prepared
under an old session, and no existing prepared plan was rebound to new source.

Before any future runner, main review must accept the source and a separately
verified immutable updated image. Prefer a single bounded existing-ACR no-push
Linux validation first (CA existence/readability, locked native imports, libpq,
network-forbidden synthetic SDK, numeric loader and two sanitizer boundaries).
Review its explicit timeout/CPU and incremental task cost **before submission**;
no such paid task was needed for the offline reproduction or submitted here.
The prior build's conservative allowance was USD 0.18 at 2 vCPU for 900 seconds;
this is historical planning evidence, not a fresh quote or hard billing cap.
An old digest cannot contain this source fix. **Do not recreate NAT/subnet/ACI
or rerun either MI merely to recover diagnostic information lost previously.**