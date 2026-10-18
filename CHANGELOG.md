# Changelog

All notable changes to TokenMaster are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow semantic versioning.

## [Unreleased]

### v7 navigation in host setup — October 18, 2026

- `setup.py` now installs one MCP server, `tokenmaster-nav` (`navigation_mcp.py`),
  with the three v7 tools. Only the server and the three modules it imports are
  copied. The symbol index is prebuilt, and the server builds it on first use if it
  is missing.
- Pre-v7 graph servers are removed on install and uninstall, but only when
  TokenMaster's ownership receipt says it installed them: `graphify-nav`, which
  exposed graphify's 6 tools, and `codegraph`. Codegraph provisioning
  (`--install-codegraph`) is gone; PRS-2 measured its `codegraph_explore` source
  dumps as the most expensive graph tool.
- The Claude and Copilot agent templates replace 1,383 tokens of routing rules with
  the 66-token hint tested in PRS-3. Their task-discipline, memory and freshness
  sections remain. Those sections were not part of the PRS-3 configuration.
- Added `tests/test_navigation_mcp.py`, which runs the installed layout over MCP
  stdio. The setup test now covers the upgrade path.

### Graph-first navigation (v7) and PRS-3 — October 18, 2026

- Added `brainspace/symbol_index.py` (v7). It keeps a SQLite index of Python
  symbols, Markdown sections and JSON keys with exact line ranges, and offers three
  compact tools:
  - `locate` finds a symbol, or returns a file's outline.
  - `read_symbol` returns exactly one symbol, file or line range.
  - `impact` lists callers. Call sites resolved by graphify come first; call sites it
    missed are added from name matches and marked `[name]`; edges from files edited
    since the graph was built are dropped.
  - Every result stays under 2,400 tokens, and the three tool definitions cost 269
    tokens.
- Added `evals/run_prs3_study.py`, `evals/prs3_tasks.json`,
  `docs/PRS3_PROTOCOL.md` and `docs/PRS3_RESULTS.md`.
- PRS-3 (pre-registered, 480 live sessions, 24 fresh blind-authored tasks):
  - v7 lowered cost by 22.0% against stock (95% CI −35.4% to −8.9%, Holm
    p = 0.006). Quality was unchanged at 120/120.
  - v6 replicated, at −13.0% against stock.
  - v7 against v6 was −10.4%, which is not significant (p = 0.16). The goal of at
    least 30% savings is not met.
- v7 is not yet wired into host setup.

### `request-policy-v6` and PRS-2 — October 18, 2026

- Added `request-policy-v6` (`brainspace/v6_shaping.py`):
  - Each tool result is shaped by a deterministic, position-independent function,
    so earlier messages never change and provider prompt caches stay valid.
  - Search and list output is folded losslessly.
  - Oversized results become digests that state what was omitted and how to fetch it.
  - Tool notices are kept verbatim.
  - v6 adds no recovery tool and cannot be combined with prompt guidance.
- `ResponsesTransport` gained a `parallel_tool_calls` flag (default unchanged).
- PRS-2 (pre-registered, 216 live sessions):
  - On 12 fresh tasks, v6 lowered cost by 11.6% (95% CI −20.8% to −3.8%) and raw
    tokens by 17.2%, with quality unchanged at 36/36.
  - On 12 older tasks, it lowered cost by 16.8%.
  - Graph tools as shipped raised cost by 12.9%.

### PRS-1 pre-registered study and retraction — October 18, 2026

- Retracted the October 17 savings claims (−83.29%, −73.19%, −65.68%, −48.51%,
  −44.20%, −43.14%). They came from synthetic padded modules, scripted file reads,
  unused tools in the baseline, a misconfigured Headroom adapter, and ignored
  prompt caching.
- Added `evals/run_prs1_study.py`, `evals/prs1_tasks.json`,
  `docs/PRS1_PROTOCOL.md` and `docs/PRS1_RESULTS.md`. Together they make up a
  pre-registered 252-session live study on 12 blind-authored tasks from this
  repository, with 7 arms and the real Copilot CLI system prompt.
- Results:
  - No TokenMaster configuration significantly reduced total tokens: v5 +7.8%,
    graph −1.1%, graph + v5 +4.8%.
  - v5 raised cache-weighted cost by 61.6% (95% CI +19.6% to +111.0%).
  - Every TokenMaster arm passed 36/36.
- Recorded product gaps, left unfixed:
  - `parallel_tool_calls` is forced to `false`.
  - v5 breaks the provider's prompt cache.
  - `exact_reuse` skips `view` reads.
  - The agent text names stale codegraph tools.

### Experimental `request-policy-v5` — October 17, 2026

- Added `request-policy-v5` (`brainspace/v5_reducer.py`). It is wired into
  `request_policy.py`, `pipeline.py`, `runtime_policy.py` and `runtime.py`, and
  preserves the `v1`–`v4` policy identities.
- v5 keeps the newest tool result verbatim. It compacts older reads (code
  skeletons, JSON overviews, Markdown and log summaries) behind one
  `compact-root-v1` reference (`[[BR:<64-hex>|r=1]]`) backed by SQLite `CCR`.
