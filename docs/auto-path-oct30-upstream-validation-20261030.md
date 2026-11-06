# Oct30 upstream adaptation: actual offline validation

## Actual source diff (not a whole-worktree diff)

- Added [private collector](../scripts/deployment/auto_path_oct30_collector.py):
  private collector/customer/persistence/release bindings, original snapshot and
  historical protected guard, pinned whole-account verification before the
  exact historical-copy IP removal, actual-five retention and second-read match.
- Updated only the unbound [Oct30 controller](../scripts/deployment/auto_path_diagnostic_oct30.py):
  use this collector for prepare and production captures, bind new tests/docs,
  retain finite sanitized exclusive prepare failures and refuse their replay.
  Before SHA256 `108db7277bb5cfa469433b59ef767c0d3c7f79495e0e9a21e63cab7e9fa8020d`;
  after `d0d53217a30150929b03b0c7b87c8b9cc2974cfe3859add4fed18e39efd47091`.
- Added [32 regressions](../tests/unit/test_auto_path_oct30_collector.py) and
  [adaptation contract](auto-path-oct30-collector-adaptation-20261030.md).
- The old [four-IP guard](../scripts/deployment/project_route_product_access.py)
  was NOT edited. All old173 hashes remain exact. Of the retained old207 set,
  206 current files remain exact and only the unbound Oct30 controller differs;
  three added files yield the tested **210-source** set. Historical evidence
  remains unchanged; no old manifest/source set was restamped.

## Actual tests

Sole full offline validator PID3212 completed **exit0**, at
**2026-10-30T04:19:35.514656+00:00**, then was awaited without replay.

| Suite | Tests | Result |
|---|---:|---|
| [Python receipt](../.deployment/auto-path-oct30-upstream-full-20261030-python.xml) | 217 = existing185 + new32 | exit0; failures/errors/skips0 |
| [Native Oct30 receipt](../.deployment/auto-path-oct30-upstream-full-20261030-native.xml) | 50 | exit0; failures/errors/skips0 |
| [Offline browser fixtures](../.deployment/auto-path-oct30-upstream-full-20261030-browser.xml) | 67 | exit0; failures/errors/skips0 |

The [actual result](../.deployment/auto-path-oct30-upstream-full-20261030-result.json)
binds all sources and receipt hashes. Its SHA256 is
`2cb07aa228104b32acc1cd2c5455c36b4ed35a729f21334604b99b99fedb373a`.
Full210 source-set SHA256:
`54e18aa6d86323a2b43f2384b0e91a613f2dce41c7af898a54aacd6cbdced9c5`.
New collector SHA256:
`085c698fa055c9c3ff42a0c3d9e24ba4eafd04a38cb448a385d71679600b354f`.
Post-test offline checks proved source equality, all three receipt hashes, the
unchanged historical207 result hash, pinned approved four-to-five transition,
absent new package and absent shared owner. Editor diagnostics: no errors in
the changed Python/test modules or offline runner.

Regressions exercise the ACTUAL collector → private ACTUAL snapshot → original
protected-function path using offline external-read fixtures; every original
security guard still executes. Exact approved five passes, original four passes
outside context and five still fails there. Other/missing/duplicate/reordered/
CIDR/action/sixth IPs, VNet/IPv6/resource rules, bypass, defaultAllow, public/shared
key and other whole-account property/metadata changes all fail. Body/entry
exceptions restore transport/class bindings. Finite failure receipts preserve
UNKNOWN historical PID27864 exception without arbitrary exception strings.

The initial new-only regression run had 27pass/4fail: incomplete policy fixture
and rebinding a contextmanager wrapper instead of its underlying generator.
Those receipts are retained; after correction new-only31 passed and the final
full run above includes one further real-collector regression (32 new total).
No failed run is represented as passing. The historical full-native binding
failure remains **unwaived**, and was not rerun here. One existing Starlette
deprecation warning is not a test failure.

## Readiness and hard stop

[Retained CLI handoff](../.deployment/auto-path-oct30-upstream-20261030-ready-cli.json):
**ready_cli=false**, manifest/window absent. Parser/import-only help actually
returned exit0; the retained future read-only-prepare argv was NOT executed and
is NOT approval. Independent parent source review of this exact source set and
separate new authorization must precede any fresh read-only preparation. No
independent reviewer approval or original PID27864 error is invented here.

**Actual prepare/cloud calls/mutations/Send/Terraform/builds: all zero.**
Temporary fixture-package construction in offline tests is not a real prepare.
No activation, cleanup or release command was run. No task-completion claim.