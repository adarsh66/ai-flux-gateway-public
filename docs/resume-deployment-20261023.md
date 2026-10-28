# Deployment pause and resume — 2026-10-23

## Checkpoint

### Latest JWT continuation — Key Vault selected; firewall blocker

- User approved resuming with **Key Vault-backed JWT**, superseding the temporary
   direct-App-Service-setting approach after receiving Secrets Officer access.
   No bootstrap password secrets are needed; both accounts are already seeded.
- Terraform backend access was restored: the existing read-only state-list task
   completed with exit code 0 (visible execution evidence). No apply was performed.
- Current local runtime changes remove production bootstrap-password validation
   and prevent production seeding. Terraform accepts a JWT-only Key Vault object;
   the optional direct-secret route remains unused. No signing secret was supplied
   to Terraform or generated into local files.
- Validation performed during this continuation: Terraform validate succeeded;
   Windows-native filtered Terraform tests **11 passed**; production JWT/login,
   one-time seeder, bootstrap and credential Python tests **94 passed** (one
   existing Starlette/AnyIO deprecation warning). Relevant editor diagnostics clean.
   A first forward-slash Terraform filter selected zero tests; only the subsequent
   Windows-native run is counted as test evidence.
- Live expected operator object/tenant/subscription verified. Metadata-only Key
   Vault listing for `pocidstokenexkv` failed **403 ForbiddenByFirewall**, reporting
   client address **167.103.66.93**. Existing JWT secret presence is unknown; no
   secret value was read/generated, no secret was created, and no URI is confirmed.
   New Secrets Officer assignment does not bypass the vault network ACL.
- User was unavailable to choose a network exception. Preserve the firewall:
   **no network widening, role changes, app deployment or Terraform apply**. Next
   live step requires an already-authorized network path, or explicit approval for
   a reviewed temporary single-IP Terraform exception with cleanup. Never open the
   vault broadly or print JWT values. Do not overwrite an existing signing secret.
- Runtime image rebuild and actual deployment/Key Vault-reference resolution,
   live managed-identity database login and portal E2E remain unverified. Old
   published image pins do not contain these runtime changes. PostgreSQL temporary
   public-access closure remains pending independently.

### Earlier decision — one-time user seeding; JWT then deferred

- User approved seeding the initial admin/customer accounts without using Key Vault
   for their passwords. JWT discussion/configuration is explicitly deferred.
- Prepared the separate [interactive seeder/runbook](postgres-user-seeding.md).
   All **63 focused tests pass**; account passwords are entered privately by the
   user in the external Cloud Shell and only application-compatible hashes are
   inserted. Existing accounts are never overwritten. No runtime/JWT/ARM changes.
- **Live user seeding succeeded (user-supplied Cloud Shell output):** final JSON
   reports `database_step=seed_users`, `committed=true`, admin@tokenx-ids.com with
   role `ids_admin` and developer@caldova.com with role `customer`. Reviewed-file
   verification reports 104 files; the script passed Entra administrator/session,
   schema and single-IP network guards before accepting hidden password inputs.
   `jwt_changes=false`, `runtime_deployed=false`. Do not rerun seeding or reset users.
- An earlier attempt failed the Entra-only authentication guard before seeding.
   User corrected authentication in the portal; the successful rerun passed that
   guard. This was a user-performed portal change, not an agent Terraform apply.
   Reconcile/verify its desired state in the next reviewed Terraform plan.
- The secret-provisioning requirement below describes the previous runtime plan,
   not a prerequisite for this separate seeder. Production runtime validation still
   expects bootstrap secrets and must be deliberately refactored before rollout;
   a working JWT signing configuration will also be needed later.
- Temporary PostgreSQL public-access cleanup and Terraform backend-storage access
   remain unresolved. Do not widen networks or self-assign roles to bypass them.

### Resume checks performed — 2026-10-23, approximately 13:50 UTC

- Resumed read-only Azure checks as the expected Puneet account, subscription and
   tenant. No repeat schema/principal bootstrap and no Azure configuration writes.
- Fresh ARM reads confirm Entra Enabled/password Disabled, public PostgreSQL
   Enabled, and only `temporary-cloud-shell-bootstrap` for `135.171.36.90`.
   Cleanup has **not** happened.
- Key Vault secret metadata listing fails `ForbiddenByRbac` for the operator.
   Current direct role read shows Contributor, Storage Blob Data Contributor and
   Key Vault Certificates Officer; the certificate role does not grant secret
   metadata/read/write. Secret existence is unknown, not confirmed absent.
- Local `local_auth` is still null; immutable runtime-image overlay exists and
   supplies image pins and the evidence-derived RBAC flag. An empty base `apps`
   object is not by itself a blocker when that overlay is supplied.
- A fresh narrowly targeted PostgreSQL containment **plan** failed loading remote
   Terraform state with storage `403 AuthorizationFailure`; no plan was applied.
   Storage account `projpoctokenex` is public Enabled/default Deny, with five
   existing IP rules including `167.103.66.114`. Operator Blob Data Contributor
   still exists at resource-group scope, so do not assume missing RBAC: network/
   current egress or credential context needs checking. No storage opening attempted.
- Packaged production seeding skips `create_all`; secure account seeding can use
   application DML once approved secrets resolve. Do not grant DDL to the API.

Previous runtime-plan external input: either central team provisions the three approved login
secrets and supplies versionless URIs only, or grants operator secret-management
authority scoped to this vault. Do not paste secret values in chat. Independently
restore authorized Terraform-state access before any rollout/cleanup apply.

Paused at the user's request after successful live PostgreSQL schema and principal
bootstrap. No further cloud operations, user seeding, image rollout or cleanup were
performed as part of saving this checkpoint. Resume only when the user returns.

### Completed, with evidence

