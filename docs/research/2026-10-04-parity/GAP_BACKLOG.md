# Implementation-sized parity backlog

**Research proposal — October 4, 2026. Nothing below has been implemented.**

This is an ordered set of reviewable changes, not a request to reproduce every feature in either competitor. The acceptance criteria deliberately separate behavioral compliance, safe context transformation, host compatibility and measured economics. Upstream evidence and capability limits are in `PARITY_REPORT.md`; the release experiment is in `BENCHMARK_PROTOCOL.md`.

Every existing local touch point below is at TokenMaster commit **`426fc853389ddba4bc6e1dd35a28179a895c064f`**. Exact source snapshots, hashes and pinned upstream file URLs are in `tokenmaster/source-manifest.json`. New paths are explicitly marked **proposed**.

## P0 — trust the result before adding compression

### G01. Repair the benchmark's recovery oracle

**Why first:** `benchmark_one` extracts bare hashes, then applies the placeholder regex to those hashes again, so the recovery branch is skipped. The fresh broken-store probe reports `lossless=True` with **zero retrieve calls**. It also never compares a retrieved payload against the original payload.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\benchmark.py`, lines 73–89 and 120–139.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\tests\test_benchmark_validation.py`.

**Small change:** record minted reference → expected payload pairs; parse references once; verify byte/text equality under a stated encoding contract; distinguish full-input recovery from fragment recovery and semantic task success. Return nonzero when a required recovery check fails. Never treat “nothing checked” as recovery established.

**Acceptance tests**

- Missing original, incorrect original and corrupted original each fail, not merely raise or disappear.
- Literal placeholder examples are excluded without excluding newly minted references.
- Full-root JSON recovery, fragment-only recovery and no-op are separately labeled.
- The existing `BrokenRecovery` probe becomes a failing-validation test with `retrieve_calls > 0`.

**Depends on:** none. **Do not bundle with:** a new tokenizer, proxy or compression algorithm.

### G02. Make recovery-required transforms fail closed

**Why:** JSON elision and code stubs still hide content when the stash fails; the log compressor already demonstrates the safer passthrough behavior. “N lines elided” is not a reversible representation.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\compressors\json_compressor.py`, lines 98–168.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\compressors\code_compressor.py`, lines 301–319.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\compressors\prose_compressor.py`, lines 127–144 and 178–184.
- Existing JSON/code/prose tests in `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\tests\`.

**Small change:** introduce an explicit recovery-required mode at the existing router boundary; retain original content when storage or reference creation fails. Keep intentionally lossy experiments opt-in and visibly labeled. Remove tests and comments that equate a marker with losslessness.

**Acceptance tests**

- Store returns `None`, throws, is read-only or is full: recovery-required input remains unchanged.
- No-CCR operation does not silently delete code bodies or records.
- Optional ML failure never removes content without an available original.
- Missing grammar, malformed input and unsupported type stay passthrough.

**Depends on:** G01 for credible verification.

### G03. Honor native output schemas and validate the real host boundary

**Why:** the hook currently extracts one string and emits a plain-string replacement for every tool. Current Claude Code documentation says mismatched built-in output schemas are ignored. A local hook subprocess returning JSON is not a host integration test.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace_posttooluse.py`, lines 66–83 and 111–160.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace_setup.py`, lines 161–198.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\tests\test_host_envelopes.py`.

**Small change:** preserve the tool envelope; replace only eligible textual leaves and preserve stderr, status, interruption flags, image blocks, IDs and other fields. Use a versioned capability table and bypass unknown shapes. Keep tool output as untrusted data, not higher-priority instructions.

**Acceptance tests**

- Structured Bash `{stdout, stderr, interrupted, isImage}` remains that shape.
- Read, Grep, Glob, Windows PowerShell and MCP content arrays are separately covered using current captured host fixtures.
- Error payloads, mixed text/image content and unsupported versions are passthrough.
- A real, isolated host run proves the provider-bound message contains the accepted transformed result and not the original; no production homes are touched.
- Hook disable/uninstall restores behavior and leaves unrelated hooks/configuration unchanged.

**Depends on:** G02. **Release gate:** no “transparent Claude compression” claim before real-host acceptance is proved.

### G04. Apply the budget guard to the final emitted representation

**Why:** the core router checks size before the MCP and hook footers are appended. Fresh fallback-tokenizer probes show `4 → 2 → 24` estimated tokens for raw/core/MCP result, and `204 → 226` for raw/hook replacement.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\router.py`, lines 140–179.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace_mcp.py`, lines 63–91.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace_posttooluse.py`, lines 132–160.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\tokens.py`, lines 19–50.

**Small change:** compare complete model-facing before/after representations, including references and footers. Move detailed savings telemetry out of every model-visible result. Treat tokenizer fallback as an estimate; do not promise actual provider-token nonexpansion from a heuristic.

**Acceptance tests**

- Tiny JSON, modest whitespace changes, long random hashes, Unicode and structured envelopes never violate the selected measurement contract.
- No footer on bypass; any necessary retrieval instruction is counted.
- Wire-byte/output caps measure the actual serialized payload, not only the inner string.
- Pin tokenizer identity and test representative provider tokenizers when available; billed cost remains a separate measurement.

**Depends on:** G03 for the final envelope.

## P1 — a useful minimum parity release

### G05. Add explicit task/scope/output discipline, not a slogan

**Parity target:** Ponytail's user-facing discipline: solve the actual requirement, reuse existing functionality, avoid speculative infrastructure and stop after sufficient verification. Preserve requests that genuinely require depth, architecture or abstraction.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\agent.template.claude.md`, especially lines 26–69.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\agent.template.copilot.md`, lines 39–82.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\SKILL.md`.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master-review\SKILL.md`.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\evals\behavior\`.

**Small change:** an opt-in scoped mode with a compact task contract: required result, non-goals, evidence needed, stop condition and output budget. Add a bounded review mode for unnecessary complexity. Keep session enable/disable separate from task-local invocation. Deterministic hooks can record state and metadata; they cannot guarantee the model will reason minimally.

**Acceptance tests**

- “Explain only” produces no edits; “one small fix” avoids unrelated refactors.
- “Create a reusable abstraction” is not incorrectly rejected as overengineering.
- Required tests, safety caveats and user-requested detail are retained.
- Stop/off removes only this mode's state; later sessions do not inherit it unexpectedly.
- Blinded reviewers score requirement completion and maintainability, not just fewer lines.

**Depends on:** no compressor feature; benchmark under G09. **Scope limit:** audit/debt/gain commands are separate optional follow-ups, not necessary to claim minimal task-discipline parity.

### G06. Replace blind sampling with contract-aware structured views

**Parity target:** useful structured compression that preserves the task's answer-bearing information, rather than matching a headline reduction ratio.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\router.py`, lines 52–102 and 140–177.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\compressors\json_compressor.py`, lines 85–168.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\compressors\logs_compressor.py`, lines 28–32 and 151–186.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\compressors\prose_compressor.py`, lines 62–75.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\tests\test_task_sensitive_views.py`.

**Small change:** first add bypass rules for exact text, exhaustive queries, aggregates, patches, security decisions and already-small outputs. Then support schema-aware compact views and explicit anomaly/error retention. Remove the unsupported “same shape” assertion for unchecked heterogeneous lists. Preserve code bodies by default for modification/debugging tasks; skeletons are an explicit navigation view.

**Acceptance tests**

- Rare `DENIED` record in the omitted middle remains answerable; heterogeneous types are disclosed.
- `FAILED` test lines, nonzero exits and stderr diagnostics survive.
- Counts, sums, ordering, null/missing distinctions and exact quotes are unchanged or bypassed.
- Markdown code fences and whitespace-sensitive literals are not normalized as ordinary prose.
- Compression under a budget can say “cannot safely meet budget”; it must not force unsafe truncation.

**Depends on:** G02–G04; recovery under G07.

### G07. Make retrieval complete, scoped and bounded

**Parity target:** useful recovery/search over originals, not the weaker claim that an original exists somewhere.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\ccr.py`, lines 54–69, 133–203 and 228–254.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace_mcp.py`, lines 47–56 and 94–114.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\tests\test_recovery_contract.py`.

**Small change:** define root vs fragment references, full length and digest; add offset/limit or cursor paging with a completion flag. Add bounded exact search before introducing semantic search. Scope stores and references to the intended workspace/session, with explicit sharing rather than accidental parent-directory discovery. Separate content identity from display/source metadata.

**Acceptance tests**

- A 200,001-character original reconstructs completely through the public tool.
- Byte/text digest validates every page and full reconstruction.
- Unknown, expired, corrupted and ambiguous references fail explicitly; no partial answer is labeled complete.
- Same policy/content/source produces stable output; metadata does not pretend to be content-only.
- Cross-workspace reference access fails unless explicitly shared.
- GC cannot evict references still needed by an active session; quotas, TTL and cleanup are observable.

**Depends on:** G01–G04.

### G08. Add a real Codex/Windows adapter without weakening existing hosts

**Parity target:** explicit supported host behavior, not “MCP therefore works everywhere.”

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\setup.py`, lines 44–77 and 302–338.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace_setup.py`, lines 49–106 and 137–231.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\SKILL.md`.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\hosts\codex.py`.
- **Proposed:** host contract fixtures under `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\evals\hosts\`.

**Small change:** support Codex's documented MCP configuration and appropriate skill surface, with an explicit mode/capability summary. Do not translate Claude hook fields into Codex and assume equivalence. Evaluate Codex's current feedback-based PostToolUse controls separately before treating them as a compression transport.

**Acceptance tests**

- Claude Code, Codex CLI and Codex desktop can each list/call/retrieve from the expected server in isolated configuration.
- Existing Copilot mode remains functional and labeled model-invoked where appropriate.
- Windows native paths with spaces/Unicode, CRLF, argv quoting, executable lookup, UTF-8 stdio and process cleanup pass.
- Invalid existing JSON/TOML aborts safely rather than being replaced with `{}`.
- Atomic writes, backups, idempotent merges, concurrent updates and uninstall preserve unrelated settings.
- Resolve dependencies from an explicit lock/package; do not re-resolve unpinned `uv --with` dependencies at every launch.

**Depends on:** G03–G04; no live configuration changes until separately authorized.

### G09. Replace token-savings marketing with an end-to-end evidence ledger

**Parity target:** measured-quality parity and honest economics.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\benchmark.py`.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\tokens.py`.
- `C:\Users\shyamsridhar\code\TokenMaster\README.md`, especially the routing, losslessness, host-verification and cumulative-token claims.
- **Proposed:** `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\evals\` with immutable task/run manifests and provider/host adapters.

**Small changes, in order**

1. Add non-sensitive per-transform telemetry: decision, bytes, estimated tokens, latency, retrieval outcome and policy version.
2. Add captured provider usage and normalized cache/input/output accounting.
3. Run the quality-first protocol; publish failures, uncertainty and unsupported cells.

**Acceptance tests**

- All retries, recovery calls, metadata, output tokens and warmup costs are included.
- A shorter prompt that increases cache writes or retrieval can correctly be reported as more expensive.
- Provider counters reconcile with captured responses; estimates and invoices are not conflated.
- A fixture with 15,000 total input, 12,000 provider-reported cache reads and 3,000 provider-reported cache writes normalizes to zero ordinary input; inferred-write counters do not masquerade as those explicit fields.
- Passing quality threshold is required before any cost-saving claim.
- Current “lossless” claims are replaced with precise terms: storage round-trip, view omission, retrieval completeness and task non-inferiority.

**Depends on:** G01 immediately; full promotion after G02–G08. Instrument early, claim late.

### G10. Preserve the graph advantage with freshness and completeness contracts

**Parity target:** protect TokenMaster's differentiator; neither generic behavioral discipline nor generic context compression validates inferred code edges.

**Touch points**

- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\graphify_mcp.py`, lines 76–114, 161–197 and 236–281.
- `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\setup.py`, graph-generation/indexing flow.
- Existing routing templates' freshness and fallback sections.

**Small change:** record index supplier/version and source fingerprint; detect changed source/graph after startup. Expose bounded paging/completeness rather than pretending truncated rows are exhaustive. Retain inferred-edge caveats and source verification.

**Acceptance tests**

- Edit source or replace index after the first query: stale state is detected.
- High-fanout callers/impact results can be fully enumerated through bounded pages.
- Name collisions and dynamic dispatch do not produce false “complete” answers.
- Graph-build cost is included in cold-start and amortization experiments.

**Depends on:** none for source safety; evaluated under G09.

## P2 — expand only after the minimum release qualifies

### G11. Conversation-level budgets and cache-aware transform policy

**Touch points:** the existing `brainspace/router.py` remains the content dispatcher; **proposed** request-level integration under `C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\skills\token-master\brainspace\request_policy.py`, plus host/provider contract tests under `token-master-plugin/evals/`.

Protect system/developer instructions, tool schemas, tool-call pairs, newest results, exact-answer blocks and stable cached prefixes. Choose transformations using task, model limits, recovery availability and expected whole-task cost. Add history reduction only as an explicit separate policy.

**Acceptance:** synthetic multi-turn prefix tests; correct accounting when cache reuse falls; late-answer recovery; no protocol corruption; deterministic policy at the same version; fail-open passthrough when no safe transformation fits. Compare against the pinned current Headroom behavior rather than an old README description.

**Depends on:** G03–G09. **Do not start with:** default aggressive history pruning.

### G12. Optional advanced engines and transports

Treat richer semantic compression, model-backed pruning, provider proxies, streaming interception, multimodal transforms, cross-process caches and hosted services as **separately scoped** work. They bring model assets, latency, auth, privacy, failure and maintenance obligations absent from a small local plugin.

Before selecting or embedding an upstream component, make a dependency-specific decision covering exact version, license notices/model licenses, transitive dependencies, Windows availability, resource footprint, auth passthrough and maintenance. Preserve a deterministic dependency-light fallback.

**Acceptance:** measured task-quality gain on a held-out stratum, complete request/response/stream/tool-call tests, opt-in disclosure of any network/model download, no secret-bearing telemetry, bounded resource usage and a clean disable path.

**Depends on:** G09's measured need. **Not required for initial parity:** copying every UI, dashboard, deployment integration or compression modality.

## Suggested release boundaries

- **Evidence repair release:** G01–G04 plus corrected claims and regression tests. This is correctness work, not competitor parity.
- **Minimum useful parity release:** G05–G09, with G10 protecting graph correctness; qualify named Claude/Codex/Windows workloads through the benchmark protocol.
- **Expanded transport/context parity:** only the G11/G12 capabilities demanded by measured workloads, each with an independent acceptance gate.

Do not declare parity merely because the same commands exist, a store retains an original, or a synthetic output shrinks. Declare the supported capability set and the measured quality/cost envelope.
