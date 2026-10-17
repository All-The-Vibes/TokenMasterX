# TokenMaster parity benchmark protocol

**Plan, not an executed provider benchmark. October 4, 2026.** No model calls, services, dependency installations, or production configuration changes were made for this research. The only fresh measurements are the offline TokenMaster checks described in `PARITY_REPORT.md`.

## 1. The claim this protocol could establish

For explicitly named host versions, model versions, repositories, task strata, and cache conditions, the candidate completes tasks with non-inferior correctness and safety while improving **observed cost per successful task** and/or end-to-end latency. It does **not** establish universal token savings, semantic losslessness, parity on every upstream feature, or lower subscription fees.

Treat these as three separate hypotheses:

1. **Behavioral discipline:** reduce unnecessary scope, code, narration, and tool calls without omitting required work.
2. **Information acquisition:** answer suitable structural questions with a current, bounded graph rather than repeated exploration.
3. **Context handling:** change what reaches the model without breaking tool protocols, exact-answer tasks, cache reuse, or later recovery.

These interventions can interact. Do not multiply independently reported savings percentages.

## 2. Freeze the experiment before running it

Create a run manifest containing:

- Task ID, original human request, acceptance oracle, difficulty stratum, repository URL and full commit SHA, relevant fixture hashes, and task license.
- Tested implementation SHA and clean/dirty patch hash. The starting research baselines are TokenMaster `426fc853389ddba4bc6e1dd35a28179a895c064f`, Ponytail `c982cd411abb53323c4baa1baa3c2f020b8d0b08`, and Headroom `1cf496612e781ef8d67ff87ee4f78037492f0bc7`.
- Exact host executable/version, OS and architecture, Python/Node/runtime versions, dependency lock hashes, provider endpoint class, model/version, reasoning setting, temperature/seed where available, tool schema hash, system/developer instruction hash, and request limits.
- Product configuration, compression thresholds, transform ordering, retrieval policy, graph supplier/version, index hash and source freshness, pruning policy, and cache configuration.
- Price-table URL, retrieval timestamp, immutable saved price sheet/hash, currency, negotiated discounts if actually known, and any separately priced tools/storage.
- Separate cold-start, warm-process, cold-provider-cache, and warm-provider-cache conditions.
- An agreed maximum currency spend, task-attempt budget, wall-time budget, and stop conditions. This research does not authorize those future runs.

Never label a moving model alias, unpinned package, default threshold that changed mid-run, or unknown cache state as controlled.

## 3. Two comparisons, not one confounded tournament

### A. End-user product comparison

Use the actual supported installation/transport for each product. Include each product's real skill, tool-schema, hook, and retrieval overhead in its bill.

| Arm | Purpose |
|---|---|
| Stock host | Primary baseline, no new efficiency product |
| Ponytail upstream | Behavioral intervention at the pinned upstream version |
| Headroom upstream default | Actual default behavior, not a hand-picked maximum-compression setting |
| Current TokenMaster | Graph and Brainspace configuration as actually supported by the host |
| Ponytail + Headroom | Tests the complementary-product hypothesis |
| Candidate TokenMaster | The proposed integrated policy/routing/compression release |

Report unsupported cells as **unsupported**, not zero savings. For example, do not silently replace a proxy integration with a model-invoked compression tool and call them the same arm.

The installed Engineering Suite Ponytail 2.0.0 is a skills-only snapshot derived from upstream 4.9.0, not the pinned 4.10.3 runtime. If the user's installed experience is a target, add it as a separately named arm rather than substituting it for upstream. Headroom's Claude wrapper also has quiet-output controls and default Serena integration; those source-acquisition changes must be recorded as part of its product arm and controlled separately in the mechanism ablation. The source evidence is in the two competitor reports.

### B. Mechanism ablation

After adapters are validated, use a controlled `2 × 2 × 3` design:

- Routing policy: off / graph-first.
- Scope-output discipline: off / on.
- Compression: off / TokenMaster candidate / pinned Headroom.