- Qualified GitHub Copilot CLI `1.0.98` in `native_copilot.py` and `native_runtime.py`.
- Added synthetic sandbox harnesses (`run_isolated_sandbox_savings.py`,
  `run_native_copilot_sandbox.py`, `run_2m_4way_sandbox_study.py`,
  `run_full_stack_graph_v5_study.py`). Their savings figures are retracted; see
  the October 18 entry.

### Conservative request-policy repair — October 8, 2026

- Added opt-in V3 exact visible-read reuse: retain unique evidence, require
  bound executor receipts, verify full reconstruction, and guard the complete
  request without lossy callbacks, external recovery, or task-mode instructions.
- Added the explicit `request --conservative --source-reads` CLI path and
  preserved disabled defaults and legacy V1/V2 transformation behavior.
- Fixed successful `fetch_artifact` alias receipts to retain the actual
  model-facing tool identity; failed and mismatched reads remain untrusted.
- Replayed 69 prior baseline requests unchanged. A new frozen paired run matched
  baseline on six reading questions and used 9.9% fewer gateway-reported task
  tokens on four deliberate repeated-read probes, with all answers correct
  and no extra requests. This is not a general savings or promotion claim.
- Added corruption, CLI/installed-copy, negative-control, and failure-accounting
  tests. Historical captures and the previous unsuccessful scorecard are retained.

### Token-only foundations and conservative parity work — October 4, 2026

- Added pinned reference measurement identities, complete task/call inventories,
  sealed learning accounting, and independent fixed/anytime confirmation.
- Added a durable bounded hill-climber with immutable safe policy neighbors,
  registry-only promotion, stale-version checks, cancellation and rollback.
- Added the opt-in typed Jev client. Jev remains advisory; it never provides
  authorization or its own correctness certificate. No credentials are persisted.
- Added task/session contracts, bounded review, explicit request planning and
  protected instructions, tool pairs, recent results and declared stable prefixes.
- Repaired the recovery benchmark: it now retrieves emitted references and checks
  exact equality, distinguishes root/fragment/no-op/unverified results, and never
  equates storage recovery with successful task completion.
- Made code/prose conservative by default; skeletons and lossy overviews are
  explicit. Added final representation guards and removed savings footers.
- Added scoped, digested, paged Unicode recovery and bounded exact search.
- Added schema-preserving Claude output adapters, explicit Codex configuration,
  safe owned-setting install/uninstall, and pinned offline-at-launch runtimes.
- Added graph provenance, source/index freshness and bounded enumeration.
- Replaced current README efficiency/host claims with explicit evidence boundaries.
  No monetary objective or model-weight changes are part of this implementation.
- Added a frozen-source real-model challenge runner, separately graded synthetic
  workspaces, bounded WSL code execution and complete visible call captures.
- Added an offline whole-task savings audit with exact recounting, source/call/
  outcome hashes, explicit review opt-in, separate bridge-reported diagnostics,
  per-pair results and retained-receipt verification. No statistical certificate
  is issued from the non-IID pilot.
- Added compact task-contract rendering without machine/session telemetry, and
  repaired a Windows cleanup-test startup race with bounded readiness and an
  exact retained descendant handle.
- Repaired native Claude MCP text-result handling using captured bare content
  arrays; preserved mixed media, structured strings, errors and interruption
  bypasses under an explicit updated contract.
- Added an 11-cell native envelope matrix and real temporary user-settings
  install/uninstall verification, with complete provider-result comparisons,
  helper-source integrity checks and unrelated-configuration preservation.

**Historical notes below describe the earlier implementation and measurements.**
Their blanket losslessness, stable-ratio, default-skeletonization, unpinned-launch
and host-verification claims are superseded by the current contracts and
verification matrix. They are retained for history, not current release evidence.

### Added — Rust as a first-class language

Both token-economics layers now treat Rust the way they treat Python.

- **Brainspace code compressor skeletonizes Rust** (`brainspace/compressors/code_compressor.py`).
  The compressor is now spec-driven: a small per-language table names the grammar
  to load and the node roles that drive the walk, so Python and Rust share one
  engine. For Rust it elides `function_item` bodies (including trait *default*
  methods), recurses into `impl` / `trait` / `mod` blocks, and keeps the
  structural signal verbatim — `struct` / `enum` fields, bodiless trait method
  signatures, `use`, `const`, `///` doc comments and `#[attributes]`. Lossless
  recovery and determinism hold exactly as for Python.
- **Language is resolved from the file extension** (`brainspace/router.py`). The
  router now threads a `lang` (`.rs` → `rust`, `.py`/`.pyi` → `python`) into the
  code compressor; without it every code output was parsed as the Python default,
  so Rust silently passed through. The `PostToolUse` hook now uses the tool's
  input file path as its routing hint (`brainspace_posttooluse.py`) so a `Read`
  of `foo.rs` actually resolves to Rust.
