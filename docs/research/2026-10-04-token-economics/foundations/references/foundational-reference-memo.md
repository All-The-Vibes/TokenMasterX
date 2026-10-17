# Research: Safe black-box search around a frozen LLM

**Retrieval date:** October 4, 2026. **Scope:** foundational evidence and mathematical specializations for independent review; no application inspection, implementation, installations, paid inference, or delegation.

## Request Type

Bounded implementation-reference and theorem research. Five directly inspected primary works/source collections, plus the original Hoeffding bibliographic reference. TypeSafe Jev is outside this slice.

## Direct Answer

Treat GEPA as a **candidate generator**, not a population-improvement certificate. A candidate chosen using arbitrary previous search can receive a valid *new* certificate from an independent confirmation batch, conditional on that history. Spend error probability across attempts. If stopping within a batch depends on observed scores, use a time-uniform boundary or spend error across sample sizes too. Ordinary fixed-sample intervals do not automatically survive optional stopping or adaptive reuse of a fixed holdout. These are specializations of [R3–R5], not claims of universal LLM improvement.

### 1. Precise estimand and assumptions

At attempt \(t\), condition on the entire past \(\mathcal H_{t-1}\). Fix candidate \(c_t\), comparator \(b_t\), scoring protocol, target distribution \(P\), margin \(\delta_t\ge0\), bound \(B>0\), error allocation \(\alpha_t\), and fixed sample count \(n_t\) **before seeing that attempt's confirmation observations**.

Draw fresh independent evaluation tuples \(Z_{t,i}\) from \(P\), including whatever model/judge randomness defines the intended estimand. Set

\[
D_{t,i}=R(c_t,Z_{t,i})-R(b_t,Z_{t,i}),\qquad
\mu_t=\mathbb E[D_{t,i}\mid\mathcal H_{t-1}].
\]

Require \(D_{t,i}\in[-B,B]\) almost surely, with independence across tuples conditional on history and a common conditional mean. Dependence **within** a candidate/comparator pair is allowed: shared inputs, and valid shared-randomness coupling, do not violate the bound. If each reward is in \([0,1]\), \(B=1\). If each reward is in \([-B,B]\), their difference is instead in \([-2B,2B]\); do not confuse these two bounds. [R3; R4 §2]

The guarantee concerns this scoring protocol's **expected** reward, not every output, subjective truth, worst-case safety, or performance under distribution/model/judge drift. A stochastic judge must be included in the estimand; judge agreement is not automatically task correctness. These are scope implications of the assumptions, not additional source theorems.

### 2. Fixed-sample paired confidence bounds — constants

Hoeffding's bounded-sum specialization gives, for independent \(D_i\in[a_i,b_i]\),

\[
\Pr\!\left(\bar D-\mathbb E\bar D\ge x\right)
\le \exp\!\left(-\frac{2n^2x^2}{\sum_i(b_i-a_i)^2}\right).
\]

For \(D_i\in[-B,B]\), therefore,

\[
\Pr(\bar D-\mu\ge x)\le e^{-nx^2/(2B^2)},\qquad
\Pr(|\bar D-\mu|\ge x)\le2e^{-nx^2/(2B^2)}.
\]

Thus:

| Quantity | \(D_i\in[-1,1]\) | \(D_i\in[-B,B]\) |
|---|---|---|
| One-sided \(1-\alpha\) lower bound | \(\bar D-\sqrt{2\log(1/\alpha)/n}\) | \(\bar D-B\sqrt{2\log(1/\alpha)/n}\) |
| Two-sided \(1-\alpha\) radius | \(\sqrt{2\log(2/\alpha)/n}\) | \(B\sqrt{2\log(2/\alpha)/n}\) |

The factor \(2B\) is the support **width**. Using the \([0,1]\)-mean radius \(\sqrt{\log(1/\alpha)/(2n)}\) directly for differences in \([-1,1]\) is wrong by a factor of two. The same one-sided bound follows from Dwork et al.'s Lemma 1: the paired sample mean has replacement sensitivity \(2B/n\). [R3 Lemma 3(c); R5 Lemma 1; original attribution R6]

**Candidate acceptance specialization:** accept only if
\[
L_t=\bar D_t-B\sqrt{2\log(1/\alpha_t)/n_t}>\delta_t.
\]
For fixed \(\delta_t\), the bad event “accepted and \(\mu_t\le\delta_t\)” has conditional probability at most \(\alpha_t\). This controls false improvement declarations; it does not ensure acceptance, or ensure that an improving candidate exists.

