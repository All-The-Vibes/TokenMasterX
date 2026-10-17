# Frozen-model optimization: what can actually be proved

**Date:** October 4, 2026  
**Context:** TokenMaster source `426fc853389ddba4bc6e1dd35a28179a895c064f`.  
**Status:** mathematical design and research; not an implemented optimizer or measured improvement.

## Answer in one paragraph

Yes: keep the target model's weights fixed and optimize the **policy around it**.
Jev can cheaply propose or screen decisions; hill climbing or evolutionary
search can change that policy. However, the improvement certificate must come
from independently verified outcomes and valid statistics—not from the same
Jev score being optimized. We can prove conditional information-preservation,
statistical promotion safety, and convergence properties. We cannot prove
universal correctness, a global optimum from ordinary hill climbing, or
unlimited improvement from arbitrary black-box observations.

This note gives self-contained proofs for a deliberately simple design.
They are applications of standard mathematical ideas, not claims of new
research theorems. The accompanying primary-source memos distinguish these
arguments from published empirical results.

## 1. Formal problem: optimize the controller, not the weights

Let:

- \(M_w\): a fixed target model, with fixed weights/version \(w\).
- \(\pi_\theta\): a controller parameterized by \(\theta\).
- \(x \sim D\): a task and its starting environment drawn from a specified
  workload distribution.
- \(\omega\): model/tool randomness under that environment.
- \(Q_\theta(x,\omega)\in[0,1]\): a predeclared, independently measured quality
  score. For a binary verified-success measure, it is 0 or 1.
- \(C_\theta(x,\omega)\in[0,B]\), with \(0<B<\infty\): complete deployment cost, including Jev,
  retrieval, retries, model verification, cache effects, and allocated
  infrastructure work, counted once.

Define:

\[
q_\theta=\mathbb E[Q_\theta],\qquad
c_\theta=\mathbb E[C_\theta].
\]

For \(q_\theta>0\), the cost-per-verified-success objective is:

\[
J(\theta)=\frac{c_\theta}{q_\theta}.
\]

The name “cost per verified success” assumes binary \(Q\). For a graded
score, the same ratio is cost per unit of declared quality, not a count of
successful tasks.

This is not \(\mathbb E[C_\theta\mid Q_\theta=1]\): failures also cost money.
On independent repeated tasks, the observed total-cost / total-success
ratio converges to \(J(\theta)\) by the law of large numbers, provided
\(q_\theta>0\).

Typical policy variables, without changing \(w\):

```text
which structural query or source slice to request
which exact projection or representation to send
whether to compress or pass through a result
retrieval thresholds and bounded context budgets
cache-preserving assembly rules
when to restore original evidence
allowed reasoning/output budgets
when to stop, verify, or escalate
```

The optimization problem can be:

\[
\min_{\theta\in\Theta_{\mathrm{admissible}}}J(\theta)
\quad\text{subject to}\quad q_\theta\ge q_{\min}
\]

where \(q_{\min}\in(0,1]\), with additional safety/latency constraints. A syntactically admissible policy
is not automatically a semantically correct one.

### Assumptions that must remain visible

1. **Defined outcome:** \(Q\) measures the declared target, not merely whether
   another model likes the answer. If the validator only checks unit tests,
   the guarantee is about that verification procedure, not all possible
   interpretations of the user's intent.
2. **Stable regime:** \(D\), model versions, tools, prices, permissions and
   cost-accounting rules are fixed during the guarantee's scope. Define
   cold/warm cache conditions rather than mixing them opportunistically.
3. **Bounded cost:** \(B\) is a valid enforced upper bound. Silently clipping
   an unbounded cost to \(B\) only proves something about clipped cost.
4. **Fresh confirmation:** each candidate is fixed before its confirmation
   tasks are drawn. Those tasks are independent of the search history.
5. **Independent task units:** correlations within a task or paired
   comparison are allowed. Treating turns from the same task as independent
   trials is not.

These are mathematical assumptions, not properties established merely by
putting an API behind a wrapper.

## 2. Exact foundational limit: universal semantic compression is impossible

### Proposition 1 — collision obstruction

