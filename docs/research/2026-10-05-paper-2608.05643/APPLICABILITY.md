# Research: arXiv:2608.05643v1 and token-efficient black-box refinement

**Status:** research only; no experiment executed, no implementation changed.  
**Retrieved:** October 5, 2026 UTC.  
**Request type:** comprehensive paper/source research plus current official API guidance.  
**Evidence labels:** **Paper** = what the pinned paper reports; **Author code** = the separately pinned, self-described author implementation, not proof of the original runs; **Official** = documented public platform behavior; **Analysis** = this report's deduction; **Proposal** = an untested study design; **User constraint** = supplied implementation boundary, not repository inspection.

## 1. Identity and conclusion

**Identity independently confirmed.** The exact supplied [HTML URL][paper] and its separate [arXiv record][record] both identify **Refining Over Resampling: Test-Time Self-Correction for LLM Reasoning**, by Ahsan Bilal, Muhammad Ahmed Mohsin, Muhammad Umer, Lena Trigg, Ali Subhan, Muhammad Ali, and Dean F. Hougen. The record identifies **v1, submitted August 6, 2026, 06:38:37 UTC**, and says submitted to EMNLP 2026; that is not evidence of acceptance. The title and method characterization were verified from these retrieved bodies, not inherited as facts from the handoff. The HTML snapshot SHA-256 is `33a805ecd594621879e1b4f10bbf52089df2cb9fb489102d3df0b414d821ad68`. The arXiv source archive independently corroborates the method. Sources carry the authors' CC BY 4.0 license.

**Analysis — applicability:** The method is mechanically adaptable to black-box text-generation interfaces without foundation-weight changes: repeatedly generate an exposed solution, critique it, rewrite it, then deterministically select an answer. However, **the paper does not establish lower total tokens per independently correct result**, does not evaluate OpenAI/Anthropic through Copilot, and does not test cross-provider refinement. It is a research candidate, not a token-savings or correctness certificate.

**Important source divergence:** The discovered [author-associated implementation][author-readme] folds initialization into depth 1, uses a PRM-dependent default vote tie-break, and estimates token counts with a proxy tokenizer and approximate prompts. These are material differences from the literal v1 algorithm and its accounting/verifier-free claims. See Section 2.4 and [AUTHOR_CODE_AUDIT.md](AUTHOR_CODE_AUDIT.md).

**User constraint — preserve the audit boundary:** The neutral ledger can represent per-call `model_id` and roles. The existing saved-study adapter intentionally pins one primary model and a stateless, no-retry Responses loop. Leave that adapter and checker unchanged. An iterative or multi-model policy requires a **separate frozen adapter, separate policy identity, and fresh task capture**. The eight exposed, non-IID pilot cases are search-only evidence, not a fresh holdout and not multi-model evidence. These are current user-supplied facts; no TokenMaster source inspection was performed.

## 2. What the paper actually does

### 2.1 Algorithm, not a generic "ask again" loop

**Paper — [Algorithm 1][algorithm], [Sections 3.1–3.4][method]:**

1. Initialize \(N\) solution traces \(r_i^{(0)}\), each conditioned on problem \(x\).
2. For every branch and every depth \(d=1,\ldots,D\), use the **same base model**, with different role prompts:
   - continuation/rewrite: \(g_i^{(d)} \sim \pi^G(\cdot\mid x,r_i^{(d-1)})\), **Eq. (3)**;
   - critique: \(c_i^{(d)} \sim \pi^C(\cdot\mid x,g_i^{(d)})\), **Eq. (4)**;
   - correction: \(r_i^{(d)} \sim \pi^R(\cdot\mid x,g_i^{(d)},c_i^{(d)})\), **Eq. (5)**.
3. Extract normalized terminal answers and take their **plurality**, although the surrounding prose often calls this majority voting. There is no external reward/verifier model in this policy and no learned stopping rule. Intermediate-depth votes are diagnostics, not oracle feedback to the algorithm.

**Analysis — call accounting:** The literal algorithm has

\[
K_{\mathrm{generation}}=N+3ND=N(1+3D).
\]

The default \(N=8,D=4\) therefore entails **104 logical generation calls**: 8 initial, 32 continuation, 32 critique, 32 correction; extraction/voting is non-generative. Batching may combine transport/scheduling, but does not eliminate the 104 sequences' processed tokens. Treating this as eight samples or \(ND\) calls materially understates its work. A two-stage critique/rewrite loop omitting continuation is a modified policy, not Algorithm 1. Removing the critic from the literal default pipeline leaves 72 generation calls, so the Table 2 ablation is not an equal-token control.

**Author code — different indexing:** `src/cimr_step.py` uses the depth-1 generator output as both initial rollout and first reasoning trace: **\(3ND=96\)** logical generation calls, or **\(2ND=64\)** without critique, at the same nominal defaults. With the default PRM enabled, up to **\(2ND=64\)** additional logical trace-scoring evaluations occur; batching can combine these into fewer forwards. The actual frozen schedule, not a paper label, must determine accounting. [Pinned implementation and consequences](AUTHOR_CODE_AUDIT.md).

