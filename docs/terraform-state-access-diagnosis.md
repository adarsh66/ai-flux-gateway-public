# Terraform state storage access diagnosis

## Executed storage-only approval — 2026-10-27 (supersedes older ACL below)

The user explicitly approved **only** adding `167.103.65.36` to the existing
`projpoctokenex` account. Fresh CLI account/tenant/subscription checks passed.
Write interval: **01:00:06.9876267–01:00:12.6457396 UTC**; independent ARM/CLI
readback completed **01:00:17.5486864 UTC**. The allowed set is now exactly
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
are the narrow operator reconciliation record. The existing read-only FinOps
diagnostic allowlist now recognizes precisely these three state-account IPs and
still reports every additional IP as unexpected. No Terraform resource/input was
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