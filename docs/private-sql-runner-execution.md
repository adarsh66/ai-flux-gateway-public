# Temporary private SQL runner execution — 2026-10-23

## Result: private migration, seed and real API identity probes succeeded

Final run `f5e448f7600a40478f4a0eb48698dd56` completed `migrate --seed
--verify-api-mi` with process exit **0**, job status **ok**, all ten checks and
three genuine permission-denied DDL probes. All four temporary resources were
deleted and independently verified absent. Existing credentials were reused
unchanged. SQL public access remained Disabled and its Entra administrator stayed
unchanged. No App Service deployment/configuration or main deployment-plan edits
were made. Browser login and application readiness are not attested.

### Exact syntax fault and least-privilege correction

Fixed safe stage `runtime_deny_database_ddl` isolated SQLSTATE `42000`, native
`102` in r3. The database-level combined DENY incorrectly included `CREATE
SEQUENCE`, which is a **schema** permission. Removed only that item from the
database-level DENY and added `DENY CREATE SEQUENCE ON SCHEMA::dbo TO
[aiflux-api]`. Retained database `CREATE TYPE` denial, schema ALTER denial, all
other DDL denials and strict direct/effective permission, role and ownership
checks. No additional grant or runtime migration capability was introduced.

References: [CREATE SEQUENCE permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-sequence-transact-sql?view=sql-server-ver17#permissions),
[CREATE TYPE permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-type-transact-sql?view=sql-server-ver17#permissions),
[database DENY permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/deny-database-permissions-transact-sql?view=sql-server-ver17).

Each statement emits only a fixed stage label; failure diagnostics expose only
allowlisted stage, SQLSTATE, numeric driver codes and finite exception type.
No SQL parameters, raw driver messages, tokens, passwords or seed JSON are logged.
Generated migration/reflection/seed SQL uses fixed phase labels.

### Final live evidence

- ACR build `cmc`, immutable tag `sql-runner-20261023-r6`: Succeeded.
- Runner digest: `sha256:9c55a2449cea8cd626df4dbc1c491fe7d94512cb47bafba1fb533ee2120574f4`.
- ACI provisioning: Succeeded; process: Terminated, exit 0.
- Alembic head/schema, runtime DML permissions and four accounts verified:
  `customer1`, `customer2`, `customer3` with customer roles; `admin` with
  `ids_admin`. Password hashes, organization/tenant and roles match original seeds.
- Separate real `ManagedIdentityCredential` session selected the API UAMI,
  authenticated as `aiflux-api` without CONTROL and passed strict effective checks.
- Real INSERT/SELECT/UPDATE/DELETE probe passed, transaction rolled back, and a
  separate connection confirmed the unique probe row absent.

| Real API UAMI probe | Result | SQLSTATE | Native code |
| --- | --- | --- | --- |
| CREATE TABLE | SQL_DENY_DDL | 42000 | 262 |
| CREATE SEQUENCE | SQL_DENY_DDL | 42000 | 15247 |
| CREATE TYPE | SQL_DENY_DDL | 42000 | 262 |

Microsoft documents [15247](https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/database-engine-events-and-errors-15000-to-15999?view=sql-server-ver17)
as “User does not have permission to perform this action.” It is now recognized
alongside the finite permission-denial codes; syntax 102, unknown/missing codes
and unexpected DDL success still fail verification. All probes use rollback-only
transactions. Only the human operator token performs migration/provision/seed;
there is no API MI fallback for those operations.

All ten final checks: `configuration_validated`, `private_dns_validated`,
`odbc18_available`, `operator_database_verified`, `migration_head_schema_verified`,
`runtime_dml_identity_verified`, `four_portal_accounts_verified`,
`api_managed_identity_authenticated`, `api_managed_identity_dml_verified`,
`api_managed_identity_ddl_denied`.

## Owned new files

- [Orchestrator](../scripts/deployment/run_private_sql.py): Python 3.13, absolute
  Azure CLI executable, supplied combined CA, in-memory verified HTTPS ARM requests,
  digest-pinned build, secureValue token/expiry/seeds, bounded ARM polling and
  ownership-verified cleanup in finally.
- [Diagnostic entrypoint](../scripts/deployment/private_sql_diagnostic.py): delegates
  to the instrumented job; exposes only fixed status/check labels/stages,
  SQLSTATE and numeric driver codes, never raw exception text.
- [Safety regressions](../tests/unit/test_run_private_sql.py): redaction, secure ACI
  environment properties, no ingress/listening service, secret CLI guards,
  untrusted-log rejection, ARM polling-host restriction, immutable image tag guards
  and journal/ownership-limited deletion.

The orchestrator supports `--preflight`, `--execute --image-tag NEW_TAG`, and
`--cleanup-run RUN_ID`. An existing runner tag is rejected, not overwritten.
Use a fresh tag for any future execution. The default r1 tag already
exists. Only public runner sources and a generated Dockerfile enter the ACR build
context; no repository-wide upload or secret-bearing temporary file is used.

## Live prerequisites verified

- Subscription: `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`.
- Tenant: `beb276ac-6e9f-498e-8e31-019ee666decd`.
- Resource group: `IDS-TOKEN-EXCHANGE-POC`; location: `southeastasia`.
- `Microsoft.ContainerInstance` registered.
- Existing VNet `poc-ids-token-ex-vnet`, address space `10.240.0.0/16`.
- New runner subnet `10.240.5.0/24` verified vacant before each allocation.
- Existing private SQL DNS zone linked to that VNet; the job verified that SQL
  resolved only within `10.240.3.0/24`.
- Operator object ID `dd928302-055b-4516-9b8e-b06ae823057b` remained the SQL
  Entra administrator; actual SQL session `dbo`/database CONTROL checks passed.
- Existing API UAMI client ID `f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1`, principal ID
  `4e7b70ed-9868-47ba-9b61-304f1e1fdd89`, had AcrPull and successfully pulled both
  images. No new Azure role assignment or managed identity was created.

The ACI had no public IP/ports or listening server, restart Never, one CPU,
1.5 GiB memory, Azure DNS `168.63.129.16`, a dedicated delegated subnet and NAT
outbound. Only the NAT gateway had a public egress IP. SQL stayed private.

## Historical initial build and runtime results (superseded by r6 above)

Base API image for both builds:

`pocidstokenexacr.azurecr.io/aiflux-api@sha256:5e7e41ad72185b6ce28494fcf78a79e1071466bb2d200fa124c5703331e65532`

Both synchronous ACR builds used `--no-logs`. Each Dockerfile successfully ran
an import check for aiflux/Alembic/pyodbc, checked the Alembic configuration and
versions directory, and confirmed ODBC Driver 18 availability.

| ACR run | Runner tag | Build | ACI provisioning | Process |
| --- | --- | --- | --- | --- |
| cm7 | sql-runner-20261023-r1 | Succeeded | Succeeded | Terminated, exit 1 |
| cm8 | sql-runner-20261023-r2 | Succeeded | Succeeded | Terminated, exit 1 |

cm7 runner image:

`pocidstokenexacr.azurecr.io/aiflux-sql-runner@sha256:8cd14e6c9de207f03abae8958f13bbf058343af2afe255a2f04df07639c652eb`

cm8 diagnostic runner image:

`pocidstokenexacr.azurecr.io/aiflux-sql-runner@sha256:107e0fc71c7dba0e85d0c9cb307963221060931fcb9ae81dacbca5e757eca835`

The initial r1/r2 jobs completed exactly these checks:

1. `configuration_validated`
2. `private_dns_validated`
3. `odbc18_available`
4. `operator_database_verified`
5. `migration_head_schema_verified`

At r1/r2, not completed: `runtime_dml_identity_verified`, `four_portal_accounts_verified`.
Both subsequently passed in r4/r5/r6.

| Follow-up | ACR build | Run ID | Outcome |
| --- | --- | --- | --- |
| r3 | cm9 | ec5604f8163140ae92babf9a1cde16dd | Exact database DENY stage, 42000/102; no seed |
| r4 | cma | 7ed14cfca15d4ee28ffa3f647625c318 | Scope fixed; seed and real MI CRUD passed; denial classifier failed |
| r5 | cmb | 609aa2fd0bf14f16b8df64cb2a8c5c31 | Reverified existing accounts/CRUD; identified sequence denial 42000/15247 |
| r6 | cmc | f5e448f7600a40478f4a0eb48698dd56 | All checks/probes passed, exit 0 |

r3/r4/r5 runner digests respectively:
`sha256:a68afc1526c1296f13f46e5d3be3abcc48986bfb338396e1ab4b5dc6a4eceb47`,
`sha256:1628216f6ad396e8f6964fe9e6518fcf7419aa3769b8538305e55bdd47a4781a`,
`sha256:9e65cc5ff2e82c516d37182b5d6c425293209c750c6d03e03e4e3835de9f4e9a`.
Each attempt cleaned and verified all temporary resources absent.

An earlier local build submission failed before upload because ACR resolved a
relative Dockerfile path against the process working directory. Fixed by using
an absolute path and covered by regression test. No resources were created by
that attempt (run ID `c1a2554b006c43088610b3eebee6d812`).

## Credentials and non-secret execution journals

Generated once and reused for the diagnostic retry, outside the repository:

- Credentials and separate signing key: C:/Users/p4032099/.aiflux-poc/credentials.json
- cm7 journal: C:/Users/p4032099/.aiflux-poc/private-sql-6acda7a0bb3f47db890f8218c2b3e429.json
- cm8 journal: C:/Users/p4032099/.aiflux-poc/private-sql-0120f52944504e2d9d9cb618cbd1a774.json

The parent directory's Windows DACL was restricted with icacls and verified via
Win32 ACL inspection to contain exactly one allow ACE for the current user SID
before credentials were written. Existing credential file ACLs are reset to
inherit only that protected parent. The file contains four independent random
passwords and a random signing key; these values were never printed. The SQL
token was never persisted in this directory or passed as a command argument.

Seeding committed in r4; r5/r6 verified the same accounts without password reset.
The orchestrator now requires the existing protected credential file and never
generates replacements. Its content checksum remained unchanged through retries
(only the equality boolean was reported). These are database-verified credentials;
browser/application login is not attested. Final non-secret journal, in the same
protected external directory: private-sql-f5e448f7600a40478f4a0eb48698dd56.json.

## Cleanup evidence and exact resource IDs

Resource ID prefix:

`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC`

Suffixes (concatenate to that prefix):

- `/providers/Microsoft.ContainerInstance/containerGroups/poc-ids-token-ex-sql-runner`
- `/providers/Microsoft.Network/virtualNetworks/poc-ids-token-ex-vnet/subnets/poc-ids-token-ex-sql-runner`
- `/providers/Microsoft.Network/natGateways/poc-ids-token-ex-runner-nat`
- `/providers/Microsoft.Network/publicIPAddresses/poc-ids-token-ex-runner-ip`

Each attempt journaled the exact IDs before PUT. ACI/NAT/IP used the ownership
tag `aiflux-private-sql-run` with the run ID. Subnets do not support tags; the
delegation name `aiflux-run-RUN_ID`, exact CIDR and NAT ID provided the ownership
guard. Deletion checked both the journal and current ownership marker.

All four resources were deleted in dependency order and verified absent by ARM
GET after **each** execution. An independent final ARM GET reconfirmed all four
absent, SQL publicNetworkAccess Disabled and unchanged SQL administrator SID.
No resource group, preexisting subnet, identity, DNS link or application was
deleted. Build artifacts remain in the existing ACR for audit/reuse. The final
subscription inventory capture found zero new remaining resources and no cleanup
concerns.

## Validation and handoff

- Final focused runner/orchestrator suite: **112 passed**, 8 deprecation warnings;
  explicit AST parsing of all three runner Python modules passed.
- Editor import-resolution diagnostics remain under the system interpreter;
  runtime tests use the configured source/root/existing venv site-packages path.
- No Azure RBAC, managed-identity assignment, image pull, policy or SQL operator
  permission blocker remains in the completed runner task. The syntax error was
  corrected at its actual permission scope, not bypassed.
- Future retries must preserve least-privilege checks, use a new immutable image
  tag and reuse the same protected credentials. Never use API MI for migrations
  or grant DDL. Main-plan attestations were not changed by this task.
- No App Service deployment/configuration or main deployment-plan edits were made
  by this runner task. Customer/admin browser and application readiness checks
  remain outside this task and are not attested.