# GLM external provider integration

## Current status

**Verified 2026-10-26 23:01 UTC (2026-10-27 local session): deployment and
authenticated customer acceptance complete.** The blocked checkpoint below is
historical and superseded by this section.

- Initial API/portal guarded apply completed at 16:45:50 UTC, saved-plan SHA256
  `64b4e6b3f9063c2d0662f83fffc11d4895b85fef56ee4d5a9cd9dce49ca8baa2`.
- Latest portals, tag `local-20261026t165602z-eee5c65cfe99`, applied at 22:36:34 UTC:
  **0 added, 2 changed, 0 destroyed**, exact image-only guard passed; saved-plan
  SHA256 `e3c13fc6c184bc65746337314acee27ff37a61d438a5a920ced5a9cb33139aca`.
- Installed API: `sha256:b123162c32f24c5d565d8472c3777c293b93d218ba3d483c95bc6b73760c1171`.
- Installed admin: `sha256:36a78667cbbc2c57a41c93181184c4a94cd7178673b6ce868abf2d281a67ae30`.
- Installed customer: `sha256:e77a533672eaecd4936818d1c764e051ca30310027146e942c2029d075ce6560`.
- Fresh `verify-live`, `probe-live`, and `diagnose-activation` each exited **0**.
  Verification follows the exact original apply and portal successor, not the
  superseded initial portal digests. API and portal source manifests match; no
  source/freshness or apply guard was bypassed. All 199 focused tests passed;
  compilation passed, with one existing Starlette warning.
- Full protected baseline matches. API stays private, JWT resolved, ingestion
  unchanged. Storage remains default Deny with `167.103.66.93` and the explicitly
  approved `167.103.66.248` rules preserved. No new cloud configuration writes,
  provider-key reads, secret output, inference retries or counter resets this resume.
- All sites Running/Normal, instances READY. Customer startup evidence mentions
  its current digest. Both portal health probes return 200 and unauthenticated API
  probes return JSON 401. This proves functional activation, not just desired pins.
  Sidecontainer metadata is unparseable; independent per-process digest attestation
  is not claimed for admin/API.
- Bounded gateway GLM inference returned 200, nonempty, stop, 16 prompt / 52
  completion / 68 total tokens. Luna/GPT-4o regressions passed, as did missing/invalid
  key 401, over-cap/unknown 400 and exact-origin CORS. Protected policy hashes match.
  This is **not a fresh all-ten inference run**.
- Existing authenticated admin session worked. At 23:01:06 UTC, audited
  `POST /api/admin/model-deployments/sync` returned 200, `changed=[]`, 11 accepted
  models, auto disabled, gateway not republished, prices unchanged. Before/after
  catalog counts both 11. Discovery has 12 entries: 11 selectable chat models plus
  Decision-1 routing-only/nonselectable; GLM pricing stays unknown.
- At 23:01:37 UTC a real customer Playground **Send** returned 200 and displayed
  **Hello.** for `glm-5.3`, stop, 16 prompt / 29 completion / 45 total tokens.
  The request was nonstreaming with the existing 1,024 completion-token cap.
  Browser credentials stayed in memory. Fresh password login was not tested;
  existing authenticated sessions were sufficient.
- Deployment had already completed on resume; no obsolete plan was replayed.
  The unchanged 24-hour accepted-inventory expiry still applies. Future refresh
  requires genuine evidence and rebuilt source when needed, never timestamp restamping.

Current acceptance:
[gateway/validation/glm-release-20261026.json](../gateway/validation/glm-release-20261026.json).

### Historical blocked status (superseded)

Source support exists for ModelArts `glm-5.3` through the existing APIM development
gateway. **APIM is applied and GLM gateway inference is verified; runtime/catalog/UI
publication is blocked, not complete.** The accepted external inventory records
`gateway_validated=true` and `credential_healthy=true` from the actual 15:36:52 UTC
metered probe, not from a build or configuration inspection.

### Actual release checkpoint — 2026-10-26 16:02 UTC

- APIM apply completed at 15:36:27 UTC: exactly one GLM backend create and one
  existing development API-policy update. Compiler and readback passed. The
  APIM-internal secret remains unmanaged; do not replay the predecessor-only apply.
