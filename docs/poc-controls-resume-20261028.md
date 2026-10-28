# Scoped gateway and safety controls — resume checkpoint

## Fragment CREATED AND VERIFIED — Entra handoff

The detached fragment was **created on 2026-10-28 at 04:02:15 UTC**, by the
single targeted01 apply of saved plan SHA256
`1d35fbd135345241f7a4115aeb9ab16fa0d439360188595198e440e447545dcd`.
**Do not recreate it, retry apply, import it or write its content.**

[Open the existing fragment in Azure Portal](https://portal.azure.com/#resource/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim/policyFragments/aiflux-dev-unified-poc-settings/overview).

Fresh exact-resource GETs report **Succeeded**. The first verifier failed at
04:02:27 UTC because `format=xml` adds an extra entity-escaping layer in the
organization C# expression and quota counter-key (`&quot;` → `&amp;quot;`).
`format=rawxml` retains the expected entities and adds only CRLF/tab indentation.
No C# text, literal quota, counter identity, element order or defaults differ.
The separate strict cross-export verifier preserves significant text and checks
both exports; 131 focused Python tests passed with no failures or skips.

**Independently verified at 2026-10-28 04:08:00 UTC**, with a fresh reader's exact
rawxml/xml GETs after the full protected-baseline collection. Resource identity,
description, provisioning state, strict XML semantics and the existing Terraform
owner/state lineage were verified. All four images/settings, existing APIM
resources, model metadata, identities, private-network controls and FinOps
timer/cutoff remain identical, excluding only the authorized new fragment.

- Complete protected-baseline SHA256 (unchanged):
   `9654aa8c45559941fb7033ab11f9f13c3e743a4c4d27339b95caac8fef0272ee`.
- Active policy SHA256 (unchanged):
   `e45b6de7b61b29a4085b4569609da48314d9c144306a9c02211d1ce58ce5b456`.
- [Fresh independent read-only proof](../.deployment/poc-fragment-bootstrap-20261028-targeted01/read-only-verified-20261028T040606436606Z.json).
- [Current result](../.deployment/poc-fragment-bootstrap-20261028-targeted01/result.json)
   now records `fragment_exists: true` and
   `created_and_readonly_semantically_verified`.
- [Preserved original failed result](../.deployment/poc-fragment-bootstrap-20261028-targeted01/result-before-readonly-20261028T040606436606Z.json),
   including the stale false field and original failure; its history is also
   retained as the exact prefix of the current result history.
- [Focused test evidence: 131 passed, zero failures/errors/skips](../.deployment/poc-fragment-bootstrap-20261028-targeted01/readonly-semantic-tests.xml).

Original rejected plans and successful apply/review/validation markers remain
hash-identical. Total applies remain **one**; this reconciliation performed
**zero cloud writes**, no Terraform execution and no inference requests.

**Next step is central Entra action, not another deployment:** grant the existing
API identity principal `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` (client ID
`f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1`) only
`Microsoft.ApiManagement/service/policyFragments/read` and
`Microsoft.ApiManagement/service/policyFragments/write` at the single fragment
scope linked above. No data actions, delete, broader scope or operator role grant.
Return assignment/role-definition IDs for read-only permission verification.
No grants were made here. Publisher permission remains unverified; POC/V2
controls remain OFF. Any subsequent activation requires a separately approved
release; no settings, images, database, network or inference changes are part of
this creation/reconciliation task.

## Detached fragment bootstrap — retained creation history

The user explicitly authorized **creation only** of the detached
`aiflux-dev-unified-poc-settings` fragment on `poc-ids-token-ex-apim`, to enable
central Entra assignment at that exact resource scope. Publisher permission is
still unverified/false and is **not a prerequisite for operator creation**.
All controls remain OFF; creation must not include the fragment in the active
API policy or activate settings.

The original saved plan was rejected by the unchanged exact-one-fragment-write
guard because APIM refresh proposed a policy `xml` → `rawxml` export
normalization. Its failure logs and plan are retained **NEVER APPLY**. Stored
policy bytes already equal the current render; no cosmetic policy repair is
authorized. The corrected attempt is isolated in
[.deployment/poc-fragment-bootstrap-20261028-targeted01/result.json](../.deployment/poc-fragment-bootstrap-20261028-targeted01/result.json).
Its completed creation workflow required a fresh protected baseline, actual tests, a separate full refreshed
**NEVER APPLY** validation companion and an exact fragment-only targeted saved
plan, independent sequential validation/Section 7 proof, one exclusive apply,
then exact-ID/XML and full protected readback. Creation succeeded; the original
readback failure is reconciled separately above, without replaying that workflow.

Current corrected-attempt validation: **101 focused Python tests and 29 Terraform
mock tests passed**, with zero failures. Fresh protected baseline equals the
original checkpoint (SHA256
`9654aa8c45559941fb7033ab11f9f13c3e743a4c4d27339b95caac8fef0272ee`).
The refreshed full companion independently confirms stored rawxml policy body
equals current render bytes (SHA256
`509c48ed61fd9eda2a9acf06ea1c9b6478f76c7d99425528a49bee61a078d4b2`), decoded
live semantics are identical, and all ten existing managed resources are no-op
apart from the representation-only policy diff in that **NEVER APPLY** companion.
The actual release must contain no policy write.

## Status

**Settings activation is not deployed: exact publisher permission remains
unverified.** The detached fragment creation succeeded as recorded above; it is
not feature activation. The earlier 00:10 resume check below performed no image
push, infrastructure apply, settings activation, database initialization or role
assignment. Read-only reconciliation adds no cloud writes and sends no inference,
playground, safety or quota traffic.

Azure CLI account metadata verified the expected tenant, subscription and
operator using the existing combined corporate CA bundle, with TLS verification
enabled. The supplied Zscaler roots are trust certificates, not Azure login
credentials; an existing Azure session was available.

Fresh read-only evidence at 2026-10-28T00:10:36Z:
[preflight](../gateway/validation/poc-controls-preflight-20261028T001036Z.json).
Protected runtime configuration and active API policy exactly match the previous
preflight. The four live image pins remain unchanged. The POC settings feature
is not activated. Local operation markers contain the previous validation
builds, not a POC release plan/apply intent.

## Central-team action required

As specified in [central RBAC ownership](central-rbac-handoff.md), role definition
and assignment writes remain with central administrators. The deployment user's
existing Contributor permission is not authorization-management permission.

Grant the API's existing user-assigned managed identity:

- Principal object ID: `4e7b70ed-9868-47ba-9b61-304f1e1fdd89`.
- Client ID: `f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1`.
- Actions only:
  - `Microsoft.ApiManagement/service/policyFragments/read`
  - `Microsoft.ApiManagement/service/policyFragments/write`
- Data actions: none. Delete permission: not required.
- Assignment target: the single `aiflux-dev-unified-poc-settings` fragment on
  `poc-ids-token-ex-apim`, not every APIM policy or the subscription.

Exact resource scope:

> /subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim/policyFragments/aiflux-dev-unified-poc-settings

Use a custom role containing only those two actions, or an existing central-owned
role with the same effective permissions. The target now exists; use the verified
existing resource rather than requesting recreation. Do not substitute Owner, Contributor or APIM Service
Contributor, grant the operator additional authorization roles, or broaden the
scope as a workaround. Return the assignment and role-definition IDs for read-only
verification; do not send credentials or tokens.

## After the grant

1. Recheck effective permissions and the complete protected baseline.
2. Finish the narrowly guarded release preparation and independent validation.
   Previous native Linux checks are validation-only, not published release images.
3. Reuse the already-created safe-default fragment without recreation. Any switch
   of API policy, API/admin images or feature settings is a separate approved
   activation release, not part of this completed creation task.
4. Initialize the audited schema-3 revision through authenticated admin APIs and
   verify management-plane publication, inheritance and benign save/removal.
5. Preserve product-wide default access, existing counter identities/windows,
   pricing, all model routes, Foundry shared safety bindings, private networking
   and FinOps timer/cutoff. Skip all inference traffic verification as requested.

Earlier successful validation: 185 focused release regressions, 111 UI tests and
96 production-package API tests. These are previous checkpoint results, not tests
rerun during this resume. The separate unfiltered workspace run had two migration
failures, retained in the previous checkpoint; do not describe all workspace tests
as passing. Deployment remains incomplete until the pending checks and rollout
are actually executed.