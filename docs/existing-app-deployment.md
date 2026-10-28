# Existing App Service deployment (no infrastructure rollout)

[scripts/deploy.ps1](../scripts/deploy.ps1) routes only `validate-apps`,
`build-apps`, and `deploy-apps` to
[scripts/deploy-existing-apps.ps1](../scripts/deploy-existing-apps.ps1), before
the original Python/Terraform launcher. Existing actions retain their behavior.
Neither app-only entry point provisions resources or invokes that launcher.

For the later admin-only same-origin proxy/explicit-CIDR ingress preparation,
see [admin allowlisted ingress](admin-allowlisted-ingress.md). SQL admin builds now
force VITE_CONTROL_API_URL=/api regardless of the legacy ControlApiBase argument;
customer build inputs remain unchanged. The proxy needs existing-subnet outbound
VNet integration and private DNS from admin before activation. The generic
three-app workflow does not enable this ingress or deploy the new candidate.

## Boundaries and defaults

- Subscription: `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`
  (`singtel-ids-sandbox-sea-01`); tenant:
  `beb276ac-6e9f-498e-8e31-019ee666decd`.
- Resource group: `IDS-TOKEN-EXCHANGE-POC`; registry: `pocidstokenexacr`.
- Web Apps: `poc-ids-token-ex-api`, `poc-ids-token-ex-customer`,
  `poc-ids-token-ex-admin`.
- SQL server/database: `poc-ids-token-ex-sql` / `aiflux`.
- Control API base: `https://poc-ids-token-ex-api.azurewebsites.net/api`.
- `ExpectedAccount` must explicitly identify the signed-in Azure CLI user name
  (or service-principal application ID). Active subscription, tenant, enabled
  state and account must match; the script never logs in or switches accounts.
- `GatewayUrl` is required explicitly, including the actual API path when needed
  (for example, `https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1`). Do not
  assume the APIM hostname alone is the correct inference route.
- Resource and application names, subscription/tenant, and URLs are overridable.
  Image repository names remain `aiflux-api`, `aiflux-customer`, `aiflux-admin`.
- Windows PowerShell 5.1 and ConstrainedLanguage supported: cmdlets/operators,
  no .NET constructors/static calls, local Docker, local npm or local Python.
  An installed, authenticated Azure CLI with modern container arguments is required.

## Actions and operator sequence

Use the wrapper with named parameters (`Action`, `ExpectedAccount`, `GatewayUrl`,
and optionally the resource-name overrides). No examples here are instructions
to run a live deployment without approval.

1. **`validate-apps`**: read-only Azure control-plane and registry queries. Checks
   current account, RG, registry, all three Linux single-container Web Apps,
   attached user identities, inherited unconditional `AcrPull`, SQL server and
   database existence, API configuration, and obvious network blockers. Does not
   build, write configuration, resolve Key Vault secrets, or connect to SQL.
2. **`build-apps`**: repeats validation, then checks that the chosen tag is absent
   from all three repositories **before** building. Supply a unique `Tag`, or
   retain the emitted millisecond timestamp default for deployment. Channel tags
   such as `latest` are rejected. Three synchronous `az acr build --no-logs` runs
   use repository-root context with the existing API/customer/admin Dockerfiles.
   Both portal builds receive `VITE_PORTAL_MODE=sql`, `VITE_GATEWAY_URL`, and
   `VITE_CONTROL_API_URL` as build arguments. No `--no-wait`, streamed build logs,
   local Docker/npm, registry login, or registry admin credentials are used.
   Each successful build is locked with `writeEnabled=false` and
   `deleteEnabled=false`; the digest and locks are checked. A failure can leave a
   partial release: choose a new release tag rather than overwriting old tags.
   Serialize builds for a release: the precheck is not an atomic reservation.
3. **SQL operator handoff**: independently complete the SQL steps below. The
   deployment script neither initializes SQL nor pretends ARM settings prove SQL
   reachability, schema state, grants, or user-account readiness.
4. **`deploy-apps`**: requires an **explicit existing `Tag`** and the
   **`SqlInitialized` switch**. The switch attests that the SQL operator completed
   the handoff; it is not a live SQL check. Validation repeats; all three tagged
   images must exist and be locked before any App Service write. Images are
   deployed by immutable digest, not by mutable tag.
5. Retain all emitted previous `linuxFxVersion` values **before the first write**.
   Deployment sets `acrUseManagedIdentityCreds=true` and
   `acrUserManagedIdentityID` to the **client ID** of an already attached identity,
   then uses `az webapp config container set --container-image-name` and
   `--container-registry-url`. It sets only `WEBSITES_PORT` (API `8000`, portals
   `8080`), `AZURE_CLIENT_ID`, and portal `GATEWAY_ORIGIN`/`CONTROL_ORIGIN` derived
   from the supplied HTTPS URLs. Existing secrets, SQL settings, API CORS and
   all other application settings are preserved. No passwords are generated.
6. Verify configured image/MI values, then separately run application smoke tests
   through the approved private/allowlisted route: API health/readiness, SQL
   login, invalid passwords, disabled accounts, customer/admin authorization,
   CORS and CSP. Configuration success is **not** application-readiness proof.

