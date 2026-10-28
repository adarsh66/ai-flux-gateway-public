# Customer catalog copy — Linux validation complete

## LIVE — customer-only successor applied and verified, 2026-10-28 06:21 UTC

The authorized release completed. Fresh exact saved plan
**ff727deec82fed08e962bb19a57284ab5c2a85aee2ea8022bfdba0eb767bfe42**
passed independent validation at 06:15:27 UTC, including the actual sequential
workflow through UpdateStatus and timestamped Section 7 proof. The full companion
proved identical configuration/variables and exact customer delta with **all** real
preconditions passing; its unrelated full-stack changes remain **NEVER APPLY**.
Only the customer-targeted saved plan applied, once at 06:18:54 UTC:
**0 added, 1 changed, 0 destroyed**. Neither original plan nor companion was applied.

The installed customer image is
**sha256:d9d8b4b21283801feb2aff3ad12707155f5c38c59b6fc09091a4c22c35e71ea3**,
reusing production build **cm2g**, source
8ace54e9ae15b4e88a6206020dbc6ad3f8781a2d459277a07c5a43f929bb28e4 and native
cm2f **116 tests / 15 files**. No rebuild or push occurred in this continuation.
Three new exact-reconciliation mutation tests and all four existing guard suites
also passed. Independent operator web actions, existing customer AcrPull,
Terraform validate/default workspace/state ownership and complete live baseline
were checked before the one apply.

Independent protected readback at 06:20:53 UTC confirms **only customer image differs**
from the explicitly reconciled baseline. API, admin and ingestion image pins,
all four complete settings hashes, thirteen-model gateway/policies/counters/safety,
FinOps timer/Always On/cutoff, private database/network/state ACL, current RBAC and
the detached fragment are unchanged. Optional controls remain OFF. Deployment
inventory captured 74 preexisting resources and **zero new resources** afterward.
No role writes, key operations, inference calls or TLS bypass occurred.

Both customer /healthz and /models returned **HTTP 200**. Reloading the existing
authenticated customer browser at 06:21:23 UTC loaded the new bundle
index-CecMpr6g.js and asserted all **13** descriptions exactly match curated source,
the Luna heading is exactly **gpt-5.6-luna**, and every Playground link retains its
original model ID. No credential extraction, login or inference was used.

Live endpoint: https://poc-ids-token-ex-customer.azurewebsites.net/models

- [Independent validation](../.deployment/customer-catalog-successor-20261028/validation.json)
- [One completed apply](../.deployment/customer-catalog-successor-20261028/applied.json)
- [Independent complete protected readback](../.deployment/customer-catalog-successor-20261028/independently-verified.json)
- [Authenticated browser assertions](../.deployment/customer-catalog-successor-20261028/browser-acceptance.json)
- [Final release evidence](../.deployment/customer-catalog-successor-20261028/deploy-result.json)

The optional publisher grant remains absent, deliberately not restored; this does
not remove the existing subscription-manager grant. Role metadata is not runtime
key-operation acceptance. Existing dependency audit/chunk warnings below remain.

## RBAC diagnosis and authorized successor — 2026-10-28 06:05 UTC

The failed fresh-role task is diagnosed, not assumed to be a missing essential
grant. It reached assignment listing and Azure CLI rejected its combination of
--all and --scope: **group or scope are not required when --all is used**.
The scoped read was corrected by removing --all; no release guard changed.
[Durable failure diagnosis](../.deployment/customer-catalog-release-20261028/rbac-failed-execution-diagnosis.json).

