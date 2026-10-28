# Live deployment readiness — 2026-10-24

## Admin-only redirect release — current authorized execution

Current release: local-20261023t183934z-bed4dd3bfdc3. Only runtime correction:
admin nginx absolute_redirect off, retaining / root302 to /admin/ behind public
HTTPS termination without exposing container port8080. Shared regression test
retained and corrected to use resolve(process.cwd(), ...) after the first ACR
attempt actually reproduced Vitest ERR_INVALID_URL_SCHEME with import.meta.url.
Failed candidate local-20261023t183641z-74427a35c663 never deployed/published.

Actual current validation2026-10-23T18:47:45.353310+00:00 passed36safety tests
(18original+18admin-only), full source inventory/hash, ACR cm12 typechecks/UI
111tests/12files/both builds, and cm13 admin-only runtime build plus rendered
nginx -t. No customer runtime image rebuilt. New approved admin digest:
sha256:8ff02fb1d3b0299dc2d0255e5ba202a7a721221a479f7a7d29d5a5b23c7cd7b0.
SourceHash:bed4dd3bfdc3a87a15f8636ad2c85a9984e482cc137748f10a136a9b1396e0a3.

Pinned Terraform init/fmt/validate, remote backend70addresses/defaultworkspace,
template/JSON scan, exact-registry admin UAMI AcrPull and policy review passed.
Fresh validation plan permits exactly one admin image-only update. Full current
validation proof binds helpers/tests/TF/lockfile/approved build evidence hashes.
Original PowerShell workflow progress write reproduced ConstrainedLanguage
UTF8Encoding failure; existing faithful Python transition implementation used
sequentially only after actual checks. No Group Policy bypass or fake success.
Current workflow through UpdateStatus complete; scoped plan Validated before
invoking azure-deploy's existing-resource pure Terraform exact-saved-plan recipe.
Inventory baseline73resources. Actual apply and live activation results follow
only after they are independently captured; validation alone is not deployment.

Fresh baseline differs from older historical reports: admin main defaultDeny
with existing MyIP167.103.66.93/32, independent SCM defaultAllow. Preserve both;
SCMAllow remains a separate known security issue. API private, JWTResolved,
PostgreSQL publicDisabled/zero firewall rules, vault defaultDeny/currenttwoIPs,
all identities/routing/roles and customer/API/ingestion images must remain equal.
User-edited Terraform override untouched, SHA256
c254e1170afd3eb8154114ba8e24f90f6d55328c93d86acc9c3bd8aff13c621c.
No secret values/passwords read, real login attempted, browser password/storage
inspected, or credential/reseed/RBAC/network/SCM/routing/worker/gateway write.

## Superseding actual deployment — 2026-10-23 18:13 UTC (02:13 Singapore)

**Portal-only deployment completed and verified.** Earlier blocked checkpoints
below are historical. Existing published release local-20261023t173114z-571d75366033
was reused; no rebuild. Current validation passed 18 safety tests, 65 source hashes,
fresh successful ACR cmw/cmx/cmy evidence and exact manifest digests, pinned
Terraform init/fmt/validate and exact-two-image guard. Existing Python workflow
adaptation completed all validation steps after reproducing the precise CLM
UTF8Encoding failure; no PowerShell policy change or fake validation status.

Only override addition: site_config[0].vnet_route_all_enabled lifecycle ignore
preserves current live routing; all existing user-edited entries retained.
The unchanged guard still rejects any routing change. New apply mode plans into
an operator/SYSTEM-only temporary directory, inspects that plan, verifies current
evidence and source hashes plus immediate full live-baseline equality, then applies
that exact plan before automatic deletion. Terraform actual result:
**0 added, 2 changed, 0 destroyed.** Saved-plan SHA256:
b2fb800e2e88e7c55d7a507ec0d70ff5ab7147d5c4444500b312aac48ae9da2e.

