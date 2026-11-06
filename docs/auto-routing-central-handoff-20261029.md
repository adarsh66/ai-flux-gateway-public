# Auto routing: exact central authorization handoff

## Superseded architecture — gateway-direct implementation, 2026-10-29

**The API-MI grant and API-audience reconciliation requested below are NOT gates
for the current gateway-direct implementation. Do not execute those historical
instructions or grant an additional identity to enable this design.**

APIM calls the fixed Decision-1 SystemOne endpoint using its existing gateway
user-assigned MI, client `5792b72e-1605-4dce-a594-4c430a5af619`, with resource
`https://cognitiveservices.azure.com`. It does not call the legacy private API
resolver. The API only reports readiness and optional desired admin settings.
Shared source-bound Balanced/Cost/Quality defaults require no tenant seed,
subscriber allowlist or new customer approval; normal existing active-product
subscription authorization applies.

The earlier scoped audit observed the gateway's existing Cognitive Services
User assignment, but does not prove gateway-MI scoring access, connectivity or
the live response shape. No new grant, registration or infrastructure is being
requested here. No fresh scoring probe or metadata collection was performed.
Actual APIM-native MI/response proof, a trusted exact-policy publication receipt,
broader regression remediation and independent platform release review remain
necessary before activation. Auto remains default-off and undeployed.

See the [authoritative source and validation reconciliation](auto-gateway-source-only-20261029.md)
for `cm36`, 123 focused passes, seven Terraform mock passes and the unresolved
broader-suite defects. The original audit is retained below solely as historical
evidence for the abandoned API-mediated path, not as current deployment guidance.

## Historical API-mediated handoff (do not execute for gateway-direct)

Prepared from the [fresh read-only audit](../.deployment/auto-identity-readback-20261029T042927919100Z/readback.json)
started 2026-10-29 04:29:27 UTC. **No grant or configuration change was made.**

## Confirmed runtime authorization gap

Current source architecture: gateway MI authenticates to the private API with a
distinct API-audience token; **the API obtains its own MI token** for Decision-1
using `https://cognitiveservices.azure.com/.default`. The gateway's existing
Foundry assignment cannot authorize the API identity.

For separate central review/approval, the documented built-in inference role is:

| Field | Exact target |
|---|---|
| Tenant | `beb276ac-6e9f-498e-8e31-019ee666decd` |
| Existing API principal/object ID | `4e7b70ed-9868-47ba-9b61-304f1e1fdd89` |
| Existing API client ID | `f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1` |
| Principal type | ServicePrincipal (existing user-assigned managed identity) |
| Role | Cognitive Services User |
| Role definition ID | `a97b65f3-24c7-4388-baec-2e87135dc908` |
| Scope | `/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry` |
| Intended use | Existing Decision-1 SystemOne scoring, not chat generation or resource administration |

Fresh assignment collection at the Decision deployment (including inherited
account/RG/subscription grants) contains **no API-principal assignment**; transitive
group enumeration succeeded with zero memberships. All returned role definitions,
including custom roles, were read. Deny lists at subscription/RG/account/deployment
were empty. No claim is made about unobserved out-of-band policy restrictions,
PIM activation, runtime token propagation or private endpoint connectivity.

The actual Cognitive Services User definition contains data action
`Microsoft.CognitiveServices/*`, with exclusions for UserIdentityImpersonation and
two fine-tuning-deployment writes. It also contains key/connection-secret-related
management actions: these were **not invoked**. This is the documented existing
built-in role, not a fabricated scoring-only custom role. Central governance may
review whether a narrower approved existing role is suitable; this task creates
no role definition. Scope is the one account, not the subscription or resource
group. No blanket Owner and **no operator inference grant** are requested.

Gateway principal `bcf69911-f34e-4f33-acd8-a36f164db811` already has that role at
the account, unconditional assignment `3314027c-3549-4f4b-88dd-8f6356028cad`.
Do not grant both identities or switch architecture just to reuse that grant.

## Separate existing API audience gate

Fresh configured API audience is `local://turnstile-postgres-auth`, Entra client
ID empty, and Easy Auth returned no Entra client/issuer/allowed audiences. These
are local-login settings, **not an Entra token resource**. The API MI client ID
above is the caller identity, not proof it is a registered API resource audience.

Central/application owners must identify an already-existing API registration,
identifier URI, tenant, accepted token version and gateway app-only authorization
path, if one exists. Gateway client ID is `5792b72e-1605-4dce-a594-4c430a5af619`;
gateway principal is the one above. The source verifier currently requires v2
issuer and exact tenant/audience/principal/client; v1 MI-token support is not
claimed. No registration creation, shared-key workaround, audience substitution,
public ingress or network/config writes are authorized by this handoff. If no
compatible existing resource/path exists, report that constraint as a blocker.

## After separate authorization, not performed here

Re-read scoped metadata/propagation, then verify the actual existing private API
runtime identity and one separately approved bounded benign scoring contract.
Do not replay the historical operator 401 probe, impersonate MI from the laptop,
print tokens or treat ARM GET/role metadata as inference proof. Validate private
gateway-to-API authentication separately, then complete release review before any
profile initialization or Auto enablement. Keep all existing explicit routes,
safety, inventory persistence, network and FinOps behavior unchanged.