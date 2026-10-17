# Conservative request-policy repair

October 8, 2026. **Implemented and verified locally. V3 is explicit and opt-in;
normal host profiles are unchanged.**

## Measured result

The new frozen run completed all 20 planned task attempts without retries,
unknown usage, or failed answers. Baseline and V3 used the same model label,
questions, instructions, tools, limits, and paired execution order.

| Workload | Passed, baseline / V3 | Model requests, baseline / V3 | Gateway task tokens, baseline / V3 | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Six original reading questions | 6/6 / 6/6 | 23 / 23 | 116,883 / 116,883 | 0.0% |
| Four deliberate repeated-read probes | 4/4 / 4/4 | 18 / 18 | 89,417 / 80,541 | 9.9% |

**Interpretation:** the earlier overhead is absent on the six-question
regression workload. It now matches baseline; it does not save tokens there.
On the separate, deliberately redundant probe workload, V3 avoids **8,876**
gateway-reported tokens with the same request count and all answers correct.
Neither arm made any recovery-tool call in either suite.

Do not report the previous 33.0% penalty as a new 33.0% savings rate. Do not
report the probe's 9.9% as typical production savings. This is one exposed
regression pass and four dependent mechanism probes, not a population
certificate, coding qualification, or new Ponytail/Headroom parity experiment.

### Input and output separately

| Workload and arm | Gateway input | Gateway output | Total |
| --- | ---: | ---: | ---: |
| Six questions — baseline | 115,345 | 1,538 | 116,883 |
| Six questions — V3 | 115,345 | 1,538 | 116,883 |
| Repeated reads — baseline | 88,377 | 1,040 | 89,417 |
| Repeated reads — V3 | 79,501 | 1,040 | 80,541 |

### All four repeated-read probes

| Probe | Baseline tokens | V3 tokens | Tokens avoided | V3 transformed requests |
| --- | ---: | ---: | ---: | ---: |
| Recovery entry source — protected negative control | 14,501 | 14,501 | 0 | 0 |
| Recovery store source — protected negative control | 18,154 | 18,154 | 0 | 0 |
| Rust hook source — eligible exact duplicate | 25,104 | 21,754 | 3,350 | 2 |
| Rust compressor source — eligible exact duplicate | 31,658 | 26,132 | 5,526 | 2 |

These probes retain real, unchanged pinned source; there is no artificial
padding or change to the expected answers. The repeated reads were instructed
in advance in both arms and remain in the accounting. The two negative controls
contain literal recovery-marker syntax and therefore stay unchanged.

### Accounting boundaries

There are **82 task requests plus one shared readiness request**. Readiness
reported 10 input + 5 output tokens and is not assigned to either arm.
The captured gateway batch, including both arms and readiness, reported
**403,739 tokens across 83 observed requests**. This is experiment usage, not the
runtime usage of one configuration, a complete development/learning-overhead
ledger, or a claim that prior research is amortized.

Primary figures above are captured **gateway-reported** input plus output,
not independently authenticated serving counters or hidden upstream compute.
Full API-body reference counts remain separate:

| Workload | Baseline reference tokens | V3 reference tokens |
| --- | ---: | ---: |
| Six questions | 168,070 | 168,058 |
| Repeated reads | 132,546 | 122,641 |

The 12-reference-token difference in the unchanged six-question workload is
captured-body/metadata variation, not policy savings. The readiness reference
count is 1,114; these counts include API metadata and opaque fields and are not
substitutes for the primary metric.

## What was wrong

The earlier V2 policy shortened requests by removing unique source bodies.
Models then requested that content again. The controlled reading scorecard
showed 33.0% more whole-task gateway-reported tokens for the retained-two
configuration than baseline, despite all answers passing.
Its additional task-mode instructions also increased request size.
Those historical results remain in `CONTROLLED_SCORECARD.md`.

## What changed

`request-policy-v3` never calls the lossy compressor or external recovery
callbacks. It keeps every unique source body.

It can replace an older duplicate only when:

1. Both reads have successful, executor-issued receipts bound to their actual
   tool calls, paths, and exact UTF-8 contents.
2. The tool name and path match, and the complete strings are identical.
3. An earlier full original remains unchanged and visible in the same request.
4. The target is outside the protected prefix, exact-message set, and recent
   result window. Ambiguous marker-containing content is left alone.
5. The complete serialized request has fewer measured reference tokens and
   no more UTF-8 bytes; all configured budgets still hold.
6. Expanding every accepted reference reconstructs all original messages exactly.

The marker identifies the earlier visible tool call. It is not a new tool,
an external storage reference, or an instruction added to the system prompt.
The conservative evaluation configuration adds **no task-mode instructions**.
The executor adapter also retains the correct model-facing name when
`fetch_artifact` delegates to the exact `read_file` implementation.

Explicit V1/V2 policies remain available for historical use. Their core
transformation semantics, the disabled constructor default, and promotion gates
are unchanged. The new live study uses frozen code; old studies are not rewritten.

## The precise guarantee

Let \(H\) be the original message sequence, \(D(H)\) the accepted request, and
\(R\) the verified expansion operation. A changed target \(j\) can refer only to
an earlier, unchanged source \(i\) with identical content. No source is another
replacement target. Every other message field is unchanged. Therefore, replacing
each marker with its still-visible source reconstructs every message:

\[
R(D(H))=H.
\]

Each accepted replacement also passes a whole-request comparison. By induction
over accepted replacements, a transformed request has strictly fewer tokens
under the declared reference tokenizer and serialization, and no more bytes.
If the checks fail, the original request is returned.

**This does not prove identical model behavior or lower complete-task usage.**
A model may respond differently to a reference. Gateway tokenization can differ
from the local reference counter. Correctness, all model requests, retries,
recovery, and input plus output tokens still require empirical measurement.