Verified live pins:
- Admin: sha256:a7e13ae5e89dc5bd1c5380213ba0beb7a8cef945d1d5c64a1188734c95d2d31f.
- Customer: sha256:d4891893d8d145acce36633eb7fb5029110a932f1130ee3da2bbcc1c7adbf242.

Complete security snapshot equals pre-apply except the two portal images. API
remains private, JWT Resolved; API/ingestion images, all observed routing, identities,
ingress/SCM (including existing admin Allow), role assignments, vault ACLs and
PostgreSQL public Disabled/zero rules unchanged. No worker/gateway activation,
secrets, network write or extra restart. Inventory:73 baseline,0 new resources.

| Probe round | Admin health / me / invalid login | Customer health / me / invalid login |
| --- | --- | --- |
| 18:08:03–18:08:11Z, activation incomplete | 200 / 502 / 502 | 200 / 502 / 502 |
| 18:13:42–18:13:48Z, after startup | 200 / 401 JSON / 401 JSON | 200 / 401 JSON / 401 JSON |

Both rounds retained in release deploy-result evidence; verification.json is the
final round. Platform logs show customer startup complete at18:09:49–18:09:56Z,
after the first probes. Private API via existing authorized admin SCM independently
returned health200, ready200, me401 at18:09:52–18:10:13Z. No activation fix/write
was needed. Initial old-bundle browser502 was recorded, not counted as success.
Final isolated browser test: actual synthetic login401 displays invalid credentials;
browser-local mocked502 displays service temporarily unavailable (not a password
rejection). No real-password test or successful password login is claimed.

## Portal rollout checkpoint — 2026-10-23T17:44:47Z (01:44 Singapore)

**Authorized rollout attempted; blocked, not deployed.** This supersedes the
earlier statement below that no replacement images had been built. The successful
approved ACR build was reused without rebuilding:
`local-20261023t173114z-571d75366033` (validation cmw, admin cmx, customer cmy).
Fresh live manifests match admin
`sha256:a7e13ae5e89dc5bd1c5380213ba0beb7a8cef945d1d5c64a1188734c95d2d31f`
and customer
`sha256:d4891893d8d145acce36633eb7fb5029110a932f1130ee3da2bbcc1c7adbf242`;
all 65 packaged source hashes match. Ten focused guard tests passed.

Two deployment blockers remain:

1. Required azure-validate workflow fails its progress write with
  `CannotCreateTypeConstrainedLanguage` at UTF8Encoding construction. No policy
  bypass or manual Validated claim was made.
2. Fresh Terraform init/fmt/validate reached plan inspection, but the exact
  two-portal guard rejected additional `vnet_route_all_enabled` changes alongside
  `application_stack`. No apply ran. The temporary plan was automatically deleted;
  the current helper has no apply action. User-edited override remains unchanged.

Fresh operator/tenant/subscription identity checks passed. API remains private,
PostgreSQL public Disabled/zero firewall rules, JWT reference Resolved and admin
SCM default Allow unchanged (known security finding, not fixed here). Neither new
image is live: admin remains `sha256:ed5db6bc445929322b4e7bfe23c4908953e4d055c94df3ff12c8eb67dc6f214f`,
customer remains `sha256:5728330a052d33cc4b5a045617eaab9be52a371b3abf73ad74062ab963bceb14`.
Both portal /healthz probes return 200; both /api/me probes still return 502.
Customer root returns 200; admin root encountered URLError, not verified 200.
Synthetic-login and post-rollout canary tests remain pending. No real-password
login was attempted or claimed. No Azure configuration changes, secret reads,
network openings, password resets, reseeding or restarts were performed.

Actual sanitized results are retained in the release's blocked-checkpoint evidence;
the deployment plan records the commands and rejected-plan timestamp. Resume only
with policy-compliant validation completion and a strictly image-only saved plan.

## Scope and evidence time

Fresh read-only collection ran **2026-10-23 16:48:09–17:04:17 UTC** (2026-10-24
00:48–01:04 Singapore time). The host clock and Azure HTTP Date agree on these UTC
timestamps; the report filename uses the requested local date.

