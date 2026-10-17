# TokenMaster: fundamental LLM token economics

**Research date:** October 4, 2026  
**Repository examined:** `All-The-Vibes/TokenMasterX`  
**Local source revision:** `426fc853389ddba4bc6e1dd35a28179a895c064f` (`master`)  
**Scope:** research, source inspection, and isolated local probes—not a production implementation or a newly run model-quality benchmark.

## Executive decision

**Optimize the total cost of a verified successful task, subject to quality, latency, privacy, and safety constraints. Do not optimize a compression percentage in isolation.**

TokenMaster's most promising fundamental advantage is preventing unnecessary work: answer a structural question with a bounded, versioned graph query instead of repeatedly reconstructing the answer through file reads. Its next advantage is choosing the smallest sufficient representation of the evidence the agent actually needs. Compression is one mechanism within that strategy, not the objective.

The recommended order is:

1. Make the measurements and recovery guarantees trustworthy.
2. Capture actual per-call usage and cache behavior rather than summing context-utilization displays.
3. Reduce evidence acquisition before it reaches the model: targeted graph queries, filtering, projection, aggregation, and pagination.
4. Compress new evidence once, preserving the existing cacheable prefix and exact critical details.
5. Introduce task-aware memory, model routing, and reasoning/output budgets only behind end-to-end evaluations.
6. Treat inference-engine optimizations as a separate deployment option, not something a Claude/Copilot plugin can universally provide.

**The research does not establish any new percentage saving for TokenMaster.** Local probes expose concrete defects in the present measurement/safety layer. Published results below belong to their authors' models, datasets, baselines, and hardware.

### Reading map

- **This report:** conclusions, economic model, local evidence, implementation sequence, and consolidated research.
- **Paper methods/results:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\papers\research-memo.md` — 16 core publications and 4 mechanism-boundary references, with versioned metadata.
- **Eight-project source review:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\oss\REPORT.md` — source/test lines, maintenance, releases, licenses, runtime, and security.
- **Three direct harness references:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\reducers\REVIEW.md` — RTK, TOON, Context Mode.
- **Reproducible local evidence:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\local-audit.json`.

## 1. Evidence standard and limitations

The report distinguishes:

- **Observed:** source inspected at the revision above or an isolated probe executed during this review.
- **Publisher result:** an upstream paper or project reports a result; it was not independently reproduced here.
- **Inference:** a conclusion from inspected source, documented interfaces, or explicit assumptions.
- **Proposal:** an implementation or experiment that has not been performed.

Primary sources include upstream source/tests, arXiv papers, and official provider/protocol documentation. Popularity is an adoption signal, not proof of relevance, safety, or savings.

Research outputs live under:

`C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics`

The repository deliberately ignores research directories. These files are local artifacts, not committed deliverables. No production source, account configuration, model routing, or installed dependencies was changed.

## 2. What “real token economics” means

### 2.1 There are at least four different quantities

| Quantity | What it measures | What it does not establish |
|---|---|---|
| Context occupancy | Tokens occupying the current window | Actual billed tokens, number of model calls, or task success |
| Cumulative input tokens | Sum of input over calls | Equal price per token, output/reasoning cost, cache writes, compressor cost |
| Provider/account usage | Uncached, cached, write, output, and other billable categories | Whether the task was completed correctly or the user actually paid incremental cash |
| Cost per verified successful task | All measured spend, including failed attempts, divided by verified successes | A guarantee on other tasks, models, traffic, or cache conditions |

For a benchmark batch, use:

```text
cost_per_verified_success =
    total_cost_of_all_attempts_and_required_verification
    / number_of_verified_successes
```

Report success rate beside this metric. Do not hide failed attempts by reporting cost only among successful runs. When a batch has zero successes, the metric is undefined/infinite—not zero.

For mutually exclusive billing categories normalized by a provider adapter:

```text
C_task = sum over model calls/call-shares attributed to this task j (
    p_uncached(j) * U_j
  + p_cache_read(j) * R_j
  + p_cache_write(j) * W_j
  + p_output(j) * O_j
) + C_additional_nonmodel_compression
  + C_additional_nonmodel_tools_and_storage
  + C_additional_nonmodel_index_build_and_updates_allocated_to_task
  + C_other_costs_not_already_in_the_ledger
```

