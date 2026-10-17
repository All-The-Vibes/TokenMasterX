# Optional Jev advisory client

## Later real-metric screen — October 8, 2026 UTC

After the new source-backed four-arm comparison, one authorized request sent
only sanitized outcomes, call counts and valid policy neighbors. The existing
human-supplied credential was used process-locally, never printed or saved.
Jev returned HTTP 200 and **abstained**. Its decision was retained rather than
re-prompted until it chose a preferred answer.

The sealed learning receipt records **1163 input + 97 output = 1260 reference
tokens**, separately from **1992 input + 73 output = 2065 vendor tokens**.
Public body captures were checked for the credential before being retained.
No quality outcome, deployment gain or policy promotion is attached to that
screening call.

An independent zero-inference activation audit then found that keeping two
recent results was the only neighbor that changed any of the 28 recorded
incumbent requests. That **deterministic fallback**, not a Jev recommendation,
was frozen and tested on four new source-disjoint tasks. Both arms passed 4/4;
reference usage was 100149 versus 62649. The gain is concentrated in one trace
and includes a wrong recovery-tool selection in the incumbent. It does not
establish Jev's causal utility or repeatable population improvement.

See `COMPARATOR_RESULTS.md` and
`evidence/parity-agent-comparison-20261008/jev-retention-screen/`. The strict
promotion gate and normal host settings remain unchanged.

## Client contract and earlier verification

Verified against the official API reference on October 4, 2026, with a
source-only documentation refresh on October 7, 2026 UTC:
https://docs.typesafe.ai/api (the `.md` representation was retrieved with
stdlib `urllib.request`). The research memo is supporting evidence, not a
substitute for the independently retrieved contract.

## Public API

```python
from brainspace.jev import JevClient, Question

questions: dict[str, Question] = {
    "route": {
        "type": "choice",
        "instructions": "Pick a relevant route, or skip when none applies.",
        "criteria": {"keep": "Relevant", "skip": "Not relevant"},
    }
}

client = JevClient()  # Disabled; no key read and no network.
result = client.decide("invented example", questions)
assert result.reason == "disabled"
```

Constructor:
`JevClient(enabled=False, allow_network=False, timeout=10.0, max_response_bytes=1048576, max_request_bytes=1048576)`.
Both flags must be actual booleans. Timeout must be finite, greater than zero,
and at most 60 seconds; it bounds each blocking socket operation, **not total
elapsed time**. Request and response limits are 1–4,194,304 bytes. Oversized
serialized requests reject before credential access or network I/O.

An authorized caller must set **both** flags true and call
`decide(state, questions, data_classification="synthetic" | "sanitized")`.
This explicitly discloses the entire supplied state and questions to TypeSafe.
The classification is an attestation, not automatic sanitization; there is no
zero-retention claim. Authorization and any deterministic failure fallback remain
caller policy. This module does not authorize actions or certify correctness.

`Choice`, `Score`, `Noul`, their answer types, `Usage`, and `Payload` are
TypedDicts: use the vendor's wire dictionaries, not a second object protocol.
State/instructions support JSON strings, objects, and arrays. All nested values
must be JSON-native, with string keys, finite numbers and at most 64 nested
levels. Choice accepts 1–255 options; Score accepts 2–10 rubric levels. Noul's
optional criteria may use `true` and `false`. Unknown request fields are rejected.

`validate_request(state, questions)` returns a detached pinned request.
`validate_response(payload, questions)` returns a detached validated payload.
Both raise `ValidationError` with content-free `invalid_request` or
`invalid_response` codes. `Result.validate(questions)` rechecks an accepted
payload and returns a boolean.

## Transport and validation

- Fixed `POST https://api.typesafe.ai/v1/systemone`; fixed `jev-1.13.0`.
- Reads only `TYPESAFE_API_KEY` at call time, after gating/request validation.
  No key parameter, key discovery, configuration writes or credential storage.
- Stdlib HTTPS with ordinary certificate verification; proxy environment lookup
  is disabled. Redirects are denied, including 301/302/303/307/308. No retries.
- Reads at most the configured byte limit plus one detection byte, before UTF-8
  decoding. Duplicate JSON keys, nonfinite values and malformed shapes fail.
- Requires exact question IDs/types, exact probability keys, Choice membership
  and a maximal selected probability, `[0,1]` probabilities/confidence, and
  distributions summing to one within absolute `1e-6`.