- Subscription: aa28274d-fea0-46d4-b9c8-30f3ef0a0e52.
- Tenant: beb276ac-6e9f-498e-8e31-019ee666decd.
- Resource group: IDS-TOKEN-EXCHANGE-POC.
- Token tenant and operator object dd928302-055b-4516-9b8e-b06ae823057b verified.
- No Azure configuration/RBAC/network writes, builds, restarts, secret-value reads,
  publishing-credential requests, password submissions, or Terraform operations.
- Local diagnostic scripts, sanitized JSON evidence, and VS Code tasks were added.
  SCM command POSTs executed only fixed read-only configuration/network probes.

## Customer login 502 — investigation first

**High-confidence cause: portal nginx upstream certificate-chain verification
depth is too shallow for the API's currently served certificate chain.**
This is supported by a reproduced TLS failure, not inferred from HTTP 502 alone.
Direct nginx request stderr and rendered application-container configuration were
not available under existing access/logging; therefore this is not claimed as a
captured nginx error or a verified deployed fix.

| Current observation | Evidence |
| --- | --- |
| Customer `/` and `/healthz` return 200; `/api/me` and GET `/api/auth/login` return nginx HTML 502 | 16:48:09 UTC; final `/api/me` still 502 at 17:04:17 UTC |
| Customer and API state Running, instance READY; health metric 100% | Fresh ARM/instance/metrics reads; static liveness does not test the proxy |
| API JWT Key Vault reference Resolved | Fresh reference-status metadata; no secret retrieved |
| API public network access Disabled | Expected private API topology, not itself an error |
| API private endpoint Approved, correct sites target, NIC 10.240.3.9 | Correct private DNS zone group; API and SCM A records match NIC |
| Private DNS zone linked to integration VNet; default Azure DNS | Linked state Completed; no custom DNS servers or attached UDR |
| Customer's expanded CSP contains `https://poc-ids-token-ex-api.azurewebsites.net` without explicit port | Live header expands the same `CONTROL_ORIGIN` variable used in released `proxy_pass`; direct customer env read blocked |
| Authorized admin SCM resolves API to 10.240.3.9 | Actual in-network DNS, not workstation public DNS |
| Private API GET `/health` 200 and `/ready` 200 | 16:53:44–45 UTC, uvicorn JSON responses |
| Private API GET `/api/me` 401, “Access token required” | 16:54:00 UTC; expected anonymous response, no password or token supplied |
| OpenSSL verification with depth 1 fails | `depth=2 ... CN = Microsoft TLS RSA Root G2`, `verify error:num=22:certificate chain too long` |
| OpenSSL verification with depth 5 succeeds | TLS 1.3, `Verification: OK`; peer `*.azurewebsites.net` |
| Separate hostname verification succeeds | Correct API hostname verified against `*.azurewebsites.net` |
| Both released portal templates enable `proxy_ssl_verify on` but omit `proxy_ssl_verify_depth` | Exact archived release context inspected; nginx documented default is 1 |

The private API `/ready` implementation executes `SELECT 1` and SELECTs against
every application model table. Its live 200 provides current runtime database
connectivity/table-read evidence, beyond ARM existence or historical bootstrap
logs. It does not prove seeded passwords, effective no-DDL permissions, or worker
database access. No database mutations were performed by these readiness checks.

### Logging/access limitations and rejected explanations

- AppLens was consulted first. Its initial customer “stopped” diagnosis cited
  15:48:52 UTC; current Running/READY and live 200 responses supersede that stale
  instance explanation. API startup success is also reported.
- AppLens queried again for 16:48–16:54 UTC found insufficient application logs.
  Customer application/HTTP logging is Off; ARM container logs contain platform
  lifecycle events, not the required request-time nginx TLS stderr.
- Customer SCM VFS and read-only command requests return **403**. Access was not
  widened. Existing admin SCM Entra access works, but that is a separate SCM
  container, not proof of access to the customer nginx filesystem.
