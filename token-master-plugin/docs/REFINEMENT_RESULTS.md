# Refinement implementation and live results

**October 5, 2026. Exploratory development evidence, not a production certificate.**

## Decision

**Do not enable always-on self-refinement or cross-model critique by default.**
They are implemented and callable, but neither tested policy improved the
one-shot baseline under the frozen workload and limits. The existing production
optimizer, statistical gates, and incumbent policy were not changed.

The earlier missing representative workload and Desktop isolation prevented
broad qualification, not this no-tools synthetic experiment. This work closes
the implementation/testing gap for a small black-box refinement policy without
claiming full Ponytail/Headroom parity or changing foundation-model weights.

## What was implemented

- Separate frozen-study CLI, never a change to the original quality pilot.
- One-shot, four-sample plurality, and four-stage
  initial/continuation/critique/correction policies.
- Same-model and cross-model critique; explicit requested and reported model
  identities, API mapping, and policy hashes.
- Native Responses and Messages adapters through the existing credential-free
  loopback bridge. No credentials were discovered or persisted.
- Fresh seeded exact-answer scheduling, path-counting, conditional-probability,
  and integer-optimization tasks. Independent deterministic oracles; models
  receive problem text only and have no tools or access to gold answers.
- Bounded calls, input/output controls, local client deadlines, complete raw
  capture, no retries, no silent answer carry-forward, and stop on HTTP 429.
- Offline source/case/inventory/prompt/selection/outcome/token audit. Missing
  usage stays unknown; an audit is not provider authentication.

`REFINEMENT_EXPERIMENT.md` defines the controls and reproduction interface.

## 1. Same-model comparison: eight fresh tasks

Source-frozen v1; requested/reported `gpt-6-astra`; identical task pairs,
randomized arm order; maximum 1,024 output tokens per call.

| Policy | Correct | Calls | Bridge-reported tokens | Complete-body reference tokens | Recorded task seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| One-shot | **8/8** | **8** | **5,909** | **57,388** | **101.952** |
| Four fresh samples + plurality | 7/8 | 29 | 21,776 | 201,022 | 374.313 |
| Four-stage self-refinement | 7/8 | 32 | 23,785 | 172,722 | 317.673 |

Self-refinement used **4.03 times** the bridge-reported tokens and **3.12 times**
the recorded task time of one-shot, with one fewer successful task. Full-body
reference totals increased by 3.01 times. These are distinct declared metrics,
not interchangeable measures of hidden computation.

### A real harmful revision

For `path_counting-01`, the refinement policy initially answered **1397**, which
the exact oracle verifies. Its continuation changed the answer to **1712**;
critique/correction retained that wrong answer. All eight refinement initial
answers were correct; seven final answers were correct.

Thus, within this small trace set, there were zero wrong-to-correct changes
and one correct-to-wrong change. A plausible critique is not a correctness
oracle. No learned controller should promote a change because it sounds more
confident or uses another pass.

The plurality arm's failure was different: its first `path_counting-02`
response reached `max_output_tokens`. The predeclared policy stopped rather
than hiding the failed attempt or spending three replacement calls. That
explains 29 rather than 32 calls. It is a policy failure under these controls,
not a claim that every completed plurality answer was mathematically wrong.

## 2. Cross-model comparison: four different fresh tasks

Source-frozen v3. GPT uses `/responses`; Claude uses `/messages`. The observed,
explicitly pinned Claude mapping is request `claude-opus-5.5` to response
`claude-opus-5-5`. This is a recorded provider identity, not independent access
to or verification of the underlying weights.

| Policy | Correct | Calls | Complete-body reference tokens | Recorded task seconds |
| --- | ---: | ---: | ---: | ---: |
| GPT one-shot | **3/4** | 4 | 30,797 | 53.186 |
| Claude one-shot | 2/4 | 4 | 9,757 | 40.953 |
| GPT with Claude critique | 2/4 | 12 | 59,727 | 120.439 |

Cross-model refinement did not beat GPT alone on this sample. Its
bridge-reported raw sum was 10,666 tokens, comprising GPT 6,975 and Claude
3,691. GPT one-shot reported 3,113; Claude one-shot reported 5,100. **Different
providers' native tokens are not equivalent compute units.** Body-reference
tokens also include provider-dependent metadata/ciphertext and must not be
used to rank underlying model compute.

