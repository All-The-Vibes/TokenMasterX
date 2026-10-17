# TokenMaster × Ponytail × Headroom: practical parity, with evidence

**As of October 4, 2026. Source-pinned research and implementation plan—not a shipped change or a live model benchmark.**

## Executive decision

**TokenMaster should combine three capabilities, not imitate one competitor wholesale:**

1. **Ponytail-style task discipline:** do the required work, reuse what exists, avoid speculative scope, keep unsolicited output short, verify, then stop.
2. **TokenMaster's structural acquisition advantage:** use a current, bounded code graph when it is the appropriate evidence source.
3. **Headroom-style context engineering:** transform eligible content at a real transport boundary, preserve task-critical information and cache stability, and provide usable recovery.

That is a product direction, **not a proven multiplicative savings formula**. Ponytail is primarily instruction delivery and mode state, while Headroom is primarily a content/request pipeline. They are complementary, but not completely orthogonal: current Headroom also has optional output shaping, quiet-output controls and default Serena integration in its Claude wrapper. Graph routing, fewer tool calls and smaller tool results can affect the same traffic. Measure the combination. [P01] [P02] [P03] [P04] [H02] [H20] [H21] [H35] [H36] [T01] [T02]

**The first release should repair trust, not add a stronger compressor.** Fresh isolated checks found that TokenMaster's benchmark can label recovery “lossless” without calling retrieval, JSON/code fallback paths can omit data when storage fails, wrapper footers bypass the core size guard, and public retrieval truncates at its default 200,000-character cap. The hook also emits a string for structured Bash results; current Claude documentation says such mismatched built-in replacements are ignored. These are narrower, source-backed findings—not claims of observed host data loss or billed-cost regression. See §4. [T03] [T05] [T09] [T10] [T11] [T12] [T13] [O1]

**Meaningful parity is achievable only as a named capability and workload envelope.** The initial target should be safe task discipline + graph acquisition + conservative tool-output handling + complete retrieval + verified Claude/Codex/Windows integration + a quality-first cost/latency experiment. Recreating Headroom's entire proxy, provider matrix, semantic model, image path, memory machinery and deployment surface is a different project. No current evidence here establishes universal answer equivalence or lower invoices for any of the three products.

### Deliverables

- **This synthesis:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\PARITY_REPORT.md`
- **12 prioritized implementation slices with exact local touch points and acceptance tests:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\GAP_BACKLOG.md`
- **End-to-end quality/latency/billed-cost protocol:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\BENCHMARK_PROTOCOL.md`
- **Deep upstream dossiers:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\ponytail\REPORT.md` and `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\headroom\REPORT.md`
- **Evidence guide:** `C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\EVIDENCE_INDEX.md`

## 1. Provenance and evidence levels

### Canonical identities, not name matching

| Object | Verified identity / pin | Version and date boundary |
|---|---|---|
| TokenMaster | `All-The-Vibes/TokenMasterX` at **`426fc853389ddba4bc6e1dd35a28179a895c064f`**, branch `master` | Configured remote verified; commit August 8, 2026, 06:23:53 UTC. Plugin manifest still says 0.1.0. [T20] |
| Ponytail upstream | `DietrichGebert/ponytail` at **`c982cd411abb53323c4baa1baa3c2f020b8d0b08`** | Main tip fetched October 4; commit October 3, 2026, 05:12:55 UTC; metadata 4.10.3. [P16] |
| Headroom upstream | `headroomlabs-ai/headroom` at **`1cf496612e781ef8d67ff87ee4f78037492f0bc7`** | Main tip fetched October 4; commit October 3, 2026, 21:14:17 UTC; source metadata 0.39.1/Beta, Python ≥3.10. A development-tree version is not proof every change is in a published wheel. [H01] |
| Former Headroom URL | `chopratejas/headroom` | GitHub API redirects to repository ID `1129940957`, whose canonical `full_name` is `headroomlabs-ai/headroom`. Not a separate competing implementation. |
| Installed Ponytail bundle | `C:\Users\shyamsridhar\.codex\plugins\cache\openai-curated-remote\engineering-suite-ponytail\2.0.0` | Bundle 2.0.0, skills-only; provenance lock points to Ponytail **4.9.0**, **`356918eba965ee1eac64bd3a7f0dd02108350de5`**, September 7, 2026. Not upstream-current runtime parity. [I1] |

Raw API identity/redirect evidence is saved in `repository-identities.json`; exact commit metadata is saved with each upstream dossier. These are observations at retrieval time, not promises that moving branches cannot advance.

**Integrity:** 31 TokenMaster snapshots match their pinned Git bytes; working-tree text matched after newline normalization. Ponytail's 169 archive files were verified against the pinned Git tree. The installed bundle's 29 file hashes were recorded and its files left unchanged. Headroom's source archive hash, 2,542-file inventory count and 164 validated cited line ranges are recorded in its manifest. No source archive was installed or used to launch a service.

