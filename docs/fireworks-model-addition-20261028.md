# Fireworks additive model release — 2026-10-28

## Acceptance continuation — release must not be replayed

This section supersedes the historical pending-build/pending-apply checkpoints
below. Runtime plan f099f30da4bdef7b31570562d275530ea075d55bbad1e95f473d1a4103d92420
was applied once at 02:57:25.945420 UTC. Independent readback at
03:01:20.527545 UTC proves `protected_equal_except_two_images=true` and all four
settings hashes unchanged. API digest dd8b048b8a189061d870ca9011c3d8e0152ff63712ee6d61fe3f2a37af3b0a33
and ingestion digest fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90
are already live. **Never build, plan, apply or replay the gateway for this
acceptance task.** Native no-push cm2b and the saved 269 release regressions are
retained, not rerun.

The saved authenticated audited sync at 03:02:23.744 UTC returned HTTP 200,
added both Fireworks rows, reconciled router candidates, and kept auto-routing
disabled and prices unchanged. The preceding duplicated-prefix HTTP 404 did
not execute a sync. Current admin catalog read at 03:09 UTC confirms both
Fireworks entries as gateway-verified chat routes and the separate ModelArts
GLM entry. **Method limitation:** the saved sync used the existing authenticated
admin client endpoint, not a visible UI sync button. The current normal admin
catalog has no sync control; its buttons are Compare, Activate and Disable.
No second sync, SQL operation, authentication-storage inspection or credential
extraction was performed to disguise that distinction.

Current customer catalog shows 13 active models. A fresh ordinary Playground
read at 03:08:51 UTC confirms all 13 selector options, including both Fireworks
aliases and external `glm-5.3`. The retained unmodified-selector/Send acceptance
completed at 03:03:44.874 and 03:03:55.045 UTC for Caldova / Caldova-AI:

| Alias | HTTP | Nonempty visible answer | Measured input | Measured output | Total |
|---|---|---|---:|---:|---:|
| FW-GLM-5.3 | 200 | Confirmed — I can answer your questions. | 24 | 333 | 357 |
| FW-MiniMax-M3 | 200 | Yes, I can answer your questions. | 139 | 102 | 241 |

These are real normal-selector requests, without request-body model overrides,
streaming or automatic retries. Their output counts are below 512, but their
**configured request cap was 1024**, not 512. The normal deployed Playground
only displays a fixed 1024-token output limit and exposes no cap input. No new
request was sent above the latest requested 512 cap, and no UI/request mutation
was used to manufacture a 512-capped normal-selector proof. The separate public
endpoint proofs at 01:39/01:40 did use a 512 request cap, but had an explicit
model-body override and are not substituted for normal-selector acceptance.

Pricing remains honest: both Fireworks tariffs Unknown, not zero/free; the
separate ModelArts GLM price remains its sourced publisher-proxy TBC estimate.
Its historical credential-health probe was not restamped. Metadata renewal is
not a fresh external credential-health test. Decision-1 remains routing-only;
its inference integration and automatic routing remain unavailable.

**Scheduled reporting verified at 03:10 UTC.** Ordinary authenticated customer
Usage and admin Showback refresh responses cover the identical half-open window
2026-10-27T03:11:00Z to 2026-10-28T03:11:00Z, Caldova organization
00b30bd3-bf91-470d-b336-a192be32996e. Both return **25 requests, 1413 input,
2483 output, 3896 measured total tokens**, zero missing token measurements,
estimated USD0.007271089999 for 19 estimable requests and six unestimated requests.
Recorded cost remains null, not zero. Both hourly model-token responses equal
the request summary and each other's Fireworks buckets.

The normal query success advanced from 03:05:00.248644Z to 03:10:00.147098Z,
watermark from 03:00:00.248644Z to 03:05:00.147098Z, with new rows ingested at
03:10:01.452734Z. Health is healthy; customer/admin lag320/325 seconds is below
the900-second stale threshold. Both new03:03 requests appear exactly once per
dashboard, under Caldova-AI, provider Fireworks, regioneastus, HTTP200:
GLM24+333=357 and MiniMax139+102=241. Their combined delta is two requests,
163 input,435 output,598 total tokens. The03:00–03:11 partial hourly bucket
contains these exact measurements. Both rows correctly disclose `price_missing`
and Unknown estimated/recorded costs. Old01:39/01:40 probe records retain their
original `backend_attribution_missing` state; history was not rewritten.

No timer invocation, cursor reset, replay, backfill or financial-record repair
was performed. The 03:06:19 console read
confirms the expected ingestion image and Running host, but contains no paired
post-apply scheduled-start/success log evidence; absence of these console lines
is not proof of timer failure. The later authenticated checkpoint/row evidence
above establishes the actual scheduled reporting outcome, without claiming paired
console invocation IDs. Final reporting observations and remaining gaps
are recorded in the [live acceptance record](../gateway/validation/fireworks-live-acceptance-20261028.json).

## Historical checkpoint: runtime applied and independently read back — 03:02 UTC

