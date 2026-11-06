# Clean additive Auto release — implemented offline contexts

## Original build/plan continuation checkpoint

See the [actual original cm4g and saved-plan checkpoint](auto-additive-buildplan01-checkpoint.md).
The successor build succeeded with ten Linux tests and both forward plans were
saved; no build/plan replay or apply occurred. This document's offline clean
composition remains historical evidence. The successor adds inline publication
delivery; independent delta review, executable rollback binaries and completion
of technical/official validation are explicitly unresolved, not accepted here.

## Outputs and ownership

Implementation is complete for the narrow **offline composition** scope. It is
not a deployment, independent review, runtime acceptance, or publication receipt.
No cloud reads/writes, builds, installs, paid requests, Playground Send, diagnostic
controllers, or historical test suites were run. Do not replay either consumed
packager/checker; partial and completed outputs are retained evidence.

- [API Dockerfile](../.deployment/auto-additive-clean01/contexts/api/Production.Dockerfile):
  ten-file, dual-module-path overlay **FROM actual cm45 digest**
  `sha256:792e4be648a0b4042bfb6f08f81500e3e3f7a8a2e9c70731481db2bcccfa94ff`.
- [Customer context manifest](../.deployment/auto-additive-clean01/source-manifest.json):
  68 files, **byte-identical to retained actual cm4f source**, including auth,
  pending-send protection, customer warnings, SGT/granularity/bar/pie behavior.
  Existing Auto dropdown/profile/request/response code is already present.
  **No customer image rebuild is required.** Keep cm4f digest
  `sha256:9c2b6ec156cfafe9f43a0449aeddedff4f472b0e4d62c371cc3ba4ec6ce582e7`.
- [API archive](../.deployment/auto-additive-clean01/api.tar.gz): SHA256
  `e3a4c4ea914a63fbb29dde6960df5f3082ba59bbdb2977e8beec13d4054a32d6`.
- [Customer archive](../.deployment/auto-additive-clean01/customer.tar.gz): SHA256
  `3206ffde95a865fc798556c52433352efd85da95bcf936183e2c3e2abe852097`.
- [Source manifest](../.deployment/auto-additive-clean01/source-manifest.json): SHA256
  `42236bc95d5e45967886c180c696a7af188e741d35bb3b6b30014c17aaf097de`.
- [Packager](../scripts/deployment/auto_additive_clean.py) and
  [focused checker](../scripts/deployment/auto_additive_clean_check.py).

Only the two context directories (or their exact archives) are image inputs.
The effective source tree under checks is **validation-only**, not a build input.
It includes retained catalog evidence needed for offline imports/resources.

## Exact source composition and resolved blockers

The API baseline is the actual production overlay, not the dirty workspace
entrypoint. Original production overlay files were checked against its retained
source manifest, itself hash-bound to cm45's actual build result. cm4f's full
68-file source map was checked against its actual build-bound source manifest.

The sole entrypoint delta is one authenticated availability GET plus its import:
[entrypoint diff](../.deployment/auto-additive-clean01/deltas/app.py.diff).
Removing those two AST nodes reproduces **the entire original cm45 AST**.
The existing `User` and `Db` dependencies remain; no admin profile initialize/save,
private resolver, Decision client, new credential, database writes or DDL is added.
The narrow read-only router is
[auto_availability.py](../.deployment/auto-additive-clean01/contexts/api/modules/auto_availability.py).
The broad dirty decision router is deliberately **not** packaged: its imports
would unnecessarily bring admin mutations, resolver/fallback and scorer clients.

The actual all22 inventory hashes differently from frozen Auto defaults and maps
the existing six routes to the public gateway rather than upstream Foundry URLs.
The implementation therefore preserves the full current inventory/catalog and
adds a **separate byte-bound frozen Auto inventory resource**. See
[snapshot delta](../.deployment/auto-additive-clean01/deltas/auto_snapshot.py.diff).
Every candidate must still be currently accepted with matching model/version,
backend, provider, capabilities, cap, API format, reasoning and token parameter.
The only allowed endpoint transition is the exact retained fixed Foundry URL to
the exact current fixed APIM URL. Current acceptance controls price eligibility;
the immutable original six-option rates still provide descriptors. No defaults
bytes, version or Terraform snapshot inputs are rewritten.

The API overlay contains exactly four modules: baseline-plus-GET entrypoint,
baseline-plus-five-fields settings, adapted snapshot/publication reader, and
read-only availability. Three added resources are immutable defaults, their
original inventory, and the decision-overhead KQL. All are copied to **both**
source and Python 3.11 site-packages paths, with expected SHA256 verification.
No new pip dependency. All22/catalog/pricing/finops/auth/SGT/schema modules are
inherited from pinned cm45. Its prior full effective expected-file map is retained
except the four new/changed modules and three added resources.

**Ingestion cm40 and admin cm4e stay pinned; neither needs a context or image.**
The decision-overhead query is packaged as a separate read-only trace view, not
wired into completion ingestion. Actual parent trace persistence/correlation is
still a runtime acceptance requirement; nullable usage/cost is never zero/free.

Terraform formatting: native `fmt -check -diff` failed because Windows has no
`diff` executable. Fresh non-mutating `terraform fmt -` stdout showed exactly six
single-space alignment changes. One exact patch was applied; the **one** final
fmt check passed for all three affected HCL files. No manual formatting iteration.
New Auto HCL SHA256 is
`426154d543790242e34b60665a0eab334b8c89c1b26c14083e08aa9a11b25796`.
Historical final-source/fmt failure receipts were not changed.