- GLM returned HTTP 200 with nonempty assistant text, stop finish reason, 25 prompt,
  52 completion and 77 total tokens. Over-cap/unknown-model requests returned 400;
  missing/invalid client keys returned 401. Customer/admin CORS and untrusted-origin
  omission passed. Two post-GLM Foundry regressions (Luna and GPT-4o) returned 200
  with visible output. These are not fresh all-ten regressions.
- Existing API build cm17 succeeded. Its packaged source hashes still match the
  current control-plane/catalog source. Built digest:
  `sha256:b123162c32f24c5d565d8472c3777c293b93d218ba3d483c95bc6b73760c1171`.
  **Not installed**: live API remains
  `sha256:f799db9df6260a5708784c4c2b2ae3a6effbec0595cc572d4e4b818210501807`.
- Both portal sources differ from deployed versions. After cm18's three test
  failures, current fixed source passed full Linux validation cm19: all three
  TypeScript workspaces, 100 tests in 12 files, and both production builds.
  Admin cm1a and customer cm1b built successfully, but are **not installed**.
- Fresh runtime validation passed 192 Python tests and separately 18 Terraform
  mock plans; main Terraform formatting and validation passed. The guarded live
  workflow is blocked before planning by remote-state `403 AuthorizationFailure`.
  It remains at `AddValidationSteps`, not `Validated`.
- Exact existing state backend is account `projpoctokenex`, container `tfstate`,
  key `poc-ids-token-ex/main.tfstate`; tenant/subscription and existing operator
  Blob Data Contributor assignment were verified. Independent authenticated blob
  list also returned 403, request ID `139bab6d-301e-005d-6c63-65bbef000000`.
  Storage network default is Deny with one allowed IP, 167.103.66.93. Current
  storage-facing egress was not established; firewall versus another data-plane
  authorization cause is not conclusively distinguished. No access changes made.
- Independent readback confirms all app images and the protected baseline stayed
  unchanged. No runtime plan/apply, catalog sync, or GLM browser Send occurred.
  Browser `/api/model-deployments` is still 404 at both portals. Existing browser
  sessions now return 401 for authenticated catalog/admin requests; their cached
  ten-active-model screens are not fresh live API counts.

Sanitized staged acceptance: [gateway/validation/glm-release-20261026.json](../gateway/validation/glm-release-20261026.json).
Resume only after legitimate access to the existing state backend is restored by
the authorized operator/network owner (or from an already approved execution
location). Do not open storage, switch to shared keys, copy local state, bypass
the workflow, or apply an obsolete runtime plan. Then rerun exact runtime
validation, bind its fresh saved-plan hash, promote the three images, invoke the
authenticated audited sync, verify live counts and perform bounded GLM Send.

## Approved storage decision — APIM encrypted internal secret

On 2026-10-26 the user explicitly authorized the APIM-stored secret alternative.
This is the default `glm_credential_storage="apim-internal"`, not a silent downgrade
to an inline policy credential. The fixed encrypted secret named value is
`aiflux-glm-5-3-api-key` on the existing `poc-ids-token-ex-apim` service.
The policy contains only `{{aiflux-glm-5-3-api-key}}`, never its value.

The decision avoids identity, network, RBAC and vault changes. Read-only checks found:

- APIM Basic v2 has a user-assigned identity only; no system-assigned identity.
- The vault uses RBAC and a deny-by-default firewall, with AzureServices bypass
  and two existing single-IP rules. Public access is enabled but restricted.
- These facts do not prove APIM Key Vault named-value resolution. The current
  optional Key Vault reference expects the system-assigned resolver; that prerequisite
  is not satisfied. No identity, network, or RBAC changes were performed.

The initial metadata check returned 404. That historical blocker was subsequently
resolved out-of-band: fresh 15:29:14 UTC metadata proved `secret=true` and no
`keyVault` reference; the successful metered 15:36:52 inference proved usability.
No provider-secret value was retrieved by the deployment assistant.

## Credential installation and later rotation (not currently blocking)

