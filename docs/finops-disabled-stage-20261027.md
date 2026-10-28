# FinOps disabled runtime stage — applied 2026-10-27

> **Latest06:17UTC:** this disabled stage is historical. The later host plan was
> actually applied05:57:58UTC; current host enabled=true, timer disabled=true,
> catalog=true/cutoff present. New corrected ingestion-only image cm1u was built
> but NOT applied: current bounded task's disabled/no-cutoff prerequisite fails,
> and scanner has two findings. All current pins/full settings/security unchanged.
> Do not replay this stage or the already-applied host/catalog plans. See the
> [fresh bounded build/plan/readback evidence](finops-activation-20261027.md#latest-bounded-execution--061745-utc-built-not-applied).

> **05:09 UTC activation follow-up:** forward-only activation is delegated; a
> historical-cutoff question is no longer the blocker. Actual package/live
> catalog membership failed (9 missing + 9 obsolete aliases). Host/timer remain
> disabled; no reapply occurred. See [current activation evidence and exact
> blocker](finops-activation-20261027.md). The applied-stage evidence below is
> retained unchanged and is not an activation approval/proof.

## Result

**Applied once; read-only verification passed. Activation remains blocked.**
Terraform completed at **04:53:24.237114 UTC**. The protected applied marker binds
the exact reviewed saved-plan SHA256:

`6e8232a8fc591894b43d1557ecc9721c1e110349eaef80c34ffbd80775d6d090`

The saved plan and settings remain ACL-protected under
.deployment/finops/finops-20261027t040422z/disabled-stage-preserved-config.
Earlier rejected plans and the initial failed verification were retained.
Do not rerun apply: apply-intent.json and applied.json both exist.

## Immutable image publication

Reused completed tag **finops-20261027t040422z**. All current application-source
manifests and remote run/digest bindings matched. Controller changes are not
inputs to any of these four images. **No rebuild or new probe occurred.**

| Component | Existing successful run | Configured sha256 digest |
| --- | --- | --- |
| API | cm1p | 7c8b9c715963a1a365895c38f2e79cb1bbfff0b4e166a57cec6e16df9f05ffce |
| Ingestion | cm1q | 81b2c6a96c8a82807eb9bec6098fc305af664b55d97e44e1a3b226e8f3efd56f |
| Admin | cm1r | 4606e769e95ac647c7ba175f5c0e152baf16dbf02a78fd5d1c3f1a6be289baed |
| Customer | cm1s | 568cd3f1d4d88cf59ff63528f4baa6b84827a3da45e6ede5da13395d06de29a1 |

All pins use pocidstokenexacr.azurecr.io/aiflux-{component}@sha256:{digest}.
This is configured-image proof, not successful host startup or usage acceptance.

## Actual validation and exits

- Azure deployment guidance was fetched successfully; current Azure validation
  workflow completed sequentially through UpdateStatus with fresh Section 7 proof.
- 61 focused controller/release tests passed before apply. Exact finite guard:
  four in-place updates; no other writable fields, Create/Delete or replacement.
- Generated Terraform init/validate/default workspace passed. All source,
  controller, artifact and plan hashes plus current security/settings baseline
  matched. Existing sole identities and all four AcrPull assignments rechecked.
- Existing Linux validation cm1n reverified against current source: three
  TypeScript workspaces, 103 tests/12 files, both production portal builds.
- Terraform apply exited **0** and wrote applied.json. The encompassing apply
  task exited **2 only after apply**, because its first verification treated
  Azure's three injected registry settings as unexpected. **No apply replay.**
- Read-only verification now checks the exact registry URL and exactly empty
  username/password, then compares every remaining Function setting against
  the pre-apply target hash. No configurable-setting allowlist was widened.
  Additional rejection tests cover credentials, foreign URL, missing/extra
  settings, timer/cutoff and authentication drift.
- Final **70 tests passed**, one pre-existing Starlette deprecation warning;
  read-only verification task exited **0** at **04:57:24 UTC**. Full protected
  baseline matched; API/admin/customer complete settings hashes unchanged.
- Final ARM-only evidence collected at **04:58:42 UTC**. No raw application
  settings, credentials, state, Terraform plan bodies or function metadata exported.

## Changed Function setting names only

AIFLUX_APIM_PRODUCT_ID, AIFLUX_APIM_RESOURCE_ID, AIFLUX_CATALOG_CONFIGURED,
AIFLUX_CATALOG_PATH, AIFLUX_DATABASE_URL, AIFLUX_ENVIRONMENT,
AIFLUX_LOG_WORKSPACE_ID, AZURE_CLIENT_ID, WEBSITES_ENABLE_APP_SERVICE_STORAGE.

The container provider additionally materialized DOCKER_REGISTRY_SERVER_URL,
DOCKER_REGISTRY_SERVER_USERNAME and DOCKER_REGISTRY_SERVER_PASSWORD. Verified
exact approved registry URL and empty credentials; not a new secret or grant.
All existing host-storage settings and every other Function setting preserved.
Catalog false is copied from canonical API settings, not promoted to acceptance.

## Current state / handoff to activation stage

- API/admin/customer ARM state **Running**. No HTTP, browser or ingestion-health
  acceptance asserted. API public network access remains Disabled; admin/customer
  existing ingress settings unchanged.
- Function ARM state **Disabled**, enabled=false; public network access remains
  Disabled; timer disabled=true; catalog configured=false; cutoff absent.
- ARM functions discovery returned **HTTP400**. No discovery, host execution or
  scheduled ingestion is proved. No sync/start/trigger attempt was made.
- Protected identity, ingress, TLS, SCM restrictions, PostgreSQL/vault containment,
  role assignments and all non-stage settings match baseline. Existing 11-model
  source/catalog inputs, GLM secret, authentication, CORS, safety and quotas were
  not changed by this four-resource saved plan. No network/RBAC/database writes.

**Return to the activation stage, not another disabled-stage deployment.** Next:
review the exact business/history cutoff and actual catalog readiness/acceptance,
then validate a separate finite host/timer activation plan. No cutoff was chosen;
that did not block this approved disabled stage. Replay, historical ingestion,
scheduled passes and persisted DB/API/UI reconciliation remain unperformed.

## Evidence

- [Current apply and readback report](../gateway/validation/finops-disabled-stage-applied-20261027t0457z.json)
- [Pre-apply current validation](../gateway/validation/finops-disabled-stage-validation-20261027t044611z.json)
- [Final 70-test JUnit](../gateway/validation/finops-disabled-stage-readback-tests-20261027t0457z.xml)
- [Current deployment proof](../.azure/deployment-plan.md)