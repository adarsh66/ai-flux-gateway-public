# Persistent POC output and expiry update — 2026-10-26

## Current final verification — 13:00–13:10 UTC

**All ten models now pass both direct HTTPS1024-token probes and actual
customer browser select-and-send tests**, with nonempty text, stop and Completed.
Fresh customer/admin API responses confirm exactly the same ten enabled chat
models, each1024; auto is disabled. Decision-1 is disabled/routing-only metadata,
not a chat route. This supersedes the earlier catalog-mismatch findings below.

See the [final per-model results and exact metadata evidence](multimodel-acceptance-20261026.md)
and [sanitized acceptance record](../gateway/validation/multimodel-acceptance-20261026.json).
263 focused Python tests and11 Terraform mock tests passed; Terraform validate,
fmt and all three TypeScript checks passed. Vitest remains blocked before
collection by native esbuild spawn UNKNOWN. Protected policy hashes still match;
no expiry, quotas or counters were changed/reset by verification.

Remaining release limitation: the running API returns404 for the newer source
deployment-metadata endpoint, and deployed catalog/admin wording still suggests
a Decision-1 simulator. Newer deployment-status UI, audited sync release,
Decision-1 inference integration, pricing and strict exhaustion acceptance are
not attested. Working ten-model chat does not imply these features are deployed.

## Historical execution verification — 12:25–12:30 UTC

Executed the existing runner's tests and `probe` command; no replacement runner
or framework was written. Python 3.13.1 used the existing workspace dependency
path. Discovery collected 28 persistent guard tests; the four existing
persistent/model/demo/live suites passed 95 tests (one existing Starlette
deprecation warning). Terraform validate and recursive fmt-check passed;
11 Terraform mock tests passed. Provider development-override warning remains.

Fresh ARM reads verified that the policy already equals the approved applied
plan, its saved-plan/source hashes still match, the subscription is correct,
and all protected policy hashes remain unchanged. Authenticated live `/models`
returned HTTP200 and exactly all ten manifest routes. The separately saved
current verification plan has SHA256
a05599a7f273d56aa575cede70b42b8072ae931fb7f24ddc9c51b5c3a74afa86:
0 creates, 1 policy update, 0 deletes, with **no semantic policy change**;
ARM exports `xml` while source requests `rawxml`. It was NOT applied. The
original predecessor-only plan/apply runner must not be replayed against an
already-applied policy or used to overwrite the protected rollback evidence.
No validation status was forged or advanced for this read-only verification.
The original completed validation/apply proof remains the deployment evidence.

Fresh outcomes, using the same harmless approximately80-word rainbow prompt:

- Existing runner `probe`, 12:28 UTC: Luna requested256, HTTP200,256 completion
  tokens, all256 reasoning, no visible text, finish_reason=length. Runner exited1
  with `output_over32_verified=false`; this failure is retained in the current
  ignored probe artifact, not relabeled success. Output1025 returned400;
  missing and invalid subscription keys returned401.
- Direct API GPT-4o, 12:30:19 UTC: requested256, HTTP200,101 completion tokens,
  zero reasoning,22 prompt tokens,123 total, nonempty assistant text and
  finish_reason=stop. Exact customer CORS origin matched. Protected hashes
  were rechecked after this request and still matched.
- Actual signed-in customer browser after full reload/catalog fetch: selected
  Luna, displayed1024, requested1024, HTTP200,416 completion tokens including
  312 reasoning (104 non-reasoning),21 prompt tokens,437 total, stop. A full
  rainbow explanation visibly rendered with Completed. This is a distinct
  bounded user-authorized test, not an automatic inference retry.

At12:30 the catalog mismatch was verified: refreshed browser choices included
older nonmanifest entries and omitted several of the ten gateway routes. The
default `auto` selection advertised16384, while explicitly selecting Luna
correctly advertised1024. No claim of ten-model portal reconciliation or
all-model runtime acceptance was made at that time. Separate scoped metadata
reconciliation was still necessary; no broad apply, metadata reset, or speculative
route-acceptance evidence was used to conceal that limitation. No credentials,
raw application settings, request headers or response text were saved here.
These are historical findings, superseded by the13:05–13:06 live API readback
and ten-model browser verification linked above; they are not current blockers.

## Applied scope and effective controls

The latest explicit user authorization supersedes the earlier preserve-expiry
plan. Existing endpoint:
https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1

