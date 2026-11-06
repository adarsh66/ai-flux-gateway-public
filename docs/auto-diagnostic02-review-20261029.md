# Diagnostic02 — offline compiler correction, parent review package

This is a new audited successor, not a retry of the consumed diagnostic01 PUT.
The original XML, manifest, native review, intent, HTTP400 receipt and sanitized
07:17:46 compilation failure remain untouched and are hashed into the successor.
No create, Terraform, historical offline PATCH, image build, UI build, online,
Send, scoring or completion operation is authorized by this package.

## Correction and full expression review

[Successor controller](../scripts/deployment/auto_diagnostic02.py) reuses the
[original guards](../scripts/deployment/auto_diagnostic_stage.py), without editing
them, under scoped temporary bindings restored on exit. The spawned one-shot
writer also explicitly binds diagnostic02; it cannot load diagnostic01's body.
Only prepare and policy-put are exposed. A new exclusive fsynced policy-put
intent is created only after the actual parent native review, fresh all13 and
supplemental baseline, same state ownership/nonce, actual offline flags, exact
predecessor XML and current opaque policy ETag checks. No generic reapproval gate.

The [official APIM allowlist](https://learn.microsoft.com/en-us/azure/api-management/api-management-policy-expressions)
explicitly allows DateTime.UtcNow and Ticks. ToUniversalTime, ParseExact and
SpecifyKind are NOT listed for DateTime. No runtime Parse/DateTimeStyles/local
timezone conversion is used. Python calculates integer .NET ticks from the UTC
year-one epoch, using integer days/seconds/microseconds only, and emits signed
64-bit literal bounds with L suffix. Start inclusive, end exclusive, fixed20min;
no silent refresh. Original access/IP/product/path, fixed benign input, safety,
PII, counter identities, terminal return and no retry guards are unchanged.

All expression-bearing attributes AND text in the actual entire rendered XML are
inventoried, not only the first rejected choose: all inbound, backend, outbound
and on-error branches, including unreachable copied code. The source-bound audit
lists each expression hash/location and every lexical member with its official
type-family review. Newtonsoft JSON/LINQ, generic collections, numeric/String,
Math, Encoding and DateTimeOffset used members are allowlisted; context,
IResponse/IMessageBody, dictionary extensions and LastError match documented APIM
interfaces. Constructors are JObject/JArray/Exception/List, allowed types.
The old copied DateTimeOffset.UtcNow.ToUnixTimeSeconds is in an All-members row.
The lexical inventory is deliberately NOT advertised as full C# type checking,
APIM compilation, policy schema validation or gateway runtime proof. Only the
actual reviewed offline PUT can supply APIM compiler acceptance; both exact
format exports must then match and revision2 must remain offline/noncurrent.

[Production Auto resolver](../gateway/policies/auto-resolve.xml.tftpl) already
uses only DateTime.UtcNow.Ticks at start/end for latency; no unsupported date
member found, no production template edit needed. Regression binds its exact
hash and both expressions. No UI source changes: no UI cloud rebuild required.

## Failure capture and review handoff

New wire implementation retains one bounded45s open, no redirects/SDK retry and
60s parent watchdog. On HTTP failure it reads at most65537 bytes in memory,
keeps only safe ARM error-code and recognized unsupported-member/type syntax;
never saves arbitrary messages, raw XML/error body, credentials or other headers.
Oversized/malformed/unrecognized messages remain suppressed. Any failure or
timeout consumes the new intent permanently; read-only reconcile only afterward.

Preparation emits immutable diagnostic.xml, policy-put.json, manifest.json,
expression-audit.json and actual fresh prepare-capture.json under the new
scoring-diagnostic02 directory. Manifest binds all historical evidence bytes,
all transitive controller source, tests/receipt, production template, window,
original state owner and baseline. Do not edit any bound source after prepare.

Parent has a working native independent reviewer. Supply the exact manifest,
XML, source/test/audit hashes and fresh baseline to it. Do not fabricate its
invocation/transcript. Parent binds its actual policy-put-parent-review.json
using the unchanged review contract: approved, independent_native_review, stage,
manifest_sha256, actual at_utc, transcript within package and transcript_sha256.

After that exact parent review, executable Python313 arguments are -X utf8 -u
-m scripts.deployment.auto_diagnostic02 policy-put. Source PYTHONPATH order:
services/control-plane/src, workspace root, existing .venv/Lib/site-packages.
Do not invoke auto_diagnostic_stage policy-put or any historical executor.
No generic CLI availability blocker: parent owns the native review and next PUT.

This successor cannot online or score. The inherited revision-path uncertainty
and later separately reviewed one-Send/cleanup contract remain unchanged.
Auto is off and the original13 current routes remain protected. A clean offline
harness is not a successful actual APIM compile and neither proves MI scoring.