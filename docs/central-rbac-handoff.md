# Central-team RBAC handoff

## Latest live recheck — 2026-10-23 09:15 UTC

This supersedes the 09:08 check below: **all 11 requested application role
assignments are now visible at their expected scopes**, including Gateway Azure
Event Hubs Data Sender. The runtime-readiness verifier reports zero missing
visible grants. Assignment visibility is not proof of successful runtime data
access; no database login or application cutover was performed.

The deployment user's vault metadata read still fails ForbiddenByRbac, so
operator secret-provisioning access is not yet demonstrated. PostgreSQL remains
Ready/public-disabled; local DNS still resolves to public `4.193.98.244`, and no
existing private runner candidate was found. Login-secret provisioning and an
approved private database bootstrap route remain outstanding. Existing apps
retain their older image digests; no runtime apply or network change was made.

## Latest live recheck — 2026-10-23 09:08 UTC

This supersedes earlier missing-grant counts below. Fresh Azure assignment reads
and the runtime-readiness verifier confirm **10 of the 11 requested application
assignments now exist**, including API Key Vault Secrets User. Gateway Event Hubs
Data Sender is still absent from the checked assignments; Gateway Data Receiver
was assigned instead and does not authorize sending. Central administrators must
review that mismatch; no role assignments were changed here.

The deployment user's vault metadata check still returns ForbiddenByRbac.
PostgreSQL is Ready with public networking Disabled, but this workstation still
resolves its hostname to public `4.193.98.244`; no VM/ACI/Container Apps job runner
candidate was returned. Neither private database access nor bootstrap is proven.

Safe release preparation was rerun: packaged 104-file hashes/Python syntax and
unique migration head `0003` passed, including empty disposable SQLite upgrade
and repeat; six focused mocked Terraform tests passed. These are not live
PostgreSQL migration tests. The verifier regenerated immutable image inputs but
retained `manual_rbac_verified=false` and disabled workers. Existing apps still
use their older images. No runtime deployment, secret provisioning, network
change or live database bootstrap was performed.

Next: central secret provisioning (or approved vault-scoped operator access),
an approved private bootstrap route, and correction of the gateway sender grant.
Gateway sending is distinct from portal local-login prerequisites; its missing
grant does not prevent offline preparation, but the complete runtime attestation
must not be asserted while it remains unverified.

## Supplemental deployment-user and database handoff — 2026-10-23

This section separates deployment permissions from runtime permissions and
PostgreSQL database privileges. All Azure role assignments remain central-owned;
this is a request/checklist, not executable authorization code.

A fresh read-only subscription-and-descendants role list returned successfully
on 2026-10-23, without truncation. It confirms the deployment user's direct
subscription Contributor and resource-group Storage Blob Data Contributor
assignments. It returned no direct Secrets Officer assignment for that user and
none of the 11 runtime assignments listed below. This particular check did not
refresh group membership or management-group inheritance; absence from this list
alone is not a complete effective-permission determination. The earlier vault
metadata request at 08:37:43 UTC separately failed ForbiddenByRbac.

### Deployment user: additional versus already available

- User: `xv.puneet.devadiga@singtel.com`.
- Object ID: `dd928302-055b-4516-9b8e-b06ae823057b`.
- Tenant: `beb276ac-6e9f-498e-8e31-019ee666decd`.

| Permission | Scope | Disposition |
| --- | --- | --- |
| Contributor | Existing subscription; project RG is the preferred boundary for a future scoped deployment identity | Already directly assigned at subscription. No additional Contributor, Website Contributor, Network Contributor or Managed Identity Operator is needed for resources/identities within that existing permission scope. |
| Storage Blob Data Contributor | Terraform state container in `projpoctokenex` | Already inherited from a direct project-RG assignment. Covers state read/write/locking; does not remove backend networking restrictions. |
| Key Vault Secrets Officer | Existing `pocidstokenexkv` vault only | Additional request if this user will provision/rotate the three local-login secrets. Prefer time-limited access. Unnecessary if central administrators provision the secrets and supply only versionless reference URIs. |
| ACR build/control-plane permissions | `pocidstokenexacr` | Existing Contributor covers this deployment's ACR task orchestration. Do not request another build role merely because runtime identities need AcrPull. Direct image push by a different identity is a separate workflow. |
| PostgreSQL Entra administrator or delegated migration privileges | `poc-ids-token-ex-pg`, database `turnstile` | Database authorization, NOT an Azure RBAC role. Verify the configured administrator and a real private login before bootstrap. Azure Contributor/PostgreSQL resource-management roles do not grant SQL access. |

