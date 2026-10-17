# Research: Task-level LLM token economics

**Review date / literature cutoff:** October 4, 2026.  
**Request type:** Comprehensive research, bounded to primary publications.  
**Scope:** Context selection/compression, information retention, long-context failure, agent memory, reasoning/output budgets, and quality–cost evaluation. No TokenMaster implementation was inspected or benchmarked. No package selection, production edits, installations, paid API calls, or delegation occurred.

## Direct answer

**Optimize total cost per successful task under explicit quality constraints—not compression ratio.** Task-conditioned selection, compressor overhead, memory maintenance, output generation, and recovery attempts belong in the same experiment. This is a synthesis, not a performance claim about TokenMaster. The strongest foundations are task-dependent rate–distortion analysis [P06], evaluation beyond literal retrieval [P08], [P09], [P10], [P11], and deployment-sensitive compression measurements [P16].

Three conclusions have particularly strong support:

1. **Useful information is task-dependent.** Query-aware selection and selective omission can outperform preserving a longer context; a single “retain important words” criterion is not a universal objective [P03], [P05], [P06], [P07].
2. **Context capacity is not reliable context utilization.** Position, lexical overlap, distractors, and multi-session dependencies materially change measured success [P08], [P09], [P10], [P11].
3. **Savings have separate meanings.** Fewer input tokens, reduced KV memory, faster prefill, faster complete responses, and lower invoiced cost are different outcomes. Compressed-input quality and end-to-end timing both require measurement [P13], [P16], [B02], [B03], [B04].

## Official / primary research evidence

The matrix contains **16 load-bearing publications**. All links pin the reviewed arXiv revision; dates are revision dates, not necessarily first publication dates. `sources.json` includes first-submission dates, complete retrieved version histories, reviewed sections, claim conditions, and limitations.

**Access legend:** **P** = ordinary text API can consume the result; external compressor/orchestration may still require compute or state. **E** = usable as an evaluation protocol, not itself an optimization. **M** = target-model, embedding/activation, training, or serving control required. These are capability classifications inferred from the methods—not compatibility assertions about a particular provider.

### Compact evidence matrix

