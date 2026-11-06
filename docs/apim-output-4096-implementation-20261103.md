# APIM 4096 output allowance — live rollout and usability evidence

## Latest live evidence — 2026-11-03 — COMPLETE with documented limitations

Authoritative readable [FINAL report](../.deployment/apim4096-rollout-20261103-03/FINAL.md)
and [final20 receipt](../.deployment/apim4096-rollout-20261103-03/final20/FINAL.json)
supersede historical NOT DEPLOYED/1024 and capacity-blocker release status below.
Historical receipts are preserved unchanged; this finalization is documentation
and retained-evidence review only, not another deployment or live probe.

The NOT deployed and USD-cap-missing statements in the historical sections below
are superseded by later explicit authorization: **USD50 total**, short calls,
no requirement to generate4096 tokens. Feature2 remains paused and excluded.

- Gateway correct15: one mutating apply of the original reviewed saved binary,
  exactly two policy updates. Exact active rawxml and fragment readback passed.
  Earlier continue14 state-lineage rejection made zero resource writes.
- Root17: one successful API-only apply with four coordinated release settings;
  root150→151 and gateway child203→206. All other pins/settings protected.
  Existing production cm62 API digest
  5893ab10178c85e9c4260d478c9f88a9257a44a069a7293da75c63bbdf68efd7 reused.
- [Original short probes](../.deployment/apim4096-rollout-20261103-03/probes19/RESULTS.json)
  completed once at08:04:28 UTC: **22 explicit + Auto balanced/cost =24 attempts,
  24 HTTP200,24 nonempty text,24 stop**. One separate4097 denial returned400.
  No paid retry or fallback; no master key; Caldova-AI key memory-only.
- Operational reservation **USD24.26**: USD24 completion attempts, USD0.24 safety,
  USD0.02 two Decision-1 calls. Includes failed/empty attempt reservation (none
  occurred). This is not actual billing, nor a certified external tariff bound.
- Auto responses verify successor config_version
  5f6d1b489403af83d635fbc4128a0a4389ca2d7e100c8ed620dbb3de1adc1e51,
  rate-card-v2 pricing and fallback_used=false. Both selected gpt-5.6-luna.
  Quality has not been paid-probed; no additional call is needed for this matrix.
- Independent final20 completed at08:07:46 UTC. [Protected guards](../.deployment/apim4096-rollout-20261103-03/final20/GUARDS.json)
  at08:07:44 UTC passed: root151/child206, exact4096 policy/fragment readback,
  all22 preserved, pricing rows unchanged, exact root/child postapply state and
  lease unlocked. Quotas, safety, roles, networks, protected settings and backend
  revisions remain unchanged. Master/subscription disposition unchanged;
  Feature2 remains PAUSED/EXCLUDED.
- Optional portal catalog/Auto advertised4096 metadata remains **unverified**.
  [Metadata STOP](../.deployment/apim4096-rollout-20261103-03/final20/metadata-STOP.json)
  records AssertionError / normal_customer_login_failed_no_retry, not an
  established permission or credential cause. No login replay, secret extraction,
  token logging or credential manipulation. No additional browser check during
  finalization. This limitation does not invalidate core APIM/user-usability
  acceptance. All three Auto profiles were not live paid-probed.

**Closure: LIVE successful APIM4096 + all22 explicit/Auto balanced+cost short
usability + protected final guards. No further paid calls/build/plan/apply/replay
or rollback. Actual billing, full4096 generation, all-provider capacity and
full-length opaque safety-service certification are not claimed.**

Requested completion output was128 per call, not4096. Some Grok usage reports
separate hidden reasoning beyond128: requested output is not a uniform cap on
all reported/billed reasoning tokens. No all-provider maximum-output or opaque
safety-service certification is claimed. Pricing row preservation versus the
old fragment was verified offline: only pool_version and its integrity hash
changed; this is not a claim that the entire fragment byte hash stayed constant.

## Historical source checkpoint (retained for provenance)

Date: 2026-11-03. **Focused fixture repaired; offline native validation passes;
acceptance revised as recorded below; NOT deployed.**

Feature 2 remains paused. This work does not change subscription ownership,
master disposition, organization permissions, pricing or quota allowances.

## Historical user direction — operator ceiling and short usability probes

The authorization/cap questions and proposed matrix in this historical section
were superseded by explicit USD50 authorization and the executed 128-output,
22-explicit plus balanced/cost matrix above; they are not current action items.