| Control | Effective value |
| --- | --- |
| Maximum requested completion |1024 tokens; all ten current model-specific policy checks |
| Token rate |2048 prompt+completion tokens/minute per existing subscription/model key |
| Request rate |60 requests/minute per existing subscription/model key |
| Token quota |10000/day per existing subscription/model key, Daily UTC reset |
| Call quota |1000 valid POSTs/86400 seconds per existing subscription key |
| Deadline |None; expiry gate removed, empty expiry input |
| Retries |0; exactly one backend forward |
| Safety |Threshold1, original/redacted/output checks and prompt shield |
| PII |Mandatory fail-closed inspection and redaction unchanged |
| Access |Existing exact subscriber/product and customer/admin CORS unchanged |
| Production acceptance |False; persistent authorized POC only |

Daily token quota is not an aggregate ten-model budget or monetary ledger.
Existing counter keys `rpm:`, `tpm:` and `project-demo:` are unchanged; no epoch,
release identifier, timestamp or first-period-start was introduced. APIM's
distributed rate/quota approximations and provider-native limits still apply.
Reasoning can consume completion allowance:1024 is not a promise of1024 visible
tokens or a reason to allocate unlimited reasoning.

## Exact deployment and rollback evidence

Applied at2026-10-26T12:12:06.872573Z through the existing isolated
[Terraform module](../infra/project-route/main.tf), not the main stack.
Saved plan SHA256:
4bb58ff5bb842bbfbb4081071b0276cbc72b675f2ae0f730f7b5c870fb03cfae.

Exactly0 creates,1 update to azapi_resource.project_policy[0],0 deletes.
The [guard](../scripts/deployment/project_route_persistent.py) compares all
policy XML after only the output32->1024, TPM1000->2048 and expiry-removal
transformations. It also checks every input, exact resource target, unknown
values, source hashes, active product subscriber and live predecessor.
Live readback matched. Global and both protected legacy policy hashes remained
unchanged. No permissions, network, model deployments, product bindings,
API children, image pins, global-policy writes or destructive cleanup occurred.

Protected local artifacts (ignored, not release credentials):

- [.deployment/project-route-persistent.tfvars.json](../.deployment/project-route-persistent.tfvars.json): current final inputs, all ten routes, no exclusions, persistent flagtrue and expiryempty.
- [.deployment/project-persistent-review.json](../.deployment/project-persistent-review.json): exact plan and source/baseline hashes.
- [.deployment/project-persistent-apply.json](../.deployment/project-persistent-apply.json): apply/readback proof.
- [.deployment/project-persistent-rollback-policy.xml](../.deployment/project-persistent-rollback-policy.xml): exact pre-update policy baseline. Any rollback requires a fresh independently guarded plan; never replay the original candidate cleanup.

Historical demo/quota/model variable files and plans remain predecessor evidence,
not the current applied input set. They must not be replayed to reintroduce expiry.

## API, metadata and browser proof

The API runtime had no AIFLUX_GATEWAY_MAX_COMPLETION_TOKENS setting. Existing
Luna database metadata advertised32. Through the existing signed-in admin API,
only that cap was changed to1024, with all other submitted row fields retained.
Readback of admin and customer APIs confirmed1024; other model caps were unchanged.
The existing portal automatically displayed “Development output limit:1024
tokens.” No application image or runtime-settings update was needed.

- API GPT-4o: HTTP200,99 completion tokens,22 prompt tokens,121 total,0 reasoning,
  finish_reason=stop and nonempty text. Request capped256. Actual evidence:
  [.deployment/project-persistent-visible-api.json](../.deployment/project-persistent-visible-api.json).
- Signed-in customer browser, Luna: HTTP200, requested cap1024,131 completion
  tokens including29 reasoning,21 prompt tokens,152 total; finish_reason=stop.
  Full approximately80-word rainbow explanation visibly rendered with Completed.
- Initial Luna256 probe: HTTP200 but256 reasoning tokens and empty visible
  content, finish_reason=length. Recorded as failure, not successful completion.
  No automatic inference retry or unlimited reasoning was introduced.
- Request cap1025: HTTP400 unsupported_request_shape. Missing/invalid keys:401.

Credentials existed only in process/browser memory. No credential file was read,
and no key, bearer token, raw appsettings or secret policy was printed.

## Historical validation and subsequent multi-model completion

95 focused policy/demo/model/executor Python tests passed;11 Terraform mock plans
passed. Terraform validate and recursive fmt-check passed. New rejection tests
cover foreign writes, creates/deletes, unknown bodies, wrong targets, route
changes, quota increases, safety/PII changes and counter/epoch changes.
Additional catalog tests exercise1024 and preservation of a smaller route bound.

The initial policy-only update retained all ten aliases but did not itself
reconcile the portal catalog. Subsequent live readback now confirms that catalog
reconciliation and fresh all-model1024/browser acceptance; the source inventory
now contains ten accepted bindings. The final report above separates that
working runtime metadata from newer source features not yet attested deployed.
Decision-1 remains outside chat dispatch. No pricing or full negative
safety/rate/quota exhaustion acceptance is invented.