Actual ARM definition 16ca19f5-170e-4549-a223-d6f3381a6ccf is
**poc-ids-scoped-APIM-read-write-role**, with exactly policyFragments/read and
policyFragments/write. The missing assignment remains 404. It is **not** the
subscription-manager role. The API principal retains unconditional assignment
796ed394-f2c5-4344-a578-faf4e50cfdcf, actual role
fa10dd61-c879-43e6-b259-384d4d29d452 / poc-ids-token-ex-subscription-manager,
covering all seven service/product/subscription read, subscription write,
listSecrets and primary/secondary regenerate actions. Scoped direct/inherited/group
query returned this existing grant, with no inherited replacement for optional
fragment publishing. This is active assignment/role metadata coverage, **not** a
runtime reveal/rotate success claim; no such calls were made. Removal cause and
PIM history are not established. No broad grant is required or requested.
[Fresh role facts](../.deployment/customer-catalog-release-20261028/fresh-rbac-facts-2026-10-28T060110.576047_0000.json).

Under the user's explicit safe-reconciliation authorization, only that exact
optional publisher removal is accepted for this frontend-only release. Optional
controls/publishing stay OFF; every other baseline field matches. Original
baseline bbd14dd0e2fc03b0b567e656cda10b8d3eb83afd7420c1b9781db134623067c0
and plan 40fe1728720d6d4ece18faba097f6992533b3b7f1ef150d60153cec921ed463f
remain untouched; the original target is **superseded NEVER APPLY**. Accepted
successor baseline is
4274cf1e30cf3eeee1b3c9b8422ce77b31e929d52f1c62e0abdf8922bb44e2db.
[Exact reconciliation record](../.deployment/customer-catalog-successor-20261028/reconciliation.json).

No rebuild/push: retain source-bound cm2g customer image d9d8b4b2…71ea3 and
cm2f 116 tests/15 files. A fresh isolated successor target was saved as
ff727deec82fed08e962bb19a57284ab5c2a85aee2ea8022bfdba0eb767bfe42.
At that checkpoint it was **not yet validated/applied**: unrelated unknown target checks had to be
resolved by the identical-input full **NEVER APPLY** companion, with all real
checks passing and the unchanged strict image-only guard. No manual_rbac_verified
input was changed or synthesized. Independent actual validation/workflow and
post-apply protected/HTTP/authenticated-browser acceptance subsequently passed as above.

## Historical blocked checkpoint — 2026-10-28 05:02 UTC

The authorized customer-only release is **not deployed**. No rebuild, image push,
target replan, apply, permission change or inference was performed in this continuation.
Initial process reconciliation listed no Python/Terraform workers. Existing production
build **cm2g** was independently re-read as succeeded, with the original source hash
below and immutable digest
`sha256:d9d8b4b21283801feb2aff3ad12707155f5c38c59b6fc09091a4c22c35e71ea3`.
The retained customer-only plan SHA-256 remains
`40fe1728720d6d4ece18faba097f6992533b3b7f1ef150d60153cec921ed463f`.

The original target has unrelated unknown preconditions. Five offline companion
guard tests passed. The permitted identical-input full **NEVER APPLY** companion
preparation stopped at its live protected-baseline check, **before any companion
intent or plan was created**. This is actual RBAC membership drift, not ordering:
the recorded baseline contains 80 assignments; current inventory contains 79.
Exact ARM GET confirms **404** for assignment
`941a880c-ec30-47bc-bbe7-26adab3ed6cf`, scoped to the existing APIM service, for API
managed identity `4e7b70ed-9868-47ba-9b61-304f1e1fdd89`, role definition
`16ca19f5-170e-4549-a223-d6f3381a6ccf`. No added assignments were found.
**Every other protected baseline field matches.** The removal's cause/intent and
effect on existing API permissions have not been established. No role was restored,
baseline replaced, guard weakened or validation status advanced for this release.

At 05:02:21 UTC the customer image remains predecessor
`sha256:072fe85e23168d20081894357ac87aa036e14363eb031e796e68686f4d357594`.
Both https://poc-ids-token-ex-customer.azurewebsites.net/healthz and
https://poc-ids-token-ex-customer.azurewebsites.net/models returned **200**;
the HTML still references the old asset index-CWvwWdp8.js.
An existing authenticated Contoso browser was reloaded: all 13 model cards remain,
Luna still reads **Luna — bounded demo (2026-07-09)**, the requested exact
**gpt-5.6-luna** heading is absent, and legacy operational descriptions remain.
Therefore new-bundle/live-copy acceptance **has not passed**.