Exact preserved plan f099f30da4bdef7b31570562d275530ea075d55bbad1e95f473d1a4103d92420
completed independent validation at02:52:19UTC and was applied once at02:57:25UTC.
Independent full protected readback at03:01:20UTC confirms equality except the
two approved immutable images, with all four complete settings hashes unchanged.
Neither image was rebuilt; gateway was not replayed. Existing authenticated admin
inventory sync succeeded03:02:23UTC, adding the two Fireworks rows and reconciling
router candidates while retaining automatic routing disabled and prices unchanged.
A first sync request had a duplicated API prefix and returned404 without executing;
the corrected existing authenticated endpoint returned the actual audited result.
Unmodified customer Playground and scheduled reporting acceptance are in progress,
not yet claimed. Stage outcomes are retained in
[runtime acceptance checkpoint](../gateway/validation/fireworks-runtime-live-final-20261028.json).

## Reconciled immutable builds — do not rebuild

Fresh exact two-image plan reviewed02:49:03UTC, SHA256
f099f30da4bdef7b31570562d275530ea075d55bbad1e95f473d1a4103d92420.
Historical pre-apply checkpoint (superseded by the completed readback above):
all target writable fields except immutable image pins are equal. Unknown
nontarget Terraform checks were resolved from a separate refreshed full plan
with identical variables/configuration and identical target changes; every
companion check passes. Companion plans are validation-only and NEVER applyable
through the release controller. Original unknown checks remain unmodified.
Actual current regression suite269passed; independent workflow is in progress.
No runtime apply is claimed at this checkpoint.

Existing durable build records show API cm2c succeeded at02:08:33UTC,
digest dd8b048b8a189061d870ca9011c3d8e0152ff63712ee6d61fe3f2a37af3b0a33.
Corrected ingestion cm2e succeeded at02:14:07UTC,
digest fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90.
Original ingestion packaging failure is preserved; successful API was retained.
The first runtime plan was rejected before review/apply because a historical
helper default proposed Always On true to false. That plan must never be applied.
The existing corrected controller explicitly preserves Always On=true and uses
a separate fresh preserved-image-plan directory. Independent validation/apply
and actual unmodified Playground/scheduled reporting acceptance remain pending.

## Runtime continuation — native packaging correction

Gateway plan 9f32083df4f47c2a5b93ee56bfa4d783446d6f54cbbbb1e33f56731a192dff66
remains applied; NO replay. Actual bounded HTTP200 metered new-model probes at
01:39:51Z and 01:40:18Z are recorded in the live rollout result. Accepted source
now joins those proofs to actual deployment metadata for thirteen enabled chat
models. External smoke timestamp and counters remain immutable; a separate
86400-second unchanged-policy/backend/internal-secret-reference attestation
renews metadata only, NOT fresh credential health. Display limitation explicitly
distinguishes historical health from metadata verification, without portal rebuild.

First no-push native validation cm29 failed at collection: validation Dockerfile
omitted gateway.tools. No production image build/apply resulted. Original intent
and failure log are retained. Corrected validation uses a separate exclusive
intent/context and includes source-bound collector code. Live policy/backend/
reference equality and expiration are rechecked before plan and before apply.
Public Fireworks pricing page returned Forbidden; no tariff invented.

Corrected collector validation cm2a ran116 tests:115 passed, one unit test assumed
4096 default despite production's1024 environment cap. Isolated that unit test's
settings explicitly; actual persistent-POC1024 tests unchanged. Final no-push
native run cm2b Succeeded02:05:45UTC. Local focused suite261passed. Original
failed runs retained; production image build and promotion not yet claimed.

## Approved scope and checkpoint

Implementation started under explicit Agent-mode authorization. Add only existing
FW-GLM-5.3 and FW-MiniMax-M3; preserve ten original Foundry routes and external
ModelArts glm-5.3. Decision-1 remains disabled. No model provisioning, roles,
grants, credentials, networking, TLS relaxation, scoped-controls activation,
financial/history updates or ingestion backfill is authorized.

Fresh Azure CLI ARM deployment reads on 2026-10-28 confirm:

| Alias | Provider | Version | SKU | Capacity | State | RAI binding |
|---|---|---|---|---|---|---|
| FW-GLM-5.3 | Fireworks | 2 | GlobalStandard | 250 | Succeeded | Microsoft.Nil |
| FW-MiniMax-M3 | Fireworks | 1 | DataZoneStandard | 250 | Succeeded | Microsoft.Nil |

Both advertise chatCompletion=true. This is metadata, NOT inference acceptance
or native safety evidence. Exact upstream is
https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1/chat/completions.
Existing gateway identity/audience, mandatory three safety passes, PII, auth,
stable counters, one forward and zero retry must remain unchanged.

CLI account matches approved subscription/tenant/operator. Corporate combined CA
exists and is used without disabling TLS. Azure MCP CLI guidance returned403;
its troubleshooting guide was consulted. Foundry dependency check reports azd
absent; this existing non-azd Terraform child-route workflow does not use azd.
No historical apply was replayed. Existing product-access apply/verified markers
are present; optional-controls directory contains validation artifacts only.