Hold the visible tool inventory, schemas, host, and task contract constant for this ablation. Keep the end-user product comparison separate because making graph tools available in every arm changes the baseline. Add retrieval-disabled or maximum-compression conditions **only as stress tests**, never as the shipping default comparison.

If a full factorial is too expensive, predeclare the necessary pairwise contrasts and run a staged subset. Do not retrospectively choose only the favorable combinations.

Explicitly audit baseline contamination: active plugin directories, inherited environment, user/repository instructions, auto-memory, MCP servers and lifecycle hooks. Ponytail's publisher withdrew an earlier comparison after its activation leaked into the baseline; that is a concrete reason to verify isolation rather than assume a “baseline” label is sufficient. See the pinned June 18 result and current agentic harness cited in `ponytail/REPORT.md`.

## 4. Workload: evaluate what each mechanism can damage

Use held-out tasks across multiple repositories and languages. A pilot can start with 24 paired tasks, two repetitions and six product arms: **288 task executions for one host/model/cache condition**. That is a planning count, not a claim of sufficient statistical power. Determine the full sample size from pilot variance and discordant outcomes; repeated seeds are not independent new tasks.

| Stratum | Required cases | Independent success oracle |
|---|---|---|
| Structural navigation | Callers, callees, inheritance/traits, two-to-five-hop impact, duplicate names, missing/dynamic edges, deliberately stale graph | Curated source evidence plus an independently built oracle; not the same inferred graph being evaluated |
| Code changes | Small bug fix, API change, justified abstraction, task where no code change is needed, tests that must be added | Hidden tests, build/typecheck, scoped diff review and required-work checklist |
| Debug/build/test logs | Rare failure in middle, `FAILED` without `ERROR`, nonzero exit with stderr, warning-as-signal, repeated success noise | Root cause and exact diagnostic/exit status; passing regression test where applicable |
| JSON/tabular output | Rare middle record, heterogeneous arrays, exhaustive enumeration, count/sum/min/max, null vs missing, ordered list, duplicate key input | Exact computation against original data; order and type checks |
| Long multi-turn use | Late query about earlier omitted detail, interrupted/retried tool, resumed session, cache-prefix mutation, changing user goal | Future-answer correctness, reference survival and complete replay/continuation |
| Exact text and negative controls | Quote/hash/patch/line-number tasks, fenced code, whitespace-sensitive literals, small outputs, already concise answers | Byte/field equality where required; no forced transformation |

Include common Python/Rust cases and JavaScript/TypeScript cases; do not generalize the current Python/Rust skeletonizer to all code. Add Unicode paths and text, CRLF/LF, Windows paths with spaces, multibyte input, malformed JSON, large outputs, image/binary content, and multiple tool-result blocks.

### Offline safety corpus before provider spend

At minimum test:

- Store unavailable, disk full, corrupted blob, ambiguous short hash, expired/missing reference, concurrent store access, wrong namespace, and retrieval beyond 200,000 characters.
- Compressor exception, unsupported grammar, partial parse, tokenizer unavailable, and a result made larger by its footer/envelope.
- Mixed structured/text/image MCP blocks, `isError`, stdout/stderr separation, interrupted commands, multiple tool calls, tool-call/result ID pairing, and bounded streaming completion.
- Malicious instructions embedded in tool output, placeholder-shaped literals, secrets, environment-key redaction, source/path metadata containing delimiters, and bypass attempts.
- Determinism under the same content **and policy/version/source metadata**, plus historical-prefix immutability across turns.
- Graph changes after first query; explicit refresh/invalidation and stale-result disclosure.

A safety fixture that requires exact retention must pass unchanged or recover completely through a defined protocol. A marker that merely admits data was omitted is not recovery.

## 5. Trace the actual boundary

Record a common, provider-neutral event schema:

