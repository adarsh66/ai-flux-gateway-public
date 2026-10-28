# APIM exact-project correction — 2026-10-26

## Current 06:38 UTC result — authorized call increase applied; API and browser complete

The user explicitly authorized lifting only the existing bounded daily CALL
allowance from8 to1000. This supersedes the quota-blocked06:21 result below.
At2026-10-26T06:37:16.184005Z, the exact saved Terraform plan applied to the
existing isolated state: **zero creates, one existing API-policy update, zero
deletes**. No candidate apply/cleanup or broad main-stack apply ran.
Plan SHA256: 04ab6d7cf9d5be205e3e476ef12cb587be0ad26a6741799aa48ce419c99d5c75.
The only policy-content delta is quota-by-key calls="8" -> calls="1000".
Independent guard and live readback verified identical counter-key
`project-demo:` + existing Caldova subscription ID, renewal-period86400,
unchanged absent first-period-start (no epoch shift), and unchanged expiry
2026-10-27T05:41:01Z. No reset API was called and no counter was renamed.

Unchanged: correct Foundry project and gpt-5.6-luna/2026-07-09; RPM60,
TPM1000, Daily10000tokens, output32, retries0, threshold1, original/redacted/output
safety, prompt shield, fail-closed PII, exact origins, API authentication,
product/subscriber and global route gate. No app, role, network, model, price
or admin settings changed. Global raw hash c67db2cd1b29b5621520621edd84cb043ecb90fc8a68a3dfcd13d800acaacb2d;
both old API hashes a51f2fd903ab277257649d16d19eeb74c839a83ae39dc3f158c91d25e3e9cbfd,
identical before/after. Full before/after guard rejects any other content change.

Actual bounded verification, no inference retries:

- 06:37:41.277221Z direct API hello: **HTTP200, nonempty assistant text**,
  correct customer allow-origin; prompt9/output12/total21tokens.
- 06:38:07.143Z signed-in Caldova customer playground: **HTTP200**,
  real assistant response **visibly rendered** and Completed. Usage9+12=21tokens.
  The existing browser tab/key stayed in memory; no key page or secret snapshot.
- Two model completions consumed **42 reported tokens total**. The direct API
  reported remaining TPM979/daily9979 before the browser call; estimates, not an
  exact current balance or evidence of a counter reset.
- Customer/admin preflight200 with exact respective origins; untrusted200
  without allow-origin. Authenticated models200; missing/invalid keys401;
  unsupported model and output33 both400. These did not invoke model inference.

Validation: **168 focused Python tests**, **eight Terraform mock plans**, validate,
recursive fmt-check and editor diagnostics passed. Current sequential validation
workflow and exact-plan proof completed before apply. New dedicated
[quota runner](../scripts/deployment/project_route_quota.py) never calls destructive
cleanup, even on failure. Original conservative call default remains8; current
reviewed demo override is1000, and restricted candidates still cannot inherit it.
Current sanitized evidence: [final result](../.deployment/project-route-final-result.json),
[quota apply](../.deployment/project-route-quota-result.json) and
[API checks](../.deployment/project-route-quota-verification.json).

**Remaining limits:** 1000calls/86400seconds is a cap, not guaranteed completions
or a dollar budget. Daily10000tokens can bind earlier; all existing safety,
token, output and expiry gates remain. Strict RPM and full negative safety/PII
acceptance, daily-token exhaustion and the monetary ledger remain unverified.
No further inference is needed for this narrow demonstration.

Read-only post-apply replan was **not applied**: it reports one policy update
because ARM reads the policy back as `xml` while the source submits `rawxml`
(body lengths60844/56575). Parsed policy structures are identical; only body
serialization and computed output differ. No zero-drift-plan claim is made,
and no second apply is needed. Protected global/legacy hashes were independently
rechecked unchanged; JSON/AST/fmt and owned whitespace checks pass.

## Historical 06:21 UTC result — deployed RPM60 demo; bounded call quota blocked chat

