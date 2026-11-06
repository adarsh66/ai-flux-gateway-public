# Additive Auto release — source implementation checkpoint

## Successor implementation (clean01)

The formatting and clean-context blockers below are now resolved by the separately
named [clean implementation and exact release/rollback requirements](auto-additive-clean-release.md).
Actual [offline check result](../.deployment/auto-additive-clean01/checks/result.json)
passes: one exact fmt patch/check, minimal ten-file cm45 API overlay, byte-exact
68-file cm4f customer context (no customer rebuild), Python syntax/import checks
and direct Node shared-UI/customer typechecks. No cloud/build/inference or frozen
diagnostic replay. Historical receipts and findings below remain as the original
checkpoint, not the current clean-composition status. Independent review, Linux
validation, real publication readback/review hashes and parent acceptance remain.

## Decision / readiness

Implemented the additive source contract and affected offline tests. **Ready for
independent narrow source review; NOT ready to deploy or advertise Auto.** No
cloud reads, writes, image builds, paid inference, Playground Send, identity,
permission, database, or network changes were performed for this checkpoint.
Worker 9744 and diagnostic controllers/successors 06–12 were not rerun or killed.
Historical diagnostic proof is outside this release's critical path.

The normal default remains OFF. Public inference remains the existing chat
completions endpoint with exact lowercase `model="auto"`; the existing dropdown
uses the authenticated availability endpoint. Default profile is balanced, with
the existing cost/quality profiles and reviewed six candidates unchanged. No
production retry/fallback has been added. The legacy private resolver remains
separately default-disabled and must not be enabled for this release.

## Source changes

- [Terraform Auto gate](../infra/project-route/auto-routing.tf): optional
  `auto_routing_direct_release`, mode `bounded-production-direct-v1`, permits
  explicit pending-runtime validation in place of historical runtime evidence.
  Requires two attempts/scorings/completions, zero retries, no fallback, stop on
  explicit regression, exact defaults/predecessor/candidate and review/rollback
  hashes. Null preserves default-off behavior. Existing security gates remain.
- [All-22 gate](../infra/project-route/foundry-successor22.tf): allows Auto only
  with that satisfied gate; preserves exact membership, native backend identities,
  deployment readiness and original POC exclusions. Historical exact-eight gate
  remains unchanged.
- [Snapshot/publication](../services/control-plane/src/aiflux/auto_snapshot.py):
  frozen default prices bind their original rate manifest rather than the expanded
  display manifest. Current accepted-price eligibility still gates candidates.
  Schema 1 continues to require actual runtime proof. New schema 2 explicitly
  states `runtime_verified=false` and requires separate default-off opt-in,
  source/readback/review/rollback bindings and the exact bounded budget.
- [Settings](../services/control-plane/src/aiflux/config.py): adds default-false
  `auto_routing_direct_validation_enabled`.
- [Availability](../services/control-plane/src/aiflux/decision_router.py): schema-2
  readiness includes the pending validation mode and `runtime_verified=false`;
  corrupt/unavailable publication fails closed, without inference or seeding.
- [Unit tests](../tests/unit/test_auto_additive_release.py),
  [new contracts](../tests/contract/test_auto_additive_release.py), and
  [mock tests](../infra/project-route/tests/auto-routing.tftest.hcl) cover the
  bounded contract. The existing
  [render helper](../tests/contract/test_auto_gateway_policy.py) additionally
  returns final policy and native validity for the new final-composition check.

The existing gateway MI → fixed Decision-1 endpoint path, safety/PII order,
closed six-model choice and separate decision-overhead trace are reused; the
gateway templates were not rewritten. Existing selected-model completion usage
is not replaced with scoring usage. Missing scoring tokens/cost remain unknown,
not zero/free. Actual trace persistence is still pending runtime acceptance.

**These hash contracts are not automatic paid-budget enforcement, proof of
review, or runtime proof.** Parent must own an exclusive durable two-attempt
ledger and actual independent review. No schema-2 publication receipt with
invented readback/review/runtime hashes was generated. The historical schema-1
publication packager was not repurposed.

## Actual validation and durable receipts

Receipts are in [.deployment/auto-additive01](../.deployment/auto-additive01/).
Launchers use exclusive intent/output creation; consumed launchers must not be
replayed. Tests used existing Python 3.13 and installed dependencies, existing
Terraform/providers, no init/install/cloud. Windows-blocked Ruff/esbuild were not
attempted. No UI runtime tests or live all-22 inference are claimed.

| Actual run | Result | Receipt |
|---|---|---|
| Initial affected Python suite | 47 passed, 20 setup errors (HCL bracket typo, subsequently fixed) | [initial JUnit](../.deployment/auto-additive01/pytest.xml) |
| Corrected render contracts | 25 passed, 1 failed (projection retained Auto error node) | [render JUnit](../.deployment/auto-additive01/render-fix.xml) |
| First projection correction | 1 failed (asserted no retry on pre-wrapper policy) | [projection JUnit](../.deployment/auto-additive01/projection.xml) |
| Corrected explicit-route projection | **1 passed** | [projection result](../.deployment/auto-additive01/projection-corrected.xml) |
| Correct Windows-filter Terraform mocks | **9 passed, 0 failed** | [mock log](../.deployment/auto-additive01/terraform-corrected.txt) |
| Actual final direct-release policy and hash-drift rejection | **1 passed** | [final policy JUnit](../.deployment/auto-additive01/final-policy.xml) |