The equations condition each stage on the listed problem/trace/critique, not automatically on an ever-growing conversational transcript. Replaying full accumulated history would change the policy and increase repeated context. The paper mentions truncation but does not supply enough implementation detail to recreate exact context construction; the later code supplies concrete settings, with the version mismatches documented below.

### 2.2 Experiments and what the comparisons support

**Paper — [Sections 4–5][experiments], [Table 1][table1]:** Five mathematics benchmarks; four open-weight backbones: Qwen2.5-Math-7B-Instruct, Qwen2.5-1.5B, Ministral-8B, and LLaMA-3.1-8B. Defaults are \(N=8,D=4,\tau=0.7\), on one H100 80 GB. Correctness is final-answer agreement with gold after normalization. Baselines include greedy, Maj@8, RM@8 with Qwen2.5-Math-RM-32B, beam width 8, and lookahead with eight continuations at three checkpoints.

Selected **reported**, not independently reproduced, results:

| Location | Comparison | Reported result | What it does not establish |
|---|---|---|---|
| Table 1, Qwen2.5-1.5B/MATH500 | RM@8 versus refinement | 29.6% versus 58.0% | Equal-token superiority |
| Table 1, Qwen2.5-1.5B/AMC | RM@8 versus refinement | 25.0% versus 32.5% | Closed-provider transfer |
| Table 1, Qwen2.5-Math-7B/AIME24 | RM@8 versus refinement | 13.33% versus 10.0% | Universal improvement |
| Table 1, LLaMA-3.1-8B/AIME25 | Maj@8 versus refinement | 10.0% versus 6.7% | No-regression guarantee |
| [Table 2][table2], Qwen2.5-1.5B/MATH500 | Without/with explicit critique | 55.6% versus 58.0% | That critique beats spending the extra tokens elsewhere |
| [Table 3][table3], Ministral-8B/AMC23 | \(N=8,D=2\) versus \(N=8,D=4\) | 45.0% versus 42.5% | Monotonic benefit from depth |

**Paper — [Section 5][results]:** The authors explicitly acknowledge that their principal comparison fixes initial sample count, **not total compute**; the compute-normalized analysis is not majority voting scaled to an equal compute budget.

**Paper — [Section 3.5][compute], [Appendix A.7, Eq. (10), Table 4][table4]:**

\[
\mathcal C_m^{gen}=\sum_u 2P_{gen}(T_{in,u}+T_{out,u}),\qquad
\mathcal C_m^{rm}=\sum_v2P_{rm}T^{rm}_{in,v}.
\]

They say lengths are measured after inference truncation. Their efficiency statistic is

\[
\eta=\frac{10^3(a_{ours}-a_{base})}{\mathcal C_{ours}-\mathcal C_{base}},
\]

where accuracy and compute are averaged across the five benchmarks. For Qwen2.5-1.5B versus Maj@8, Table 4 reports average accuracy 13.21% to 25.67%, additional compute 728.39 TFLOPs, and \(\eta=17.10\). For LLaMA versus RM@8, the benchmark win/tie/loss count is 2/1/2.

**Analysis:** Positive \(\eta\) means accuracy improved while extra compute was spent. It does **not** imply lower \(\mathcal C/a\), lower \(E[T]/p\), or equal-budget dominance. Figure 5 visibly shows substantial additional compute. The \(2P\) approximation is not measured hardware utilization, latency, or an interchangeable unit across proprietary models with undisclosed architectures. Do not transplant it as a Copilot compute meter. Without raw per-task counts and an explicit common task weighting, this report does not reconstruct an exact pooled \(J\) from the aggregate tables. **The released compute script's proxy/reconstruction behavior also does not substantiate the paper's exact-realized-context claim; see the code audit.**

### 2.3 Proof and diagnostic audit

**Paper:** There is no theorem proving Algorithm 1 improves correctness or token efficiency. The complete v1 contains motivation equations and diagnostic identities, not a convergence or concentration proof for the proposed algorithm.

- **[Section 2, Eq. (1)][motivation]:** Expresses diversity saturation asymptotically. Figure 1 and Appendix A.6 use finite sampling and a particular sentence-embedding clustering method. **Analysis:** Those observations do not prove a universal asymptotic property of arbitrary black-box or mixed-provider distributions.
- **Section 2, Eq. (2):** Models intended-answer accuracy \(\lambda>1/k\) and symmetric perturbation probability \(h\):
  \[
  q=\lambda(1-h)+\frac{h(1-\lambda)}{k-1}<\lambda.
  \]
  **Analysis — checked algebra:** \(\lambda-q=h(k\lambda-1)/(k-1)>0\). This is a single-trace statement under its noise assumptions, not a voting accuracy ceiling. Counterexample: \(k=2,\lambda=.9,h=.1\) gives \(q=.82\); genuinely independent binary majority voting then converges to correctness as sample size grows. The per-trace inequality alone cannot prove refinement is better than resampling.