Retries, retrieval calls, model-based verification, model-backed tools, and model-based compression belong in the call sum. Shared model-based indexing is attributed once through an explicit allocation policy. **Every additional term excludes costs already represented by those calls/call-shares**; a model-based compressor must not be charged again as compression overhead. A provider may include reasoning inside output usage or cached usage inside total input; normalize those definitions before adding fields. Unknown cost is **unknown**, not zero.

For subscription and included-credit plans, report resource consumption, consumed credits/quota, and actual marginal cash separately. Saving credits is not necessarily an immediate reduction in a flat monthly invoice.

Visible response length is also not necessarily billed reasoning length. Anthropic documents configurations where displayed thinking is summarized but full thinking is charged. Measure native usage rather than the length of what a UI renders. [D7]

### 2.2 Cache-aware cost can reverse the apparent winner

**Illustrative arithmetic, not a provider price quote or measured TokenMaster result.**

Assume an uncached input token costs 1 unit and a cached read costs 0.1 units:

| Case | Uncached tokens | Cached-read tokens | Cost units |
|---|---:|---:|---:|
| Existing warm 10,000-token request | 1,000 | 9,000 | 1,900 |
| Rewrite history to 5,000 tokens and miss cache | 5,000 | 0 | 5,000 |
| The 5,000-token representation after warming | 500 | 4,500 | 950 |

The transition request has **50% fewer input tokens but 2.63 times the input cost**. Under this simplified repeated-request scenario, the new representation becomes cumulatively cheaper on request 5. Compression compute, retrieval, quality changes, TTL expiry, and changing suffixes are deliberately excluded.

The example is reproducible in `local-audit.json`. It illustrates why the decision is not “always compress” or “never rewrite.” Compare the transition cost with the expected remaining horizon.

Official caching documentation makes exact-prefix reuse and provider/model-specific usage/pricing material to this decision. A deterministic chunk helps, but it does not establish that the entire request prefix, tool ordering, routing, model, retention policy, and cache lookup are unchanged. [D1, D2]

### 2.3 The right decision is marginal, not global

For one proposed transformation:

```text
expected_net_benefit =
    expected_future_billed_cost_avoided
  - compression_and_indexing_cost
  - expected_cache_transition_cost
  - expected_retrieval_and_extra_turn_cost
  - expected_recovery_or_retry_cost
```

Apply a separate quality/safety constraint; do not pretend every possible error can be assigned a reliable dollar price.

For graph construction:

```text
break-even uses > build_cost /
    (baseline_lookup_cost - indexed_lookup_cost - average_update_cost_per_use)
```

This is an illustrative amortization model. If the denominator is non-positive, the index does not pay back under those assumptions. Include source changes and validation costs: “understand once forever” is not a correctness contract.

### 2.4 Compression is a task-conditioned information problem

Let `X` be the available evidence, `q` the task, and `Z = f(X, q)` the representation sent to a model.

The proposed optimization is:

```text
minimize expected total task cost using Z
subject to:
    task distortion D(answer(X, q), answer(Z, q)) <= chosen tolerance
    latency and safety constraints are satisfied
```

For a code-editing task, distortion should measure patch correctness, tests, and preserved requirements—not word overlap. For an extraction task, exact IDs, quantities, negation, and missing-field handling matter.

A hash or compressed disk blob does not communicate arbitrary omitted facts to an unchanged language model. A retrievable original creates a side channel; it does not guarantee the agent recognizes when to use that channel. Evaluate both **recoverability** and **successful discovery/retrieval of needed evidence**.

## 3. What TokenMaster can actually control

| Layer | Feasible in the existing harness/plugin boundary? | Main economic mechanism |
|---|---|---|
| Task scope and stopping rules | Yes, through instructions and orchestration; host-dependent enforcement | Avoid unnecessary work and output |
| Structural retrieval / graph query | Yes | Avoid repeated search/read/reasoning calls |
| Tool-result projection and compression | Yes for owned tools; broader rewriting requires verified host/transport support | Reduce new context and later context residency |
| Context assembly and provider cache policy | Only to the extent the host or an authorized adapter exposes it | Reuse unchanged prefixes; avoid expensive cache transitions |
| Persistent memory | Implementable locally, but requires provenance/invalidation and retrieval evaluation | Avoid re-derivation without replaying entire histories |
| Model and reasoning-budget routing | Host/API dependent; not automatically controlled by an MCP server | Choose a cheaper sufficient execution policy |
| KV allocation, quantization, eviction, speculative decoding | No for arbitrary hosted model backends | Requires inference-server/model control; usually hardware efficiency rather than fewer visible prompt tokens |
| Learned latent/soft-token compression | Generally not a transparent drop-in to hosted APIs | Requires compatible encoders/decoders, training, or model access |