Passing coverage is distributed across retained runs, not a fictional single
all-green rerun. Previously passing cases were not blanket replayed. An earlier
slash-form Windows Terraform filter ran **zero** tests; it is not counted.
The final-policy test confirms exact all-22 membership/native validity, one
scorer request, one forward request and no retry in `local.policy` under the
source-bound contract. Pre-wrapper explicit backend/body/auth/safety/limit XML
fingerprints match after removing only Auto hooks. Timeout/schema/denied tests
are structural branch-isolation checks, not executed APIM C# fault injection.

Editor diagnostics reported no errors in edited source/tests. Final formatting
check still exits 3 for the Auto Terraform file (whitespace only); other checked
HCL files pass. Three formatting correction attempts are retained; **formatting
remains an explicit handoff blocker**, not a claimed pass. See
[final check/source hashes](../.deployment/auto-additive01/final-source.json).

## Clean release composition: not yet safe

Preserve API **cm45**, ingestion **cm40**, admin **cm4e**, customer **cm4f**.
These are retained baseline labels, **not freshly verified live state**.

The local [source audit](../.deployment/auto-additive01/audit.json) and
[API delta](../.deployment/auto-additive01/app.py.composition.diff) found that
the workspace entrypoint includes unrelated usage/catalog changes versus the
retained clean API context. Do not copy the whole dirty entrypoint or build the
whole tree. Clean cm45 production layering also installs selected modules in
both source and site-packages locations. The clean release must preserve both.

Before packaging, compose only the authenticated availability endpoint and
required settings/snapshot/router dependencies onto the exact cm45 production
module baseline. Do not include admin profile mutation or legacy resolver
activation merely because the dirty workspace contains them. Audit dependencies,
pricing/catalog package data and existing query packaging. Preserve cm45's
usage/catalog/SGT behavior. Compare against its production overlay, not only an
older full context. No clean image context has been certified here.

Portal baselines must likewise come from the retained cm4e/cm4f clean contexts;
review only existing availability-driven dropdown/profile additions if absent.
Do not rebuild ingestion or introduce SQL DDL. Retain the existing overhead KQL
packaging; verify actual telemetry inheritance/persistence after acceptance.

## Parent release / rollback sequence (not executed)

1. Finish whitespace and clean source composition; independently review exact
   source manifests, clean build contexts, final saved plan and final policy
   digest. Review must bind final `local.policy`, not just pre-native
   `auto_with_error`. No broad dirty-tree build. Authorized Linux/no-push
   validation precedes any separately authorized production build/push.
2. Freshly capture protected production policy/config, full all-22 route/backend
   inventory, global/product inheritance, auth/limits/counter namespaces, image
   pins, ETags, relevant existing identity/role/network state and rollback bytes.
   Preserve cm45/cm40/cm4e/cm4f unless the narrow reviewed release changes an
   explicitly approved leaf. Unknown/missing settings are not an empty-settings
   proof. Any unexpected drift blocks live action.
3. Parent reviews and applies only the exact authorized saved deployment artifact.
   Gateway acceptance first; API advertisement/publication afterward. Default OFF
   in normal configuration; pending-validation schema 2 is a deliberate release
   opt-in, not a blanket claim of readiness. Populate only actual review,
   policy-readback and rollback hashes. Do not use a diagnostic controller.
4. Perform bounded acceptance only after authority and guards: at most **two
   end-to-end Auto attempts**, one greeting via Playground and then (only if it
   passes) one direct API arithmetic request. Each permits one scoring request
   and at most one completion; failed/unknown attempts count. No automatic
   retries or fallback. Record the attempt before sending. Stop on first failure
   or explicit-model regression. No speculative/repeated Send.
5. Verify MI scoring, selected alias/profile/version metadata, unchanged explicit
   routing/auth/safety/limits, selected completion usage, and separately persisted
   correlated decision overhead. Metadata/offline checks do not prove all-22 live
   inference. Missing telemetry/token/cost remains unverified/unknown.
6. On Auto failure, disable Auto acceptance and hide its advertisement immediately;
   do not leave a ready publication pointing at a disabled route. On explicit
   regression restore the freshly captured, independently reviewed exact policy,
   settings and affected image pins, then verify readbacks. Never overwrite drift
   with historical rollback bytes. No new permissions, firewall changes or DDL.

Outstanding release blockers: whitespace check, independently reviewed clean
source contexts and Linux/UI validation, actual parent source-bound publication
artifact, fresh protected production reads, exact saved-plan review and authorized
runtime acceptance. None is substituted with fabricated evidence.