```text
run_id, task_id, arm, attempt_id, turn_id, request_id, tool_call_id
host_version, model_version, source_sha, policy_version, fixture_hash
request_started_at, first_token_at, response_completed_at, task_completed_at
tool_started_at, tool_completed_at, transform_started_at, transform_completed_at
input_estimate_before, input_estimate_after, estimation_method
provider_uncached_input, provider_cache_read, provider_cache_write_by_ttl
provider_output_total, provider_reasoning_subcount, provider_usage_raw
request_bytes_before, request_bytes_after, prefix_fingerprint, protected_block_hashes
transform_name, decision_reason, source_ref, retrieval_requested, retrieval_succeeded
http_status, retry_reason, context_limit_event, cancellation, final_task_outcome
```

Capture what the **provider actually receives**, not just a compressor's return value. Include skill instructions, tool definitions, result envelopes, footers, retrieval calls, summarizer/model calls, retries, failed attempts and final answers.

Use an opt-in encrypted/redacted trace sink. The default performance ledger should contain counts, hashes and reason codes, not raw source, tool output, prompts, secrets or credentials. Preserve a controlled fixture's exact bytes separately when needed for reproducibility.

For Claude Code, verify built-in output schemas and the final outbound request. Emitting JSON from a hook subprocess does not prove the host accepted the rewrite. Current official documentation requires `updatedToolOutput` to match the tool's output shape; malformed built-in replacements are ignored. [O1]

For Codex, validate stdio MCP registration and tool invocation independently of transparent result rewriting. Current documentation supports MCP and PostToolUse hooks, but says `updatedMCPToolOutput` is not supported; do not use additional-context injection as evidence that original context was removed. [O2] [O3]

## 6. Cost accounting

Store raw provider usage and normalize it in provider-specific adapters. A proposed normalized per-attempt formula is:

```text
cost = uncached_input * rate_uncached
     + cache_read * rate_cache_read
     + sum(cache_write[class] * rate_write[class])
     + output_total * rate_output
     + separately_priced_tool_or_storage_charges
```

Apply the appropriate unit divisor from the saved price sheet. Do not assume every provider has every category.

- **OpenAI:** current documentation distinguishes `input_tokens`, `input_tokens_details.cached_tokens`, and, for GPT-5.6+ in the documented interface, `input_tokens_details.cache_write_tokens`. Its example computes ordinary input as total input minus both cache-read and cache-write tokens. Consume explicit provider fields when present; do not substitute an inferred write count or charge it twice. Keep absent/unknown fields distinct from measured zero and use the exact model/interface's pricing. Do not add reasoning tokens again when already included in billed output. [O4]
- **Anthropic:** uncached input, cache-read input and cache-creation input are distinct usage categories; preserve TTL-specific cache-creation detail where returned. Cache writes and cache reads do not have the same price. [O5]
- An estimated tokenizer count is not a provider usage counter. A provider usage counter plus a public price sheet is an **estimated charge**, not a reconciled invoice. Label each evidence level.
- For subscription or premium-request products, report quota/request effects separately. Lower token usage is not proof that the user's invoice fell.
- Attribute warmup, retries, compression-model calls, retrieval, index construction, and local compute/storage where relevant. Show cold-start cost and amortized steady-state cost separately.

Report both:

1. Cost per attempted task, with all failures included.
2. Total experiment cost divided by successful tasks, with failed attempts' costs retained in the numerator.

Do not compare successful-only token traces while discarding expensive failures.

## 7. Cache and latency experiments

Run paired cold-cache and warm-cache cohorts. Keep tool schemas, static instructions, model, routing key, prefix order, account/project partitioning and TTL treatment controlled. Count priming cost. Isolate sessions so one arm cannot warm another arm's cache accidentally.

Capture:

- Input/cache-read/cache-write usage on every request.
- Earliest changed serialized block and protected-prefix hash.
- Time to first token, full response time, whole-task completion time.
- Cold startup, warm transform latency, subprocess startup, store latency, retrieval latency, retry delay and provider latency separately.
- p50/p95 and paired distributions, not just averages.

Exact-prefix caching makes position and stability important; changing an old block can erase useful reuse. A deterministic content hash alone does not establish that the full serialized request stayed stable or that compression was cheaper. [O4] [O5]

