# POC publisher diagnostics — API-only deployment

Completed 2026-11-04 15:24UTC. Original plan17 applied once, native exit0:
0added/1changed/0destroyed, root166→167/child206 unchanged.

| Gate | Actual result |
| --- | --- |
| Retained Linux cm7k | 357 passed incl73 diagnostics;0fail/error/skip;1 deliberate migration deselection |
| Real PostgreSQL | 7 passed on container-local127.0.0.1:55432; no production DB access |
| Retained production cm7m | Succeeded, exact context14 and immutable parent0c01 |
| Saved plan17 | 0create/1API image update/0delete; exact archive/input/lock |
| Native predicates | 38 conditions; saved unknowns preserved;6 unsafe mutations rejected |
| Official validation18 | 9 actual workflow calls through UpdateStatus, each exit0 |
| Apply19 | One native API completion, exit0; no replan |
| Protections | Full46 each preapply/postapply/finalread20; final whole root exact postapply |
| Normal authenticated browser | Settings +both history pages200, current/published13; all3response hashes equal pre-release |
| Inventory/workers | 74before/0created; strict final workers pass,0kills/waivers |

API image:
`pocidstokenexacr.azurecr.io/aiflux-api@sha256:cdc16f8d834b38357c16e17c5cfd503680306bb5036e2d0df06d1577dd6180a7`.

Original binary SHA256:
`6773fe627c4daba830e80938e5f2da98c27fdde21e2896e17099256cadbe06db`.
Plan JSON SHA256:
`0e9c2fd20cd21d6a74f9d21b96c1cb763172f63c76218a4961417fec0f143b64`.

Only two diagnostic modules overlay installed/source copies of parent0c01.
Admin4a6/customer c564/ingest995c/all4settings/APIM22+Auto4096/pricing/current13,
active POC fragment, roles/network/DBsecurity unchanged. Feature2 remains paused.
Ordinary credentials/exact audiences/TTL≥600/corporate CA enforced. No inference,
Save/Retry/Reconcile, controls activation or settings/policy/pricing/DB/schema/
RBAC/network writes. Seven PG cases cover five archival locking/race cases and
two budget archive-vs-save races; these are isolated tests, not production SQL.

## Corrections and limits

Original failed cm7g/cm7h/cm7j and contexts preserved; separately named08/11/14
fixed validation fixture/config/import packaging only, production overlay exact.
There is no cm7i run in the actual receipts. First official18 local log audit
failed before any official invocation; raw-byte hash correction preserved the
STOP and all9 official steps then ran once. No production gate was waived.

Historical502 cause remains unproven; missing/null readiness still rejected,
12poll/60second limits unchanged. No failing live publication attempted.
Fresh ARM configured digest is verified, not an in-container process attestation.
Authenticated business GET200 verified; no repeated private health probe or403
success claim. Native summary pointer timed out; normal DOM UI handlers used,
not full accessibility acceptance. Existing UI output1024 wording unchanged;
active gateway4096 preservation independently guarded.

## Authority and no-replay boundary

- [Current full report](../.deployment/poc-publisher-release-20261104-01/FINAL.md)
- [Current machine status](../.deployment/poc-publisher-release-20261104-01/FINAL.json)
- [Official proof](../.deployment/poc-publisher-release-20261104-01/OFFICIAL18-PROOF.json)
- [Sole apply19 receipt with inherited filename](../.deployment/poc-publisher-release-20261104-01/rollout17/APPLIED09.json)
- [Final verification](../.deployment/poc-publisher-release-20261104-01/VERIFY20.json)
- [Postdeployment browser](../.deployment/poc-publisher-release-20261104-01/BROWSER20.json)

Verified page: https://poc-ids-token-ex-admin.azurewebsites.net/admin/settings

Never replay consumed stages or the saved binary. No remaining in-scope deploy
stage; live failure reproduction/publication needs separate scope. No generic
onboarding, azd, new infrastructure, rollback or restart.