Key Vault Secrets Officer role ID:
`b86a8fe4-44ce-4948-aee5-eccb2c155cd7`.
It includes secret read/write/delete operations, not authorization management.
If this is too broad, central secret provisioning avoids granting it to the user.
Do not additionally request Secrets User for the same user when Officer is given.

Do not request Owner, User Access Administrator, RBAC Administrator, Key Vault
Administrator, or tenant-wide directory roles for this deployment user. Role
assignment/definition writes stay with central administrators. Existing broad
Contributor is evidence of current access, not a recommendation to grant more
subscription-wide privileges.

### Exact Azure scopes

All scope suffixes below are appended to:
`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC`.

| Alias | Scope suffix |
| --- | --- |
| Vault | `/providers/Microsoft.KeyVault/vaults/pocidstokenexkv` |
| Registry | `/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr` |
| Function storage | `/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc` |
| Insights | `/providers/Microsoft.Insights/components/poc-ids-token-ex-insights` |
| Usage hub | `/providers/Microsoft.EventHub/namespaces/poc-ids-token-ex-eh/eventhubs/token-usage` |
| State container | `/providers/Microsoft.Storage/storageAccounts/projpoctokenex/blobServices/default/containers/tfstate` |
| PostgreSQL server | `/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg` |

### Previously requested runtime grants — not extra deployment-user grants

These 11 requests are consolidated here to avoid confusing app identities with
the operator. Do not duplicate grants that central administrators subsequently
confirm effective. Built-in role IDs are in the data-only Terraform handoff.

| Identity | Principal ID |
| --- | --- |
| API | `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` |
| Ingestion | `edbfc3e2-a8e5-4652-9bb0-311233756d42` |
| Control-plane | `967370eb-a5b0-4531-bc2b-b15a83ac3efd` |
| Gateway | `bcf69911-f34e-4f33-acd8-a36f164db811` |

| Identity | Role | Scope alias |
| --- | --- | --- |
| API | Key Vault Secrets User | Vault |
| API | Storage Table Data Contributor | Function storage |
| Ingestion | AcrPull | Registry |
| Ingestion | Azure Event Hubs Data Receiver | Usage hub |
| Control-plane | AcrPull | Registry |
| Control-plane | Monitoring Metrics Publisher | Insights |
| Control-plane | Storage Blob Data Owner | Function storage |
| Control-plane | Storage Queue Data Contributor | Function storage |
| Control-plane | Storage Table Data Contributor | Function storage |
| Gateway | Storage Table Data Contributor | Function storage |
| Gateway | Azure Event Hubs Data Sender | Usage hub |

Event Hubs grants do not implement a missing Event Hubs consumer. Do not enable
unimplemented workers or runtime APIM publication under the Terraform-only
configuration-write policy. Optional APIM fragment/custom-role requests remain
separate and are not prerequisites for basic local login.

### PostgreSQL bootstrap: separate database authorization

The authorized PostgreSQL Entra administrator must create/register these database
principals using the principal IDs above, not application/client IDs:

| Database login | Purpose |
| --- | --- |
| `poc-ids-token-ex-api-identity` | API runtime access to required application tables/sequences |
| `poc-ids-token-ex-ingestion-identity` | Ingestion runtime access to its required tables/sequences |
| `poc-ids-token-ex-control-plane-identity` | Only the access needed by approved, enabled control-plane functions |

The DBA must review the exact table-level privilege matrix. Runtime access needs
CONNECT on the database, USAGE on the application schema, appropriate table DML
and sequence privileges, and suitable default privileges for objects later
created by the migration owner. Runtime identities must not receive database
ownership, schema CREATE, CREATEROLE or CREATEDB. Migrations require a separate
authorized owner/migration identity with DDL privileges. Do not describe the
runtime matrix as implemented or verified before the private database checks.