Durable [read-only live blocker proof](../.deployment/customer-catalog-release-20261028/blocked-live-proof.json)
binds the unchanged plan/build, exact missing assignment, full other-field equality,
current customer image and HTTP responses. Review, validation, apply-intent and
applied markers are absent. Resume requires explicit reconciliation of the external
RBAC change under the approved protected-baseline contract; do not rebuild, replan
the retained target, restore roles automatically or replay historical releases.

## Result

One fresh Azure ACR Linux/amd64 **no-push** validation run, **cm2f**, succeeded on
2026-10-28 at 04:30:32 UTC (1m46s reported by ACR). No deployment was performed;
the live customer portal was not updated.

- Existing registry: pocidstokenexacr; expected subscription, tenant and operator verified.
- Existing corporate CA environment reused; TLS verification retained.
- Existing [validation Dockerfile](../infra/image-build/FinOpsValidation.Dockerfile) executed npm ci, all workspace typechecks, all UI tests and both portal production builds.
- **116 tests passed across 15 files**, including all four model-presentation unit tests and the customer-card regression for exact Luna heading, sanitized copy, original Playground IDs, unknown pricing and filters.
- Admin/customer/shared UI typechecks passed. Both production portal builds passed.
- Customer output: index-BL06ItVq.js, 653.32 kB (186.82 kB gzip); index-DwPAoQA0.css, 26.95 kB (6.10 kB gzip). Outputs existed in the ephemeral validator; no deployable image was published or local dist download claimed.

## Source and evidence

Curated source scope: 72 files from `portal_fix.source_files()` plus the existing validation Dockerfile; root npm manifests/configuration, both portal source trees and shared UI. No backend, infrastructure release inputs, credentials, node_modules or prebuilt dist were uploaded.

The source manifest explicitly includes the current new [presentation module](../packages/ui/src/modelPresentation.ts), [presentation tests](../packages/ui/src/modelPresentation.test.ts), [customer cards](../packages/ui/src/pages/TokenExchangePages.tsx) and [page regressions](../packages/ui/src/token-exchange.test.tsx). Workspace and staged-context bytes matched every manifest hash after completion.

- Source SHA-256: `8ace54e9ae15b4e88a6206020dbc6ad3f8781a2d459277a07c5a43f929bb28e4`.
- [Source manifest](../.deployment/customer-catalog-copy-20261028T042834246153Z/sources.json).
- [Exclusive one-build intent](../.deployment/customer-catalog-copy-20261028T042834246153Z/build-intent.json).
- [Redacted build log](../.deployment/customer-catalog-copy-20261028T042834246153Z/validation.log).
- [Final read-only verification](../.deployment/customer-catalog-copy-20261028T042834246153Z/verification.json).
- [Reusable validation-only launcher](../scripts/deployment/customer_catalog_validate.py) and [offline launcher tests](../tests/unit/test_customer_catalog_validate.py).

The first local result incorrectly treated ACR's `outputImages: [null]` as a published image. Original result evidence is preserved. The check was corrected with a regression test; read-only reconciliation of the **same completed run** passed at 04:31:29 UTC. **No second cloud build** was submitted. All four final offline launcher tests and scoped whitespace checks passed.

## Warnings and boundaries

Existing dependency audit warnings: **4 vulnerabilities (1 moderate, 1 high, 2 critical)**. Both Vite builds warned about chunks larger than 500 kB. No dependency or bundling refactor was attempted.

No test/build failures remain. No image push, application deployment, site-setting change, RBAC/network/database operation or inference request was performed. Historical fragment and Fireworks releases were not replayed. Browser/manual responsive verification was not part of this validation-only run.