- Release `local-20261023t074801z-939ccecd80d1`: five images built/published;
  immutable image pins already prepared locally. Release source has 104 hashed files.
- Cloud Shell Entra token login to `turnstile` as `Puneet Devadiga` succeeded.
- Live schema step: administrator session verified; `database_step=schema`,
  `committed=true`. Upgraded/repeated/verified revision `0003` and 15 application
  tables plus Alembic version table.
- Live principals step: administrator session verified;
  `database_step=principals`, `committed=true`. API/ingestion mappings and scoped
  grants passed checks rejecting effective DDL privileges. No control-plane grants.
- Both live steps explicitly report no user/password seeding.
- Corrected bootstrap locally verified with **47 passing focused tests**.
  SHA256: `91CD0D5414F5A7CDC2253B25FE599C0982A84B722B0487091ADA3D139A8258BF`.
- Evidence above is supplied Cloud Shell output, not an independent runtime probe.

## Security status during pause — must not assume cleanup

Latest successful Cloud Shell audit showed PostgreSQL public access **Enabled**,
with exactly one rule `temporary-cloud-shell-bootstrap`, start/end
`135.171.36.90`. Entra enabled, password authentication disabled at that audit.
No cleanup has been verified after bootstrap. A single-IP rule is temporary access,
not private-only containment. It does not expire automatically.

Do not run stale containment tasks blindly: prior containment attempts exited 1;
Terraform state may contain imported firewall resources whose live state changed.
Use a fresh read, narrow reviewed plan and readback for cleanup. Preserve private
endpoints and existing app networking. No broad Azure-services rule is needed.

## First actions on return

1. Read this checkpoint and `docs/postgres-bootstrap-execution-20261023.md`.
2. Read current local changes before editing, especially `.vscode/tasks.json`.
   Preserve user edits and do not apply old saved plans.
3. Refresh Azure login/token and verify tenant/subscription/user. Cloud Shell may
   have timed out; `COMMON`, environment variables and outbound IP may have changed.
   Never print tokens/passwords. Do not rerun bootstrap simply because a session ended.
4. Read current PostgreSQL auth/network/firewall configuration. If further public
   DBA access is unnecessary, close temporary public access using a fresh scoped
   Terraform plan and independently verify Disabled plus no temporary rules.
   Otherwise agree a limited remaining window; do not reuse an old Cloud Shell IP.

## Remaining deployment work, in order

1. **Inspect existing login/secret inputs without disclosing secret values.**
   The last runtime plan failed because local login was enabled but `local_auth`
   was null. Required versionless Key Vault references: JWT signing secret,
   initial admin password and initial customer password; also approved account
   emails/customer organization. API Secrets User was previously verified; operator
   secret-write authority was not. Use central provisioning if the operator cannot
   write secrets; do not self-grant roles or request broad RBAC privileges.
2. **Securely initialize portal users.** Use the reviewed release's production
   bootstrap/seeding path with approved secrets; no default passwords, plaintext
   SQL password inserts, or credentials in chat/logs/state. Verify API startup
   seeding behavior before choosing a separate one-shot seed operation. The schema
   and role scripts do not seed users. Do not grant runtime DDL to enable seeding.
3. **Prepare a fresh narrow application rollout plan.** Reuse verified immutable
   pins, PostgreSQL managed-identity URLs and versionless secret references. Keep
   existing MSSQL retained. Review the complete fresh plan before any apply.
   The previous failed partial plan included unrelated APIM/OpenAPI/logger and
   Key Vault drift; it is not approved or safe to apply. Do not use the whole
   prerequisites graph against the running stack.
4. **Deploy approved application changes.** Azure configuration writes remain
   Terraform-only except explicitly authorized CLI exceptions. Role assignments
   remain central-team-owned. Preserve admin ingress `167.103.66.114/32`, private
   API, closed SCM, storage restrictions, and existing private endpoints.
5. **Verify actual runtime behavior.** Check deployed image digests, Key Vault
   reference resolution without secret disclosure, private PostgreSQL connectivity
   using API/ingestion managed identities, startup/health, and admin/customer login
   end to end. Database grant success is not proof of managed-identity login.
6. **Verify final containment and report honestly.** Confirm public PostgreSQL
   access disabled/temporary rule removed, and record deployment/login evidence.
   Unsupported workers stay disabled; no claim that image publication implements
   missing release/provisioning engines or an Event Hub consumer.

## Resource identifiers

- Subscription: `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`
- Tenant: `beb276ac-6e9f-498e-8e31-019ee666decd`
- Resource group: `IDS-TOKEN-EXCHANGE-POC`
- PostgreSQL: `poc-ids-token-ex-pg.postgres.database.azure.com`, database `turnstile`
- Approved DBA: `Puneet Devadiga`, object `dd928302-055b-4516-9b8e-b06ae823057b`
- API: `poc-ids-token-ex-api-identity`, object `4e7b70ed-9868-47ba-9b61-304f1e1fdd89`
- Ingestion: `poc-ids-token-ex-ingestion-identity`, object `edbfc3e2-a8e5-4652-9bb0-311233756d42`
- Key Vault: `pocidstokenexkv`; registry: `pocidstokenexacr.azurecr.io`
- Cloud Shell working directory: `$HOME/aiflux-pg-bootstrap`; explicit interpreter
  `.venv/bin/python`. Entra functions are in `postgres`, not `turnstile`; the script
  handles separate connections and the live `rolname` column spelling.

## Resume prompt

> Resume from docs/resume-deployment-20261023.md. Live PostgreSQL schema and API/
> ingestion principal grants committed successfully. Do not repeat bootstrap or
> assume cleanup. First recheck network containment and remaining login-secret
> inputs, then prepare a safe application-only deployment and verify portal login.