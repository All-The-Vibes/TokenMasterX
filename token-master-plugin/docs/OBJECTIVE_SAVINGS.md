# Check token savings objectively

The question is **whether a policy completes the same verified tasks using fewer
total tokens**, not whether one prompt or tool result became shorter.

The offline checker recomputes counts from captured calls and checks their
inventories, hashes, task/model/control identities, and saved outcome evidence.
It makes no model calls, needs no API key, executes no generated code, changes no
policy, and performs no monetary calculation.

## Latest comparison and retention experiments

The latest [V3 repair report](CONSERVATIVE_POLICY_FIX.md) separates regression
neutrality from actual savings: the six original questions use **116,883
gateway-reported task tokens in each arm**, while four deliberate repeated-read
probes use **89,417 baseline versus 80,541 V3** (9.9% fewer). Every answer passes,
with equal request counts and zero recovery calls. All 20 planned attempts
are retained; no selective retries or automatic promotion occurred.

The 69-request offline replay is a separate passthrough check, not a live
savings claim. The probe percentage is not an estimate of typical usage.
The earlier [controlled scorecard](CONTROLLED_SCORECARD.md) and the studies
below remain historical evidence, including their failures.

### Earlier comparison and retention experiments

`COMPARATOR_RESULTS.md` qualifies the earlier positive headlines. In that
six-task four-arm study, TokenMaster and Ponytail both got 6/6 correct, but
TokenMaster used more primary-reference tokens: **224150 versus 195335**.
Headroom's HTTP 502 and the baseline's wrong answer remain in the accounting.

A separately frozen retention neighbor then used **62649 versus 100149**
reference tokens with 4/4 correct in both arms on four source-disjoint tasks.
Almost all of that difference came from one active trace. Jev abstained, the
candidate came from deterministic fallback, and no default was promoted.
Keep all search/learning overheads separate and visible; neither result is a
typical savings rate or a population certificate.

A fresh replication with clearer shared recovery instructions then produced
4/4 correct, 12 calls and 35,418 bridge-reported tokens in each arm. There were
zero transformed requests. Its 62,072 versus 62,041 reference counts reflect
captured-body variation, not an optimization effect. The positive retention
observation remains concentrated in its original single active trace.

The later predeclared three-repeat check reused that exposed active case with
clarified tools. Retain-1 made five calls including two genuine recoveries;
retain-2 made three, in every repeat. Both remained correct. Totals were
118,010 versus 61,213 reference tokens. This supports the recovery mechanism
on that case, not fresh-task generality or a promotion certificate.

## Earlier repository pilot

The October 8, 2026 UTC scoped-profile pilot completed four source-pinned
repository tasks correctly in each arm with 12 calls each. Full-body reference
tokens were **81,530 → 76,410 (6.28% fewer)**; separate bridge counters were
**55,603 → 51,868 (6.72% fewer)**. Task discipline and context views were enabled
together, so this is not a pure-compression estimate. All raw captures, exact
patch bytes, recovery and invocation receipts were checked offline.

See `CODING_VALIDATION.md` for that runnable command and the retained negative
and interrupted context-only repeats. The new repository receipt is
`evidence/combined-request-validation-20261008/offline-verification.json`.
The `verify_savings.py` command below targets the **earlier synthetic study**,
not this different repository-study format. Neither experiment is a population
certificate or establishes project-wide savings after all learning work.

## Earlier synthetic result: exploratory, not a general savings claim

The frozen `pilot-frozen-v2` study ran eight synthetic-workspace challenges in
two arms, in randomized order, using the same reported model (`gpt-6-astra`),
tools and call limits. The combined arm added scoped instructions and explicit
recoverable views. It was **not** a native Desktop run or a direct upstream
Ponytail/Headroom benchmark.