MCP tools are model-controlled application capabilities. A separate compression tool cannot retroactively remove a raw output that has already been put into the host's transcript. Prefer a bounded result from the originating tool, a verified append-boundary hook, or an explicitly supported transport adapter. [D4]

Current provider contracts also protect opaque/signed reasoning state. Do not run generic text compression over these protocol fields. Preserve tool-call/result relationships and model-specific message invariants. [D7]

## 4. Source-level findings in current TokenMaster

All production paths in this section are relative to:

`C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master`

Their source is pinned to the revision at the top of this report. The independent probe is:

`C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\audit_local.py`

### 4.1 Findings that should precede stronger savings claims

| Priority | Finding | Evidence and consequence |
|---|---|---|
| P0 | The shipped recovery validator can report success without attempting recovery | `brainspace/benchmark.py:130–138` calls `findall` on the compressed text, then parses the returned bare hash with the placeholder regex again. The second match is empty, so the check is skipped. A fault-injected store whose `retrieve` always returns `None` still reported `lossless=true`; it received **zero retrieval calls**. |
| P0 | “Never expand” is checked before the outer footer | `brainspace/router.py:170–177` checks the inner text, but `brainspace_mcp.py:84–89` and `brainspace_posttooluse.py:132–137` append more text afterward. In the shipped character-proxy mode, the real entry points produced **269 input units → 267 inner units → 290 emitted units**. This is not an exact provider-token measurement. |
| P0 | Default prose normalization can change literal meaning without a recovery reference | A small Markdown code fence containing unequal string literals became an assertion comparing identical strings. `prose_compressor.py:62–75,136–144` rewrites interior spaces, while originals under the stash threshold receive no reference. The task-relevant statement changed, not just its typography. |
| P0 | Exact CCR recovery is not exact MCP delivery for large originals | `brainspace_mcp.py:109–111` truncates at 200,000 characters by default. A 200,100-character original round-tripped through CCR, but not through the actual retrieval tool. There is no range/continuation argument in its current signature. |
| P1 | Structured hook output loses its original shape | `_extract` records a response key, but `main` does not use it when emitting `updatedToolOutput`. A structured Bash fixture was replaced with a string. Current Claude Code documentation requires built-in output replacements to preserve response shape; host rejection is a documentation-based inference, not a live-host result from this review. [D3] |
| P1 | Graph freshness is not invalidated in-process | `graphify_mcp.py:76–81,103–114` loads once. Replacing a temporary graph file with a new symbol left the running module serving the old symbol. Rebuilding a graph file alone does not establish freshness in an already running server. |
| P1 | Current compression measurement is not native usage | `brainspace/tokens.py:19–50` uses optional `cl100k_base`, otherwise `ceil(chars/4)`. Neither a fixed cross-model tokenizer nor this heuristic proves provider-billed savings or universally stable compression ratios. |
| P2 | Same bytes do not guarantee the same complete placeholder | `ccr.py:151–166` hashes content but embeds caller-supplied metadata in the visible marker. The same content with two source labels produced the same hash but different marker strings. Determinism must include canonical metadata and placement. |

Even after repairing the benchmark's parsing, checking only that retrieval is non-null is insufficient. Verify exact content/hash equality, complete delivery, needed-evidence recall, and task outcome separately.

### 4.2 Existing navigation evidence needs reconciliation, not dismissal

The README's 73.1% pooled cumulative-input reduction matches the on-disk:

`C:\Users\shyamsridhar\code\TokenMaster\sandbox-plugin-bench\swebench\NAV_REPORT.md`

That report is an older local artifact, not a benchmark rerun performed here. It explicitly says the metric is summed CLI context utilization, not cloud-billed tokens, and that this is a navigation pilot rather than SWE-bench patch resolution.

It also reports:

- 2 repositories, 3 tasks, 2 repetitions, and 3 arms.
- Graph routing in 12/12 B-arm runs.
- A scikit-learn inheritor cell with baseline correctness 2/2 and B-arm correctness 0/2.
- Tolerant name/count-based oracles, not an exact semantic ground truth.

Thus **12/12 routing adoption must not be presented as 12/12 correctness**. The README's zero-regression language and this matching local report need explicit provenance reconciliation. The aggregate token benefit remains an interesting signal; it is not proof of universal savings, no per-task regressions, or monetary savings.