### Reading the claims

- **Observed/source:** an inspected implementation, configuration, test assertion or fresh offline result.
- **Publisher claim:** a reported benchmark or guarantee that this work did not reproduce with models/providers.
- **Inference:** a conclusion from those observations, explicitly qualified.
- **Proposal:** a target or acceptance test for future implementation—not an existing feature.

An inspected upstream test is not automatically a passed test. A passed unit test is not automatically host integration or answer-quality evidence.

## 2. Capability matrix

This matrix compares the **pinned upstreams** against actual TokenMaster code. The installed Ponytail bundle is treated separately in §3.

| Capability | Ponytail upstream | Headroom current upstream | TokenMaster today / priority |
|---|---|---|---|
| Task/scope/output discipline | Explicit reuse/simplicity ladder, lite/full/ultra, terse unsolicited explanation, required-work safety floor; model guidance, not deterministic enforcement. [P01] | Optional request-side verbosity/effort shaping and quiet-output controls, not the same anti-overengineering workflow. [H21] [H35] [H36] | Structural routing instructions only; no comparable general task-discipline mode. **G05**. [T01] |
| Session mode lifecycle | Real Node hooks/state; same-repo sharing and compact/resume reset caveats. [P02] [P03] [P04] | Configuration/request policy rather than a Ponytail-style persona contract. [H06] [H09] | Agent installation, not a generic scoped-mode state machine. **G05/G08**. [T14] |
| Review/audit/debt/gain | Prompt-defined workflows; gain is a historical static card, not local savings telemetry. [P05] [P06] [P07] [P08] | Different product surface: transform decisions, usage and proxy state. [H13] [H14] [H15] | No equivalent review/audit/debt workflows. Core review first; audit/debt optional, gain should be an honest ledger. **G05/G09**. |
| Structural code acquisition | Guidance to inspect callers/reuse, no code graph in the inspected runtime. [P01] [P02] [P03] | Claude wrapper enables separate Serena integration by default; do not count that as semantic-compressor quality. [H20] | Six graph tools, bounded results, inferred-edge caveats and precision fallback guidance. Distinct strength, but freshness/completeness need protection. **G10**. [T01] [T02] |
| JSON/structured data | No transform in the inspected instruction runtime. | Rust SmartCrusher: lossless-first compact representation, statistical selection, anomalies/errors/diversity, optional row dropping and CCR sentinels. Not universally schema-preserving. [H03] [H04] [H37] | Fixed head/tail sampling and long-string elision; a rare middle record can disappear. **G02/G06**. [T03] |
| Logs/search/config/diffs | No transform in the inspected runtime. | Multiple format-specific routes, reversible folds and selected lossy paths; query-conditioned reduction. See detailed dossier. [H38] [H47] [H48] [H49] [H50] | Logs: repetition + severity regex + full-log stash; no equivalent dedicated search/config/diff pipeline. **G06**, later **G11**. [T06] |
| Code handling | Simplification instructions concern generated/edited code, not input AST compression. [P01] | AST compressor exists but is off by default in ContentRouter; separate file-read/edit-anchor protections. [H06] [H07] [H08] | Python/Rust skeletonization; can remove bodies even when a task needs them. Unsupported grammars normally no-op. **G02/G06**. [T04] [T05] |
| Prose/semantic compression | Changes behavior/output, not input token pruning. | Kompress/ModernBERT importance scoring with must-keep and line/table safeguards; still lossy heuristics. [H05] | Whitespace normalization; optional LLMLingua path off by default. **Not a first-release ML requirement.** [T07] |
| Images | No image transform in inspected runtime. | Separate image/OCR/detail/resizing route; not covered by text-retention evidence. [H34] | None. **Explicit non-goal for minimum parity.** |
| Content recovery | MCP serves instructions, not original-content retrieval. [P10] | Persistent/global store, expiry and bounded continuation loops; availability depends on entry point and transport. [H16] [H17] [H18] | SQLite full hashes/short references, some fragment storage; public retrieve truncates without paging. **G07**. [T08] [T09] |
| Role/task-aware protection | Instructional completeness floor. [P01] | User/error/code/read-lifecycle guards with important exceptions and entry-point-specific defaults. [H06] [H07] [H08] [H09] [H32] | Router mostly sees content/hint, not task, role, request budget or edit intent. **G06/G11**. [T11] |
| Cache stability | No provider-prefix cache machinery in inspected hooks. | Detector-only CacheAligner plus stateful replay of the previously forwarded prefix, provider-dependent. [H10] [H11] [H12] | Content-addressed references and append-boundary intent; no provider-aware prefix replay or whole-request cache accounting. **G09/G11**. [T08] [T10] |
| Token/cost observability | Historical benchmark instruments, no runtime local-savings gain calculation. [P05] [P11] [P12] [P13] | Local/provider accounting and counterfactual valuations; current nested cache-write field not consumed on inspected paths. Not paired invoice proof. [H13] [H14] [H15] [H51] [H52] | `cl100k_base` or chars/4 estimates and projected cumulative savings; no billed-usage ledger. **G01/G09**. [T12] [T13] [T17] [T18] |
| Claude Code integration | Native lifecycle hooks/skills. [P02] | Proxy/wrapper route, not just a PostToolUse hook. [H20] [H21] | Hook + MCP implemented; built-in output-shape mismatch undermines current transparency claim. **G03**. [T10] [O1] |
| Codex integration | Dedicated upstream plugin manifest, hooks and skills; trust/host execution still required. [P09] | Managed provider configuration; Responses HTTP/WebSocket paths. [H19] [H39] | No Codex host branch in installers; generic MCP is a potential route, not verified shipped support. **G08**. [T14] [T15] [T16] [O2] |
| MCP | One prompt + instruction tool over stdio; not always-on behavior by itself. [P10] | Explicit compression/retrieval/stats; stdio and separate HTTP server. [H18] [H40] | Three Brainspace tools plus six graph tools; a model-invoked compress call does not intercept other tools or erase earlier transcript. **G03/G08**. [T02] [T09] |
| Windows evidence | Windows-oriented hook tests, path/config handling; full real-host matrix not run here. [P17] | Native-wheel and limited newline CI; some Unix locking/permission safeguards absent. [H24] [H33] | Python offline probes worked; optional grammar/MCP dependencies absent in this runtime. **G08**. |
| Proven end-to-end quality/cost parity | Not established here. | Not established here. | Not established here. **G09 is a release gate, not a marketing afterthought.** |