All five unsuccessful policy runs in this comparison reached output limits:

- GPT one-shot and cross-refinement both stopped on the scheduling task's
  initial GPT response.
- Claude one-shot stopped on scheduling and path-counting.
- Cross-refinement stopped on the path-counting critique from Claude.

The completed final answers were correct. This finding is therefore about
the specified policy **under the fixed 1,024-token-per-call setting**, not proof
that cross-provider refinement can never work at another setting.

No output-limit relaxation or outcome-driven retry was performed. No evidence
shows a cross-model correction rescued a wrong answer: its two completed
refinement traces started and ended correct.

## 3. Integration failures were retained, not erased

Before v3, two frozen protocol studies exposed and fixed actual integration
issues:

1. **V1:** Responses rejected Claude with HTTP 400,
   `unsupported_api_for_model`. Its declared fallback ran GPT controls only.
2. **V2:** native Messages succeeded at HTTP level but reported the hyphenated
   model identifier. The strict identity check failed rather than silently
   accepting an alias. Its four fresh GPT control tasks passed 4/4, using
   2,701 bridge-reported task tokens. This compatibility phase is not pooled
   into either comparison above.
3. **V3:** the explicitly frozen mapping passed both readiness checks and
   completed the mixed-provider experiment.

These API/identifier fixes do not alter the old captures or retroactively turn
a failed readiness check into a success.

## 4. Complete experiment accounting

| Phase | Attempts, including readiness | Execution seconds | Complete-body reference tokens |
| --- | ---: | ---: | ---: |
| V1 same-model controls | 71 | 797.297 | 432,441 |
| V2 API compatibility/control | 6 | 51.157 | 29,459 |
| V3 cross-model comparison | 22 | 218.734 | 101,751 |
| **Total** | **99** | **1,067.188** | **563,651** |

This stayed below the original **114-request and 1,200-execution-second**
allowances. The elapsed total is the sum of script execution periods; it does
not include source freezing, offline recounting, implementation, review, or
local tests. It is not the elapsed time of this entire development chat.
Reference-token thresholds were per frozen study, not one combined 500,000-token
project allowance. No hard bound on proprietary or hidden compute is claimed.

Whole-experiment native usage remains **unknown** because the rejected
compatibility probes did not provide complete usage. Their literal requests
and responses are included in the reference recount. Cache components were
not discounted; reasoning breakdowns were not added twice.

“All-in” here covers these scripted experiments and readiness calls, not
earlier research, implementation/review assistant calls, previous studies,
other agents, or unobserved upstream activity. Net project-wide learning
savings remain unknown.

## 5. Evidence and interpretation

Under the repository's ignored `evidence/refinement-20261005/` directory:

- `study-summary.json` binds the three source-frozen studies and receipt hashes.
- `live-v1/`, `live-v2-native-messages/`, and `live-v3-pinned-native-id/` each
  contain the manifest, frozen source, vocabulary, exact-answer task inventory,
  raw captures, saved results, readiness checks, and offline audit.
- All three audits reported **consistent**. All **35** frozen source-file
  hashes across those studies were rechecked without mismatches.
- Current disjoint test suites: **1,332 plugin tests + 40 host-harness tests =
  1,372 passed**, with no failures/errors/skips; one nonfatal MCP/Pydantic
  warning. Ruff passed, and configured mypy passed on five implementation
  files. The initial six test-fixture failures and their clean rerun are
  preserved separately; no recorded model result was modified to obtain a pass.

Each study is a small, seeded, non-IID challenge set. They share task families
but have different parameters and API contracts; do not pool their success
counts as one paired experiment. No population confidence interval, continuous
improvement theorem, statistical acceptance certificate, or production
promotion follows from these results.

The relevant mathematical lesson remains:

`expected tokens / success probability` improves only when proportional
success improvement exceeds proportional token growth. These observed
policies did not meet even that descriptive objective, much less the existing
strict joint quality-and-token promotion gate.

## Next engineering decision

Keep the new policy experimental and retain the incumbent. A future study
could test verifier-triggered repair on a task distribution with demonstrable
baseline failures, while counting the verifier, routing, and recovery work.
That would be a separately frozen candidate—not a reason to silently loosen
this run's limits or turn Jev confidence into truth. Jev was deliberately off
here to isolate refinement; this experiment does not establish real-model
improvement from the Jev hill-climbing controller.
