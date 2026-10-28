# Approved bounded ingestion data-plane continuation — 2026-10-27 07:33 UTC

Current explicit user approval authorizes one fresh nonce/private ACI with the
existing ingestion UAMI only (no second API-identity probe). Purpose: actual MI
PostgreSQL SELECT, Log Analytics `print ingestion_probe=1`, and one metadata-list
page each for the existing host account's Blob/Queue/Table services. No storage
entity/message/blob content, DDL/DML, app initialization, seeding or write tests.
Read access is **not** proof of write/lease/table-creation permission.

ARM read metadata verified host account pocidstokenexfunc private endpoints:
Blob **10.240.3.6**, Queue **10.240.3.7**, Table **10.240.3.8**; workspace GUID
matches deployed settings; explicit ingestion client/object selection matches.
Existing unconditional Blob Data Owner, Queue/Table Data Contributor and workspace
Log Analytics Reader assignments are present. No new grants are authorized.

Reviewed dedicated `ingestion_dataplane` egress profile adds **only TCP443** to
those three **/32** private addresses and the **AzureMonitor** service tag to the
existing PG10.240.3.12/32:5432, Azure DNS53, IMDS80, Entra/ACR/image-layer HTTPS
rules. Deny-other-outbound remains; no Internet/AzureCloud catch-all. Ingress
remains VNet10.240/16 -> nonce-dedicated10.240.5/24 TCP19390 then deny-all.
No shared subnet/PE/DNS modification. New NSG/NAT/static-IP/subnet only after
fresh all-six-ID GET404 baseline and actual exact-four-Create validate/what-if.

Dedicated isolated pinned Linux image, native offline SDK transports, scanner,
fixed hash-bound entrypoint and existing strict ownership/finally/detached
deadline cleanup remain mandatory. One ingestion probe, no automatic retries,
10-minute probe including provisioning, 60-minute resource deadline (cleanup
starts eight minutes before deadline). Detached cleanup still depends on this
workstation remaining powered, connected and authenticated, as previously
disclosed; it is not a cloud-hosted reaper. JSON must be persisted before deletion
and exact-ID absence independently reconciled afterward. Host, image pins, catalog,
disabled timer and cutoff2026-10-27T06:06:02.045288+00:00 remain unchanged.

# FinOps private runner: exact access proposal — 2026-10-27

## Decision and authorization boundary

**APPROVED by the user, including both distinct managed-identity exposures;
execution stopped at preprovision gates, not an approval gate.** No runner,
subnet, NAT, public IP, identity attachment, role, image build, deployment
plan/apply or database operation was created/executed.
The separately approved state-storage rule was executed; see the
[state-access evidence](../gateway/validation/finops-state-access-20261027.json).
That rule does not authorize any application, SCM, APIM, PostgreSQL or VNet change.

### Approved execution continuation: actual result

Fresh read-only collection **01:25:16–01:25:48 UTC** checked the exact account,
subscription and tenant. The new `10.240.5.0/24` range fits the VNet, overlaps no
existing subnet and has 251 addresses after Azure reservations. Existing subnet
purposes remain unchanged. ACI is Registered and Southeast Asia is listed;
quota is 0/100 groups and 0/1000 Standard cores. This is not allocation proof.
The registry is Basic, Southeast Asia, without dedicated data endpoints; ACR
HTTPS alone would therefore not cover image layers. PostgreSQL remains public
Disabled/firewall count zero. State storage remains Deny with exactly the three
previously approved IPs; no further firewall operation ran.

**Concrete failed gates, not another request to approve this proposal:**