This supersedes the source-only/no-final-route statements below. The earlier
agent had actually deployed an expiring demo at06:01 without updating the older
candidate report. Its recorded MI completion200/21tokens and bounded TPM429 are
real historical evidence, not current usable-chat or full safety acceptance.

The final route is https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1 for
gpt-5.6-luna/2026-07-09 on the correct poc-ids-token-ex-foundry project.
RPM60 is explicitly authorized; strict rate testing is deferred, **not passed**.
TPM1000, daily tokens10000, output32, threshold1, zero retries and mandatory
original/redacted/output safety, prompt shield and PII are retained. Fixed demo
expiry remains2026-10-27T05:41:01Z. The stable eight-valid-POST/86400-second
demo ceiling is also retained; neither key nor quota epoch was reset.

Actual follow-up found error responses lost CORS because return-response replaces
the response object. Narrow isolated rendering now sets exact-origin CORS and a
fixed non-sensitive error stage **inside** each error return-response, with
set-status first as required by APIM. No wildcard or arbitrary-origin echo.
A failed policy-only compiler attempt triggered verified full baseline rollback;
the corrected guarded recovery plan then applied successfully, SHA256
812e1053329c9b8f0e01e203fc796a090867bad9e6f171a476a5767e6e3e28d4.
Seven owned-child creates/one imported-global update only; no roles, network,
model provisioning, apps or unrelated admin settings changed.

Final independently executed checks at06:20–06:21UTC:

- Customer/admin OPTIONS200 with exactly their respective origin; untrusted
  OPTIONS200 **without** allow-origin. No wildcard.
- Missing/invalid keys401; invalid model400 unsupported_request_shape;
  authenticated models200. Customer-origin rejection responses retain CORS.
- API chat403 bounded_call_quota_exceeded, fixed failure stage quota. The
  authenticated browser actually sent the same bounded Luna request and got
  the same403 with exact customer allow-origin; UI displays the quota message,
  **not** the former generic Network error. No assistant answer claimed.
- Live API policy matches the exact saved-plan structure after only ARM XML
  serialization normalization; both legacy raw policy hashes remain unchanged.

**Real blocker:** the preserved eight-call daily allowance is exhausted, not RPM
acceptance or missing MI permissions. No further inference/fuzzing or counter
reset is attempted. Natural renewal or separately authorized bounded allowance
change is required for more safety/PII and usable-chat checks. Daily-token10000
rejection and full negative safety/PII acceptance remain unverified; call-quota403
must not be mislabeled token-quota acceptance. The route is left deployed under
its expiry/controls, but usable chat is currently quota-blocked.

Current sanitized evidence: [final result](../.deployment/project-route-final-result.json).
The older candidate result is explicitly marked historical and points there.
Final local validation: **147 focused Python tests passed**, five Terraform
mock plans passed, Terraform validate/fmt-check passed and changed source has
no editor errors. Existing provider-override/dependency warnings remain.

## Default-controls follow-up — source only, no new live activation

See [where to edit defaults and how to verify them](gateway-default-controls.md).
Explicit validated inputs now replace hardcoded rate/token/output values in the
isolated mapping. Default authorization never sets acceptance or activation.
Existing source edits outside this mapping/runner/tests/docs are preserved.

The previously applied saved plan was inspected directly, not inferred from the
new render: its single rate-limit-by-key had calls1, renewal-period60 and the
stable subscription/model key, with **no increment-condition or increment-count**.
Therefore the documented outbound-expression increment delay is not present in
that policy. GET models returns before the POST counter; no OPTIONS operation
exists and CORS runs first. Neither explains the second valid POST200.

The actual response timestamps are05:02:53.035779 and05:02:56.038923 UTC,
**3.003144 seconds apart**. From the preceding unsupported-model rejection at
05:02:47.145067 through the second completion is **8.893856 seconds**; the runner
has no wait between those calls. The evidence does not support a model-latency
delay exceeding60 seconds or a local wall-clock-minute-reset assumption. Exact
per-request start times, gateway instance/counter diagnostics were not recorded,
so the precise runtime cause is **unproven**. APIM documents approximate distributed
rate limiting, but that caveat is not evidence identifying this particular cause.
Observed200 remains200; strict RPM1 acceptance was not demonstrated.