### 4.3 Fresh verification performed

- Shipped test suite under the available default Python: **110 passed, 10 failed**.
- Those 10 failures are in code-skeletonization paths; the environment lacks `tree-sitter` and the Python/Rust grammars. They are an explicit dependency-limited validation gap, not evidence that all those code paths are intrinsically broken.
- No dependencies were installed to change that result.
- Research probes used an existing MCP environment (`mcp 1.27.2`, Python 3.13.15); they executed real local functions and the actual hook subprocess.
- That environment lacked `tiktoken`; emitted-size probes use the product's supported heuristic fallback and are labeled accordingly.
- No paid model/API calls, live CLI task benchmark, host-rewrite acceptance test, or inference-server benchmark was run.
- Tracked working-tree contents remained unchanged.

Machine-readable evidence: `local-audit.json`. Baseline log: `pytest-baseline.txt`; the final baseline rerun's exact interpreter, command, environment dependencies, duration, and exit code are recorded in `pytest-baseline-run.json`.

## 5. Measurement implementation proposal

### 5.1 A minimal ledger, not another large framework

Add a small append-only per-task usage ledger in the existing benchmark/runtime boundary. A useful record contains:

```text
task_id, attempt_id, call_id, parent_call_id
provider, host, host_version, model, model_version, pricing_snapshot_id
native_usage_payload_reference, normalized_usage_categories
estimated_tokens_before, estimated_tokens_after, estimator_identity
final_serialized_result_size, transform_id, source_version, retrieval_reference
cache_hit_or_read_usage, cache_write_usage, compression_time
wall_time, tool_time, model_time, retrieval_count, retries
verification_result, task_outcome, cost_status
```

Missing native usage stays null with an explicit status. Record estimates and native usage separately. Do not silently fall back from billed cost to a heuristic “dollar” number.

Important current opportunity: GitHub's Copilot SDK documents distinct per-call usage, context-window utilization, and accumulated session cost APIs. It also exposes model billing prices and flags several aggregate RPCs as experimental. This is a stronger foundation than scraping utilization lines, when TokenMaster owns or is integrated with that client boundary. Pin both SDK and CLI versions and reconcile aggregate totals rather than assuming a field called `cost` is currency. [D5, D6]

Do not assume that a plugin installed into somebody else's opaque host can access the same signals. Make capability detection explicit:

```text
mode = native-usage | observed-host-usage | estimated-only
```

### 5.2 Keep the useful existing architecture

Extend, rather than replace:

- `brainspace/tokens.py`: explicitly identify estimator/model; retain safe offline estimates without calling them native billing.
- `brainspace/router.py`: return transform provenance and fidelity classification; accept task intent and an explicit budget only when available.
- `brainspace_mcp.py` and `brainspace_posttooluse.py`: validate final emitted envelopes, not only internal strings; preserve host response schemas.
- `brainspace/ccr.py`: versioned, scoped retrieval with exact hashes, complete ranges/continuations, and live-reference retention.
- `brainspace/benchmark.py`: correct byte/hash equality tests, then separate micro-compression reports from task-outcome reports.
- `graphify_mcp.py`: graph identity and source-digest checks, incremental refresh or a clear stale refusal, bounded deterministic query views.

These are proposed edits, not changes made by this research.

Move routine savings counters/marketing footers into the ledger or user interface rather than making the model pay to read them on every turn. Keep only compact operational recovery instructions where they are needed.

## 6. Context policy proposal

### Before compression: avoid acquiring unnecessary content

The cheapest large tool output is often the one never requested. For structured evidence, push operations into the data/tool layer:

- `SELECT` only required fields; filter before serialization.
- Return failed test cases plus exact error evidence rather than a full successful-test stream.
- Return graph candidates with locations and coverage/uncertainty, then inspect the needed slices.
- Compute exact aggregates in code rather than asking the model to scan a large table.
- Paginate stable datasets and expose count/coverage/continuation explicitly.

These transformations have task-specific contracts. A test-log filter that hides warnings or the only causal line is not safe merely because it is smaller.

### At the append boundary: choose a representation

For each new evidence item, choose between:

1. Full original.
2. Deterministic exact structured projection.
3. A bounded extract with preserved identifiers, quantities, errors, and provenance.
4. A semantic summary plus retrievable original, labeled lossy.
5. A compact reference when omission is acceptable and retrieval is discoverable.