- Admin SCM nginx-path request returns 404. Available admin logs contain platform
  events, not corroborating nginx request errors. No arbitrary filesystem scan.
- No evidence supports the proposed “SNI includes :443” cause: the rendered origin
  has no explicit port and explicit hostname verification passes. Nginx documents
  its default SSL name as the host portion of `proxy_pass`.
- `clientCertMode=Required` is misleading alone: fresh reads show
  `clientCertEnabled=false` on all three web apps. AppLens' suggestion that the
  expected anonymous 401 meant missing mTLS certificates is not supported.

### Recommended follow-up — not applied

Set an explicit adequate `proxy_ssl_verify_depth` (5 passed the live probe) in
**both** portal proxy templates, retaining certificate verification, trusted CAs,
and correct hostname/SNI. Rebuild immutable portal images and use the separately
approved guarded rollout. Then require proxied anonymous `/api/me` to return the
same API 401 rather than nginx 502, before any optional user-run password test.
The UI must distinguish infrastructure 502/503 from invalid credentials; that
local UI change is outside this read-only investigation.

## Deployment completeness

### Local remediation prepared after investigation — not deployed

- Both portal nginx templates now explicitly set `proxy_ssl_verify_depth 5`,
  retaining certificate verification, hostname/SNI and the trusted CA bundle.
- Local UI error handling now labels HTTP 5xx as service unavailability, not
  invalid credentials; 401 retains the generic password-rejection message.
- Added regression tests for HTTP error mapping and TLS policy in both templates.
- The existing portal validation/build task was attempted, but Windows **Group
  Policy blocked the TypeScript compiler invocation**. Type checking therefore
  did not complete, and that task did not reach tests or builds. No workaround
  around the corporate policy was attempted. Relevant editor diagnostics are
  clean, but this is not a substitute for executed tests/builds.
- No runtime image was rebuilt or deployed. Complete validation on an approved
  runner before guarded rollout, then verify `/api/me` returns 401 via each portal
  and allow the user to test their password privately. Keep API/private services
  closed; do not enable workers or gateway release as part of this proxy fix.

Inventory returned **70 resources**, including four sites, one Linux App Service
plan, six user-assigned identities, nine approved private endpoints, eight private
DNS zones and eight VNet links. Existence is not end-to-end operational acceptance.

| Resource/service | Live finding | Readiness classification |
| --- | --- | --- |
| poc-ids-token-ex-customer | Running/READY; latest released digest; port 8080 template; UI/liveness 200; API proxy 502 | **Deployed, proxy broken** |
| poc-ids-token-ex-admin | Running/READY; latest released digest; SCM confirms configured port 8080; liveness 200, `/api/me` 502 | **Deployed, same proxy symptom; ingress risk below** |
| poc-ids-token-ex-api | Running/READY; latest released digest; /health and /ready 200 from private network; anonymous API 401 | **Operational for these read-only checks**, no password-login acceptance |
| poc-ids-token-ex-apps-plan | Linux B1, capacity 1, Ready, not zone-redundant | Provisioned; not HA |
| poc-ids-token-ex-ingestion | Disabled, enabled=false, no instances; PYTHON\|3.11 rather than released container | **Exists but worker image not deployed/active**; disabled flags intentional |
| poc-ids-token-ex-control-plane | Exact ARM GET/functions GET 404; absent from four-site inventory | **Separate Function resource missing**; publication disabled by design, not a login dependency |
| pocidstokenexacr | Succeeded; admin and anonymous access false; five immutable release manifests independently read and match | **All five images published; only three web images deployed** |
| poc-ids-token-ex-pg / turnstile | Server Ready; database present; public Disabled; zero firewall rules; Entra enabled/password auth disabled; PE 10.240.3.12 Approved | **Contained, live API readiness passes table reads** |
| pocidstokenexkv | Succeeded; RBAC enabled; PE 10.240.3.4 Approved; JWT reference Resolved | Runtime reference healthy; public Enabled/ACL Deny with two exact-IP exceptions |
| pocidstokenexfunc | Succeeded; public Disabled; shared keys disabled; Blob/Queue/Table PEs Approved | Storage exists; ModelRoutes and TurnstileLedger tables present; no processing evidence |
| poc-ids-token-ex-eh / token-usage | Succeeded/Active, four partitions, seven-day retention; public Disabled; local auth disabled; PE 10.240.3.11 Approved | Infrastructure present; **no active ingestion/consumer proof** |
| poc-ids-token-ex-apim | BasicV2 Succeeded, public Enabled, virtualNetworkType None | **Not a released working gateway**: product aiflux notPublished; native validation pending API; dev API points to disabled.invalid |
| poc-ids-token-ex-logs / poc-ids-token-ex-insights | Succeeded, Insights links to expected workspace | Provisioned; not proof of request/worker telemetry ingestion |
| poc-ids-token-ex-sql / aiflux | Legacy SQL retained and private endpoint Approved | Retained legacy resource, not active PostgreSQL runtime proof |
| Foundry/safety and existing model accounts | Five Cognitive Services accounts present; queried deployments Succeeded where present | Infrastructure/model inventory only; no inference requests or costs generated |
| Public edge / MISE sidecar / release and provisioning engines | No new edge resource provisioned; no sidecar acceptance claimed; unsupported engines are documented unavailable | Do not label optional/gated capabilities as deployed or silently enable them |