Future runner reports include monotonic starts, elapsed time, numeric remaining
headers and fixed RPM-vs-token failure attribution. Out-of-window probes are
inconclusive, and token429 cannot pass the RPM check. No new inference, policy
write, broad apply, RBAC/network/model change or final activation occurred in
this follow-up; historical live evidence below is preserved unchanged.

Read-only ARM verification at **05:24:38 UTC** reconfirmed all three protected
raw policy hashes match, candidate/final APIs absent and candidate backends
absent. No subscription keys were retrieved; no inference was sent.

Local validation: **213 focused Python tests passed**; all **five offline Terraform mock
plans**, Terraform validate and recursive fmt-check passed. These do not accept
the new telemetry attributes live or supply missing negative safety/quota tests.
Existing provider-development-override and dependency-deprecation warnings remain.
The whole-tree whitespace check still reports the pre-existing unrelated final
blank line in the main-stack disabled test; it was left untouched.

## Current threshold1 live result — 05:03:45 UTC: MI works; RPM acceptance FAILED

**The gateway is not activated.** The authorized restricted candidate was applied,
tested live, and removed by guarded finally rollback. Latest sanitized evidence:
[live result](../.deployment/project-route-live-result.json).

- Fixed the actual APIM400 backend compiler error: backend now contains exactly
  one forward-request, zero retry. Typed aiflux-backend-attempt=1 is initialized
  in inbound and remains available to outbound usage accounting.
- Fixed gateway propagation handling with bounded static-models GET polling only,
  never inference retries. Fixed the explicit-operation API's missing implicit
  OpenAPI schema dependency using fail-closed JSON-object parsing and16384 UTF8
  byte cap; existing strict shape/model/field limits remain unchanged.
- Latest177 focused Python tests PASS; Terraform validate/fmt-check and both
  offline mock plans PASS. Existing trusted provider-override warning retained.
- Exact saved plan7creates/1imported-global-update/0deletes independently guarded,
  SHA25686c54d3490e88387f225f464225964571c77c823c924def283057afb9fbbe836.
  No broad apply, new model, role grant, app or network change.
- At05:02:46 models200; missing/invalid keys401 invalid_subscription_key;
  unsupported model400 unsupported_request_shape.
- At05:02:53 the actual gpt-5.6-luna/2026-07-09 bounded MI completion returned
  **200 with assistant text**, prompt9/completion12/total21 tokens, output cap32,
  streamfalse. Original/redacted/output safety and fail-closed PII remained in
  the policy path. This proves a benign traversal, **not** negative safety/PII
  acceptance. No request/assistant text, keys or bearer tokens were printed.
- At05:02:56 the immediate RPM-rejection probe also returned **200**, another
  21 tokens, instead of429. Runner returned failure: RPM enforcement acceptance
  failed. Both requests were separately named probes, not a backend retry.
- At05:03:45 cleanup_verified=true: original global raw SHA
  fc043b134fe3d3cc1cada5472ec975240da4441ea6982776d077e64dba2a8171 and both
  legacy raw SHA a51f2fd903ab277257649d16d19eeb74c839a83ae39dc3f158c91d25e3e9cbfd
  matched; candidate/final API and candidate backends absent. Final route false.

**Current real blockers:** strict RPM1 behavior was not demonstrated (APIM's
distributed counters can be approximate; do not relabel this observed200 as429).
Negative prompt-shield/input/output safety and PII behavior, TPM/daily-quota
rejections, and the monetary ledger remain unaccepted. No browser Send was run
after failed acceptance. Threshold1 is already authorized and is no longer a
decision blocker; gateway MI inference is now proven on the correct parent.
Any further rate-limit repair must retain the8-POST/day candidate ceiling and
7create/1update scope or undergo a separately reviewed scope change. Do not
consume repeated model requests or grant roles to hide a counter failure.

