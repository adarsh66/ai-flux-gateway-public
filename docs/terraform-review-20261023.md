# Terraform review — 2026-10-23

## Scope and result

Read-only review and Terraform planning against the latest local source. No
Terraform apply, cloud resource changes, database migration, state migration,
RBAC grants, or application redeployment was performed. Terraform input files
were not changed. This is not full deployment-readiness certification.

**Result: do not apply either saved review plan.** The existing prerequisite
inputs are stale for the latest code, and switching the database engine is not
currently a safe side-by-side migration.

## Confirmed target and backend

The Azure resource-group inventory, configured inputs, initialized backend
metadata, and refreshed plan agree on:

| Setting | Value |
| --- | --- |
| Subscription | aa28274d-fea0-46d4-b9c8-30f3ef0a0e52 |
| Tenant | beb276ac-6e9f-498e-8e31-019ee666decd |
| Resource group | IDS-TOKEN-EXCHANGE-POC |
| Main root | infra/terraform |
| Backend | azurerm, remote Azure Blob state |
| State storage account | projpoctokenex |
| Container | tfstate |
| Main state key | poc-ids-token-ex/main.tfstate |
| Models state key | poc-ids-token-ex/models.tfstate |
| Backend authentication | Azure CLI with Entra ID; use_azuread_auth=true |

Main backend source: infra/terraform/backend.hcl. Models backend source:
infra/models/backend.hcl. The models stack was not replanned in this review.
The live inventory contains Microsoft.Sql resources and no PostgreSQL Flexible
Server or Event Hubs namespace.

Terraform 1.12.1 matches the pinned version. Validation succeeded. Provider
development overrides in .deployment/terraform.rc were used for the existing
trusted provider executable paths; Terraform emitted the expected warning.
No provider upgrades were requested.

## Current-input plan

Inputs: .deployment/prerequisites.tfvars.json, without overrides.
Saved plan: .deployment/review-current-20261023.tfplan.

The saved plan reports complete=true and errored=false, with:

- **0 additions, 4 updates, 4 deletions.**
- Updates: three APIM policy bodies and the dev OpenAI API import.
- Deletions: API, customer, and admin web apps plus the ingestion Function.

Reason: the inputs select deployment_stage=prerequisites. The latest apps.tf
only retains these application resources when local.platform_stage is true.
The older disabled_app_scaffold_enabled input remains in the input file but is
no longer declared by this Terraform root. It cannot protect existing apps.

The effective database_engine is mssql, turnstile_platform_enabled is false,
and control_plane_worker_enabled is false. Therefore this plan does not add
PostgreSQL, the Turnstile ledger/routes tables, Event Hubs, or its worker.

## PostgreSQL and Turnstile diagnostic preview

The same input file was previewed with command-line overrides only:
database_engine=postgresql and turnstile_platform_enabled=true. No persistent
inputs were edited and no deployment approvals were fabricated.

Artifacts:

- .deployment/review-postgres-turnstile-20261023.tfplan
- .deployment/review-postgres-turnstile-20261023.log

**The preview failed:** azurerm_mssql_database.main[0] cannot be destroyed
because lifecycle.prevent_destroy is set. The saved diagnostic plan reports
applyable=false, complete=false, errored=true. Its partial summary is 12 to add,
6 to change, 5 to destroy; this is not a complete, approved migration plan.

The partial graph includes PostgreSQL 16 server/database/Entra administrator,
TurnstileLedger and ModelRoutes tables, Event Hubs namespace/hub/APIM logger,
and the control-plane identity. It also attempts to remove the existing MSSQL
server/database, replace SQL private DNS and its VNet link/private endpoint,
and change the NSG database port from 1433 to 5432. Existing app-deletion risks
from the prerequisite-stage baseline remain unresolved.

Do not remove prevent_destroy to bypass this failure. Preserve SQL and its
network resources while designing an explicit side-by-side migration.

## Additional verified rollout gaps

1. **Production local authentication:** apps.tf sets AIFLUX_ENVIRONMENT to
   production but does not configure AIFLUX_LOCAL_AUTH_ENABLED or a secure
   AIFLUX_LOCAL_JWT_SECRET. config.py only automatically enables local auth for
   PostgreSQL outside production. Creating PostgreSQL alone will not activate
   the new email/password login in this deployment.
2. **Passwordless PostgreSQL API connection:** db.py only installs the PostgreSQL
   token callback when engine_for receives an explicit credential. The normal
   get_db path calls engine_for(settings.database_url) without one. The MSSQL
   branch has a DefaultAzureCredential fallback; the PostgreSQL branch does not.
   Resolve and test this before switching to an Entra-only PostgreSQL server.
3. **Manual RBAC:** rbac.tf deliberately leaves assignments commented out.
   Turnstile storage and Event Hubs sender/receiver grants must be provisioned
   and verified by an authorized administrator. Do not set manual_rbac_verified
   to true without evidence.
4. **Full platform inputs:** a safe platform plan needs real Entra settings,
   immutable images for api/customer/admin, reviewed current network restrictions,
   and any worker configuration. Do not simply change the stage and fabricate
   missing values. Preserve the existing admin-only ingress policy and private
   API/data access when reconciling the runtime configuration.
5. **Data/schema migration:** moving portal authentication requires deliberate
   schema and account migration/bootstrap. Terraform creates infrastructure;
   these previews do not migrate existing SQL portal users or prove app readiness.

## Recommended next step

Prepare reviewed platform inputs matching the existing deployed images,
identities and security posture. Reconcile the removed scaffold support without
deleting running applications. Add PostgreSQL alongside existing SQL rather
than changing a mutually exclusive engine switch, resolve runtime authentication
and token handling, verify new RBAC, and rerun a complete non-destructive plan.
Only then seek approval for infrastructure changes and application/data cutover.

Saved Terraform plans and logs may contain sensitive material. Keep them local
and out of source control. Replan before any future approved deployment.