1. The approved NSG denies all inbound traffic. Current Microsoft ACI guidance
  says platform management port **19390** must be open and warns blocking it
  can prevent deployment/log access; the VNet limitations also discuss inbound
  access. Compatibility of the exact approved deny-all topology with the needed
  diagnostic/log channel was **not established**. No platform-port exception,
  blanket VNet/Internet rule, Firewall service or alternate host was added.
  This is a documented preprovision compatibility failure, **not an observed
  Azure allocation failure or proof that every deny-all deployment fails**.
  See [ACI platform firewall requirement](https://learn.microsoft.com/azure/container-instances/container-instances-egress-ip-address#configure-rules-on-the-firewall)
  and [VNet limitations](https://learn.microsoft.com/azure/container-instances/container-instances-virtual-network-concepts#other-limitations).
2. The previously missing NAT quote was found in successful same-session Retail
  API responses: public-cloud **Global** Standard Gateway **USD 0.045/hour**,
  Standard Data Processed **USD 0.045/GB**, not the US Government or StandardV2
  meters. Regional ACI and IPv4 rates below were reconfirmed. One combined hour
  of 1 vCPU/1.5 GiB plus NAT and IP is **USD 0.108895 fixed-resource subtotal**,
  plus NAT data and build/storage/transfer. The reproducible collector then
  stopped with a sanitized pricing-stage failure; a separate bounded diagnostic
  returned **HTTP 429**, without automatic retries. An **all-in estimate was not
  completed** and this subtotal is neither an all-in quote nor a billing cap.

No IaC generation/validate/what-if, ACR build, identity attachment, private SQL
probe or cleanup-controller installation followed these failed gates. The
60-minute combined resource lifetime, 10-minute probe deadline and independently
tested cleanup controller remain mandatory **before any future create**; they
were not installed or attested as passed here. The original approval is retained.
The next resolution is proof of a supported no-inbound ACI diagnostic path, or
an explicitly reviewed narrow platform-channel design change—not broad approval
to deploy some other topology. No service-port exception is assumed authorized.

Exact ownership nonce **2f75015b55d1**, all six reserved resource IDs and the
pre-PUT inventory journal were recorded. No PUT occurred. Independent ARM GETs
**01:29:00–01:29:01 UTC returned HTTP 404 for every reserved ID** (both sequential
groups, new subnet, NSG, NAT and IP). Created/deleted resources: **0/0**. No
cleanup was required or executed; absence is directly verified, not inferred
from an empty inventory. There is no newly provisioned NAT/IP left billing.
See [current exact-ID evidence](../gateway/validation/finops-runner-preflight-20261027.json).

Both private probe exits and aggregates are **null / not run**, not successful
zeros. Reviewed probe source SHA-256:
`105b265e97fc9f7a64caf2c0a9c07a55ca1c8da4d54bf82aa1e25254e5ae16b4`.
No immutable probe image was built or executed. Actual verification: **238
backend/contract tests passed** in 25.20 seconds, including the prior 207 and
31 new ownership/foreign-resource denial, exact create-only resource-plan,
single-MI/immutable-image/source-hash/entrypoint/output and price-selection
guards. Cleanup cases are **synthetic unit tests, not an external watchdog
deadline test**. [JUnit evidence](../gateway/validation/finops-runner-full-tests-20261027.xml).
Prior 103 UI results are retained, not rerun. Cutoff remains null; no replay,
database write, timer enablement or application release ran.

### Historical proposal evidence and original approval wording

The sections below preserve the original proposal and its unresolved-at-the-time
approval language. They do **not** rescind the explicit approval recorded above.
The original NAT-missing observation is superseded by the Global meter quote
above; no all-in or apply-ready claim follows from finding that quote.

Read-only collection began at 00:59:16 UTC; identity/network/quota metadata was
collected from 01:01 UTC, with storage/ACI quota/PostgreSQL firewall reconfirmed
at 01:09 UTC. CLI account `xv.puneet.devadiga@singtel.com`, subscription
`aa28274d-fea0-46d4-b9c8-30f3ef0a0e52` and tenant
`beb276ac-6e9f-498e-8e31-019ee666decd` were checked before the storage operation.
All proposals below are in resource group `IDS-TOKEN-EXCHANGE-POC`, region
`southeastasia`. No alternative subscription/region is implicitly approved.

## Existing network: what is and is not usable

Define the exact existing VNet ID **V** as:

`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.Network/virtualNetworks/poc-ids-token-ex-vnet`

| Existing subnet ID (append suffix to V) | Read-back metadata | Decision |
| --- | --- | --- |
| `/subnets/poc-ids-token-ex-app-service-integration` | `10.240.4.0/24`, delegated `Microsoft.Web/serverFarms`, existing integration NSG | Not a VM/ACI runner subnet; do not change delegation or NSG. |
| `/subnets/poc-ids-token-ex-private-endpoints` | `10.240.3.0/24`, no delegation/NSG/NAT/route table; nine private endpoints | Technically an undelegated subnet can host a VM NIC, but mixing a privileged diagnostic host into this shared endpoint segment is **not selected/approved**. ACI cannot share it with endpoints. |
| `/subnets/poc-ids-token-ex-appgw` | `10.240.1.0/24`, no delegation/NSG/NAT/route table, no listed IP configurations | Empty is not unowned: main Terraform reserves it for Application Gateway. No silent reassignment to a runner; App Gateway requires a dedicated subnet. |

All three report `defaultOutboundAccess=true`, but no NAT gateway or route table
exists in this RG. This is **not a verified explicit egress path** for a new
VM's agent/downloads or a supported ACI NAT configuration. No subnet property,
association, delegation, route or DNS setting was changed. No existing VM or ACI
was found. The historical operator root is a different-subscription, undeployed
design and must not be applied/imported here.

Existing private DNS is Azure-provided (VNet DNS-server list empty).
`privatelink.postgres.database.azure.com` has a Completed, registration-disabled
link named `poc-ids-token-ex-postgres` to **V**. Its `poc-ids-token-ex-pg` A record
is `10.240.3.12`. The probe must still resolve and validate that address **on the
runner**, retain the server hostname for TLS `verify-full`, and reject any address
outside `10.240.3.0/24`. ARM DNS metadata is not an authenticated DB connection.
PostgreSQL public access remains Disabled and firewall-rule count remains zero.

## Capacity and actual price lookups

- Compute regional usage/limit: **0/350 vCPUs**; BS and Basv2 family usage/limit:
  **0/350 each**. Quota is sufficient but is not SKU availability.
- Subscription-scoped Compute SKU response has no next page. `Standard_B1s`
  (1 vCPU/1 GiB) and `Standard_B2ats_v2` (2 vCPU/1 GiB) both have **Location
  NotAvailableForSubscription** for Southeast Asia. A bounded search of B-series
  and D2/F2 candidates with at most 2 vCPUs/8 GiB found no candidate without a
  location restriction. No quota-increase, SKU registration or region change ran.
- Retail Prices API, verified TLS, queried this date: Linux VM PAYG B1s
  **USD 0.0132/hour**; B2ats v2 **USD 0.0118/hour** for the *Virtual Machines
  Basv2 Series* product. The separate Cloud Services meter is not a VM quote.
  B1s is also listed as end-of-life by current Microsoft documentation. These
  are unavailable comparison candidates, **not deployment selections**; disk
  and egress charges would be additional.
- ACI Southeast Asia regional usage/limit: **0/100 container groups**, **0/1000
  Standard cores**. This supports a 1-vCPU proposal, not a capacity guarantee.
- Standard non-Windows/non-GPU ACI retail meters: **USD 0.0506/vCPU-hour** and
  **USD 0.00553/GiB-hour**. For one group at a time, 1 vCPU/1.5 GiB, and at most
  one combined running hour across both probes, the compute-only estimate is
  **USD 0.058895**. Meter units and product were checked; no reserved/Spot price
  was substituted.
- The exact-region `NAT Gateway` product-name lookup returned no meters. A broader
  Virtual Network lookup verified the Standard IPv4 Static Public IP meter at
  **USD 0.005/hour** (not Basic/Global/prefix). NAT gateway-hour/data-processing,
  image transfer and other egress must still be priced before approval.
  **No all-in price/cost ceiling is
  asserted.** A lifetime limit is not a billing cap, and deleting only a container
  does not stop NAT/public-IP billing. No cost-bearing resource exists from this task.

## Concrete minimal separate network change (NOT applied)

**Preferred conditional candidate:** two sequential Linux ACI jobs, not a
persistent CI/GitHub runner. This avoids an OS disk, SSH credential and an
unavailable VM SKU. It cannot run within the current no-subnet-mutation boundary.

Proposed resource prefix: `poc-ids-token-ex-finops-probe-RUNID`, where RUNID is a
fresh 12-hex ownership nonce recorded before any PUT; exact generated names/IDs
must be bound into the later reviewed plan. Existing-name collisions fail closed.

1. **New subnet only**, proposed exact ID
   **V** + `/subnets/poc-ids-token-ex-finops-probe`, CIDR `10.240.5.0/24`,
   delegated only to `Microsoft.ContainerInstance/containerGroups`, explicit
   default outbound disabled. This subnet does **not** currently exist. The CIDR
   does not overlap the three observed subnets, but fresh collision/address-use
   and network-owner review remain required. Do not edit any existing subnet.
2. One owned Standard NAT gateway and one owned Standard static outbound IPv4;
   associate only with the **new** subnet. The IP is on NAT, never on a runner.
   This is a new outbound egress facility and expense requiring separate approval,
   not an extension of the state IP approval. No inbound service/public runner IP.
3. One owned subnet NSG: deny all inbound; allow outbound TCP 5432 only to
   `10.240.3.12/32`, UDP/TCP 53 only to Azure DNS, and the reviewed platform/MI,
   Entra, ACR/image-layer HTTPS dependencies; deny other outbound. Exact service
   tags/destinations and ACI platform requirements must be resolved in the actual
   template/what-if. No blanket VNet access or silent Internet allow. NAT is not
   a domain firewall; do not claim these dependencies are already tested.
4. At most one container group at a time, restart Never, no published ports or
   listening server, no volume/log-workspace/secret mounts, no registry password.
   Use an existing verified immutable ACR digest with the probe dependencies and
   a hash-bound reviewed probe entrypoint, **not** the normal application entrypoint
   that might initialize/seed data. Nothing was built or uploaded here. Packaging,
   dependency checks and entrypoint binding precede any execution authorization.

An existing-subnet VM is not a fallback to try blindly. Its NIC would need an owned
deny-all-inbound NIC NSG, no public IP/password/SSH, an explicitly available SKU,
verified outbound agent/HTTPS access, and separately reviewed restricted Run Command.
The checked small SKUs are unavailable and the existing subnet-purpose/egress
decisions are unresolved. If a VM is later selected, review its image/Trusted Launch,
disk deletion and one-time public-key generation in memory (discard private key;
never print/persist it); no credential was generated in this proposal.

## Identity scope decision and audit (no attachment performed)

Existing identity resource IDs use this prefix:

`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ManagedIdentity/userAssignedIdentities/`

| Identity suffix / purpose | Client ID / object ID | Existing exposure when attached |
| --- | --- | --- |
| `poc-ids-token-ex-ingestion-identity`: read-only snapshot as ingester | `e1d25c87-9df1-4225-9744-ce22121cf462` / `edbfc3e2-a8e5-4652-9bb0-311233756d42` | Blob Data Owner, Queue/Table Data Contributor at `pocidstokenexfunc`; Log Analytics Reader at `poc-ids-token-ex-logs`; Metrics Publisher at Insights; AcrPull at `pocidstokenexacr`; Event Hubs Data Receiver at `token-usage`. |
| `poc-ids-token-ex-api-identity`: separate read-only snapshot as API | `f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1` / `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` | Key Vault Secrets User at `pocidstokenexkv`; custom APIM subscription-manager at `poc-ids-token-ex-apim`; Table Data Contributor; Log Analytics Reader; Metrics Publisher; AcrPull at the same respective resources. |

**These privilege sets are not equal.** The API custom role explicitly includes
subscription write, listSecrets and primary/secondary-key regeneration, not merely
read. The read-only probe will not invoke them, but attaching that MI exposes all
its token audiences/permissions to code on the runner. The ingester can also write
storage; a read-only SQL transaction does not reduce its Azure privileges. There
is no safe claim that an attached runtime MI becomes globally read-only.

Proposed scope decision: an isolated ingester-only group first; delete and verify
absent before any separate API-only group. Never attach both together, invent a
new role or reuse the human operator token for DB proof. **Because the roles
differ, the second identity attachment requires explicit review of its distinct
privilege exposure, not an automatic identical-privilege assumption.** Both
already have AcrPull; no new image-pull assignment is proposed. DB grants remain
unverified. Ingestion's absent DB setting means a constructed reviewed destination
would prove this MI's readiness for that target, not a currently configured timer.

The existing operator has subscription Contributor. ARM permissions readback at
each MI reports `Microsoft.ManagedIdentity/userAssignedIdentities/assign/action`
allowed; RG readback reports VM write/delete, both Run Command actions, disk
write/delete, NIC/NSG write/delete and subnet join allowed. This is read-only
permission metadata, not a successful create or exhaustive deny/policy evaluation.
No role/identity/federation change was made or is required by this proposal.

Additional RG permissions readback confirmed container-group read/write/delete/log
read, subnet read/write/delete/join, NAT and public-IP read/write/delete/join,
and ARM deployment validate/what-if actions allowed by the existing permissions.
This verifies the required existing action metadata without creating a resource;
it does not authorize network changes or establish a successful what-if/policy pass.
Recheck those actions plus NIC/NSG association permissions against the exact saved
plan before execution. No new role grant is authorized if any action is missing.
Restrict resource IDs to
the proposed owned objects and the existing read/join/assign scopes. For a VM,
Run Command is root-equivalent: review the exact nonsecret script/hash, restrict
existing operator use, and never dump the host environment/IMDS credentials.

## Probe, lifetime, evidence and cleanup contract

- Reuse [finops_private_probe.py](../scripts/deployment/finops_private_probe.py).
  AIFLUX DB destination is handled in memory, never dumped. Selected MI client,
  tenant/object/audience claims must match, and PostgreSQL validates the token;
  no CLI/operator/password fallback. No MI token is sent in ARM/script payloads.
- Read-only repeatable snapshot: current DB/schema/search path, no runtime
  elevation/DDL/ownership, effective SELECT and DML **catalog flags only**, aggregate
  row/input/output/measured/missing/price coverage, checkpoint and ownership-match
  counts/dates. Timeouts and unconditional rollback apply. No permission writes,
  schema migration, row IDs, prompts, secrets, DSN or raw driver output.
- Proposed **60-minute maximum total resource lifetime**, **10-minute maximum per
  probe**, bounded deployment deadline, no automated retries/restarts. An external
  cleanup deadline is mandatory because ACI termination does not delete networking.
  Cleanup implementation/deadline is not yet installed and must be tested before
  provisioning. No deployment until the all-in cost is reviewed and bounded.
- Before any create, record inventory baseline, exact names/IDs and owner nonce;
  capture after each attempt and on failure. Attribution categories are evidence,
  not deletion authority: never delete unverified/orphaned or preexisting resources.
- Finally on success/failure/timeout: delete only ownership-proven container group(s),
  then the owned new subnet/NSG and NAT/IP in dependency-safe order. Check tags and
  the subnet's exact CIDR/delegation/NAT ownership journal; refuse a changed object.
  Independently GET each ID to verify absent. No deletion of VNet, DNS, original
  subnets, MI, registry artifacts, app resources or storage rule. VM alternative
  additionally deletes its owned disk/NIC/extensions; no sensitive files/logs or
  credentials are to be written in the first place. Escalate failed cleanup with
  owned IDs and continuing costs, never claim guaranteed cleanup from a finally alone.
- Sanitized result only. Snapshot/cutoff/ownership failures block recovery.
  [finops_replay.py](../scripts/deployment/finops_replay.py) stays **dry-run only**;
  activation cutoff is null and no replay ran in this turn. No timer enablement,
  backfill, DB write or image/app release follows automatically. Those require
  a separate factual activation/configuration and exact saved-plan workflow.

## Remaining approval/evidence

Review the **new dedicated subnet + outbound NAT/IP + NSG** change and separate
identity-exposure decisions above, or supply an already authorized suitable private
host. Resolve NAT pricing, image/entrypoint/dependency
binding, policy checks and tested cleanup before a fresh exact deployment plan.
No runner topology is represented as Validated/Approved-for-apply here. The old
SQL runner's destructive migration/seed entrypoint must not be reused.

References: [ACI VNet/NAT requirements](https://learn.microsoft.com/azure/container-instances/container-instances-virtual-network-concepts),
[Application Gateway subnet dedication](https://learn.microsoft.com/azure/application-gateway/configuration-infrastructure),
[Run Command restrictions](https://learn.microsoft.com/azure/virtual-machines/linux/run-command),
[Bv1 lifecycle/specifications](https://learn.microsoft.com/azure/virtual-machines/sizes/general-purpose/bv1-series),
[Basv2 specifications](https://learn.microsoft.com/azure/virtual-machines/sizes/general-purpose/basv2-series),
[Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices).