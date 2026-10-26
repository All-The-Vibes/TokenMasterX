# PRS-6 protocol (pre-registered: Copilot CLI 1.0.98)

Written and committed on October 26, 2026, before any PRS-6 study call. All October 18–22 real-CLI
runs used Copilot CLI `1.0.78-3` because passing `--no-auto-update` to the Windows WinGet
`copilot.exe` launcher selects its bundled `1.0.78-3` build even when `1.0.98` is installed.
PRS-6 tests the current TokenMaster install on real **GitHub Copilot CLI `1.0.98`** across both
`gpt-6-astra` and `claude-opus-5.5`.

## Question

On the real GitHub Copilot CLI `1.0.98`, how many raw tokens and how much cold-repriced and as-run
cost does the documented TokenMaster install save across `gpt-6-astra` and `claude-opus-5.5` without
reducing task pass counts?

## Arms

| Arm | Definition |
| --- | --- |
| `stock` | GitHub Copilot CLI `1.0.98` (`GitHub Copilot CLI 1.0.98.`), default agent, no TokenMaster component. |
| `tm` | GitHub Copilot CLI `1.0.98` after the documented install (`setup.py --host copilot` and `brainspace_setup.py --host copilot`), launched through `brainspace_copilot_bridge.py`: lean tool set (`--excluded-tools` removing the 11 unused built-in tools), `tokenmaster-nav` MCP server (`locate`, `read_symbol`, `impact` on Graphify `0.9.91` + SQLite `SCHEMA_VERSION = 4` with import-alias resolution), v6 `view` hook, and BYOK bridge (`stable_session_prefix` + one-shot v6 tool-result shaping). |

Both arms use:

- Real `copilot.exe` pinned to `1.0.98` via `COPILOT_CLI_DIST_DIR` in an isolated per-arm `HOME` /
  `LOCALAPPDATA` / `COPILOT_HOME`, verified before the first session by `run_prs5_study.cli_version`
  (`GitHub Copilot CLI 1.0.98.`).
- Non-interactive mode (`-p`) with `--model <model> --reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps --output-format json`.
- Offline BYOK routing (`COPILOT_OFFLINE=true`, `COPILOT_PROVIDER_BASE_URL`) through the local
  recording relay (`run_prs5_study.Relay`), which adds the GitHub Copilot credential in memory and
  records every request and response unchanged.
- Models and wire formats:
  - `gpt-6-astra` over OpenAI Responses (`COPILOT_PROVIDER_MAX_PROMPT_TOKENS=200000`,
    `COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=16000`).
  - `claude-opus-5.5` over Anthropic Messages (`COPILOT_PROVIDER_MAX_PROMPT_TOKENS=200000`,
    `COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=32000`, required by Copilot CLI `1.0.98`).
- Before each session, the harness resets the lane with `robocopy /MIR` from the arm's read-only
  template and clears Copilot CLI's `session-state` and `session-store.db*`.

## Tasks and design

1. **Primary confirmatory benchmark (this repository, snapshot `703aa20`):**
   - **29 tasks per model:** all 24 PRS-4 tasks (`P01`–`P24`: locate 6, logic 6, impact 4, docs 4,
     edit 4) plus 5 heavy PRS-5 tasks (`H01`, `H02`, `H03`, `H05`, `H06`: 3 investigate, 2 multi-file
     edits).
   - **Schedule:** 1 run per task, arm, and model (`29 x 2 x 2 = 116` sessions), split into two
     shards per model (`shard-a`: `P01`–`P12,H01,H02`; `shard-b`: `P13`–`P24,H03,H05,H06`), shuffled
     with seed `20261019` (`SEED + 1`), running `stock` and `tm` concurrently in each shard.
   - **Workload floor:** at least `2,000,000` raw tokens in the `stock` arm per model across the 29
     graded tasks.
   - **Grading:** `investigate` tasks require an exact JSON match and zero repository file content
     changes. `edit` tasks run their AST/file check (`P21`–`P24`) or executable test check (`H03`,
     `H06`) in an isolated home and fail if any file with changed content (`same_content` ignoring
     CRLF-only rewrites) lies outside `allowed_paths`.
2. **Django 5.2 caller replication (`D01`–`D15`, commit `9e7cc2b6`):**
   - **15 caller tasks per model** (`D01`–`D15` from `evidence/django-impact-20261019/tasks.json`,
     including `D13` where `django.contrib.auth.login` is imported as `auth_login`), `stock` vs full
     `tm` (`15 x 2 x 2 = 60` sessions), testing `1.0.98` and `SCHEMA_VERSION = 4` import-alias
     resolution on a 2,818-file codebase.

## Endpoints and statistics

- **Co-primary endpoints (tested separately for `gpt-6-astra` and `claude-opus-5.5` on the 29-task
  primary benchmark):**
  1. **Raw tokens:** `input + output` tokens summed over all model calls of each session, recounted
     from `captures.jsonl`.
  2. **Cold-repriced USD cost:** per-session cost at GitHub's published prices (`gpt-6-astra`:
     `$10 / $1 / $12.50 / $50` per 1M tokens for uncached input, cache read, cache write, output;
     `claude-opus-5.5`: `$4 / $0.20 / $5 / $20` per 1M), with every session's first call repriced as
     cold (`first_call.cached` moved from cache-read to cache-write).
- **Secondary endpoints:** as-run back-to-back USD cost (verified against GitHub's per-call
  `copilot_usage` / `total_nano_aiu`), model calls, warm starts, `tokenmaster-nav` calls, and task
  pass counts.
- **Inference:** paired ratio of sums (`tm / stock - 1`) with a 10,000-resample paired bootstrap 95%
  CI (`seed = 20261022`) and an exact two-sided Wilcoxon signed-rank test on per-task differences,
  with Holm-Bonferroni correction across the 2 co-primary endpoints per model (`alpha = 0.05`).
