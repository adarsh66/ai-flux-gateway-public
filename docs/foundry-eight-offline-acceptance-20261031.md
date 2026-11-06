# Eight-model evidence acceptance — offline promotion

## Accepted scope

All eight already-consumed requests have valid technical identity and measured
usage evidence. This does not claim a runtime publication or a new inference test.
The immutable successor03 failed receipt and final integrity remain unchanged.

The user explicitly authorized exactly the technical identity mapping
`Mistral-Large-3` deployment → provider model `mistral-large-3`, conditioned on
the existing correlated LLM record's exact deployment, model, response ID,
correlation ID and measured usage. These conditions are proven. There is no
generic case folding and no change to the public capability contract.

The first bounded metadata query returned no rows with a case-sensitive Azure
resource-ID filter. Its failure and empty response are preserved. The sole
remaining query used case-insensitive comparison **only for the Azure resource
ID**, and joined the exact existing LLM/gateway records in the same fixed
20-second historical window. Two metadata queries total, zero inference sends,
no message/body columns, no TLS bypass, no roles/network changes or installs.

## New build context and proof-requiring profile

- [Accepted source context](../.deployment/foundry-eight-offline-promotion-20261031/accepted-context)
- [Selected inventory, packaged under the configured historical filename](../.deployment/foundry-eight-offline-promotion-20261031/accepted-context/gateway/catalog/foundry-inventory-20261026.json)
- [Accepted catalog](../.deployment/foundry-eight-offline-promotion-20261031/accepted-context/gateway/catalog/ingestion-approved.json)
- [API catalog](../.deployment/foundry-eight-offline-promotion-20261031/accepted-context/gateway/catalog/dev-models.json)
- [Ingestion catalog](../.deployment/foundry-eight-offline-promotion-20261031/accepted-context/services/usage-ingestion/ingestion-approved.json)
- [Acceptance provenance and source/context hashes](../.deployment/foundry-eight-offline-promotion-20261031/accepted-provenance.json)
- [Separate exact pricing source freeze](../.deployment/foundry-eight-offline-promotion-20261031/pricing-freeze/manifest.json)

Profile: `foundry-eight-accepted`. The new profile requires genuine hash-anchored
receipts, intents, all eight consumed ledger entries and correlated Terra/Mistral
metadata. Synthetic `gateway_validated` flags alone cannot pass. It invokes the
unchanged historical builder's explicit `foundry-eight` validation afterward.
Both API and ingestion Dockerfile copies run this proof-required validation;
original Dockerfiles and bound JSON remain untouched. Curated source context
contains API/ingestion/admin/customer build inputs, not dependencies, credentials,
cloud state or build outputs. No image builds were performed or certified here.

Exact membership: 20 Foundry chat routes + external `glm-5.3` = 21 enabled chat
models, plus disabled routing-only `Decision-1`. No ninth addition; the unrelated
`mistral-medium-3-5` deployment is excluded. No Auto activity is authorized here.

The old twelve deployments/routes retain their original inventory timestamp and
all original fields except the explicitly documented public endpoint conversion.
Per-route original hashes and the historical inventory hash are in provenance.
This is grandfathered acceptance, not a fresh probe. External inventory bytes
and timestamps are unchanged. Pricing's eight-model source remains separately
frozen, not identity or inference evidence.

## Actual measured usage

| Alias | Input | Output | Total |
|---|---:|---:|---:|
| `claude-sonnet-5-5` | 18 | 13 | 31 |
| `claude-opus-5-5` | 18 | 13 | 31 |
| `claude-opus-5-5-fast` | 18 | 13 | 31 |
| `claude-haiku-5-5` | 18 | 13 | 31 |
| `gpt-6.1-terra` | 12 | 5 | 17 |
| `gpt-6-luna` | 12 | 7 | 19 |
| `claude-opus-4-8` | 16 | 9 | 25 |
| `Mistral-Large-3` | 9 | 7 | 16 |
| **Total** | **121** | **80** | **201** |

[All eight exact response/correlation IDs, original usage and acceptance proofs](../.deployment/foundry-eight-offline-promotion-20261031/all-eight-usage-proofs.json)
are retained. Terra's original raw model field stays null; its exact correlated
dated model evidence resolves identity without inventing a raw response.
Claude fast retains exact policy/normalizer guard-based proof; it is not claimed
to be a retained direct native trace or inferred from latency.

## Validation and limits

- [214 offline tests, zero failures/errors/skips](../.deployment/foundry-eight-offline-validation-20261031/result.json).
- Actual catalog `build`, packaged verification, strict `FoundryInventory` schema
  and every route's runtime acceptance check passed. A bogus provider field in
  a route is explicitly rejected, rather than added to the schema.
- Original failures, telemetry query failure, historical sources and consumed
  ledgers are preserved. Remaining inference budget: **zero**.
- No fresh post-probe policy read was performed or claimed; this remains a
  historical evidence promotion, not a fresh runtime policy attestation.
- No builds, runtime publish, database/APIM mutations, role/network changes,
  installs, TLS bypass or Auto activity occurred.
- Recorded timestamps use the machine's actual UTC clock; dated folder labels
  are identifiers and are not used to restamp historical observations.