**MCP is not a blanket compression transport.** If a model copies a blob it has already seen into `brainspace_compress`, that tool call does not remove the earlier blob from history. Its arguments, result, footer and possible retrieval add work. Savings require a suitable acquisition or interception boundary, not merely registering a tool. TokenMaster's own MCP module acknowledges this distinction. [T09]

## 3. What the competitor investigations change

### Ponytail: emulate useful discipline, not “deterministic simplicity”

Its meaningful runtime is instruction construction, lifecycle injection and mode state. The six skill workflows are substantive specifications, but there is no production analyzer that mechanically enforces minimal scope, rejects every unnecessary dependency, executes every requested check, or caps every output. Review/audit/debt findings remain model judgments. [P01] [P02] [P03] [P04] [P05] [P06] [P07] [P08]

The fresh state probe confirmed that activation restores the configured default on compact/resume: manual ultra can become full, and off can reactivate. Same-repository sessions share state. A TokenMaster task mode should define its own explicit session identity and off/resume contract instead of copying this behavior uncritically. [P02] [P03] [P04]; `ponytail/verification/runtime-state-probe.stdout.txt`.

**Installed snapshot is a different target.** All six installed Ponytail skill bodies match locked 4.9.0 after frontmatter removal and newline normalization. Four bodies differ from 4.10.3:

- Review lacks the current reuse-finding tag.
- Audit lacks current reuse/deletion-reference guidance.
- Debt lacks executable grep exclusions and block-comment recognition.
- Help retains older Codex invocation forms.

Core Ponytail and gain bodies match the current pin. Whole-file bytes differ because the bundle changes frontmatter, including invocation metadata. The 29-file bundle adds an entry router and a separately sourced code-simplification skill, but ships **no upstream hooks, MCP package or benchmark runtime**. Installed help therefore describes some absent runtime features. Cache presence does not prove active loading. [I1]; `ponytail/HASHES.md`, `ponytail/skill-parity.json`, `ponytail/skill-parity.diff`.

### Headroom: the current source is materially different from older summaries