Never treat system/developer policies, user requirements, denial decisions, tool-call IDs, opaque reasoning blocks, or access-control facts as ordinary redundant prose.

Check **the full delivered representation**, including footers, references, JSON framing, tool schemas, and additional model calls. Fail open to the original when safe compression is unavailable.

### During continuation: preserve working state, not every observation

Maintain a bounded task record:

```text
objective and explicit requirements
verified facts with source version and evidence reference
decisions and rationale needed for continuation
current patch / relevant diff
unresolved questions and failed approaches worth remembering
next verification action
```

This is a proposed task memory, not an assertion that semantic summarization is lossless. Preserve the raw evidence out of band when authorized, and test memory retrieval on questions not used to create the summary.

### Cache and security constraints

- Prefer stable policy/tool prefixes and append new evidence without repeatedly rewriting old turns.
- Changing representation mid-task is a deliberate transition with expected payback, not automatically a bug.
- Keep cache keys, repository identity, tenant/access scope, model/tokenizer identity, and source freshness separate.
- A content hash is an identifier, not an authorization token. Retrieval must remain inside the caller's permitted scope.
- Do not log credentials or full sensitive payloads merely to measure savings.
- Store audit metadata and source digests; make full evidence retention explicit and configurable.
- Do not mistake KV reuse for semantic answer caching. Returning an old answer requires an equivalence and freshness contract.

## 7. Experimental plan

### Gate A: deterministic correctness and accounting

Before model experiments, add regression tests for every finding in section 4 and for:

- Exact literals/identifiers, negation, zeros, nulls, units, and Unicode.
- Rare failures buried in repeated success logs.
- JSON ordering and cardinality, absent versus empty fields, and paging boundaries.
- Source edits after indexing and stale-memory retrieval.
- Store failure, eviction, hash ambiguity, malformed references, and cross-scope denial.
- Full final-envelope token/size accounting and complete recovery of oversized originals.
- Unsupported host contracts returning the original rather than pretending to transform it.

Include the actual function/tool/hook paths. Pure compressor unit tests cannot establish host behavior.

### Gate B: task-level ablations

Use a randomized paired design, not separate hand-picked demos:

| Arm | Configuration |
|---|---|
| A | Unmodified host baseline |
| B | Graph routing only |
| C | Compression only |
| D | Graph plus compression |
| E | Cache-aware, task-aware policy |

Start with a cost-bounded pilot, for example 20 tasks × 5 arms × 2 repeats = **200 runs**, only after a run budget is explicitly approved. This is a proposed design, not an execution commitment or a powered final study.

Include structural navigation, edits that must pass tests, debugging, large structured data, long-session recall, and a negative-control class where the baseline is already cheap.

Hold model/version, tool catalog, repository snapshot, system policy, task prompt, and success oracle constant within comparisons. Randomize order. Separate cold and warm cache regimes, account for TTL, and prevent shared-prefix contamination between arms.

### Required outcomes

- Native billed categories and consumed credits/currency where available.
- Cost per verified successful task and success rate.
- p50/p95 end-to-end latency and time to first useful output.
- Extra calls, retries, restoration requests, and fallback rates.
- Exact-evidence retention/recall and silent-omission failures.
- Index build/update cost and amortization horizon.
- Confidence intervals grouped by task/repository, not treating repeated turns as independent tasks.

A proposed rollout gate might require the **upper confidence bound of candidate-minus-baseline cost per success to be below zero**—equivalently, the lower confidence bound of savings must be above zero—while meeting a predeclared non-inferiority margin on success and an agreed latency budget. A favorable lower bound on the cost difference alone is insufficient. Choose the margins with users; they are product requirements, not constants supplied by a paper.

Do not infer a negligible failure rate from a small zero-failure sample. For independent Bernoulli trials, zero failures in `n` trials has a one-sided 95% upper failure bound of `1 - 0.05^(1/n)`; roughly 300 independent trials are needed to push that bound below 1%. Correlated tasks weaken that calculation.

## 8. Delivery sequence

