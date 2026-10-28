# Application deployment continuation — 2026-10-23

## Earlier application rollout outcome (before the build-only continuation)

Direct user authorization was accepted. No onboarding/resume UI or deployment
agent was used. Live authorization and network checks found real blockers;
there was **no application rollout, PostgreSQL bootstrap, secret provisioning,
new cloud image build, or live login/E2E success** in this continuation.
No Azure resource/configuration/RBAC writes, network openings or privilege
elevation were performed. Existing user changes were preserved.

The previously approved r5 resource apply is independently confirmed by its
local transcript: **14 added, 1 changed, 0 destroyed**. That is not an application
deployment result.

## Live access evidence

- CLI account: `xv.puneet.devadiga@singtel.com`, object ID
  `dd928302-055b-4516-9b8e-b06ae823057b`.
- Tenant: `beb276ac-6e9f-498e-8e31-019ee666decd`.
- Subscription: `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`.
- Resource group: `IDS-TOKEN-EXCHANGE-POC`.
- Read-only role enumeration, including inherited assignments, returned 58
  visible assignments. The relevant identities still have only the older grants;
  the new control-plane principal has no visible assignments. Absence here is
  reported as a missing visible grant, not as a successful service access test.
- Operator grants visible directly: subscription Contributor and resource-group
  Storage Blob Data Contributor. Effective ACR permissions include control-plane
  actions through Contributor, exclude authorization writes/elevation, and expose
  no Key Vault secret data permissions. **ACR build permission is not claimed to
  be denied.**
- ACR `pocidstokenexacr` remains in LegacyRegistryPermissions mode, public network
  Enabled, registry admin Disabled. Neither configuration nor credentials changed.
- A non-secret vault metadata-only request failed with **403 ForbiddenByRbac**,
  `Microsoft.KeyVault/vaults/secrets/readMetadata/action`, assignment not found,
  deny assignment null. No secret values were requested or printed.
- PostgreSQL `poc-ids-token-ex-pg` is **Ready**; public access Disabled, Entra auth
  Enabled, password auth Disabled. Its administrator is the operator object ID
  above. This proves administrator configuration, not database authentication.
- Local DNS returned CNAME
  `poc-ids-token-ex-pg.privatelink.postgres.database.azure.com` with public address
  `4.193.98.244`, not the approved private subnet. No PostgreSQL connection was
  attempted over that public resolution, and no firewall/DNS/network settings
  were changed. A verified existing private execution route is still required.

## Exact central-team grant gaps

Let `S` be the exact resource ID prefix:

`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC`

Append the resource suffixes below to `S`; these are resource scopes, **not** a
request for resource-group/subscription-wide grants. These 11 requested grants
were not found in the visible direct/inherited assignments:

| Principal/object ID | Missing requested role | Scope suffix |
| --- | --- | --- |
| `967370eb-a5b0-4531-bc2b-b15a83ac3efd` (control-plane) | AcrPull | `/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr` |
| Same control-plane principal | Monitoring Metrics Publisher | `/providers/Microsoft.Insights/components/poc-ids-token-ex-insights` |
| Same control-plane principal | Storage Blob Data Owner | `/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc` |
| Same control-plane principal | Storage Queue Data Contributor | `/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc` |
| Same control-plane principal | Storage Table Data Contributor | `/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc` |
| `edbfc3e2-a8e5-4652-9bb0-311233756d42` (ingestion) | AcrPull | `/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr` |
| `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` (API) | Key Vault Secrets User | `/providers/Microsoft.KeyVault/vaults/pocidstokenexkv` |
| Same API principal | Storage Table Data Contributor | `/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc` |
| `bcf69911-f34e-4f33-acd8-a36f164db811` (gateway) | Storage Table Data Contributor | `/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc` |
| Same gateway principal | Azure Event Hubs Data Sender | `/providers/Microsoft.EventHub/namespaces/poc-ids-token-ex-eh/eventhubs/token-usage` |
| `edbfc3e2-a8e5-4652-9bb0-311233756d42` (ingestion) | Azure Event Hubs Data Receiver | `/providers/Microsoft.EventHub/namespaces/poc-ids-token-ex-eh/eventhubs/token-usage` |

Role-definition UUIDs are in the [data-only handoff](../infra/terraform/central-handoff.tf).
The API's existing APIM subscription-manager assignment was visible; no claim of
missing subscription-manager access is made. Existing API/customer/admin AcrPull
and older monitoring/storage/AI grants were also visible.

