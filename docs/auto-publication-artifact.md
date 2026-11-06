# Offline Auto production-release receipt

## Status and scope

[The builder](../scripts/deployment/auto_publication_artifact.py) supplies the
missing local packaging step for
[`auto_snapshot.publication()`](../services/control-plane/src/aiflux/auto_snapshot.py).
It has **no cloud, build, deployment, SQL/DDL, publisher POST, scoring, or runtime
launch path**. It does not collect evidence. Platform release only: no tenant
approval, enrollment, or database override is introduced.

**Actual full-production Auto proof is still missing. No production receipt or
runtime artifact was generated for this change.** In particular, diagnostic02
and probability-only/two-unconnected-choice diagnostic results do not prove the
production parser, native compilation, full candidate pool, provider routing,
or successful end-to-end Auto completion. The current production parser requires
`answers.route.type`, `answers.route.choice`, and probabilities for exactly the
profile's source-bound candidates. This tool does not relax that contract.

## Trust boundary—not cryptographic attestation

The caller supplies an explicit **operator-controlled, retained deployment
evidence directory**, not a list of allegedly successful hashes. File references
are relative paths plus SHA256 of actual local bytes. Referenced files must be
regular, bounded files inside that directory; links, hardlinks, reparse points,
absolute paths, traversal, duplicate JSON keys, and nonfinite JSON are rejected.
Consumed files are re-read before output. Complete current release sources are
also checked against their retained manifest.

This verifies **consistency of trusted deployment records**, not their origin or
truth. SHA256 is not a signature, an independent identity check, a trusted clock,
an immutable filesystem, or proof that a network request occurred. An attacker
able to fabricate or replace the entire trusted directory can fabricate mutually
consistent evidence. The release system/operator must enforce ownership, retained
immutability, collector authenticity, reviewer independence, credential hygiene,
and the provenance of native logs and gateway transaction captures. Do not select
an arbitrary upload or unit-fixture directory as this boundary. There is no
"accept fixtures", "skip review", or `runtime_verified` input switch.

The collector contract below is **new and intentionally fail-closed**. Existing
historical diagnostic records are not automatically converted to production proof.
No live collector or automatic migration is added. A trusted release collector
must retain actual records in this contract; missing records block packaging.

## Local interfaces

`prepare_artifact(trusted_root, manifest_name, package_path)` validates all proof
before creating any output directory. `read_local_receipt()` re-evaluates the same
retained evidence and checks receipt, settings, and package hashes. `manifest_name`
is a relative path within `trusted_root`; the package must be outside it, with an
existing parent. Both operations are offline. The module CLI provides `create`
and `read`, each requiring `--trusted-root`, `--manifest`, and `--package`.
Failures return nonzero (`2` through the CLI), not an unverified receipt.

Do not invoke creation with production paths until actual proof exists. The
[unit tests](../tests/unit/test_auto_publication_artifact.py) use clearly labeled
synthetic fixtures and pytest temporary directories only. Passing these tests is
not production verification and does not authorize runtime execution.

## Evidence contract, schema 1

All JSON roots are objects. A file reference has exactly `path` and `sha256`.
No digest-only replacement is accepted. Times are real collector timestamps in
explicit UTC (`Z` or `+00:00`), not future values or invented reconstruction times.
The tool checks their order within the authorized release attempt; it cannot
authenticate the collector's clock.

### Manifest and binding

The manifest has exactly:

| Field | Required content |
| --- | --- |
| `schema` | Integer `1` |
| `kind` | `auto-production-release-evaluation` |
| `release` | Nonempty `id`, `attempt_id`, `actor`; `stage = production-auto`; `started_at`, `finished_at` |
| `sources` | Reference to the complete current source-hash map |
| `snapshot` | Reference to the evaluated gateway defaults snapshot |
| `rendered_policy` | Reference to exact complete UTF-8 production policy rendering |
| `authorization` | Reference to platform release authorization and role evidence |
| `native` | Reference to actual native validation and rendering records |
| `readback_rawxml`, `readback_xml` | References to actual published policy GET records, both formats |
| `runtime` | Reference to the correlated production end-to-end evaluation |
| `review` | Reference to actual independent native release review |

Each primary evidence record has `origin = deployment-collector`, `collected_at`,
and `binding` with exactly `release_id`, `attempt_id`, `stage`,
`source_manifest_sha256`, `snapshot_version`, and `policy_sha256`. Here the policy
hash is of the exact candidate rendering bytes—not a caller-provided digest.
`runtime_verified` is rejected as a primary evidence input. The output value is
derived only after the entire validation succeeds.