| Stage | Deliverable | Exit criterion |
|---|---|---|
| 0 — Trust | Fix local guarantees and publish reproducible tests | Every section-4 issue has an explicit passing regression or documented host limitation |
| 1 — Meter | Native-usage ledger plus pricing/capability adapters | Per-task totals reconcile to the source provider/host counters; estimates remain separately labeled |
| 2 — Avoid work | Fresh graph queries and task-specific bounded tools | Pilot task success is maintained; total cost includes indexing and verification |
| 3 — Pack safely | Exact/projection/extractive views and complete recovery | Final-envelope accounting passes; no silent loss of critical evidence; cache transitions are measured |
| 4 — Adapt | Task memory, selective learned compression, model/reasoning routing | Held-out workload improves cost per success within latency/quality limits |
| 5 — Optional serving | LMCache / serving-engine experiments for self-hosted deployments | Separate hardware-throughput benchmark; no claim that this is enabled by the plugin alone |

Avoid building a universal optimization gateway before stage 0/1 can tell whether an optimization actually helped.

## 9. What the papers establish

**Sixteen core publications plus four mechanism-boundary references were reviewed.** The paper appendix pins versions and records inspected methods/evaluation sections, exact conditions, conflicting numbers, and limitations. It does not claim an exhaustive “latest in the field” inventory.

| Research thread | Reviewed primary evidence | Implication for TokenMaster |
|---|---|---|
| Task-conditioned information | **Fundamental Limits of Prompt Compression**, `2407.15504v2`; **QUITO-X**, `2408.10497v3` | Optimize downstream distortion under a query/workload, not a universal “importance” score. Exact theoretical optima in tractable settings do not yield a universal production guarantee. |
| Text compression without changing the target model | **Selective Context**, `2310.06201v1`; **LLMLingua**, `2310.05736v2`; **LLMLingua-2**, `2403.12968v2` | Extractive compressors can sit before an ordinary text API, but introduce auxiliary-model work and content-selection risk. Treat code, instructions, IDs, and protocol fields differently from redundant prose. |
| Query-aware retrieval compression | **LongLLMLingua**, `2310.06839v2`; **RECOMP**, `2310.04408v1` | Select documents/sentences for the current question; sometimes the right augmentation is empty. Separate selection, reordering, and token deletion in ablations. |
| Effective rather than advertised context | **Lost in the Middle**, `2307.03172v3`; **RULER**, `2404.06654v3`; **NoLiMa**, `2502.05167v3` | Evaluate evidence position, multi-hop/aggregation, distractors, and minimal lexical overlap. A large context window or a literal-needle pass is not a quality guarantee. |
| Durable memory and evidence recovery | **LongMemEval**, `2410.10813v2`; **MemCoRe**, `2602.07885v3` | Preserve source evidence below compact indexes; test temporal corrections, abstention, and retrieval/reader errors separately. MemCoRe is the September 2026 revision of work earlier named MemFly; account for memory construction/refinement cost. |
| Latent/gist representations | **Gist Tokens**, `2304.08467v3`; **ICAE**, `2307.06945v4` | Learned activations/memory slots are not strings a generic proxy can substitute. ICAE trains an encoder with a fixed decoder: “all compression requires retraining the target” would be wrong. |
| Reasoning/output budgets | **TALE**, `2412.18547v5`; **s1**, `2501.19393v3` | Budget reasoning by task, with fallback and success tests. More reasoning can help; shorter is not inherently better. s1's evaluated decoding intervention is not equivalent to an ordinary prompt instruction. |
| Deployment-sensitive net benefits | **Prompt Compression in the Wild**, `2604.02985v1` | Include compressor overhead and the actual serving stack. Its commercial-API experiments did not show reliable compressor-inclusive **time-to-first-token** improvements; the timing setup generates one output token, not a whole task. |
| Serving-only mechanisms | **KIVI**, `2402.02750v2`; **H2O**, `2306.14048v3`; **Speculative Decoding**, `2211.17192v2` | KV precision/eviction and speculative generation optimize a different layer. They require serving/model control and do not imply fewer visible or billable prompt tokens. |

### Three results that change the engineering decision

1. **Baseline caching matters.** The gist-token paper's historical LLaMA-7B experiment reports approximately 40% FLOP reduction against no instruction cache, but about 1% wall-time improvement against full instruction caching. Compare against a strong cached baseline, not a deliberately wasteful one.
2. **Output savings can trade away quality.** TALE's reported MathBench-College cell reduces output from 675.78 to 259.85 tokens while accuracy drops from 78% to 70%. Its favorable GSM8K result does not remove that failure slice.
3. **Task awareness changes the bottleneck.** LongLLMLingua's middle-position NaturalQuestions condition improves from 54.1 to 71.2 accuracy without its separate reordering step; the reordered 75.5 result is another pipeline. Attribute gains to the right mechanism instead of claiming all improvement came from shorter strings.