- **[Appendix A.2, Eqs. (6)–(7)][diagnostics]:** Recovery and regression are *unconditional fractions of evaluation questions*, not probabilities conditional on previously being wrong/correct. Their difference equals the change in final-vote accuracy.
- **Appendix A.3, Eqs. (8)–(9):** Analogous rollout-level wrong-to-correct and correct-to-wrong flip diagnostics. These use gold labels offline. They do not make the inference procedure an independent verifier.
- **Appendix A.4:** "Diversity" is the fraction of questions with more than one distinct nonempty answer; agreement is the fraction with exactly one. **Analysis:** A diversity value near one is not evidence of independent errors, independent reasoning, or high correctness. Different wrong answers satisfy it.
- **[Appendix A.5–A.6][normalization]:** Lightweight string normalization differs from a mathematical equivalence proof. Sentence embeddings are used for Figure 1's redundancy analysis, not as a runtime selector. The specified encoder/clustering is diagnostic machinery, not a dependency required by Algorithm 1.

**Analysis — concrete source cautions:**

1. [Appendix B][example] is not a verified proof trace. Its depth-2 critique proposes \(124+x+90=180\), which yields \(x=-34\), not 28. Its purported rebuilt reasoning claims \(AB=BC\Rightarrow\angle ABC=\angle ACB\); the equal opposite angles are \(\angle BAC=\angle ACB\). The errors exist in the author TeX, not just HTML conversion (`arxiv.tex` lines 1053–1088 in the preserved archive). Matching the supplied answer 28 therefore does not validate the reasoning or critique. This report does not reconstruct the missing original geometry diagram or re-grade the benchmark item.
2. Figure 4(a) shows increasing answer-change rates across depths for LLaMA and Qwen2.5-1.5B, whereas Appendix A.8 broadly describes decreasing changes as traces stabilize. Prefer the plotted model-specific behavior over that blanket description.
3. Table 2's added critique consumes additional generation work. It supports a useful ablation, but not an isolated causal claim that critique is better than an equal amount of alternative generation.
4. The rendered paper lacks sufficient exact stage prompts, maximum lengths/truncation settings, extraction/tie/failure rules, model revision pins, repeated-run details, raw per-question token logs, and uncertainty intervals for an exact independent reproduction. The later code fills some specification gaps, but is not identical to v1. A commented-out TeX paragraph gives benchmark cardinalities; it is **not** part of the rendered experimental specification and is not used here as authoritative sample-size evidence.

These flags limit the strength of conclusions; they are not claims that every reported result is false.

### 2.4 Limitations and author code

**Paper — [Limitations][limitations]:** More forward passes, dependence on reliable critique/correction, possible harmful revisions, and evaluation limited to mathematics with relatively straightforward answer extraction.

**Source inspection:** Read all main sections, Algorithm 1, Tables 1–4, Figures 1–6, all numbered equations, references, and Appendices A–B. Inspected the author TeX/source archive and rendered every supplied figure PDF for visual checking. Then inspected the separately discovered repository's complete core refinement loop, prompts, aggregation, model wrapper, scoring entry point and relevant accounting/evaluation code without executing it.

No implementation link was present in the HTML, arXiv record or TeX. Initial narrow repository searches returned zero; a **README-scoped title search found `AhsanBilal7/self_refine`**, whose README identifies this exact title and method. The account name matches the corresponding author's name, but the arXiv record does not itself link back to this repository; retain that association/provenance limitation.

The inspected pin is **`cf260f39da0640ea5faf6db6139121485ee78fc7`**, committed **October 4, 2026, 19:52:02 UTC**. GitHub metadata says the repository was created October 4, after the August v1 paper. This is a public implementation reference, not proof that these exact files generated the paper's tables. Its current tree has no raw experiment result store or root license file. Do not infer that the paper's CC license licenses the whole code repository.

Key code findings: **96 versus 104 generation calls; default PRM-assisted tie-breaking despite verifier-free framing; proxy token accounting rather than an exact processed-token ledger; differing model/checker specifications; resumable stores that are not frozen-study identities.** Exact SHA/path/line citations and bounded findings are in [AUTHOR_CODE_AUDIT.md](AUTHOR_CODE_AUDIT.md). No author code was run, modified, installed or imported.

## 3. Black-box and cross-provider applicability

