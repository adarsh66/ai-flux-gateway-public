# Admin allowlisted ingress — deployed and verified

## Current execution — 2026-10-23T02:48:23Z

**Completed.** The user explicitly authorized ONLY **167.103.66.114/32**,
correcting/revoking 167.220.255.79. The revoked address was never installed.
The missing-CIDR/private-browser blockers in the historical preparation below
are superseded by this execution evidence.

Admin URL: https://poc-ids-token-ex-admin.azurewebsites.net/admin/

### Exact permanent changes

- Admin outbound VNet integration changed from absent to the existing
   poc-ids-token-ex-app-service-integration subnet, 10.240.4.0/24, already delegated
   Microsoft.Web/serverFarms. No subnet, NSG, DNS or private-endpoint rewrite.
- While public access was Disabled, admin was updated/restarted to
   pocidstokenexacr.azurecr.io/aiflux-admin@sha256:dd71e8fa9d75bc3b5f4bd4f8393ad1de09cac1fdbfab3564be6c1438a4243c60.
   ACR run cmd/tag sql-poc-20261023-admin-proxy-r1 remain Succeeded/write-delete locked.
- Existing managed-identity pulls retained: client
   3143ef2e-4a97-40cf-9a8c-2880d697f64b; existing scoped AcrPull verified, no grant.
- Admin publicNetworkAccess now Enabled. Main default Deny; sole allow
   operator-0, priority 100, 167.103.66.114/32; explicit final Any Deny.
- SCM is independent: use-main=false, default Deny, only explicit Any Deny,
   zero allows. Exact rule sets read back before and after public enablement.
- API public Disabled, SQL public Disabled; customer image/config/ingress unchanged.
   API/admin Approved private endpoints remain 10.240.3.9/10.240.3.10; SQL remains
   10.240.3.5. No secret rotation, app-settings write, database migration/seeding,
   role grant, gateway policy change or catalog/inference gate change.

Original admin rollback digest retained:
sha256:82e2cd7b36d6da18288c939b02532f361a6ac414661e8e8ae10b995c26ed9be3.
Protected original baseline: external admin-ingress-baseline-20261023.json under
C:/Users/p4032099/.aiflux-poc. If rollback becomes necessary, disable public access
and confirm it first, restore the old image/MI configuration privately and restart;
do not publicly expose the old direct-API bundle. Original network baseline is
retained; never restore unsafe inherited SCM allows. No rollback was required.

### Actual validation/deployment sequence

Read azure-validate/azure-deploy AZCLI recipes/checklist plus App Service VNet and
access-restriction documentation, AppLens best-practice review, current code and
prior evidence. Explicit subscription/RG/location approval reused. Original
azure-validate workflow invocation exited 1 because CLM blocks UTF8Encoding;
existing faithful Python adaptation completed all sequential steps through
UpdateStatus after real checks and before image deployment. The admin-only plan
addendum was Validated at deploy time; the historical three-app plan was retained.

The new fixed-scope [admin rollout helper](../scripts/deployment/admin_rollout.py)
uses existing deploy_portals/run_private_sql ARM/network/identity primitives; it
never invokes the three-app deployment routine. Preparation, validation, deploy
and restart succeeded. No full Terraform apply, template deployment, AZD init,
ACR admin enablement, SCM opening or new persistent resource was needed.

Private smoke run **67ba8cfcd7864f22a89f972aa8bc8914** passed before ingress:
API health/ready 200; private DNS exact API/admin/SQL addresses; candidate admin
healthz/admin page 200; admin same-origin unauthenticated me 401; all four original
accounts login/me 200 and expected roles; admin organizations/gateway-settings
200 for ids_admin, 403 for all three customers; invalid admin password 401.
TLS-validating nginx upstream forwarding was therefore exercised, not inferred
from ARM Running state. API auth source hashes still match workspace.

The existing temporary private-smoke procedure created its ACI, dedicated subnet,
NAT and public IP only for the checks. Ownership-safe cleanup completed; a later
independent ARM read verified **all four absent**. No temporary resource remains.

The actual admin_ingress module then ran with --apply, only the corrected /32,
and the independently verified candidate digest: exit 0. Its disable/readback,
write/readback, enable/readback fail-closed ordering completed successfully.

### Live public and browser proof

From this workstation after allowlisting:

| Check | Observed |
| --- | --- |
| GET /admin/ and /healthz | 200 |
| Unauthenticated GET /api/me | 401 |
| Original admin login /api/auth/login and authenticated /api/me | 200; ids_admin |
| Admin GET /api/admin/organizations and /api/admin/gateway-settings | 200 |
| Each original customer login/me through admin origin | 200; customer |
| Each customer's organizations/gateway-settings requests | 403 |
| Deliberately incorrect admin password | 401 |
| Public admin/customer/API SCM | 403 |
| Direct public API /health | 403 |

Independent external negative probe: ACR QuickRun **cme** Succeeded at
2026-10-23T02:46:42Z, no output image/persistent task. Secret-free Python worker
resolved public DNS **20.212.64.16** (asserted globally routable) and GET /admin/
returned **403**, not private-endpoint traffic. Its only uploaded context was
[the public probe task](../.azure/admin-ingress-probe/task.yaml). No credentials
or login request were sent from this external worker. The webpage-fetch facility
also rendered the portal but does not establish an independent network source;
it is not used as negative-access evidence.

Browser reloaded the real AIFLUX IDS Admin SQL sign-in page and a deliberately
invalid sign-in displayed “Invalid username or password”, with HTTP 401.
Valid credentials/tokens were used only in programmatic memory and never passed
to browser tools or printed. **Authenticated browser navigation is not claimed**;
valid-account same-origin HTTP authentication/authorization is proven.

Customer regression: GET / and /healthz 200, unauthenticated me 401, admin path
403. Baseline comparison confirms API/customer images, identities, integration and
ingress unchanged. API catalog acceptance still false, startup seed absent;
catalog/inference functionality remains deliberately gated (existing /api/models
503 limitation, not an admin ingress blocker).

Final focused tests: **109 passed, 2 dependency warnings** (rollout, ingress,
deployment, portal auth); AST and editor checks clear. Evidence:
[current result](../.azure/admin-ingress-result.json),
[deployment plan addendum](../.azure/deployment-plan.md), and protected external
portals-admin-candidate-deploy / portals-private-smoke / portals-admin-public-smoke /
portals-admin-external-probe JSON journals. No password/token/signing key in evidence.

## Historical preparation — superseded by the execution above

## Approval and blocking input (2026-10-23)

The user approved exposing the existing admin portal through an App Service IP
allowlist. **No public IP/CIDRs were supplied.** Autonomous continuation does not
authorize guessing an IP, looking up the workstation's egress address, or opening
Internet-wide access. The remaining ingress blocker is **operator-specified
public IP CIDRs required, no permission blocker demonstrated**.

The current admin remains private. No new ACI, network resource, role assignment,
SQL/firewall change, credential rotation, catalog acceptance or inference-policy
change was made. Customer routing and role acceptance remain unchanged.

## Nonsecret live baseline

Authenticated ARM reads on 2026-10-23 confirmed:

- Admin/API/SQL publicNetworkAccess Disabled; HTTPS-only on all three portals/API.
- Admin main default Deny, deny-all. SCM default Deny, deny-all, but currently
  use-main=true. The future ingress helper must set use-main=false **before**
  public ingress is enabled; inheriting admin allows would expose public SCM.
- Admin outbound VNet integration is absent. Existing API and customer outbound
  integration use the existing App Service integration subnet.
- Admin live image remains
  `pocidstokenexacr.azurecr.io/aiflux-admin@sha256:82e2cd7b36d6da18288c939b02532f361a6ac414661e8e8ae10b995c26ed9be3`.
- Admin uses existing managed-identity registry pulls, client ID
  `3143ef2e-4a97-40cf-9a8c-2880d697f64b`.
- API/customer images remain their previously deployed digests. Customer public
  access Enabled/default Allow and independent SCM Deny remain unchanged.

The prior private smoke evidence is historical and has not been rerun for this
candidate. No credential values or full app settings were requested or printed.

## Candidate build (not deployed)

ACR run **cmd** Succeeded; tag `sql-poc-20261023-admin-proxy-r1` is write/delete
locked. Candidate immutable reference:

`pocidstokenexacr.azurecr.io/aiflux-admin@sha256:dd71e8fa9d75bc3b5f4bd4f8393ad1de09cac1fdbfab3564be6c1438a4243c60`

Build inputs: VITE_PORTAL_MODE=sql, VITE_CONTROL_API_URL=/api,
VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net.
Only frontend source/manifests were uploaded from a temporary minimal context,
removed afterwards. No backend, SQL, deployment artifacts, attachments or
credential files were included. Build success proves TypeScript/Vite compilation,
the SQL same-origin build guard, the CA bundle and actual runtime nginx syntax
check; it does **not** prove live private routing, login or browser readiness.