Build and deploy must use the **same** gateway/control URLs. These Vite values are
compiled into the portals; changing runtime variables cannot repair a wrong build.
Tags/digests do not attest the compiled URL values; retain reviewed build inputs
with release evidence. Preconfigure API `AIFLUX_CORS_ORIGINS` for the actual portal
browser origins separately; this script deliberately does not overwrite it.

Every native CLI failure terminates the action; no missing-resource, denied-query,
image-lock, build-status or post-update failure is ignored. CLI JSON and stderr
are captured, not printed; generic failures omit raw diagnostics because Azure
can include settings in them. Do not enable CLI debug, PowerShell tracing or
secret-bearing transcripts. Diagnose denied operations with an administrator
using targeted non-secret queries. App settings are inspected only in memory;
neither full settings nor signing/SQL values are output or persisted. The temporary
MI configuration JSON contains only a public client ID and boolean and is removed
in `finally`; it avoids Windows command-line JSON quote stripping.

## Existing identities and precise permission requests

Let `S` mean
`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC`.
Use these **exact resource scopes**, substituting `S` in the table. No grant is
made by these scripts; request existing permission verification or separate
administrator approval. No subscription-wide Contributor or Owner is needed.

| Principal / purpose | Scope | Requested access |
| --- | --- | --- |
| Deployment operator: RG lookup | `S` | `Microsoft.Resources/subscriptions/resourceGroups/read` (Reader on this RG is a convenient read-only umbrella) |
| Deployment operator: each existing Web App | `S/providers/Microsoft.Web/sites/poc-ids-token-ex-api`, `S/providers/Microsoft.Web/sites/poc-ids-token-ex-customer`, `S/providers/Microsoft.Web/sites/poc-ids-token-ex-admin` | `Microsoft.Web/sites/read`, `Microsoft.Web/sites/config/read`, `Microsoft.Web/sites/config/list/action`; deploy additionally `Microsoft.Web/sites/config/write` (Website Contributor at each site is a broader built-in alternative) |
| Deployment operator: ACR inspection/build/lock | `S/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr` | Reader, `Container Registry Tasks Contributor` for remote build submission/run inspection, `AcrPull` for repository/tag/manifest inspection and `AcrPush` for image metadata locking; use registry RBAC mode, not ABAC. Review equivalent custom-role actions if these built-ins are too broad. Build service must also be permitted to push outputs. |
| Deployment operator: role inspection | Same ACR resource scope | `Microsoft.Authorization/roleAssignments/read` (Reader covers this); inherited grants must be visible to the role-list query |
| Deployment operator: attached identity lookup | `S/providers/Microsoft.ManagedIdentity/userAssignedIdentities/poc-ids-token-ex-api-identity`, `S/providers/Microsoft.ManagedIdentity/userAssignedIdentities/poc-ids-token-ex-customer-identity`, `S/providers/Microsoft.ManagedIdentity/userAssignedIdentities/poc-ids-token-ex-admin-identity` | `Microsoft.ManagedIdentity/userAssignedIdentities/read` (Reader at each full identity resource ID) |
| Deployment operator: SQL existence checks | `S/providers/Microsoft.Sql/servers/poc-ids-token-ex-sql` and its child `databases/aiflux` | `Microsoft.Sql/servers/read`, `Microsoft.Sql/servers/databases/read` (Reader on this server) |
| `poc-ids-token-ex-api-identity`, `poc-ids-token-ex-customer-identity`, `poc-ids-token-ex-admin-identity` | `S/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr` | Existing unconditional **AcrPull**, role ID `7f951dda-4ed3-4680-a7ca-43fe172d538d`, granted to each identity's **principal/object ID** |

The identity names above follow the existing Terraform naming convention. The
script discovers **attached** identity resource IDs and looks them up rather than
creating identities or deriving client IDs from names. If several are attached,
the existing `AZURE_CLIENT_ID` must unambiguously select one; a sole identity can
be selected if the setting is absent. Different overridden resource/identity names
require requests at their actual resource IDs. Conditional grants and ABAC
repository permissions fail closed instead of being treated as working AcrPull.
No Managed Identity Operator/assign action is needed: attachments are not changed.
No ACR admin enablement, `listCredentials`, password, role-assignment write,
identity attachment, SQL firewall or App Service access-rule write is performed.

## SQL initialization and configuration prerequisite

The API must already have `AIFLUX_ENVIRONMENT=production`, a passwordless
`AIFLUX_DATABASE_URL` for the named existing database using explicit
`mssql+pyodbc` parameters, ODBC Driver 18, encryption enabled and server certificate
validation enabled, and `AIFLUX_HOME_TENANT_ID` matching the expected tenant. Opaque
ODBC strings and credential/authentication query parameters are rejected. API
VNet integration must already exist. These checks prove configuration only.