### 3. Adaptively chosen candidates: what survives

The preceding conditional statement permits \(c_t,b_t,n_t,\alpha_t,\delta_t\) to depend on **all previous attempts**, including previous confirmation results, provided the current confirmation batch is independent of that history. No independence between attempt-level decisions is needed.

For deterministic spending \(\sum_{t\ge1}\alpha_t\le\alpha\), a countable union bound and the tower property give
\[
\Pr(\exists t:\text{accepted}_t\ \&\ \mu_t\le\delta_t)\le\alpha.
\]
Examples: \(\alpha_t=\alpha/T\) for a predeclared maximum \(T\), or \(\alpha_t=\alpha/[t(t+1)]\) for an unbounded attempt horizon. Predictable, history-dependent spending also works if the sum is bounded by \(\alpha\) almost surely. This is a derived error-spending argument, **not a separately attributed theorem about GEPA**. [R3–R4 supply the conditional concentration machinery.]

Stopping the *overall search* after a success is allowed under this simultaneous event. Repeatedly inspecting within-attempt data and choosing \(n_t\) from those observations is **not** covered by the fixed-\(n_t\) argument.

If every accepted comparator is the incumbent, and all attempts use the same population objective, the simultaneous event certifies each accepted increment. If comparators are arbitrary GEPA ancestors, an increment over that ancestor need not improve the deployed incumbent. Noninferiority with an allowed loss per step can accumulate loss; it is not monotone improvement.

### 4. Optional stopping: two explicit valid choices

**Elementary spending over sample sizes.** For one fixed candidate/comparator pair with an indefinitely fresh stream, choose \(\eta_n=\alpha/[n(n+1)]\). Then
\[
L_n^{\mathrm{spend}}
=\bar D_n-B\sqrt{\frac{2\log(n(n+1)/\alpha)}{n}}
\]
is a simultaneous one-sided lower sequence, by the union bound. For adaptive attempts as well, replace \(\alpha\) here with the attempt budget \(\alpha_t\). This construction is valid but conservative; it is a derivation from fixed-sample concentration, not Howard's sharper stitched construction.

**Howard et al.'s closed-form normal-mixture sequence.** For a fixed pair, or more generally bounded adapted observations with \(\mathbb E[D_i\mid\mathcal F_{i-1}]=\mu\), Hoeffding's lemma makes
\[
S_n=\sum_{i=1}^n(D_i-\mu),\qquad V_n=nB^2
\]
sub-Gaussian in both directions with \(l_0=1\). Fix \(\rho>0\) before observing this stream. Proposition 5, equation (51), gives
\[
u_\alpha(v)=\sqrt{(v+\rho)\log\!\frac{v+\rho}{\alpha^2\rho}},
\qquad
C_n=\left[\bar D_n-\frac{u_\alpha(nB^2)}n,\,
\bar D_n+\frac{u_\alpha(nB^2)}n\right].
\]
Then \(\Pr(\forall n\ge1:\mu\in C_n)\ge1-\alpha\). Its lower endpoint is a conservative one-sided bound at level \(\alpha\); no extra factor of two is needed for this already two-sided formula. For \([-1,1]\), use \(V_n=n\). Across candidates, use \(\alpha_t\) in each new sequence. [R4 Proposition 5; R3 Lemma 3(c)]

This allows arbitrary stopping of a valid sequence. It **does not** make an adaptively queried fixed dataset fresh, or certify the latest candidate by pooling observations collected under earlier candidates. In the latter case the general Howard estimand is an average of conditional means, not necessarily the current candidate's mean. Changing \(\rho\) after inspecting scores also needs separate justification. [R4 §2 and §6]

### 5. Fixed holdout reuse and Dwork's actual remedy

Ordinary marginal confidence bounds for a fixed candidate need not hold for a candidate chosen from scores on the same holdout. Merely applying Bonferroni to the number of realized adaptive queries does not repair invalid per-query coverage. A predeclared finite candidate family independent of the holdout is different: simultaneous bounds over the **whole family** can justify selection. Fresh decoding on the same tasks only refreshes decoding noise, not the population task sample. [R5; specialization]

**Thresholdout is a mechanism, not permission for unrestricted reuse.** It compares training and holdout means using noisy thresholds, returns training means when close, otherwise returns noisy holdout means and consumes an overfitting budget. Access to the holdout must be mediated by this mechanism. [R5 §4.1, Figure 1]

