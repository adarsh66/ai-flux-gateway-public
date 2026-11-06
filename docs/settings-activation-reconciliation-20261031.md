# Settings activation reconciled — no apply replay

## Actual installed state

- The [original apply receipt](../.deployment/auto-additive-buildplan01/settings-activation03/activation06/APPLIED.json) records the sole successful settings apply at **2026-10-31 13:51:49 UTC**, exact plan SHA256 `d732ea24095d4e31e05a476e14b58c9a795a2a4aecd2101039ebf0857327b5ff`. Its historical pending status is preserved, not overwritten.
- The [completed postguard report](../.deployment/auto-additive-buildplan01/settings-activation03/activation06/REPORT.json) supersedes the pending postguard state: **PASS**, root serial **132**, child serial **193**, API settings **52 ARM / 49 Terraform**. Exactly five additions; all existing settings, other apps, pins, security/network/RBAC, backend inventory, and 22 explicit routes preserved. All eight policy format/scope readbacks match.
- The previous local comparison stopped only on Terraform sensitivity metadata. The [exact proof](../.deployment/auto-additive-buildplan01/settings-activation03/activation06/postapply-remaining08/exact-sensitivity-proof.json) binds the added `app_settings` sensitivity marker to the exact saved plan. No values were normalized or waived.
- The retained opening root GET was not replayed. A fresh matching HEAD and closing full read bound the remaining capture. API/gateway installs and settings apply were not repeated.

## Actual customer publication and browser

The [authenticated browser observation](../.deployment/auto-additive-buildplan01/settings-activation03/activation06/readiness09/browser-observation.json) captured the app's normal GET response after reload, without extracting a token: **HTTP 200**, `ready: true`, profiles `balanced`, `cost`, `quality`, `architecture: gateway-direct`, `validation_mode: bounded-production-direct-v1`, `runtime_verified: false`. The rendered selector contains **22 explicit models plus auto**. No DOM option was injected and no Send/key reveal was used.

The [strict-CA asset/offline report](../.deployment/auto-additive-buildplan01/settings-activation03/activation06/readiness09/REPORT.json) confirms the actual served JS contains the availability endpoint. It is **669507 bytes**, SHA256 `2b1921a65f265cbd82eac8d8fd8355811f77d68bb1717a56ea6192e0ada00948`. Asset name and rounded size match the hash-bound original cm4f build log; the current customer image digest matches cm4f. This is not claimed as an image-extracted byte-for-byte asset comparison, which was unnecessary once presence was proven.

**No missing portal code was demonstrated. No portal release is needed.** The earlier “22 only / no request” observation is no longer reproducible; its exact transient cause is unproven. Retained UI source fetches availability asynchronously and only adds Auto once `ready` is true, so a pre-response view alone cannot establish missing code.

## Readiness versus remaining acceptance

Offline execution of the packaged modules with retained inventory/defaults and the actual inline publication reproduces `ready: true`, three profiles and six candidates. The publication matches exactly. Schema 2 deliberately permits bounded-production readiness while runtime evidence remains absent; readiness is not proof of successful managed-identity Decision-1 scoring, completion, selected-model response, or overhead trace persistence.

**Genuine remaining gap: runtime acceptance is unproven (`runtime_verified: false`).** No paid calls were made to close that gap. The receipt budget is not reported as exercised or as an enforced global quota based on this read-only work.

Direct API health **403** is expected with disabled public ingress and is not an application failure verdict. Portal `/api/health` returned JSON404 (route absent), not a successful health assertion; authenticated availability200 is the relevant functional observation. Anonymous availability remains JSON401 as expected.

## Boundaries

No new cloud writes, apply replay, replan, build, model calls, Send, token extraction, ingress changes, or rollback. Existing pinned CA verification remained enabled. Original receipts and STOP evidence were preserved. AppLens returned a platform CPU/single-instance advisory, but it does not establish the cause of the earlier missing Auto observation and prompted no changes.