## 8. Quality adjudication and statistics

Predeclare primary endpoints and acceptance margins. Suggested release gates, to be agreed before execution:

- **Protocol/security invariants:** zero violations in the defined fixture suite; no uncaught cross-session disclosure; no hidden required safety/error field.
- **Exactness:** 100% pass on tasks whose contract requires exact bytes, exhaustive records, executable patches, or complete retrieval. Bypass is an acceptable outcome.
- **Task success:** candidate minus comparator success rate has a one-sided 95% confidence bound above a predeclared non-inferiority margin (proposed margin: −2 percentage points). No critical-severity new failure, regardless of aggregate score.
- **Economics:** after passing quality gates, demonstrate a predeclared useful reduction in cost/successful task (proposed target: ≥10%), with a paired confidence interval; otherwise call it a token/latency result, not billed-cost parity.
- **Latency:** no material p95 regression beyond a predeclared tolerance (proposed: 10%) unless the product explicitly trades latency for a demonstrated quality/cost improvement.

These are **proposed product thresholds**, not externally established standards and not results from this research.

Use paired tasks and cluster uncertainty by task/repository. Bootstrap ratios carefully; use an appropriate paired binary analysis for success. Plan multiplicity handling or restrict primary contrasts. Report small-stratum uncertainty, effect distributions, failures and denominator changes. A non-significant difference is not proof of non-inferiority.

Grade with hidden tests and independent evidence first. Use blinded human review for scope and maintainability, with a rubric that rewards completing requirements rather than merely deleting lines. A model judge can be supplemental; it must not be the sole correctness oracle or know which arm produced an answer.

## 9. Promotion sequence and deliverables

1. **Correct the measurement oracle and pass offline invariants.**
2. **Validate host contracts** against current real host versions in isolated, disposable homes; snapshot original configuration and prove cleanup.
3. **Run the budgeted pilot** to find failure modes and estimate variance.
4. Freeze transforms, defaults, tasks and scoring; keep the final held-out set untouched during tuning.
5. Run the powered comparison; publish raw redacted usage, exact commands, dependency locks, task outcomes and uncertainty.
6. Ship conservative defaults first. Consider adaptive/ML pruning only after a separate non-inferiority result.

Proposed tracked home: `token-master-plugin/evals/` with task manifests, host/provider adapters, usage normalization, statistical analysis, fixtures and redacted example results. Keep expensive/raw sensitive artifacts outside the distributed plugin and publish their hashes and redaction policy.

Required artifacts: `run-manifest.json`, `events.jsonl`, `provider-usage.jsonl`, `task-outcomes.jsonl`, `safety-results.xml`, `summary.json`, `failure-cases.md`, and a report that distinguishes **observed**, **publisher-reported**, **estimated**, and **not measured**.

## Official-source references

Fetched October 4, 2026. Saved copies and SHA-256 hashes are in `official/manifest.json`.

- **O1:** [Claude Code hooks — PostToolUse decision control](https://code.claude.com/docs/en/hooks#posttooluse-decision-control); local snapshot `official/claude-code-hooks.md`, lines 2062–2089.
- **O2:** [Codex MCP](https://developers.openai.com/codex/mcp/), redirecting to [MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli); local snapshot `official/codex-mcp.md`.
- **O3:** [Codex hooks](https://learn.chatgpt.com/docs/hooks); local snapshot `official/codex-hooks.md`, especially lines 923–941.
- **O4:** [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching); local snapshot `official/openai-prompt-caching.md`, especially lines 557–607 for explicit cache-read/write accounting.
- **O5:** [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching); local snapshot `official/anthropic-prompt-caching.md`.

[O1]: https://code.claude.com/docs/en/hooks#posttooluse-decision-control
[O2]: https://developers.openai.com/codex/mcp/
[O3]: https://learn.chatgpt.com/docs/hooks
[O4]: https://developers.openai.com/api/docs/guides/prompt-caching
[O5]: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