An exact sufficient specialization of **Theorem 25 via Lemma 24's \(n_0\) branch** is useful for seeing the costs. Rename the paper's budget \(B\) to \(K\) to avoid collision with our range bound. For queries \(\phi_i:\mathcal X\to[0,1]\), \(m\ge K\ge1\), \(0<\tau,\beta<1\), set
\[
T=3\tau/4,\quad \sigma=\tau/[96\log(4m/\beta)],
\]
\[
n\ge\max\left\{
\frac{1536K\log(4m/\beta)}{\tau^2},\
\frac{64\log(12m/\beta)}{\tau^2}
\right\}.
\]
For an i.i.d. holdout and an analyst with no other access to it, the theorem bounds by \(\beta\) the event that some answer differs from its population query mean by at least \(\tau\) while \(Z_i<K\), where \(Z_i\) counts queries so far whose training mean differs from population mean by more than \(\tau/2\). This is **not** an unlimited-answer guarantee. For paired \(D\in[-B,B]\), use \(\phi=(D+B)/(2B)\); error \(\tau\) on \(\phi\) corresponds to \(2B\tau\) on \(D\). These constants are explanatory, not an implementation recommendation.

### 6. GEPA: empirical method versus certification

Paper v2's Algorithm 1 evaluates a selected ancestor on a feedback minibatch, reflects on trajectories/feedback to mutate a prompt, and retains a candidate if its score improves on that same minibatch. It then scores retained candidates on the repeatedly used Pareto dataset and returns the best average there. Algorithm 2 diversifies ancestor selection by instance-wise Pareto performance; Appendix D.1 adds system-aware merging. This changes textual components rather than training task-model weights. Reported benchmark gains and rollout reductions are empirical, not a theorem of population improvement or global convergence. [R1]

The current **`gepa.optimize`** source was verified at
`gepa-ai/gepa@fb1ed589fd83372caef499cffc2c73173d3b096b`
(main snapshot, commit timestamp October 1, 2026, 23:53:49 UTC):

- `src/gepa/strategies/acceptance.py:L44-L66`: default acceptance is simply `new_sum > old_sum`; an alternative permits equality.
- `src/gepa/proposer/reflective_mutation/reflective_mutation.py:L592-L618,L686-L706`: the child is scored on its proposal task's minibatch; its before/after scores feed acceptance.
- `src/gepa/api.py:L56-L99,L140-L157,L229-L231`: default Pareto selection, optional merge disabled, minibatch size documented as 3, and absent `valset` reuses `trainset`.
- **Important hook limitation:** `src/gepa/core/engine.py:L1007-L1040` accepts optional merges with `new_sum >= max(parent_sums)` directly. The custom reflective acceptance criterion is therefore not, by itself, a universal gate over all pool additions.

These are implementation facts, not evidence that any data are statistically fresh. See pinned clickable file references in [R2]. The tree declares version `0.1.4`; that is not a claim that this main snapshot equals a published release.

### 7. Cost and limits

Count **search rollouts, optimizer/reflection calls, judge/evaluator calls, confirmation samples, tokens, tools, retries, latency, and final inference cost** separately. GEPA explicitly reports reflection-model calls separately in Appendix N. Its source also distinguishes metric and reflection-cost budgets. A “metric call” is not a universal unit of tokens, dollars, or total computation. [R1 Appendices E.3/N; R2 API and evaluation counters]

**Calculated examples, not measured runs:** for \([-1,1]\) differences and one-sided \(\alpha=.05\), making the fixed-sample radius at most .01 requires **59,915 independent pairs**; .02 requires 14,979; .05 requires 2,397. With one uncached generation per arm per pair, the first example entails 119,830 task generations, plus judging and optimization. These are radius budgets, **not** 95%-power guarantees.

For true excess improvement \(g=\mu-\delta>0\), a sufficient fixed-sample power condition for acceptance with probability at least \(1-\beta\) is
\[
g\ge B\sqrt{\frac{2\log(1/\alpha)}n}
  +B\sqrt{\frac{2\log(1/\beta)}n}.
\]
This follows by applying the opposite Hoeffding tail to nonacceptance. Smaller effects, more comparisons, and optional stopping can be expensive. Pairing can reduce actual variance, but range-only Hoeffding ignores that benefit. Howard's Theorem 4 gives a justified variance-adaptive alternative; substituting observed variance into a sub-Gaussian boundary without its required conditions is not justified. [R3; R4 Theorem 4/§5]