Secret provisioning is a separate operator authorization issue. For operator
`dd928302-055b-4516-9b8e-b06ae823057b`, central administrators must either execute
approved secret provisioning themselves or approve the required secret-write
permissions, for example Key Vault Secrets Officer **at this vault only**. The
API needs Secrets User for runtime reads. Contributor is not sufficient for
either operation. No grant is made by this repository.

Keep `manual_rbac_verified=false`; do not replace evidence with an attestation.

## Repository work and validation

- The ignored local platform input now explicitly sets
  `retain_legacy_mssql=true`. It remains an **incomplete runtime draft**:
  `local_auth=null`, `apps={}`, and RBAC verification false. Do not apply it.
- [Application settings](../infra/terraform/apps.tf) now derive the local-login
  token audience and Azure tenant without an Entra **portal** registration.
  Per-service Azure managed identity selection remains intact; no Azure identity
  authentication was replaced with passwords.
- [Input validation](../infra/terraform/variables.tf) requires portal registration
  only for Entra portal login, and rejects combining local login with the Entra
  sidecar. Private API/admin/SCM policies were not weakened.
- Added isolated [local-login tests](../infra/terraform/tests/local-login.tftest.hcl),
  leaving the user-edited [rebuild test](../infra/terraform/tests/rebuild.tftest.hcl)
  unchanged. Focused execution of these two files: **6 passed, 0 failed**. These
  are mocked configuration tests, not live deployment acceptance.
- Terraform validation passed with the existing trusted-provider override warning.
  Terraform 1.12.1, AzureRM 5.9.0 and AzAPI 2.13.0 were retained.
- Installed 175 lockfile-selected npm packages using the existing corporate CA
  with lifecycle scripts disabled after the native esbuild installer failed.
  The dependency lockfile was not intentionally changed.
- Standard npm typecheck/build commands failed with **blocked by group policy**.
  Invoking the installed TypeScript compiler through Node confirmed successful
  admin and customer typechecks. A successful Vite bundle/container build is not
  attested; the native esbuild executable also failed to launch during install.
  Application-control policy was not changed or bypassed.

The existing migration graph also needs reconciliation before any bootstrap:
[stable teams](../services/control-plane/migrations/versions/0003_stable_teams.py)
and [portal users](../services/control-plane/migrations/versions/0003_portal_users.py)
both declare revision `0003` with parent `0002`. Do not blindly rename or stamp
the retained MSSQL history. No migration files or database history were changed
in this continuation.

## Concrete image-build and rollout handoff

No old CLI rollout/build script was executed: those paths contain configuration
writes that do not satisfy the current Terraform-only policy. No new ACR Task,
runner, public endpoint or subnet was created just to work around restrictions.

The next build-only implementation should use the existing registry, a fresh
non-channel tag, and Terraform-controlled ACR build actions. Its build context
must contain the current reviewed local source (including required uncommitted
changes), never an unrelated Git HEAD or repository-wide upload with deployment
inputs, state, credentials, dependencies or generated bundles. Use a narrow
source allowlist, not just an informal ignore assumption. Upload URLs/tokens must
be handled as secrets without terminal/log exposure. Legitimate ACR actions must
be verified; they must not be mistaken for authorization-role writes.

| Image | Dockerfile | Required public inputs |
| --- | --- | --- |
| `aiflux-api` | [API Dockerfile](../services/control-plane/Dockerfile) | Current reviewed backend and migration graph, once reconciled |
| `aiflux-admin` | [Admin Dockerfile](../apps/admin-portal/Dockerfile) | `VITE_AUTH_MODE=local`, `VITE_CONTROL_API_URL=/api`, reviewed gateway URL |
| `aiflux-customer` | [Customer Dockerfile](../apps/customer-portal/Dockerfile) | Same local-login and same-origin API inputs |

The attempted local build gateway input was
`https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1`; this is a compile-time
candidate, not live inference acceptance. Pin completed images by verified digest
before filling runtime `apps`. Do not invent digests or reuse stale images as if
they contain these changes.

After central grants and a verified existing private execution route are
available: reconcile migration history, provision/reuse secrets without printing
them, bootstrap PostgreSQL with the authorized database administrator, verify each
real MI's DML/no-DDL rights, generate a fresh Terraform runtime plan, and inspect
every change. Preserve legacy MSSQL, approved admin `167.103.66.114/32`, closed
SCM, and private API/PostgreSQL/vault/storage. Only apply a reviewed non-destructive
plan. Then perform live login, invalid-password and customer/admin authorization
E2E through the approved route. None of those future steps is marked complete.