The admin nginx proxy preserves `/api/` paths (including `/api/admin/`), bearer
Authorization and query strings. Its sole upstream is the fixed HTTPS API host,
with matching Host/SNI, certificate verification, bounded timeouts and no-store
responses. API role/tenant checks remain authoritative. Customer nginx still
blocks administrative paths. The existing build wrapper now forces only admin
SQL builds to `/api`; the customer build input is unchanged.

## Safe activation sequence after CIDRs are supplied

1. Obtain **explicit operator-specified canonical public CIDRs**. Supply each
   separately using `--allow-cidr`; bare IPs must include /32 or /128. No defaults,
   placeholders, service tags, private/special-use ranges or /0 are accepted.
   Input-only validation is the default; without `--apply` there is no Azure call.
2. Review the admin-only addendum under azure-validate/azure-deploy. The existing
   three-app deployment plan is historical Deployed, not validation of this
   candidate. Do not rewrite its status or reuse its three-app deploy routine to
   push this change; that routine intentionally pins the prior approved release.
3. While admin public access stays Disabled, attach admin outbound integration to
   the **existing** App Service integration subnet through a reviewed update;
   preserve its Approved sites private endpoint and DNS zone group. Confirm API
   hostname resolves privately from the admin container and HTTPS is reachable.
   No new subnet/ACI/NAT/public IP or extra role grant is needed by this design.
4. Deploy the validated candidate by digest to **admin only**, retaining the prior
   image for rollback and existing UAMI/client-ID registry configuration. Keep API,
   SQL, customer and all secrets untouched. Restart and verify private admin
   health, same-origin login/me, admin API authorization, invalid login and
   customer-role rejection. Do not expose a release without this proof.
5. The fixed-scope module
   [scripts/deployment/admin_ingress.py](../scripts/deployment/admin_ingress.py)
   accepts `--apply`, repeated `--allow-cidr`, and the independently verified
   `--admin-image-digest`. Its CLI requires the admin private endpoint/DNS proof,
   exact existing outbound integration, nonlegacy digest with MI pulls and API/SQL
   remaining private. It does not build/deploy images or configure routes.
6. The reusable `configure_ingress` validates inputs before any Azure access,
   disables public access/readbacks, writes main explicit allows + default Deny
   and **independent SCM Deny with no allows**, verifies the exact rules/readbacks,
   then enables public access and verifies again. Any write/readback/interruption
   failure attempts Disabled + readback, never restores a prior unsafe public
   state. `ingress_failed_rollback_unconfirmed` requires immediate operator
   inspection; it must not be reported as successfully disabled. Uncatchable
   process termination/service unavailability cannot guarantee rollback.
7. Confirm HTTPS from an allowed operator network, 403 from an independent
   nonallowlisted network, public SCM 403, and API/SQL still private. ARM readback
   is configuration proof, not a completed browser login. Private-endpoint traffic
   bypasses public IP restrictions by Azure design; preserve private access.

No live ingress helper invocation was made for this task because the CIDRs are
missing. The CLI deliberately requires private-state preflight; after a successful
enablement use a separately reviewed change procedure to replace the allowlist.
The lower-level operation is idempotent and always closes the site before updates.

## Validation

Final focused run: **104 passed, 2 dependency warnings**, covering admin ingress,
existing deployment safeguards and backend SQL authentication/authorization.
Python AST parsing and editor checks passed. The real module entrypoint without
CIDRs exits 2 before authentication. PowerShell's explicit parser API is blocked
by ConstrainedLanguage (confirmed exit 1); it is **not** claimed as a successful
PowerShell syntax validation. The editor reported no PowerShell errors.

Final live readback independently confirmed all three prior image references
unchanged; admin/API/SQL public Disabled; customer public Enabled; all SCM
defaults Deny with no allows. Fresh anonymous HTTPS probes of admin, admin SCM
and API returned 403. ACR run cmd was independently read back as Succeeded.
Only ACR build/tag-lock writes were performed; no site/network changes were made.

Focused unit tests cover missing/invalid input without Azure calls, IPv4/IPv6
special-range rejection, exact main/SCM rule verification, deny-before-enable
ordering, existing configuration preservation, timeout-after-enable rollback,
interruption rollback and explicit rollback failure reporting. Existing deployment
safety and backend SQL authorization tests are run separately. No public admin
or authenticated candidate browser E2E success is claimed.