Rotate the credential previously disclosed in chat. Never put a replacement in
chat, command arguments, Terraform variables/state, catalog metadata, or logs.
The masked interactive launcher is
[scripts/deployment/install_glm_secret.ps1](../scripts/deployment/install_glm_secret.ps1), invoking
[scripts/deployment/install_glm_secret.py](../scripts/deployment/install_glm_secret.py).
It uses the selected Python interpreter and workspace SDK dependencies. From a
normal interactive PowerShell terminal at the repository root, with no transcript,
debugger, HTTP capture or tracing enabled:

```powershell
& ./scripts/deployment/install_glm_secret.ps1 -CaBundlePath 'C:/Users/p4032099/AppData/Local/Temp/zscaler-login-7860c54ccee94b5d8fa181e004a50458/azure-cli-combined-ca.pem'
```

If the temporary CA bundle no longer exists, supply the current approved combined
CA bundle path; never disable TLS verification. Azure CLI must already be logged
in to the correct existing subscription. The installer uses CLI ARM authentication;
the provider key goes only into the HTTPS JSON request body in process memory.
It is never passed through CLI arguments, environment variables, files, Terraform,
catalog, assistant output, SDK logs or exception text. No credential is accepted
as an installer argument. The prompt requires a real TTY, uses masked `getpass`,
and fails if protected input would fall back to echo. Enter a **new rotated key**
directly in that prompt, not through chat or an assistant input form. The installer
does not and must not read transcripts or reuse any previously exposed key.

The fixed-scope ARM transport performs ordinary metadata GET and PUT only, refuses
redirects, does not configure retries, suppresses exception bodies, and does not
parse the PUT response. It refuses replacement of a nonsecret or Key Vault-backed
named value; rotation requires the metadata ETag to prevent stale overwrites.
Python cannot guarantee zeroization of immutable strings or HTTP buffers: use a
trusted terminal/host with no debugger or request capture.

Readiness is checked by
[scripts/deployment/check_glm_secret.py](../scripts/deployment/check_glm_secret.py):
fixed resource ID/display name, `secret=true`, no `keyVault` reference. Only those
fields and check time are emitted; ordinary GET never invokes `listSecrets`.
Metadata proves storage configuration, **not key validity or inference acceptance**.

### Terraform ownership and deployment gate

In internal mode Terraform never creates, imports or reads the secret named value,
and never exports its value. It references only its fixed identifier in policy.
There is no named-value data source. `glm_internal_secret_verified=true` must follow
a fresh metadata check; `glm_secret_identifier` stays empty and
`glm_resolver_verified=false`. The exact saved-plan guard requires metadata no older
than five minutes, the explicit reviewed storage mode, and exactly **one GLM backend
create plus one existing dev API policy update**. Any named-value ownership, including
a no-op imported internal-secret resource, is rejected. No backend-only partial
deployment is useful while the secret is absent.

Keep existing persistent inputs and full semantic predecessor checks. Never apply
the broad main stack or an obsolete plan. Recheck live metadata, active subscriber,
protected global/legacy hashes and exact current predecessor immediately before a
new scoped plan/apply. Complete the repository validation/deployment workflow with
fresh proof for that plan; historical persistent-POC validation is not GLM approval.

### Rotation and privilege caveats

Rotate the chat-exposed key at the provider before use. Rotate the internal value
using the same installer on the organization's credential schedule and immediately
after suspected exposure or privileged-operator departure. No automatic Key Vault
refresh exists in this mode. After updating the value, verify a bounded harmless
gateway completion and metering before revoking the old unexposed credential; if
compromise is suspected, revoke immediately and keep GLM unavailable until verified.
Updating the named value needs no Terraform import or secret-bearing plan.

APIM encryption/masking is **not** a boundary against administrators with
`namedValues/listSecrets/action`, policy-writing or tracing/debug privileges.
Policy editors can deliberately exfiltrate referenced values. Restrict and audit
those privileges, disable request/response body and Authorization-header diagnostics,
and do not enable APIM tracing for these probes. Review inherited diagnostic settings
before live use. Credential validation and policy failure responses must stay sanitized.

### Optional Key Vault mode (not selected)

Before enabling GLM, review and approve the exact APIM identity and minimum
secret-read access needed **only if selecting `glm_credential_storage="key-vault"`**
for the firewall-supported Key Vault resolver topology.
Keep existing identities and network restrictions intact. Prove control-plane
named-value resolution/refresh without retrieving its value into assistant output.
Do not set `glm_resolver_verified=true` based on metadata or role listings alone.
Do not open the vault firewall. Optional mode manages only the versionless vault
reference, never a raw secret. The current APIM-internal authorization does not
authorize resolver identity, network or RBAC changes.

