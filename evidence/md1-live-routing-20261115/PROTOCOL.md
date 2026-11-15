# Live 3-Arm Routing Study: Stock Copilot CLI vs. TokenMaster `--lean` (Regex) vs. TokenMaster `--lean` + MD-1

Pre-registered before session 1 is run. `PROTOCOL.sha256` records the SHA-256 of this file at `prepare` time (`run.py prepare`) and is verified by `analyze.py` before any outcome is tabulated.

## 1. Research Question & Motivation

TokenMaster v0.3.0 (`brainspace_copilot_bridge.py --lean`) removes up to 13 auxiliary built-in tool schemas (`LEAN_EXCLUDED_TOOLS`) from Copilot CLI's prompt prefix by default, keeping capability families only when the user's `-p` prompt triggers a router:

1. **Regex router (`tm_regex`, default when `TOKENMASTER_MD1_ENDPOINT` is unset):** Zero-latency keyword patterns over 7 capability families (`agents`, `session_history`, `background_shell`, `copilot_docs`, `skill`, `workflows`, `sql`).
2. **MD-1 semantic router (`tm_md1`, active when `TOKENMASTER_MD1_ENDPOINT` is set):** Sends 7 binary `Microsoft-Decision-1` policy questions (`MD1_QUESTIONS`, threshold `0.5`) to an Azure AI Foundry serverless deployment before launching Copilot CLI, unioned with explicit slash/named triggers.

Prior repository evidence had two critical gaps:
- **Live CLI A/B studies (`evidence/lean-20261101`, PRS-6)** tested only pure coding tasks (`prs4_tasks.json`, `prs5_tasks.json`) that never needed any of the 13 excluded tools, and ran without MD-1.
- **MD-1 evaluation (`evidence/md1-routing-20261108/md1_routing_eval.json`)** scored 65 static strings offline without launching Copilot CLI, so it never measured end-to-end task completion, behavioral workarounds when a needed tool is stripped, MD-1 wall-clock latency inside real sessions, or live token/credit cost when false-keep traps leak schemas back into the prompt.

This study closes both gaps in a live 3-arm × 3-bucket paired design on **Copilot CLI `1.0.112`**.

## 2. Arms & Isolation

Each arm runs in an isolated lane with neutral directory names (`l1`, `l2`, `l3`) so path lengths and prompt caches are balanced and never leak condition labels into model prompts:

| Arm ID | Lane | Description | Launch Mechanism |
| --- | --- | --- | --- |
| `stock` | `l1` | Unmodified Copilot CLI `1.0.112` (all 21 built-in tools active) | `copilot -p <prompt> ...` |
| `tm_regex` | `l2` | Documented TokenMaster Copilot install (`setup.py --host copilot` + `brainspace_setup.py --host copilot`), regex-only `--lean` | `python brainspace_copilot_bridge.py --lean -- -p <prompt> ...` (`TOKENMASTER_MD1_ENDPOINT` unset) |
| `tm_md1` | `l3` | Identical TokenMaster Copilot install + workspace snapshot to `tm_regex`, with live Azure Foundry `Microsoft-Decision-1` (`Decision-1`) | `python brainspace_copilot_bridge.py --lean -- -p <prompt> ...` (`TOKENMASTER_MD1_ENDPOINT=https://raifoundry.services.ai.azure.com`) |

### Isolation Invariants
- Both `tm_regex` and `tm_md1` lanes are cloned (`robocopy /MIR`) from the **exact same installed TokenMaster template** so `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`, `tokenmaster-nav` (`symbols.sqlite`), and `graphify-out/` are byte-identical prior to every task.
- Before every task, `reset_lane()` restores the lane's `work` tree from its clean template (`git status --porcelain == ""`) and clears `<home>/copilot/{session-store.db*,session-state,logs,command-history-state.json}` plus `<home>/copilot/token-master/launches.jsonl`.
- Every session runs with `--model gpt-6-astra --reasoning-effort low --disable-builtin-mcps --allow-all-tools --no-ask-user --output-format json --secret-env-vars=GH_TOKEN,GITHUB_TOKEN,COPILOT_GITHUB_TOKEN`, with `COPILOT_CLI_DIST_DIR` pinned to each lane's isolated `1.0.112` package (`copilotVersion == "1.0.112"` verified on all 45 sessions in `analyze.py`).
- For `tm_md1`, `<home>/copilot/token-master/md1-token.json` is refreshed by the parent harness before each session (since isolated lanes have an allowlisted `PATH` without `az` or `~/.azure`) and deleted immediately when the study finishes so no bearer token remains on disk.
- No prompt in `tasks.json` was probed against `Microsoft-Decision-1` prior to freezing `PROTOCOL.sha256`.