Use PostgreSQL's Entra principal mapping, not a bare CREATE ROLE, password login,
or the MSSQL bootstrap script. Microsoft documents
`pgaadauth_create_principal_with_oid` for known object IDs; do not add broad
Directory Readers/Graph grants solely to discover IDs already supplied here.
Any additional directory-integration requirement must be justified against the
selected server configuration and bootstrap method.

### Private runner: conditional permissions, not an unconditional role bundle

An approved private route and DNS resolution are required in addition to roles.
No Azure role assignment alone supplies that connectivity. Prefer an existing
approved private runner or VPN-connected workstation; keep PostgreSQL public
access disabled.

If a new runner is approved, provision its infrastructure through Terraform and
export its actual identity before requesting grants. A managed-identity runner
needs AcrPull only when pulling a private ACR image, Secrets User only when
reading the bootstrap secrets itself, and a separate PostgreSQL migration role
if it executes migrations. A runner executing Terraform additionally needs its
own scoped deployment/state permissions; it does not inherit the human user's
roles. VM login/Bastion permissions apply only if that access method is selected.
Do not assign SQL administration to the API merely to use it as a bootstrap host.

The three application secrets are a JWT signing secret and initial admin/customer
passwords; PostgreSQL remains Entra-only. No PostgreSQL password or Event Hubs
shared-key connection string is requested. Secret provisioning must follow the
approved Terraform/central process without values in chat, source or logs.