## Explicit local use

The CLI is `skills/token-master/brainspace_tools.py`. For a materialized
Chat Completions request, select:

```text
--workspace WORKSPACE request --conservative
    --protocol chat-completions-v1
    --source-reads EXECUTOR_RECEIPTS.json
```

Supply the request JSON on standard input. The output is a diagnostic wrapper;
`plan.request` / `plan.serialized` is the request, not the entire CLI output.
If a harness adds wrappers or changes serialization, it must recheck the final
transport token/byte guard. No interceptor or global installation is implied.
Keep the original client-side history and plan each fully materialized request
again. A reuse marker is valid only while its original remains in that request;
do not persist the projected view as a replacement for the durable tool result.

The receipt file is a JSON array of `SourceReadInfo` records:
`call_id`, `tool_name`, `source_path`, `content_sha256`, and `status`.
Generate it from actual successful tool execution using
`SourceReadInfo.from_text`, not from model claims or request-body fields.
This is a trusted adapter contract, not cryptographic authentication.

`--conservative` and `--policy` are mutually exclusive. With no selection,
request planning remains disabled. Missing receipts or a missing exact local
tokenizer produce unchanged requests. Legacy V1/V2 additionally require an
explicit `--intent navigation` or `--intent overview`; their existing
fail-closed `conservative` intent default is intentionally retained.

The CLI conservative configuration and evaluated `ConservativeArm` share the
same policy: V3 enabled, minimum 512 characters, one recent result retained,
at most four replacements per request.

## Verification

The repair plan and pre-change reproduction are retained under
`evidence/conservative-policy-20261008/`.

- Regression tests exercise source preservation, exact reconstruction, hostile
  identifiers, corrupt receipts, missing counters, budgets, artifact aliases,
  CLI opt-in, and legacy compatibility.
- Offline replay checks all 69 baseline requests from the prior reading study.
  It is a fixed-history replay, not a counterfactual quality experiment.
- The fresh run contains the six original reading questions once per arm.
- A separate four-probe suite deliberately repeats reads from two of those
  questions. Two are eligible duplicates; two are negative controls containing
  protected recovery-marker syntax. These are not four independent new tasks
  or a representative workload.
- Policies, sources, questions, gold answers, grading code, paired order, limits,
  and measurement are frozen before requests. There are no selected retries.
- Primary usage is captured gateway-reported input plus output over every task
  request. Missing usage remains unknown. Full API-body reference counts and
  the shared readiness call are reported separately.
- The full regression suite runs alongside live collection. Wall times are
  retained, but this run is not used to claim a latency improvement.

### Evidence

Under `evidence/conservative-policy-20261008/`:

- `plan.md`, `before-reproduction.json`: pre-change contract and unique-body loss.
- `before-hashes.json`, `legacy-compatibility.json`: retained originals and
  byte-identical legacy transformation body.
- `offline-replay-final.json`: all **69/69** saved baseline inputs unchanged,
  no mutation, no transform/recovery callbacks, and **380,817 → 380,817**
  input reference tokens. This is not a task-savings experiment.
- `batch-001/manifest.json`, `source-manifest.json`: 47 frozen implementation
  and corpus files, policies, controls, and schedules.
- `batch-001/summary.json`: all 20 task outcomes and separate suite totals.
- Per-run `captures.jsonl`, `invocations.jsonl`, `source-read-info.json`,
  `plan-audit.jsonl`, and `result.json`: raw accounting and reconstruction evidence.
- `regression-tests.txt`: **2,196 plugin tests passed**, one existing nonfatal
  Pydantic dependency warning.
- `host-tests-final.txt`: **51 host-harness tests + 19 subtests passed**.
- `installed-copy-validation.txt`: **one additional test passed** after the
  full run had collected its inventory. The actual installer copies V3 and
  the copied CLI runs outside the checkout without changing host configuration.
  Total disjoint coverage: **2,248 tests + 19 subtests**, zero test failures/skips.
- `static-checks.txt`, `type-check-bodies-final.txt`: Ruff and MyPy, including
  untyped function bodies for the six implementation/evaluation files.
- `audit-live.json`, `audit-live.py`: independent raw audit **PASS**. All 20
  outcomes regraded, 82 task captures recounted, one readiness call separated,
  41 V3 plans reconstructed, and 47 frozen sources plus eight source-matching
  Python caches verified. No missing attempts, audit discrepancies, lost unique
  source bodies, or extra recovery/model requests were found.
- `final-test-inventory.txt`, `final-verification.json`: current collection has
  2,248 distinct tests; final checks verify all 211 audit-bound artifacts still
  match, and the 47 frozen source files match the current checkout.

### Implementation files

Under `token-master-plugin/skills/token-master/`:

- `brainspace/request_policy.py`: separately versioned V3 planner.
- `brainspace/exact_reuse.py`: pure duplicate planning and verified expansion.
- `brainspace_tools.py`: explicit conservative CLI and executor-receipt input.
- `tests/test_exact_reuse.py` and five `tests/test_conservative_*.py` modules:
  policy, CLI, adapter, workload/accounting, and offline replay regressions.

Under `token-master-plugin/evals/`:

- `source_read_adapter.py`: conservative arm and correct artifact-alias receipts.
- `run_conservative.py`: frozen two-arm, two-suite live diagnostic.
- `conservative_replay.py`: offline fixed-history verification.

The simplification is behavioral: replace lossy source rewriting and subsequent
external recovery with exact, request-local duplicate reuse. No new dependency
or model call is needed. Unique or uncertain content remains unchanged.

The implementation remains local and opt-in. No commit, push, release, normal
profile update, model-weight change, or statistical policy promotion was made.
