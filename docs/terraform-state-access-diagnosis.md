# Terraform state storage access diagnosis

## Current: authorized connection restored — 2026-10-29

**Backend ready, independently verified at 2026-10-29T03:06:02.708163Z.**
The user's explicit approval in this session superseded the previous no-firewall
restriction **only** for adding the single IPv4 Allow item `167.103.63.12` on
the existing `projpoctokenex` account. Approval was recorded at
**2026-10-29T03:04:15.312094Z**; this is the execution-record timestamp, not an
invented timestamp for the user's message.

The verified exact current Allow entries are:

- `167.103.66.93` — retained.
- `167.103.66.248` — retained.
- `167.103.65.36` — retained.
- **`167.103.63.12` — this operation's only addition.**

The new exclusive workflow is
[backend_connection_restore_oct29.py](../scripts/deployment/backend_connection_restore_oct29.py).
Evidence is in the fresh directory
[final result](../.deployment/backend-connection-restoration-20261029-030415311253Z/result.json),
[approval record](../.deployment/backend-connection-restoration-20261029-030415311253Z/approval.json),
and [network verification](../.deployment/backend-connection-restoration-20261029-030415311253Z/network-verification.json).
It did **not** retry the previous inventory backend intent or run its controller.

### Actual action, concurrency and preservation

- Correct native CLI subscription `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`, tenant
  `beb276ac-6e9f-498e-8e31-019ee666decd`, and operator token identity were verified.
  The existing runtime-rollout environment and corporate CA were used with strict
  TLS. The Azure MCP CLI-extension lookup returned the known HTTP403; the official
  troubleshooting guide was consulted. Available Terraform best-practice guidance
  was retrieved; nothing in it authorized a plan or apply in this delegation.
- Live ARM reads captured the complete account configuration and actual ETag
  fields **before** mutation. Both response-header and body ETags were **absent**.
  The Storage update contract does not expose a documented conditional-write
  token here; no fictitious ETag or `If-Match: *` protection was claimed.
- An immediate fresh full-account comparison matched the original baseline.
  The inspected native CLI single-IP operation then performed its own fresh GET
  and merge. Only `--ip-address 167.103.63.12 --action Allow` was supplied; no
  cached full ACL, account-update document, default-action or bypass flag was sent
  by the caller. Exactly **one** CLI write attempt succeeded, exit0, during
  **03:04:47.398452–03:04:52.000609 UTC**. The durable intent prevents replay.
- **Concurrency limitation:** this CLI operation is read/merge/write, not an
  atomic compare-and-swap. No concurrent change was observed. Fresh pre-write
  comparison, CLI's own read and independent post-write whole-account comparison
  verified the actual outcome; they are not a guarantee against an unobserved
  external writer in the small read/write interval. A future mismatch must stop
  for reconciliation, never overwrite or automatically retry.
- Independent ARM plus separate native CLI readback passed at
  **03:05:18.621974 UTC**, followed by final ARM verification. Every returned
  account configuration field matched except the exact added IP item; ARM ETag
  and bookkeeping `systemData` are the only comparison exclusions and remain in
  raw evidence. Existing/concurrent IP rules, default **Deny**, existing
  **AzureServices** bypass, public network **Enabled**, shared-key setting **true**,
  IPv6/VNet/resource-access settings and every other configuration were retained.
  Shared keys were not requested or used.
- No admin, SCM, PostgreSQL or APIM ACL, role, identity, other infrastructure,
  application setting or policy was modified.

### Connection and isolated initialization results

- Entra-only container existence probe: `exists=true`, exit0.
- OAuth **HEAD**, not a body download, of the existing state blob: HTTP200;
  lease status `unlocked`, lease state `available`. No lease was broken/acquired.
- Fresh isolated **backend-only** Terraform root, existing backend configuration,
  copied existing provider lock, `TF_WORKSPACE=default`, readonly lockfile:
  **init exit0**, backend configured, **03:05:55.243868 UTC**. No source-root
  initialization was overwritten, no provider upgrade, state migration, workspace
  creation, plan, apply or state command was executed. This proves backend
  connectivity, not a full application-provider validation or release approval.
- State blob ETag, length, last-modified time, lease state/status were identical
  before/after init. No state body or credentials were printed or persisted by
  this workflow; Terraform output was captured privately in memory and only its
  structural result/hash retained. Remote state writes: **0**.
- Historical intent hashes, including the previous failed inventory backend
  intent, were unchanged. Worker checkpoints found **0 competing mutation
  workers**, only the current restoration process and the existing MCP service.
  Final [offline audit](../.deployment/backend-connection-restoration-20261029-030415311253Z/offline-final-audit.json)
  at **03:07:40.422284 UTC** verified **92 retained intent hashes**, the exact
  CLI/Entra cached backend configuration with no resource/output payload, original
  and copied provider-lock byte equality, and **13 passing preservation/no-replay
  tests**. It made **0 cloud calls** and did not rerun init.
  A native process check after task exit at **03:08:16 UTC** found only the
  existing `azmcp.exe` PID **19628** among Python/Terraform/Bash/MCP processes:
  **0 remaining restoration, audit, Terraform or release workers**.