These are publisher results on historical setups, not predictions for TokenMaster or current models. See the paper appendix for additional numbers and caveats, including conflicting TALE aggregate text and oracle-versus-trained RECOMP results.

## 10. GitHub implementations: what to borrow, what not to conflate

The combined review covers **11 GitHub projects**. Context Mode is source-available under a restrictive license, so this is deliberately not labeled “11 permissive open-source dependencies.”

Stars below are approximate readings from the October 4 metadata snapshots; exact values, full SHA pins, release differences, inspected tests, and primary URLs are in the two implementation appendices. Nothing was installed, and upstream test suites were not executed.

| Project / adoption snapshot | Best idea to transfer | Limitation or adoption gate | Suggested role |
|---|---|---|---|
| **RTK**, ~82.4k stars | Tool-specific reducers before verbose command output enters context; bounded recovery hints | Its accounting still uses a byte-length/4 token proxy. Command rewriting must preserve behavior and permissions. Apache-2.0; inspected `develop` differs from release metadata. | Near-term pattern |
| **Context Mode**, ~25.4k | Execute/filter outside the prompt; index raw evidence and retrieve exact slices | Subprocess execution needs a real security boundary; BM25 can miss nonliteral evidence. **ELv2 licensing gate.** | Architecture reference, not blanket code reuse |
| **TOON**, ~25.5k | Factor repeated field names into a compact typed/tabular representation | Data shape matters. Its own mixed-structure total is 1.6% larger than compact JSON; do not benchmark only against pretty JSON. MIT; reference is TypeScript/ESM. | Optional shape-gated experiment |
| **Microsoft LLMLingua**, ~6.7k | Learned keep/drop scoring; LLMLingua-2 offers a lighter auxiliary encoder path | Displayed dollar savings use a hard-coded historical rate. Audit model code/trust, runtime overhead, and exact-field retention. Source head and 0.2.2 package are separate. | Controlled prose experiment |
| **Selective Context**, 426 | Surprisal-based historical comparison baseline | Last observed head change is February 2024; no discovered test suite or license text despite an MIT classifier. | Research baseline, not preferred adoption |
| **lm-sys/RouteLLM**, ~5.6k | Calibrate strong-versus-cheap model selection | MF routing adds an embedding call and the controller scores the last message; training is first-turn-oriented. Last observed head is August 2024. | Borrow/calibrate the mechanism; do not deploy unchanged |
| **mem0**, ~66.6k | Persist/retrieve facts instead of replaying full histories | Extraction, embeddings, storage, updates, and retrieval cost money. `top_k` is not a token limit. Current headline benchmarks refer to managed-platform optimizations. | Memory experiment for repeated workloads |
| **Outlines**, ~15.9k | Prevent invalid structured outputs and unnecessary formatting retries | Grammar/schema correctness is not semantic correctness; provider support differs. | Conditional output/retry optimization |
| **vLLM**, ~93.2k | Prefix reuse and efficient KV/serving management | Needs owned serving infrastructure; no automatic hosted-API billing discount. | Separate self-hosted track |
| **SGLang**, ~36.8k | Radix/prefix reuse and cache-aware serving | Backend, model, configuration, namespace, and traffic shape matter. | Separate self-hosted track |
| **LMCache**, ~12.0k | Reuse KV state beyond immediate GPU residency | Storage/transfer can dominate; cache counters can overlap with locally computed pages. | Add only after measuring an owned serving engine |

### What this means for prioritization

The first product step should not be to add all eleven dependencies. Source patterns suggest a smaller path:

- **Avoid and project first:** existing graph routing plus a few high-value task-specific reducers.
- **Represent exactly where possible:** select compact JSON/table/TOON by measured shape, counting all framing.
- **Use learned compression selectively:** long redundant prose, a persistent audited compressor instance, and a quality gate. The present optional helper constructs a compressor per call and is not enabled by the default public MCP/hook path.
- **Route models only with task-state and overhead accounted for:** copying a 2024 first-turn router into a 2026 tool-using agent is not a validated cost policy.
- **Keep persistent memory minimal and source-backed:** reuse fact provenance and versions; do not equate a memory library's managed benchmark with its OSS package.
- **Do not pursue GPU-cache parity as plugin parity:** reserve serving work for a product/deployment where TokenMaster controls the backend.