## Route contract

- Client endpoint: existing `/dev/llm/v1/chat/completions` with the client's APIM
  subscription key and model `glm-5.3`.
- Fixed external upstream: `https://api-ap-southeast-1.modelarts-maas.com/v1/chat/completions`.
- Chat only, nonstreaming, maximum 1,024 completion tokens. No inference retries.
- Provider Bearer credential is injected server-side after inbound safety/PII
  calls. Foundry routes retain managed-identity authentication.
- External responses require nonempty assistant text, valid token accounting,
  and supported provider finish reasons; invalid responses fail closed.
- Pricing is unknown, not free. Exclude the unpriced model from cheapest routing.
- ModelArts receives sanitized input outside Azure. PII redaction is best-effort,
  not a guarantee of anonymization.

Existing persistent POC controls remain: no expiry, 60 RPM, 2,048 TPM, 10,000 daily
tokens at the existing subscription/model scope, and 1,000 calls per 86,400 seconds
at the existing subscriber scope. Preserve counter keys; do not reset counters.

## Release and acceptance

1. Install the rotated credential out-of-band; verify internal-secret metadata.
  Review the exact scoped saved plan: GLM backend and existing API policy only.
  Identity/RBAC/network changes require separate review. Internal secret is unmanaged.
2. Verify diagnostics are safe and policy compilation, then make a bounded harmless
   gateway request. Record only sanitized status, model, assistant presence and usage.
3. Verify invalid credentials, unknown model, over-cap requests, exact-origin CORS,
   sanitized external failures, and existing Foundry managed-identity routes.
4. Only after real success, publish fresh external acceptance evidence and run
   audited catalog synchronization. Deploy any required control-plane/UI images.
  Compare currently deployed image digests and packaged source against the provider-
  aware source; a metadata-only catalog edit cannot repair Foundry-only deployed code.
  Build immutable images only for changed components, using their existing guarded
  workflows; do not publish GLM as selectable ahead of runtime/UI readiness.
5. Verify the customer catalog, actual playground Send completion, and admin
   metadata. No provider credential or secret URI belongs in those responses.

Rollback disables only GLM, restoring the original ten-model policy/catalog.
Rotate/revoke the provider credential if compromised. Do not replay obsolete
expiry-limited plans or change production `/v1`, which remains disabled.

## Storage-alternative validation — 2026-10-26

- 113 focused Python tests passed, including installer/transport security,
  internal-secret saved-plan rejection cases, external inventory, Foundry
  inventory and multi-model route regressions. One existing Starlette warning.
- Terraform validate passed; 7 external-storage mock plans and 11 existing
  default/persistent-control mock plans passed. Changed Terraform formatting passed.
  Existing provider development-override warning remains visible.
- Admin portal, customer portal and shared UI TypeScript checks passed.
- UI Vitest did **not execute**: local Windows esbuild failed during configuration
  startup with `spawn UNKNOWN`. No UI pass or full validation is claimed.
- A separate PowerShell AST-parser check was blocked by constrained language mode;
  its printed success message was invalidated by the accompanying runtime error.
  The secret installer was not executed or fed input by the assistant.
- Scoped whitespace check passed. The unrelated existing trailing blank line in
  the main-stack disabled Terraform test was left untouched.
- The verification task now fails if any check fails, rather than treating a
  blocked UI run as overall success. Per-check results are recorded in
  [gateway/validation/glm-workspace-test-status-20261026.json](../gateway/validation/glm-workspace-test-status-20261026.json),
  with the test report in
  [gateway/validation/glm-focused-tests-20261026.xml](../gateway/validation/glm-focused-tests-20261026.xml).

The bullets above describe the earlier storage-alternative validation attempt,
not the latest release. They are superseded by the timestamped current checkpoint:
APIM apply, metered GLM inference, accepted evidence and immutable builds succeeded;
image promotion, audited catalog sync and actual runtime/UI acceptance have not.
Do not reuse historical workflow status or mistake artifact inventory for live data.