There was **1 cloud configuration write**, exclusively the approved storage IP.
Builds/pushes/plans/applies: **0**. The application inventory-expiry issue is **not
fixed by this connection repair**; source work is delegated separately. Existing
historical release baseline snapshots still describe the older three-IP ACL and
must not be silently rewritten/replayed. The backend owner should incorporate
this approved fourth item without adopting the account into another Terraform
root. No automatic expiry/removal was introduced; owner review remains required.

## Historical executed storage-only approval — 2026-10-27

The user explicitly approved **only** adding `167.103.65.36` to the existing
`projpoctokenex` account. Fresh CLI account/tenant/subscription checks passed.
Write interval: **01:00:06.9876267–01:00:12.6457396 UTC**; independent ARM/CLI
readback completed **01:00:17.5486864 UTC**. The allowed set at that time was exactly
`167.103.66.93`, `167.103.66.248`, `167.103.65.36`, all single-IP Allow entries.
Default Deny, existing AzureServices bypass, public-network setting, shared-key
setting and empty IPv6/VNet/resource-access rule sets were preserved. No key was
requested/used; no RBAC, application/SCM/APIM/PostgreSQL ACL or other network changed.

Entra `tfstate` **container-existence only** returned `exists=true`, CLI exit 0,
at **01:00:22.2270686 UTC**. Reconfirmation at **01:09:12.680171 UTC** also reported
verified metadata access and zero unapproved IP rules. No blob names/content,
state downloads, leases, Terraform init/plan/apply or state ownership changes
were performed. Success verifies this operation's network/auth path; it does not
attest every future destination's egress or permit broader firewall rules.

### Exact operator drift reconciliation and ownership

Existing ARM resource:
`/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.Storage/storageAccounts/projpoctokenex`.
The rule is an item in **`properties.networkAcls.ipRules`**, not a separately named
ARM resource; CLI exposes it as `networkRuleSet.ipRules[].ipAddressOrRange`.
The operation was an approved existing-backend **operator change**, not a new
Terraform resource or permission to adopt ownership.

Backend declarations reference this external account; no active workspace source
resource declaring ownership of this existing account was found. Remote state
was deliberately not read to speculate about another owner's resource address.
[The deferred state root](../infra/state/main.tf) has `azapi_resource.state`, but
creates a different private/keyless design behind approval gates: **it is not
evidence of ownership of this deployed external backend**. Do not import this
account there, apply that root, duplicate its ownership, or update global
`operator_ip` (which can affect admin/PostgreSQL ingress) to reconcile this rule.

This document and [the execution record](../gateway/validation/finops-state-access-20261027.json)
are the historical narrow operator reconciliation record. The then-current read-only FinOps
diagnostic allowlist recognized precisely these three state-account IPs and
reported every additional IP as unexpected. Those historical release guards were
not replayed or broadened during the Oct29 connection-only delegation. No Terraform resource/input was
changed or applied. The actual backend owner must incorporate this approved item
in its existing desired ACL without replacing concurrent rules or settings.
This rule has no automatic expiry; retention/removal must be reviewed by that
owner. Any later cleanup removes only this added IP after checking current ownership
and concurrency; never remove either prior rule or alter default Deny.

Private DB execution is a different problem; see the
[runner proposal](finops-private-runner-proposal-20261027.md). No runner was created.

## Historical diagnosis (before the explicit approval)

## Fresh read-only findings

- Backend account: `projpoctokenex`; container: `tfstate`.
- Current Azure CLI subscription and tenant match the backend configuration.
- CLI acquired an Entra token for `https://storage.azure.com/` successfully.
- An independent OAuth container-list request returned HTTP 403,
  `AuthorizationFailure`, request ID `d390ebaf-401e-0039-2465-658f64000000`.
  No state contents or blob names were emitted.
- Account management-plane reads succeed. Public network access is enabled,
  but firewall default is `Deny`; its only allowed IP is `167.103.66.93`.
  There are no private endpoints or virtual-network allow rules.
- An HTTPS public-IP check reported `167.103.66.248`, which differs from the
  allowed IP. This is supplemental evidence: destination-specific corporate
  proxy routing can use a different egress for Azure Storage.
- The operator has inherited `Storage Blob Data Contributor` at resource-group
  scope, with no assignment condition returned, plus subscription Contributor.
  Adding another copy of these roles is not indicated.
- No diagnostic settings exist on the account or Blob service, so there is no
  configured diagnostic destination available to correlate Storage's caller IP.

## Conclusion and limits

The leading explanation is corporate egress no longer matching the single-IP
Storage firewall rule, not a Terraform-specific error. Independent OAuth failure
reproduces the problem outside Terraform. Token acquisition and existing role
assignments do not by themselves override the Storage firewall.

The exact Storage-observed caller IP is not proven. Do not automatically allow
`167.103.66.248` based solely on the public-IP check or broaden the firewall.
Other deny/perimeter controls have not been exhaustively excluded.

## Narrow remediation

Confirm the egress used specifically for `projpoctokenex.blob.core.windows.net`
with the corporate network/proxy team. Prefer running Terraform from an existing
approved execution location. If a firewall update is needed, obtain approval for
the confirmed exact egress IP and manage it through the established infrastructure
process, retaining default-deny restrictions and cleanup requirements.

After approved connectivity is restored, repeat the OAuth container-list probe
and Terraform backend initialization before planning any runtime promotion.
Do not use shared-key fallback, recreate the backend, move state locally, or
reset Terraform state to work around this failure.

No firewall, identity, RBAC, diagnostic, state, or runtime changes were made.