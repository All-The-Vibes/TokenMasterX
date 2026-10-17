# Controlled token-efficiency scorecard

October 8, 2026. **Decision: do not promote the updated policy.**

All 120 planned runs finished: ten distinct task types, four configurations,
three repetitions. This is not 120 independent tasks or a population estimate.
The two suites are kept separate. No failed attempt was replaced.

## Primary metric

Reported task tokens = sum of gateway-reported input + output tokens over
every task request, including recovery and failed attempts when usage is known.
A missing usage counter makes the complete total **unknown**, not zero.
These are captured gateway claims, not independently authenticated serving counters.

Payload/reference counts tokenize the complete captured API JSON, including
metadata and opaque fields. They are a secondary accounting measure, not pure
model usage. No monetary objective or conversion is used.

## 1. Six source-reading tasks, each repeated three times

| Configuration | Passed | Requests | Reported task tokens | Change vs baseline |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 18/18 | 69 | 350,649 | +0.0% |
| Ponytail | 18/18 | 69 | 437,865 | +24.9% |
| TokenMaster old | 18/18 | 84 | 492,615 | +40.5% |
| TokenMaster updated | 18/18 | 79 | 466,336 | +33.0% |

- Updated versus old: **5.3% fewer** reported tokens (26,279 fewer).
- Updated versus baseline: **33.0% more** (115,687 extra).
- Updated versus Ponytail: **6.5% more** (28,471 extra).
- Those directions hold in every repetition; all configurations passed all 18 runs.

### Where the extra work occurred

Original-content recovery requests: old **15**, updated **10**, baseline **0**, Ponytail **0**.
The updated configuration made 10 more model requests than baseline, matching its ten recovery requests.
Retaining two results reduced recovery overhead but did not eliminate it.
This is observed behavior in this suite, not a universal causal estimate.

Ponytail added instructions but did not reduce the request count or improve
the observed pass count here. It also used more tokens than baseline.

### Reported tokens by repetition

| Repetition | Baseline | Ponytail | Old | Updated |
| --- | ---: | ---: | ---: | ---: |
| 1 | 116,883 | 145,955 | 164,334 | 153,744 |
| 2 | 116,883 | 145,955 | 164,322 | 154,284 |
| 3 | 116,883 | 145,955 | 163,959 | 158,308 |

## 2. Four new code-edit challenges, each repeated three times

**Qualification: inconclusive for ordinary Python coding quality or token savings.**

| Configuration | Passed restricted checks | Rejected before behavior tests | Other failure | Requests | Reported tokens for all attempts |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 3/12 | 9 | 0 | 72 | 101,704 |
| Ponytail | 1/12 | 10 | 1 | 69 | Unknown |
| TokenMaster old | 1/12 | 11 | 0 | 72 | 106,019 |
| TokenMaster updated | 4/12 | 8 | 0 | 72 | 106,199 |

There were **9 passes, 38 pre-execution sandbox rejections, and one HTTP/API
failure**. The latter has missing reported usage, so Ponytail's full token
total is unknown. No executed submission was observed to fail the hidden
behavior tests in this batch; most submissions never reached those tests.

The tasks disclosed a restricted functional Python subset. The checker is
narrower than ordinary Python and rejects forms such as tuple-unpacking
comprehension targets, bare exception-class raising, and assertions. The
blanket statement that comprehensions are supported did not explain every
restriction. These rejections must not be relabeled as proven wrong algorithms.
A broader or more precisely specified execution environment is needed before
using this suite as normal coding-quality evidence.

**Both TokenMaster settings made zero request transformations and zero
recovery calls in this coding suite.** Their different model outputs, pass
counts, and small token differences do not demonstrate a retention-policy effect.
The raw gate verdicts remain preserved in scorecard.json; they are not a
general coding-quality or causal improvement claim.

The hidden tests and corpus were fixed before study requests. Policies,
instructions, cases, and safety restrictions were not retuned after results.
No generated candidate code was executed on the Windows host.

## Secondary payload/reference counts

| Configuration | Reading suite | Coding suite |
| --- | ---: | ---: |
| Baseline | 503,947 | 289,418 |
| Ponytail | 597,402 | 461,319 |
| TokenMaster old | 687,049 | 309,020 |
| TokenMaster updated | 650,026 | 308,738 |

Do not combine percentages from different counters or suites.

## Verification and limits

- **586 task requests + 2 readiness requests = 588 observed primary attempts.** Readiness is outside the task tables.
- **2,083 tests + 19 subtests passed** across
  the skill and host-guard suites; zero failures/errors/skips and one existing
  dependency warning. Unit tests do not establish benchmark savings.
- Ruff and targeted MyPy checks passed. A post-freeze working-copy annotation
  repair has the same normalized runtime AST; frozen study sources were not edited.
- The independent audit re-counted captures and regraded stored submissions
  with the frozen oracles. It is not an independently authored correctness
  specification or an external timestamp authority.
- The audit retains two earlier failed receipts: the auditor initially rejected
  generated bytecode caches, then compared unsynchronized provider and local
  clocks. Cache contents were verified against pinned trusted sources; chronology
  was repaired to use same-host evidence. No model run or outcome was replaced.
- Same recorded model label, tools and limits across configurations; order
  varied using seeds 0, 1 and 2. Hidden upstream routing/retries are unobserved.
- Exposed reading tasks and authored coding challenges are not a representative
  production sample. Repetitions are not additional independent task types.
- No confidence certificate, production parity, native Desktop qualification,
  or advanced-Jev benefit is claimed. Headroom was not rerun.
- Jev and policy search were off. Native agent development/review tokens,
  earlier experiments, and auxiliary compute are outside the task ledger,
  not asserted zero. There is no net project-wide savings claim.

## Decision and saved evidence

**Reject global promotion of this candidate.** It is less wasteful than the
old setting on the six-task diagnostic, but still loses to doing nothing.
Keep experimental artifacts for diagnosis; do not enable the setting by default.
No normal profile, model weight, or promotion gate was changed.

Evidence root: `evidence/controlled-scorecard-20261008/`

- `batch-001/scorecard.json`: complete original machine-readable scorecard.
- `batch-001/manifest.json`: frozen policies and measurement contract.
- `per-run.csv`: all 120 individual observations, with missing usage left blank.
- `audit-batch-001-v3.json`: passing independent audit; earlier receipts retained.
- `coding-rejection-causes.json`: isolated diagnostic examples, not new model runs.
- `validation.json`: tests, static checks, source integrity, preservation checks.
- `decision.json` and `goal.json`: decision and user-approved execution status.

The repository execution plan is in `ACTIVE_EVALUATION_GOAL.md`. The older app
goal remains incomplete; the available goal tool cannot rewrite its objective.
