# Source handoff — 2026-10-24

## Superseding GLM live checkpoint — 2026-10-27 local / October 26 23:01 UTC

API tag `glm-20261026t154044z-dfb523bedf4e` and latest portal tag
`local-20261026t165602z-eee5c65cfe99` are **already applied**, not waiting to
deploy. Initial three-image apply completed at 16:45 UTC; latest portal-only
correction at 22:36 UTC changed exactly two existing apps, with no adds/destroys.
Fresh captured `verify-live`, `probe-live`, and `diagnose-activation` exits are all
0. Protected baseline, source manifests, private API, resolved JWT and approved
storage rules match. All sites report READY; health/proxy probes pass.

Authenticated admin sync returned 200 with no changes and 11 accepted chat models;
discovery has 12 entries including nonselectable Decision-1. Actual customer GLM
Playground Send returned 200 and displayed Hello., with 16 prompt / 29 completion /
45 total tokens. Current focused tests: 199 passed. No provider-key read, new cloud
configuration writes, inference retries or counter resets during this resume.
Do not replay obsolete apply plans. Accepted inventory retains its 24-hour expiry;
fresh all-ten inference and fresh password login were not performed this resume.
Exact digests and evidence are in the
[current GLM deployment checkpoint](docs/glm-external-provider.md) and
[sanitized acceptance report](gateway/validation/glm-release-20261026.json).

## Branches and review order