| ID / pinned paper | Method and inspected evidence | Concrete result and experimental boundary | Limitations / control |
|---|---|---|---|
| **P01** [Selective Context: Compressing Context to Enhance Inference Efficiency of Large Language Models](https://arxiv.org/abs/2310.06201v1), **2023-10-09** | Scores self-information with a smaller LM; removes low-scoring linguistic units. Read method, experimental setup, efficiency and quality evaluation. | Reports **50% context reduction**, **36% inference-memory reduction**, **32% inference-time reduction**, with **0.023 BERTScore** and **0.038 faithfulness** decreases across its applications. | News, arXiv text, and conversations are not arbitrary agent traces. Similarity/faithfulness proxies are not executable-task correctness. **P**, with local scoring overhead; no target retraining. |
| **P02** [LLMLingua](https://arxiv.org/abs/2310.05736v2), **2023-12-06** | Coarse budget control, iterative token pruning, and small-LM distribution alignment. §4–5, Table 2. | GPT-3.5-Turbo-0301 GSM8K: **2,366→117 prompt tokens**, **78.85→77.33 EM**; the approximately **20×** compression loses **1.52 percentage points**. At 446 tokens, EM is 79.08. | Few-shot demonstrations dominate this setup; it is not evidence that arbitrary evidence/code can lose 95% of tokens safely. **P**; compressor adaptation differs from target-model retraining. |
| **P03** [LongLLMLingua](https://arxiv.org/abs/2310.06839v2), **2024-08-12** | Question-conditioned coarse/fine selection, dynamic allocation, document ordering, and recovery. §4–5, Tables 1–2. | NaturalQuestions, 20 documents, GPT-3.5-Turbo: **2,946→748 tokens**. With the answer document at position 10 and no reordering, accuracy **54.1→71.2**; the separate reordered result is **75.5**. | The advertised 21.4-point gain compares that original middle-position result with the reordered pipeline. Selection, pruning, and ordering must be ablated separately. **P**, but depends on the current question. |
| **P04** [LLMLingua-2](https://arxiv.org/abs/2403.12968v2), **2024-08-12** | GPT-4 produces extraction-style supervision; a bidirectional encoder learns keep/drop classification. §3–5, Tables 3, 5, 11. | GPT-3.5-Turbo-0613 LongBench, 2,000-token target: **39.1 aggregate score at 1,954 tokens** versus LLMLingua **34.6 at 1,950**. Its reported local V100 end-to-end example is **14.9→5.2 s**, labeled 2.9×, at 5× compression. | Task-agnostic compression is reusable but cannot exploit a future query. Aggregate improvement over a compressor is not equivalence to full context. Hardware-specific timing is not API timing. **P**, trained auxiliary encoder. |
| **P05** [RECOMP](https://arxiv.org/abs/2310.04408v1), **2023-10-06** | Trains extractive sentence selection or abstractive summaries for downstream LM utility; can return empty augmentation. §3–5 and transfer experiments. | Trained compressors retain about **25%** of retrieval tokens for language modeling with small degradation; QA retains **5–10%**, with reported relative performance loss below 10%. The often-quoted **6%** also appears prominently in **oracle** analyses. | Separate trained results from oracle selection and LM→QA transfer. Generation can omit or alter evidence; training uses downstream feedback. **P**, with compressor training/inference cost. |
| **P06** [Fundamental Limits of Prompt Compression: A Rate-Distortion Framework for Black-Box Language Models](https://arxiv.org/abs/2407.15504v2), **2024-12-11** | Defines rates and task-output distortion; derives achievable tradeoffs and studies query-aware/adaptive compression. §2–4, experiments, Appendices C–D. | Exact achievable curves are demonstrated in tractable synthetic settings. NarrativeQA has roughly **3,500 examples** with prompts hundreds of tokens long; the paper explicitly says exhaustive optimal curves are infeasible there. | “Optimal” is relative to the prompt/query distribution, compressor class, target model, and distortion function. Synthetic Mistral-7B experiments include fine-tuning; not a universal lossless-compression theorem. **P** for text methods, not a deployable universal optimizer. |
| **P07** [QUITO-X: A New Perspective on Context Compression from the Information Bottleneck Theory](https://arxiv.org/abs/2408.10497v3), **2025-10-13** | Uses an information-bottleneck formulation and query–context cross-attention from an **80M FLAN-T5-small** compressor as a relevance surrogate. §3–4, Table 2. | Llama-3-8B-Instruct, Quoref, retained ratio **0.25**: QUITO-X **86.8 EM** versus full context **93.1**; LLMLingua-2 gives **65.5** in that comparison. | Better than another compressor is still **6.3 points below full context**. Attention is a practical surrogate, not proof all task information survives. Chunking and benchmark/model choice matter. **P**, requiring auxiliary-model internals, not target internals. |
| **P08** [Lost in the Middle](https://arxiv.org/abs/2307.03172v3), **2023-11-20** | Moves answer-bearing documents through otherwise comparable multi-document QA prompts; also evaluates key–value retrieval. §2–3, Appendix G Table 6. | GPT-3.5-Turbo with 20 documents: **75.8%** when evidence is first, **53.8%** at index 9, **63.2%** last; closed-book accuracy **56.1%**. | The same evidence can yield a **22-point** positional gap in this historical setup. Not a claim that every 2026 model has the same curve. **E/P**: position tests and reorder ablations work through APIs. |
| **P09** [RULER](https://arxiv.org/abs/2404.06654v3), **2024-08-06** | **13** configurable synthetic tasks expand beyond single-needle retrieval into multi-hop tracing and aggregation. §3–6, Table 3. | GPT-4 row: **96.6** at 4K, **87.0** at 64K, **81.2** at 128K; effective length **64K** under the paper’s **85.6** Llama2-7B reference threshold. | Effective length is an operational benchmark definition, not a hardware limit. Synthetic behavior and the fixed threshold need not represent production tasks. **E**, black-box testing possible. |
| **P10** [NoLiMa](https://arxiv.org/abs/2502.05167v3), **2025-07-09** | Constructs retrieval questions with minimal literal overlap, requiring associative links; varies length, position, and distractors. §3–5, Table 3, appendices. | GPT-4o: short-context base **99.3**, **69.7 at 32K**; its effective length is **8K** at the paper’s 85%-of-base threshold. | Failure without exact lexical cues can be missed by ordinary needle tests. Synthetic association coverage and historical model snapshots limit transfer. **E**, suitable as one stress-test family. |
| **P11** [LongMemEval](https://arxiv.org/abs/2410.10813v2), **2025-03-04** | **500** questions cover extraction, multi-session reasoning, temporal reasoning, updates, and abstention; separates indexing, retrieval, reading. §3–5. | LongMemEval-S is about **115K tokens** per problem. Figure 3: Llama-3.1-Instruct-8B accuracy **0.710 oracle→0.420 full history** (**40.8% relative drop**). M uses 500 sessions, about 1.5M tokens. | Oracle evidence is an upper-bound diagnostic, not an available production input. Fact-only memory loses information overall even when it helps some categories. **E/P**, needs persistent state and lifecycle evaluation. |
| **P12** [MemCoRe: Recovering Evidence from Progressively Compressed Factual Knowledge for Agent Memory](https://arxiv.org/abs/2602.07885v3), **2026-09-04** | Preserves atomic factual notes beneath compressed keyword/topic indexes; retrieves and refines evidence through multiple paths. §2–3, Tables 1–2, appendices. | LoCoMo with GPT-4o-mini: reported average **43.76 F1**, versus **41.97** for A-MEM and **39.74** for the paper’s LoCoMo baseline. Retrieval allows up to **3** refinement iterations. | Renamed from **MemFly** across revisions. These results do **not** establish lower lifetime cost; construction, storage, retrieval, and refinement are additional work. Recent preprint, lexical metrics, limited benchmark coverage. **P**, stateful orchestration rather than a stateless filter. |
| **P13** [Learning to Compress Prompts with Gist Tokens](https://arxiv.org/abs/2304.08467v3), **2024-02-12** | Instruction-tunes with special gist tokens and attention masks; caches their learned activations. §2–6, Table 3. | Average instruction KV length **26→1**. LLaMA-7B, single-forward-pass profiling: roughly **40% FLOP reduction versus no cache**, but only **0.11% FLOP** and **1% wall-time** improvement versus full instruction caching. | The cache-aware baseline changes the economic story. Instruction compression is not arbitrary long-document retention. **M**; literal text spelling of a gist token is not its learned activation. |
| **P14** [TALE: Token-Budget-Aware LLM Reasoning](https://arxiv.org/abs/2412.18547v5), **2025-06-02** | Estimates a task budget and prompts concise reasoning (EP); also studies training-based internalization (PT). §3–6, Tables 3–4. | GPT-4o-mini GSM8K: **318.10→77.26 output tokens**, **81.35→84.46%** accuracy. MathBench-College: **675.78→259.85 tokens**, but **78→70%** accuracy. | Large savings are not uniformly quality-neutral. Table 3’s caption conflicts with its average row; use task cells. Prompt budgets are soft; PT requires training. **P** for EP, **M** for PT. |
| **P15** [s1: Simple test-time scaling](https://arxiv.org/abs/2501.19393v3), **2025-03-01** | Fine-tunes Qwen2.5-32B-Instruct on **1,000** curated examples; budget forcing terminates or extends thinking via decoding interventions. §2–5, Tables 3–4; Appendix A. | s1-32B AIME24: **50.0→56.7%** with four “Wait” extensions; Table 3 reports **100%** control for forcing versus **40%** for token-conditional prompting. | Extra reasoning sometimes buys quality—the optimum is not always shortest. Small math sets, inference nondeterminism, and separate s1.1 results matter. **M** for the evaluated mechanism; ordinary prompting is not equivalent. |
| **P16** [Prompt Compression in the Wild](https://arxiv.org/abs/2604.02985v1), **2026-04-03** | Separates compressor overhead, **compressor-inclusive time-to-first-token (TTFT)**, quality, achieved rate, and GPU memory. §4.2 uses a **one-token-output setup** for the plotted speedups. | Mistral-7B with Transformers reports **3–4× TTFT speedups** for prompts >2K and compression ≥5×—**not full-generation or task-completion speedups**. The paper reports **no reliable TTFT speedup for its tested GPT-3.5 Turbo / GPT-4o mini API setups**. | Specific historical endpoints, hardware, and serving conditions; not a universal API result. Abstract/body metrics and reader-reported memory figures remain unresolved; see ambiguity note 8. **P/E**. |

## What “information retention” should mean

### Task-level objective, not text reconstruction

Let `C` be available context, `q` a task/query, `z=f(C,q)` selected or compressed context, and `a=M(z,q)` the result. An appropriate **proposed** optimization is:

```text
minimize  E[total lifecycle cost(f, M, task)]
subject to
  task success >= a predeclared non-inferiority threshold
  critical evidence/constraints retained
  latency and failure-rate limits met in every critical slice.
```

Rate–distortion asks which information can be discarded at an acceptable downstream loss; the answer changes with the query and distortion definition. Information-bottleneck methods supply a related relevance–compression perspective, but their operational surrogates do not constitute a universal sufficiency certificate [P06], [P07].

**Proposed distinction:** maintain both an evidence-retention test and an outcome test. Preserving every required datum does not guarantee the model will use it; a correct answer does not prove the compressor preserved evidence—it may have relied on prior knowledge. Oracle-evidence and no-context controls help separate these cases [P08], [P11].

A compression result should therefore report the task-conditioned failure surface, not just semantic similarity, a recovered paraphrase, or average benchmark score. This is an inference from the failure modes above, not a theorem that any particular selection policy is optimal.

### Query-specific versus reusable compression

- A query-aware compression can discard material irrelevant **to this query**, but reuse for another query requires another retention check [P03], [P06], [P07].
- A task-agnostic compressed artifact can be reused across questions, but its tested retention is empirical rather than guaranteed [P04].
- A summary or index can be a retrieval aid rather than the sole remaining record. MemCoRe explicitly retains factual evidence below more compressed indexes; this supports testing recoverable memory against destructive repeated summarization [P12].

## Why latent / special-token compression needs learning and a compatible interface

“Compressed prompts need retraining” is too broad. Ordinary extracted or summarized **text** can be sent to an unchanged target model; several methods train only an auxiliary compressor [P02], [P04], [P05].

The stronger requirement applies to a **new latent representation**. Gist training learns embeddings, attention behavior, and activations through which later tokens receive the hidden prompt information. Sending the string `<GIST>` to an unrelated text endpoint does not transmit those activations [P13].

**Important counterexample to “retrain the decoder”:** [ICAE, arXiv:2307.06945v4, 2024-05-08](https://arxiv.org/abs/2307.06945v4) (**B01**) trains a LoRA-adapted encoder and memory slots using autoencoding/continuation objectives and instruction fine-tuning, while keeping the target LLM unchanged. Its standard example maps **512 context tokens→128 memory slots**. The learned soft representations are injected at the model interface; they are not an ordinary text payload. It also reports that concatenating independently compressed spans initially failed until that pattern was added to training (§3.3).

**Inference:** latent compression needs an already learned encoder/decoder compatibility relationship; it need not update every base-model weight, and it need not retrain for every new prompt. An ordinary text-only proxy cannot assume embedding/activation injection or special-token semantics. Byte-level encodings such as compressed binary transported as text are also not demonstrated substitutes for a trained semantic bottleneck. No current provider-interface compatibility was tested here.

## Do not conflate the mechanisms

| Mechanism / primary source | What changes | What does not follow |
|---|---|---|
| Text selection/compression [P01], [P02], [P03], [P04], [P05], [P06], [P07] | The context actually submitted to the model. | It is not automatically lossless, faster, or cheaper after all stages are counted. |
| Learned soft/gist compression [P13], [B01] | Internal embeddings, activations, or learned memory slots representing the input. | Text API portability; arbitrary cross-model compatibility. |
| **B02** [KIVI, 2402.02750v2, 2024-07-25](https://arxiv.org/abs/2402.02750v2) | Quantizes KV-cache numerical precision, with asymmetric key/value treatment. | Fewer submitted prompt tokens or a provider billing discount. Requires serving-kernel/cache access. |
| **B03** [H2O, 2306.14048v3, 2023-12-18](https://arxiv.org/abs/2306.14048v3) | Evicts/selects cached attention states using recent and heavy-hitter tokens. | Pre-submission text compression; no guarantee evicted states preserve all evidence. Requires attention/cache control. |
| **B04** [Fast Inference from Transformers via Speculative Decoding, 2211.17192v2, 2023-05-18](https://arxiv.org/abs/2211.17192v2) | Drafts and verifies multiple candidate tokens, with an exact sampling correction preserving the target distribution under its assumptions. | Fewer semantic input/output tokens. The original T5-XXL experiment reports **2–3×** acceleration, not a token-price reduction. Requires draft/target decoding coordination. |

B02–B04 were reviewed for mechanism boundaries, not as deployment candidates or a comprehensive serving-performance comparison.

## Defensible quality / cost experiment design

**Everything in this section is a proposed protocol, not an executed experiment or a reported paper result.** Papers motivate the controls; numeric grids and gates below are suggested starting points to pre-register, not validated universal defaults.

### 1. Freeze the target and the success contract

Record target model/version, date, endpoint, tokenizer, temperature, decoding limits, tool permissions, prompts, and task rubric. Keep a held-out test set separated by document, user/session, and task family—not merely shuffled questions from the same source.

Define:

- **Primary:** end-to-end task success and total cost per success.
- **Non-inferiority:** e.g., no more than an agreed absolute task-success loss, with a confidence bound—not “looks similar.” The owner must set the margin according to failure consequences.
- **Critical slices:** exact identifiers, numbers/units, negation, temporal corrections, code constraints, tool schemas, provenance, and safety requirements. Do not permit overall averages to mask severe slice failures.
- **Abstention/recovery:** when required evidence cannot be retained within budget, test fallback to fuller evidence or abstention. Include their costs.

Do not let the compressor see answers, oracle evidence labels, future conversation turns, or hidden tests. Use oracle evidence **only** in a separately labeled diagnostic arm [P05], [P08], [P11].

### 2. Build a paired factorial evaluation

For the same tasks, compare:

1. Full context within the actual supported window.
2. The current truncation policy as a **separate** baseline when full input cannot fit.
3. No context / no demonstrations.
4. Simple whole-document or sentence selection at matched token budgets.
5. Query-aware text selection/pruning.
6. Query-agnostic pruning.
7. Abstractive summaries with citations/provenance.
8. Stateful memory: full evidence retrieval, summary-only memory, and compressed-index-plus-evidence recovery.

Within applicable arms, use a retained-input grid such as **1.0, 0.75, 0.5, 0.25, 0.1**; report actual target-token counts, not the requested ratio. Cross a short/default/long output or reasoning budget with selected context budgets. Keep stop limits distinct from instructions asking for brevity. Measure truncation and incomplete answers, rather than counting them as cheap successes [P14], [P15].

Include no-op bypass for short inputs; repeated-prefix/cached versus cold requests; one query versus multiple different queries over the same document. For learned latent methods, use a separate model-controlled experiment—never silently compare them as if they were interchangeable proxy operations [P13], [B01].

### 3. Include adversarially useful, task-relevant slices

- Move the same decisive evidence across beginning/middle/end while holding content constant [P08].
- Vary distractor count, multi-needle retrieval, joins, aggregation, and required evidence count [P09].
- Paraphrase away lexical overlap; include semantically similar distractors [P10].
- Test persistent memory across updates, contradictions, dates, and unanswerable questions; evaluate cold-start construction and long-lived sessions separately [P11], [P12].
- Test irreversible loss of IDs, signs, quotation boundaries, paragraph labels, schema fields, and relationships. Review failures where a fluent summary preserves topic but not answer-critical detail. Structural pruning failures are demonstrated in P16.

Alongside output correctness, measure recall of annotated required evidence, provenance correctness, constraint preservation, hallucinated additions, retrieval misses, malformed outputs, tool-call validity, and retries. Use executable or exact-match checks when appropriate; blinded human adjudication for ambiguous tasks. If an LLM judge is used, freeze its version/rubric, audit a stratified sample, and account for its evaluation expense separately.

### 4. Count the complete economics

Use an explicit ledger per task and aggregate across the lifecycle:

```text
total task cost =
    selection/compressor inference
  + all target-model calls
  + memory construction and update allocation
  + embedding/search/storage allocation
  + tool/external-service charges
  + verification, retry, recovery, and fallback calls.

cost per successful task =
    total cost of all attempted tasks / number meeting the success rubric.
```

For model calls, record separate **billed uncached input, cached input, visible output, and billable reasoning categories where exposed**. Use actual usage/invoice semantics at experiment time; avoid double-counting categories. If a provider exposes no reasoning count, mark it unknown rather than inferring it from visible verbosity. Do not insert current prices from memory; this review did not retrieve or assume current tariffs.

Measure wall-clock **preprocessing**, **time to first token**, **time to final successful result**, p50/p95, queue/concurrency effects, cold/warm state, and variability across interleaved paired runs. Separately record local GPU memory, GPU-time/energy if observable, and cache behavior. Reduced remote input counts are not proof of end-to-end latency improvement [P16].

For a reusable compressed artifact, compare amortized cost at different actual reuse counts and a changed-query workload. A useful accounting identity is:

```text
compression pays financially only when
    downstream billed savings across reuse
    > compression + upkeep + extra retries/recovery + cache-related penalties.
```

This is bookkeeping, not a claim that all those terms are positive or exposed by every service.

### 5. Analyze uncertainty and select on a frontier

Use paired differences and confidence intervals; cluster resampling by document/user/session where observations share evidence. Pilot task variance and disagreement rates, then determine sample size for the declared non-inferiority margin. Do not claim that a convenient fixed number of tasks is automatically enough.

Pre-register the search grid and select budgets on development data. Report test results once for selected policies, including all adverse categories and failure examples. Show the Pareto frontier for **quality, total cost, and completion latency**, not a single weighted number unless the weights were declared in advance.

Publish at least:

- a per-task ledger and paired outcomes;
- actual versus requested compression and generation budgets;
- subgroup quality confidence intervals;
- conditional failure rates when evidence was retained versus lost;
- total and marginal memory costs at declared reuse/session lengths;
- cold/warm latency distributions;
- bypass/fallback rates and complete cost;
- exact model/source/tokenizer versions and run dates.

**Proposed acceptance:** adopt a policy only if it meets the declared quality and critical-slice gates and improves the chosen economic objective with uncertainty reported. “No compression” must remain an eligible winner.

## Version notes and unresolved ambiguity

1. **Not a complete census of all literature published by October 4, 2026.** The search started from the requested works, followed their methodological connections, and added recent primary work. MemCoRe and the 2026 deployment study were inspected beyond abstracts. No “latest in the entire field” claim is made.
2. **Selective Context has two identifiers in circulation.** The load-bearing conference-era paper here is **2310.06201v1**. [**2304.12102v1 (2023-04-24)**](https://arxiv.org/abs/2304.12102v1) is the earlier *Unlocking Context Constraints of LLMs* preprint; its metadata is retained as a precursor, not counted as independent corroboration.
3. **MemFly→MemCoRe:** use **2602.07885v3 (2026-09-04)** claims and title; do not combine the earlier abstract’s headline with this revision’s tables.
4. **TALE v5 inconsistency:** Table 3’s caption gives **80.22 accuracy / 138.53 output tokens**; its average row gives **81.03 / 148.72**. The body also says seven datasets where six rows appear. The matrix deliberately uses individual task cells. No aggregate from the caption is treated as resolved.
5. **Compression-ratio conventions differ.** Here “retained ratio” is compressed/original and “× compression” is original/compressed. Report which tokenizer counted which input, and whether instructions, query, wrappers, or examples were excluded.
6. **Surrogate and selection biases:** similarity scores, lexical F1, oracle choices, truncation-limited baselines, and comparisons against weaker compressors can all support narrower claims than “quality preserved.” The matrix identifies these boundaries.
7. **Historical models remain historical.** The reviewed papers do not establish current TokenMaster workload performance, present provider prices, current endpoint behavior, or the safety of a specific compression policy.
8. **P16 metric and source mismatch (rechecked October 4, 2026):** the abstract advertises **up to 18% end-to-end speedup**, while §4.2's favorable **3–4×** result measures compressor-inclusive **one-token TTFT**. Do not merge these into one latency headline. The reader-supplied extract additionally reports **43% TTFT improvement** and **53% / 64% aggregate GPU-memory increases** in a §4.4 example, alongside low-memory-overhead wording. Those conditions and memory-accounting scopes are **unresolved, not reconciled**. The [v1 HTML](https://arxiv.org/html/2604.02985v1) and [v1 PDF](https://arxiv.org/pdf/2604.02985v1) returned during this recheck instead label the TTFT plot **Figure 3** and memory analysis **§4.5**; neither yielded the 43%/53%/64% figures or literal `max_new_tokens=1` parameter, although the one-token setup is explicit. These additional figures and the Figure 2/§4.4 numbering are therefore retained as **reader-supplied, not independently verified in the retrieved representations**. No causal explanation, aggregate memory-saving claim, or full-generation speedup is inferred from the discrepancy [P16].

## Supporting examples / source-reference evidence / OSS evidence

The numeric examples above are paper results, not reproductions. No upstream implementation or third-party source was necessary to establish the central claims; no OSS implementation was audited. API feasibility is an explicitly labeled inference from each paper’s required interfaces.

## Reusable takeaway

**Treat context, memory, and reasoning length as a joint task-conditioned allocation problem. Preserve recoverable evidence, test hard failure slices, and choose measured quality–cost frontiers. Do not sell token reduction as proven latency reduction, or a paper’s benchmark as TokenMaster validation.**

## Pinned source index

[P01]: https://arxiv.org/abs/2310.06201v1
[P02]: https://arxiv.org/abs/2310.05736v2
[P03]: https://arxiv.org/abs/2310.06839v2
[P04]: https://arxiv.org/abs/2403.12968v2
[P05]: https://arxiv.org/abs/2310.04408v1
[P06]: https://arxiv.org/abs/2407.15504v2
[P07]: https://arxiv.org/abs/2408.10497v3
[P08]: https://arxiv.org/abs/2307.03172v3
[P09]: https://arxiv.org/abs/2404.06654v3
[P10]: https://arxiv.org/abs/2502.05167v3
[P11]: https://arxiv.org/abs/2410.10813v2
[P12]: https://arxiv.org/abs/2602.07885v3
[P13]: https://arxiv.org/abs/2304.08467v3
[P14]: https://arxiv.org/abs/2412.18547v5
[P15]: https://arxiv.org/abs/2501.19393v3
[P16]: https://arxiv.org/abs/2604.02985v1
[B01]: https://arxiv.org/abs/2307.06945v4
[B02]: https://arxiv.org/abs/2402.02750v2
[B03]: https://arxiv.org/abs/2306.14048v3
[B04]: https://arxiv.org/abs/2211.17192v2