- Score requires zero-based rubric keys, matching string rubric descriptions,
  and a score in range matching the probability-weighted expectation within
  absolute `1e-6`. The HTTP reference labels legend values strings, while the
  structured Score examples and Python response types also permit objects and
  arrays. For structured rubric descriptions, an object/array legend must
  match the requested JSON exactly, ignoring object-key order but not JSON
  types. A string legend retains the existing acceptance rule because its
  serialization is unspecified. String rubrics still require identical string
  legends. Confidence formulas/calibration are not re-certified.
- Requires exact response model and nonnegative integer native input/output
  usage (booleans rejected). Unknown JSON response metadata is preserved.

## Results and ledger boundary

`Result` has `ok`, `reason`, `request_text`, `response_text`, `payload`, and
`diagnostics`. Only accepted responses populate `payload`. Neither client nor
result repr includes credentials/state/body text. No logging or persistence
occurs; caller logging is opt-in and caller-owned.

`request_text` is the complete serialized UTF-8 JSON body actually prepared for
sending, excluding headers/credentials. `response_text` is the complete decoded
response body, preserving whitespace, including on fully received HTTP/schema
failures. No body is rewritten/redacted before reference-token measurement.
Missing/incomplete/oversized/undecodable text is `None`, **not a zero-token
measurement**. Byte counts are not token counts.

`Diagnostics` contains `attempts`, `http_status`, `request_bytes`,
`response_bytes`, `response_complete`, `native_input_tokens`,
`native_output_tokens`. Well-formed usage from a 200 response remains diagnostic
even if its decision is rejected. These provider-native counts must stay separate
from the caller's reference-token ledger. Partial bytes lost on transport failure
are not reconstructed; callers must classify such ledger coverage as incomplete.

Reasons: `ok`, `disabled`, `network_not_allowed`,
`data_classification_required`, `invalid_request`, `missing_api_key`,
`invalid_api_key`, `transport_error`, `response_too_large`,
`invalid_response_encoding`, `redirect_denied`, `http_error`,
`invalid_response`, `request_too_large`. No reason includes provider exception/body details.
Configuration errors raise content-free `ValueError`.

Offline validation uses synthetic fixtures and mocked HTTPS. On October 4, 2026,
one authorized synthetic request also returned HTTP 200 with validated Choice,
Score and Noul responses; the user key was process-local and not persisted.

The October 7 documentation check did not repeat inference. It confirmed the
pinned model remains documented and found a structured-legend compatibility
gap, reproduced and repaired with offline response fixtures. Official sources:
`https://docs.typesafe.ai/primitives/score` and
`https://docs.typesafe.ai/sdk/python/api/types/responses`.
The latter permits missing native usage in SDK types; this HTTP client still
rejects absent native integer counters rather than fabricating zeros.
The documentation's confidence example and stated formula disagree on one
rounded value. This client does not use vendor confidence as a correctness
label, authorization decision, or promotion certificate.

A separate authorized synthetic structured-Score check at
`2026-10-07T02:16:43Z` returned HTTP 200 from `jev-1.13.0`, with object-valued
legends for both rubric levels. It made exactly one attempt. The complete
observed JSON bodies accounted for 71 input + 89 output reference tokens;
separate vendor diagnostics were 345 input + 17 output tokens. The learning
inventory was sealed; no deployment/task-success metric or all-in savings
claim was created. The existing key stayed process-local and was not written
to a repository file. Raw bodies were not persisted; hashes, counts, types and
diagnostics are in `evidence/parity-refresh-20261007/jev-structured-live.json`.
This confirms the client contract, not quality gain or a promotion certificate.
`evals/jev_smoke.py` provides a reproducible explicit network check and a sealed
learning ledger. Native counts are not mixed with reference counts.

## Pilot-evidence screening, not automatic improvement

The subsequent real-model challenge study used actual synthetic-workspace model
actions and independent grading, not Jev-generated truth labels. A later Jev
call screened aggregate/per-case search evidence and selected the valid neighbor
`min_tool_chars: 512 → 384`, with other settings unchanged.

Its sealed learning receipt records **2704 input + 352 output = 3056 reference
tokens**. Raw bodies were not retained with that receipt, so the offline savings
checker does not call these independently recounted totals. This is separate
from the earlier API smoke and toy-controller learning inventories.

A deterministic activation audit inspected the 27 recorded combined-arm
requests. Three texts entered the new eligibility band, but no router output
changed. That required zero model calls. It is neither a global equivalence
proof nor evidence of token savings from the proposal; no default or deployment
policy changed. A genuinely activating candidate would still require fresh,
independent paired confirmation under the unchanged statistical gate.

See `OBJECTIVE_SAVINGS.md`. Keeping a candidate only when it has evidence of
improvement is compatible with hill climbing; inventing gains or repeatedly
spending calls on an inactive proposal is not.
