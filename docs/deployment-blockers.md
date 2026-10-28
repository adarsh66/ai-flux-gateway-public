# Deployment status and administrator handoff

## Latest continuation: all runtime images built, PostgreSQL rollout blocked

The five-image release `local-20261023t074801z-939ccecd80d1` is built and
digest-verified, including ingestion and a real fail-closed publication Function.
See [implementation, run IDs, full digests and verification](runtime-image-release-20261023.md).
The latest Terraform runtime plan failed its genuine central-RBAC and missing
production-auth-secret checks. All 11 grant gaps remain visible; PostgreSQL has
no verified private workstation route. No runtime apply occurred. Older SQL
deployment successes below are historical and do not attest this new release.

Verified 2026-10-23. Never include tokens, passwords, seed JSON or signing keys
in this document or deployment logs.

## Completed and verified

- ACR release `sql-poc-20261022-r1`: API cm3, customer cm4, admin cm5 succeeded.
- API endpoint `poc-ids-token-ex-api-pe`: Approved / Succeeded.
- Existing VNet linked to `privatelink.azurewebsites.net`; API and API SCM A
  records are `10.240.3.9`.
- Customer App Service publicNetworkAccess Enabled, default access Allow.
- Customer SCM has separate rules: use-main=false, default Deny, deny-all.
- Customer outbound VNet integration uses the existing App Service subnet.
- Customer private-proxy build cm6 Succeeded:
  aiflux-customer:sql-poc-20261022-private-r2, digest
  sha256:c8dffdbd29ab1a6388d04e6446a4c72cd0df8a0c37db43ba322360b829d864ba.
  Deployed by digest and write/delete locked. Live same-origin TLS proxy login,
  identity and subscriptions checks passed for all three customer accounts.
- API/SQL public restrictions have not been relaxed. Admin now has the explicitly
  approved single-/32 ingress described below; no earlier address is allowed.
- API/customer/admin user-assigned identities already have registry AcrPull.
- Operator principal `dd928302-055b-4516-9b8e-b06ae823057b` is already SQL Entra
  administrator and subscription Contributor. No Entra directory role request
  is currently substantiated.

## Resolved: SQL initialization and three-app runtime deployment

Private SQL r6 applied/verified Alembic 0003/schema, all four accounts and actual
API managed-identity CRUD/no CONTROL/DDL denial. See
[private SQL execution evidence](private-sql-runner-execution.md). No missing SQL
role/network blocker remains for the running application. SQL stayed private.

All three App Services now have digest-pinned images, correct separate MI ACR
pull configuration and runtime ports. Production API uses encrypted ODBC18 MI SQL,
original protected signing key, correct home tenant, no startup seed JSON.
No secret values passed through CLI arguments or temporary files.

Public customer /healthz 200; unauthenticated /api/me 401; all three customer
accounts login/me/subscriptions 200; invalid password 401; /api/admin path 403.
Private smoke run 41f849a169534c599782c3bbc0d88c15: API /health and /ready 200,
admin /healthz and /admin/ 200, all four accounts login/me 200, customer admin
access 403 and admin role access 200. API image auth/startup source hashes match
current workspace. SQL/API/admin public access remains Disabled; all public SCM
probes 403. Temporary ACI/subnet/NAT/IP independently verified absent.

## Resolved: approved admin workstation ingress

Executed 2026-10-23, final readback 02:48:23Z. User corrected approval to ONLY
**167.103.66.114/32**; earlier 167.220.255.79 was never allowed. Admin now uses
the existing 10.240.4.0/24 integration subnet and locked same-origin proxy digest
sha256:dd71e8fa9d75bc3b5f4bd4f8393ad1de09cac1fdbfab3564be6c1438a4243c60.
Public Enabled/main default Deny/sole /32 allow; SCM independent default Deny,
deny-all/no allows. API/SQL remain public Disabled. Existing private endpoints,
customer, credentials, roles, gateway policies and inference gates are unchanged.

Private candidate smoke 67ba8cfcd7864f22a89f972aa8bc8914 passed before enablement;
all four temporary resources were cleaned and independently confirmed absent.
Allowed workstation GET admin/healthz, admin login/me/organizations/gateway-settings
200; all three customer roles denied admin APIs 403; wrong password 401.
Independent public ACR QuickRun cme resolved public 20.212.64.16 and got admin
403. Public SCM/API probes 403. Browser SQL sign-in rendering and actual invalid
password rejection verified. Valid-account browser navigation is not claimed;
same-origin authenticated HTTP is proven. There is **no admin ingress blocker**.

Final focused suite 109 passed, 2 warnings; AST/editor clear. Original admin
rollback digest/baseline retained externally. See
[admin execution evidence](admin-allowlisted-ingress.md) and
[current result](../.azure/admin-ingress-result.json).

## Remaining functional gate: catalog and inference acceptance

Configured catalog path: /app/gateway/catalog/dev-models.json. The capability
acceptance flag remains false because a successful build or SQL login does not
prove guarded gateway inference. Actual authenticated /api/models returns 503:
“Model catalog has not passed gateway capability validation”. Catalog/model picker
and inference cannot be advertised as released until the existing gateway's
capability verification is actually performed and accepted. No APIM/model policy
changes or acceptance bypass were made by this application-deployment task.

## Exact scopes if a future operation is denied

Resource group scope:
/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC

- Network Contributor at the existing VNet/private DNS/endpoint scopes covers
  network configuration, if current Contributor is restricted by policy.
- Website Contributor on the three existing sites covers app configuration;
  site publicNetworkAccess changes additionally require sites/write.
- SQL database DDL is a database permission, not Azure SQL ARM Contributor.
- New role grants, if actually required, must be performed by Role Based Access
  Control Administrator/User Access Administrator at the narrow resource scope.
- Azure Policy deny requires the policy owner's approved exemption; additional
  Entra roles do not override policy.

No authorization-denied error or policy denial has been confirmed for the
network changes completed above. Do not request broad Owner/Global Administrator
permissions as a workaround.

## Deployment safety

SqlInitialized is supported by the actual successful r6 proof. Validation workflow
completed through the faithful Python CLM adaptation before deployment; the original
PowerShell workflow's encoding constructor is blocked by ConstrainedLanguage.
Actual adapted PowerShell validation/deployment entry points both exited 0.
Do not treat build success/ResourceHealth Available alone as application readiness.

The deployed customer is the private r2 same-origin bundle, not the old direct-API
r1 customer. The historical admin r1 used the direct private API URL and is now
superseded by the verified same-origin candidate above. All selected
images and MI IDs, live results and remaining gates are recorded in
[deployment plan](../.azure/deployment-plan.md#L1). New safety tests: 13 passed.
The same-origin admin candidate is now **deployed and allowlisted**; see the
[current ingress evidence](admin-allowlisted-ingress.md).
Original external credentials location: C:/Users/p4032099/.aiflux-poc/credentials.json.

Inventory capture reported two unattributed additions: approved persistent admin
private endpoint and its managed NIC. Retain/review these; they are not safe-to-delete
temporary artifacts. All four temporary smoke-runner resources are absent.