**Local/global boundary:** empirical improvement over an ancestor is not improvement over every candidate. Even certified incumbent improvements do not establish local optimality unless the relevant neighborhood was covered, nor global optimality without extra objective/search structure. Example: rewards .5, .4, .9 along a three-node path defeat strict one-step hill climbing from the first node. A baseline already achieving the maximum has no strictly better candidate. These elementary counterexamples suffice here; no broad no-free-lunch theorem is invoked.

## Official / Primary Evidence

- **[R1] Agrawal et al., GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning.** [arXiv:2507.19457v2](https://arxiv.org/html/2507.19457v2), February 14, 2026. Read §3, Algorithms 1–2, Appendix D.1, E.3 and N. Primary algorithm and empirical evidence.
- **[R2] Canonical GEPA upstream source**, pinned full SHA above. [API](https://github.com/gepa-ai/gepa/blob/fb1ed589fd83372caef499cffc2c73173d3b096b/src/gepa/api.py#L46-L103), [acceptance](https://github.com/gepa-ai/gepa/blob/fb1ed589fd83372caef499cffc2c73173d3b096b/src/gepa/strategies/acceptance.py#L44-L66), [proposal evaluations](https://github.com/gepa-ai/gepa/blob/fb1ed589fd83372caef499cffc2c73173d3b096b/src/gepa/proposer/reflective_mutation/reflective_mutation.py#L592-L706), [merge path](https://github.com/gepa-ai/gepa/blob/fb1ed589fd83372caef499cffc2c73173d3b096b/src/gepa/core/engine.py#L1007-L1040). Source was necessary because current hooks/defaults extend the paper pseudocode.
- **[R3] Howard, Ramdas, McAuliffe and Sekhon, Time-uniform Chernoff bounds via nonnegative supermartingales.** [arXiv:1808.03204v8](https://arxiv.org/html/1808.03204v8), December 17, 2025 revision of the 2020 work. Read Lemma 3(c), scalar specialization and sub-Gaussian definitions; Table 1 explicitly connects Corollary 1(a) to Hoeffding's original Theorem 2.
- **[R4] Howard, Ramdas, McAuliffe and Sekhon, Time-uniform, nonparametric, nonasymptotic confidence sequences.** [arXiv:1810.08240v9](https://arxiv.org/html/1810.08240v9), August 6, 2022 revision of the 2021 work. Read §2, Proposition 5/equation (51), Theorem 4, and §5–6.
- **[R5] Dwork, Feldman, Hardt, Pitassi, Reingold and Roth, Generalization in Adaptive Data Analysis and Holdout Reuse.** [arXiv:1506.02629v2](https://arxiv.org/html/1506.02629v2), September 25, 2015. Read Lemma 1, Thresholdout §4.1/Figure 1, Lemma 24 and Theorem 25. This is the detailed theorem source, rather than relying only on the shorter Science reusable-holdout article.
- **[R6] Hoeffding, Probability Inequalities for Sums of Bounded Random Variables.** JASA 58(301), 13–30, March 1963; [DOI](https://doi.org/10.1080/01621459.1963.10500830). **Bibliographic provenance only:** publisher/JSTOR full text could not be retrieved in this run. Do not represent its original pages as directly inspected. Constants were instead verified through the primary-author rigorous treatment [R3] and [R5] Lemma 1.

## Version Note / Caveats

- ArXiv histories were checked live. In particular, R3 has a December 2025 v8; do not silently cite older v4 equation numbering as current.
- GEPA evidence is a pinned current-main source inspection, **not** an installed-package test or reproduction of paper experiments. No external OSS or third-party tutorial was needed.
- Mathematical specializations, substitutions, examples, and error-spending arguments above are explicitly this memo's derivations for the parent's independent review.
- Web search tool calls returned no usable content; primary URLs were retrieved directly over HTTPS. No original PDFs or upstream source files were copied into the workspace.

## Reusable Takeaway

Freeze the candidate and comparator before fresh confirmation; specify the population, scoring semantics and known range; choose fixed-\(n\) versus time-uniform inference; and account for all attempts. The defensible claim is **bounded probability of any false accepted population-improvement declaration under stated assumptions**, not a theorem that search always improves an LLM, reaches a global optimum, or is economically worthwhile.
