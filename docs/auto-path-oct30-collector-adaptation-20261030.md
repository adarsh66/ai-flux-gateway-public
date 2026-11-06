# Oct30 upstream exact storage collector adaptation — OFFLINE ONLY

## Scope and call path

The original [collector](../scripts/deployment/auto_path_diagnostic_release.py)
calls `r.persistence.release.snapshot()`, whose globals resolve `ProductRun` in
[poc_activation_release](../scripts/deployment/poc_activation_release.py).
Its strict transport substitutes `ReadOnlyProductRun`, which inherits
`ProductRun.protected()` from
[project_route_product_access](../scripts/deployment/project_route_product_access.py).
That function's exact-four-IP guard rejects the approved fifth rule BEFORE the
downstream Oct30 predecessor/storage comparison. The latter is not sufficient
to adapt this upstream call path. This is a source/runtime-binding finding, not
recovery of the original PID27864 exception; that exception remains UNKNOWN.

The new [private collector](../scripts/deployment/auto_path_oct30_collector.py)
clones only controller/customer/persistence/release module dictionaries and
rebinds the snapshot/collector function globals. A private read-only class runs
the unchanged historical protected function with a private runtime binding.
The exact storage GET response must equal the whole approved after account
reconstructed by `storage_transition()` from the pinned 00:44 audit/result and
all hashed evidence. This includes every property, IP order/count/action,
VNet/IPv6/resource rules, bypass, Deny, public access, shared key and metadata.
Only THEN a deep copy loses the known last Allow167.103.67.80 rule; the entire
copy must equal the approved four-IP before account. Every historical guard
runs normally. Its returned state projection must equal the historical one;
the result then retains the ACTUAL five-rule projection. A separate account
read's whole-account digest and the complete 13-field snapshot must match the
pinned actual after state. No broad normalization or arbitrary filtering.

The original strict read transport, verified TLS, no redirects and finite
settings-list POST read allowlist are retained. Context and function bindings
restore on exceptions, including context-entry failure. Original source and
guard behavior outside the private context are unchanged. Existing transport
helpers temporarily bind shared transport functions; they are scoped and
restored, not a thread-isolation guarantee. Use a single exclusive parent
process, not concurrent live collectors in one interpreter.

## Durable failure and no replay

Future explicit Oct30 preparation failures retain an exclusive fsynced sibling
failure receipt with finite error/phase codes, PID/time and no exception text,
response bodies, arbitrary class names, settings, tokens or locals. The receipt
blocks retry of that package name and preserves the historical UNKNOWN error.
It is a partial-progress stop, never a successful capture/acceptance receipt.
Neither the old failed coordinator nor its artifacts may be replayed/restamped.

## Parent gate

This adaptation performs no prepare, cloud read/write, Send, Terraform or build.
Tests use only fixtures and local pinned evidence. The old173 source hashes must
remain exact; historical 207-source evidence stays immutable but new unbound
Oct30 sources necessarily need a fresh source set in any later freeze.
Historical full-native binding failure is not waived. Independent parent source
review is REQUIRED BEFORE separately authorized fresh read-only preparation.
No package/manifest/window/approval/browser-preflight is synthesized here.

The existing [parent CLI](../scripts/deployment/auto_path_oct30_parent.py) remains
the future entrypoint, with `prepare` and genuine new test receipt paths only
after that review/authorization. `run-reviewed-window` additionally needs the
actual frozen manifest hash/page binding and six-stage approval. No exact live
ready CLI exists before those inputs: `ready_cli=false`.

Offline execution results and source hash are recorded separately after tests;
this document does not assert an unexecuted test or independent approval.