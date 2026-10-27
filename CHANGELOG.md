# Changelog

All notable changes to TokenMaster are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow semantic versioning.

## [Unreleased]

### Fixed

- Graph navigation covers Rust again. Rust became a first-class language in `9b86c8a` (#10), but the v7 symbol index
  (`brainspace/symbol_index.py`) took code symbols only from `.py` and `.pyi` files, so `locate`, `read_symbol` and
  `impact` found no Rust function, type or caller. It now parses `.rs` files with the pinned `tree-sitter-rust`:
  functions, methods, types, traits, inline modules, constants and macros, with callers through `use ... as` aliases
  and inside macro arguments such as `assert_eq!`. Targets accept Rust paths (`Store::new`,
  `src/store.rs::Store::new`) and pytest-style `path::Class::method`, which used to return an error. `impact` lists
  same-language callers only, and leaves out calls that name another concrete type or a standard-library item, such
  as `std::path::Path::new()` for `Store.new` or `fs::read()` after `use std::fs` for the crate's own `fs::read`,
  with the graphify edges built on them: graphify 0.9.17 resolves such calls to the file's own function. A call stays
  listed when it goes through the method's trait (`FromStr::from_str`), a type that implements the trait, a generic
  parameter or a type alias. A graphify edge that rests on such a path, or on a same-named type from another crate
  (`dep::Error::new()` for the crate's own `Error.new`), is marked `[inferred]`. Cargo's `target/` build output is
  not indexed. The index schema moves to version 5, so an existing `.token-master/symbols.sqlite` is rebuilt on
  first use.
- `/token-master` runs both Copilot installers: `setup.py` for graph navigation, then `brainspace_setup.py` for the
  `view` hook, the launcher and `/tokenomics` (`skills/token-master/SKILL.md`). It ran only `setup.py` before, so the
  README's launcher command pointed at a file that setup never copied.
- The skill looks for the pinned runtime in `<COPILOT_HOME>/token-master-runtime`, then an activated virtual
  environment, and stops with the one-time setup commands when neither exists. It no longer tries another interpreter
  that fails the pin check.
- The missing-`graphify` hint in `setup.py` names the real PyPI package, `graphifyy`. No package named `graphify`
  exists on PyPI.
- The missing-tokenizer error (`hosts/tokenizer.py`) gives the command that caches `cl100k_base`, and reports a
  mistyped `--tokenizer-file` or `BRAINSPACE_TOKENIZER_FILE` as not found.
- `config_lock` (`hosts/config.py`) retries on Windows while a just-released lock is still delete-pending. Creating it
  then raised `PermissionError` in 1.4% to 2.3% of contended lock attempts, which also made
  `test_concurrent_updates_do_not_lose_other_server` flaky.

### Changed

- README Quickstart: install from the marketplace (`copilot plugin marketplace add All-The-Vibes/TokenMasterX`, then
  `copilot plugin install token-master@token-master`), with a new "Prepare the runtime" step. Commands use `$HOME`
  instead of `~`, which Windows PowerShell 5.1 passes to native programs literally, and the launcher runs on the
  runtime's Python, whose `tiktoken` BYOK shaping needs.
- README hero: a TokenMasterX logo and banner (`assets/tokenmasterx-mark.svg`, `tokenmasterx-logo.svg`,
  `tokenmasterx-hero.svg`), drawn from token chips by `assets/generate_logo.py` so they render the same everywhere
  with no fonts to embed. The intro drops session and task counts, CLI versions and the word "real", and the "up to
  80% back to back" figure: it came from bring-your-own-model runs on CLI `1.0.78-3`, where the bridge fixed a
  per-session cache miss that `1.0.98` no longer has.
- Docs cleanup: the README hero now credits its numbers to the pre-registered study, where both versions passed every
  task. `MISSION.md` drops its October 23 status and open-levers sections for a pointer to current results.
  `DUAL_HOST_PLAN.md` is removed; `harness-command-design.md` and `token-efficient-harness-research.md` move to
  `docs/history/` and `docs/research/` with superseded notes.

### Added

- Uninstall: `/token-master uninstall` runs both installers with `--uninstall`, and the README documents the full
  removal order, including the backup copies that uninstall keeps.
## [0.2.0] - 2026-10-26

### Added

- **Pre-registered PRS-6 confirmatory study on real GitHub Copilot CLI `1.0.98`**
  (`token-master-plugin/docs/PRS6_PROTOCOL.md`, commit `19443fc`; evidence and recount script in
  `evidence/prs6-copilot-1.0.98-20261026/`):
  - Verified `Version number: 1.0.98` across all 176 session captures (`0` recount mismatches; per-call
    `total_nano_aiu` matching calculated USD within `$0.0001`).
  - **29-task repository benchmark (`P01`–`P24` + `H01, H02, H03, H05, H06`, 116 sessions):** `gpt-6-astra` cut raw
    tokens by **49.5%** (`2,449,067 → 1,237,510`; 95% CI −55.9% to −42.3%; Holm $p < 0.0001$; lower on 27/29 tasks),
    cold-repriced cost by **41.5%** (`$8.91 → $5.21`; Holm $p < 0.0001$), and back-to-back cost by **50.2%**
    (`$6.83 → $3.40`), passing **29/29 vs 29/29**. `claude-opus-5.5` cut raw tokens by **38.0%**
    (`2,672,316 → 1,655,797`; 95% CI −44.7% to −31.3%; Holm $p < 0.0001$; lower on 27/29 tasks), cold-repriced cost
    by **34.0%** (`$4.23 → $2.79`; Holm $p < 0.0001$), and back-to-back cost by **40.1%** (`$2.72 → $1.63`), passing
    **29/29 vs 29/29**.
  - **15-task Django 5.2 caller replication (`D01`–`D15`, 60 sessions):** `gpt-6-astra` cut raw tokens by **58.5%**
    (`707,799 → 293,779`; lower on 15/15 tasks), cold cost by **53.5%** (`$3.40 → $1.58`), and back-to-back cost by
    **70.7%** (`$2.36 → $0.69`), passing **15/15 vs 15/15**. `claude-opus-5.5` cut raw tokens by **53.7%**
    (`989,925 → 457,875`; lower on 15/15 tasks), cold cost by **46.0%** (`$1.81 → $0.98`), and back-to-back cost by
    **61.2%** (`$1.11 → $0.43`), passing **15/15 vs 15/15**.
- **Dynamic capability-aware tool routing (`brainspace_copilot_bridge.py`):** replaced static 11-tool pruning with
  `CAPABILITY_GROUPS`, `select_excluded_tools()`, and `_installed_names()`. The launcher now inspects CLI flags
  (`--agent`, `--resume`, `--continue`), prompt intent (`-p` / `--prompt`), installed skills and agents in
  `<COPILOT_HOME>` and `.github/` / `.claude/`, and `TOKENMASTER_KEEP_TOOLS` to keep needed auxiliary tool families
  automatically while pruning unused schemas via `--excluded-tools`.
- **Import-alias resolution in `impact` (`brainspace/symbol_index.py`, `SCHEMA_VERSION = 4`):** `_aliases()` and
  `_Calls` now resolve `import a.b as c` and `from a import b as c` back to the imported symbol or module name
  (excluding shadowed function parameters), enabling `impact("django/contrib/auth/__init__.py::login")` to find
  `auth_login(...)` callers in `django/contrib/auth/views.py` (`D13`) and raising `D01`–`D15` caller recall from
  `54/56` to `56/56`.
- **Out-of-sample `/tokenomics` validation on Copilot CLI `1.0.98` (`docs/TOKENOMICS.md`, `tokenomics.py`):**
  validated the pre-frozen October 23 `1.0.98` calibration against the four PRS-6 runs (`59.0%` to `123.9%` of
  measured token savings and `56.0%` to `103.6%` of measured USD savings).
- **Live demo runbook and interactive HTML deck:** added `docs/DEMO_SCRIPT.md` and `docs/tokenomics-demo-slide.html`.

### Changed

- **Plugin-first `README.md` and Swiss editorial `assets/tokenmaster-hero.svg`:** streamlined `README.md` into a
  concise, scannable guide leading with `copilot plugin install All-The-Vibes/TokenMasterX:token-master-plugin`,
  `/token-master`, and `/tokenomics`, with full experimental protocols and results linked under
  `token-master-plugin/docs/`.
- Bumped plugin and package version metadata to `0.2.0` (`.claude-plugin/marketplace.json`,
  `token-master-plugin/.claude-plugin/plugin.json`, `brainspace/__init__.py`, `package.json`).

### Fixed

- **Legacy cross-platform test failures:** added `token-master-plugin/evals/repository-cases.json -text` to
  `.gitattributes` to preserve its pinned CRLF SHA-256 (`f4ebd67e...`) and added `@pytest.mark.skipif` in
  `tests/test_native_responses.py` when the local October 9 capture file is absent (`4,450 passed, 5 skipped, 0
  non-WSL failures` across all `106` test files, plus `6/6` study `self-test`s).
- **Real-CLI evaluation harness (`run_prs5_study.py`, `quick_copilot_ab.py`, `django_ab.py`):** pinned
  `COPILOT_CLI_DIST_DIR` to the target `CLI_VERSION` package directory, set
  `COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=32000` for Anthropic models on `1.0.98+`, switched `run_prs5_study.reset_lane`
  to `robocopy /MIR`, cached `TEMPLATE_MANIFESTS`, and ignored CRLF-only rewrites via `same_content()` in
  `changed_files()`.

### Correction: the real-CLI runs used Copilot CLI 1.0.78-3, not 1.0.98 — October 23, 2026

- Every real-CLI A/B run, PRS-5 and the bridge checks passed `--no-auto-update`. With that flag, the WinGet
  launcher runs its bundled build, 1.0.78-3, even when the installed 1.0.98 package is present. The harnesses
  recorded `copilot --version` without the flag, which printed 1.0.98. All 403 local session captures from the
  Django runs say "Version number: 1.0.78-3". The documents now say 1.0.78-3. The evidence records that said 1.0.98
  now carry a correction note; the frozen protocol `PRS5_PROTOCOL.md` keeps its text.
- `run_prs5_study.cli_version` now checks the version with the same flags as the sessions. With the October flags,
  the version check stops `django_ab.py` and `quick_copilot_ab.py`, because `CLI_VERSION` names 1.0.98.
- A probe compared the two versions (`evidence/copilot-version-probe-20261023/`). On 1.0.98, stock Copilot CLI's
  first call is smaller (11,083 tokens with `gpt-6-astra`, 18,104 with `claude-opus-5.5`, against 13,507 and
  20,723). The lean tool set still removes about half of it: 5,558 and 9,727 tokens, against 6,775 and 11,552.
  When another 1.0.98 session ran shortly before, stock 1.0.98 read 6,450 and 11,226 tokens from the cache on its
  first call, in both folders tested.
- The bridge makes the system prompt the same only for sessions in the same working folder: the system prompt
  also names that folder. The documents now say so.
- With `claude-opus-5.5`, 1.0.98 asked for 32,000 output tokens and stopped when the provider limit was 16,000
  (`evidence/copilot-version-probe-20261023/opus-1.0.98-output-limit.txt`).
- As of October 23, no A/B run had used 1.0.98 yet (subsequently completed on October 26 in `0.2.0` PRS-6 above).

### `/tokenomics` dashboard for Copilot CLI — October 23, 2026

- New `tokenomics.py`: a ccusage-style report (daily, weekly, monthly, session) of Copilot CLI usage. It reads
  Copilot CLI's own per-call records in `<COPILOT_HOME>/session-store.db`: tokens, cache reads and writes, and
  GitHub's charge for each call. It opens the database read-only, or reads a copy if Copilot CLI holds it.
- It estimates TokenMaster's savings for each TokenMaster call: fewer fixed tokens per call (lean tool set, less the
  navigation tools), and the first call's prompt-cache write against stock's. The estimate assumes the same model
  calls as stock. It uses Copilot CLI 1.0.98 values from the probe. With the 1.0.78-3 values, on the measured A/B
  runs, it gave 72% to 125% of the measured token saving (`evidence/tokenomics-validation-20261023/`). See
  `docs/TOKENOMICS.md`.
- The launcher appends a start and an end record for each Copilot CLI launch to
  `<COPILOT_HOME>/token-master/launches.jsonl` (time in milliseconds, folder, lean tool set, bridge, navigation
  tools; no prompt text). A session counts as TokenMaster only if its first call came during a launch in its folder.
  Before this rule, a stock session that ran up to 5 seconds before a launch in the same folder counted as
  TokenMaster (`evidence/tokenomics-check-20261023/readme-example.txt`).
- `brainspace_setup.py --host copilot` installs `tokenomics.py` and a personal skill,
  `<COPILOT_HOME>/skills/tokenomics/SKILL.md`. Uninstall removes the skill only if TokenMaster wrote it. The skill
  pre-approves no tool: Copilot CLI asks before it runs the command, unless it started with `--allow-all-tools`.
- When a range has no TokenMaster calls, the dashboard prints the launcher command with the full path of its own
  Python. On some Windows machines, `python` on PATH is only the Microsoft Store placeholder.
- Stock's usual first-call cache read now comes from the store's own stock sessions (median per model); the
  calibration value applies only to a model without stock sessions. In a real Copilot CLI 1.0.98 home with default
  GitHub routing, all 6 stock first calls read 0 tokens from the cache, so the calibration's 6,450 had turned two
  measured savings (33% and 41% lower cost) into a small negative estimate. The validation results do not change.
- Live checks (`evidence/tokenomics-check-20261023/`): typed in an interactive session, `/tokenomics` works on
  Copilot CLI 1.0.78-3 and 1.0.98, although the lean tool set removes the `skill` tool. It took 2 model calls,
  16,445 tokens and $0.16 on 1.0.98. The `!` shell form needs no model call. With `-p`, Copilot CLI passes
  `/tokenomics` to the model as text and does not run the skill.

### Real Copilot CLI: 45-task Django run, graphify 0.9.91 and documentation — October 22, 2026

- Documentation now leads with the real Copilot CLI results. The new
  `docs/COPILOT_CLI_RESULTS.md` gives their method, numbers and limits. README, MISSION,
  `docs/COPILOT_BRIDGE.md`, the documentation index, the skill guide and the slide were updated.
  PRS-1 to PRS-4 are now labeled as studies in a replica harness.
- A 45-task Django 5.2 run measured stock Copilot CLI, TokenMaster without graphify and
  full TokenMaster, with `gpt-6-astra` and `claude-opus-5.5` (270 sessions, exploratory). The client was
  Copilot CLI 1.0.78-3; this entry said 1.0.98 until October 23 (see that day's entry).
  - Raw tokens, full TokenMaster against stock: −53.4% (95% CI −57.1% to −49.1%) and −51.6%
    (−55.7% to −47.2%). Fewer raw tokens on all 45 tasks with each model.
  - Cost with sessions back to back: $11.55 → $2.33 (`gpt-6-astra`) and $3.31 → $1.30
    (`claude-opus-5.5`). Re-priced with every first call cold: −49.5% and −46.0%.
  - Correct answers: stock 90/90, each TokenMaster version 88/90. The 4 errors were model errors.
  - Graphify cut a further 15.4% and 9.8% of the raw tokens that TokenMaster without graphify
    used.
  - The tasks were committed before the run (`0516a82`); results `5d27601`.
  - `evidence/django-scale-20261022/analyze.py` gives the confidence intervals and the cold
    re-pricing. `evidence/copilot-lean-analysis-20261022/` does the same for the 27-task run of
    October 19.
- `evidence/django-scale-20261022/audit.py` recounts the run from the committed per-call
  records. Its totals match, and GitHub's own per-call charges add up to the same costs
  (`f3e6c36`).
- `evals/django_ab.py` runs these Django A/Bs (`dd1f38a`). It resets each workspace with
  `robocopy /MIR` and hashes each template once per run (`0516a82`). A reset of the 289 MB
  TokenMaster workspace now takes 0.3 seconds instead of minutes. `--self-test` covers both.
- Graphify was upgraded from 0.9.84 to 0.9.91, the newest version that the company package feed
  served (`35bc10b`). On Django, `impact` found the same 54 of 56 answer-key callers with either
  version. Both versions miss calls through an import alias.
- Two smaller Django runs earlier that day (`dd1f38a`, `d34b5c3`) used 15 of the 45 tasks. The
  45-task run repeated them and supersedes them.

### Lean tool set for Copilot CLI and the first real-CLI A/Bs — October 18–19, 2026

- `setup.py` now adds `graphify-out/` to `.gitignore`. Before, `rg` searched graphify's 9.5 MB
  `graph.json` (`319d1b2`, October 19).
- Without a model, a repository-wide `rg` for "who uses X" printed 128,279 tokens for 40 Django
  symbols; `impact` returned 8,401. For "where is X defined", `rg` printed 992 tokens and
  `locate` returned 2,116 (`319d1b2`). These are raw `rg` outputs; Copilot's search tool shortens
  long results.
- The launcher now applies a lean tool set by default (`981444d`, October 19).
  - It passes `--excluded-tools` for 11 built-in tools that no session called in the October 18
    runs: `session_store_sql`, `task`, `read_agent`, `write_agent`, `list_agents`, `skill`,
    `sql`, `read_powershell`, `stop_powershell`, `list_powershell` and
    `fetch_copilot_cli_documentation`. One later stock session (P13, October 19) called `task`.
  - It skips this when the user passes `--all-tools`, chooses tools, or runs a subcommand.
  - Without a provider URL, it runs Copilot CLI with its normal routing and the lean tool set.
  - In a one-task probe (Copilot CLI 1.0.78-3), the `gpt-6-astra` system prompt fell from 7,216 to
    5,117 tokens, and
    the session from 27,255 to 13,702 raw tokens.
- A 27-task A/B on this repository (`c5681a7`, October 19, exploratory): full TokenMaster used
  44.8% (`gpt-6-astra`) and 53.5% (`claude-opus-5.5`) fewer raw tokens than stock. Cost fell
  62.8% and 51.2% with sessions back to back, and 40.8% and 43.9% with every first call
  re-priced as cold. Passed: stock 27/27 and 27/27; TokenMaster 27/27 and 26/27.
- The bridge also supports Anthropic Messages, because GitHub's API serves `claude-opus-5.5`
  only on Anthropic Messages and Chat Completions (`5524197`, October 18). An A/B before the
  lean tool set raised raw tokens by 7.6% (`gpt-6-astra`) and 2.4% (`claude-opus-5.5`), and
  lowered cost by 14.3% and 19.8%.
- `brainspace_setup.py --host copilot` no longer installs the `brainspace` MCP server
  (`763d451`, October 18). Its 5 tools got no calls in live sessions, and their definitions
  added about 500 tokens to each call. `--brainspace-mcp` installs it; a reinstall removes an
  owned one. The navigation tool descriptions now say which searches and reads they replace.
- PRS-5, a pre-registered real-CLI study (`dec1bb2`, `3f2b5a9`), stopped after 10 of 32
  sessions on October 18. Its partial data are kept as evidence, not as a study result.

### Copilot CLI bridge and a live fix for the v6 hook — October 18, 2026

- New opt-in `brainspace_copilot_bridge.py` runs Copilot CLI in bring-your-own-key mode through
  a local bridge. The bridge applies the cache-stable system prompt and v6 shaping (grep, glob
  and whole-file view results) to every request. Copilot CLI keeps its full tool set. The bridge
  never reads, stores or adds credentials. `brainspace_setup.py --host copilot` installs it.
  See `docs/COPILOT_BRIDGE.md`.
- Live checks with Copilot CLI 1.0.78-3: through the bridge, every later session's first call
  read about 13,400 tokens from the cache. Without the bridge, no first call did. One-line edits
  through the bridge were correct, and an interactive session worked. (Corrected October 23: the
  later checks were labeled 1.0.98, but `--no-auto-update` ran the bundled 1.0.78-3 there too.)
- Fix: Copilot CLI 1.0.78-3 sends the hook's `toolArgs` as a JSON string, so the v6
  `view` hook changed nothing. The hook now parses the string. In live sessions, the model then
  received a 1,799-character digest instead of a 20,112-character view. 1.0.98 was not checked.
- Finding: Copilot CLI refuses plain whole-file views of larger files. It refused a 22.4 KB file
  and a 37.3 KB file. v6 read digests apply only below that limit. In both live hook sessions,
  the model then read the file again with `forceReadLargeFiles`, so the hook saved nothing there.

### Cache-stable system prompt and PRS-4 — October 18, 2026

- The native Copilot route moves Copilot CLI's per-session `Session folder:` line from the
  system prompt to the first user message (`stable_session_prefix` in
  `brainspace/native_transport.py`; transport version `native-responses-transport-v2`).
  - The system prompt is then the same for every session in the same working folder.
  - A new session's first call can then read that prompt from the provider's cache. This
    works only if another session sent the same prompt within the cache lifetime.
  - The rewrite is a no-op when the line is absent or ambiguous. It gives the same bytes on
    every call of a session.
- PRS-4 (pre-registered, 360 live sessions, 24 fresh blind-authored tasks) measured billed
  cost per finished task against stock. Every arm passed 120/120.
  - Under continuous use, v7 with the cache-stable system prompt cost 49.8% less (95% CI
    −57.1% to −42.9%).
  - v7 alone cost 18.2% less.
  - Re-priced as if every first call missed the cache, v7 with the cache-stable system prompt
    cost 18.9% less.
  - See `docs/PRS4_RESULTS.md`.
- In one cache-lifetime probe, the cached prompt was still in the cache after 6.5 minutes. It
  was gone after 31 minutes.

### v6 as the default for Copilot — October 18, 2026

- The native Copilot route (`brainspace_tools.py native-copilot`) now defaults to
  `request-policy-v6`, the configuration measured in PRS-2 and PRS-3. Before, its
  default turned the optimizer off. `--runtime-policy` still overrides it.
- The native transport now keeps the client's `parallel_tool_calls` instead of
  forcing it to `false`; when the client sends no value it defaults to on. Copilot
  CLI sends `true`.
- The Copilot output hook applies `request-policy-v6` to whole-file `view` results
  instead of lossless JSON whitespace compaction. v6 does not compact JSON, and the
  measured v6 configuration did not either.
- `brainspace_setup.py --host copilot` installs the hook by default.
  `--no-copilot-output-hook` skips it. If the user has set `disableAllHooks`, the
  hook is skipped but the MCP server still installs; an explicit
  `--copilot-output-hook` still fails in that case.
- The v6 hook has offline contract tests only. It has not yet had a native Copilot
  CLI lifecycle run.

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