## 3. Task Design: 3 Buckets × 5 Tasks = 15 Paired Tasks (45 Live Sessions)

All 15 tasks execute against a clean snapshot of `All-The-Vibes/TokenMasterX` at commit `f9750ff`:

### Bucket A (`A01`–`A05`): Pure Repository Coding & Editing (0 auxiliary tools needed, 0 regex trigger words)
- `A01` (`investigate`): Multi-module audit of `brainspace/symbol_index.py` + `navigation_mcp.py`.
- `A02` (`investigate`): Control-flow and budget audit of `brainspace/v6_shaping.py`.
- `A03` (`investigate`): Invariant audit of `brainspace/exact_reuse.py` + `brainspace/token_ledger.py`.
- `A04` (`edit`): Implement public `has_exact_reuse_marker(text)` validator in `brainspace/exact_reuse.py` + unit tests in `tests/test_exact_reuse.py`.
- `A05` (`edit`): Implement `--limit N` CLI row-cap option in `tokenomics.py` preserving full-dataset totals + unit tests in `tests/test_tokenomics.py`.

### Bucket B (`B01`–`B05`): Natural-Language Multi-Capability Tasks (1 auxiliary group genuinely needed per task, phrased naturally with 0 regex trigger matches)
- `B01` (`agents` -> `task` / `read_agent`): Delegate independent audits of `symbol_index.py` and `v6_shaping.py` across two separate helper workers and merge their findings.
- `B02` (`session_history` -> `session_store_sql`): Recall an agreed HTTP header contract from Tuesday's seeded conversation in `<home>/copilot/session-store.db` (`3` seeded prior sessions, `0` usage events).
- `B03` (`background_shell` -> `powershell(mode="async")` + `read_powershell` / `stop_powershell`): Start a persistent local loopback TCP echo listener bound to ephemeral port `0`, read its bound port and probe it twice from separate client checks (`alpha`, `tokenmaster`), and leave the port freed on completion.
- `B04` (`copilot_docs` -> `fetch_copilot_cli_documentation`): Query Copilot CLI's own environment variable reference (`COPILOT_GH_HOST`, `USE_TGREP_WARM_START`, `COPILOT_AUTO_TIER` profiles).
- `B05` (`sql` -> `sql`): Load all `test_headroom_*.py` test counts into `headroom_suite(file_name, def_test_count)` in the built-in SQLite session database and aggregate via SQL.

### Bucket C (`C01`–`C05`): Adversarial Lookalike Coding Tasks (0 auxiliary tools needed, natural code prompts containing regex trap words)
- `C01` (`investigate`, traps: `workflow`, `workflows`, `skill`, `agent`): Audit `CAPABILITY_GROUPS["workflows"]`, `skill` group implications, `LEAN_EXCLUDED_TOOLS`, and `MD1_THRESHOLD` in `brainspace_copilot_bridge.py`.
- `C02` (`investigate`, traps: `previous sessions`, `session-store`): Audit `STARTUP`, `LAUNCH_TIMEOUT`, `CLI_VERSION`, `LEAN_WEIGHTS["session_store_sql"]`, and `open_readonly` in `brainspace_copilot_bridge.py` + `tokenomics.py`.
- `C03` (`investigate`, traps: `in the background`, `run a sql query`): Audit `_SCHEMA` tables/indexes, `MAX_ECHO`, and lazy locked initialization in `symbol_index.py` + `navigation_mcp.py`.
- `C04` (`investigate`, traps: `copilot cli settings`, `subagent`): Audit `config_lock` / `transaction` suffixes, lock timeout, `TOKENOMICS_MARKER`, and default `brainspace_mcp` host behavior in `hosts/config.py` + `brainspace_setup.py`.
- `C05` (`edit`, traps: `workflow`, `session-store`, `subagents`): Implement `--min-calls N` session filter in `tokenomics.py` + unit tests in `tests/test_tokenomics.py`.

