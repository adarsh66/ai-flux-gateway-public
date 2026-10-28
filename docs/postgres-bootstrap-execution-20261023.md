# PostgreSQL bootstrap execution — 2026-10-23

## Latest Cloud Shell findings (supersede workstation-only status below)

- **Live user seeding succeeded (user-supplied Cloud Shell output):**
  `database_step=seed_users`, `committed=true`; admin@tokenx-ids.com has role
  `ids_admin`, developer@caldova.com has role `customer`. Reviewed release check
  reports 104 files; Entra-only administrator/session, schema and single-IP guards
  passed before hidden password entry. Final output explicitly reports
  `jwt_changes=false`, `runtime_deployed=false`. No portal-login or network-cleanup
  success is implied. Do not rerun seeding. User fixed an earlier auth-guard failure
  in the portal; no agent ARM change was made.
- **Earlier preparation checkpoint (superseded by live success above):** the separate interactive
  [user seeder and Cloud Shell runbook](postgres-user-seeding.md) has 16 focused
  tests passing, alongside all 47 bootstrap/credential regression tests. It reuses
  the reviewed release's password hashing, audited Entra administrator and single-IP
  guards; inserts both users/memberships/organizations in one transaction; refuses
  overwrites; and needs neither Key Vault secrets nor JWT configuration. Passwords
  must be entered privately in the user's external Cloud Shell. No seeded-account,
  runtime rollout, portal-login or network-cleanup success is claimed.
- **Live schema bootstrap succeeded (user-supplied Cloud Shell output):** corrected
  script reports `database_admin_session_verified=true`, followed by
  `database_step=schema`, `committed=true`, `seeding=false`, and
  `control_plane_grants=false`. The schema-mode implementation upgrades through
  `0003`, repeats the upgrade and verifies the exact application table set before
  commit. This is real database schema initialization, not only offline validation.
  Initial-user seeding, secret configuration,
  application image rollout, end-to-end login and temporary-access closure remain
  pending; no success for those steps is implied.
- **Live principal/grant bootstrap also succeeded (user-supplied Cloud Shell
  output):** `database_admin_session_verified=true`, `database_step=principals`,
  `committed=true`, `seeding=false`, `control_plane_grants=false`. API object
  `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` and ingestion object
  `edbfc3e2-a8e5-4652-9bb0-311233756d42` were supplied using their verified managed
  identity names. Script success includes mapping checks, scoped table grants and
  checks rejecting effective runtime DDL privileges. This is not proof of a live
  application/managed-identity connection; runtime smoke tests remain pending.
- User-supplied Cloud Shell `psql` output confirms Entra token authentication to
  `turnstile` as session/current user `Puneet Devadiga` succeeds. Switching to
  password authentication is not necessary for this path.
- Latest user-supplied bootstrap audit shows public access with exactly one rule:
  `temporary-cloud-shell-bootstrap`, start/end `135.171.36.90`. This is temporary
  bootstrap access, **not** verified private containment; cleanup remains pending.
- Schema attempt returned SQLSTATE `42883` before migrations, incorrectly labeled
  authentication rejection because the failing function name contained `principal`.
- User's read-only catalog query finds neither Entra function in `turnstile`.
  In `postgres`, `pg_catalog.pgaadauth_list_principals(boolean)` exists, and
  `pgaadauth_create_principal_with_oid` exposes seven arguments:
  text/text/text/boolean/boolean/text/boolean (including tenant and skip-validation).
- First corrected Cloud Shell attempt reached the mapping lookup but failed with
  `KeyError` before administrator-session verification or migrations. A subsequent
  read-only diagnostic confirms actual columns include `rolname`, not the documented
  `rolename`. The result adapter now normalizes either label to `rolename`, rejects
  missing/conflicting columns, and preserves all OID/type/tenant/admin checks.
- Bootstrap correction uses a separate Entra connection to `postgres` for mapping
  verification/creation, checks session identity independently in `turnstile`, and
  keeps application migrations and grants in `turnstile`. Five- and seven-argument
  creation signatures are detected explicitly; the seven-argument call supplies
  the approved tenant and `skipvalidation=false`, with admin/MFA flags false.
- Principal creation commits in `postgres` before application grants, because
  cluster-wide roles must be visible across connections. This is **not atomic
  across databases**: a failed grant step can leave verified nonadmin roles for a
  safe retry. Existing conflicting/elevated roles still fail closed.
- The code correction changes no ARM settings, image digests, runtime configuration,
  application source manifest, secrets, or firewall safeguards. Local unit/offline
  tests alone are not live proof. Live schema success is recorded above from
  Cloud Shell output; principal/grant success is also recorded above.
  **Application identity connections and image rollout remain unverified**.

## Actual execution