| Aspect | Evidence and proposed interpretation |
|---|---|
| Weight access | **Paper:** no training/weight modification. **Analysis:** exposed-text role calls need no gradients, logits, or foundation-weight access. |
| Hidden reasoning | **Analysis:** operate on an exposed solution/checkable work product, not a promise to access private reasoning. An internal reasoning summary is not the complete token trace. All native generated-token usage still matters. |
| Same-model replication | **Proposal:** keep one resolved model across the three roles, fixed prompts, explicit stage contexts and limits. If temperature/seed controls are unavailable, label this a black-box adaptation, not exact \(\tau=.7\) reproduction. |
| Mixed providers | **Proposal, not paper result:** OpenAI and Anthropic may occupy different branches/roles. That changes the policy and distribution; it needs its own frozen study. A multi-provider vote is not evidence of independent errors or verified correctness. |
| Selection | **Paper:** deterministic verifier-free plurality, not an LLM judge. **Author code:** default ties use PRM scores; disabling PRM removes that dependency. **Proposal:** freeze a genuinely non-verifier tie rule if testing the paper's verifier-free idea. A generative aggregator is a different policy, with extra input/output tokens and another possible error source. |
| Coding/open-ended tasks | **Analysis:** distinct valid programs/texts do not naturally collapse into a reliable string-answer vote. Restrict the first confirmatory study to independently checkable outputs with a committed answer-equivalence protocol, or explicitly accept this additional adaptation and its limitations. |
| Identity | **Analysis:** requested/resolved model identifiers support audit attribution, not proof of identical weights, serving stack, reasoning settings, or independent errors. Public availability is not this user's entitlement. |

The paper justifies exploring a policy, not changing the existing TokenMaster checker or enabling an inference route.

## 4. Current official Copilot controls and version boundaries

### 4.1 Selection and programming surface

**Official:** GitHub's [supported-model tables][models] include OpenAI and Anthropic models in Copilot CLI, with client, policy, and plan restrictions. Examples visible in the retrieved CLI table include GPT-5.4 and Claude Sonnet 4.6; these are documentation examples, **not selected experiment models or assertions about this user**. The SDK [README][sdk-readme] says models available through Copilot CLI are supported by the SDK.

**Official:** [Programmatic reference][programmatic] documents `-p`/`--prompt`, `--model`, JSONL output, and model precedence. A custom-agent model may override the CLI selection; inspect actual request/response attribution in a future authorized capture rather than trusting a label alone. `auto` is a routing policy, not a frozen model. `--silent` suppresses usage statistics in ordinary CLI output ([command reference][commands]); clean final text is not a complete accounting record.

**Pinned official source:** SDK **v1.0.16**, released September 30, 2026, resolves to `f8ae645902b74b62cd47aac1fd9b29adaec3aff2`. Inspected:

- `github/copilot-sdk@f8ae645902b74b62cd47aac1fd9b29adaec3aff2:nodejs/src/types.ts:L2315-L2334` — session model/allowed-model/reasoning configuration. [Source][sdk-types]
- `github/copilot-sdk@f8ae645902b74b62cd47aac1fd9b29adaec3aff2:nodejs/src/client.ts:L2471-L2529` — `listModels()` and cache/custom-handler behavior. [Source][sdk-client]

No `listModels`, quota, account, authentication, CLI, SDK, or inference operation was invoked locally. Only public documentation/source GETs were used. No generic Copilot-session temperature/seed control was established from the inspected public types. `maxOutputTokens` appears in custom-provider/model definitions; that alone is **not** proof of an equivalent hard total-token control on the ordinary Copilot subscription route.

### 4.2 Concurrency is not independent sampling or a token limit

**Official:** [Multiple sessions][sessions] documents side-by-side running sessions. Pinned SDK tests explicitly exercise concurrent sessions and event isolation:

`github/copilot-sdk@f8ae645902b74b62cd47aac1fd9b29adaec3aff2:nodejs/test/e2e/session_lifecycle.e2e.test.ts:L97-L145`. [Source][sdk-concurrency]

This is upstream test-source evidence, **not a test run performed here** or a service concurrency guarantee. Within each refinement branch, continuation → critique → correction remains sequential. Across branches, separate sessions can run concurrently.

**Official ambiguity:** The retrieved [CLI command reference][commands] has inconsistent concurrency descriptions: its environment-variable table gives `COPILOT_SUBAGENT_MAX_CONCURRENT` default 32, range 1–256, while its "Subagent limits" section describes plan-dependent concurrency with a maximum of 32. Do not silently reconcile those as a universal quota. Session concurrency, subagent-tree concurrency, and provider request throttling are different limits. [Usage-limit guidance][rate-limits] acknowledges throttling and advises waiting/reducing automated request pressure, but supplies no universally applicable concurrency allowance for this experiment.

**Proposal:** Use a small fixed application-level concurrency bound in the separately authorized adapter; record it and fail/stop according to the frozen no-retry policy. Do not use parallelism to evade throttling. Parallel execution changes elapsed time, not the sum of processed tokens, and does not prove independent errors.

### 4.3 Usage and hard-cap caveats

**Official:** The [SDK usage guide][sdk-usage] distinguishes:

- `assistant.usage`: live per-model-call token events, including subagents; ephemeral, not replayed on session resume.
- `session.usage_info`: current context-window occupancy, **not total tokens processed across calls**.
- `session.usage.getMetrics`: accumulated totals, with experimental RPC/version caveats.