| Measurement | Baseline | Combined | Observation |
| --- | ---: | ---: | --- |
| Bridge-reported input tokens | 43,791 | 38,701 | 11.62% fewer |
| Bridge-reported output tokens | 1,908 | 2,075 | **8.75% more** |
| Bridge-reported total tokens | 45,699 | 40,776 | **10.77% fewer** |
| Full API-body reference tokens | 104,775 | 101,117 | **3.49% fewer** |
| Explicit-context reference input | 53,083 | 46,431 | 12.53% fewer; complete output unavailable |
| Verified outcomes | 8/8 | 8/8 | No observed failure regression |
| Model calls | 25 | 27 | **8% more** |
| Recorded task wall time | 74.234s | 88.343s | **19.01% longer** |

The two token totals have **different units**:

- **API-body reference:** exact local `cl100k_base` tokenization of every complete
  submitted/received JSON body, unchanged. Includes metadata, identifiers and
  ciphertext. This was the study's predeclared primary measurement; it is not a
  measurement of model-serving tokens.
- **Bridge-reported usage:** arithmetic validation of the usage counters returned
  by the configured bridge. No cache discount or reasoning double-counting.
  This is a post-hoc diagnostic, not independently authenticated upstream usage
  or a replacement primary metric.
- **Explicit-context reference:** a separately defined projection retaining
  messages, tools and call/result pairs. Encrypted reasoning makes a complete
  output total unknown, **not zero**.

**The aggregate is dominated by one constructed navigation/recovery case.**
That case saved 5,905 bridge-reported tokens while using seven calls instead of
five, including actual search and retrieval of the original. The proof case
saved eight reported tokens; the other six cases used more. Do not advertise
10.77% as a typical task saving or multiply it by component-level percentages.

Seven cases per arm passed deterministic/executable grading. The two complete
harmonic-sum proofs passed an arm-metadata-blinded mathematical review by the
principal assistant, recorded before opening the mapping. This was **not** human
review, a mechanized proof checker, Jev scoring, or a claim of independent
reviewer model weights.

## Run the offline check

From the repository root, using the existing development environment:

```powershell
$repo = (Get-Location).Path
$study = Join-Path $repo 'evidence\jev-quality-20261004\pilot-frozen-v2'
& "$repo\.token-master-dev\Scripts\python.exe" `
  "$repo\token-master-plugin\evals\verify_savings.py" `
  --study $study --use-recorded-reviews
```

The local study evidence is intentionally ignored by packaging; it is not
silently fetched from a service. On another machine, supply a complete approved
study directory and the existing runtime requirements.

To save a new receipt, add `--output <new-json-path>`. Existing files are never
overwritten. Keep the resulting `evidence_digest` outside the study's mutable
directory, then rerun with:

```powershell
& "$repo\.token-master-dev\Scripts\python.exe" `
  "$repo\token-master-plugin\evals\verify_savings.py" `
  --study $study --use-recorded-reviews `
  --expect-evidence-digest <previously-retained-digest>