References:
[Key Vault role definitions](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/security#key-vault-secrets-officer),
[PostgreSQL Entra principal management](https://learn.microsoft.com/azure/postgresql/security/security-manage-entra-users).

## Latest application continuation — live access checked

See the [2026-10-23 application deployment evidence](application-deployment-20261023.md)
for the current direct/inherited role check, 11 missing visible runtime grants,
the deployer's confirmed vault `ForbiddenByRbac`, and local private PostgreSQL DNS
blocker. The direct deployment authorization was accepted; no onboarding/resume UI
is required. Runtime remains gated on actual permissions, secrets, migrations and
private reachability, not UI state. The r5 resource apply below succeeded; older
failed-plan and approval notes later in this document are historical only.

## Latest provisioning result — 2026-10-23

The user explicitly approved applying the reviewed resource-only r5 plan.
Terraform completed successfully: **14 added, 1 changed, 0 destroyed**.
The authoritative transcript is the local deployment artifact
`resource-provisioning-central-r5-apply.log`. Earlier failed-plan evidence below
is historical and does not describe this successful apply.

Created resources include PostgreSQL 16 and database `turnstile`, its Entra
administrator, TurnstileLedger and ModelRoutes tables, Event Hubs namespace and
token-usage hub, private PostgreSQL/Event Hubs DNS zones, VNet links and private
endpoints, and the control-plane managed identity. The one update adds private
TCP 5432 while preserving 1433/443 and the existing deny rule. Existing MSSQL,
application resources and role assignments were not changed by this apply.

The applied `identity_principal_ids` output confirms:

| Newly created identity | Principal ID |
| --- | --- |
| poc-ids-token-ex-control-plane-identity | `967370eb-a5b0-4531-bc2b-b15a83ac3efd` |

For this identity, request AcrPull on `pocidstokenexacr`, Monitoring Metrics
Publisher on `poc-ids-token-ex-insights`, and Storage Blob Data Owner, Storage
Queue Data Contributor and Storage Table Data Contributor on `pocidstokenexfunc`.
Each scope is the named resource under subscription
`aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`, resource group `IDS-TOKEN-EXCHANGE-POC`.
The remaining identity IDs and role scopes below still require central review;
their presence does not attest that grants exist.

The new Event Hubs grant scope is
`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.EventHub/namespaces/poc-ids-token-ex-eh/eventhubs/token-usage`.
Request Data Sender for gateway and Data Receiver for ingestion as listed below.

No runtime RBAC was assigned, application activated, secret created, migration
run, or authentication cutover performed. Central grants and private PostgreSQL
principal/schema bootstrap remain pending. Do not run the MSSQL-specific
bootstrap SQL against PostgreSQL. The targeted apply warning is expected: this
result is resource-only, not a full application deployment or readiness claim.

## Ownership and sequence

Azure role definitions and assignments are owned and managed **externally by the
central team**, not by this repository. Resource provisioning requires the
appropriate resource-provider permissions, not authorization-write permissions.
This stack creates resources and managed identities first and emits grant
requests; it neither creates grants nor attests that requested grants exist.

1. Review resource-only Terraform changes, cost/quota, and obtain deployment
   approval. Keep `manual_rbac_verified = false` and runtime/inference disabled.
2. Provision the approved resource-only saved plan using Terraform only.
3. Export `identity_principal_ids` and `central_rbac_handoff` from Terraform after
   provisioning. Principal IDs must come from applied state, never mocked tests
   or values still marked unknown in a plan. A targeted apply can omit unrelated
   outputs: missing output data is not evidence of successful provisioning.
4. Central administrators review the requests and manage grants through their
   own approved external process. Do not add role resources or role-writing
   commands to this repository. Custom role actions are data in the handoff,
   not executable role definitions.
5. Record evidence of each effective grant (principal ID, role ID, exact resource
   scope, verification time, and central change reference). Only then may a
   separately reviewed runtime plan set `manual_rbac_verified = true`.

Creating an identity or producing a handoff does **not** verify its permissions.
Contributor does not confer Key Vault secret access, SQL database privileges,
directory privileges, or permission to assign Azure roles.

## Existing-state safety

**Never apply the full `prerequisites` graph to this existing deployment.** That
stage omits running Web Apps and Functions and would otherwise delete them.
Use [the plan-only guard](../scripts/plan-resource-provisioning.ps1) with the
reviewed local variable file and a fresh saved-plan filename. The guard pins:

- Subscription: `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`.
- Resource group: `IDS-TOKEN-EXCHANGE-POC`.
- Trusted provider configuration: the local deployment Terraform CLI config.
- PostgreSQL provisioning with legacy MSSQL retained, including the original
  MSSQL private endpoint and DNS key; no database cutover or app changes.
- Private PostgreSQL and Event Hubs endpoints/DNS; public SQL, vault and Function
  storage access remain disabled. Shared-key/local data-service auth is not
  enabled to bypass managed identity.
- Runtime workers, inference and the RBAC attestation remain disabled.

The guard refuses overlapping Terraform processes, overwriting saved plans,
deletions/replacements, changes outside its explicit resource allowlist, and
updates to existing identities or private endpoints/DNS. Dependencies still
appear in targeted plans and must be inspected: targeting is **not** a guarantee
that only new resources change. Review all NSG changes, including the narrowly
scoped PostgreSQL port addition within the existing private subnets. Do not
accept wider ingress, removal of deny rules, public exposure, or new service
bypasses. A blocked or partial plan must not be applied.

Terraform reports `complete = false` for normal targeted plans because they
exclude untargeted resources; that flag alone does not mean an error. The guard
requires an applyable, nonerrored plan with no deferred changes and enforces its
resource boundary. A passing targeted guard is not full-stack validation.

Plan approval is not deployment approval. This script never applies. Retained
MSSQL must remain retained in subsequent runtime plans until a separately
approved data cutover/removal; do not fall back to its default `false` by mistake.

## Central review checklist

The [data-only handoff](../infra/terraform/central-handoff.tf) identifies exact
principal IDs, intended resource scopes, built-in role IDs and requested custom
actions. Intended ARM IDs do not prove resources already exist. Confirm target
resources before granting; do not broaden scope to the resource group or
subscription just because a target is not yet provisioned.

| Identity | Requested access | Scope |
| --- | --- | --- |
| API, customer, admin, ingestion, control-plane as applicable | AcrPull | Reviewed container registry |
| Gateway, API as applicable | Key Vault Secrets User | Existing application vault |
| Deployed identities | Monitoring Metrics Publisher | Application Insights |
| API, ingestion | Log Analytics Reader | Workspace |
| Ingestion, control-plane | Blob Data Owner, Queue/Table Data Contributor | Function storage |
| Gateway, API | Table Data Contributor | Ledger storage |
| Gateway / ingestion | Event Hubs Data Sender / Receiver | Token-usage event hub |
| Gateway | Cognitive Services User | Content Safety and configured Foundry account |
| API | Reviewed subscription-manager custom actions | APIM service only |
| API, if settings enabled | Reviewed gateway-settings custom actions | Approved policy fragments only |
| Edge, if TLS enabled | Key Vault Secrets User | Reviewed certificate vault |

The subscription-manager request concerns **APIM product subscriptions**, not
Azure subscription management. The custom requests must not include role,
service, backend or general policy-management privileges. Optional and future
requests should be granted only when needed and approved.

PostgreSQL Entra principal creation/schema grants, Key Vault app-secret
provisioning and schema migrations are separate administrator/data-plane tasks.
Do not treat Azure RBAC approval as completion of those tasks or as permission
to open a private service to the public network.

## Verification evidence

Focused mocked Terraform tests verify resource-first planning without grant
attestation, retained MSSQL/private networking, and rejection of runtime
activation before central verification. Mocked tests do not create Azure
resources, return real principal IDs, or prove regional capacity. Record live
plan/apply outcomes separately; never label a plan as a successful deployment.

### Historical verification before the successful r5 apply (superseded above)

- Final `terraform validate` passed (expected trusted-provider override warning),
  and formatting checks passed for the reviewed Terraform files. The Windows
  focused filter `tests\rebuild.tftest.hcl` completed with **4 passed, 0 failed**,
  including the private-storage bypass and handoff-scope regression assertions.
  The final focused-test transcript is retained in the local deployment folder.
- Azure CLI and the initialized Terraform backend both target the subscription
   and resource group above. The backend uses Entra/CLI authentication to storage
   account `projpoctokenex`, container `tfstate`, key
   `poc-ids-token-ex/main.tfstate`.
- A fresh targeted plan failed **before resource refresh** while loading remote
   state: `403 AuthorizationFailure`, request ID
   `fb3c1585-401e-004b-1dae-62882b000000`, time
   `2026-10-23T05:23:34.6482785Z` on the final retry after the security fix.
   No valid refreshed plan was produced by that
   attempt. Backend storage has a default-deny firewall and four explicit IP
   rules; the evidence does not conclusively distinguish network denial from
   data-plane authorization. An independent egress-IP check was also denied.
- Offline review of the earlier `resource-provisioning-central-r1` saved plan
   found **14 creates, 2 updates, 0 deletes/replacements**, with no Web App or
   Function changes. It is **not approved for apply**: it changed Function
   storage bypass from `None` to `AzureServices`. Private provisioning now
   preserves `None`, with a regression assertion. A fresh live plan is still
   required to verify the corrected configuration.
- The other update in that earlier plan adds TCP `5432` alongside `1433` and
   `443`, only from `10.240.4.0/24` to `10.240.3.0/24`; it retains the outbound
   deny rule. The planner now checks this precise boundary.
- **No Terraform apply or Azure resource/role mutation was performed.** Separate
   scaffold/deployment approvals are not recorded in the active onboarding
   session; the general `deployment_approved` input is not a substitute.

These are **existing** managed-identity principal IDs returned by a read-only ARM
list on 2026-10-23, not newly provisioned identities or proof of granted roles:

| Identity | Principal ID |
| --- | --- |
| gateway | `bcf69911-f34e-4f33-acd8-a36f164db811` |
| api | `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` |
| customer | `fef60be5-f8ef-4330-8c22-a692b122856a` |
| admin | `e717101e-1ffa-4ff8-874e-e07faaa7da86` |
| ingestion | `edbfc3e2-a8e5-4652-9bb0-311233756d42` |

No `control-plane` identity was returned. Its principal ID is unavailable until
successful provisioning. No new applied `central_rbac_handoff` output is claimed.
Resume from an authorized backend network/identity, without changing its firewall
or creating grants here; regenerate the guarded plan, review quota/cost and all
diffs, complete the separate approval gates, then use Terraform-only provisioning
and export the applied handoff.