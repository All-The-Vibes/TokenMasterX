# TokenMaster: harness-agnostic token efficiency

**Current scope — October 4, 2026.**

This document supersedes the monetary objective in the earlier research.
Pricing, invoices, credits, subscription plans, and monetary ROI are excluded.
Earlier source studies and reviewed proofs remain unchanged as historical
evidence; their financial framing is not the active product specification.

**Goal:** accomplish the same verified task with less observable token traffic
and less context pressure, without changing foundation-model weights.

## 1. Define a reproducible unit

Tokens depend on a tokenizer. Harness independence does not mean that every
model has the same tokenization.

Pin:

- A reference tokenizer \(\tau\), its version and vocabulary identity.
- A deterministic measurement serialization/extraction protocol \(S\).
- The model-call boundary and textual fields observable at that boundary.
- The task distribution, model versions, outcome oracle and measurement scope.

For a complete captured or faithfully materialized model input \(P\), let
\(\ell_\tau(P)=|\tau(S(P))|\). Preserve model-facing text, including literals,
whitespace, instructions, tool schemas and framing covered by \(S\).
Do not count arbitrary chunks separately and assume their counts add to the
tokenization of the joined request. Compare identical measurement versions.

These are **reference-token measurements**, not a claim to reproduce every
provider's internal chat template or hidden computation. Native token counts
may be retained separately, but must not be mixed with reference counts.
Heuristic estimates remain labeled estimates; they cannot prove an exact
reference-token nonexpansion claim.

## 2. Count the entire task trajectory

For all model invocations \(j\) involved in one deployed task:

\[
I_\tau=\sum_j\ell_\tau(P_j),\qquad
O_\tau=\sum_j\ell_\tau(Y_j),\qquad
T_\tau=I_\tau+O_\tau.
\]

- \(I_\tau\): cumulative input footprint, including replayed history.
- \(O_\tau\): returned textual-output footprint under the same protocol.
- \(T_\tau\): combined observable token footprint.
- \(P_\tau=\max_j\ell_\tau(P_j)\): peak observed model-input footprint, not
  an assertion about opaque internal context.

Retain the vector \((I_\tau,O_\tau,P_\tau,\text{call count})\), rather than
hiding every trade-off behind the combined total.

The sum covers the main model, runtime Jev decisions, retries, recovery calls
and model-based verification. Separate these by role for diagnosis, but
include all of them in the runtime total.

### Counting rules

1. A replayed token is counted again at every model-input event in which it
   appears. This measures logical context traffic, not unique stored content.
2. An output token and its later appearance in an input are distinct events;
   counting both is intentional.
3. Raw tool output is **not an extra additive token count**. It enters the
   total when included in a counted model input. Its raw/compressed sizes may
   be separate diagnostics.
4. Count the final representation, including recovery references and necessary
   wrapper text—not merely the compressor's intermediate string.
5. Cache reuse does not subtract tokens from a supplied request in this
   metric. Prefix stability can be a separate diagnostic, not a token saving
   unless less text actually crosses the declared input boundary.
6. Output footprint does not assert that each returned token was generated
   autoregressively. A decision model's structured response and a generative
   model's response can both have an observable textual footprint.
7. Hidden reasoning, server-added messages, non-text payloads and unseen
   auxiliary calls are **unobserved, not zero**. Label visible-only or partial
   traces explicitly; do not claim a complete internal-model token total.

Lower token footprint does not by itself establish lower FLOPs, GPU-memory
use or wall-clock latency. Measure timing separately under comparable setups.
No conversion from tokens or time into money is part of this framework.

## 3. Quality-normalized objective

For binary independently verified success \(Q_\theta\):

\[
J_\tau(\theta)=
\frac{\mathbb E[T_{\tau,\theta}]}
{\Pr(Q_\theta=1)}.
\]

On an evaluation batch, report:

\[
\widehat J_\tau=
\frac{\text{all observed runtime tokens, including failed attempts}}
{\text{number of verified successful tasks}}.
\]

Also report success rate and critical failure categories. Zero successes do
not imply zero usage; the ratio is undefined/infinite. For graded outcomes,
name the ratio tokens per unit of declared quality, not tokens per success.

The optimization contract is:

```text
Reduce reference tokens per verified successful task
subject to an explicit correctness requirement,
protected-evidence invariants,
and declared peak-context / execution limits.
```

Do not optimize a percentage reduction on one tool result while ignoring
extra calls, longer answers, failed tasks or restoration traffic.

## 4. Learning overhead remains visible—in tokens

Keep search/confirmation invocations separate from deployment invocations.
Let \(A_\tau\) be the token footprint of candidate generation, rejected
candidates, Jev screening and confirmation during a defined learning run.

For a predeclared deployment horizon:

\[
J_\tau^{\mathrm{all\text{-}in}}=
\frac{A_\tau+\sum_iT_{\tau,i}^{\mathrm{deployment}}}
{\sum_iQ_i^{\mathrm{deployment}}}.
\]