- Verified signed-in user `xv.puneet.devadiga@singtel.com`, approved object,
  tenant and subscription against Azure; PostgreSQL configured administrator is
  `Puneet Devadiga`, the same approved object. Entra enabled/password auth disabled.
- Fresh workstation IP endpoint returned `167.103.66.114`. Another HTTP endpoint
  returned a different egress (`167.220.255.145`); HTTP proxy egress is not proof
  of the PostgreSQL TCP source. No second IP or broad range was allowed.
- Found public PostgreSQL already enabled with two out-of-band rules: a workstation
  rule and an Azure-wide `0.0.0.0` exception. The old saved plan missed these.
- Imported both firewall rules into Terraform state. Reviewed narrow plan applied:
  **one exact-IP rule created, two old rules deleted**, no other resources changed.
- Ran the PostgreSQL-specific bootstrap twice with cleanup between attempts.
  The reviewed release passed 104 file hashes, Python parsing, unique Alembic graph
  `0001 -> 0002 -> 0003`, PostgreSQL DDL compilation and SQLite upgrade/repeat.
- Both live schema attempts failed before a verified database-admin session.
  Safe driver classification on the second attempt: `OperationalError`,
  category `timeout`, SQLSTATE absent. DNS resolved to `4.193.98.244`.
  **No successful database authentication, migrations, MI mappings or DML checks
  are claimed.** Principal step was not reached; no account/password seeding ran.
- Each attempt's finally path applied a fresh guarded Terraform close plan,
  disabling public access and deleting the temporary rule. Immediate ARM reads
  confirmed disabled with zero rules. A subsequent independent read unexpectedly
  showed public access enabled again, still with zero rules. A further close-only
  operation applied a server-network-only update. Final independent CLI reads
  confirmed **publicNetworkAccess Disabled and firewall list empty**. The
  close-only result records `closed=true`. Do not assume an immediate response
  establishes durable containment; independent rechecks are required.
- Existing MSSQL, applications, storage, vault, SCM and central role assignments
  were not changed by these bootstrap applies. The later full *plan* observed
  unrelated vault drift; it was not applied.

## Runtime deployment preparation

- All eleven central grants reverified at `2026-10-23T10:08:10.570Z`.
  Generated five immutable image pins now carry evidence-derived
  `manual_rbac_verified=true`; base user-authored input is not overwritten.
- Fixed the verifier's unconditional false attestation. Ingestion, its timer and
  publication worker remain disabled; unsupported release/provisioning engines
  remain disabled. Legacy MSSQL retention stays true.
- Fresh existing runtime planning task executed with immutable pins. **Exit 1**:
  local login enabled but `local_auth=null`; reviewed secret references are absent.
  Partial output reports 1 addition, 5 updates, 0 deletions, but is **not an
  applyable or approved rollout plan** and must not be applied.
- The partial plan includes APIM API/OpenAPI changes and an Event Hub logger;
  it is not a safe API-cutover-free application-only plan. Vault drift was also
  observed: public access enabled in Azure, desired false, ACL Deny -> Allow in
  the proposed configuration. No vault writes or network opening were performed.
- Vault metadata-only check remains `403 ForbiddenByRbac`. No secret values were
  requested, generated or logged. Central secret provisioning and reviewed
  versionless references/accounts remain prerequisites for local login.
- Existing API remains private, admin allows only `167.103.66.114/32`, SCM closed;
  sites still report older digests. New runtime release was not deployed.

## Evidence and validation

- `.deployment/postgres-execute-*.log`: imports, reviewed open/close plans,
  Terraform applies, sanitized schema failure and ARM containment reads.
- `.deployment/postgres-execute-result.json`: most recent execution status;
  close-only runs replace the summary, not the schema log.
- `.deployment/image-build/local-20261023t074801z-939ccecd80d1/runtime-readiness.json`
  and `runtime-images.tfvars.json`: live grants and immutable rollout inputs.
- Same directory `runtime-plan.log`: failed fresh runtime plan; **never apply**.
- Focused bootstrap/credential tests: **34 passed**, one existing deprecation warning.
- JavaScript syntax check passed. Terraform validate passed with existing trusted
  provider override warnings. Focused Terraform bootstrap tests: **8 passed,
  0 failed**. Full `git diff --check` reports an existing blank line at EOF in
  the unrelated disabled-stage test; it was not changed.

## Remaining blockers

An approved, working TCP 5432 route to PostgreSQL is required (the exact cause of
the timeout is not established). Do not broaden database access or change identity
privileges to diagnose a transport timeout. Once reachable, rerun reviewed schema
and API/ingestion principal steps, verify effective no-DDL grants, close access,
then provision/reuse strong secrets through authorized central/private execution.
Only then generate and review an application-only, non-destructive plan that
excludes APIM cutover and unrelated configuration drift. No E2E success is claimed.