## 4. Pre-Registered Endpoints & Hypotheses

### Co-Primary Endpoints (across all `n = 15` tasks, pairwise comparisons: `tm_md1 vs stock`, `tm_regex vs stock`, `tm_md1 vs tm_regex`)
1. **Task pass rate (`passed`):** Objective ground-truth JSON match + clean working tree for `investigate`/`capability` tasks; `allowed_paths` discipline + independent `pytest` check pass for `edit` tasks (plus port-free check for `B03`). Note: **task pass grades objective task outcome, NOT whether a specific tool was called**, so `tm_regex` is credited fairly whenever the model succeeds via a shell/Python workaround!
2. **Cold-start token cost (`cold_usd`):** Exact per-call `token_details_json` rates from `session-store.db`, repricing every session's call 0 prefix (`cache_read + cache_write`) at `cache_write` rate (`nano_cold`), removing cross-session prompt-cache order effects.
3. **Raw billed token total (`raw_tokens`):** `input_tokens + output_tokens` summed across all `assistant_usage_events` in the session (including any spawned subagent calls!).

### Secondary / Diagnostic Endpoints (Bucket-Stratified)
1. **Target-Capability Tool Compliance (`target_tool_used` on Bucket B, `n = 5`):** Fraction of Bucket B tasks where the session actually invoked the intended built-in capability tool (`task` for `B01`, `session_store_sql` for `B02`, `read_powershell`/`stop_powershell` or `mode="async"` for `B03`, `fetch_copilot_cli_documentation` for `B04`, `sql` for `B05`) vs. falling back to `powershell` workarounds (`shell_workaround`).
2. **False-Keep Leak Rate (`false_keep_tools` on Bucket C, `n = 5`):** Number of unneeded auxiliary tools left enabled per launch (`13 - len(excluded)` from `launches.jsonl`) and measured `tool_tokens + tool_instructions` from Copilot CLI `1.0.112`'s `promptCacheBreakState` telemetry.
3. **As-run billed cost (`billed_usd`), wall-clock session duration (`seconds`), and MD-1 pre-launch routing overhead (`md1_ms`).**

### Pre-Registered Hypotheses
- **H1 (Prompt-prefix compression on coding tasks, Buckets A + C):** Both `tm_regex` and `tm_md1` materially reduce `tool_tokens + tool_instructions` and `raw_tokens` / `cold_usd` relative to `stock` without degrading task pass rate.
- **H2 (Semantic recall & workaround elimination on Bucket B):** `tm_regex` strips needed tools on `5/5` Bucket B tasks (`0%` routing recall), forcing shell workarounds or degraded compliance (`B01` cannot spawn native subagents; `B05` cannot populate the in-session `sql` database), whereas `tm_md1` restores the needed capability family on natural-language prompts (`>= 80%` routing recall).
- **H3 (Adversarial lookalike precision & additive-union audit on Bucket C):** `tm_regex` suffers false-positive tool keeps on `5/5` Bucket C tasks due to literal keyword collisions in code-inspection/editing prompts, measurably inflating `tool_tokens + tool_instructions` relative to Bucket A. Because `v0.3.0`'s `select_excluded_tools` unions regex matches with `md1_families` (`regex | md1`), we test both: (a) whether standalone `Microsoft-Decision-1` (`md1_only_kept_groups`) rejects the lookalike traps that fool regex, and (b) the exact live token/cost penalty caused by `v0.3.0`'s additive union keeping regex false positives even when MD-1 scores `< 0.5`.

## 5. Statistical & Audit Rules

- **Audit Gate (`analyze.py`):** Verifies `PROTOCOL.sha256`, exact `n = 15` task pairings across all 3 arms (`45` sessions), zero exit failures unless recorded as task failures, valid `token_details_json` billing reconciliation (`<= 1%` rounding tolerance on every call), and `launches.jsonl` attribution for all `30` TokenMaster sessions (`15 tm_regex + 15 tm_md1`).
- **Paired Inference:** 10,000-draw paired bootstrap (`random.Random(20261022)`) for mean differences and ratios (`95%` percentile CIs), paired with exact two-sided Wilcoxon signed-rank p-values and Holm-Bonferroni multiplicity adjustment across the three pairwise arm comparisons.
