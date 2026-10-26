# TokenMaster

<p align="center">
  <img src="assets/tokenmaster-hero.svg?v=2" alt="TokenMaster" width="100%">
</p>

TokenMaster is an experimental toolkit that cuts the tokens AI coding agents spend. Its main
target is GitHub Copilot CLI. In the real-CLI runs so far, answer quality matched or stayed close
to stock: in the pre-registered PRS-6 study on Copilot CLI `1.0.98`, TokenMaster passed **58 of 58**
on this repository and **30 of 30** on Django `D01`–`D15` (matching stock); in the earlier
exploratory `1.0.78-3` runs, it had 2 fewer correct answers of 90 on Django and 1 fewer of 54 on
this repository, all model errors.
It has four parts:

1. **Lean tool set (launcher).** Copilot CLI re-sends its system prompt and tool definitions on
   every model call. The TokenMaster launcher removes 11 built-in tools that no session called in
   the October 18 runs used to choose them. Their definitions and the system-prompt text about
   them then leave every call.
2. **Copilot CLI bridge (bring-your-own-model mode only).** A local bridge makes the system
   prompt the same for every session in the same working folder, so later sessions there read it
   from the provider's cache. It also shapes grep, glob and whole-file view results with
   `request-policy-v6`.
3. **Graph-first navigation (v7, `brainspace/symbol_index.py`).** Three compact tools over
   graphify's call graph and an exact-range symbol index.
   - `locate` finds a symbol or a file's outline.
   - `read_symbol` returns exactly one symbol or range.
   - `impact` lists callers.
   - Every result stays under 2,400 tokens. `setup.py` installs the tools as one MCP server,
     `tokenmaster-nav`.
4. **Tool-result shaping (`request-policy-v6`).** v6 shapes each tool result once, when it enters
   the conversation. It packs search output losslessly and turns oversized results into short
   digests. It never rewrites history, so the provider's prompt cache keeps working. It runs in
   the bridge, in the Copilot output hook for whole-file `view` results, and in the native
   Copilot route.