1. `fix/backend-postgres-jwt-auth` starts at upstream `origin/main`, not the
   portal branch. It contains production PostgreSQL credential/JWT validation,
  no-write production account bootstrap/login, and their regression tests.
  Published commit: `c6ed78e977bcb49f584154d06e027b80b4cf8981`;
  [upstream PR #13](https://github.com/adarsh66/ai-flux-gateway-public/pull/13).
2. `fix/terraform-postgres-bootstrap-handoff` is **stacked on the backend branch**.
   Review its incremental diff against that branch; merge the backend first.
   It contains the reviewed Terraform changes, mocked regression tests,
   PostgreSQL DBA bootstrap/seeder source and offline checks, a guarded
   resource-only planner, and ignore rules.
3. The separately pushed `fix/portal-proxy-tls-admin-redirect` (`07d4b34`) remains
   independent. Neither branch here includes its proxy/UI/redirect changes.
  [Upstream PR #12](https://github.com/adarsh66/ai-flux-gateway-public/pull/12)
  targets upstream `main` independently of the backend/infrastructure stack.

These are source handoffs, not an authorization to deploy. The backend and portal
PRs above were verified through GitHub's public API. No infrastructure PR has
been created by this handoff; review its diff against the backend branch, not an
unrelated portal branch or an assumed upstream branch of the same name.
The fork is `puneetdevadiga/ai-flux-gateway-public`; upstream `origin` remains
`adarsh66/ai-flux-gateway-public`.

## Reproducibility and offline checks

Install this project's declared development dependencies from
[pyproject.toml](pyproject.toml), and ensure the checkout's
[source package](services/control-plane/src/aiflux/__init__.py) precedes any
older installed copy on Python's module search path. Run `pytest -q tests/unit`
from an isolated checkout. Backend-only snapshot: **328 passed, 6 skipped**.
Infrastructure index-tree snapshot: **386 passed, 15 skipped**; Terraform
`validate` passed and mocked `test`: **61 passed, 0 failed**. Historical-release
checks skip when their deliberately unpublished local artifact is absent; the
portable source-only tests run without it. No live database was contacted.

[Portable bootstrap/seeding tests](tests/unit/test_postgres_source_handoff.py)
create a synthetic local manifest from tracked source, compile PostgreSQL DDL,
upgrade and repeat against disposable SQLite, and verify hashing, transaction
rollback and refusal to reset/promote accounts. This is not a live PostgreSQL
integration test or reproduction of a historical image/archive.

Terraform requires version 1.12.1 and the locked provider versions. In a disposable
checkout, initialize providers with backend initialization disabled; then run
`terraform validate` and `terraform test` in [infra/terraform](infra/terraform/main.tf).
All test providers are mocked. Validation here used the workstation's trusted
provider development overrides (AzureRM 5.9.0 / AzAPI 2.13.0), and Terraform warned
that these may differ from released providers. This is not independent validation
of downloaded registry binaries; repeat with standard locked providers on the
reviewer's approved runner. Windows focused filters must use backslashes,
for example `-filter=tests\postgres-bootstrap.tftest.hcl`; verify a nonzero test
count. A workstation-specific trusted-provider configuration is not included.
Never initialize the live backend or execute a real plan/apply for these checks.

## Deployment and database safety

- Role definitions/assignments are **central-team owned**, outside this stack.
  The [data-only handoff](infra/terraform/central-handoff.tf) derives requests
  from configured scopes and actual managed identity principal IDs. Its output
  is not evidence that grants exist. Verify effective grants separately before
  setting `manual_rbac_verified`; never substitute subscription-wide grants.
- Azure resource-management access does not supply PostgreSQL SQL privileges
  or private connectivity. Use a separately approved DBA/migration identity.
  Runtime roles must not own schema, run migrations, or receive DDL privileges.
- [DBA bootstrap](infra/sql/bootstrap-postgres.py) verifies the release manifest,
  unique migration graph and administrator/session identity. It separates Entra
  principal mapping in `postgres` from grants in the application database.
  Live schema/principal operations require an explicit mode and `--execute`.
- [One-time seeder](infra/sql/seed-postgres-users.py) requires hidden interactive
  passwords, inserts users/memberships atomically and refuses existing accounts
  or conflicting memberships. It performs no password resets, JWT provisioning,
  migrations or Azure configuration writes. Do not rerun it on seeded accounts.
- Both database helpers intentionally pin a historical release tag; the seeder
  also pins the bootstrap companion's SHA256. They need an independently reviewed
  manifest/context. The historical artifact is excluded; do not remove those
  guards to make a new release work. Re-review and regenerate pins for a new
  approved release. The synthetic test artifact is never deployable approval.
- Prefer a private runner. Any exact-IP temporary public bootstrap is a separate
  approval, followed by containment and independent verification. Keep the
  bootstrap input null normally. `postgres_bootstrap_rules_to_retire` is solely
  for reviewed state adoption/removal, not access: nonempty input can create
  Azure-wide wildcard rules if misused. Do not apply it as normal configuration.
- [The resource planner](scripts/plan-resource-provisioning.ps1) is plan-only
  and environment-specific: it pins a subscription/resource group/operator IP
  and expects a local trusted-provider configuration. Review and adapt it for a
  different environment; it is not a portable deployment entry point. A full
  prerequisites apply against existing app state can delete workloads. Never
  apply partial/errored plans or bypass its resource/action/security boundaries.
- JWT bootstrap passwords never reach production app settings. Prefer a resolved
  Key Vault JWT reference. Sensitive direct-secret input is still stored in
  Terraform state/plans and App Service settings; `sensitive` is not encryption.

## Reported runtime status; not revalidated during this Git handoff

Customer password login and the admin HTTPS redirect were previously reported
successful. The admin real-password login still returned **401** and is unresolved;
synthetic invalid-password 401 checks do not establish real-password success.
Workers remain disabled/missing; APIM/native inference is not released. Admin SCM
allow-all ingress is a separate outstanding security finding requiring remediation.
Do not claim the service is production-ready or that this handoff fixed those items.
No Azure deployment, secret, network or RBAC operation was performed here.

## Deliberately unpublished; preserve locally for separate review

- Local workflow/editor/deployment state, Terraform inputs/state/plans/logs,
  credentials, build output and the security-drift runtime override.
- The legacy auth module and duplicate `0003` migration. The active checked-in
  migration is [0003_stable_teams.py](services/control-plane/migrations/versions/0003_stable_teams.py).
  Reconcile conflicting history with the user/DBA before any migration; do not
  delete, renumber, import, or publish the conflicting migration speculatively.
- Dated execution dumps, internal RBAC/account/IP handoffs, current deployment
  guide edits linking them, and the unreviewed auto-deploy pipeline.
- The broader ACR/image-release, runtime/portal/JWT/ingress rollout helpers and
  associated tests, the optional publication Function/worker, and legacy MSSQL
  private-runner tooling. They need a separate complete dependency/security
  review. They are not required by the isolated backend or this safe subset.
  Do not copy all untracked files into a build or commit them indiscriminately.

Recreate environment-specific ignored inputs, protected evidence directories and
workflow approval state through the approved process, never by publishing local
state or fabricating validation success. Ignore rules are not access control.