Let \(\mathcal X\) contain \(N\) distinguishable source inputs. Suppose a
query-independent compressor \(T:\mathcal X\to\mathcal Z\) has
\(|\mathcal Z|<N\). A downstream system sees only \(T(x)\) and a later query;
it has no original-content retrieval or other source-dependent side channel.

If the allowed query family can distinguish every pair of inputs, the system
cannot answer every query correctly for every source.

**Proof.** By the pigeonhole principle, some \(x\ne x'\) have
\(T(x)=T(x')\). Choose an allowed query \(q\) whose correct answers differ
on \(x\) and \(x'\). The downstream system receives the same \((T(x),q)\)
in both cases, so it must have the same output distribution in both cases.
It cannot assign probability 1 to two different correct answers. For a
balanced two-source example with two distinct correct labels, average
accuracy is at most \(1/2\). \(\square\)

**Consequence:** no hash, summary, clever prompt, or frozen auxiliary model
can provide universal answer-preserving compression of arbitrary future
queries without enough retained information or a usable side channel.
Retrieval changes the information available; it does not invalidate the
argument.

### Proposition 2 — query-relative sufficient information

For a fixed query family \(\mathcal Q\), define:

\[
x\sim x' \quad\Longleftrightarrow\quad
\forall q\in\mathcal Q,\ A(x,q)=A(x',q),
\]

where \(A\) is the desired answer function. If there are \(K\) equivalence
classes, any exact representation for all queries in \(\mathcal Q\) must
distinguish at least \(K\) states.

**Proof.** Combining any two distinct classes gives the same contradiction
as Proposition 1. Conversely, a class identifier is information-theoretically
sufficient if the answer lookup for that class/query is available. Therefore
a fixed-length binary identifier requires at least
\(\lceil\log_2 K\rceil\) bits. \(\square\)

**Important qualification:** information sufficiency does not prove that an
arbitrary frozen model understands the representation. It is a necessary
representation result, not a neural-decoding guarantee.

### An exact result we can use in software

If a declared query has the form \(A(x,q)=g_q(T(x))\), then returning \(T(x)\)
preserves all information needed for that query by substitution. For example,
for the precise question “count records whose status equals FAILED,” a
deterministically computed count is sufficient. For “which records failed,”
the IDs must also be preserved.

This is why typed, task-specific graph queries and data projections can have
stronger guarantees than generic word deletion. If the question changes,
the old sufficiency contract may no longer apply.

## 3. What Jev can and cannot certify

Jev is TypeSafe's decision model, not the name of an evolutionary optimizer.
Its official launch describes typed decisions. The current provider contract,
SDK source and the independent September 2026 evaluator study are examined
in the `jev` companion memo.

**Citation correction:** the relevant independent paper is *JEV vs. LLMs as
Rubric Judges*, arXiv `2609.29769v2`, first submitted September 24 and revised
September 28, 2026. The `2609.26301` pointer in my initial research note is
an unrelated polar-codes paper, not evidence about Jev. Its replacement is
explicitly identified rather than silently substituted.

**Direct precedent:** TypeSafe's autoresearch feature-discovery cookbook
combines generated questions, Jev features and a supervised learner without
updating Jev's weights. It is an empirical example, not the certificate
developed here. `COOKBOOK-ADAPTATION.md` separates that precedent from a
proposed TokenMaster implementation, including a no-extra-model-training option.

A useful division of labor is:

```text
Jev:
  rank candidate policies
  classify task/result type
  estimate whether a representation is promising
  cheaply reject obviously poor candidates

Deterministic guards:
  enforce allowed actions, scopes and schemas
  preserve protected requirements/protocol fields
  reject unsupported or unsafe transformations

Independent validation:
  determine outcome quality and actual cost
  decide whether a candidate is promoted
```

Typed output means that the decision has an allowed form. It does not prove
the selected label is true. Model confidence is not automatically calibrated
correctness, and calibration on one workload is not a uniform guarantee over
policies selected to maximize that model's score.

### Proposition 3 — when a proxy improvement would transfer

Let \(S_\theta\in[0,1]\) be a surrogate score and \(Q_\theta\in[0,1]\) true
declared quality. Suppose, for **every policy that search may select**,

\[
\mathbb E|S_\theta-Q_\theta|\le\varepsilon.
\]

Then for any incumbent \(a\) and candidate \(b\):

\[
q_b-q_a
\ge
\mathbb E[S_b]-\mathbb E[S_a]-2\varepsilon.
\]

**Proof.** By the triangle inequality,
\(|\mathbb E S_\theta-q_\theta|
\le\mathbb E|S_\theta-Q_\theta|\le\varepsilon\).
Use \(q_b\ge\mathbb E S_b-\varepsilon\) and
\(q_a\le\mathbb E S_a+\varepsilon\), then subtract. \(\square\)

Thus a surrogate gain greater than \(2\varepsilon\) implies a true quality
gain **if that uniform error bound is established**. Jev's returned
probability or its marketing accuracy does not establish this assumption.

**Counterexample without the assumption:** policy A is always correct and
gets surrogate 0.8; policy B is always wrong and gets surrogate 0.99.
Hill climbing on the surrogate selects B. Every returned value can be valid,
well-formed JSON. Nothing about output typing prevents this.

Using another closely correlated LLM judge does not automatically create
independent evidence. Prefer executable specifications, exact answer keys,
hidden tests with a stated coverage claim, and/or independently audited labels.

## 4. A provably safe statistical promotion rule

### Setup

At confirmation round \(k\), search may adaptively select a candidate \(b_k\)
using all previous search data. Let \(a_k\) be the incumbent. Freeze both,
then draw \(n_k\) fresh independent task pairs. Here \(k\ge1\) and
\(n_k\) are positive integers; choose \(n_k\) before inspecting that round's
confirmation outcomes.

For pair \(i\), record:

\[
X_i = Q_{b_k,i}-Q_{a_k,i}\in[-1,1],
\qquad
Y_i = (C_{b_k,i}-C_{a_k,i})/B\in[-1,1].
\]

The two outputs within a pair may be correlated. What matters here is
independence across task pairs and the correct marginal evaluation regime
for each policy. Isolate/randomize cache conditions and tool state so
evaluation order does not change the intended estimand.

Let \(\mathcal H_k\) denote the complete history before confirmation.
The means used in the conditional probability statements are:

\[
\mu_{X,k}=\mathbb E[X_i\mid\mathcal H_k]
=q_{b_k}-q_{a_k},
\qquad
\mu_{Y,k}=\mathbb E[Y_i\mid\mathcal H_k]
=(c_{b_k}-c_{a_k})/B.
\]

The policies are random across search histories, but fixed after conditioning
on \(\mathcal H_k\).

Choose an overall error probability \(\alpha\in(0,1)\), and allocate:

\[
\alpha_k=\frac{6\alpha}{\pi^2 k^2},\qquad
\sum_{k=1}^{\infty}\alpha_k=\alpha.
\]

With fixed \(n_k\), define:

\[
r_k=\sqrt{\frac{2\log(2/\alpha_k)}{n_k}}.
\]

Promote only when:

\[
\overline X-r_k\ge0,\qquad
\overline Y+r_k\le-\eta/B,
\tag{G}
\]

where \(\eta>0\) is a required absolute expected-cost improvement.

### Theorem 4 — simultaneous safety of all promotions

Under the assumptions in §1 and the fresh-confirmation setup, with probability
at least \(1-\alpha\), **every policy promoted by (G)** satisfies:

\[
q_{b_k}\ge q_{a_k},
\qquad
c_{b_k}\le c_{a_k}-\eta.
\]

This statement permits adaptively generated candidates and an adaptively
chosen number of proposal rounds.

**Proof.** Conditional on the complete history before round \(k\), the
candidate and incumbent are fixed and the confirmation pairs are fresh.
Hoeffding's one-sided bound for a variable with range width 2 gives:

\[
\Pr(\overline X-\mu_{X,k}>r_k\mid\mathcal H_k)
\le e^{-n_k r_k^2/2}=\alpha_k/2,
\]

and:

\[
\Pr(\mu_{Y,k}-\overline Y>r_k\mid\mathcal H_k)
\le\alpha_k/2.
\]

Except on an event of conditional probability at most \(\alpha_k\), both
\(\mu_{X,k}\ge\overline X-r_k\) and
\(\mu_{Y,k}\le\overline Y+r_k\) hold. On that event, (G) implies the two
claimed inequalities. Taking expectations over history and applying the
union bound over all rounds yields total failure probability at most
\(\sum_k\alpha_k=\alpha\). \(\square\)

**What this proves:** control of falsely accepted mean regressions on the
specified stable workload. It does not make every individual answer correct.

**What it does not permit:**

- Selecting the winner of many candidates on a confirmation batch and
  applying the single-candidate bound without a selection correction.
- Repeatedly peeking at a fixed-\(n\) interval until it passes.
- Treating a repeatedly reused adaptive holdout as fresh data.
- Replacing verified \(Q\) with an unvalidated Jev score and retaining a
  guarantee about actual quality.

Confidence sequences can address optional stopping for valid fresh streams;
they do not by themselves repair adaptive reuse of a fixed dataset, missing
ground truth, or biased judges.

### Corollary 4.1 — cost per success improves

If \(q_{a_k}>0\), then on the same event:

\[
\frac{c_{b_k}}{q_{b_k}}
\le \frac{c_{a_k}-\eta}{q_{a_k}}
<\frac{c_{a_k}}{q_{a_k}}.
\]

The first inequality uses nonnegative cost and
\(q_{b_k}\ge q_{a_k}>0\). This is a genuine conditional improvement result
with fixed model weights.

### Important power limitation

If true quality is exactly unchanged, a finite-sample lower bound proving
nonnegative quality difference will generally not pass. In particular,
if every observed quality difference is zero, (G)'s quality inequality fails
because \(r_k>0\).

Zero observed harm is not proof of zero possible harm. A strict zero-regression
gate needs genuine quality margin, a structural equivalence proof, stronger
assumptions, or willingness to keep a candidate unpromoted. We must not market
this conservative theorem as a practical guarantee of constant progress.

### Corollary 4.2 — optional stopping with an elementary valid sequence

For a fixed candidate/incumbent pair in round \(k\), retain a fresh stream of
independent task pairs. For look \(n\), allocate:

\[
\alpha_{k,n}=\frac{\alpha_k}{n(n+1)},\qquad
r_{k,n}=\sqrt{\frac{2\log(2n(n+1)/\alpha_k)}{n}}.
\]

Use the same two inequalities as (G) with \(r_{k,n}\) at every look.
Then the probability of any false promotion across all rounds and all looks
is at most \(\alpha\).

**Proof.** The two one-sided failures at look \((k,n)\) have combined
probability at most \(\alpha_{k,n}\) by Theorem 4's calculation.
Because
\(\sum_{n\ge1}1/[n(n+1)]=1\), the union bound over looks gives
\(\alpha_k\); summing over rounds gives \(\alpha\). Dependence between
overlapping looks is allowed by the union bound. \(\square\)

The candidate and comparator must remain fixed within the stream. Do not
pool observations across mutated candidates and label them a certificate
for the latest one.

This elementary sequence is conservative. Better time-uniform and
variance-sensitive boundaries are available in the primary confidence-sequence
literature; they also require valid data and assumptions.

If \(\mu_{X,k}>0\) and \(\mu_{Y,k}<-\eta/B\) strictly, the law of large
numbers and \(r_{k,n}\to0\) imply that this round eventually passes almost
surely under unlimited continued independent sampling. That is not a finite
evaluation-budget or economic-payback guarantee. If a budget is exhausted,
report “not certified,” not “proved no improvement.”

## 5. Practical alternatives without quietly weakening the claim

### 5.1 Fixed-reference non-inferiority

If a product permits quality loss \(\varepsilon>0\), compare every candidate
to a fixed reference policy \(a_0\) and certify:

\[
q_b\ge q_{a_0}-\varepsilon.
\]

Do not simply allow loss \(\varepsilon\) against the latest incumbent forever:

\[
q_{\theta_K}\ge q_{\theta_0}
-\sum_{k=1}^{K}\varepsilon_k
\]

is all that such per-step inequalities imply. A 1-point allowance at every
step is not a permanent 1-point allowance against the original baseline.

Cost improvement plus tolerated quality decline also does **not** necessarily
improve cost per success. For example:

```text
incumbent: cost 1.00, success 0.99 -> cost/success 1.0101
candidate: cost 0.99, success 0.90 -> cost/success 1.10
```

Therefore use an explicit ratio-improvement gate when the ratio is the target.

### Proposition 5 — conservative ratio gate

Suppose simultaneous intervals cover both policies' true means:

\[
c_j\in[L^C_j,U^C_j],\qquad
q_j\in[L^Q_j,U^Q_j],\quad j\in\{a,b\},
\]

with \(q_a>0\), \(L^Q_b>0\), and \(U^Q_a>0\). If:

\[
\frac{U^C_b}{L^Q_b}+\zeta
<
\frac{L^C_a}{U^Q_a},
\quad \zeta>0,
\]

then \(J(b)+\zeta<J(a)\).

**Proof.** On simultaneous coverage,
\(J(b)\le U^C_b/L^Q_b\) and
\(J(a)\ge L^C_a/U^Q_a\), so the conclusion follows by chaining
inequalities. The existence of a positive upper bound on incumbent quality
alone would not establish its separately assumed positive true success probability.
\(\square\)

Also require \(L^Q_b\ge q_{\min}\), or a separately certified fixed-reference
non-inferiority constraint.

One elementary construction for four mean intervals uses eight Hoeffding
tails. With per-round failure budget \(\alpha_k\):

\[
s_k=\sqrt{\frac{\log(8/\alpha_k)}{2n_k}},
\]

use radii \(s_k\) for quality and \(Bs_k\) for cost, clipped to their known
ranges. Apply the same across-round error spending. This construction is
conservative; more efficient paired/variance-sensitive methods need their
own valid assumptions and error accounting.

All certificates used in one promotion share one total \(\alpha_k\).
If a separate reference comparison or additional latency/safety test is added,
split that budget between the tests; do not give each component the full
\(\alpha_k\) and retain the original overall claim.

### Proposition 6 — a narrower zero-observed-harm bound

For binary outcomes, let
\(H_i=1\{Q_{a_0,i}=1,\ Q_{b,i}=0\}\). If independent confirmation pairs
have harm probability \(h\) and none of \(n\) observations is harmful, an
exact one-sided \(1-\beta\) upper bound is:

\[
h\le 1-\beta^{1/n}.
\]

**Proof.** The probability of zero harms is \((1-h)^n\). For
\(h>1-\beta^{1/n}\), this probability is below \(\beta\). Invert this
one-sided test. \(\square\)

Since \(q_b-q_{a_0}=P(\text{improvement})-h\ge-h\), this can certify a
specified non-inferiority tolerance. Use the allocated \(\beta\) for that
round/test—not 5% afresh forever.

The bound concerns observed-oracle harm on \(D\), not every possible future
task. It is not a zero-regression proof.

### 5.3 Strong guarantees can be expensive

For overall \(\alpha=0.05\), the first round gets
\(\alpha_1\approx0.030396\). The elementary paired bound requires:

| Desired radius for a bounded paired difference | Independent task pairs |
|---|---:|
| 0.05 | 3,350 |
| 0.02 | 20,933 |
| 0.01 | 83,732 |

These are sufficient worst-case sample counts for the stated Hoeffding
radius, not information-theoretic lower bounds, evidence that an improvement
exists, or statistical-power guarantees. A radius of 0.01 means one
percentage point in quality difference, or 1% of the **cost cap \(B\)** in
normalized cost—not 1% of the incumbent's mean bill.

The narrower zero-observed-harm procedure needs 417 pairs to place the first
round's allocated quality-test upper bound below 1% when no harms are
observed. That is a different, weaker claim permitting up to 1% harm; it is
not a shortcut to strict zero-regression certification.

Use exact structural contracts, cheap executable tasks, larger meaningful
effect thresholds, and justified variance-sensitive confidence procedures
where appropriate. Jev triage can reduce the number of candidates reaching
expensive confirmation; it cannot erase confirmation's evidence requirements.
The numerical values are reproduced in `math-checks.json`.

## 6. What hill climbing proves—and where it stops

### Proposition 7 — finite exact hill climbing

Let \(\Theta\) be finite, and let \(J(\theta)\) be a fixed exact objective.
Every accepted move strictly lowers \(J\). Then no policy is revisited,
and at most \(|\Theta|-1\) moves are accepted.

If stopping occurs only after all feasible neighbors are evaluated and none
has smaller \(J\), the final policy is a local minimum for that neighborhood.

**Proof.** A repeated policy would require the same objective value after
a chain of strict decreases, a contradiction. A finite set therefore allows
at most \(|\Theta|-1\) distinct accepted moves. The local-minimum statement
is exactly the stopping condition. \(\square\)

This does not prove global optimality. For policies arranged as
\(A\leftrightarrow B\leftrightarrow C\), with costs \(2,3,0\), ordinary
cost-decreasing hill climbing initialized at A cannot reach the global
best C.

With statistical gates, “could not certify an improvement” is not the same as
“no improving neighbor exists.” The local-minimum conclusion does not
automatically transfer from the exact-oracle theorem to a noisy finite test.

### Stronger search without unsafe deployment

Use nonlocal mutations, random restarts, recombination, and reflective
proposals on the **search side**, while deploying only candidates that pass
the independent gate. GEPA is a relevant frozen-weight search reference, not
a theorem of global convergence or a replacement for that gate.

The population may explore worse policies offline. The deployed champion need
not follow those downhill intermediate steps.

**Concrete integration boundary:** the inspected GEPA source at
`fb1ed589fd83372caef499cffc2c73173d3b096b` has a custom reflective acceptance
criterion, but its optional merge path makes a separate empirical acceptance
decision. Therefore put the deployment certificate **outside the optimizer**,
over every proposed replacement, rather than assuming a single internal
callback covers all candidate routes. This is source inspection, not a
claim that GEPA promises statistical safety or that its optional merge is
enabled by default. The reference memo supplies exact file/line pins.

If each accepted promotion lowers expected cost by at least \(\eta>0\), then
Theorem 4's good event also implies at most
\(\lfloor c_{\theta_0}/\eta\rfloor\) such promotions. A bounded objective
cannot improve by a fixed positive amount forever. “Continuous improvement”
should mean repeated opportunities, monitoring, and justified promotions—not
an infinite stream of guaranteed gains.

## 7. Optimization must pay for itself

### Proposition 8 — expected amortized break-even

Condition on the completed search history, fixing its realized
search/certification cost \(A\) and selected policies \(a,b\). Suppose
deployment cost per task decreases from \(c_a\) to \(c_b\), with
\(\Delta=c_a-c_b>0\), and both policies satisfy the required quality
contract. On \(N\) future tasks from the same regime:

\[
\mathbb E[\text{baseline cost}-\text{optimized total cost}]
=N\Delta-A.
\]

Therefore nonnegative expected savings (break-even) require:

\[
N\ge A/\Delta.
\]

Strictly positive expected savings require \(N>A/\Delta\).

**Proof.** By linearity of expectation, future baseline cost is \(Nc_a\);
optimized cost is \(A+Nc_b\). Subtract. Independence is not needed for
this arithmetic if each task retains the stated means, but the estimation
of those means must still satisfy its inference assumptions. \(\square\)

Without conditioning, when \(N\) is deterministic the corresponding
expectation is \(N\mathbb E[\Delta]-\mathbb E[A]\). A random future horizon
requires accounting for its dependence on the selected policy and search.

Count mutation/reflection-model calls, Jev calls, all rejected candidates,
confirmation trials, index rebuilds, and human labeling in \(A\) where
applicable. Runtime Jev calls belong in \(c_b\), not a hidden free service.
Do not count the same call in both terms.

With a valid lower bound \(\Delta_L>0\), require
\(N\Delta_L>A\) for a conservative **expected** payback decision. That is
not a guarantee of positive realized savings on every finite deployment.

## 8. Drift invalidates unqualified continual guarantees

For a fixed bounded function \(f\) whose range has width \(R\), if
\(\mathrm{TV}(D,D')\le\delta\), then:

\[
|\mathbb E_D f-\mathbb E_{D'} f|\le R\delta.
\]

**Proof sketch.** Rescale \(f\) to a function in \([0,1]\) and apply the
variational characterization of total variation; multiply back by \(R\).
\(\square\)

Here \(\mathrm{TV}(D,D')=\sup_E|D(E)-D'(E)|\), the normalized convention.
For stochastic task outcomes, apply the bound to the fixed function
\(f(x)=\mathbb E_\omega[Q_b-Q_a\mid x]\), or its cost analogue, while
holding the conditional model/tool behavior fixed.

For a fixed pair's quality difference the range width is 2; for raw-cost
difference it is \(2B\). Thus a mean margin certified on \(D\) can erode by
up to \(2\delta\) in quality or \(2B\delta\) in cost under this assumption.

This does not estimate \(\delta\), and input-distribution TV alone does not
cover a changed model/tool kernel. Freeze and record versions, define
workload epochs, watch gold-task/outcome drift, and recertify or roll back
when the assumptions no longer hold.

## 9. Recommended optimizer architecture

```text
1. Freeze champion, target/Jev versions, workload epoch, metric and budget.
2. Generate bounded policy mutations using traces and known failure cases.
3. Apply deterministic policy/schema/security/retention checks.
4. Use Jev to triage/rank candidates on search data, counting its cost.
5. Use cheap exact fixtures to discard obviously poor candidates.
6. Choose one candidate before opening its fresh confirmation batch.
7. Execute paired, isolated full-task evaluations with independent outcomes.
8. Apply a predeclared quality/ratio/cost gate with error spending.
9. Deploy only a certified candidate; retain the previous policy for rollback.
10. Monitor regime changes and stop search when expected payback is absent.
```

First search a small interpretable policy space: thresholds, routing choices,
exact projections, budgets and guard-compatible templates. Do not begin with
an unrestricted self-modifying prompt that can rewrite its own success tests,
permissions, reference data, or statistical acceptance rule.

For TokenMaster specifically, repair the existing recovery oracle, final
emission guard, literal preservation and complete retrieval before this
optimizer consumes those outputs as evidence. Otherwise the loop optimizes
against a defective measurement system.

### What we can responsibly promise

- Exact preservation for explicitly proved query/representation contracts.
- Valid promotion guarantees relative to a defined outcome, workload,
  bounded cost and confidence procedure.
- No target-weight updates are required for these controller improvements.

### What we cannot promise

- Every answer improves, arbitrary compression is lossless, or Jev knows truth.
- Ordinary hill climbing reaches the global optimum.
- A permanent holdout stays independent after unlimited adaptive reuse.
- A 95% single-test interval is a 95% guarantee across unlimited experiments.
- Deployment under drift is covered by a stationary-workload theorem.
- Infinite optimization produces infinite net economic gain.

## 10. Reproducibility and references

`math_checks.py` contains numerical checks and counterexamples; its output is
**not a mathematical proof or a model benchmark**. The proofs are the
arguments above.

Primary-source details are in:

- `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\foundations\jev`
- `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\foundations\references`

Core sources to connect to this design:

- TypeSafe's official Jev launch, September 15, 2026.
- *JEV vs. LLMs as Rubric Judges*, arXiv `2609.29769v2`, revised September 28, 2026.
- *GEPA*, arXiv `2507.19457`, and canonical upstream implementation.
- Hoeffding's bounded-sum concentration inequality.
- Howard et al., time-uniform confidence sequences.
- Dwork et al., validity under adaptive data analysis / reusable holdouts.
- The previously reviewed task-dependent rate–distortion paper,
  arXiv `2407.15504v2`.

Source/version caveats and any limitations of current Jev contracts belong
to the companion memos. Nothing in this note turns a vendor claim into a
mathematical axiom.