Do not count one invocation both in \(A_\tau\) and deployment totals.
Report runtime efficiency and learning overhead separately before reporting
this aggregate. Changing the horizon changes the aggregate; declare it
rather than choosing it after observing favorable results.

An optimizer that spends a large token budget chasing negligible reductions
is not efficient merely because the final prompt is shorter.

## 5. The mathematical improvement guarantee still applies

The earlier proof uses a bounded nonnegative quantity; it does not require
that quantity to be monetary. Specialize it to
\(T_{\tau,\theta}\in[0,B_\tau]\), where \(0<B_\tau<\infty\) is a valid
token-footprint bound for the declared measurement scope.

For incumbent \(a\) and candidate \(b\), use fresh independent paired tasks:

\[
X_i=Q_{b,i}-Q_{a,i},\qquad
Z_i=(T_{\tau,b,i}-T_{\tau,a,i})/B_\tau.
\]

Both differences lie in \([-1,1]\). Freeze the candidates and measurement
protocol before confirmation. With:

\[
\alpha_k=\frac{6\alpha}{\pi^2k^2},\qquad
r_k=\sqrt{2\log(2/\alpha_k)/n_k},
\]

promote only if:

\[
\bar X-r_k\ge0,\qquad
\bar Z+r_k\le-\eta_\tau/B_\tau,
\]

where \(\eta_\tau>0\) is a required expected token reduction.

**Proof.** Conditional on the prior search history, each one-sided
Hoeffding failure has probability at most \(\alpha_k/2\).
Union-bound both failures and then all confirmation rounds. Because
\(\sum_k\alpha_k=\alpha\), with probability at least \(1-\alpha\), every
promoted update preserves expected verified success and lowers expected
reference-token footprint by at least \(\eta_\tau\).
For positive incumbent success probability:

\[
\frac{\mathbb E T_{\tau,b}}{q_b}
\le
\frac{\mathbb E T_{\tau,a}-\eta_\tau}{q_a}
<
\frac{\mathbb E T_{\tau,a}}{q_a}.
\]

This certifies a defined token metric on a defined workload—not internal
computation or every possible future task. Additional constraints need their
own deterministic enforcement or allocated statistical error budget.

The prior limitations remain:

- Strict zero-regression may be inconclusive when quality is truly equal.
- A tolerated decline against each new incumbent can accumulate; use a fixed
  reference or an explicit quality floor and a valid ratio gate instead.
- Optional stopping needs time-uniform bounds or spending across looks.
- Reusing an adaptively exposed holdout is not fresh confirmation.
- Tokenizer, serialization, coverage, model or workload changes require a new
  comparison/revalidation; do not combine incompatible measurements.
- No claim of global optimality or infinite guaranteed improvement follows.

## 6. Jev and hill climbing

Jev can rank questions, representations and routing rules. Hill climbing,
restarts or reflective search can propose new policies. Neither may rewrite
the tokenizer, measurement protocol, outcome oracle or acceptance gate to
manufacture an apparent improvement.

```text
propose policy
  -> exact applicability / retention checks
  -> Jev-assisted screening on search data
  -> full-task paired evaluation
  -> token-and-quality certificate
  -> promote or retain the incumbent
```

A small supervised router is optional; explicit rules and thresholds are
enough for a first experiment. Foundation-model weights remain fixed.

The implementation priority is still to repair TokenMaster's existing
measurement/recovery defects before using its reports as optimization labels.

## 7. Harness-neutral measurement boundary

The core consumes a versioned trace contract—not a billing SDK:

```text
task_id, attempt_id, call_id, parent_call_id
phase: deployment | learning
role: primary | auxiliary | verification
model_id, harness_id                     # descriptive metadata
measurement_protocol_id, tokenizer_id
captured input/output or their retained references
reference_input_tokens, reference_output_tokens
coverage: complete_for_declared_boundary | partial | unknown
missing_or_opaque_components
completion_status, verification_result
```

Each adapter captures available calls at its own boundary. An opaque harness
may provide only a partial trace; it does not get a fabricated complete
score. Harness neutrality is a common contract, not a promise of universal
interception.

Boundary coverage must also be equivalent across compared harnesses. A state
handle or incremental transport delta is not a fully materialized model input.
Reconstruct equivalent input when possible; otherwise report a separate
transport-only/partial measurement and do not use it to claim a reduction
against full-context traces.

No financial fields or provider rate tables belong in the core objective.
Optional native counts and elapsed time stay separate diagnostics.

## 8. Current versus implemented

This is the active research specification, not a deployed measurement system.
Production code is unchanged. `check_metric_examples.py` checks synthetic
counting examples and the concentration substitution; it does not run a model,
tokenizer or host integration test.

The older economic notes, source evidence and original reviewed proofs remain
unchanged for provenance. Where their objectives conflict with this document,
this token-only specification takes precedence.