The direct source review also found that public `microsoft/TokenCut` could not be verified; the similarly named public computer-vision project is not relevant evidence. It was excluded rather than added as a plausible-sounding token optimizer.

## 11. Ponytail / Headroom companion research

A separate user-requested chat completed source-backed parity planning:

```text
chat_id: 01a10894-ab5f-7752-96d4-50b296687226
exclusive output directory:
C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity
```

It delivered canonical identities, pinned implementation/tests, host compatibility, an actual-capability matrix, licensing/security, implementation-sized gaps, and parity acceptance tests. Its final report records 280 validated pinned line references. It is separate from the broad paper/implementation review above.

Treat parity as **capability plus measured outcome**, not equal advertised reduction. The shared experiment must preserve success criteria and account for instruction/skill overhead, context transforms, cache transitions, retrieval, and verification.

### Source-backed companion conclusions

The companion reports inspect:

- `DietrichGebert/ponytail@c982cd411abb53323c4baa1baa3c2f020b8d0b08` — source metadata 4.10.3.
- `headroomlabs-ai/headroom@1cf496612e781ef8d67ff87ee4f78037492f0bc7` — source metadata 0.39.1/Beta. The former `chopratejas/headroom` URL redirects to this repository.
- The installed Ponytail bundle separately: bundle 2.0.0, upstream lock 4.9.0, primarily skills rather than the full current upstream runtime.

**Recommended combination:**

| Capability | Role in a combined TokenMaster |
|---|---|
| Ponytail-style task discipline | Avoid speculative scope, reuse existing code, perform required verification, and stop when the actual task is satisfied. These are instructions/workflows, not a deterministic guarantee that the model always does less work. |
| TokenMaster graph acquisition | Obtain the needed structural evidence through bounded, current queries rather than repeated exploratory reading. |
| Headroom-style context delivery | Transform eligible representations at a verified transport boundary; preserve provider protocol, cacheable history, and usable recovery. |

Do not assume independent or multiplicative savings. Current Headroom also has optional output-shaping controls and a Claude wrapper that can add Serena, so parts overlap with instruction discipline and structural acquisition.

Two implementation details make older comparisons unreliable: current Headroom's SmartCrusher is **lossless-first, not lossless-only**, and its CacheAligner is detector-only while provider paths replay previously forwarded context. Recreating an old generic “compress + canonicalize” description would not establish current parity.

The companion backlog has **12 bounded implementation slices**:

1. **G01–G04:** repair recovery validation, failed-storage behavior, native host envelopes, and final emitted-budget guards.
2. **G05–G08:** scoped task discipline, task/role-aware structured views, complete/scoped retrieval, and explicit Codex/Windows integration.
3. **G09–G10:** native-usage/quality experiments and graph freshness/completeness.
4. **G11–G12:** request-level cache/budget policy and optional advanced engines/transports only after earlier gates pass.

This matches the main research's conclusion: **the next release should make the current system truthful and dependable before adding stronger learned compression.** First parity does not require every Headroom provider, image, memory, proxy, or ML feature.

Companion artifacts:

- `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\PARITY_REPORT.md`
- `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\GAP_BACKLOG.md`
- `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\BENCHMARK_PROTOCOL.md`

The companion separately exercised selected upstream unit checks/probes. Those are not live-host or model-quality benchmarks, and its own evidence index carries their scope.

## 12. Primary documentation register

All documentation below was consulted during this review. It is live documentation, not a versioned compatibility guarantee for every installed host.

- **D1 — OpenAI prompt caching:** `https://developers.openai.com/api/docs/guides/prompt-caching`
- **D2 — Anthropic prompt caching:** `https://platform.claude.com/docs/en/build-with-claude/prompt-caching`
- **D3 — Claude Code hooks / PostToolUse response replacement:** `https://code.claude.com/docs/en/hooks`
- **D4 — MCP server concepts and model-controlled tools:** `https://modelcontextprotocol.io/docs/learn/server-concepts`
- **D5 — Copilot SDK usage and billing metrics:** `https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing`
- **D6 — Copilot model pricing and billing units:** `https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing`
- **D7 — Anthropic thinking-block preservation:** `https://platform.claude.com/docs/en/about-claude/models/extended-thinking-models`

The companion paper and OSS research appendices supply versioned scholarly and implementation evidence. The separate Ponytail/Headroom parity chat supplies the detailed competitive plan.
