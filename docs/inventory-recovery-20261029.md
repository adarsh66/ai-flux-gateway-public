# Inventory availability recovery — 2026-10-29

## LIVE FIX VERIFIED — 03:59 UTC

The user-approved persistent-acceptance correction is deployed. The exact saved
API-image-only plan applied once at 03:54:25 UTC: zero additions, one update,
zero deletions. The live API image digest is
29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64.
Independent state and protected-baseline verification confirmed all settings,
other images, routes, safety, detached fragment, identities and FinOps preserved.
The approved storage IP 167.103.63.12 was added without removing previous rules;
Entra state access and backend initialization succeeded.

Normal authenticated browser acceptance at 03:59:36–03:59:43 UTC confirmed:

- Admin model-router: zero alerts/expiry errors; all 14 deployment entries,
  including routing-only Decision-1, render successfully.
- Customer model catalog: zero alerts/expiry errors; all 13 chat models render.
- Customer Playground: zero alerts/expiry errors; all 13 model options, active
  subscription selector and Send control render. No key was revealed and no
  completion was submitted.
- The original October 28 inventory timestamp remains visible. This proves the
  correction did not merely renew its timestamp for another 24-hour window.

Elapsed inventory age and legacy accepted-route deadlines no longer revoke
availability. Structural, parentage, deployment/binding, timestamp-integrity and
historical metered-acceptance checks remain, as do authentication/security expiry,
TLS, safety and quotas. Unfinished Auto changes were not deployed and Auto stays
unavailable. The earlier Decision-1 operator401 remains a separate issue.

The direct private API health probe returned403, as preserved in verification
evidence; it was not bypassed. Successful acceptance is through the existing
authenticated portal paths, not a claim that private ingress became public.
See [browser acceptance](../.deployment/inventory-persistence-20261029-urgent01/browser-acceptance.json).
Historical blocked and preparation checkpoints below are superseded by this
live result and retained for audit.

## Authorized exact saved-plan execution — applied, browser pending

The user separately authorized the LIVE API-only saved-plan apply once. The
exclusive intent was recorded at **2026-10-29T03:53:13.647034 UTC**. This supersedes
historical no-apply handoff language below, not the immutable validation evidence.
Actual apply ran **03:53:13.648574–03:54:25.238401 UTC**, exit0, exactly
**0 added / 1 changed / 0 destroyed**. Only the API image changed to immutable
digest29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64;
the exact saved plan/source bindings in the table below remain unchanged.

Immediately before the intent, all **30 validation evidence hashes, 22 reviewed
artifacts and 10 bound tooling hashes** matched. Actual completed official
validation and the current Validated Section 7 were reconciled without rerunning
validation/build/plan tasks. The full current 13-component protected baseline and
supplemental roles/RAI/network metadata matched the reviewed baseline, including
all four settings sets, all image pins and the separately approved four-IP
storage ACL. Remote state retained lineage and serial109, unchanged blob metadata
and an available/unlocked lease. No competing mutation worker was present.

The separate executor uses only the existing API-only saved target, without
variables/overrides, init, refresh-only apply, replan, companion apply, or any
other resource write. The full companion remains **NEVER APPLY**. Private
Terraform output is ACL-protected and must not be copied into public evidence.
The durable intent forbids retry even if the wrapper fails; reconcile existing
live configuration, remote state and markers instead.

Evidence: [exclusive intent](../.deployment/inventory-persistence-20261029-urgent01/live-apply-intent.json),
[pre-apply integrity](../.deployment/inventory-persistence-20261029-urgent01/apply-execution01/integrity-immediately-before.json),
[execution ownership](../.deployment/inventory-persistence-20261029-urgent01/apply-execution01/terraform-process.json).
Independent after-reads completed **03:56:20.107060 UTC** in a separate process:
exact live/state digest, all13 protected components equal except the authorized
API image; all four settings sets and other three images equal; role definitions,
RAI policies/13 deployment bindings and network collections equal. Policy/counters,
detached fragment bytes/properties, Foundry/product/auth, storage ACL and FinOps
equal the reviewed baseline. Baseline and image-normalized after SHA256 both equal
1b8a11d867c511a8a5317491c5c2566490650ca9c6f795c85fb89fd09c20156d.
State lineage b05cbf70-2d31-0e6e-34b7-c97e8f617ed6 was retained,
**serial109 advanced to110**, and the backend lock was released.

