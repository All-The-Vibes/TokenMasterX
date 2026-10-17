# Native document runtime: measured result — October 9, 2026

**No demonstrated live optimization benefit.** The new explicit document
strategy passes its installed mechanism check. In the separate real-model
comparison, however, it changed **none of the seven candidate requests**.
Do not describe the small between-run token difference as compression savings.

## Baseline and comparison

The baseline is the same installed native Copilot execution path, gateway,
model, task inputs, allowed tools, outcome checker and accounting, with
`backend="none"`, `instruction="none"` and the local request policy disabled.
It is optimizer-off, not a different model or an uninstrumented stock client.
The native recovery tool definitions remain available in both configurations.

The configured alternative is actual pinned Ponytail plus actual pinned
Headroom, with `headroom_strategy="native-documents-v1"`, the existing
whole-original-input nonexpansion guard and a 60-second cooperative Headroom
budget. Configuration is not evidence that either component affected a request.

The frozen schedule used `gpt-6-astra`, low reasoning, a 2,048-token output cap,
four calls per task attempt, and one separately counted readiness call.
The fixed order was off/document, candidate/exact-code, candidate/document,
off/exact-code. No selective retry, policy promotion or statistical registry
reset occurred.

## Every real task attempt

Gateway-reported input plus output tokens, including every observed model call:

| Task | Off: outcome / calls / tokens | Configured alternative: outcome / calls / tokens |
| --- | ---: | ---: |
| Document handoff | Pass / 4 / 22,898 | Pass / 4 / 22,865 |
| Exact `fsutil.py` reading | Pass / 3 / 15,229 | Pass / 3 / 14,592 |
| **Whole two-task workload** | **2/2 / 7 / 38,127** | **2/2 / 7 / 37,457** |

- Descriptive difference: **670 reported tokens, or 1.76% lower**.
- Separate complete-body reference counts: **52,370 off; 51,725 alternative**.
- Both configurations: **zero accepted transformations and zero recoveries**.
- All four attempts completed, had known reported usage, passed the private
  answer checker and preserved their public task workspaces.
- Readiness is separate: **one call, 3,433 reported tokens, 5,215 reference
  tokens**. Across both configurations plus readiness the observed experiment
  consumed **15 calls and 79,017 reported tokens**.
- No Jev screen, policy-search call or runtime local-neural component was
  invoked by this study. This is not a complete inventory of hidden provider or
  native-internal computation.

Two authored tasks, one pair per task, are not independent population sampling,
repeatability evidence, a general quality claim or a release certificate.
The source-derived private checker is separate from the public task copy;
this native route is not an OS filesystem/network sandbox.

## Why this is not a savings result

All four candidate document preparations recorded
`headroom_no_eligible_sources`; all three exact-code preparations recorded
`headroom_intent_bypass`. The whole-input guard then restored the unaugmented
original request and omitted the proposed Ponytail instructions. Actual applied
instructions were `none`. The runtime did not start its Headroom component.

The native client chose ranged document reads. This implementation deliberately
does not grant source receipts to ranged `view` results; it also preserves the
newest-result and exact-code protections. The live document task therefore
never supplied an eligible older document to the compressor.

For each candidate request, the final recorded runtime input equals its own
unaugmented original. Consequently, for any deterministic tokenizer on that
representation, the sum of original-input tokens minus final-input tokens is
**exactly zero**. This input-effect statement is different from comparing two
independently generated task histories and outputs.

The 670-token between-run difference cannot be credited to compression or
Ponytail. Neither changed the model-bound content in these candidate requests.
This run verifies operational completion and conservative fallback, not active
compression efficacy.

One concrete source of between-run variation is read order: the off exact-code
run read the longer source first, while the candidate read the shorter schema
first. Their second-request reported input counts were 5,187 and 4,540
respectively. This is different model behavior, not a compressed representation
of the same input. No causal allocation of every differing token is claimed.

## What the implementation did prove separately

The explicit, default-off document mode uses the real upstream
`TransformPipeline`, retaining its default stage order and replacing one
`ContentRouter` configuration so that only native `view` is removed from its
excluded-tool set. Non-eligible messages are protected before upstream work,
system compression is disabled, and parent-side source, fence, recovery and
complete-input guards still determine whether a result is submitted.

The installed scripted native qualification (`native-002`) recorded:

- Six synthetic upstream requests and **zero real model calls**.
- Four accepted complete-request reductions, removing **1,262 reference input
  tokens** across those scripted requests.
- Exact native Root retrieval and actual native upstream-fragment delivery,
  including the **5,892-byte** stored fragment.
- Protected messages unchanged within the upstream pipeline, smaller changed
  final inputs, unchanged source/install pins and completed owned cleanup.

That flow deliberately exercises compression and recovery. Its input reduction
is mechanism evidence, **not** live task quality or whole-task savings.
The failed `native-001` and never-started `live-001` are retained.

## Earlier results are not replaced

| Experiment | Observed result | Meaning |
| --- | --- | --- |
| Eight-task local V4 | 1.43% fewer reported tokens; both 8/8 | Small fixed-workload result for local JSON compaction, with no Ponytail or Headroom execution |
| Six-task guarded combined profile | 4.9% more reported tokens; both 6/6 | Negative whole-workload result for that combined profile |
| This two-task native document diagnostic | 1.76% fewer reported tokens; both 2/2; no transformed request | No demonstrated optimizer effect |

Do not pool different workloads or use the latest small numerical decrease to
erase the earlier negative result.

## Next unresolved boundary

Ordinary native ranged reads are not yet an eligible source representation.
Any support for them must bind exact observed content and range semantics,
preserve source/status/newest/exact/edit/debug protections and exact recovery,
and be qualified before another predeclared efficacy study. Forcing full reads,
padding the corpus or weakening the guards to obtain activation is not a fix.

Native learning/evaluator coupling, write/debug workflows, feasible independent
evaluation, all-in coverage and release qualification remain open. No normal
profile, model weights or policy incumbent changed. The full goal is unfinished.

## Evidence and verification

Evidence root: `evidence/integrated-runtime-20261009/native-documents/`.

- `PLAN.md`, `REVIEW.md`: implementation contract and independent review.
- `native-002/summary.json`: installed mechanism result.
- `live-002/plan.json`, `plan-seal.json`: pre-inference configuration and seal.
- `live-002/summary.json` and all four attempt directories: complete schedule,
  saved answers, grades, raw requests/replies and runtime preparations.
- `live-002/activation-diagnosis.*`: independent per-request admission,
  applied-instruction and original-versus-submitted-wire verification.
- `live-002/independent-audit.*`: independent raw recount and regrade of all
  15 primary calls, matched recovery schemas, frozen inputs and recorded cleanup.
- `live-tasks/private/`: frozen source-derived oracle and offline checker.

The focused document/native-event/minimal-CLI regression passed **426 tests**.
The independent live audit passed and retained hashes for **175 unchanged
evidence/input files**, including all **49 installed package files**. Ruff
passes for 15 involved sources. MyPy passes for the 14 host sources under the
Windows target and the isolated worker under its actual Linux target, using
`--follow-imports=silent --ignore-missing-imports --check-untyped-defs`, not
strict mode. The earlier missing-tool and wrong-platform check attempts are
retained; no source suppressions or dependency installations were used.

The final full skill/core/host regression passed **4,209 tests plus 19 subtests**,
with **three skips and one existing Pydantic warning**. All 197 snapshotted
Python source files remained unchanged, and no Python source file was added
during the run. Evidence is in `full-regression-001/`. The 426 focused checks
overlap the full suite; their counts must not be added.

Passing software checks must not be presented as token-efficiency evidence.