## Acceptance and rollout gates

1. Fresh protected baseline, actual metadata and unchanged predecessor policy.
2. Additive implementation and focused real regression tests.
3. Fresh exact isolated-root saved plan, independent validation workflow/proof.
4. Gateway-only rollout before accepted catalog/image promotion.
5. Real bounded new-model public APIM and customer Playground requests, measured
   usage and nonempty answer; never fabricate gateway_validated.
6. Accepted evidence promotion, immutable API/ingestion images, audited admin sync
   and scheduled customer/admin reporting only if all release gates pass.

Existing external GLM evidence has verified_at=2026-10-26T15:36:52.071373+00:00,
older than its unchanged86400-second acceptance limit. Do not silently drop it,
restamp its smoke time, invent credential-health evidence or reuse old acceptance
as a fresh functional probe. Resolve provenance honestly or block API/catalog
promotion while retaining the current runtime images. Missing exact Fireworks
tariff stays unknown unless a defensible public sourced TBC proxy is verified;
ModelArts pricing is not a Fireworks tariff.

FinOps timer remains enabled, Always On true, cutoff remains
2026-10-27T06:06:02.045288+00:00. No cursor reset or historical writes.

## Superseding gateway-only checkpoint — 2026-10-28 01:36 UTC

**Gateway status: APPLIED and independently verified. Catalog/model release:
NOT promoted.** This supersedes the earlier implementation-only checkpoint.

The requested original saved plan was **not adopted or applied**. Inspection
found a later formatted attempt with a matching exclusive apply-intent and
applied marker. Its exact saved-plan SHA256 is
9f32083df4f47c2a5b93ee56bfa4d783446d6f54cbbbb1e33f56731a192dff66.
Validation was recorded at 2026-10-28T01:24:03.823610+00:00; apply-intent at
01:25:53.119027+00:00; apply completion at 01:26:13.276300+00:00.
The original plan is now blocked by the cross-attempt no-replay guard. No marker
was reset, no plan was regenerated, and this reconciliation attempted no apply.

Independent verification at 2026-10-28T01:36:38.252926+00:00 authenticated the
saved-plan bytes, current source/input hashes, rollback and exact current render
using the existing release checks and strict backend/policy guard. It bound the
existing validation proof (228 prior focused tests, existing operator permission
checks, all plan checks passing), matching intent/completion hashes, completed
azure-validate `UpdateStatus` workflow and exact timestamped Section 7 proof.
No manual `Validated` bypass or retroactive validation stamp was used; the
historical release controller and its source-bound proof remain byte-identical.

Actual independent ARM readback confirms:

- Exactly the new aiflux-project-fireworks backend, with the reviewed HTTPS
   upstream, protocol and both TLS validation flags retained.
- The live unified policy structurally equals the reviewed exact new render:
   both Fireworks routes added, original routes/auth/counters/safety/PII retained.
- Every old backend value and collection field is unchanged. APIM's derived
   collection `count` is exactly the list length and increases by exactly one.
   That verified derived increment was the earlier post-apply verification
   failure; it is not an unrelated backend mutation or an apply failure.
- The full protected runtime/security baseline equals its predecessor after
   accounting only for that new backend collection. Runtime images, complete
   settings hashes, FinOps timer/cutoff/Always On, state ACL, private PostgreSQL,
   identities and protected policies remain unchanged. Existing product
   subscriptions and API association were independently checked.

The added [scoped reconciler](../scripts/deployment/fireworks_gateway_stage.py)
also implements fail-closed adoption for a genuinely never-attempted plan:
cross-directory attempt exclusion, fresh protected/predecessor equality, exact
archived Terraform module/lock bytes, every default-expanded variable, current
render, existing `guard()`, all plan checks and an exclusive review capture.
Adoption does not grant validation or apply authority. Here its actual execution
correctly stopped at `existing_apply_requires_readonly_reconciliation`.

Actual final regression run: **70 passed**, zero failures/errors/skips, one
existing Starlette deprecation warning. The
[regression tests](../tests/unit/test_fireworks_gateway_stage.py) cover adoption,
archive/input/default drift, prior-attempt exclusion, protected readback,
validation/workflow proof rejection and exact collection-count handling.
An intermediate Python indentation error was corrected and the complete focused
suite rerun successfully before final verification; it caused no cloud writes.

Required factual result:
[gateway-stage-result.json](../.deployment/fireworks-models-20261028/gateway-stage-result.json).
Independent result and authenticated original artifacts are retained in the
later formatted attempt directory. The result records the exact applied plan,
validation and verifier hashes, final test-report hash, zero apply attempts/cloud
writes/inference requests during this reconciliation and `catalog_promoted=false`.

**Still outside this completed gateway stage:** new-model metered inference and
customer Playground acceptance, external evidence expiry, accepted catalog/image
promotion and any subsequent reporting acceptance. No model acceptance, fresh
external credential health or full model release is claimed. No new roles,
networks, keys, optional-controls activation, images or financial/history writes
were performed.