## Historical 04:25–04:28 source correction (threshold0 stopping superseded)

The threshold0/default-approval discussion and no-live-write statements in this
historical section describe only that earlier checkpoint. They are superseded by
the user-authorized threshold1 candidate and actual live outcome above.

The user's correction supersedes the earlier IDS-AI-Token target, inventory,
missing-role conclusion and grant request. **Do not request that grant.** The
ONLY target is
https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project.

Fresh ARM reads and the actual collector completed at **04:25:19 UTC**:

- Parent account **poc-ids-token-ex-foundry**, exact child project both Succeeded.
  Project advertised endpoint exactly matches the URL above. Connections: **0**,
  complete successful list. Therefore this project's verified deployment scope is
  its own parent account, not IDS-AI-Token or arbitrary RG resources.
- Existing deployments: gpt-6.1-sol/2026-09-29/OpenAI/capacity5000;
  gpt-5.6-luna/2026-07-09/OpenAI/capacity5000;
  DeepSeek-V4-Flash/2026-04-23/DeepSeek/capacity2500;
  Decision-1/1/Microsoft/capacity250. All Succeeded, deploymentState null.
  First three report chatCompletion=true; Decision-1 is **not** a chat deployment.
- ARM advertises https://poc-ids-token-ex-foundry.openai.azure.com/ for OpenAI.
  The candidate OpenAI v1 backend is
  https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1,
  **not** the project management URL. MI inference success remains unverified.
- Gateway client5792b72e-1605-4dce-a594-4c430a5af619 /
  principalbcf69911-f34e-4f33-acd8-a36f164db811 has **Cognitive Services User**
  on this parent account and poc-ids-token-ex-safety, freshly reread at04:28 UTC.
  The project-scope query includes that inherited account grant. This is the
  actual permission relationship; project discovery and account inference are
  separate operations. No additional role is requested or granted. No real
  denied gateway-MI inference response exists to justify a new grant.
- Operator project deployments discovery still returns PermissionDenied. The
  collector used complete, verified own-parent ARM evidence. That operator
  discovery denial is **not** gateway inference denial and needs no broad role.

### Implemented routing and conservative configuration

[Runtime defaults](../services/control-plane/src/aiflux/config.py),
[repair planner](../scripts/deployment/apim_route_repair.py), and the fresh
[inventory](../gateway/catalog/foundry-inventory-20261026.json) use the corrected
project. Old-project evidence is rejected. Inventory routes remain empty: no
gateway acceptance is manufactured by refreshing deployments.

[The isolated route mapping](../infra/project-route/main.tf) renders the existing
fail-closed original/redacted/output safety and batched PII contracts, but binds
only gpt-5.6-luna to the exact parent OpenAI backend. It preserves the active
Caldova subscriber and products/aiflux scope, exact customer/admin origins,
legacy closed branches, and backend MI authentication. No legacy gates, model
provisioning, app/private-network settings or roles were changed. Both activation
and acceptance default false. An existing global policy must be imported and
reviewed against a protected rollback baseline before any exact saved-plan apply;
this module is **not** a one-command production deployment runner.

| Configuration authorized by user | Selected value | Acceptance status |
| --- | --- | --- |
| Existing deployment candidate | gpt-5.6-luna, version2026-07-09 | Existing succeeded OpenAI deployment; not inference accepted |
| RPM / TPM | 1 / 1000 | Rendered-policy tests passed; live enforcement untested |
| Daily total token quota | 10000, UTC Daily | Configured token gate, not a monetary ledger |
| Max output / backend retries | 32 / 0 | Rendered one forward, no retry wrapper |
| Safety | EightSeverityLevels, threshold0 for all4 categories | Valid most-restrictive configuration, NOT a passing test |
| Prompt shield / original+redacted+output safety / PII | Mandatory, fail closed | Contracts retained; live MI acceptance untested |
| Model/provider terms | No automatic acceptance | Existing-deployment bounded-use authorization only |
| Cheapest model | Not attested | No comparable approved prices; Luna is a candidate, not an asserted cheapest model |