`AIFLUX_PORTAL_LOGIN_ENABLED` must already be enabled and
`AIFLUX_PORTAL_LOGIN_SECRET` independently generated through the approved secret
process. The conservative script check requires at least 32 printable ASCII
bytes and 12 case-sensitive distinct characters and rejects known placeholder
markers. This does not measure entropy; the security owner must verify provenance.
Unresolved Key Vault references are rejected rather than falsely claiming their
strength was checked. This path does not fetch secrets from Key Vault, write them
to the command line, create users, seed passwords, or change signing settings.

Before supplying `SqlInitialized`, the SQL operator must:

- Use an already approved private-network execution location with SQL private
  DNS/routing and Entra authentication; verify actual database/token connectivity.
- Apply the reviewed Alembic migrations to head (including the portal-auth
  migration), verify schema and secure account initialization with the application
  owner, and confirm disabled/orphan accounts cannot authenticate. Do not assume
  startup creates or repairs production accounts.
- Run the reviewed identity bootstrap in
  [infra/sql/bootstrap-identities.sql](../infra/sql/bootstrap-identities.sql).
  Map contained user `aiflux-api` to the client-ID SID of existing
  `poc-ids-token-ex-api-identity`. Existing `poc-ids-token-ex-ingestion-identity`
  maps to `aiflux-ingestion`; ingestion is **not deployed by this path**.
- Verify runtime API **SELECT/INSERT/UPDATE/DELETE on schema dbo**, with no DDL
  grants. Ingestion has only the table-specific SELECT and ingestion DML grants
  in the bootstrap script; portal identities need no SQL rights. Do not grant
  `db_owner`, `db_ddladmin`, or schema-alter permissions to runtime identities.
- Use a **separate reviewed SQL operator identity** with the required database
  CONTROL/DDL and user/grant-management authority for migrations and bootstrap.
  Azure SQL ARM Contributor/Reader is not database DDL authority; an Entra SQL
  administrator or delegated database owner must authorize the SQL operator.
  SQL contained-user SID uses the MI **client ID**; Azure RBAC uses its
  **principal/object ID**. Record evidence without credentials and hand it off.

## Private access and deny-all blockers

Private SQL stays private. An administrator must provide existing VNet integration,
private endpoint approval, private DNS, NSG/routes, and an approved operator host;
this workflow never opens public SQL, adds firewall exceptions, or changes networking.
Likewise, approved browser/operator routes and API CORS must precede release.

App Service public access disabled, explicit catch-all deny rules, and default-deny
with no allow rules are **explicit blockers**. This conservative script does not
infer effective access from private endpoints, priority/header/service-tag rules,
or test HTTP reachability. Even a valid private-only Web App requires a separately
reviewed adaptation; do not enable public access to satisfy this check. Default-deny
with selective allows is not proof the operator/browser is allowed: have the
network owner verify the real route. Restricted ACR (public disabled or network
default deny) is also blocked: private registries need an existing approved build
agent/pull route, which this standard remote-build path does not create. RBAC alone
does not establish connectivity. No network restriction is silently relaxed.

## Failure, rollback and non-live testing

There is no multi-app transaction or automatic rollback. A failure after a write
may leave a partial update. Retain previous image references and a separately
reviewed non-secret configuration baseline; revalidate locks and prerequisites
before an operator reselects a prior release. An empty previous image denotes an
unconfigured scaffold, not a usable rollback image. Image rollback alone does not
restore prior ports/CSP/MI settings or database schema. Do not roll back SQL with
the runtime identity. Never dump all app settings for backup.

Offline checks do not contact Azure: load script command metadata to check parsing,
invoke invalid/missing-argument cases (they must fail before CLI use), and run both
entry points with a session-local `az` function replacing the native CLI. A mock
must provide account/resource/configuration/role/image JSON, record all writes and
set `LASTEXITCODE` on every call. Cover read-only validation; all three remote builds
with SQL Vite arguments and locks; digest-only deployment/MI/ports/CSP; failure on
wrong account/subscription/tenant, missing resources/AcrPull/signing/production SQL,
deny-all, tag collisions, unlocked images, failed build status, native nonzero exit,
and missing SQL attestation. Ensure no secret sentinel appears in captured output
and no Python/Terraform invocation occurs. Do not use a mock pass as live SQL,
permission, networking, or application-readiness evidence.

### Offline verification performed (2026-10-22)

- Both entry points parsed with no editor diagnostics in Windows PowerShell 5.1
  ConstrainedLanguage; missing release tag and SQL attestation were rejected.
- Session-local CLI mocks passed read-only wrapper validation, three synchronous
  no-logs builds with portal build arguments and locks, digest deployment with
  managed-identity configuration, rollback capture, ports and CSP origins.
- Eighteen negative mock scenarios passed: wrong account/subscription/tenant,
  missing app, private-disabled Web App, app deny-all, restricted ACR, weak signing
  key, disabled portal login, non-production environment, invalid/password-bearing
  SQL URL, missing AcrPull, duplicate release tag, unlocked image, failed remote
  build status, native CLI failure and credential-shaped previous image reference.
- Timestamp defaults for all three builds and five unsafe/missing URL cases passed.
  The tests used synthetic settings with a sentinel to check output redaction.
- No live Azure validation, remote build, application update or SQL probe was run.