```

**Exit 0 means the evidence is internally consistent—not that savings occurred
or a statistical test passed.** Inspect `comparison`, `quality`, and `statistical`.
Exit 2 rejects an invalid/incomplete corpus or mismatched receipt. Without
`--use-recorded-reviews`, pending proofs remain ungraded and efficiency wins are
blocked; the checker does not silently convert review-needed into success.

The checker:

1. Verifies the frozen source/vocabulary and exact declared case × arm × repeat
   inventory, including the oracle source identity.
2. Recounts each full input/output and verifies its saved digest and count.
3. Rejects missing/duplicate calls, partial capture, model/control/tool mismatch,
   opaque request state, orphaned/reordered conversation history, altered
   follow-up tasks, changed workspaces, and type-exact answer/event discrepancies.
4. Keeps complete failed calls in the numerator. Counts recovery-related model
   calls and replayed context; raw tool text is not added again.
5. Binds optional review labels to the exact blinded answer and original run.
   Failed calls must follow the pinned runner's terminal transitions; the same
   response cannot be counted as both primary work and shared setup.
6. Reports every task pair, complete token vectors, unknowns, outcomes and
   separate learning receipts. It does not trust `summary.json` totals.

The current import adapter is the explicit stateless Responses study format.
The underlying reference ledger and mathematical gate remain harness-neutral.
Other harnesses require adapters proving their own complete call inventory and
materialized boundary; changing a filename or supplying plausible counters is
not such an adapter.

The current integrated suite passes **1,121 tests**, including the subsequent
native-envelope work. Independent review also
retested the dropped-call, altered-follow-up, typed-answer, terminal-failure
and duplicated-preflight bypasses. The reviewed raw pilot retains evidence
digest `673749b407bac18d3ae89af0b25813abc30c6ba98d2a82f8d79a47d15a839bd3`;
its saved receipt is `objective-savings-v2.json`. Unit-test success and receipt
consistency remain distinct from real-model efficiency qualification.

## Mathematical interpretation

For arm \(a\), all task attempts and calls are included:

\[
T_a=\sum_{i,j}(I_{aij}+O_{aij}),\qquad
S_a=\sum_i Q_{ai},\qquad
\widehat J_a=T_a/S_a.
\]

Here \(Q_{ai}\) is the separately verified outcome, not a model confidence.
The ratio is undefined when outcomes are unknown or \(S_a=0\). The empirical
total reduction is

\[
\widehat R=1-\frac{T_{\mathrm{candidate}}}{T_{\mathrm{baseline}}}.
\]

This is a ratio of **whole-study sums**, not the mean of task percentages.
Input reduction does not establish total reduction; a lower total with newly
failed tasks does not qualify as an observed efficiency win.

These equations are accounting identities, **not population confidence bounds**.
Repeating a fixed, deliberately constructed challenge suite does not produce
fresh independent task samples. Consequently this audit reports **no confidence
interval, statistical certificate, promotion, or generalization claim**.

For that stronger claim, freeze the policy pair, outcome oracle, sampler,
measurement and enforced token cap before drawing fresh independent paired
tasks. Use the existing fixed/anytime registry gate in
[`TOKEN_EFFICIENCY.md`](TOKEN_EFFICIENCY.md), including cumulative error spending.
Search-exposed cases cannot be relabeled as fresh confirmation. Equal observed
quality can still leave the strict zero-regression gate inconclusive.

## Learning overhead and what is not observed

- The shared model-readiness call is counted separately: 1,138 API-body
  reference tokens and 23 bridge-reported tokens. It is not assigned to both arms.
- The later real Jev screening call has a sealed receipt for **3,056 reference
  tokens** (2,704 input + 352 output). Its raw bodies were not retained in this
  study, so the offline checker labels those counts **reported, not recomputed**.
- Jev proposed `min_tool_chars: 512 → 384`. A zero-model-call activation audit
  found three newly eligible texts but **no changed router output** on the
  recorded traces. No default or deployment policy changed; no gain is
  attributed to that proposal.
- The study runs themselves are evaluation/learning, not deployment. Earlier
  development, failed preflights and this review conversation are not a complete
  project-wide learning inventory. There is no declared deployment horizon,
  so **no all-in or amortized efficiency ratio** is claimed.

A receipt hashes evidence; it does not authenticate a provider, guarantee the
oracle is correct, prove that no unrecorded internal call occurred, or make an
unsigned corpus tamper-proof. These remain explicit trust assumptions.

## Counter semantics references

Official documentation checked October 5, 2026:

- [Responses usage fields](https://developers.openai.com/api/reference/resources/responses/methods/create#responses-create-response-usage)
- [Reasoning and usage](https://developers.openai.com/api/docs/guides/reasoning#managing-the-context-window)
- [Token counting limitations](https://developers.openai.com/api/docs/guides/token-counting)

These define OpenAI's contract, not proof that a third-party bridge implements
it faithfully. Missing `usage` is unavailable, not zero. Cached input and
reasoning output are subsets of their parent counters.
