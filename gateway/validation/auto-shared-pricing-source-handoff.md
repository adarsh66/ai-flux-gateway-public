# Shared pricing gateway/infra source delta — not deployed

## Changed paths in this source-only continuation

- gateway/policies/auto-resolve.xml.tftpl
- infra/project-route/auto-routing.tf
- infra/project-route/poc-controls.tf (ownership comment only; existing lifecycle retained)
- infra/project-route/tests/auto-routing.tftest.hcl
- tests/contract/test_auto_price_expression.py
- tests/contract/test_auto_gateway_expressions.py
- tests/contract/test_auto_pricing_preservation.py
- gateway/validation/auto-shared-pricing-source-handoff.md

Backend/UI sources were inspected, not edited. Earlier partial shared-pricing
gateway code was tightened, not reverted. No manifest/default binding changed.

## Actual local evidence

2026-11-01: Python 3.13.1, installed .NET 10 SDK, actual C# 7.3 gateway
expressions and Terraform console locals: **104 passed**, exit 0, 83.21s.
Command test targets: test_auto_price_expression, test_auto_gateway_expressions,
test_auto_pricing_preservation, test_auto_gateway_policy, test_auto_additive_release.
These cover canonical sorted/compact/ASCII hash excluding sha256 (including
Unicode/DEL and reordered transport), closed schema/types/provenance/units,
zero and unknown rates, atomic invalid fallback, fixed six pool/three profiles,
dynamic cost criteria and response validation, and actual informational trace.
Date-shaped provenance remains string data (Newtonsoft date coercion disabled).
Scoped git diff whitespace check also passed.

The native fixtures have no provider request transport. Terraform console does
not refresh, plan or apply. No cloud build, actual cloud apply, paid calls,
roles/network changes or DDL occurred. Editor diagnostics: no errors.

Terraform test invocation returned `Success! 0 passed, 0 failed`; that is **not**
evidence that the added HCL test executed. HCL execution remains pending; the
same inclusion/pool/lifecycle guards have passing Python source/console tests.
No Linux/Python3.11 or actual APIM expression validation is claimed.

Historical reference: .deployment/auto-shared-ratecard-20261101-01/baseline01,
REPORT.json: root137, child193, ARM_requests46, all22, writes0, paid0. Retained
embedded six descriptors/prices/profiles equal current Terraform fallback.
This does not refresh the historical baseline or prove current live state.

## Parent's once-only live policy delta instructions

1. Coordinate the compatible backend release and initial successful pricing
   publication FIRST. The current authorized fragment must be the validated
   schema1 price-only choose/when/otherwise envelope. An unwrapped detached
   fragment is **not safe to include**: mode true alone cannot stop old controls.
   Read back the full fragment, validate its projection and original otherwise
   controls/quota semantics. Do not activate detached controls or duplicate quota.
2. Obtain fresh full protected root/child/API/policy/fragment guards and exact
   accepted decoded policy. Historical baseline is comparison/rollback evidence,
   not authority to overwrite a different live policy. Preserve all22 routes,
   authentication, provider dispatch/body dialect, safety, admission/quota and
   FinOps expressions byte-for-byte outside the reviewed Auto pricing delta.
3. Patch ONLY the existing Auto branch: after embedded snapshot initialization,
   before aiflux-auto-started/Decision-1 criteria, insert mode true, include the
   existing aiflux-dev-unified-poc-settings fragment, mode false, and the reviewed
   price merge expression. Retain embedded snapshot bytes/default manifest binding.
4. Change only the cost/null response check to the source's
   cost_suitability_fallback-aware check; add the source's pricing provenance and
   suitability metadata to routing result and decision-overhead trace. No new
   failure/admission gates, scorer promotion, retries or inference fallback.
   The cost profile uses known-price options if >=2; otherwise all six with
   suitability instructions. Unknown is null, never a fabricated zero tariff.
5. Explicitly preserve MULTILINE accepted C# expressions. XML literal attribute
   newlines normalize to spaces and can turn // comments into a comment covering
   the rest of a function. Full-source render is not a safe live replacement;
   transport-text parity alone is not native FinOps semantic proof. Decode only
   the retained documented XML transport layer and use proper XML escaping once.
6. Independently review the exact saved candidate/predecessor diff and protected
   nodes, native expression tests, whole fragment <=65536 UTF-8 bytes, and raw
   projection <=24576 bytes. Pricing pool_version stays the immutable defaults
   SHA; pricing_sha256/revision/source are informational, not availability proof.
7. Parent executes the existing official guarded once-only policy publication,
   with exact predecessor/ETag, ambiguity reconciliation and full postguards.
   No policy write is performed by this source-only continuation. No paid-call
   acceptance is authorized here. Preserve the runtime fragment on future
   Terraform releases: prevent_destroy and ignore_changes=[body.properties.value]
   remain in source; never replace that payload with packaged controls/prices.

## Remaining release work

Native APIM acceptance, initial live envelope/publication, exact saved-policy
independent review and once-only protected deployment remain the parent's work.
Backend publication serialization, durable last-good CAS/reconciliation and all
save-preservation behavior remain owned by the implemented auto_pricing backend
contract; no duplicate backend publisher or ownership override was added here.