`source_paths()` defines the required source set: project-route Terraform inputs,
gateway policies/catalog JSON, pricing/defaults, backend snapshot/config/router
and inventory/pricing implementation, plus the builder itself. Callers cannot
omit inputs. The backend's existing `defaults()` evaluates the snapshot locally
without database or tenant records; the retained gateway snapshot must equal its
version/profiles/candidate descriptor map. The snapshot embedded in the policy
must match too. Source drift requires a reviewed successor, not a bypass.

### Authorization, native validation, readback

* Authorization kind: `platform-release-authorization`; exact `actor`,
  `authorized_stage`, `authorized_attempt_id`. References `role_assignment`,
  `role_definition`, and `deny_assignments` retain actual metadata. Require the
  fixed gateway principal's unconditional account-scoped grant, matching role
  definition with Cognitive Services wildcard data action and no excluded data
  actions, and the trusted collector's complete empty deny-assignment result.
  Role metadata alone never establishes runtime access.
* The currently supported authorization budget is exactly three Auto requests,
  three score requests, three provider requests, no retries, maximum completion
  tokens `1024`, score timeout `5000` ms, response bound `65536` bytes. Its keys
  are `auto_requests`, `score_requests`, `provider_requests`, `retries`,
  `max_completion_tokens`, `score_timeout_ms`, and `score_response_bytes`.
  Authorization precedes native validation/readbacks and all observed requests.
  This authorizes evidence collection by the release system, **not by this tool**.
* Native kind: `apim-native-production-validation`; `exit_code = 0`, nonempty
  `run_id`, exact `policy_resource_id`, reference `log`, and `render_output`.
  Retain the actual log containing run and release/source/snapshot/policy binding.
  Render output has `renderer = terraform-console`, the exact `binding`, and
  the complete `policy` string matching candidate bytes. A newly composed JSON
  summary without retained actual native execution is not admissible proof.
* Readback records: `method = GET`, `http_status = 200`, correct `format`, exact
  `resource_id`, and a `response` reference to the actual ARM response with its
  `id` and `properties.format/value`. Both formats must match exact rendering
  semantically: XML attributes/element text/C# expressions remain significant;
  only inter-element indentation and at most one known XML-export entity layer
  are normalized. DTD/entities are forbidden. The evidence hashes retain actual
  raw readback files separately. Additionally the authoritative `rawxml` policy
  value must have exactly the rendering's UTF-8 SHA256, so settings bind the
  actual deployed policy content. The `xml` export is checked semantically and
  may have different wire bytes. A raw export whose only difference is whitespace
  still fails the stricter deployed-hash check; there is no silent hash rebinding.

The fixed target is the existing `aiflux-dev-unified` API policy under
`poc-ids-token-ex-apim`, not a diagnostic revision. The complete policy must have
inbound/backend/outbound/on-error sections, one embedded source-bound snapshot,
the fixed gateway client/Cognitive Services resource, fixed System One endpoint,
and five-second scoring timeout. The `Decision-1` endpoint, principal, client and
response contract are the same fixed values as the existing receipt reader.

### Actual production request proof

Runtime kind: `production-auto-end-to-end`; exact `native_run_id`,
`policy_resource_id`, `gateway_principal`, `gateway_client`; an `api_readback`
reference proving the exact API is current and online at path `dev/llm/v1`; and
three `requests` references, one per Balanced/Cost/Quality profile. An omitted
profile means Balanced. Each transaction must finish before runtime collection,
after authorized native validation and both policy readbacks.

Each request record contains its exact `binding`, `native_run_id`, nonempty unique
`request_id`, `policy_resource_id`, `started_at`, `finished_at`, `method = POST`,
`path = /dev/llm/v1/chat/completions`, and references to actual `request`,
`redacted_request`, `score_request`, `score_response`, `provider_response`,
`response`, and `gateway_trace` records. These are retained nonsecret benign
evaluation payloads, not just status flags. Keep request content private; never
retain tokens, subscription keys, or Authorization headers in this package.

Observed fields are `score_http_status`, `provider_http_status`, `http_status`
(all 200), `score_requests`, `provider_requests` (both one), `retries` (zero),
`score_endpoint`, `score_identity`, `score_elapsed_ms`, and
`provider_selected_model`. The gateway transaction evidence has:

* `kind = apim-production-transaction`, identical request/release/run/timestamps
  and policy identity, fixed `gateway_principal` and `gateway_client`,
  `authentication = managed-identity`;