It also ships **`/tokenomics`**, a ccusage-style dashboard of your Copilot CLI tokens, GitHub's
charges and TokenMaster's estimated savings
([see below](#see-your-tokens-cost-and-savings-with-tokenomics)).

## Current evidence: the real Copilot CLI (October 18–26, 2026)

### 1. Pre-registered study PRS-6 on real Copilot CLI `1.0.98` (October 26, 2026)

- **Protocol and version verification:** pre-registered before any study call
  ([PRS6_PROTOCOL.md](token-master-plugin/docs/PRS6_PROTOCOL.md), commit `19443fc`, evidence in
  `evidence/prs6-copilot-1.0.98-20261026/analysis.json`). Pinning `COPILOT_CLI_DIST_DIR` to `1.0.98`
  and removing `--no-auto-update` ran real Copilot CLI `1.0.98`, verified in 176 of 176 session
  captures (`Version number: 1.0.98`, 0 recount mismatches, `total_nano_aiu` matching calculated USD
  to `$0.0001`).

**Primary confirmatory benchmark (this repository, 29 tasks: `P01`–`P24` + `H01, H02, H03, H05, H06`, 116 sessions, October 26, 2026, 16:59–17:05 UTC):**

| 29 tasks per model (`1.0.98`) | Stock Copilot CLI `1.0.98` | Full TokenMaster | Change (95% CI) | Wilcoxon / Holm $p$ |
| --- | ---: | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,449,067 | **1,237,510** | **−49.5%** (−55.9%, −42.3%) | $p < 0.0001$ / $< 0.0001$ |
| `gpt-6-astra` cost, every first call cold | $8.91 | **$5.21** | **−41.5%** (−47.7%, −35.5%) | $p < 0.0001$ / $< 0.0001$ |
| `gpt-6-astra` cost, as run (back to back) | $6.83 | **$3.40** | **−50.2%** (−59.6%, −42.0%) | $p < 0.0001$ |
| `gpt-6-astra` model calls | 171 | 143 | −16.4% | — |
| `gpt-6-astra` passed | 29/29 | **29/29** | — | — |
| `claude-opus-5.5` raw tokens | 2,672,316 | **1,655,797** | **−38.0%** (−44.7%, −31.3%) | $p < 0.0001$ / $< 0.0001$ |
| `claude-opus-5.5` cost, every first call cold | $4.23 | **$2.79** | **−34.0%** (−38.7%, −29.3%) | $p < 0.0001$ / $< 0.0001$ |
| `claude-opus-5.5` cost, as run (back to back) | $2.72 | **$1.63** | **−40.1%** (−48.2%, −32.3%) | $p < 0.0001$ |
| `claude-opus-5.5` model calls | 127 | 137 | +7.9% (n.s., $p = 0.136$) | — |
| `claude-opus-5.5` passed | 29/29 | **29/29** | — | — |

- **`gpt-6-astra`:**
  - Raw tokens: `2,449,067` → **`1,237,510` (−49.5%; 95% CI −55.9% to −42.3%; Wilcoxon $p < 0.0001$,
    Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Meets the 2,000,000 raw-token workload floor.
  - Cold-repriced cost: `$8.91` → **`$5.21` (−41.5%; 95% CI −47.7% to −35.5%; Holm $p < 0.0001$;
    lower on 28 of 29 tasks)**.
  - As-run cost (back to back): `$6.83` → **`$3.40` (−50.2%; 95% CI −59.6% to −42.0%)**. On
    `1.0.98`, 28 of 29 stock first calls started warm (median `6,450` cached, `4,882` cache write),
    vs 27 of 29 TokenMaster (`5,721` cached, `322` cache write).
  - Calls: `171` → `143` (−16.4%); `tokenmaster-nav` used in 29 of 29 sessions (`124` calls).
  - Passed: **29/29 stock, 29/29 TokenMaster**.
- **`claude-opus-5.5`:**
  - Raw tokens: `2,672,316` → **`1,655,797` (−38.0%; 95% CI −44.7% to −31.3%; Wilcoxon $p < 0.0001$,
    Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Meets the 2,000,000 raw-token workload floor.
  - Cold-repriced cost: `$4.23` → **`$2.79` (−34.0%; 95% CI −38.7% to −29.3%; Holm $p < 0.0001$;
    lower on 28 of 29 tasks)**.
  - As-run cost (back to back): `$2.72` → **`$1.63` (−40.1%; 95% CI −48.2% to −32.3%)**. Warm first
    calls: 28 of 29 stock (median `11,226` cached, `7,265` cache write) and 28 of 29 TokenMaster
    (`8,762` cached, `543` cache write).
  - Calls: `127` → `137` (+7.9%, not significant, $p = 0.136$); `tokenmaster-nav` used in 6 of 29
    sessions (`8` calls).
  - Passed: **29/29 stock, 29/29 TokenMaster** (including `H03`, now that `same_content()` ignores
    CRLF-only rewrites).

**Django 5.2 caller replication on `1.0.98` with `SCHEMA_VERSION = 4` import-alias resolution (`D01`–`D15`, 15 tasks per model, 60 sessions, October 26, 2026, 17:34–17:56 UTC):**

- `brainspace/symbol_index.py` (`SCHEMA_VERSION = 4`) now resolves `import a as b` and
  `from a import b as c` (minus shadowed function parameters), so
  `impact("django/contrib/auth/__init__.py::login")` finds `auth_login(...)` callers in
  `django/contrib/auth/views.py` (`D13`), bringing `D01`–`D15` caller recall from `54/56` to
  `56/56`.
- **`gpt-6-astra` (`D01`–`D15`):** Raw tokens `707,799` → **`293,779` (−58.5%; 95% CI −64.4% to
  −52.3%; lower on 15 of 15 tasks)**; cold-repriced cost `$3.40` → **`$1.58` (−53.5%)**; as-run
  cost `$2.36` → **`$0.69` (−70.7%)**; passed **15/15 vs 15/15**.
- **`claude-opus-5.5` (`D01`–`D15`):** Raw tokens `989,925` → **`457,875` (−53.7%; 95% CI −57.8% to
  −48.9%; lower on 15 of 15 tasks)**; cold-repriced cost `$1.81` → **`$0.98` (−46.0%)**; as-run
  cost `$1.11` → **`$0.43` (−61.2%)**; passed **15/15 vs 15/15**.

### 2. Exploratory runs on real Copilot CLI `1.0.78-3` (October 18–22, 2026)

These earlier runs used the real Copilot CLI `1.0.78-3` with `gpt-6-astra` and `claude-opus-5.5` on
GitHub's Copilot API. They are exploratory: no protocol was pre-registered. Until October 23 this
page said 1.0.98. The harness's `--no-auto-update` flag had selected the WinGet launcher's bundled
build (`1.0.78-3`) instead of the installed `1.0.98`
([version note](token-master-plugin/docs/COPILOT_CLI_RESULTS.md#copilot-cli-version)).

**Test parameters** (`1.0.78-3`; full table: [COPILOT_CLI_RESULTS.md](token-master-plugin/docs/COPILOT_CLI_RESULTS.md#test-parameters-october-1822-exploratory-1078-3-runs)):
- **Client:** Copilot CLI 1.0.78-3 in non-interactive mode (`-p`), reasoning effort `low`, built-in
  MCP servers off.
- **Routing:** offline bring-your-own-model mode, through a local relay that forwarded each request
  unchanged to `api.githubcopilot.com`.
- **Versions:** in the Django run, stock Copilot CLI; TokenMaster without graphify (launcher with
  the lean tool set, bridge); and full TokenMaster (the same plus graph navigation, graphify
  0.9.91). The repository run compared stock and full TokenMaster (graphify 0.9.84).
- **Sample:** 1 run per task and version. Each session started from a fresh copy of the
  repository. All versions ran at the same time, with sessions back to back.
- **Measures:** raw tokens are input plus output tokens, as GitHub's API reported them. Cost uses
  GitHub's per-token prices; GitHub's own per-call charges add up to the same totals. 95% CIs
  come from a paired bootstrap over tasks.

**Django 5.2, 45 "who calls X?" tasks per model (270 sessions, October 22, Copilot CLI `1.0.78-3`):**

| | Stock Copilot CLI (`1.0.78-3`) | TokenMaster without graphify | Full TokenMaster |
| --- | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,417,452 | 1,331,990 (−44.9%) | **1,127,277 (−53.4%)** |
| `gpt-6-astra` cost, as run | $11.55 | $3.37 (−70.8%) | **$2.33 (−79.9%)** |
| `gpt-6-astra` cost, every first call cold | $11.55 | $6.74 (−41.6%) | **$5.83 (−49.5%)** |
| `claude-opus-5.5` raw tokens | 3,457,179 | 1,855,563 (−46.3%) | **1,673,646 (−51.6%)** |
| `claude-opus-5.5` cost, as run | $3.31 | $1.48 (−55.2%) | **$1.30 (−60.8%)** |
| `claude-opus-5.5` cost, every first call cold | $6.14 | $3.39 (−44.8%) | **$3.31 (−46.0%)** |
| Correct answers, both models | 90/90 | 88/90 | 88/90 |

- **Full TokenMaster against stock (`1.0.78-3`):** the 95% CI is −57.1% to −49.1% raw tokens with
  `gpt-6-astra` and −55.7% to −47.2% with `claude-opus-5.5`. Full TokenMaster used fewer raw
  tokens on all 45 tasks with each model.
- **The as-run cost saving is a best case.** Sessions ran back to back, so TokenMaster's sessions
  read the previous session's system prompt from GitHub's cache. Stock `gpt-6-astra` on `1.0.78-3`
  could not, because Copilot CLI `1.0.78-3` writes each session's folder into its system prompt. A
  cached prompt lasted between 6.5 and 31 minutes in one probe. For sessions that start further
  apart, use the "every first call cold" rows: about half, like the raw tokens.
- **Graphify's own share (`1.0.78-3`):** on top of TokenMaster without graphify, graph navigation
  cut a further 15.4% of raw tokens (95% CI −21.7% to −8.1%) with `gpt-6-astra` and 9.8% (−18.4% to
  −0.8%) with `claude-opus-5.5`. That is 8.5 and 5.3 percentage points of stock's tokens. It saves
  model calls.
- **Wrong answers (`1.0.78-3`):** the 4 wrong answers were model errors. For each one, the other
  versions passed with the same answer key.

**This repository, 27 tasks per model (October 19, Copilot CLI `1.0.78-3`):** full TokenMaster used
44.8% fewer raw tokens with `gpt-6-astra` (95% CI −52.6% to −37.4%). With `claude-opus-5.5`, it
used 53.5% fewer (−58.8% to −48.3%). Cost fell by 62.8% and 51.2% as run, and by 40.8% and 43.9%
with every first call cold. Stock passed 27/27 with each model; TokenMaster passed 27/27 and 26/27.

**Limits:**
- 1 run per task and 2 repositories. The Django runs use one task type ("who calls X?").
- The October 18–22 exploratory runs used Copilot CLI `1.0.78-3`. On October 26, the pre-registered
  PRS-6 study measured real Copilot CLI `1.0.98`, where stock first calls also read part of the
  prompt from the cache when another session ran shortly before; see the `1.0.98` cold-repriced and
  as-run numbers above.
- All runs used bring-your-own-model mode through an evaluation relay. With Copilot CLI's
  default GitHub routing, the launcher applies only the lean tool set; graph navigation and the
  v6 `view` hook also work there, but the bridge does not. No run measured that configuration.
- The 11 excluded tools were chosen because no session called them in the October 18 runs. On
  October 19, one stock session called `task` (a subagent). For work that needs subagents,
  skills or background PowerShell, start the launcher with `--all-tools`.

Details: [COPILOT_CLI_RESULTS.md](token-master-plugin/docs/COPILOT_CLI_RESULTS.md).

## Use it with Copilot CLI

Run these commands from `token-master-plugin/skills/token-master/`:

```powershell
python brainspace_setup.py --host copilot --python <runtime> --tokenizer-file <cl100k_base.tiktoken>
python setup.py <repo> --host copilot --python <runtime>    # graph navigation; needs graphify
python <COPILOT_HOME>/token-master/brainspace_copilot_bridge.py -- copilot
```

- The last command starts Copilot CLI with the lean tool set. Plain `copilot` stays unchanged.
- In bring-your-own-model mode (`COPILOT_PROVIDER_BASE_URL` set), the same command also starts
  the bridge.
- `--all-tools` keeps every built-in tool.
- The first command also installs the `/tokenomics` dashboard
  ([next section](#see-your-tokens-cost-and-savings-with-tokenomics)).

Details: [COPILOT_BRIDGE.md](token-master-plugin/docs/COPILOT_BRIDGE.md).

## See your tokens, cost and savings with `/tokenomics`

`/tokenomics` does for Copilot CLI what [ccusage](https://github.com/ryoppippi/ccusage) does for
Claude Code. It reads Copilot CLI's own record of every model call and prints daily, weekly,
monthly or per-session tables.

- **Measured:** tokens, cache reads and writes, and GitHub's own charge for each call, from
  `<COPILOT_HOME>/session-store.db`.
- **Estimated:** what the TokenMaster sessions would have used without TokenMaster. The columns
  and lines with these numbers are marked ≈.
- **TokenMaster or stock:** the launcher records each launch in
  `<COPILOT_HOME>/token-master/launches.jsonl`: time, folder, and whether the lean tool set, the
  bridge and the navigation tools were on. The records hold no prompt text. Sessions started
  without the launcher count as stock.

To use it:

1. Install TokenMaster for Copilot with `brainspace_setup.py` (the first command above).
2. Start Copilot CLI through the launcher, and work as usual.
3. In an interactive session, type `/tokenomics`. Add a report and options after it, for example
   `/tokenomics session --since 20261020` or `/tokenomics monthly --breakdown`.
4. Approve Copilot CLI's two questions: access to the script's path, and running the command.

- **It costs model tokens.** `/tokenomics` asks the model to run the report and repeat it. In the
  live check on Copilot CLI 1.0.98, that took 2 model calls, 16,445 tokens and $0.16 with
  `gpt-6-astra`.
- **The free way:** the last line of the report gives a `!` shell command that prints the same
  report in Copilot CLI without a model call. In any terminal, run
  `python <COPILOT_HOME>/token-master/tokenomics.py`.
- **`copilot -p "/tokenomics"` does not work.** Copilot CLI runs slash commands only in an
  interactive session.

Excerpt from a live check (Copilot CLI 1.0.98, `gpt-6-astra`, October 23, 2026): one stock
session, then two TokenMaster sessions with the same one-line question in the same folder
([full record](evidence/tokenomics-check-20261023/readme-example.txt)). The "Saved (USD) ≈"
values come from the estimator of that morning. The current estimator measures stock's first-call
cache reads from your own stock sessions, so it would credit more here.

```text
┌──────────┬───────────────┬──────────────┬────────────┬──────────────┬────────────────┬───────────────┐
│ Session  │ Models        │ Total Tokens │ Cost (USD) │ TokenMaster  │ Saved Tokens ≈ │ Saved (USD) ≈ │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 579e5c15 │ • gpt-6-astra │       22,278 │      $0.15 │ -            │              - │             - │
│ repo     │               │              │            │              │                │               │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 9b2700f4 │ • gpt-6-astra │       16,847 │      $0.09 │ lean+bridge  │         16,674 │         $0.01 │
│ repo     │               │              │            │              │                │               │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 5690993e │ • gpt-6-astra │       16,844 │      $0.02 │ lean+bridge  │         16,674 │         $0.07 │
│ repo     │               │              │            │              │                │               │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ Total    │               │       55,969 │      $0.26 │ 2/3 sessions │         33,348 │         $0.08 │
└──────────┴───────────────┴──────────────┴────────────┴──────────────┴────────────────┴───────────────┘

TokenMaster savings (estimated)
  TokenMaster sessions          2 of 3  6 model calls
  Tokens, actual                33,691  GitHub's token counts
  Tokens without TokenMaster ≈  67,039  saved 33,348 (49.7%)
  Cost, actual                   $0.11  GitHub's own charge per call
  Cost without TokenMaster ≈     $0.18  saved $0.08 (41.0%)
    of which lean tool set       $0.03  33,348 fewer fixed tokens, priced as cache reads
    of which first calls         $0.04  prompt-cache writes on each session's first call
```

- The second TokenMaster session cost $0.02 against the first one's $0.09. Its first call read
  the prompt that the first session had written to the cache. The bridge makes that possible for
  sessions in the same folder.
- The stock session made 2 model calls; each TokenMaster session made 3. The estimate assumes the
  same calls for stock, so it does not show that difference.
- **How the estimate works:** each TokenMaster call is credited with the fixed tokens that the
  lean tool set removes, and each session's first call is compared with stock's prompt-cache
  write. Stock's first-call cache reads come from your own stock sessions when the store has
  them. Calls that graph navigation saved are not counted. On the measured A/B runs (Copilot
  CLI 1.0.78-3), the method gave 72% to 125% of the measured token saving. The 1.0.98 fixed-prompt
  values come from the October 23 probe; PRS-6 measured the full 1.0.98 A/B savings above.

Details: [TOKENOMICS.md](token-master-plugin/docs/TOKENOMICS.md).

## Earlier evidence: pre-registered studies in a replica harness (PRS-1 to PRS-4)

PRS-1 to PRS-4 were pre-registered live studies with `gpt-6-astra`:
- Agents that were not told the arms wrote the tasks.
- Code, tasks and analysis were frozen by hash before any live call.
- Every token was recounted from raw captures.

They ran a Copilot-CLI-shaped agent, not the real Copilot CLI. The PRS-4 agent's fixed prompt was
about 3,600 tokens. The real Copilot CLI sends about 13,500 tokens of system prompt and tool
definitions with `gpt-6-astra` (1.0.78-3; about 11,100 with 1.0.98). So the PRS numbers do not
carry over directly to the real CLI.

### PRS-4 (October 18, 2026): v7 + cache-stable system prompt cut billed cost by 50% under continuous use

- 360 sessions on 24 fresh tasks.
- Primary endpoint: billed cost per finished task, at the provider's own prices (cache read 0.1,
  cache write 1.25, output 5, relative to uncached input).
- Every graded session was checked against the provider's bill.

| Configuration | Passed | Change per finished task vs. stock (95% CI) | Holm p |
| --- | ---: | ---: | ---: |
| v7 (v6 + navigation tools) | 120/120 | −18.2% (−26.6%, −9.5%) | 0.00049 |
| **v7 + cache-stable system prompt** | **120/120** | **−49.8% (−57.1%, −42.9%)** | **< 0.00001** |

- **The 30% goal was met under continuous use.** In the study, the sessions of one repository
  ran back to back. In that regime, 119 of 120 first calls with the cache-stable system prompt
  read the prompt from the cache.
- **Cold sessions save less.** A session starts cold if no other session sent the same
  system prompt within the cache lifetime. One probe put that lifetime between 6.5 and 31
  minutes. Re-priced as if every first call missed the cache, the saving is 18.9%, close to
  v7 alone.
- **Today, two routes apply the cache-stable system prompt.** One is the experimental, read-only
  native Copilot route. The other is the Copilot CLI bridge in bring-your-own-model mode. The
  real-CLI runs above measured the bridge together with the lean tool set and graph navigation.
  Copilot CLI's default GitHub routing cannot apply it.

Details: [PRS4_RESULTS.md](token-master-plugin/docs/PRS4_RESULTS.md).

### PRS-3 (October 18, 2026): v7 cuts cost by 22%

- 480 sessions on 24 fresh tasks.
- Cost = uncached input + 0.1 × cached input + 8 × output.

| Configuration | Passed | Cost change vs. stock (95% CI) | Holm p |
| --- | ---: | ---: | ---: |
| v6 | 120/120 | −13.0% (−19.3%, −6.7%) | 0.0001 |
| **v7** (v6 + navigation tools) | **120/120** | **−22.0% (−35.4%, −8.9%)** | **0.006** |

- **v6 replicated** its PRS-2 result (−11.6%) on new tasks.
- **v7's extra saving over v6 alone is not established:** −10.4%, p = 0.16. It is
  concentrated on "who calls X" tasks: −52% against v6, an exploratory result. One
  sentence of advice without the tools saved 4.8% (not significant).
- **The goal of at least 30% savings was not met by PRS-3.** PRS-4 met it under continuous
  use, with the cache-stable system prompt.

Details: [PRS3_RESULTS.md](token-master-plugin/docs/PRS3_RESULTS.md).

### PRS-2 (October 18, 2026): v6 lowers cost

On 12 fresh tasks, v6 cut cost by **11.6%** (95% CI −20.8% to −3.8%, Holm p = 0.014),
with quality at 36/36. The graph tools as shipped raised cost by 12.9%.
Details: [PRS2_RESULTS.md](token-master-plugin/docs/PRS2_RESULTS.md).

### PRS-1 (October 18, 2026)

PRS-1 had 252 sessions, 12 real tasks on this repository and 7 arms. It used the real GitHub
Copilot CLI system prompt in the replica harness.

| Arm | Passed | Total tokens | Change vs. baseline (95% CI) | Cache-weighted change (95% CI) |
| --- | ---: | ---: | ---: | ---: |
| baseline | 36/36 | 2,082,599 | — | — |
| baseline_parallel | 35/36 | 1,399,967 | −32.8% (−50.4%, −8.8%) | −7.1% (−20.0%, +8.2%) |
| ponytail | 34/36 | 2,498,333 | +20.0% (−2.0%, +47.3%) | +19.6% (+6.1%, +38.1%) |
| headroom | 35/36 | 1,820,351 | −12.6% (−29.3%, +7.9%) | −9.8% (−22.2%, +3.5%) |
| graph | 36/36 | 2,060,438 | −1.1% (−35.1%, +42.1%) | +15.0% (−10.7%, +43.9%) |
| v5 | 36/36 | 2,245,809 | +7.8% (−24.7%, +49.8%) | **+61.6% (+19.6%, +111.0%)** |
| graph_v5 | 36/36 | 2,182,011 | +4.8% (−32.2%, +52.8%) | **+57.0% (+10.1%, +118.0%)** |

- **No TokenMaster configuration significantly reduced total tokens.**
- **v5 raised cache-weighted cost by 61.6%.** Rewriting earlier messages breaks the
  provider's prompt cache, and v5 sessions made 13% more model calls.
  Cache-weighted means cached input counts at 10%.
- **Quality held:** every TokenMaster arm passed 36/36.
- **Parallel tool calls** gave the largest observed reduction (−32.8%), but the
  Holm-adjusted p is 0.11, so it is not significant under the pre-declared rule.
  TokenMaster's transport then forced parallel tool calls off. The native route now keeps them.

Full results: [PRS1_RESULTS.md](token-master-plugin/docs/PRS1_RESULTS.md).
Protocol: [PRS1_PROTOCOL.md](token-master-plugin/docs/PRS1_PROTOCOL.md).

> **Retraction (October 18, 2026).** The October 17 savings claims (−83.29%,
> −73.19%, −65.68%, −48.51%, −44.20%, −43.14%) are withdrawn. They came from
> synthetic modules padded with repetitive lines, scripted file reads, extra tools
> in the baseline, a misconfigured Headroom adapter, and ignored prompt caching.
> The scripts that produced them are kept only as synthetic mechanism checks.

## How it works and where it falls short

| Component | Mechanism | Measured limits |
| --- | --- | --- |
| Lean tool set (launcher) | Adds `--excluded-tools` for 11 built-in Copilot CLI tools that no session called in the October 18 runs. Removes their definitions and the system-prompt text about them from every call. | Real-CLI probe (Copilot CLI 1.0.78-3): system prompt 7,216 → 5,117 tokens; one lookup task 27,255 → 13,702 raw tokens (`gpt-6-astra`). Most of the real-CLI saving came with it. Removes subagents, skills, session-store search and background PowerShell; one later stock session called `task`. `--all-tools` keeps them. |
| Copilot CLI bridge | Local bridge for bring-your-own-model mode. Cache-stable system prompt and v6 shaping of grep, glob and view results, for OpenAI Responses and Anthropic Messages. | Real CLI `1.0.78-3`, Django: 44 of 45 `gpt-6-astra` first calls read the system prompt from the cache, against 0 of 45 for stock. On `1.0.98` (PRS-6, 29 tasks), 28 of 29 stock first calls also started warm (`gpt-6-astra` median `6,450` cached, `4,882` cache write vs TokenMaster `5,721` cached, `322` cache write; `claude-opus-5.5` `11,226` / `7,265` vs `8,762` / `543`). Copilot CLI's default GitHub routing cannot use the bridge. |
| Graph-first navigation (v7) | `locate`, `read_symbol` and `impact` over a SQLite symbol index with exact line ranges and graphify's call graph. Every result is capped at 2,400 tokens. | Real CLI `1.0.78-3`, Django: −15.4% (`gpt-6-astra`) and −9.8% (`claude-opus-5.5`) raw tokens on top of the lean tool set, by saving model calls. PRS-3 (replica): −22.0% cost against stock. On October 26 (`SCHEMA_VERSION = 4`), `brainspace/symbol_index.py` added resolution of `import a as b` and `from a import b as c` (minus shadowed function parameters), so `impact("django/contrib/auth/__init__.py::login")` finds `auth_login(...)` callers in `django/contrib/auth/views.py` (`D13`), bringing `D01`–`D15` caller recall from `54/56` (`SCHEMA_VERSION = 3`) to `56/56`. Installed by `setup.py` as the `tokenmaster-nav` MCP server. |
| Graph routing (before v7) | `graphify-nav` (6 tools) and `codegraph` MCP servers on prebuilt indexes, plus a routing agent prompt. | Added about 2,100 tokens to every call; PRS-2: +12.9% cost. `setup.py` now removes these servers when TokenMaster owns them. |
| `request-policy-v6` | Shapes each tool result once, deterministically, when it enters the conversation. Folds search and list output losslessly; turns oversized results into digests that name what was omitted and how to fetch it. | PRS-2: −11.6% cost; PRS-3: −13.0% cost on new tasks. Quality unchanged. Never rewrites history, so the provider's cache stays valid. |
| `request-policy-v5` | Keeps the newest tool result verbatim. Compacts older `view` results (code skeletons, JSON overviews, Markdown and log summaries) behind one `[[BR:<sha256>\|r=1]]` reference with exact SQLite recovery. | Removed 15.7% of tokens on the requests it changed. Uncached input still rose 94.8%, because each rewrite invalidates the cached prefix. Superseded by v6. |
| Runtime transport | Captures every request and reply for whole-task accounting. | The native route now keeps the client's parallel tool calls (default on). Earlier versions forced them off, which PRS-1 suggested was costly. |
| `/tokenomics` dashboard | Reads Copilot CLI's `session-store.db` and the launcher's `launches.jsonl`. Reports measured tokens and GitHub's charges, and estimated TokenMaster savings. | On the A/B runs (Copilot CLI 1.0.78-3), the estimate gave 72% to 125% of the measured token saving. The 1.0.98 fixed-prompt parameters come from a probe; PRS-6 measured the full 1.0.98 A/B savings above. Each `/tokenomics` costs about 16,000 model tokens; the `!` form costs none. |

## Version history

| Version | What it did | What testing showed |
| --- | --- | --- |
| `v1` / `v2` | Tree-sitter skeletons with a 190-byte reference per function | Multi-function files barely shrank, and extra recovery calls raised totals. |
| `v3` | Exact reuse of repeated identical reads | 9.9% on forced duplicate reads; 0% on ordinary workflows. |
| `v4` | Lossless JSON whitespace compaction | 1.43% across an 8-task suite. |
| `v5` | Multi-format compaction with one compact-root reference per file | PRS-1: +7.8% total tokens (not significant), +61.6% cache-weighted cost, 36/36 passed. |
| `v6` | Shapes each tool result once, deterministically: lossless folding, budgeted digests, history never rewritten | PRS-2: −11.6% cost on fresh tasks (95% CI −20.8% to −3.8%), 36/36 passed. PRS-3: −13.0% on 24 new tasks, 120/120. |
| `v7` | v6 plus graph-first navigation: `locate`, `read_symbol`, `impact` on graphify's call graph and exact line ranges | PRS-3: −22.0% cost against stock (95% CI −35.4% to −8.9%), 120/120 passed; −10.4% against v6 (not significant). |

Two lessons:
- Compaction that rewrites conversation history fights prompt caching. Shape each result once,
  when it enters the conversation, and leave history alone.
- On the real Copilot CLI, the fixed prompt that rides on every call cost more than the tool
  results did. Most of the measured saving came with the lean tool set, not with result shaping.

## Reproduce

The real-CLI runs: see [COPILOT_CLI_RESULTS.md](token-master-plugin/docs/COPILOT_CLI_RESULTS.md#reproduce).

PRS-1:

```powershell
$env:BRAINSPACE_TOKENIZER_FILE = "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
$py = ".\.token-master-dev\Scripts\python.exe"
$h = "token-master-plugin\evals\run_prs1_study.py"
& $py -B $h self-test                                         # offline checks
& $py -B $h prepare --output evidence\prs1-new\study          # freeze snapshot, tasks, prompts, schedule
& $py -B $h probe-headroom --output evidence\prs1-new\probe   # offline Headroom mechanism check
& $py -B $h smoke --output evidence\prs1-new\study            # one dummy task per arm
& $py -B $h run --output evidence\prs1-new\study              # 252 live sessions
& $py -B $h analyze --output evidence\prs1-new\study          # recount from raw captures
```

Live runs need these:

- An active GitHub Copilot sign-in in OpenCode. The token is read in memory and
  never written.
- Local installs of `graphify`, `codegraph` and `headroom-ai`.

Their paths are listed at the top of `run_prs1_study.py`.

## Tests

```powershell
$env:BRAINSPACE_TOKENIZER_FILE = "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
.\.token-master-dev\Scripts\python.exe -B -m pytest -q token-master-plugin/skills/token-master/tests
```

Status on October 23, 2026 (Windows): 4,443 passed, 4 skipped, 82 failed. The same 82 tests
failed on October 18 (4,427 passed then). On October 18, they also failed on a clean checkout of
commit `703aa20`, so they predate the v5 changes:

- 76 need the trusted Linux sandbox runner, which is not available here
  (`test_fresh_coding_cases.py` 34, `test_quality_sandbox.py` 42).
- 5 fail because the committed `evals/repository-cases.json` (`b9d54dfb…`) no longer
  matches its pinned hash (`f4ebd67e…`) (`test_repository_trial.py` 4,
  `test_recovery_replication_cases.py` 1).
- 1 needs a local evidence file that is not in the repository (`test_native_responses.py`).

## Documentation

- [Documentation index](token-master-plugin/docs/README.md)
- [Real Copilot CLI results](token-master-plugin/docs/COPILOT_CLI_RESULTS.md),
  [PRS-6 protocol (`1.0.98`)](token-master-plugin/docs/PRS6_PROTOCOL.md) and the
  [launcher and bridge](token-master-plugin/docs/COPILOT_BRIDGE.md)
- [/tokenomics dashboard](token-master-plugin/docs/TOKENOMICS.md), [15-minute demo script](docs/DEMO_SCRIPT.md) and [HTML demo slide deck](docs/tokenomics-demo-slide.html)
- [PRS-4 results](token-master-plugin/docs/PRS4_RESULTS.md) and [protocol](token-master-plugin/docs/PRS4_PROTOCOL.md)
- [PRS-3 results](token-master-plugin/docs/PRS3_RESULTS.md) and [protocol](token-master-plugin/docs/PRS3_PROTOCOL.md)
- [PRS-2 results](token-master-plugin/docs/PRS2_RESULTS.md) and [protocol](token-master-plugin/docs/PRS2_PROTOCOL.md)
- [PRS-1 results](token-master-plugin/docs/PRS1_RESULTS.md) and [protocol](token-master-plugin/docs/PRS1_PROTOCOL.md)
- [Single-slide summary](docs/tokenmaster-v5-slide.html)
- [Mission](MISSION.md) and [changelog](CHANGELOG.md)
- The documentation index lists the historical `v1`–`v4` studies.

## License

[MIT](LICENSE)