Pinned event types include optional input/output/cache/reasoning counts, call IDs, actual model identifiers, and call classification:

`github/copilot-sdk@f8ae645902b74b62cd47aac1fd9b29adaec3aff2:nodejs/src/generated/session-events.ts:L6112-L6290`. [Source][sdk-events]

**Analysis:** Capture usage live and reconcile unique calls with session totals; do not add aggregate totals to the underlying events. Do not turn absent fields into zero merely because a display-oriented documentation example does so. Background/compaction/subagent calls must either be disabled in the frozen policy or included and uniquely reconciled. An unobserved call is an accounting gap.

**Official:** The documented [session-limit mechanism][session-limit] is a **soft, non-token accounting limit** checked after responses/calls complete. It is excluded from the requested objective and cannot certify \(T\le C\). `--max-autopilot-continues` limits continuation messages, not every internal model call or total processed tokens. No documented generic hard all-call token cap for the normal Copilot route was established here.

**Analysis:** A study needs a demonstrable upper bound that includes concurrent in-flight calls, complete inputs, generated output, hidden native output when claimed, and all helper calls. If the interface cannot enforce/prove that bound, report the cap guarantee as unavailable. Do not clamp an overrun afterward and claim the original hard cap held.

**Version caution:** Live documentation is rolling. In addition to stable v1.0.16, this research inspected the October 4 SDK HEAD `6b4f3a3bde7eb9a8604617b91effe0f4a2e3921b`, associated with a CLI 1.0.92-4 snapshot and a preview SDK release. The citations above deliberately use the stable pin where available. Neither pin describes this user's installed SDK/runtime; no installation was inspected. Pin the eventual SDK **and** runtime in the future study.

## 5. Complete token objective

### 5.1 Two ledgers, no silent metric substitution

**User constraint / Proposal:**

1. **Common reference metric \(T_{\mathrm{ref}}\):** preserve one explicitly versioned tokenizer/encoding and one frozen serialization/protocol for every provider and policy. Apply it to every captured call's defined input/output artifact, including repeated problem/context. If the protocol is full JSON serialization, name it *serialized-artifact tokens*, not actual model tokens. Freeze treatment of whitespace, key order, IDs, metadata, transport wrappers, tool schemas and any intentionally excluded fields.
2. **Native counts:** preserve native usage separately per actual model, provider route, endpoint, call and counting contract. Do not convert token vocabularies using guessed factors or equate counts from different models. Any sum of heterogeneous native tokens must be labeled as that raw sum, not a model-independent compute measure.
3. Declare which \(T\) is used by the confirmatory \(J\). Report \(J_{\mathrm{ref}}\) as a reference-protocol result; do not relabel it as native serving-token savings. A native-token objective requires separately adequate native evidence and bounds.

**Official counter-contract warning:** OpenAI Responses `input_tokens` already contains cached input, and reasoning is an output breakdown ([reference][openai-response]). Direct Anthropic Messages uses a different input decomposition:

\[
I_{\mathrm{Anthropic}}
=\texttt{input\_tokens}
+\texttt{cache\_read\_input\_tokens}
+\texttt{cache\_creation\_input\_tokens}.
\]