## Actual focused checks — one pass

[Durable result](../.deployment/auto-additive-clean01/checks/result.json), SHA256
`b5b7e06a92ca4719aea3424d3dc81652c40bab1b3a0db015728d6d57daccee23`:

- Both archives reopened and every member's bytes/hash matched the manifests.
- All 29 effective Python modules parsed with Python **3.11 syntax** constraints;
  imports executed on the configured installed Python **3.13.1**, not a claim of
  Linux Python 3.11 runtime execution. Network sockets denied during checks.
- Actual clean application imported, availability route present, legacy resolve
  and new admin mutation routes absent. Full baseline entrypoint AST preserved.
- Actual defaults load against current expanded inventory: six candidates and
  balanced/cost/quality profiles; changed candidate metadata rejected.
- Feature off and missing publication both return closed readiness.
- Direct Node TypeScript `--noEmit` for composed shared UI and customer: both
  exit 0. No Vite/Vitest/esbuild/Ruff or frontend runtime/build claim.
- Terraform fmt check exit 0. No plan, console, provider init or Terraform tests.
- Entire retained additive01 artifact/source receipt directory unchanged.
- Editor diagnostics found no errors in new packaging/check scripts or HCL.

## Exact parent release settings and order (not executed)

Ordinary configuration remains OFF. Prepare/review/build only the ten-file API
context; no customer/admin/ingestion rebuild. Parent independently reviews the
context manifests, actual final saved plan and **final native `local.policy`**
digest, not merely pre-wrapper `auto_with_error`. The direct-release Terraform
contract still binds its pre-wrapper candidate; record both boundaries distinctly.

After real gateway acceptance/readback and actual source-bound independent review,
the API settings required for deliberate bounded validation are:

| Setting | Required value |
|---|---|
| `AIFLUX_AUTO_ROUTING_ENABLED` | `true` only at explicit advertisement activation |
| `AIFLUX_AUTO_ROUTING_DIRECT_VALIDATION_ENABLED` | `true` only for schema2 bounded acceptance |
| `AIFLUX_AUTO_ROUTING_SNAPSHOT_INVENTORY_PATH` | `/app/services/control-plane/src/aiflux/pricing/auto-routing-inventory.json` |
| `AIFLUX_AUTO_ROUTING_PUBLICATION_PATH` | Exact operator-provisioned readable immutable receipt path; no receipt is shipped here |
| `AIFLUX_AUTO_ROUTING_PUBLISHED_POLICY_SHA256` | Actual independently reviewed final policy/readback binding, 64 lowercase hex |

Do not change existing catalog/inventory paths, catalog-configured/local-auth
values, image pins, auth, gateway limits/safety, identity/network/roles or ingestion
settings. Legacy resolver remains unregistered; do not activate its historical flag.

Schema2 receipt must use **actual evidence hashes**, not hashes of placeholders:
schema integer 2; snapshot version
`10359b8e7939683fa239c04eefb840a9e21080c1cfed0ac62631ba8ee554fe8e`;
fixed Decision-1 endpoint/deployment/gateway principal/client and response contract
as enforced by [publication reader](../.deployment/auto-additive-clean01/contexts/api/modules/auto_snapshot.py);
actual `policy_sha256`, `authorization_evidence_sha256`, `independent_review_sha256`,
`policy_readback_sha256`, `rollback_sha256`; `runtime_verified=false`;
`gateway_runtime_evidence_sha256` null/absent;
`validation_mode=bounded-production-direct-v1`; budget exactly two Auto attempts,
two scoring calls, two completions, zero retries, fallback false; and
`stop_on_explicit_regression=true`. No ready receipt was generated by this work.

The runtime publication source/transport is still a parent prerequisite: the
configured path must exist in the actual API runtime and its bytes/hash must be
read back. Do not invent a local path or assume settings alone deliver a file.
Likewise hash bindings are **not** automatic budget enforcement. Parent retains
exclusive durable attempt ownership before sending: greeting once, then arithmetic
once only if the first passes; unknown/failed requests consume budget; stop on
first failure/regression, no retries/fallback. Verify separately persisted scoring
overhead and unchanged selected completion usage.

## Rollback requirements

Before any writes parent freshly captures full protected policy/config/settings,
image pins, ETags, all22 backends/native routes, inheritance, auth/limits/counters,
identities/roles/network and rollback bytes, rejecting drift. Retained labels are
not a fresh production-state observation. Baseline API is cm45; unchanged customer
cm4f/admin cm4e/ingestion cm40 stay pinned.

On Auto failure disable the Auto route and advertisement as a coordinated change:
set API Auto enabled and direct-validation enabled false, revoke/unconfigure the
publication path/hash, and remove/disable Auto gateway acceptance. Do not leave a
ready advertisement pointing at a disabled route. On explicit regression restore
the **freshly captured exact** reviewed gateway policy, full prior settings and
only affected API image pin; verify actual readbacks. Do not overwrite drift with
historical bytes or rebuild rollback images. Restoring settings must distinguish
absent keys from empty values and restore the entire original map. No permission,
firewall, DB or ingestion mutation is needed.

Remaining blockers: independent review; authorized Linux no-push/API image and
runtime validation; actual production publication delivery/review/readback hashes;
fresh full protected production guards; exact saved-plan/final-policy review;
parent's durable bounded runtime acceptance and telemetry persistence. These are
not substituted by offline checks. The formatting and dirty-context composition
blockers are resolved.