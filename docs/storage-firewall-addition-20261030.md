# Exact storage firewall addition — 2026-10-30

**Verified successful at 2026-10-30T00:44:48.310869Z.** The current user's
explicit authorization covered only adding IPv4 Allow item **167.103.67.80**
to the existing **projpoctokenex** storage account. It did not authorize Auto,
another diagnostic window, deployment, Terraform or any other cloud write.

## Actual scope and result

- Subscription: `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`.
- Tenant: `beb276ac-6e9f-498e-8e31-019ee666decd`.
- Resource group: **IDS-TOKEN-EXCHANGE-POC**.
- Actual native CLI single-IP operation: **one PATCH reached Azure**, returning
  **HTTP200 at 00:44:24.849023 UTC**, request
  `8ed1ffde-29a0-449b-b518-2969fc721fbb`; CLI exit **0**, empty stdout/stderr.
- A permanent, exclusive, fsynced
  [wire intent](../.deployment/storage-firewall-167-103-67-80-20261030/wire-intent.json)
  preceded the request. The transport allowed only the exact account PATCH and
  exact approved network-ACL body. SDK retry budgets were zero; the exclusive
  intent also prevents a second mutation from reaching the transport.
- Fresh whole-account reads before and immediately before the request, and
  independently afterward, passed the full configuration comparison. The only
  actual configuration delta is the appended Allow item **167.103.67.80**.
  No metadata delta was observed. Account ETag was absent; the CLI's fresh
  GET/merge is **not atomic CAS**. No concurrent delta was observed, but this
  does not guarantee exclusion of an external writer during that interval.

## Exact preservation

The original Allow rules **167.103.66.93**, **167.103.66.248**,
**167.103.65.36** and **167.103.63.12** remain unchanged. The resulting list has
exactly five items, including the new exact IP; no CIDR or broad rule was added.

Default action **Deny**, bypass **AzureServices**, public network access
**Enabled**, shared-key setting, empty IPv6/VNet/resource-access arrays, and
every remaining returned account property were preserved. No key was read or
used. The existing corporate CA/environment was used with strict TLS, and the
subscription plus token tenant/operator identity were verified internally.

## Authenticated state metadata only

The existing state blob received **HEAD only**, authenticated with Entra ID:

- **HTTP200 at 2026-10-30T00:44:44.863409Z**.
- Request ID: `61627688-801e-0026-2e07-683c60000000`.
- ETag: `"0x8DF35B313448682"`; length **314338** bytes.
- Last modified: **2026-10-29 11:52:14 GMT**.
- Lease: **unlocked / available**.

No state body was downloaded. No initialization, plan, apply, lease operation,
RBAC change, build, Send, Auto activation or other cloud mutation was run.
This restores the observed backend access; it does not prove Auto acceptance
or resolve the remaining application work.

## Retained pre-wire failures and sources

Two deterministic local failures occurred **before any mutation reached Azure**:

1. The token command rejected simultaneous subscription/tenant arguments. The
   isolated continuation used the explicit subscription and independently
   checked returned token tenant/operator claims. No token was emitted.
2. The strict transport body comparison rejected the installed CLI serializer's
   omission of the observed empty IPv6 array. An offline installed-model audit
   proved that exact omission. A separate continuation accepted only omission of
   that **empty** array, without changing the installed CLI or its fresh merge.
   Actual post-read IPv6 configuration remained exactly unchanged.

Neither was a silent/ambiguous wire result. Both original helpers and their
receipts remain untouched. No mutation was replayed after reaching Azure.
Eight offline preservation checks passed; editor diagnostics reported no errors
in the new helpers. Verification preserved **484 retained files**, including
all **173 historical bound source files**, historical deployment Python helpers
and intent receipts. Existing bound source files were not edited or restamped.

The storage skill, Azure general best practices and CLI guidance were consulted.
The CLI-extension guidance service returned HTTP403; the official Azure MCP
troubleshooting guide was consulted and the existing installed CLI was used.

## Evidence

- [Complete verified result](../.deployment/storage-firewall-167-103-67-80-20261030/result.json)
- [Full before account](../.deployment/storage-firewall-167-103-67-80-20261030/before.json)
- [Fresh pre-wire account](../.deployment/storage-firewall-167-103-67-80-20261030/fresh-prewire-serialization.json)
- [Independent after account](../.deployment/storage-firewall-167-103-67-80-20261030/independent-after.json)
- [Final account read](../.deployment/storage-firewall-167-103-67-80-20261030/final-account.json)
- [Actual mutation response](../.deployment/storage-firewall-167-103-67-80-20261030/wire-response.json)
- [Authenticated HEAD metadata](../.deployment/storage-firewall-167-103-67-80-20261030/blob-head.json)
- [Original retained-file hashes](../.deployment/storage-firewall-167-103-67-80-20261030/retained-hashes.json)

## Final offline integrity and quiescence

The [independent final offline audit](../.deployment/storage-firewall-167-103-67-80-20261030/final-offline-audit.json)
passed at **2026-10-30T00:45:48.879899Z**. Removing only the exact newly appended
IP item from both after-read account objects yielded the original raw account
object byte-value-equivalent at every field, with **no metadata exclusions
needed**. It rechecked all **484 retained files**, including **173 bound sources**
and **168 historical intent files**, plus the original and new continuation
source bindings. It retained SHA256 hashes of all 21 preceding evidence files.
Only the audit itself was running during its process inspection.

After the audit exited **0**, the separate native process check at
**2026-10-30T00:45:49.0440278Z** reported **FINAL_WORKERS=0** across Python,
Terraform, Node and Bash. No background execution or deployment worker remains.
Do not invoke any mutation stage again; this exact addition is already complete.