| Change/correction | Why it affects parity |
|---|---|
| **Current SmartCrusher is Rust-backed, lossless-first, not lossless-only.** Arrays can become compact strings; lossy fallback can drop rows and add sentinels. | Copying TokenMaster's first/tail sampler does not reach this capability. Conversely, copying its default does not establish original-schema or original-byte preservation. [H03] [H04] [H37] |
| **Kompress preserves more structural cues, including October 1 line/table fixes.** It still predicts what words to retain. | Default word pruning needs task-quality evaluation, not a storage round-trip argument. Current record-bearing JSON routing and edit-anchor guards matter. [H05] [H06] [H07] [H08]; `headroom/history-evidence.md`. |
| **CacheAligner has been detector-only since the May 2 change.** Current provider handlers replay the bytes actually forwarded earlier; Gemini received that repair October 3. | “Canonicalize volatile dates” and “skip recompressing old messages” are not accurate substitutes for today's mechanism. [H10] [H11] [H12] |
| **Advertised `max_lossy_ratio` fields are explicitly unconsumed.** Library system-message compression and recent-code protection differ from broad safe-default descriptions. | Configuration fields are not enforced behavior. TokenMaster should make task/role guards executable and test them. [H07] [H08] [H09] |
| **October 2 accounting fixes distinguish provider usage and inferred cache writes.** Counterfactual savings still are not a billed baseline. | Learn the accounting separation, then measure all provider requests independently. The dossier flags a Responses-HTTP CCR continuation-accounting concern as source-derived, not runtime-confirmed. [H13] [H14] [H15]; `headroom/REPORT.md`, accounting section. |
| **October 3 tip handles proxy-injected Anthropic memory tools server-side during streaming.** Other endpoints have different retrieval/streaming tradeoffs. | Streaming, tool ownership and continuation billing must be tested per endpoint. A boolean “supports streaming” is insufficient. [H22] [H23] |
| **Privacy controls differ:** licensed reporting became opt-in, but beacon upload is separately default-on; stateless mode still permits logs. | Do not equate local ML or a local CCR store with no egress/no persistence. [H25] [H26] [H41] |

**Current-provider compatibility matters even at a fresh source pin.** The October 4 OpenAI guide exposes `usage.input_tokens_details.cache_write_tokens` for the documented GPT-5.6+ interface and subtracts it, along with cached reads, from ordinary input. The inspected Headroom Responses HTTP/WS paths do not consume that nested field distinctly; they derive writes from `input − cached`. Other explicit creation-field dialects are supported, and billing treatment differs across transports, so this is **not** a generic undercount or numerical invoice claim. TokenMaster's future ledger should implement and fixture-test the current provider contract rather than copying those assumptions. The supplemental Headroom section has the full branch-by-branch evidence. [H51] [H52] [O4]

Other current capabilities include tool-schema compaction, first-party Anthropic tool-search deferral, response caching and image handling. Some are optional or endpoint-specific. The class called `SemanticCache` is an exact content-hash/LRU/TTL cache in the inspected implementation, not an embedding-similarity cache. These details are documented with full pinned references in the Headroom dossier; they are not all necessary for TokenMaster's first parity release. [H34] [H35] [H36] [H42]

### Are they complementary?

**Inference: predominantly yes, subject to interaction tests.**

- Ponytail can avoid generating unnecessary implementation, narration and tool work.
- TokenMaster can change which information is acquired for structural questions.
- Headroom can change the representation of eligible information sent to the model.

But smaller scope can eliminate the tool output a compressor would have saved, graph tools already return bounded output, and Headroom's wrapper/output controls overlap both. Multiple simultaneous instruction injectors can also create conflicting preferences. Use one coherent task policy, then deliberately controlled acquisition and context layers. Never assume independent savings add or multiply. The proposed factorial ablation in `BENCHMARK_PROTOCOL.md` tests those interactions.

## 4. Fresh TokenMaster evidence: the gates before parity

All probes ran against the pinned source snapshot without dependency installation, model calls or services. The MCP decorator was shimmed solely to exercise the actual wrapper functions; hook probes invoked the actual hook script as a subprocess. Neither proves transport or real-host acceptance. Counts below use the explicitly selected shipped chars/4 fallback, not provider tokenizers.

| Finding | Fresh evidence and precise scope | Source / backlog |
|---|---|---|
| **Recovery benchmark is a false-positive oracle** | A stash emits a valid reference, retrieval would always return `None`, yet `benchmark_one` reports `lossless=True` and calls retrieve **zero times**. The second regex is applied to an already extracted bare hash. Even repairing it would only check non-`None`, not equality. | [T13], **G01** |
| **JSON stash failure still hides records** | A middle `DENIED` record with a unique extra key disappears and no recoverable reference remains when stash returns `None`. Original files are not destroyed; information is unavailable through the emitted view/CCR path. | [T03], **G02** |
| **Code helper fallback is not lossless** | `_make_stub` omits a body when stash fails and emits a line-count marker. This is a helper/source finding; full AST behavior could not run without tree-sitter. | [T05], **G02** |
| **Displayed outliers are not analyzed** | With working CCR, the rare JSON record is hidden but retrievable. The output still asserts “same shape” although that record has a different key set. A log containing `FAILED test_security_boundary` also hides that line because no matched severity/neighbor protects it; the complete log remains retrievable. No model mistake was measured. | [T03] [T06], **G06** |
| **Core size guard does not cover wrappers** | Small JSON: raw/core/MCP result estimates **4 / 2 / 24**. Hook string fixture: raw/replacement **204 / 226**. Footers are appended after the core guard. These are emitted-representation estimates, not observed transcript growth or charges. | [T09] [T10] [T11] [T12], **G04** |
| **Structured Bash emits the wrong replacement shape** | Structured input is flattened to a string; stderr and other envelope fields are absent from that string. Current Claude documentation says invalid built-in replacement shapes are ignored, preserving the original—not that the malformed string is accepted and stderr lost. Live behavior remains untested. | [T10] [O1], **G03** |
| **Public retrieval is incomplete at its default limit** | SQLite returns all **200,001** characters; the wrapper returns the first **200,000** plus a truncation notice, with no paging argument. The limit is configurable; storage remains intact. | [T08] [T09], **G07** |
| **Reference display is not solely content-derived** | Identical text with different `source` metadata has the same short content hash but a different complete placeholder. Stable content identity alone does not prove whole-request prefix stability. | [T08], **G07/G11** |