* `payloads`: exact hashes keyed by the six payload reference names above;
* `observed`: those observed values plus `method` and `path`.

The trusted collector must derive this structured transaction from the actual
correlated gateway execution, not unrelated operator requests or invented
assertions. These records are not a new attestation protocol. They carry the
deployment boundary's trust and must be retained/reviewed with their original
execution evidence.

The builder checks the full score body: Decision-1, bounded redacted messages and
maximum tokens, source profile instructions, and descriptors for **exactly the
production profile pool**, not an unrelated two-choice diagnostic. Descriptor
JSON string indentation/key order may differ, but content may not. It requires a
bounded HTTP-200 response with `type = choice`, explicit `choice` in that pool,
finite probabilities, exact probability keys, sum tolerance `0.02`, maximal choice,
and the policy's deterministic ordinal tie selection. It then verifies the
selected provider, actual nonempty completion, unchanged completion/usage data,
returned routing profile/snapshot/no-fallback/failure-null fields, bounded
decision latency, normalized score usage, and unknown cost remaining null.

The review kind is `independent-native-release-review`, with final `verdict = PASS`,
nonempty `reviewer` different from release actor, exact `native_run_id`, and
`collected_at` after runtime collection. Its `reviewed` map must match the eight
exact manifest references other than review (sources, snapshot, rendered policy,
authorization, native, both readbacks, runtime). A `text` reference retains the
actual review, containing exact run/binding/reviewed hashes. Conditional review,
an unrelated native run, or historical diagnostics cannot substitute.

## Packaging, settings, and lifetime

Only successful complete evaluation can create an **exclusive new directory**.
It is owner-limited: POSIX mode `0700` with `0600` files, or a protected Windows
owner-rights-only inheritable DACL. ACL failure aborts before writing files.
Writes use exclusive creation, flush and `fsync`; POSIX also syncs the directory.
Write failure removes partial output. This is not a distributed transaction or a
claim of power-loss atomic directory publication on Windows; a release must use
the completed package and its read-back checks, never consume an in-progress
directory. The parent directory must itself be protected from adversarial
replacement; path checks do not replace OS isolation or defeat a privileged
concurrent writer.

The package contains the schema-1 receipt, a local settings-binding document, and
an integrity index. Settings bind `AIFLUX_AUTO_ROUTING_PUBLICATION_PATH` and
`AIFLUX_AUTO_ROUTING_PUBLISHED_POLICY_SHA256` to the exact package/receipt, with
`AIFLUX_AUTO_ROUTING_ENABLED = false`. They are **not applied**, no auto-enable
occurs, and no existing settings file is edited. Runtime visibility still uses
the existing reader and its separate release switch. Installation/activation is
outside this tool and requires the platform release boundary.

There is **no receipt expiry or tenant approval lease**. Authorization timestamps
bind the historical release attempt, not a rolling TTL. Policy/snapshot/source
changes require a successor release. The runtime reader intentionally checks
schema-1 fixed bindings, not the complete historical evidence bundle; therefore
its configured artifact path and configured policy hash must remain trusted and
protected. The stronger offline `read` operation revalidates the retained bundle
against current sources and detects tampered settings/receipt/package content.

## Validation for this change

Tests are offline synthetic parser/security/package tests, including no-evidence
failure without directory creation, full production-schema negatives, both XML
formats, source/snapshot/review/authorization mismatch, budgets, immutable-path
guards, exclusive creation, partial-write cleanup, receipt-reader compatibility,
and settings tampering. Database/API fixtures are not needed. No SQL DDL, runtime
probe, publisher POST, cloud build or deployment is part of this test workflow.
The source checkout must precede installed package copies on the Python import
path; packaging rejects an imported snapshot implementation outside the bound
checkout. Windows tests inspect the actual protected owner-only output DACL and
the package tests verify `fsync` calls, not merely permission/write flags.

Actual local validation on 2026-10-29: **96 passed, 3 deselected** across the new
artifact tests and the existing snapshot tests, with one pre-existing Starlette/
AnyIO deprecation warning. The three deselected tests require database/API runtime
fixtures and were intentionally excluded; no SQL DDL was run. Both new Python
files passed Python AST syntax parsing, and editor diagnostics reported no errors.
Ruff could not run because its native executable was blocked by Windows Group
Policy (`WinError 1260`); it was not retried or bypassed. All generated packages
were explicitly synthetic pytest temporary output; no production/runtime artifact
was generated, installed, or enabled.