The user authorized bounded paid compatibility probes and a controlled safety
validation path, and explicitly removed the requirement to demonstrate responses
actually reaching 4096 tokens. The target is a 4096 APIM-authorized ceiling with
models remaining usable. Historical missing numeric-capacity documentation below
is retained as a limitation, not an unchanged requirement to prove full-length
generation. Do not claim those evidence gaps were resolved.

Preserve production safety controls and distinguish short usability evidence from
certification of every provider's maximum output or opaque safety-service internals.
Coordinate explicit/Auto policy, snapshot/publication and API metadata as needed;
do not blindly replace template values while an inherited full-policy override
or runtime snapshot can retain 1024. Feature 2 remains excluded.

A proposed bounded smoke matrix is one attempt per explicit model plus one per
Auto profile, short inputs, at most 32 requested completion tokens, and no
automatic retries. Auto scoring cost must also be included. This is a proposal,
not an executed probe or proof that a 4096 request succeeds upstream.

The follow-up questions requesting a numerical total USD cap and confirmation of
an organization-linked test credential both received only the unavailable-user
instruction to work autonomously. No numerical cap or credential choice was
provided. Do not infer a dollar allowance, use master, retrieve keys or claim paid
acceptance from that response. No paid calls, key retrieval or production changes
were made in this follow-up. Complete the concrete probe authorization and fresh
protected release preparation before claiming live model-usability acceptance.

## Source changes

- [completion_limits.py](../services/control-plane/src/aiflux/completion_limits.py)
  validates an optional canonical release-owned JSON contract with allowance and
  exact provider-limit bindings. Effective limits preserve lower provider limits;
  configuration is not evidence of provider compatibility.
- [config.py](../services/control-plane/src/aiflux/config.py),
  [app.py](../services/control-plane/src/aiflux/app.py) and
  [turnstile_exchange.py](../services/control-plane/src/aiflux/turnstile_exchange.py)
  apply the contract to advertised catalog/model-garden limits. Invalid contracts
  fail closed rather than advertising an unsupported allowance.
- [auto_snapshot.py](../services/control-plane/src/aiflux/auto_snapshot.py) applies
  the coordinated ceiling to Auto candidate descriptors and binds the contract
  hash into the snapshot version. Normal publication must not restore a stale
  1024 descriptor when the successor contract is enabled. Without opt-in, legacy
  descriptor behavior remains at 1024.
- [completion-limits.tf](../infra/project-route/completion-limits.tf),
  [main.tf](../infra/project-route/main.tf) and
  [auto-routing.tf](../infra/project-route/auto-routing.tf) render effective
  per-alias limits and require the contract for output above 1024. Merely allowing
  4096 in variable validation does not deploy or verify that value.
- Added [focused tests](../tests/unit/test_apim4096_source.py) and an
  [isolated offline harness](../tests/contract/apim4096_offline.py).

These are workspace changes, not a clean deployed-parent release artifact. The
workspace also contains unrelated and paused Feature 2 modifications: do not
deploy the whole workspace or infer that source changes are live.

## Actual retained evidence

Evidence directory: .deployment/apim4096-source-20261103-01.

- focused06.xml: **32 passed, zero failures/errors/skips**. Earlier focused04/05
  failures are retained and superseded by this focused run.
- regression11.xml: **128 passed, zero failures/errors/skips** after correcting a
  stale expectation for additive max_completion_tokens metadata. regression10's
  one failure is retained. Suites overlap; do not sum them as unique tests.
- native09/result.json: isolated adapted Terraform validation exited 0; mocked
  Terraform execution exited 1. Its log shows **zero passed, one errored, one
  skipped**, due to a test fixture requesting 4096 without the required persistent
  POC profile (authorization false, RPM 1, daily calls 8). Do not weaken production
  authorization checks to accommodate this fixture.
- native04's mock exit 0 discovered zero tests and is not acceptance evidence.
  Earlier alias/TPM/cycle/provider-harness failures are retained, not replayed.

## Renewed authorization and actual successor evidence

The user authorized the focused fixture repair, remaining validation and live
deployment **only if all compatibility and protection gates pass**. This
supersedes the prior fixture-review stop, not the Feature 2 pause or any release
safety gate.

