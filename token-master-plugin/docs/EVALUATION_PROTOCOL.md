# Real-workload qualification protocol

This is the stronger **qualification protocol**, not a claim that qualification
is complete. A separate eight-pair real-model challenge study and offline
recount are now recorded in [`OBJECTIVE_SAVINGS.md`](OBJECTIVE_SAVINGS.md).
That non-IID pilot, native mock-provider checks and the constructed synthetic
evaluator cannot close representative-workload or statistical qualification.

## Freeze before evaluation

Record immutable identities for:

- Repository/task-generator revision and sampling procedure.
- Exact host and model versions, available tools, sandbox and instruction set.
- Incumbent and candidate policies; source pins for any comparison baseline.
- Outcome oracle, critical failure categories and evidence format.
- Reference tokenizer/version/vocabulary, complete-body extraction protocol,
  observable boundary and how missing calls are detected.
- Whole-task token cap, maximum calls/retries/recovery and termination handling.
- Minimum expected token reduction, total alpha, fixed sample size or anytime rule.

Use one intact registry for the error-budget family. Do not create a new database
to retry unfavorable results or pretend previously exposed tasks are fresh.
Search-exposed tasks must be excluded before screening, including rejected,
baseline-validation and interrupted work. Model-produced confidence is not the
outcome oracle.

## Required strata

| Stratum | Independent evidence |
| --- | --- |
| Explain-only source question | Correct answer plus unchanged workspace |
| One small fix | Hidden regression tests and no unrelated edits |
| Explicit reusable abstraction | Requirement completion; requested abstraction not suppressed |
| Deep proof/architecture request | Assumptions, derivation and required detail retained; not merely short output |
| Structural graph question | Source-checked edges, ambiguous names and stale-index cases |
| JSON exact/aggregate/exhaustive task | Known exact values/order/counts; middle anomalies, null/missing and heterogeneous rows |
| Failing log/debug task | Rare failure and causal context remain available; no error masked |
| Navigation/overview with later detail | Exact root/fragment recovery, latency and all extra model calls |
| Unicode/large result | Complete paged reconstruction and wire-byte caps |
| Mixed media/unsupported protocol | Safe passthrough; no fabricated completeness |

Use blinded requirement/maintainability review where tests cannot supply a
complete oracle. A rubric must distinguish “not attempted”, “incorrect” and
“correct”; fewer lines or shorter answers are not correctness.

## Runtime capture

Capture every full submitted/received textual body under the pinned protocol.
Record stable call/task/attempt IDs, parent links, phase, role, model, coverage,
terminal status, reference counts and input/output hashes. Retain sensitive
payloads only in an explicitly approved location; hashes are not encryption.

The independent adapter supplies the complete expected call inventory.
Unobserved reasoning, multimodal payloads and provider additions are outside the
declared boundary, not zero. An opaque incremental transport cannot be compared
against a fully materialized request without reconstruction.

Baseline validation also requires a reserved allowance and explicit trace.
Deterministic local checks declare zero model calls with a complete empty trace.
Failures, retries, auxiliary Jev calls and model-based validation consume their
observed tokens; unknown failed capture keeps the learning report incomplete.
Seal each completed learning run's exact task inventory.

## Pairing and inference

1. Draw fresh independent tasks only after freezing the comparison.
2. Randomize/interleave incumbent and candidate execution to reduce order effects.
3. Execute both under the same declared limits; do not clip over-cap observations.
4. Use the independent oracle on actual artifacts/answers.
5. Submit both full traces and evidence digests to the registry.
6. At the predeclared look, evaluate the strict gate in `TOKEN_EFFICIENCY.md`.
7. Promote only a registry-saved passing certificate for the still-current
   incumbent and exact frozen regime. Otherwise retain it.

Report raw paired outcomes, failures, complete token vectors, rejected candidates,
learning overhead, uncertainty, unsupported cells and all inconclusive gates.
For equal observed quality the strict finite-sample zero-regression gate remains
inconclusive. Do not silently reinterpret “all observed tasks passed” as proof of
zero expected quality decline.

`evals/verify_savings.py` audits the current explicit stateless study adapter
offline: it verifies source/vocabulary, run/call inventories and outcome hashes,
recounts complete literal bodies, and keeps bridge-reported usage in a separate
post-hoc diagnostic. It never issues certificates. Repeats of the same non-IID
cases are not treated as fresh independent samples, so it emits no population
confidence interval. Missing usage and pending review remain unknown.

## Interaction and parity

Compare a declared baseline, scope discipline alone, graph acquisition alone,
views alone, and their combined policy when the workload supports those arms.
Their savings overlap: do not add or multiply component reduction percentages.
Include negative controls where the incumbent is already concise.

Ponytail/Headroom comparison requires the exact pinned upstream versions and the
same workload/model/tool boundary, with permissions and optional engines stated.
Matching command names or a smaller isolated tool result is not parity.

## Current unclosed boundaries

- Broader comparator qualification: pinned Ponytail instructions and the actual
  Headroom native/ML request pipeline now execute; a bounded four-arm primary
  study also completed. Those observations do not establish representative
  parity. `PARITY_RUNTIME.md` and `COMPARATOR_RESULTS.md` record exact boundaries.
- Representative real-model, independently graded paired task study.
- Representative blinded behavioral qualification of scoped discipline and
  requested depth, beyond the now-completed bounded proof/explain/fix challenges.
- Strict Codex CLI user-skill isolation in the tested Windows build.
- Codex Desktop runtime acceptance without changing the real desktop profile.
- Native versions/protocols beyond the now-tested 11-cell Claude 2.1.289 matrix;
  see `NATIVE_ENVELOPES.md`. The matrix and installed-settings lifecycle are
  transport-only and do not close the real-model qualification above.

Until these are resolved, describe the implemented capabilities and narrow
transport/exploratory evidence, not production-wide parity or certified
real-model savings.

Three matched repeats of an already-exposed active retention case reproduced
fewer genuine recovery calls with retained-2 under clarified tools. This is
mechanism evidence, not fresh confirmation: do not feed those exposed cases
into the registry as unseen tasks or silently relax the strict quality gate.