This is explicitly documented in [Anthropic's cache-performance section][anthropic-cache]; the addition reconstructs components, not a cache adjustment. **Do not apply that formula to Copilot's normalized `inputTokens` without establishing its route-specific mapping.** SDK cache field labels alone do not prove whether they are included in the normalized input count for every endpoint. Its `reasoningTokens` is explicitly described as output tokens used for reasoning.

**Official / Analysis:** OpenAI [token-counting guidance][openai-count] documents processed-input formatting/tool/file effects and non-visible output tokens. Independently tokenizing JSON cannot reconstruct hidden output, cache behavior, or all provider-native input processing. A third-party loopback bridge's numbers remain bridge-reported unless provenance and transformation semantics are established. The proposed reference metric remains reproducible without claiming that equivalence.

### 5.2 Count every part of the policy

For a task \(q\), in a declared, consistent token metric:

\[
T(q)=
\sum_{i=1}^{N}(I_{i,0}+O_{i,0})
+\sum_{d=1}^{D}\sum_{i=1}^{N}
\left[(I^G_{i,d}+O^G_{i,d})+(I^C_{i,d}+O^C_{i,d})+(I^R_{i,d}+O^R_{i,d})\right]
+T_{\mathrm{selector}}+T_{\mathrm{Jev}}+T_{\mathrm{other}}.
\]

This displayed schedule is the **literal paper** version. For the released-code schedule, initialization is the first generator call inside the depth sum; omit the separate initialization sum rather than double-counting it. Any actually executed PRM scoring also belongs in the ledger.

**Analysis / Proposal:** Inputs include role instructions, schemas, problem text, carried solution, critique, previous-turn material actually supplied, and any helper output reintroduced into later prompts. Outputs include all native generated output if the claim is native usage, not merely final visible answer length. Cached input is not removed; reasoning is not added again when already inside output.

`T_other` covers retries, failures that consumed tokens, fallbacks, resumed work, compaction, extraction-repair calls, tools/subagents invoking models, and any summarizer/aggregator. For a no-retry policy, unexpected retries are a protocol deviation, not free work. Deterministic local extraction/voting uses no model tokens; a generative selector does. The offline correctness oracle must not generate answers or feed outcomes back to the solver.

### 5.3 Necessary efficiency condition

Let \(\mu_j=E[T_j]\), \(p_j=P(S_j=1)>0\), and retain the existing objective:

\[
J_j=\frac{\mu_j}{p_j}.
\]

**Analysis — exact algebra:**

\[
J_1<J_0
\iff \mu_1p_0<\mu_0p_1
\iff \frac{\mu_1}{\mu_0}<\frac{p_1}{p_0}.
\]

If \(\mu_1=\mu_0+\Delta T\), \(p_1=p_0+\Delta p\), added work is justified only if

\[
\Delta p>p_0\frac{\Delta T}{\mu_0}.
\]

Since \(p_1\le1\), a necessary condition is \(\mu_1/\mu_0<1/p_0\). For example, at baseline success .9 even a perfect candidate cannot tolerate a token multiplier of 2 under this objective. These are mathematical illustrations, not measurements of this user or any model.

Include failed tasks in \(E[T]\); do not use only tokens on successful cases. The pooled ratio \(E[T]/P(S)\) is not generally \(E[T(q)/p(q)]\), nor an independently established per-task retry-until-success guarantee. Keep the study's target distribution and aggregation weights fixed.

## 6. Bounded frozen comparison experiment — not executed

### 6.1 Separation and admissibility

**Proposal:** A study proceeds only after a separately reviewed adapter can faithfully represent the chosen policy and account for all work. It must not broaden the single-model saved-study checker's acceptance rules. Reuse the neutral ledger format if suitable; create a new adapter/protocol version and new capture.

This is a **freeze-ready design, not a claim that a study is already frozen or authorized**. The user did not supply the existing cap or numerical gate thresholds for this research slice; those must be inherited unchanged where applicable and committed with the new study, not guessed here.

Before observing confirmatory outputs, commit to:

- target task distribution and independently sampled task/family units;
- one selected candidate policy, exact role-to-model mapping and resolved model identifiers;
- all prompts, stage contexts, extraction/equivalence/tie rules, no-retry/failure/abstention policy;
- common reference tokenizer/protocol; separate native counter contracts;
- per-call length controls, provable per-policy task cap \(C\), maximum logical calls, concurrency, wall-clock stop, and handling of in-flight work;
- SDK/runtime/adapter versions, allowed helpers, tools, memory, background work and compaction policy;
- oracle version and protected gold/test hashes;
- sample size \(n\le n_{\max}\), significance allocation, strict effect margins, correctness floor/noninferiority conditions, and one terminal analysis or a valid predeclared sequential gate.

Unresolved entitlement, unavailable controls, unsupported native accounting, or an unprovable required cap is an **admissibility blocker**, not permission to make assumptions. No such check against the account occurred in this research.

### 6.2 Small bounded policy family

**Proposal, not a reproduction claim:** Use development/search material to select exactly one candidate before a fresh confirmatory study:

| Policy | Definition | Maximum logical model calls/task |
|---|---|---:|
| B0 | Existing one-shot primary-model behavior, captured under its unchanged contract | 1 |
| W8 | Eight fresh primary-model solutions, committed deterministic plurality | 8 |
| R2 | Same-model **literal-paper** Algorithm-1 adaptation, \(N=2,D=1\), with separate initialization | 8 |
| X2 | **Literal-paper** cross-provider adaptation, \(N=2,D=1\): branch A uses A/A/B/A and branch B uses B/B/A/B for initialization/continuation/critique/correction | 8 |

Here A and B are placeholders, not claims about available account models. X2 uses four calls to each model and intentionally crosses critiques; it is **not** the paper's same-model algorithm. It estimates a whole-policy effect, not an isolated causal effect of provider diversity. Distinguishing provider mixture from cross-critique would require another separately frozen ablation.

This illustrative protocol intentionally fixes the literal-paper indexing. A code-indexed \(N=2,D=1\) version would have six generation calls, and is a separately named policy, not a silent substitution. The author code's default PRM tie-break and diagnostic forwards are **not included** in these verifier-free proposed arms. Jev is off in this initial comparison; an advisory wrapper is a later separately frozen candidate.

Select **R2 or X2**, not whichever later wins the holdout. The confirmatory comparison runs B0, W8 and that single candidate on the same fresh tasks: at most **17 logical calls per task**, and at most **\(3nC\)** total tokens under the shared per-policy cap. An optional Jev call changes the bound and policy identity; it cannot be omitted from accounting.

Equal call count does not imply equal tokens: refinement re-reads generated traces and critiques. W8 and the candidate must share the same declared cap, while actual consumed tokens remain in \(J\). If a cap prevents the scheduled policy from completing, the committed stop/abstention rule applies; do not exceed it or silently substitute a different policy.

Use separate stateless contexts for scheduled calls, with only the dependencies prescribed by the frozen policy. No cross-arm shared conversation, learned memory, or oracle feedback. Freeze tie-breaking; with two branches ties can be frequent. All-empty or invalid outputs should be explicit failures/abstentions, not an empty-string vote counted correct.

### 6.3 Independent correctness and fresh sampling

- Use a protected, independently prepared oracle: exact integer/rational/symbolic checks, proof checking, or a frozen executable specification/hidden test suite appropriate to the task. The claimed correctness is limited to that oracle's coverage; passing tests is not universal program correctness.
- Keep gold answers, hidden tests and correctness outcomes inaccessible to generation, critique, voting, aggregation and Jev. Evaluate only after outputs are fixed. Self-critique, consensus, confidence and model-vs-model agreement are not independent truth oracles.
- The current eight cases and their tuned descendants remain development/search data. A new filename, extra calls, paraphrases, or another provider does not make them fresh.
- Sample new task units from a committed distribution. Correlated variants belong in one family/block; do not count branches, critiques, or variants as independent observations. If the required independence assumptions cannot be justified, do not use an IID concentration gate.
- Pair all arms on the same task; randomize/interleave arm order with a committed schedule to reduce time/provider drift. Independent sampling requests or different provider names do not establish independent error events. The concentration unit is the task pair/block, not each rollout.
- Preserve every scheduled failure/refusal/timeout/abstention and consumed tokens. Missing accounting blocks certification; do not selectively drop a case, regenerate until it works, or impute missing counts as zero.

### 6.4 Strict concentration gates

> **Acceptance boundary — mandatory:** The currently implemented **strict joint quality-and-token gate remains authoritative and unchanged**. The ratio and noninferiority calculations below are diagnostic mathematical illustrations only: they are **NOT permission to relax, replace, bypass or reinterpret either acceptance requirement**. Lower \(J\) alone is not sufficient for promotion. An illustrated noninferiority tolerance does not authorize adding a tolerance that the implemented gate disallows. Every candidate must pass the existing joint gate in full, with its existing thresholds and fresh-evidence requirements.

**Mathematical consistency check, not an alternative acceptance policy:** Retain the existing cap and fresh paired strict gate. The following conservative fixed-sample construction illustrates uncertainty in a ratio claim; it grants no implementation or gate-change authority.

For independent paired task units \(i=1,\ldots,n\), arms \(j\in\{0,1\}\), require \(0\le T_{ji}\le C\) and \(S_{ji}\in\{0,1\}\). Dependence between the two arms **within** a pair is allowed. Let \(X_{ji}=T_{ji}/C\). Allocate \(\alpha_J\) to four simultaneous two-sided mean bounds and set

\[
h=\sqrt{\frac{\log(8/\alpha_J)}{2n}}.
\]

Clip each interval \(\bar X_j\pm h,\bar S_j\pm h\) to \([0,1]\), yielding \(L_{X_j},U_{X_j},L_{p_j},U_{p_j}\). Hoeffding's bound plus a union bound gives simultaneous coverage at least \(1-\alpha_J\). Require \(L_{p_0}>0\) and \(L_{p_1}>0\) for a finite-objective comparison; conservative ratio bounds are

\[
U_{J_1}=\frac{C\,U_{X_1}}{L_{p_1}},\qquad
L_{J_0}=\frac{C\,L_{X_0}}{U_{p_0}}.
\]

For the illustrative ratio claim, require **strictly** \(U_{J_1}<(1-\delta_J)L_{J_0}\) for a predeclared \(0\le\delta_J<1\). This is additional diagnostic evidence, **not a substitute for the implemented joint quality-and-token acceptance gate**. A zero denominator or equality is not a pass. The marginal bounds are valid with paired data, although they do not exploit all pairing efficiency.

For an explicit paired correctness check, \(D_i=S_{1i}-S_{0i}\in[-1,1]\). A one-sided lower bound is

\[
L_{\Delta p}=\bar D-\sqrt{\frac{2\log(1/\alpha_Q)}{n}}.
\]

The expression \(L_{\Delta p}>-\epsilon_Q\) illustrates a noninferiority calculation, **not an authorized acceptance condition for this implementation**. Do not introduce or loosen \(\epsilon_Q\), allow a quality/token tradeoff, or promote on this illustration; the existing strict joint gate controls acceptance. Allocate the full error budget across any authorized ratio diagnostics, correctness tests, comparisons against B0/W8, subgroups and repeated looks. Do not use these IID bounds on the eight non-IID pilot cases.

Freeze \(n,n_{\max}\) and margins before the holdout. For desired normalized mean radius \(h_\star\), the displayed construction requires at least \(\log(8/\alpha_J)/(2h_\star^2)\) independent units; the paired correctness radius has its own requirement. This is precision planning, not a guarantee of passing. If the prespecified finite budget cannot resolve the effect, report **inconclusive** rather than weakening the gate. Any tuning after inspection requires a new fresh holdout or a separately valid, predeclared sequential-testing procedure.

### 6.5 Jev remains advisory

**User constraint / Proposal:** Jev may advise which already-defined policy or budget tier to use only within a predeclared, statically bounded action set. Freeze its inputs, version/route, decision mapping and fallback before capture. Count its own input/output and any resulting prompt expansion. A routed policy must pass the same independently scored, fresh paired gates as a fixed one.

Jev cannot authorize extra work, lift the cap, reinterpret failures, access holdout labels, certify correctness, or replace the independent oracle. Its confidence is not a concentration bound. No Jev product capability, current entitlement, inference behavior, or measured benefit was evaluated here.

## 7. Handoff and stop condition

**Reusable takeaway:** Keep the current objective audit intact. Treat breadth-depth refinement as an unproven candidate for a **new, frozen, fully accounted policy study**. The paper's open-weight accuracy improvements, positive incremental-compute statistic and plurality votes do not certify token efficiency or truth. A cross-provider result must be measured with fresh independent correctness labels, the common reference token protocol, separate native model counts, all-call cap enforcement and strict paired statistical gates.

Research is complete at the documentation/source level. The mapping from the later author-code pin to the original reported runs, exact account availability, bridge counter fidelity, enforceable route-specific caps and experimental performance remain **unverified**. No source implementation, credentials/config inspection, generation requests, account/quota queries, commits or pushes were performed.

See [SOURCES.md](SOURCES.md) and [source_manifest.json](source_manifest.json) for retrieval URLs, release/commit pins, hashes, source-code line ranges, derivative provenance and bounded search failures.

[paper]: https://arxiv.org/html/2608.05643v1
[record]: https://arxiv.org/abs/2608.05643v1
[algorithm]: https://arxiv.org/html/2608.05643v1#alg1
[method]: https://arxiv.org/html/2608.05643v1#S3
[experiments]: https://arxiv.org/html/2608.05643v1#S4
[results]: https://arxiv.org/html/2608.05643v1#S5
[table1]: https://arxiv.org/html/2608.05643v1#S3.T1
[table2]: https://arxiv.org/html/2608.05643v1#S3.T2
[table3]: https://arxiv.org/html/2608.05643v1#S4.T3
[compute]: https://arxiv.org/html/2608.05643v1#S3.SS5
[table4]: https://arxiv.org/html/2608.05643v1#A1.SS7
[motivation]: https://arxiv.org/html/2608.05643v1#S2
[diagnostics]: https://arxiv.org/html/2608.05643v1#A1.SS2
[normalization]: https://arxiv.org/html/2608.05643v1#A1.SS5
[example]: https://arxiv.org/html/2608.05643v1#A2
[limitations]: https://arxiv.org/html/2608.05643v1#Sx1
[models]: https://docs.github.com/en/copilot/reference/ai-models/supported-models
[programmatic]: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference
[commands]: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference
[sessions]: https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/work-with-multiple-sessions
[rate-limits]: https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/usage-limits
[session-limit]: https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/set-session-limit
[sdk-readme]: https://github.com/github/copilot-sdk/blob/6b4f3a3bde7eb9a8604617b91effe0f4a2e3921b/README.md#what-models-are-supported
[sdk-types]: https://github.com/github/copilot-sdk/blob/f8ae645902b74b62cd47aac1fd9b29adaec3aff2/nodejs/src/types.ts#L2315-L2334
[sdk-client]: https://github.com/github/copilot-sdk/blob/f8ae645902b74b62cd47aac1fd9b29adaec3aff2/nodejs/src/client.ts#L2471-L2529
[sdk-concurrency]: https://github.com/github/copilot-sdk/blob/f8ae645902b74b62cd47aac1fd9b29adaec3aff2/nodejs/test/e2e/session_lifecycle.e2e.test.ts#L97-L145
[sdk-usage]: https://github.com/github/copilot-sdk/blob/f8ae645902b74b62cd47aac1fd9b29adaec3aff2/docs/features/usage-and-billing.md#per-call-token-counts
[sdk-events]: https://github.com/github/copilot-sdk/blob/f8ae645902b74b62cd47aac1fd9b29adaec3aff2/nodejs/src/generated/session-events.ts#L6112-L6290
[openai-response]: https://developers.openai.com/api/reference/resources/responses/methods/create
[openai-count]: https://developers.openai.com/api/docs/guides/token-counting
[anthropic-cache]: https://platform.claude.com/docs/en/build-with-claude/prompt-caching#tracking-cache-performance
[author-readme]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/README.md