New namespace: .deployment/apim4096-live-20261103-02. The test fixture now uses
the exact persistent authorized POC profile: 60 RPM, 300000 TPM, 20000000 daily
tokens per model and 50000 daily calls per subscription. Production validation
was not weakened. Native15's original Terraform validation, both mock runs,
compilation and native execution exited 0, but its final Unicode comparison
failed because the redirected Windows console replaced characters with question
marks. That original execution was reconciled, not replayed.

The harness now explicitly uses UTF-8 for redirected native console I/O. The
new native16 run completed once and passed:

- Isolated adapted Terraform validate, mock, C# compilation and execution: exit 0.
- **Two Terraform mock runs passed**, no failed/errored/skipped runs.
- **325 native fixtures**, **341 passed assertions** in 346 retained check records.
- Request boundaries for all 22 explicit aliases + Auto; all three Auto profiles.
- Twenty native parameter-conversion cases covering the **five Claude aliases**;
  this is not all-route provider-translation execution proof.
- Full 15020-code-point Unicode fixture preserved, including its late suffix;
  measured output usage 4096 preserved and 4097 rejected. These are synthetic
  usage values, not actual tokenizer/provider or safety-service evidence.
- Buffered response, normalization-before-safety ordering, unchanged 1000-character
  windows/100-character overlap, three safety nodes and zero retries retained.
- Six Auto candidates/three profiles and Terraform/Python successor hash parity.

See the hash-bound [successor receipt](../.deployment/apim4096-live-20261103-02/CHECKPOINT16.json).
Synthetic provider limits of 8192 are test fixtures only; **no production contract
has been certified**. Earlier Python suites above were retained, not rerun or
summed with these fixture/assertion counts.

## Historical strict-capacity blockers — revised acceptance above supersedes scope

Official documentation was reviewed again. It still does not establish:

1. Azure-hosted FW-GLM-5.3 version 2 output capacity and max_tokens >=4096.
2. Azure-hosted FW-MiniMax-M3 version 1 output capacity and max_tokens >=4096.
3. External ModelArts MaaS ap-southeast-1 glm-5.3 endpoint-specific support >=4096.
4. Azure Mistral-Large-3 version 1 numeric output limit >=4096. Its vendor's
   256K context is not an output allowance, and vendor deprecation is not proof
   of Azure deployment retirement.
5. The exact binding from accepted grok-4-1-fast-reasoning version 1 to the
   documented grok-4.1-fast-reasoning model.
6. Actual full buffered-response safety processing through the final Unicode
   windows. Native normalization/configuration checks cannot certify the opaque
   service implementation or classifier.

The [official APIM safety reference](https://learn.microsoft.com/en-us/azure/api-management/llm-content-safety-policy)
defines response windows in **characters**, not tokens, and says an over-limit
request/response returns 403. This does not establish that every 4096-token
normalized response is processed successfully. No prefix-only scan, truncation,
threshold relaxation or timeout widening was introduced to force acceptance.
The existing 45-second single-forward timeout remains a completion limitation.

The [Azure model reference](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
(commit 2998a46d463e0a297b4828de224a318c4d67420b), partner reference and Grok
guide did not close the exact missing bindings above. The Huawei documentation
index supplied no exact endpoint-capacity evidence. Prior corporate Fireworks
documentation restrictions were not bypassed. Missing evidence is not proof
that the provider cannot support 4096; it is a release blocker under the strict
all-22 requirement. No partial activation is authorized.

## Historical remaining release acceptance — since superseded by final20

The following describes the earlier stop only, not current live status or
authorization to execute again. Later release/probes/final guards are recorded
above; strict full-length capacity/safety proof remains a limitation under the
user's revised acceptance, not a demand to rerun or roll back the completed work.

After the blockers are resolved: complete all-route native translation checks,
obtain a fresh full protected live baseline; compose only the token-limit
delta from exact deployed parents; package matching public contract bytes into
API and Terraform inputs; review publication/version/readback compatibility; and
use a fresh narrowly validated release with protected pre/post guards. Paid
provider probes require separate approval. Do not claim verification flags or
fabricate publication receipts before actual acceptance.

No production release, APIM write, image build/push, Terraform plan/apply,
RBAC/network/SQL/DDL change, secret retrieval or paid inference was performed.
No new full live baseline was captured: the last retained checkpoint remains
root150/child203 with the 1024 output ceiling, **not freshly verified live state**.
Master/subscriptions/permissions, pricing, quotas and Decision-1 were not mutated.
Feature 2 remains paused and excluded. All original test controllers, including
native15/native16 and the exclusive receipt writer, are consumed; do not replay.