**Positive control:** logs with a failed stash preserve the original. That safer pattern should be propagated rather than introducing another abstraction. [T06]

Evidence files: `tokenmaster/probe_boundaries.py`, `tokenmaster/boundary-probe-results.json`. **All 11 narrowly scoped probe assertions were confirmed.** An independent read-only review found no clear false positive in those narrow assertions, while explicitly rejecting broader host, billing and AST claims: `tokenmaster/INDEPENDENT_REVIEW.md`.

### Test result, without hiding the environment limitation

The existing suite collected **120 tests: 110 passed, 10 failed, zero skipped/errors**. This runtime has pytest but not MCP, tiktoken or the tree-sitter dependencies. All ten failures expect dependency-enabled AST compression; missing grammar imports select no-op. This does **not** establish ten production defects, and some passing preservation/determinism checks also pass on no-op, so it does **not** establish full compressor coverage either. No dependencies were installed to make the result green.

The source tests themselves also conflate some marker-only behavior with “lossless”; for example, the code stash-failure test asserts an elision marker, not retention of the body. Correcting the contract and its tests is part of G02. Logs already have stronger failed-stash preservation tests. [T43]

Fresh logs and environment: `tokenmaster/pytest-output.txt`, `tokenmaster/pytest-results.xml`, `tokenmaster/pytest-run.json`.

### Why the README evidence needs narrower wording

- The routing claim is a publisher-reported **36-run structural-task study**, not a general agent-quality or invoice result. The README explicitly says cumulative tokens, not dollars. [T17] [T44]
- The shipped compression benchmark's “recovery verified” statement is not supported by its current oracle. This does not invalidate every separate storage unit test. [T13] [T18]
- The available untracked `sandbox_brainspace/verify_dual_host.py` invokes a hook subprocess with a synthetic/plain-string Bash payload and inspects stdout; that portion does not run Claude Code's schema acceptance. The research preserved that local harness with a SHA-256 provenance record, rather than presenting it as committed or current upstream evidence.
- Lossless storage, literal-byte recovery, schema preservation, model attention, task correctness, prompt-cache reuse and lower billed cost are seven different claims. None implies all the others.

## 5. What the published measurements do—and do not—prove

| Product | Useful evidence | Limit on a parity claim |
|---|---|---|
| Ponytail | Real prompt/agentic harness, deterministic graders, adversarial references, historical CLI cost/latency recording. Fresh selected tests: **21 Node tests**, **6 LOC + 4 correctness regressions**, **20 good/bad scorer references** passed. | Instrument checks are not a new model A/B. Raw historical output matrices/workspaces are absent at this pin; some graders are permissive or regex-only. The June 17 report says 42–75% lower Claude cost but higher costs for two historical OpenAI reasoning-model runs, while gain still prints 47–77%. [P05] [P11] [P12] [P13] [P14] |
| Headroom | Committed seeded table: **178,024 → 104,261 tool-content tokens**, rounded **41%**, over four generated scenarios. Current source has targeted regression tests and provider/cache accounting. Fresh **23/23** isolated pure checks passed. | This table is not full requests, output/retrieval traffic, task completion or invoices. The named CCR “round-trip” eval checks substrings/nonempty output, not retrieval. Paid suites may skip and some weekly checks are non-blocking. Native Rust, ML models and real host/provider integrations were not run here. [H27] [H28] [H29] [H30] |
| TokenMaster | Existing 120-test suite, focused offline boundary checks, structural routing study reported by the publisher. | Benchmark oracle and boundary defects above must be fixed. Current fresh run is environment-limited; no new quality, cache or billing A/B was performed. [T13] [T17] [T18] |

Ponytail's June 18 writeup also withdraws an earlier contaminated baseline and reports **54% less added LOC overall** for its replacement feature experiment; 60–94% is a subset, not the overall result. Baseline isolation and completion grading must be verified before copying that benchmark design. Headroom's documented CPU latency numbers are for an older 0.37.0 Apple-M-series setup, not the current Windows source snapshot. [P12] [P13] [H45]