The existing direct unauthenticated
[API health endpoint](https://poc-ids-token-ex-api.azurewebsites.net/healthz)
returned **403**, not200. The independent verifier retained that failure and
exited2 after the protected/state checks passed. No access change or mutation
retry was attempted. This does **not** prove successful HTTP health or clearing
the portal metadata503. The parent's normal authenticated admin model-router and
customer models browser stage is still required; no overall completion is
claimed. No DB-backed publication revision was queried or inferred.

Final local-only evidence reconciliation at **03:57:25.379339 UTC** again matched
all30 retained evidence,22 artifacts and10 tooling hashes, preserved historical
intents/private output integrity and observed apply workers0/mutation workers0.
The final nonmutating evidence reader then exited; only azmcp19628 was otherwise
observed. No source-bound script edits, validation/build/plan/replay, inference,
metadata timestamp restamp, other-image or permission/network/identity/DB/Auto
write occurred. **Never retry this apply**; the durable intent remains binding.

Evidence: [actual apply result](../.deployment/inventory-persistence-20261029-urgent01/apply-execution01/apply-result.json),
[independent comparison](../.deployment/inventory-persistence-20261029-urgent01/independent-live-verification01/protected-comparison.json),
[retained HTTP-health failure](../.deployment/inventory-persistence-20261029-urgent01/independent-live-verification01/verification-failure.json),
and [final deployment handoff](../.deployment/inventory-persistence-20261029-urgent01/deployment-handoff.json).
Private raw Terraform logs must remain private. No credential extraction is
authorized or needed for this deployment verification.

## Historical preparation checkpoint — NOT applied at 03:24 UTC

The user explicitly authorized removing **metadata-only time retirement** after
the backend restoration. This supersedes historical TTL-preservation restrictions
below; it does not authorize removal of security expiry or any apply here.
The existing live503 is not yet fixed: the new image/plan awaits parent independent
validation and a separately authorized saved-plan apply.

### Runtime changes and preserved checks

Only [Foundry inventory](../services/control-plane/src/aiflux/foundry_inventory.py)
and [external inventory](../services/control-plane/src/aiflux/external_inventory.py)
change in the production package. Accepted operator-reviewed Foundry/Fireworks
and GLM metadata remains available indefinitely unless explicitly disabled or
structurally/configurationally incompatible. Observation timestamps remain intact;
malformed, future and naive observation evidence still fails closed. Historical
metered external acceptance/hash binding remains mandatory, with **no assertion
of newly tested/current credential health**. Fresh credential-health display is
always false; historical timestamp remains exposed.

All schema, account/project parent, deployment identity/model/version/state,
capacity, chat capability, exact accepted route/catalog pool, provider and
historical credential-acceptance checks remain. Disabled catalog/operator entries
remain disabled. Runtime token authentication, gateway safety, product membership,
budget/quota counters/resets, timeouts, TLS/cert/key security and release-proof
freshness/exclusivity/short-lived credentials are untouched. No inference occurs.

Per-route expires_at is now legacy provenance, not automatic retirement. All
**actual deployed routes have expires_at=None**, so this was not the observed
outage trigger. Regressions cover old aware deadlines staying accepted and naive
deadlines remaining rejected. A future deadline is not a future observation;
future verified_at/observed_at still cannot establish acceptance.

Source audit found no separate pricing expiry gate. Fireworks routes share the
Foundry loader. The only runtime max-age consumers were these two modules. The
existing max-age configuration/environment remains unchanged and is retained for
compatibility, not used as a metadata availability lease. Dirty Auto/app/config/
schema source is deliberately excluded. No runtime ARM refresh/grant is added.

### Exact package, native validation and release artifacts

Fresh evidence: [.deployment/inventory-persistence-20261029-urgent01/review.json](../.deployment/inventory-persistence-20261029-urgent01/review.json).

| Binding | SHA256 / result |
|---|---|
| Exact inherited live API | b489df53815f0d0242eda4c28b2c471bca2ce53344abc6733220c67c87bc0e09 |
| New API image, ACR cm33 | 29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64 |
| Source/package | 47d64e16531ea19d1a77c4da9717a2920701e4abd5c41047f7ca1245de57a7d1 |
| Exact API-only saved plan | c635c2d09425f840e5340e6ff6475a25a29f8a5dd391fdc444f290d2f59d7e18 |
| Full NEVER APPLY companion | 16bcc4392d06c765a0f775be219b17df4abbf9bb4e3072b86fc6f528ded054f2 |

Production context is exactly a FROM-live Dockerfile plus the two reviewed modules.
Each is copied to packaged source and installed Python3.11 paths; every other
Python module, dependency, base layer, metadata/catalog JSON, setting, portal and
gateway remains inherited. No timestamp/pricing/catalog restamp occurs.

Fresh joined ARM metadata verification at **03:13:01.466653 UTC** matched the known
Foundry account/project/empty connections/all13 deployments and external policy,
backend/internal reference. The pure verification result was checked and its
restamped output discarded. Historical evidence and cm30 were never replayed.

Native no-push **cm32**, Succeeded **03:17:57.203346 UTC**, passed **342 tests**,
with the same two known migration exclusions. Exact immutable base503 reproduced;
packaged AND installed Python bytes verified with only two allowed module deltas.
Unmodified deployed inventory/catalog verified; synthetic100day-old evidence and
elapsed route deadlines retain all13 aliases. Future/malformed/naive evidence,
wrong parent and tampered route negatives fail closed. No Auto/Decision-1 alias
is made selectable. Tests cover models/garden/router/playground without provider
traffic; no live PostgreSQL/inference/browser acceptance is claimed.

Original **cm31** failed before runtime replacement only because the attestation
harness mishandled a relative catalog path. Its terminal Failed/no-push status,
log and original inputs are retained; corrected native02/cm32 was a separately
marked validation, not a resubmission or evidence overwrite.

Exactly one production API build/push **cm33** completed **03:19:47.596552 UTC**.
Fresh isolated Terraform init with readonly provider lock, default workspace,
fmt-check and validate passed. The saved target allows **one existing API image
update only**; full settings/all other properties remain equal. All checks resolve
through the identical-input full **NEVER APPLY** companion. Do not apply it.

Before/after native/build/plan full13 snapshots match, including all4 settings
hashes and other images. Current storage baseline includes only the approved
fourth IP167.103.63.12 in addition to the prior three; no network write occurred
in this release and historical evidence was not changed.

### Next stage — parent independent validation only

Final separate read-only audit at **03:27:44.706876 UTC** passed exact image/run,
source/immutable intents/artifacts, resolved saved-plan delta and all13 current
protected-component comparisons. **138 local/independent guard tests passed**,
zero failures/errors/skips; mutation workers **0**, applies **0**, inference **0**.
See [final handoff](../.deployment/inventory-persistence-20261029-urgent01/handoff.json)
and [guard JUnit](../.deployment/inventory-persistence-20261029-urgent01/independent-guard-tests.xml).
Official azure-validate/Section7 completion is explicitly false in the handoff.

Audit the retained exact source/package, production/native run identities and
saved target/companion hashes, complete current baseline, guard-test evidence and
worker quiescence. Perform actual sequential official azure-validate and Section7
for this plan; previous proof/status is not reusable. This task **does not apply**
and deliberately implements no apply entrypoint. No replay/rebuild/replan is needed.
After separately authorized deployment, independent live protected/HTTP/browser
readback is still required; source/native tests are not a live outage-resolution
claim. Release metadata/proof freshness remains bounded, despite persistent
runtime metadata availability.

## Backend-only follow-up — 03:06 UTC

The user subsequently approved **only** adding storage-account IP
`167.103.63.12`, preserving the three existing rules and every other setting.
The new exclusive connection-restoration workflow completed one single-IP CLI
write and independent whole-account readback; Entra container access, state-blob
metadata HEAD and isolated default-workspace backend init all succeeded.
**Backend ready** at **2026-10-29T03:06:02.708163Z**. State blob metadata/lease and
the existing provider lock remained unchanged; historical intents were not
replayed. No release build/push/plan/apply or application repair occurred.

See [current connection approval and exact results](terraform-state-access-diagnosis.md)
and [fresh final evidence](../.deployment/backend-connection-restoration-20261029-030415311253Z/result.json).
The failed backend attempt and final checkpoint below remain historical evidence,
not instructions to retry them. Their original state-ACL snapshot has three IPs;
the approved fourth rule is an explicit later operator delta, not unexplained
drift or permission to replace historical evidence. The source/expiry correction
is delegated separately and remains subject to its own release gates.

## Outcome

**Historical 02:51 UTC checkpoint: root cause verified; recovery package tested;
deployment blocked then. Live portals
are not fixed.** No production image was pushed, no release plan was generated,
and no apply, inference, permission, network, policy or settings write occurred.
This work addresses the existing admin model-router/customer models inventory
503, not Decision-1 scoring or unshipped Auto implementation.

## Verified root cause

At 02:43–02:51 UTC, live API configuration and exact immutable image provenance
were read using the existing operator account, corporate CA and strict TLS.
The image's actual filesystem was then inspected inside a native Linux no-push
build derived from that exact digest, rather than assuming dirty local source
matched production.

- Effective inventory TTL: **86,400 seconds**, unchanged. No App Service override
  of TTL or inventory paths is present. The image configures the two /app
  inventory paths and the 24-hour limit; the Python default alone is not the
  deployed limit.
- Packaged Foundry verified_at: **2026-10-28T01:46:08.848809+00:00**.
- Expiration: **2026-10-29T01:46:08.848809+00:00**. At the completed metadata
  preflight it was 90,001.503477 seconds old, exceeding the limit.
- External glm-5.3 metadata_renewal.observed_at had that same old timestamp.
  Refreshing only Foundry would silently leave that external route unavailable.
- The actual base-image loader reproduced HTTP503 with the reported inventory
  error. This failure occurs before model scoring; the earlier operator scoring
  401 is not needed to explain it and was not reprobed.

Actual base Foundry JSON SHA256:
b0a6d9473375d589dbff8c1f8fce223d6e0850858ae71aca30fd8da0e2e2807c.
Actual base external JSON SHA256:
9fba608cf459ab8eefee25538e4bf7608c3fe9515ad019b79b3ecf7bcbd39abc.

## Exact deployed images reverified

Registry: pocidstokenexacr.azurecr.io; repositories aiflux-api, aiflux-admin,
aiflux-customer and aiflux-ingestion respectively.

| Component | Immutable SHA256 |
|---|---|
| API | b489df53815f0d0242eda4c28b2c471bca2ce53344abc6733220c67c87bc0e09 |
| Admin | 2846f1ff04244f20cb6612cca62c348b6a79a2fff7245dfc609347564becbfe5 |
| Customer | a30d513ce0dd7c529491689a49ce311f7794f4785e1dd5c5577ae62da9f1b975 |
| Ingestion | fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90 |

## Prepared correction and source isolation

Exclusive evidence is retained under
[.deployment/inventory-recovery-20261029-024900Z/final-checkpoint.json](../.deployment/inventory-recovery-20261029-024900Z/final-checkpoint.json).
The directory name is an identifier; actual collection times in the JSON are
authoritative.

The candidate inherits the **exact live API digest**, preserving every existing
layer, dependency, Showback/publisher-reliability module and startup setting.
Its production context contains exactly a three-line Dockerfile and two public
inventory JSON files. No current dirty API, app/config/schema, gateway, shared UI,
portal or Auto file is included. Retained deployed-build source/manifests were
verified, then every packaged and installed Python module was byte-compared
inside the image. No new runtime source is required for this immediate remedy.

Fresh joined ARM reads at **2026-10-29T02:46:07.224194+00:00** verified the exact
account/project identities and Succeeded state, no connections/pagination,
all13 deployment identities/model versions/formats/states/capacities and chat
capabilities. Existing complete API policy bytes, external backend and internal
secret-reference metadata matched their accepted predecessor. Secret values,
keys and inference were not read or invoked.

Only these evidence fields change:

- Foundry verified_at.
- External metadata_renewal.observed_at and its fresh reference-metadata hash.

All route bindings, model/pricing data, token limits, historical external metered
smoke, credential-health timestamp and no-new-smoke flags remain unchanged.
The candidate retains all13 explicit routes; Decision-1 remains non-chat and
Auto is not introduced. This is not a claim of fresh upstream credential health.

Package manifest SHA256:
f81e3bd2ca4f2611e5e632645c1c49953a26eb5c537d9961ab38967e80f9afd8.
The candidate itself expires **2026-10-30T02:46:07.224194+00:00** under the
unchanged TTL; the stricter release guard requires evidence younger than two
hours at build/release. Do not deploy it after that guard expires without another
real joined metadata verification and newly bound candidate proof.

## Actual validation

- ACR native Linux **cm30**, Succeeded **2026-10-29T02:48:33.249513+00:00**,
  **no published image**. Original az.cmd log streaming hit cp1252 after the
  build was submitted. Read-only UTF8 reconciliation recovered that same run;
  no replacement submission occurred. ACR's [null] outputImages is the existing
  documented local no-push contract, not a published output.
- Base filesystem attestation: exact old inventory files, effective TTL,
  expired-loader HTTP503, packaged and installed API code all verified.
- Candidate attestation: same API code, no Auto, same TTL, all13 explicit routes
  load successfully after replacing only the metadata files.
- **309 retained backend regressions passed**, **two known migration tests
  deselected**. Includes Showback, usage/filtering/tokens, control plane, publisher,
  gateway controls, external and Foundry inventory. No live PostgreSQL or inference
  acceptance is claimed. Native warnings were TestClient deprecation and a
  non-writable pytest cache; no failures occurred.
- **21 local renewal/package guard tests passed**, no skips/failures. Includes
  partial/wrong-parent/duplicate/deployment drift, stale/future evidence, missing
  runtime role, exact candidate membership/deltas and historical-smoke preservation.
- Editor diagnostics reported no errors in the new Python modules.

See [native proof](../.deployment/inventory-recovery-20261029-024900Z/native.json),
[actual native log](../.deployment/inventory-recovery-20261029-024900Z/run-cm30-readback.log),
and [local test evidence](../.deployment/inventory-recovery-20261029-024900Z/final-renewal-tests.xml).

## Exact deployment blocker

An isolated **read-only Terraform init** was attempted before any production
build/push to avoid an unused release image. It failed while **listing blobs for
existing workspaces**:

- HTTP **403 AuthorizationFailure**.
- Request ID: **c275b18b-401e-005b-7850-674d43000000**.
- Azure error time: **2026-10-29T02:50:13.0882707Z**.
- Existing storage account **projpoctokenex**, container **tfstate**, state key
  **poc-ids-token-ex/main.tfstate**; correct subscription/tenant, CLI+Entra auth.

This does not independently distinguish network ACL rejection from data-plane
authorization. No firewall/RBAC change, alternate state, new runner or broad
deployment was attempted. This is the stopping condition explicitly required
for unavailable backend state access.

See [backend readiness](../.deployment/inventory-recovery-20261029-024900Z/backend-readiness.json).
The private init log is preserved in the same access-restricted evidence directory.
There is **no production build digest, saved release plan, Section7 deployment
validation or apply intent** for this recovery.

## Sustainability and preserved baseline

The current API identity has **zero matching direct unconditional Foundry
ARM-read assignments** in the fresh complete role-assignment collection. Required
account/project/connections/deployments read actions are not proven. Group-derived
access, deny assignments and actual runtime identity ARM reads were not proven.
Consequently no automatic refresh code, role grant or permission expansion was
introduced. This metadata-only image would restore availability temporarily;
it is **not** a sustainable freshness solution. Increasing/disabling TTL or
blindly restamping inventory is not an allowed substitute.

Final independent GET-only checkpoint at **2026-10-29T02:51:46.721374+00:00**
matched **all13 protected snapshot components**, including all four image pins
and full appsettings hashes, exact detached policy/fragment, product subscriptions,
Foundry deployment metadata, gateway identity, state ACL and FinOps timer/cutoff.
Current fragment bytes were preserved, not reinterpreted as historical defaults.
Settings revision12 is parent-reported; this collector did not access private DB
state to independently read its revision number. Historical intent hashes and
native/package inputs remained intact. No mutation workers were observed.

## Next exact stage

1. Existing remote-state access must be available through an already authorized
   path, **without** forbidden network, identity or permission changes.
2. Reconcile retained artifacts/workers; do not replay cm30 or completed stages.
   Reverify actual metadata and rebind/retest a new candidate if the <2h release
   evidence guard has expired.
3. Build/push exactly one immutable API-only metadata image from the bound context.
4. Prepare a fresh narrow existing-API-image-only saved plan preserving full live
   settings, all other images and complete baseline. Use an identical-input full
   **NEVER APPLY** companion only if excluded checks require resolution.
5. Independent actual sequential Azure validation and Section7 proof, followed by
   at most one saved-plan apply and independent protected/HTTP/browser verification.

No earlier release's approval/validation status can authorize skipping these gates.