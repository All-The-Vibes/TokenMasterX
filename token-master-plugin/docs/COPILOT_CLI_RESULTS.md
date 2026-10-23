# Real Copilot CLI results (October 18–22, 2026)

These runs used the real GitHub Copilot CLI and GitHub's Copilot API. The client was Copilot CLI
1.0.78-3, the bundled build of the WinGet launcher, not the installed 1.0.98 that this page named
until October 23, 2026 ([Copilot CLI version](#copilot-cli-version)). The runs are exploratory: no
protocol was pre-registered. The pre-registered studies PRS-1 to PRS-4 used a Copilot-CLI-shaped
harness instead, with a fixed prompt of about 3,600 tokens ([PRS4_RESULTS.md](PRS4_RESULTS.md)).

## Summary

- **Django, 45 "who calls X?" tasks:** full TokenMaster used 53.4% fewer raw tokens than stock
  Copilot CLI with `gpt-6-astra` (95% CI −57.1% to −49.1%). With `claude-opus-5.5`, it used
  51.6% fewer (95% CI −55.7% to −47.2%). It used fewer raw tokens on all 45 tasks with each model.
- **Cost at GitHub's prices depends on how close together the sessions run:**
  - As run, with sessions back to back: 79.9% lower (`gpt-6-astra`) and 60.8% lower
    (`claude-opus-5.5`).
  - Re-priced as if every session started with a cold cache: 49.5% and 46.0% lower.
  - Read [How to read the cost numbers](#how-to-read-the-cost-numbers) before you quote a cost
    saving.
- **Correct answers:** stock 90 of 90; full TokenMaster 88 of 90.
- **This repository, 27 tasks:** full TokenMaster used 44.8% fewer raw tokens with `gpt-6-astra`
  and 53.5% fewer with `claude-opus-5.5`.
- **Where the saving comes from:** most of it came with the lean tool set. On Django, graphify
  navigation cut a further 15.4% (`gpt-6-astra`) and 9.8% (`claude-opus-5.5`) of the raw tokens
  that TokenMaster without graphify used. That is 8.5 and 5.3 percentage points of stock's tokens.
- **Copilot CLI version:** all these runs used 1.0.78-3. On 1.0.98, a probe found a smaller fixed
  prompt, but the lean tool set still removed about half of the first call. No A/B run has used
  1.0.98 yet ([Copilot CLI version](#copilot-cli-version)).

## Test parameters

| Parameter | Django run | Repository run |
| --- | --- | --- |
| Session start times | October 23, 2026, 03:10–03:47 UTC (October 22, 22:10–22:47 local time, UTC−5) | October 19, 2026, 19:38–19:45 UTC (14:38–14:45 local time) |
| Client | Copilot CLI 1.0.78-3, the real binary: the WinGet launcher's bundled build, which `--no-auto-update` selects. The installed package was 1.0.98 ([Copilot CLI version](#copilot-cli-version)). | Same |
| Models and API format | `gpt-6-astra` over OpenAI Responses; `claude-opus-5.5` over Anthropic Messages | Same |
| Copilot CLI command | `copilot -p <task> --model <model> --reasoning-effort low --allow-all-tools --no-ask-user --no-auto-update --disable-builtin-mcps --output-format json`. The TokenMaster versions ran the same command through the launcher, which adds `--excluded-tools` (the lean tool set). Every version ran with Copilot CLI's built-in MCP servers off. | Same |
| Routing | Offline bring-your-own-model mode (`COPILOT_OFFLINE=true`, `COPILOT_PROVIDER_BASE_URL`). Copilot CLI sent each request to a local evaluation relay. The relay forwarded it unchanged to `api.githubcopilot.com`. Provider limits: 200,000 prompt tokens and 16,000 output tokens. | Same |
| Repository | Django 5.2, `git archive` of commit `9e7cc2b6`; 2,818 Python files | This repository, snapshot `703aa20` |
| Tasks | 45 questions of the form "Which non-test functions or methods call X directly?": 25 rare names, 20 common names | 27: P01–P24 (locate 6, logic 6, impact 4, docs 4, edit 4), plus H02 and H05 (questions) and H03 (edit) |
| Versions | Stock; TokenMaster without graphify; full TokenMaster | Stock; full TokenMaster |
| Graphify | 0.9.91 | 0.9.84 |
| Runs per task and version | 1 | 1 |
| Sessions | 270 | 108 |
| Order | One shuffled task order (seed 20261019), the same for every version | Two halves of 13 and 14 tasks; one shuffled order per half (seed 20261020), the same for both versions |
| Concurrency and timing | 4 processes at the same time: for each model, one with stock and full TokenMaster in parallel, one with TokenMaster without graphify. Within each version, sessions ran back to back. | 4 processes at the same time: one per model and half, each with stock and full TokenMaster in parallel. Sessions ran back to back. |
| Session limits | 1,500-second timeout; one re-run for each infrastructure failure. No session needed one. | Same |
| Isolation | Each version had its own Copilot home and profile. Each session started from a fresh copy of the repository, with Copilot's session history cleared. No Python was on the agents' PATH. | Same |
| Grading | The JSON answer must list exactly the answer-key callers (paths normalized, order ignored). Any file change fails the task. | Questions: the same rule. Edits: in P-tasks, each edited file must match the expected file (Python files by syntax tree); H03 runs its own check script. Any change outside the allowed files fails. |
| Raw tokens | Input plus output tokens, as GitHub's API reported them | Same |
| Cost | GitHub's prices per 1M tokens. `gpt-6-astra`: $10 new input, $1 cached input, $12.50 cache write, $50 output. `claude-opus-5.5`: $4, $0.20, $5 and $20. | Same |
| Statistics | Paired bootstrap over tasks, 10,000 resamples, seed 20261022 | Same |

Definitions:
- **Stock:** Copilot CLI with no TokenMaster component.
- **TokenMaster without graphify:** `brainspace_setup.py --host copilot` only. Copilot CLI started
  through the TokenMaster launcher ([COPILOT_BRIDGE.md](COPILOT_BRIDGE.md)). It had the lean tool
  set, and the bridge applied the cache-stable system prompt and v6 shaping.
- **Full TokenMaster:** the same, plus `setup.py`. That step builds the graphify graph and installs
  the `tokenmaster-nav` server (`locate`, `read_symbol`, `impact`).
- **Evaluation relay:** it added the GitHub Copilot credential to each request. It recorded
  GitHub's usage counts and GitHub's own charge (`copilot_usage`) for each call. TokenMaster does
  not ship it.

For the Django run, a separate recount from the raw per-call records gave the same token totals.
GitHub's own per-call charges added up to the same costs.

## Copilot CLI version

The real-CLI runs on this page used Copilot CLI **1.0.78-3**. Until October 23, 2026, this page said
1.0.98. That was wrong.

- The harness passed `--no-auto-update`. With that flag, the WinGet launcher runs its bundled build,
  1.0.78-3, even when a newer package is installed. Without the flag, it runs the newest installed
  package, 1.0.98.
- The harness checked the version with `copilot --version`, without the flag. That printed 1.0.98.
- Copilot CLI writes its version into its own system prompt. All 403 local session captures from the
  Django runs of October 19 and 22 say "Version number: 1.0.78-3". The repository run, PRS-5 and the
  bridge checks of October 18–19 used the same flag.
- The harness now checks the version with the same flags as its sessions (`cli_version` in
  `evals/run_prs5_study.py`). With the October flags, the check stops the harness, because
  `CLI_VERSION` names 1.0.98.

A probe on October 23 sent one short prompt per model, version and tool set
(`evidence/copilot-version-probe-20261023/`):

| Model | Copilot CLI | Stock first call | Lean tool set first call | Removed by the lean tool set |
| --- | --- | ---: | ---: | ---: |
| `gpt-6-astra` | 1.0.78-3 | 13,507 | 6,732 | 6,775 (50.2%) |
| `gpt-6-astra` | 1.0.98 | 11,083 | 5,525 | 5,558 (50.1%) |
| `claude-opus-5.5` | 1.0.78-3 | 20,723 | 9,171 | 11,552 (55.7%) |
| `claude-opus-5.5` | 1.0.98 | 18,104 | 8,377 | 9,727 (53.7%) |

- On both versions, the lean tool set removes the same 11 tools: 16 tools become 5 with
  `gpt-6-astra`, and 17 become 6 with `claude-opus-5.5`. It removes about half of the first call.
- On 1.0.98, stock first calls can read part of the prompt from GitHub's cache. When another 1.0.98
  stock session ran shortly before, they read 6,450 tokens (`gpt-6-astra`) and 11,226
  (`claude-opus-5.5`), in both folders tested. On 1.0.78-3, stock `gpt-6-astra` first calls read
  nothing. So the bridge saves less on 1.0.98.
- The bridge makes a new session warm only in the same working folder. On 1.0.98, a TokenMaster
  session in the same folder as the one before wrote 99 tokens (`gpt-6-astra`) and 207
  (`claude-opus-5.5`) to the cache on its first call. In another folder, it wrote 2,874 and 4,034.
  Stock sessions after another stock session wrote about 4,632 and 6,879.
- With `claude-opus-5.5`, 1.0.98 asked for 32,000 output tokens and stopped when the provider limit
  was 16,000, the value of the October runs
  (`evidence/copilot-version-probe-20261023/opus-1.0.98-output-limit.txt`). The probe used 32,000.
- No A/B run has used 1.0.98. The savings on this page are for 1.0.78-3.

## How to read the cost numbers

- **Raw tokens do not depend on timing.** Cost does, because GitHub's prompt cache prices tokens
  differently.
  - `gpt-6-astra`: a cache read costs 0.1× and a cache write 1.25× the price of new input.
  - `claude-opus-5.5`: a cache read costs 0.05× and a cache write 1.25×.
- **In these runs, sessions ran back to back.** A new session could read an earlier session's
  prompt from GitHub's cache if the prompt was identical.
  - Stock Copilot CLI 1.0.78-3 writes each session's folder into its system prompt. With
    `gpt-6-astra`, no stock first call read from the cache (0 of 45 in the Django run). Each stock
    session wrote its prompt to the cache again, at 1.25×. Those first-call writes cost $7.65 of
    the $11.55 stock total; all stock cache writes cost $9.33.
  - The TokenMaster bridge moves the session-folder line, so every session in the same working
    folder sends the same prompt. The system prompt also names the working folder, and the bridge
    leaves that line in place. In the Django run, all sessions of a version used the same folder.
    In each TokenMaster version, 44 of 45 `gpt-6-astra` first calls read the prompt from the cache.
  - With `claude-opus-5.5`, 44 of 45 stock first calls also read part of the prompt from the
    cache, because Anthropic's layout puts the tool definitions before the system prompt. Stock
    first calls still wrote the system prompt to the cache: a median of 7,474 tokens. Full
    TokenMaster first calls wrote a median of 314. No run isolated the bridge's own effect with
    `claude-opus-5.5`.
- **A cached prompt does not last.** One probe found it still there after 6.5 minutes and gone
  after 31 minutes. Sessions that start further apart start cold.
- **The cold re-pricing** treats every first call as a cache miss. The tokens that the first call
  read from the cache are re-priced as cache writes. It applies to every version.
- **The bridge runs only in bring-your-own-model mode.** With Copilot CLI's default GitHub routing,
  the cache-stable system prompt does not apply. No run measured that configuration.

| Cost, full TokenMaster vs stock (95% CI) | `gpt-6-astra` | `claude-opus-5.5` |
| --- | ---: | ---: |
| Django, as run | −79.9% (−82.0%, −77.6%) | −60.8% (−64.6%, −56.9%) |
| Django, every first call cold | −49.5% (−51.5%, −47.5%) | −46.0% (−48.0%, −44.0%) |
| Repository, as run | −62.8% (−71.3%, −54.6%) | −51.2% (−59.2%, −43.0%) |
| Repository, every first call cold | −40.8% (−47.1%, −34.6%) | −43.9% (−48.2%, −39.7%) |

Inference: for sessions that start far apart, the cold rows are the better estimate. They are
close to the raw-token saving.

## Result 1: 45 "who calls X?" tasks on Django 5.2 (October 22)

- **Task:** "We're about to change the signature of X. Which non-test functions or methods
  call it directly?"
  - The answer keys come from Django's syntax trees. Calls are resolved through each file's
    imports.
  - 25 tasks use rare names. 20 tasks use common names: for these, a repository-wide
    `rg -n -w <name>` returns 2,496 to 507,193 tokens.
  - The tasks were committed before the run (`0516a82`). We checked 10 answer keys by hand
    against `rg` (D04, D11–D15, D31, D32, D33 and D45). For every failed answer, the other
    versions passed with the same key.

| 45 tasks per model | Stock | TokenMaster without graphify | Full TokenMaster |
| --- | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,417,452 | 1,331,990 (−44.9%) | **1,127,277 (−53.4%)** |
| `gpt-6-astra` cost, as run | $11.55 | $3.37 (−70.8%) | **$2.33 (−79.9%)** |
| `gpt-6-astra` cost, every first call cold | $11.55 | $6.74 (−41.6%) | **$5.83 (−49.5%)** |
| `claude-opus-5.5` raw tokens | 3,457,179 | 1,855,563 (−46.3%) | **1,673,646 (−51.6%)** |
| `claude-opus-5.5` cost, as run | $3.31 | $1.48 (−55.2%) | **$1.30 (−60.8%)** |
| `claude-opus-5.5` cost, every first call cold | $6.14 | $3.39 (−44.8%) | **$3.31 (−46.0%)** |
| Correct answers, both models | 90/90 | 88/90 | 88/90 |

Change in raw tokens (95% CI):

| Comparison | `gpt-6-astra` | `claude-opus-5.5` |
| --- | ---: | ---: |
| Full vs stock | −53.4% (−57.1%, −49.1%) | −51.6% (−55.7%, −47.2%) |
| Without graphify vs stock | −44.9% (−49.7%, −39.1%) | −46.3% (−50.9%, −40.8%) |
| Full vs without graphify | −15.4% (−21.7%, −8.1%) | −9.8% (−18.4%, −0.8%) |
| Full vs without graphify, rare names | −22.5% (−29.6%, −14.6%) | +1.8% (−6.5%, +10.1%) |
| Full vs without graphify, common names | −8.1% (−17.3%, +2.9%) | −20.4% (−32.6%, −6.0%) |

Observations:

- Full TokenMaster used fewer raw tokens than stock on 45 of 45 tasks, with each model.
- Graphify reduced the number of model calls: 162 to 143 (`gpt-6-astra`) and 174 to 150
  (`claude-opus-5.5`).
- The models used the navigation tools in 45 of 45 (`gpt-6-astra`) and 26 of 45
  (`claude-opus-5.5`) full-TokenMaster sessions.
- Search output, counted once for each request that re-sent it, was 7.2% of stock
  `gpt-6-astra` tokens and 2.0% of stock `claude-opus-5.5` tokens.
- For `format` (D31), a bare repository-wide `rg` returns 507,193 tokens. The whole stock session
  used 58,880 (`gpt-6-astra`) and 89,408 (`claude-opus-5.5`) tokens. The local captures show why:
  the models searched for `dateformat` rather than `format`, limited searches to single files,
  or asked for file names only. Copilot's search tool also limits the length of its results.
- The 4 wrong answers were model errors:
  - D28, full, `gpt-6-astra`: named the public `changeform_view` and `delete_view` instead of
    the private methods that make the call.
  - D45, without graphify, `gpt-6-astra`: left out 4 admin callers.
  - D06, without graphify, `claude-opus-5.5`: named `_as_sql` instead of `as_sql`.
  - D45, full, `claude-opus-5.5`: added `smart_urlquote`, which calls the standard library's
    `urlencode`.

Evidence: `evidence/django-scale-20261022/` (`tasks.json`, `summary.json`, `analysis.json`,
`audit.json`, per-session `results.jsonl`, per-call `calls.jsonl`). Commits `0516a82`,
`5d27601` and `f3e6c36`.

Two smaller Django runs earlier on October 22 used 15 of these tasks with graphify 0.9.84
(`dd1f38a`, `d34b5c3`). The 45-task run repeated those 15 tasks and supersedes them.

## Result 2: 27 tasks on this repository (October 19)

- **Tasks:** the 24 PRS-4 tasks P01–P24, which no real-CLI run had used before, plus the heavier
  PRS-5 tasks H02, H03 and H05.

| 27 tasks per model | Stock | Full TokenMaster |
| --- | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,404,853 | **1,326,925 (−44.8%; 95% CI −52.6% to −37.4%)** |
| `gpt-6-astra` cost, as run | $9.05 | **$3.37 (−62.8%)** |
| `gpt-6-astra` cost, every first call cold | $9.05 | **$5.36 (−40.8%)** |
| `claude-opus-5.5` raw tokens | 3,048,966 | **1,419,061 (−53.5%; 95% CI −58.8% to −48.3%)** |
| `claude-opus-5.5` cost, as run | $2.75 | **$1.34 (−51.2%)** |
| `claude-opus-5.5` cost, every first call cold | $4.49 | **$2.52 (−43.9%)** |
| Passed | 27/27 and 27/27 | 27/27 and 26/27 |

- Full TokenMaster used fewer raw tokens on 27 of 27 tasks (`gpt-6-astra`) and 26 of 27
  (`claude-opus-5.5`).
- Warm first calls: `gpt-6-astra` stock 0 of 27, TokenMaster 25 of 27; `claude-opus-5.5` stock 27
  of 27, TokenMaster 26 of 27.
- The one failure (H03, `claude-opus-5.5`) rewrote one extra file with CRLF line endings and no
  content change. The grader fails any change outside the allowed paths.
- In P13, stock `gpt-6-astra` called `task`, one of the 11 tools that the lean tool set removes.
  It started a subagent. The stock session used 124,403 raw tokens in 8 calls; TokenMaster used
  38,154 in 4 calls. Both passed.
- The confidence intervals were recomputed on October 22 with the bootstrap in the parameter
  table (`evidence/copilot-lean-analysis-20261022/`). Commit `c5681a7` reported slightly different
  intervals from an earlier, quicker computation.

Evidence: `evidence/copilot-lean-{astra,opus}-{a,b}-20261019/`. Commit `c5681a7`.

## Why the saving happens

- **Fixed overhead dominates.** Copilot CLI re-sends its system prompt and tool definitions on
  every model call. In the Django run, a stock first call sent 13,605 (`gpt-6-astra`) and
  20,871 (`claude-opus-5.5`) input tokens (medians).
- **The lean tool set removes 11 built-in tools.** No session called them in the October 18 runs,
  from which the list was chosen. Their definitions and the system-prompt text about them leave
  every call. One later stock session called `task` (P13, above). The 11 tools are
  `session_store_sql`, `task`, `read_agent`, `write_agent`, `list_agents`, `skill`, `sql`,
  `read_powershell`, `stop_powershell`, `list_powershell` and `fetch_copilot_cli_documentation`.
  - A probe ran one lookup task per model on October 19. The tools sent fell from 16 to 5
    (`gpt-6-astra`) and from 17 to 6 (`claude-opus-5.5`).
  - The system prompt fell from 7,216 to 5,117 cl100k tokens (`gpt-6-astra`) and from 5,931 to
    3,833 (`claude-opus-5.5`).
  - The session used 27,255 → 13,702 and 42,544 → 19,434 raw tokens. Both answers were
    correct. One task per model shows the mechanism, not an average
    (`evidence/lean-tools-20261019/`).
- **Graph navigation saves model calls.** `impact` answers "who calls X" in one compact result.
  Each call that it saves would have re-sent at least the fixed overhead. With TokenMaster, a
  first call sent a median of 7,097 (`gpt-6-astra`) and 9,862 (`claude-opus-5.5`) input tokens.
- **The cache-stable system prompt lowers cost, not raw tokens.** See
  [How to read the cost numbers](#how-to-read-the-cost-numbers). It explains why the as-run cost
  saving with `gpt-6-astra` is larger than its raw-token saving.

## Grep and graph lookups without a model (October 19)

A script compared the tokens that each lookup returns, with no model calls. It sampled 40
random functions and classes per repository. It ran Copilot CLI's own `rg` and counted cl100k
tokens.

| Question | Repository | Raw `rg` output | Graph tool |
| --- | --- | ---: | ---: |
| Who uses X? | This repository (162 Python files) | 20,282 | `impact` 12,792 |
| Who uses X? | Django 5.2 (2,818 Python files) | 128,279 | `impact` 8,401 |
| Where is X defined? | Django 5.2 | 992 | `locate` 2,116 |

- The largest single Django `rg` output was 115,555 tokens. The largest `impact` result was
  2,325.
- These are raw `rg` outputs. Copilot's search tool shortens long results, and the models in the
  real CLI searched with narrower patterns (Result 1). So this table measures lookup output,
  not session cost.
- The same commit fixed a setup gap. `setup.py` left graphify's 9.5 MB `graphify-out/graph.json`
  visible to `rg`. Setup now adds `graphify-out/` to `.gitignore`.

Evidence: `evidence/grep-vs-graph-20261019/`. Commit `319d1b2`.

## Graphify version check (October 22)

- Graphify was upgraded from 0.9.84 to 0.9.91. That was the newest version that the company
  package feed served. PyPI was not reachable directly, and the feed did not yet serve 0.9.92
  to 0.9.94.
- On the same Django commit, 0.9.91 built 50,858 nodes and 120,650 links, 33,094 of them calls.
  0.9.84 built 50,879 nodes and 118,194 links, 31,715 of them calls.
- With either version, `impact` found 54 of the 56 answer-key callers for tasks D01–D15.
- Both versions miss calls through an import alias. In D13, `login` is imported as
  `auth_login`.

Evidence: `evidence/graphify-upgrade-20261022/`. Commit `35bc10b`.

## Earlier exploratory runs (October 18)

These runs came before the lean tool set. TokenMaster then saved cost, but not reliably raw
tokens. Their costs are as run, with sessions back to back.

| Commit | Tasks | Model | Raw tokens | Cost | Passed (stock, TokenMaster) |
| --- | --- | --- | ---: | ---: | --- |
| `763d451` | H01, H04, H06, H07, H08 × 2 | `gpt-6-astra` | −16.6% | −25.3% | 9/10, 9/10 |
| `5524197` | H02, H03, H05 × 2 | `gpt-6-astra` | +7.6% | −14.3% | 6/6, 6/6 |
| `5524197` | H02, H03, H05 × 2 | `claude-opus-5.5` | +2.4% | −19.8% | 6/6, 6/6 |

- The `763d451` run used the 5 tasks that motivated its fix, so it is not an unbiased test.
- PRS-5, a pre-registered real-CLI study, stopped after 10 of 32 sessions on October 18. Its
  partial data are kept as evidence, not as a study result. In them, the `brainspace` MCP
  server's 5 tools got no calls, and each model call carried about 500 tokens of their
  definitions. Copilot setup now skips that server.

## Limits

- **Exploratory.** No protocol was pre-registered. The tasks were committed before each run,
  except the first 10-task Django run (D01–D10, superseded), whose tasks were committed after it
  (`dd1f38a`). The task types and the excluded tools were chosen by the team that builds
  TokenMaster.
- **Scope.** 1 run per task, 2 repositories and 2 models. The Django run has one task type,
  "who calls X?". The run on this repository has mostly short tasks.
- **Copilot CLI version.** All runs used 1.0.78-3. Copilot CLI 1.0.98 sends a smaller fixed prompt,
  and its stock first call can read part of the prompt from the cache when another session ran
  shortly before. So its savings can differ ([Copilot CLI version](#copilot-cli-version)).
- **Cost depends on timing.** The as-run costs come from back-to-back sessions. See
  [How to read the cost numbers](#how-to-read-the-cost-numbers).
- **Excluded tools.** The 11 tools were chosen because no session called them in the October 18
  runs. On October 19, one stock session (P13) called `task`. Workloads that need subagents
  (`task`), skills, session-store search, SQL or background PowerShell lose these tools.
  `--all-tools` keeps them. Such workloads were not measured.
- **Routing.** All runs used bring-your-own-model mode through a relay. With Copilot CLI's
  default GitHub routing, the launcher applies only the lean tool set; graph navigation and the
  v6 `view` hook also work there, but the bridge does not. That configuration was not measured.
- **No test runs.** No Python was on the agents' PATH, so no task asked an agent to run tests.
- **Strict edit grading.** The edit grader fails any change outside the allowed paths,
  including a line-ending-only change.
- **Cost scope.** Cost uses GitHub's per-token prices. It does not count premium requests or
  plan allowances.

## Reproduce

```powershell
$env:BRAINSPACE_TOKENIZER_FILE = "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
$py = ".\.token-master-dev\Scripts\python.exe"

# Recount tokens and GitHub's charges from the committed per-call records (no model calls).
& $py -B evidence\django-scale-20261022\audit.py evidence\django-scale-20261022

# Confidence intervals and the cold re-pricing.
& $py -B evidence\django-scale-20261022\analyze.py
& $py -B evidence\copilot-lean-analysis-20261022\analyze.py

# Rebuild the 45 Django tasks from a Django 5.2 checkout.
& $py -B evidence\django-scale-20261022\make_tasks_scale.py <django checkout>

# Live run for one model: run both commands at the same time.
cd token-master-plugin\evals
& $py -B django_ab.py --repo <django checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --output <new folder>\astra-ab --variant ab --lanes djc --model gpt-6-astra
& $py -B django_ab.py --repo <django checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --output <new folder>\astra-lean --variant lean --lanes dja --model gpt-6-astra

# Then summarize the four run folders.
& $py -B ..\..\evidence\django-impact-20261019\summarize.py <new folder> <evidence folder>

# The 27-task run on this repository.
& $py -B quick_copilot_ab.py --model gpt-6-astra --tasks <ids> --repeats 1 --lanes <name> --output <new folder>
```

Live runs need an active GitHub Copilot sign-in in OpenCode and an installed Copilot CLI. The
harness reads the credential in memory and never writes it. It stops unless the Copilot CLI
version that its sessions run equals `CLI_VERSION` in `run_prs5_study.py`. With the October flags,
which include `--no-auto-update`, that version is 1.0.78-3, so a re-run needs a change to the
flags or to `CLI_VERSION`.