**Inference:** neither competitor's marketing numbers supply a fair acceptance target for TokenMaster. A better target is equivalent task completion with transparent total cost/latency on the same tasks, host and model, including unfavorable strata.

## 6. Compatibility, permissions and security

| Surface | Source-backed conclusion | Required TokenMaster contract |
|---|---|---|
| Claude Code | `updatedToolOutput` now applies to all tools **when output shape matches**; do not repeat older MCP-only descriptions. Ponytail uses lifecycle injection; Headroom's main wrapper uses a proxy. [O1] [P02] [H20] | Versioned, schema-preserving adapters and a real provider-bound trace. No claim from hook stdout alone. |
| Codex CLI/desktop | Current official docs support stdio/HTTP MCP and hooks. Codex's PostToolUse contract includes feedback replacement; it explicitly rejects `updatedMCPToolOutput`, but that does not establish how the different `updatedToolOutput` field is handled. [O2] [O3] | Implement/test its documented contract separately. Do not claim “Codex has no hooks” or silently translate Claude fields. |
| MCP | Model-invoked tools and prompt retrieval are not transparent interception. Headroom's HTTP MCP endpoint is separate from the proxy. [P10] [H18] [H40] [T09] | Preserve structured/text/image blocks, errors and IDs; scope original access; measure tool argument/result overhead. |
| Native Windows | Relevant Ponytail tests passed; Headroom has native-wheel/limited CI work but explicitly lacks owner-only NTFS ACL enforcement in inspected helpers. No full host matrix ran here. [P17] [H24] [H33] | Native Windows path/quoting/encoding/process tests, not Linux-only shell assumptions. Isolated host homes and rollback tests. |
| Privilege boundary | Ponytail hooks execute code with host/user permissions. Headroom proxies plaintext requests/credentials and is designed for local user trust, not tenant isolation. TokenMaster installers write host-level config; malformed config currently can be treated as empty before rewrite. [O1] [H26] [T16] | Least required writes, transactional merge/backup, fail on malformed config, explicit sensitive-data handling and no new network behavior hidden inside compression. |
| Persistence and egress | Headroom CCR stores plaintext originals; beacon is default-on, local telemetry and licensed reporting are different controls. TokenMaster stores zlib-compressed originals in SQLite, which is not encryption. Inspected Ponytail lifecycle code records modes, not an automatic savings/telemetry ledger. [H25] [H26] [T08] [P02] [P03] [P04] | Opt-in sharing/telemetry, retention/GC quotas, privacy-safe event logs, scoped refs, disclosure of any optional remote compressor. Do not claim “local” means secret-free or no egress. |
| Licensing/provenance | TokenMaster MIT; Ponytail upstream MIT; Headroom source Apache-2.0. Bundled Ponytail carries its upstream notice. Headroom's separately fetched Kompress model card also declares Apache-2.0, but source pinning does not pin downloaded weights. [T19] [P15] [H31] [H46] [I1] | Retain applicable notices and review exact dependency/model versions before adoption. This is source-license identification, not a comprehensive legal/security audit. |

Additional risks worth testing rather than marketing away:

- Tool-result text and originals can contain secrets and prompt injections; recovered content is still untrusted.
- Stable hashes are identities, not authorization tokens.
- A cache hit or zero retrieval does not prove that omitted information was irrelevant.
- Headroom's buffered CCR path can alter streaming latency; its transport-specific limits should be benchmarked, not flattened into one “streaming supported” badge. [H22]
- Current TokenMaster launch strings use unpinned `uv --with` dependencies. Dependency/version reproducibility and config safety are necessary before broad distribution. [T15] [T16]

## 7. Prioritized parity plan

Full implementation-sized details are in `GAP_BACKLOG.md`; this is the decision order.

| Priority | Slices | Exit condition |
|---|---|---|
| **P0: evidence and correctness** | **G01** recovery oracle; **G02** fail-closed omission; **G03** real host envelopes; **G04** final-representation budget guard | Regressions prove recovery and no unsafe boundary behavior. Withdraw/qualify unsupported current claims. |
| **P1: practical product parity** | **G05** scoped task discipline; **G06** contract-aware structured views; **G07** complete/scoped recovery; **G08** Codex/Windows adapter | Named workflows and hosts work with conservative defaults, bypasses and rollback. Do not require ML to pass. |
| **P1: measured differentiation** | **G09** end-to-end ledger/quality experiment; **G10** graph freshness/completeness | Quality-first acceptance on held-out workloads; all overhead counted; no stale/exhaustiveness deception. |
| **P2: expansion justified by data** | **G11** request-level cache/budget policy; **G12** optional advanced engines/transports | Each added mechanism earns its maintenance/security burden through a separately qualified workload benefit. |