- **Graph routing surfaces Rust trait implementors** (`graphify_mcp.py`).
  `inheritors` now reads `implements` edges (Rust `impl Trait for Type`) in
  addition to class `inherits`, so "what implements / overrides X" works in
  trait-based languages. graphify already indexes Rust natively via tree-sitter
  with a dense call graph (measured 0.21 `calls`/symbol on a real 4.1k-LOC crate —
  well clear of the sparse-warning floor), so `find` / `callers` / `callees` /
  `impact` / `explain` needed no change.
- **Install wires the grammars so code compression actually runs**
  (`brainspace_setup.py`). The MCP server and hook previously launched with
  `--with mcp` only, which made the code compressor lazy-import-degrade to a no-op
  in every real install (Python included). They now launch with `tree-sitter`,
  `tree-sitter-python`, `tree-sitter-rust`, and `tiktoken`, declared once in a
  shared `RUN_WITH`.

Measured on a real Rust crate (korg, ~4.1k LOC): **66.2% pooled token reduction**
on code outputs across 22 files (`tiktoken cl100k_base`).

### Added — Brainspace, the compression layer

A second token-economics layer that complements graph routing. Routing collapses
the cost of *re-deriving structure*; Brainspace shrinks the *raw tool outputs*
(directory listings, test logs, file dumps) that sit in the transcript and get
re-sent on every subsequent turn. Different token populations, so the savings
compound.

- **Compression engine** (`brainspace/`): a `ContentRouter` that detects content type
  (JSON / code / logs / prose) and dispatches to a per-type compressor, backed by
  the **CCR** (Content-addressed, Cached, Reversible store) — lossy *display*,
  lossless *recovery*. Originals are stashed under `sha256(content)` and replaced
  with stable `[[BR:...]]` placeholders; the model calls `brainspace_retrieve` to get
  exact bytes back. Content-addressing gives free dedup and a cache-stable
  placeholder (it never perturbs the provider's prompt-cache prefix).
- **Dual-host delivery**:
  - **Claude Code** — full layer: a `PostToolUse` hook auto-compresses tool output
    at the append boundary (via the `updatedToolOutput` field) plus model-invoked
    `brainspace_compress` / `brainspace_retrieve` / `brainspace_stats` MCP tools.
  - **GitHub Copilot CLI** — MCP-only (Copilot has no documented output-rewriting
    hook), so compression is model-invoked. Verified end-to-end against the real
    `copilot` binary.
- **`brainspace_benchmark.py`** — a self-serve benchmark that measures compression on
  *your own* files, directories, or piped output, in real `tiktoken` tokens, with
  lossless recovery verified per placeholder. Modes: file/dir args, `--stdin`,
  `--json`, and a no-args demo. Reports per-type results plus an area-under-curve
  projection (a compressed output is re-sent every turn it lingers).
- **`brainspace_setup.py`** — dual-host installer, idempotent and reversible by key
  (`--uninstall` removes only the `brainspace` keys it added). Honors
  `CLAUDE_HOME` / `COPILOT_HOME` for sandboxed installs.

### Measured impact

Real artifacts, real `tiktoken cl100k_base` tokens (reproduce with
`brainspace_benchmark.py`):

| Content type | Example | Reduction | Ratio |
| --- | --- | --- | --- |
| JSON | directory listing, 200 files | 88.0% | 8.36x |
| log | live `pytest -v` run | 83.3% | 5.97x |
| code | real engine source | 35.3% | 1.55x |
| prose | README + research doc | 0.5% | 1.01x (honest negative) |

- Claude `PostToolUse` hook, end-to-end: a 3,226→98 token output (97.0%) with the
  buried `ValueError` preserved.
- GitHub Copilot CLI, real binary, end-to-end: `brainspace_compress` invoked on
  8,299 chars → 303; tool-reported 2,075→55 tokens (97.3%).

### Fixed

- **Never-expand guard now bills tokens, not characters** (`brainspace/router.py`).
  A content-addressed placeholder can be fewer *characters* than the body it
  replaces while tokenizing to *more* tokens (hex hashes and long identifiers don't
  BPE-merge), so a char-based guard could silently cost tokens on code with many
  tiny functions. The guard keeps a cheap char fast-path, then confirms the result
  is token-smaller before accepting. Surfaced by `brainspace_benchmark.py` itself.
- **Markdown / rST now route to prose, not code** (`brainspace/router.py`). Doc files
  embedding code-fence keywords (`import`, `def`) were misdetected as code; the
  filename hint now classifies them as prose first.
- **Code-compressor reduction test de-flaked**: the assertion sat exactly on a 30%
  threshold that real tiktoken measured at 29.5%, making it pass/fail by which
  tokenizer happened to be installed. Lowered to a 25% floor both backends clear.

### Tests

- 120 unit tests across the four compressors, the router (including the
  never-expand-in-tokens regression and code-language resolution), and the
  never-expand invariant — green on both the `tiktoken` and heuristic token
  backends. Rust coverage: skeletonization, lossless recovery, struct/signature
  preservation, determinism, reduction, and graceful no-op when the grammar is
  absent.
- Isolated sandbox harnesses (`sandbox_brainspace/`, kept out of the shipped plugin):
  MCP stdio protocol conformance via the official client, and an 18/18 dual-host
  install + end-to-end verification that never touches the real CLI config.