The exact 11 central handoff grants are all currently visible at matching or
ancestor scopes: control-plane ACR/metrics/storage grants, ingestion ACR/Event Hub
Receiver, API vault/table, and gateway table/Event Hub Sender. All three web-app
identities have visible ACR pull grants. ARM RBAC visibility is not proof of
runtime worker execution or PostgreSQL SQL grants. Worker publication would still
need separate approved APIM fragment permissions and runtime-write policy.

The latest release is `local-20261023t151159z-c96420fbd5f5`, not earlier release
tables. API, admin and customer configured digests exactly match this release.
Ingestion and control-plane-function manifests exist but are not active runtimes.
Release flags explicitly keep ingestion, ingestion timer and publication worker
false and legacy MSSQL retention true. The absent separate Function is a concrete
full-platform deployment gap, not evidence of an accidental login dependency.

## Separate security and connectivity findings — no remediation authorized

1. **Admin main and SCM ingress allow Any/default Allow**, independently of the
   customer 502. The earlier exact-IP/default-Deny posture is not current. SCM
   still requires authentication; network Allow does not remove that requirement.
   The reviewed runtime override ignores ingress fields, so a guarded image-only
   rollout must not be represented as restoring ingress containment.
2. Customer SCM remains independent default Deny. API public access remains
   Disabled. Do not open either to collect logs.
3. Integration NSG explicitly allows TCP 443/1433/5432 to private-endpoint subnet,
   then denies other private-data ports. TCP **5671/5672 is not allowed**: future
   AMQP consumers would need reviewed transport/network design (AMQP-over-WebSockets
   443 is a distinct option). This does not explain HTTPS portal 502.
4. APIM currently has no VNet integration while Event Hubs/storage are private.
   Sender/table RBAC alone does not prove APIM data-plane connectivity. Do not
   claim working Event Hub telemetry/ledger access from these assignments.

## Evidence retained locally

Sanitized ignored evidence contains UTC collection timestamps, status-only probes,
resource IDs/configuration allowlists, certificate diagnostic output and grant
comparisons. No appsettings/list, secret data-plane retrieval, keys, publishing
profiles or password tests were used. Raw platform logs remained in memory.
Metric queries that returned 400/529 were not counted as successful evidence;
separate health metrics and customer 5xx metrics succeeded. Initial SCM curl
format-string quoting errors were replaced with clean fixed GET probes before
claiming status results. No end-to-end login success or deployed remediation is
claimed.