The default configuration is separately recorded in
[sanitized evidence](../gateway/validation/apim-route-repair-20261026.json).
The planner's authorized-default path does **not** demand redundant cost, safety
or budget-fragment approvals, and never flips legal/safety/runtime acceptance to
true. It still rejects missing actual enforcement/MI/safety proofs.

**Substantive safety incompatibility:** the official APIM contract blocks
severities at or above the configured threshold. Threshold0 therefore blocks even
severity0 benign content. It cannot meet the required actual benign assistant-text
acceptance. The guard explicitly rejects claiming usable-chat acceptance at0.
Do not silently raise the threshold or label configuration as a passed safety test.
If usable chat is required, the safety owner must deliberately choose a threshold
that admits benign content (1 is the smallest EightSeverityLevels value above0),
then require actual prompt-shield, PII, input/output rejection and benign-MI tests.
This is a concrete safety-policy decision, **not** another role/grant request.

Token controls alone are not proof of a dollar budget: APIM documents estimation,
concurrency and per-gateway counter limitations. No prices or monetary guarantees
were invented. Before expanding beyond bounded testing, verify the ledger budget
path and approved prices or retain explicitly accepted token-only limits. Existing
third-party provider deployments and Decision-1/auto were not silently substituted.

### Actual verification and live outcome

- **177 focused tests passed**, including actual Terraform policy rendering,
  corrected-project mismatch rejection, default authorization vs acceptance,
  catalogue/runtime isolation, exact subscriber/origins, zero retries, token quota,
  safety/PII contracts and closed legacy branches. One existing dependency warning.
- **2 offline Terraform plan tests passed**: defaults create no cloud resources;
  even an asserted acceptance flag cannot activate threshold0. These are mock
  plans, not live safety tests. Both isolated and existing Terraform roots validate.
  The saved-plan guard additionally rejects a fully reviewed old-account backend
  and any attempt to open a legacy global branch, not just unreviewed values.
- Terraform init (local existing provider cache), validate and fmt -check passed
  for the isolated mapping. Existing trusted provider-development-override warning
  remains; the new local provider lock has Windows-only checksums. Two discovered
  configuration/schema issues were fixed before the successful validation.
- At04:24 UTC allowed-customer, allowed-admin and untrusted anonymous OPTIONS all
  returned404, no allow-origin. These show an absent route, **not** passing CORS or
  rejected-origin enforcement tests.
- At **04:28:35 UTC**, one actual Caldova subscription-key POST to the required
  /dev/llm/v1/chat/completions route, gpt-5.6-luna, max_completion_tokens32,
  stream=false, no retries returned **404**, no allow-origin and no assistant text.
  Key retrieval/output stayed in process memory; no secret was printed or saved.
  Browser submission was not run because the prerequisite direct2xx never passed.
- Byte-preserving raw policy reads confirmed the original global and both legacy
  hashes below unchanged, global false/false. CLI text-mode reads normalize CRLF
  and yield different hashes; those were not treated as policy drift.
- The mandatory Windows Foundry setup script actually returned exit1: azd missing.
  Previous downloaded azd execution was blocked by enterprise policy. No policy
  bypass, unrelated azd project initialization, fake workflow completion or
  fabricated Validated status was used.
- **No live APIM write, Terraform apply, RBAC/network/app change or new model
  deployment occurred.** The adapter remains absent; this is not a restored live
  gateway. Threshold0 cannot satisfy acceptance, and no exact deployable plan with
  current safety/MI/quota evidence was approved by the validation workflow. There
  are no owned live mutations to roll back.

