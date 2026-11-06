# Feature 2 plan — organization model access

Updated: 2026-11-03.

**Status: PAUSED until further user instruction.** This documentation update adopts
the recommended subscription approach; it does not authorize implementation,
testing, live preflight, subscription changes, migration, publication or deployment.
Existing source is retained, not restarted. See the
[implementation checkpoint](organization-model-access-implementation-20261103.md)
for source evidence and outstanding acceptance, and the
[retained live preflight](../.deployment/feature2-model-access-live-20261103-01/CHECKPOINT.md)
for the historical blocker. Historical receipts are not fresh live-state proof.

## Recommended approach: reuse organization-linked APIM subscriptions

Use the existing organization-linked APIM API subscriptions for customer inference.
These are not Azure billing subscriptions. One organization may have multiple APIM
subscriptions; all inherit the same organization-level model permissions. No
per-subscription entitlement overrides or artificial organization for master.

Request authorization follows:

**Validated subscription key → trusted APIM subscription ID → organization → enabled models.**

- Compile bindings from the existing trusted subscription records and reconcile
  them against complete APIM metadata. In the verified source contract,
  `TeamSubscription.id` is the resource name used by `ApimClient.ensure`; there is
  no separate `apim_subscription_id` field. Verify actual gateway identity during
  acceptance rather than assuming a database ID is sufficient proof.
- Never derive organization ownership from a customer-supplied header, query
  parameter, display name or another subscription's ownership.
- Include default-unrestricted organizations in the binding projection too.
  Unknown, missing or ambiguous bindings must fail closed after activation, not
  become default-allow or inherit another organization's access. Invalid or
  unavailable projection is an availability failure, not permissive fallback.
- New subscriptions must have their trusted binding published and read back
  before they are reported ready. Cover reassignment, renewal and re-enable.
- Reuse the three UUID-named organization/product subscriptions observed in the
  retained inventory where their current ownership is verified. That historical
  inventory does not by itself establish today's ownership or caller usage.

## Master subscription: migrate callers, do not add a special exception

The recommended target state is that customer inference uses organization-linked
subscriptions, not the built-in service-wide master subscription. The current
compiler cannot represent master and bootstrap forbids excluding executable keys.
Do not silently exempt it, guess its organization, retrieve its key, or extend the
compiler solely to force it into an artificial organization.

After the user explicitly resumes work:

1. Review legitimate master dependencies using approved, secret-free evidence.
   Identify applications and operator workflows, intended organization ownership,
   and any usage that cannot appropriately be assigned to an organization.
2. Plan each legitimate inference caller's move to the appropriate existing
   organization-linked subscription; provision an additional mapped subscription
   only when needed. Handle credentials through approved secret channels, never
   logs or plan artifacts. Any non-organizational requirement needs a separate
   explicit design decision, not an implicit exemption.
3. Perform the separately authorized caller migration and verify no remaining
   legitimate master dependency. Successful provider inference requires separate
   paid-call authorization; do not infer migration success from metadata alone.
4. Obtain explicit approval before suspending master. This plan update does not
   authorize suspension, revocation, key rotation or any other live mutation.
   Confirm the actual supported disposition and its effect on the target API;
   inability to render master non-executable remains an activation blocker.
5. Before bootstrap/activation, freshly verify complete executable-subscription
   inventory and unambiguous organization bindings. Master must no longer provide
   an executable bypass. No active unbound key may be omitted from reconciliation.

Until these gates pass, master remains unchanged and Feature 2 activation stays
OFF. Explicit approval to resume Feature 2 is not automatically approval to
disable an operator credential.

## Product behavior retained

- Admin selects an organization and checks models to enable/disable, with search,
  provider filters and availability/pricing indicators. Decision-1 is an
  informational internal scoring dependency, not a chat-model checkbox.
- Existing and new organizations allow all current and future callable models by
  default. Store explicit model denies and an independent Auto toggle. “Disable
  current models” warns that future models remain enabled by the agreed default.
- Customer discovery and executable pickers hide denied models; APIM blocks direct
  API requests too. Customer metadata scope comes from the authenticated principal;
  gateway execution scope comes from the trusted subscription binding.
- Auto intersects the existing fixed candidate pool with organization permissions:
  zero candidates rejects before scoring/provider access, one routes directly
  without scoring, multiple retain existing profiles/scoring. Recheck the final
  selected model and retry paths. No forbidden-model fallback.
- Globally unavailable models remain unusable regardless of organization preference.
  Missing pricing alone is not a permission denial. History, transcripts and
  historical pricing/showback remain intact; stale executable selection is cleared
  with a notice and no automatic retry.
- Versioned saves, audit history and draft/conflict protection remain. Applying →
  Applied reports publication/readback, not instantaneous all-edge propagation.
  Old access may persist while changes propagate; no immediate-revocation promise.

## Architecture and release gates

Continue the existing additive entitlement/audit/outbox source implementation.
Reuse the runtime-owned settings fragment with coordinated entitlement, pricing
and detached-control branches; preserve sibling data through shared locking,
conditional ETags, generation checks and readback. Static operator-deployed APIM
guards enforce permissions before scorer/provider calls. No per-inference database
or control-plane permission lookup, broad runtime policy grant or runtime DDL.

On explicit resumption, complete the remaining acceptance rather than treating
source tests as production proof:

1. Resolve caller migration/master disposition and complete trusted ownership
   reconciliation before enforcement activation.
2. Validate frontend runtime behavior, actual PostgreSQL migration/concurrency and
   explicit least-privilege new-table runtime grants through an authorized private
   execution path. Keep the database private and runtime without DDL authority.
3. Validate Terraform/provider and APIM supported surfaces, all explicit/Auto/retry
   enforcement paths, publication conflicts/failures and subscription lifecycle.
4. Verify two organizations with different permissions, spoofed organization
   headers, missing bindings, disabled models and Auto candidate boundaries;
   prove denial does not call scorer/provider. Preserve auth, quotas, safety,
   internal Auto pricing and customer financial privacy.
5. Use separately authorized clean-parent releases and fresh protected guards.
   Stage compatible publishers/readers, perform reviewed legacy import and
   bootstrap/readback, and only then activate enforcement. Never replay consumed
   builds, migrations, plans, applies or observers. Do not remove enforcement on
   rollback while restrictions remain; use a reviewed coordinated recovery.

Features 3/4, dynamic Auto pools, output-cap changes and new pricing/budget behavior
remain out of scope. No production acceptance or fresh live verification is
claimed by this plan update.