**Recommended minimum:** implement the first two rows, protect graph correctness, then qualify the result through G09. Start with exact/structural transformations and safe bypasses; do not start by turning on stronger semantic pruning.

**Do not interpret this as an adoption decision.** Embedding Headroom or another model/package may be better than rebuilding an advanced backend, but needs a separate version/maintenance/license/security/Windows evaluation. No dependency was selected, installed or configured in this task.

## 8. How to claim measured-quality parity honestly

The protocol compares:

1. Stock host.
2. Pinned Ponytail.
3. Pinned Headroom in its actual default product configuration.
4. Current TokenMaster.
5. Ponytail + Headroom.
6. Candidate TokenMaster.

A separate `2 × 2 × 3` ablation varies task discipline, graph routing and compression engine while controlling other conditions. The installed Ponytail bundle can be a separately named additional arm; it is not a substitute for upstream.

Required outcomes:

- Hidden-test/exact-answer/independent-source task success; blinded scope/maintainability review.
- Provider-reported uncached input, cache read/write, output and every retry/retrieval/continuation.
- Cold and warm caches; graph/index and process cold starts; p50/p95 whole-task and first-token latency.
- Cost per attempted task and cost per successful task with failed-attempt costs retained.
- Separate estimates, provider usage, counterfactual attribution and reconciled invoice evidence.

**Proposed gates, not established facts:** zero protocol/security invariant failures; 100% on exactness-required fixtures; predeclared task-success non-inferiority margin (suggested −2 percentage points with a one-sided confidence bound); then a useful cost/successful-task gain (suggested ≥10%) without an unacceptable p95 latency regression. Pilot variance determines the required sample; a small non-significant difference is not parity.

These gates are stricter and more useful than “same commands,” “original exists in a cache,” “120 tests,” or “N% fewer input tokens.” No such end-to-end claim has been measured in this research.

## 9. Stop condition, preservation and remaining uncertainty

The requested research is complete: canonical identities and source pins, installed-snapshot drift, capability matrix, concrete backlog, benchmark protocol, compatibility/security/license boundaries, fresh offline evidence and limitations are documented.

No production files were intentionally changed; no install, model/API benchmark, external service, commit, push or persistent runtime-configuration change was performed. Research outputs are confined to:

`C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\`

The repository's existing whitelist `.gitignore` ignores this research directory. The reports are local artifacts, not published or committed files.

Remaining uncertainty is substantive and explicit: working dependency-enabled AST compression in this runtime, real Claude/Codex/MCP host acceptance, full Windows runtime behavior, live upstream CI state, optional model/native-component behavior, broad adversarial security, and paired quality/latency/billed-cost outcomes. Closing those gaps requires separately scoped execution; this report does not pretend they are already solved.

## Pinned reference registry

All repository links below use a full commit SHA. Upstream dossiers include additional narrow references, hashes, history, tests and raw evidence.

### TokenMaster

[T01]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/agent.template.claude.md#L26-L69
[T02]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/graphify_mcp.py#L39-L355
[T03]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/compressors/json_compressor.py#L85-L168
[T04]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/compressors/code_compressor.py#L46-L105
[T05]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/compressors/code_compressor.py#L301-L319
[T06]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/compressors/logs_compressor.py#L28-L186
[T07]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/compressors/prose_compressor.py#L62-L184
[T08]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/ccr.py#L133-L203
[T09]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace_mcp.py#L13-L114
[T10]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace_posttooluse.py#L66-L160
[T11]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/router.py#L140-L179
[T12]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/tokens.py#L19-L67
[T13]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/benchmark.py#L73-L139
[T14]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/setup.py#L44-L77
[T15]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace_setup.py#L49-L65
[T16]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace_setup.py#L137-L231
[T17]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/README.md#L76-L122
[T18]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/README.md#L140-L208
[T19]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/LICENSE#L1-L21
[T20]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/.claude-plugin/plugin.json#L1-L13
[T43]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/token-master-plugin/skills/token-master/brainspace/tests/test_code_compressor.py#L320-L340
[T44]: https://github.com/All-The-Vibes/TokenMasterX/blob/426fc853389ddba4bc6e1dd35a28179a895c064f/README.md#L309-L311

### Ponytail

[P01]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L26-L120
[P02]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/claude-codex-hooks.json#L1-L41
[P03]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-runtime.js#L19-L75
[P04]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-activate.js#L29-L62
[P05]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-gain/SKILL.md#L13-L50
[P06]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-review/SKILL.md#L13-L61
[P07]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-audit/SKILL.md#L12-L45
[P08]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-debt/SKILL.md#L15-L44
[P09]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.codex-plugin/plugin.json#L1-L31
[P10]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/ponytail-mcp/index.js#L1-L52
[P11]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-17-cost-verification.md#L7-L93
[P12]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-18-agentic.md#L40-L219
[P13]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/run.py#L31-L479
[P14]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/tasks.py#L810-L893
[P15]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/LICENSE#L1-L21
[P16]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/package.json#L1-L48
[P17]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/tests/hooks-windows.test.js#L30-L193

**I1 — exact installed evidence:** manifest `C:\Users\shyamsridhar\.codex\plugins\cache\openai-curated-remote\engineering-suite-ponytail\2.0.0\.codex-plugin\plugin.json:1–34`; lock `C:\Users\shyamsridhar\.codex\plugins\cache\openai-curated-remote\engineering-suite-ponytail\2.0.0\UPSTREAM_LOCK.json:46–61`; bundle README lines 1–21; six skill files and hashes preserved in the Ponytail dossier. The lock's older source version was verified against [4.9.0 package metadata](https://github.com/DietrichGebert/ponytail/blob/356918eba965ee1eac64bd3a7f0dd02108350de5/package.json#L1-L4). This is installed-snapshot evidence, not a claim about active host state.

[I1]: ponytail/HASHES.md

### Headroom

[H01]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/pyproject.toml#L1-L96
[H02]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/pipeline.py#L133-L170
[H03]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/crates/headroom-core/src/transforms/smart_crusher/crusher.rs#L871-L928
[H04]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/smart_crusher.py#L1-L98
[H05]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/kompress_compressor.py#L1817-L1899
[H06]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/content_router.py#L1790-L1888
[H07]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/content_router.py#L6069-L6135
[H08]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/compress.py#L104-L141
[H09]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/compression_policy.py#L94-L137
[H10]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/cache_aligner.py#L1-L24
[H11]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/gemini.py#L64-L106
[H12]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/tests/test_gemini_prefix_freeze.py#L1-L23
[H13]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/outcome.py#L60-L115
[H14]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/cost.py#L1020-L1089
[H15]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/cost.py#L1549-L1581
[H16]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/cache/compression_store.py#L1108-L1209
[H17]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/ccr/response_handler.py#L467-L552
[H18]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/ccr/mcp_server.py#L1-L53
[H19]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/providers/codex/install.py#L145-L177
[H20]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/cli/wrap.py#L1029-L1063
[H21]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/cli/wrap.py#L439-L488
[H22]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/openai.py#L1280-L1313
[H23]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/memory_tool_stream.py#L1-L49
[H24]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/fileperms.py#L9-L31
[H25]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/telemetry/beacon.py#L31-L92
[H26]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/SECURITY.md#L77-L108
[H27]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/evals/runners/compression_only.py#L75-L148
[H28]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/benchmarks/results/index_proof_table.txt#L1-L22
[H29]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/benchmarks/index_proof_table.py#L54-L97
[H30]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/.github/workflows/eval.yml#L118-L175
[H31]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/LICENSE#L1-L9
[H32]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/tests/test_compression_safety_rails.py#L92-L199
[H33]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/.github/workflows/ci.yml#L156-L219
[H34]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/image/compressor.py#L573-L636
[H35]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/output_shaper.py#L1-L37
[H36]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/rollout.py#L105-L115
[H37]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/crates/headroom-core/src/transforms/smart_crusher/orchestration.rs#L138-L225
[H38]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/content_router.py#L1922-L1948
[H39]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/openai.py#L7262-L7285
[H40]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/ccr/mcp_http.py#L22-L55
[H41]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/tests/test_stateless_no_disk.py#L137-L149
[H42]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/semantic_cache.py#L25-L73
[H45]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/docs/content/docs/benchmarks.mdx#L10-L92
[H46]: https://huggingface.co/chopratejas/kompress-v2-base/blob/e00cc5e60ff73b01674ef8fa6da6c5acf6d54181/README.md
[H47]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/log_compressor.py#L1-L40
[H48]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/search_compressor.py#L1-L41
[H49]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/config_compressor.py#L1-L27
[H50]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/diff_compressor.py#L1-L40
[H51]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/openai.py#L1783-L1814
[H52]: https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/openai.py#L6840-L6856

### Official host/provider contracts, fetched October 4, 2026

These pages are mutable documentation, so their fetched content and SHA-256 hashes are preserved in `official/manifest.json`.

[O1]: https://code.claude.com/docs/en/hooks#posttooluse-decision-control
[O2]: https://developers.openai.com/codex/mcp/
[O3]: https://learn.chatgpt.com/docs/hooks
[O4]: https://developers.openai.com/api/docs/guides/prompt-caching

See `BENCHMARK_PROTOCOL.md` for official provider-cache/usage references and exact accounting boundaries.