References: [APIM safety threshold contract](https://learn.microsoft.com/azure/api-management/llm-content-safety-policy),
[token quota caveats](https://learn.microsoft.com/azure/api-management/llm-token-limit-policy).

## Historical 04:01–04:10 evidence — WRONG TARGET, superseded

The following evidence records the earlier mistaken IDS-AI-Token investigation;
it must not supply current target, catalogue, grants, permissions or acceptance.

Inspected 04:01–04:10 UTC using the signed-in operator
xv.puneet.devadiga@singtel.com, subscription
aa28274d-fea0-46d4-b9c8-30f3ef0a0e52 and the provided combined corporate CA.
TLS verification remained enabled. The current application is PostgreSQL/local
auth; no legacy SQL seeding, private API/admin exposure or app release was used.

- APIM `poc-ids-token-ex-apim` still has only `/v1` and `/dev/v1`.
  `/dev/llm/v1` is absent. Existing APIs require subscriptions; both policies
  remain disabled. Existing operations are GET `/models` and POST
  `/chat/completions`, no OPTIONS operation.
- At 04:03–04:04 UTC anonymous OPTIONS for customer, admin and
  `https://untrusted.invalid` each returned **404**, no allow-origin. No key or
  bearer token was attached; no completion was submitted.
- At 04:10:24 UTC raw policy readback confirmed global flags **false/false**.
  Global SHA-256 `fc043b134fe3d3cc1cada5472ec975240da4441ea6982776d077e64dba2a8171`;
  both legacy API hashes
  `a51f2fd903ab277257649d16d19eeb74c839a83ae39dc3f158c91d25e3e9cbfd`.
  These match the earlier baseline; XML bodies were not printed or saved here.
- Caldova-AI subscription e9f2abb0-930b-598a-b210-0ab0b279127f is active,
  ownerless, tracing false, scoped to **products/aiflux**, not the absent
  aiflux-dev-unified product. Do not migrate/recreate it or rotate its key as a
  routing workaround. Preserve that scope and review adding the adapter binding
  with an explicit subscriber allowlist. Product remains unpublished.
- APIM backends, named values and policy fragments are empty. Product aiflux has
  no policy (`ResourceNotFound`). Therefore no existing approved model-key named
  value or budget/quota fragment can be silently reused.
- Target account and exact project are Succeeded, project connections empty.
  All five actual deployment identities/versions/capacities were freshly reread;
  see the [sanitized evidence](../gateway/validation/apim-route-repair-20261026.json).
  Four chat deployments exist; embeddings must not enter a chat route. None of
  these reads attests gateway acceptance or defines a new `auto` alias.
- ARM advertises **https://ids-ai-token.openai.azure.com/**. A candidate OpenAI
  v1 backend would be **https://ids-ai-token.openai.azure.com/openai/v1** with the
  exact approved deployment in `model`. This URL is derived from ARM and the
  OpenAI v1 contract, **not yet verified by an inference response**. The project
  URL ending in `/api/projects/proj-poc-token-exchange` is not the backend.
- Gateway UAMI client5792b72e-1605-4dce-a594-4c430a5af619,
  principalbcf69911-f34e-4f33-acd8-a36f164db811 has Cognitive Services User on
  poc-ids-token-ex-foundry and poc-ids-token-ex-safety. The corrected exact-target
  `role assignment list --assignee ... --scope IDS-AI-Token --include-inherited`
  query returned **zero assignments**. An earlier `--all`/`--scope` combination
  failed; it was not treated as empty evidence. No inference under this identity
  was attempted. Model/PII/safety service existence is not runtime access proof.
- Customer cost/network and model terms/quota attestations are false. No current
  approved severity threshold was supplied. Historical deployment_approved=true
  for infrastructure does not supply route-specific model/safety acceptance.

Foundry MCP discovery returned403 for an unrelated agents/read data action; its
troubleshooting guidance was consulted, and the exact account/project ARM reads
were used instead. **No agents/read or broad Foundry role is needed/requested for
this repair.** Operator project data-plane discovery denial from the earlier
inventory is separate from gateway inference permission.

## Implemented safe preparation

[The repair planner](../scripts/deployment/apim_route_repair.py) creates a
project-specific proposal from sanitized evidence and separate explicit approval.
It does not retrieve secrets, make HTTP calls, apply infrastructure or grant roles.
Without approvals, its CLI exits2 with named blockers; it never emits an apply
authorization, even when prerequisites would permit scoped planning.

The proposal preserves Caldova's existing product, requires the exact subscriber,
exact customer/admin origins, two operations, explicit live OpenAI deployment
version, existing gateway MI, accepted safety/PII evidence and an independently
reviewed subscription budget/quota fragment. It keeps both old routes disabled,
limits acceptance smoke output to32 tokens and specifies zero backend retries.
No speculative model list, static catalog acceptance or automatic routing is used.

The associated `guard_plan` rejects non-applyable/errored/deferred plans,
deletions/replacements, unrelated resources, changed or unknown writable values,
wrong ARM targets, omitted/duplicate changes and stale/failed readiness. It requires
complete reviewed before/after values, not just a resource-address allowlist.
**This is a preparation guard, not a completed deployment implementation or proof
that an arbitrary reviewed policy is secure.** Policy rendering/security review,
the project-specific Terraform mapping, protected rollback export, exact saved
plan and current validation workflow still must complete after blockers close.

Existing [legacy adapter Terraform](../infra/terraform/dev-unified.tf) hard-codes
Luna/Sol in two other regions and requires Haiku. Its gate must not be enabled or
weakened to substitute this project's models. No new model provisioning is needed
or authorized. Existing source-only exact-origin CORS work was preserved.

## Superseded decisions — no current grant request

The earlier IDS-AI-Token grant request and gpt-5-mini selection are withdrawn.
Use only the corrected target, existing inherited roles, authorized conservative
configuration and actual blockers at the top of this document. The sequence below
is historical procedure, not authorization to activate or reuse old acceptance.

Then render/test the candidate policy, capture a protected rollback baseline and
review a saved Terraform plan limited to the new adapter/operations/backend and
existing product binding, plus **only** the validated `/dev/llm/v1` global-gate
branch. Preserve existing `/dev/v1` and `/v1` policy hashes and closed branches.
Complete azure-validate and azure-deploy for this exact scope before any apply.
Never use the historical portal validation as current evidence.

After apply: read back all scopes, test both approved origins and a rejected origin,
missing/invalid keys, unsupported model, then **one** approved subscription-bound
non-stream POST with16–32 output tokens and no client/backend retry. Keep the key
only in memory. Only after direct2xx with actual assistant text should the shared
browser navigate to `/playground`, select that exact model, and submit one bounded
message. Do not snapshot keys/subscriptions pages. Success requires actual browser
assistant text as well; otherwise record failure and use the scoped rollback.

## Historical validation (before user correction)

- **89 focused tests passed**, including46 new proposal/plan-guard tests and the43
  existing policy/CORS/adapter-verifier cases. One existing Starlette deprecation
  warning. Initial test invocation referenced a nonexistent unit test path and
  exited4; corrected to the real contract verifier before the successful run.
- Terraform validate and changed development Terraform formatting check exit0;
  existing trusted provider-development-override warning remains.
- Editor diagnostics: no errors in the new planner/tests.
- Actual evidence CLI execution exits2 with ready_for_scoped_planning=false and
  apply_authorized=false. Syntax parsing and scoped/new-file whitespace checks
  pass. No missing approval was filled with a synthetic fixture.
- Current azure-validate workflow entry was attempted with terminating errors;
  exits1 at UTF8Encoding under PowerShell ConstrainedLanguage. No workflow step
  was acknowledged, no current scope marked Validated, and no policy bypass was
  attempted. This is an additional local tooling limitation, not evidence of an
  APIM permission failure and not the reason to bypass the substantive blockers.
- No Terraform plan/apply was generated: permission, cost, safety and budget/quota
  prerequisites fail **before** inference activation is safe. No resources were
  created, modified or removed, so no rollback mutation was needed.