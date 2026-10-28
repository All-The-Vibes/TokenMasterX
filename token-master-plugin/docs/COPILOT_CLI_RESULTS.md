# Copilot CLI results (October 18–27, 2026)

These runs used GitHub Copilot CLI and GitHub's Copilot API:

- **Default GitHub routing on Copilot CLI `1.0.104` (October 27, 2026):** the only run without the evaluation
  relay. Copilot CLI signed in and routed every request itself, and its own per-call records gave the tokens and
  GitHub's charges. Django D01–D15 with `gpt-6-astra`, 30 sessions; the protocol was committed before the sessions
  ([Default GitHub routing](#default-github-routing-on-copilot-cli-10104-october-27-2026)). A relay control on the
  same client build, account and day followed it.
- **Pre-registered study PRS-6 on Copilot CLI `1.0.98` (October 26, 2026):** pre-registered before
  any study call ([PRS6_PROTOCOL.md](PRS6_PROTOCOL.md), commit `19443fc`, evidence in
  `evidence/prs6-copilot-1.0.98-20261026/analysis.json`). Pinning `COPILOT_CLI_DIST_DIR` to `1.0.98`
  and removing `--no-auto-update` ran Copilot CLI `1.0.98`, verified in 176 of 176 session
  captures (`Version number: 1.0.98`, 0 recount mismatches, `total_nano_aiu` matching calculated USD
  to `$0.0001`).
- **Exploratory runs on Copilot CLI `1.0.78-3` (October 18–22, 2026):** used Copilot CLI `1.0.78-3`,
  the bundled build of the WinGet launcher, not the installed `1.0.98` that this page named until
  October 23, 2026 ([Copilot CLI version](#copilot-cli-version)). Those runs had no pre-registered
  protocol.
- **Earlier replica studies (PRS-1 to PRS-4):** used a Copilot-CLI-shaped harness instead, with a
  fixed prompt of about 3,600 tokens ([PRS4_RESULTS.md](PRS4_RESULTS.md)).

## Summary

### Default GitHub routing (Copilot CLI `1.0.104`, October 27, 2026)

- Django D01–D15 with `gpt-6-astra` and no relay, 30 sessions: raw tokens `708,928` → **`372,621` (−47.4%; 95% CI
  −52.8% to −41.7%; lower on 15 of 15 tasks)**. Cold-repriced cost `$3.75` → **`$2.05` (−45.4%; 95% CI −48.2% to
  −42.7%)**. As-run cost `$2.30` → **`$1.26` (−45.0%)**. Passed **15/15 stock, 15/15 TokenMaster**.
- The README's headline figures, up to 58% fewer tokens and up to 54% lower cold-start cost (the top of its 38% to 58%
  and 34% to 54% ranges) with no drop in pass rate, come from PRS-6's relay run on these tasks. Under default routing,
  58% and 54% do not hold: the 95% CIs end at 52.8% and 48.2%. The pass-rate claim holds, and both results fall
  inside the README's ranges.
- Compared with PRS-6's relay run on the same tasks and model, stock used the same raw tokens (`708,928` vs
  `707,799`) and TokenMaster used 27% more (`372,621` vs `293,779`). In this run each call carried a larger fixed
  prompt than in PRS-6, in both versions. Stock made fewer calls than in PRS-6 (47 vs 55); TokenMaster made about as
  many (44 vs 46).
- A relay control on `1.0.104`, with this run's client build, account, lanes and day, cut raw tokens by 48.6% (95% CI
  41.9% to 54.1%) and cold-repriced cost by 45.8%, against 47.4% and 45.4% under default routing. By the rule fixed
  before its sessions, routing explains none of the gap to PRS-6's 58.5% (its 95% CI allows at most 4.9 of the 11.1
  points). The gap lies in the other differences between the runs (client build, TokenMaster commit, day, account,
  lane location), and client build and routing interact. Routing does change the as-run cost: −64.9% through the
  relay, −45.0% under default routing
  ([Relay control](#relay-control-on-copilot-cli-10104-same-build-account-and-day)).

### Pre-registered study PRS-6 (Copilot CLI `1.0.98`, October 26, 2026)

- **Primary confirmatory benchmark (this repository, 29 tasks: `P01`–`P24` + `H01, H02, H03, H05, H06`, 116 sessions):**
  - **`gpt-6-astra`:** raw tokens `2,449,067` → **`1,237,510` (−49.5%; 95% CI −55.9% to −42.3%;
    Wilcoxon $p < 0.0001$, Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Cold-repriced cost
    `$8.91` → **`$5.21` (−41.5%; 95% CI −47.7% to −35.5%; Holm $p < 0.0001$; lower on 28 of 29
    tasks)**. As-run cost (back to back) `$6.83` → **`$3.40` (−50.2%; 95% CI −59.6% to −42.0%)**.
    Passed **29/29 stock, 29/29 TokenMaster**.
  - **`claude-opus-5.5`:** raw tokens `2,672,316` → **`1,655,797` (−38.0%; 95% CI −44.7% to
    −31.3%; Wilcoxon $p < 0.0001$, Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Cold-repriced
    cost `$4.23` → **`$2.79` (−34.0%; 95% CI −38.7% to −29.3%; Holm $p < 0.0001$; lower on 28 of 29
    tasks)**. As-run cost (back to back) `$2.72` → **`$1.63` (−40.1%; 95% CI −48.2% to −32.3%)**.
    Passed **29/29 stock, 29/29 TokenMaster**.
- **Django 5.2 caller replication (`D01`–`D15`, 15 tasks per model, 60 sessions, `SCHEMA_VERSION = 4` import-alias resolution):**
  - `brainspace/symbol_index.py` (`SCHEMA_VERSION = 4`) resolves `import a as b` and
    `from a import b as c` (minus shadowed function parameters), bringing `D01`–`D15` caller recall
    from `54/56` to `56/56` (including `D13`, where `login` is imported as `auth_login`).
  - **`gpt-6-astra` (`D01`–`D15`):** raw tokens `707,799` → **`293,779` (−58.5%; 95% CI −64.4% to
    −52.3%; lower on 15 of 15 tasks)**; cold-repriced cost `$3.40` → **`$1.58` (−53.5%)**; as-run
    cost `$2.36` → **`$0.69` (−70.7%)**; passed **15/15 vs 15/15**.
  - **`claude-opus-5.5` (`D01`–`D15`):** raw tokens `989,925` → **`457,875` (−53.7%; 95% CI −57.8%
    to −48.9%; lower on 15 of 15 tasks)**; cold-repriced cost `$1.81` → **`$0.98` (−46.0%)**;
    as-run cost `$1.11` → **`$0.43` (−61.2%)**; passed **15/15 vs 15/15**.

### Exploratory runs (Copilot CLI `1.0.78-3`, October 18–22, 2026)

- **Django, 45 "who calls X?" tasks (`1.0.78-3`):** full TokenMaster used 53.4% fewer raw tokens
  than stock Copilot CLI with `gpt-6-astra` (95% CI −57.1% to −49.1%). With `claude-opus-5.5`, it
  used 51.6% fewer (95% CI −55.7% to −47.2%). It used fewer raw tokens on all 45 tasks with each
  model.
- **Cost at GitHub's prices depends on how close together the sessions run (`1.0.78-3`, Django 45-task):**
  - As run, with sessions back to back: 79.9% lower (`gpt-6-astra`) and 60.8% lower
    (`claude-opus-5.5`).
  - Re-priced as if every session started with a cold cache: 49.5% and 46.0% lower.
  - Read [How to read the cost numbers](#how-to-read-the-cost-numbers) before you quote a cost
    saving.
- **Correct answers (`1.0.78-3`, Django 45-task):** stock 90 of 90; full TokenMaster 88 of 90.
- **This repository, 27 tasks (`1.0.78-3`):** full TokenMaster used 44.8% fewer raw tokens with
  `gpt-6-astra` and 53.5% fewer with `claude-opus-5.5`.
- **Where the saving comes from (`1.0.78-3`):** most of it came with the lean tool set. On Django,
  graphify navigation cut a further 15.4% (`gpt-6-astra`) and 9.8% (`claude-opus-5.5`) of the raw
  tokens that TokenMaster without graphify used. That is 8.5 and 5.3 percentage points of stock's
  tokens.
- **Copilot CLI version:** the October 18–22 exploratory runs used `1.0.78-3`. On October 26, the
  pre-registered PRS-6 study measured Copilot CLI `1.0.98`
  ([Pre-registered study PRS-6](#pre-registered-study-prs-6-on-copilot-cli-1098-october-26-2026) and
  [Copilot CLI version](#copilot-cli-version)).

## Pre-registered study PRS-6 on Copilot CLI `1.0.98` (October 26, 2026)

### 1. Protocol and version verification

- Pre-registered before any study call ([PRS6_PROTOCOL.md](PRS6_PROTOCOL.md), commit `19443fc`).
- Pinning `COPILOT_CLI_DIST_DIR` to `1.0.98` and removing `--no-auto-update` ran Copilot CLI
  `1.0.98`, verified in 176 of 176 session captures (`Version number: 1.0.98`, 0 recount mismatches,
  `total_nano_aiu` matching calculated USD to `$0.0001`).
- Evidence: `evidence/prs6-copilot-1.0.98-20261026/analysis.json` and `capture_audit.json`.

### 2. Primary confirmatory benchmark (this repository, 29 tasks, 116 sessions)

- **Tasks:** 29 tasks per model (`P01`–`P24` + `H01, H02, H03, H05, H06`).
- **Session start times:** October 26, 2026, 16:59–17:05 UTC.
- **Workload floor:** both models met the pre-registered 2,000,000 raw-token stock workload floor
  (`2,449,067` for `gpt-6-astra`, `2,672,316` for `claude-opus-5.5`).

| 29 tasks per model (`1.0.98`) | Stock | Full TokenMaster | Change (95% CI) | Wilcoxon / Holm $p$ |
| --- | ---: | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,449,067 | **1,237,510** | **−49.5%** (−55.9%, −42.3%) | $p < 0.0001$ / $< 0.0001$ |
| `gpt-6-astra` cost, every first call cold | $8.91 | **$5.21** | **−41.5%** (−47.7%, −35.5%) | $p < 0.0001$ / $< 0.0001$ |
| `gpt-6-astra` cost, as run (back to back) | $6.83 | **$3.40** | **−50.2%** (−59.6%, −42.0%) | $p < 0.0001$ |
| `gpt-6-astra` model calls | 171 | 143 | −16.4% (−25.1%, −6.0%) | $p = 0.0083$ |
| `gpt-6-astra` passed | 29/29 | **29/29** | — | — |
| `claude-opus-5.5` raw tokens | 2,672,316 | **1,655,797** | **−38.0%** (−44.7%, −31.3%) | $p < 0.0001$ / $< 0.0001$ |
| `claude-opus-5.5` cost, every first call cold | $4.23 | **$2.79** | **−34.0%** (−38.7%, −29.3%) | $p < 0.0001$ / $< 0.0001$ |
| `claude-opus-5.5` cost, as run (back to back) | $2.72 | **$1.63** | **−40.1%** (−48.2%, −32.3%) | $p < 0.0001$ |
| `claude-opus-5.5` model calls | 127 | 137 | +7.9% (−0.8%, +17.2%) | $p = 0.136$ (n.s.) |
| `claude-opus-5.5` passed | 29/29 | **29/29** | — | — |

Details by model:

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

### 3. Django 5.2 caller replication on `1.0.98` with `SCHEMA_VERSION = 4` import-alias resolution (`D01`–`D15`, 60 sessions)

- **Session start times:** October 26, 2026, 17:34–17:56 UTC (15 tasks per model, 60 sessions).
- **Import-alias resolution (`SCHEMA_VERSION = 4`):** `brainspace/symbol_index.py`
  (`SCHEMA_VERSION = 4`) now resolves `import a as b` and `from a import b as c` (minus shadowed
  function parameters), so `impact("django/contrib/auth/__init__.py::login")` finds
  `auth_login(...)` callers in `django/contrib/auth/views.py` (`D13`), bringing `D01`–`D15` caller
  recall from `54/56` to `56/56`.

| 15 Django tasks per model (`1.0.98`) | Stock | Full TokenMaster | Change (95% CI) |
| --- | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 707,799 | **293,779** | **−58.5%** (−64.4%, −52.3%; lower on 15/15) |
| `gpt-6-astra` cost, every first call cold | $3.40 | **$1.58** | **−53.5%** (−57.0%, −49.8%) |
| `gpt-6-astra` cost, as run (back to back) | $2.36 | **$0.69** | **−70.7%** (−76.6%, −63.4%) |
| `gpt-6-astra` passed | 15/15 | **15/15** | — |
| `claude-opus-5.5` raw tokens | 989,925 | **457,875** | **−53.7%** (−57.8%, −48.9%; lower on 15/15) |
| `claude-opus-5.5` cost, every first call cold | $1.81 | **$0.98** | **−46.0%** (−48.8%, −43.2%) |
| `claude-opus-5.5` cost, as run (back to back) | $1.11 | **$0.43** | **−61.2%** (−68.2%, −53.8%) |
| `claude-opus-5.5` passed | 15/15 | **15/15** | — |

- **`gpt-6-astra` (`D01`–`D15`):** Raw tokens `707,799` → **`293,779` (−58.5%; 95% CI −64.4% to
  −52.3%; lower on 15 of 15 tasks)**; cold-repriced cost `$3.40` → **`$1.58` (−53.5%)**; as-run
  cost `$2.36` → **`$0.69` (−70.7%)**; passed **15/15 vs 15/15**.
- **`claude-opus-5.5` (`D01`–`D15`):** Raw tokens `989,925` → **`457,875` (−53.7%; 95% CI −57.8% to
  −48.9%; lower on 15 of 15 tasks)**; cold-repriced cost `$1.81` → **`$0.98` (−46.0%)**; as-run
  cost `$1.11` → **`$0.43` (−61.2%)**; passed **15/15 vs 15/15**.

## Default GitHub routing on Copilot CLI `1.0.104` (October 27, 2026)

Every other run on this page sent Copilot CLI's requests through the evaluation relay in bring-your-own-model mode.
This run did not. Copilot CLI signed in with its own stored login and sent every request to GitHub's Copilot API
itself. Without a provider URL, the TokenMaster launcher adds the lean tool set, and `tokenmaster-nav` and the v6
`view` hook load. The bridge does not run, so there is no cache-stable system prompt and no request shaping.

The protocol and its decision rule were committed before the 30 study sessions
(`evidence/default-routing-20261027/PROTOCOL.md`, commit `1c84310`). The run is exploratory: unlike PRS-6, the
protocol was written after a probe and a pilot, which the analysis excludes.

### Setup

| Parameter | Value |
| --- | --- |
| Session start times | October 27, 2026, 14:19–14:30 UTC |
| Client | Copilot CLI `1.0.104`, the latest release, read from each session's own event log (30 of 30) |
| Routing | Copilot CLI's default GitHub routing with its own sign-in, a GitHub Enterprise Cloud account with data residency. No `COPILOT_PROVIDER_BASE_URL`, no relay. |
| Model | `gpt-6-astra` with PRS-6's flags (`--reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps --output-format json`) |
| Tasks | Django 5.2 commit `9e7cc2b6`, D01–D15, in PRS-6's two shards and orders, run at the same time |
| Versions | Stock; full TokenMaster `v0.2.0` (`setup.py` with graphify `0.9.91`, `brainspace_setup.py`, the launcher) |
| Measurement | Copilot CLI's own record of each model call (`session-store.db`, table `assistant_usage_events`): GitHub's token counts, GitHub's charge (`total_nano_aiu`) and GitHub's per-token prices. `tokenomics.py` reads the same table. |
| Isolation | One Copilot home and profile per version, outside the operator's profile folder. Before the first session, `copilot skill list` and `copilot instruction list` checked that neither version loaded skills or instruction files from outside the study. |
| Statistics | As in PRS-6: paired bootstrap over tasks, 10,000 resamples, seed 20261022; exact Wilcoxon; Holm over raw tokens and cold-repriced cost |
| Audit | All 30 sessions: version, model, one Copilot session per run, GitHub's charge equal to its token counts times its prices and to the CLI's own running total, results recounted from the per-call records. No problem found. |

### Results

| 15 Django tasks, `gpt-6-astra` | Stock | Full TokenMaster | Change (95% CI) | Wilcoxon / Holm $p$ |
| --- | ---: | ---: | ---: | ---: |
| Raw tokens | 708,928 | **372,621** | **−47.4%** (−52.8%, −41.7%; lower on 15/15) | $p < 0.0001$ / $p = 0.0001$ |
| Cost, every first call cold | $3.75 | **$2.05** | **−45.4%** (−48.2%, −42.7%; lower on 15/15) | $p < 0.0001$ / $p = 0.0001$ |
| Cost, as run (back to back) | $2.30 | **$1.26** | **−45.0%** (−49.4%, −40.5%) | $p < 0.0001$ |
| Model calls | 47 | 44 | −6.4% (−14.6%, +2.2%) | $p = 0.375$ (n.s.) |
| Passed | 15/15 | **15/15** | | |

`tokenmaster-nav` was used in 15 of 15 TokenMaster sessions (27 calls). The lean tool set removed the same 11 tools
for every prompt. With graphify `0.9.91`, `impact` finds all 56 answer-key callers of D01–D15
(`impact_recall-0.9.91.json`).

### The README hero numbers under default routing

`PROTOCOL.md` fixed the rule before the sessions: a hero number holds if the 95% CI of the reduction reaches it.

| README claim | Default routing, D01–D15 | Holds |
| --- | --- | --- |
| Up to 58% fewer tokens | 47.4% fewer (95% CI 41.7% to 52.8%) | No |
| Up to 54% lower cold-start cost | 45.4% lower (95% CI 42.7% to 48.2%) | No |
| No drop in pass rate | 15/15 stock, 15/15 TokenMaster | Yes |

TokenMaster used 52.6% of stock's raw tokens and 54.6% of its cold-repriced cost, close to half of each. The 58% and
54% figures are relay-mode results.

### Compared with the relay run (PRS-6, same tasks and model)

| `gpt-6-astra`, D01–D15 | Relay (PRS-6, `1.0.98`) | Default routing (`1.0.104`) |
| --- | ---: | ---: |
| Stock raw tokens | 707,799 | 708,928 |
| TokenMaster raw tokens | 293,779 | 372,621 |
| Raw-token change | −58.5% (−64.4%, −52.3%) | −47.4% (−52.8%, −41.7%) |
| Cold-repriced cost change | −53.5% (−57.0%, −49.8%) | −45.4% (−48.2%, −42.7%) |
| As-run cost change | −70.7% (−76.6%, −63.4%) | −45.0% (−49.4%, −40.5%) |
| Model calls, stock → TokenMaster | 55 → 46 | 47 → 44 |
| Stock first call: input / cached / written (medians) | 11,200 / 6,450 / 4,749 | 13,587 / 9,017 / 4,569 |
| TokenMaster first call: input / cached / written (medians) | 5,906 / 5,723 / 181 | 7,791 / 4,865 / 2,924 |
| `tokenmaster-nav` used | 15 of 15 sessions (23 calls) | 15 of 15 sessions (27 calls) |
| Passed, stock and TokenMaster | 15/15, 15/15 | 15/15, 15/15 |

What the numbers show:

- Stock used the same raw tokens with both routings; TokenMaster used 27% more under default routing. The smaller
  saving is on the TokenMaster side.
- Each call carried more tokens under default routing: stock 15,084 per call (relay 12,869) and TokenMaster 8,469
  (relay 6,387). Stock made 8 fewer calls than in PRS-6; TokenMaster made 2 fewer. Stock's fewer calls offset its
  larger calls, and TokenMaster's did not.
- The two runs differ in routing, and also in Copilot CLI build (`1.0.104` vs `1.0.98`), account (Copilot CLI's own
  sign-in vs the relay's), day, TokenMaster commit (`v0.2.0` vs `19443fc`) and lane location. In this run's pilot,
  stock first calls under default routing were 13,519 tokens on `1.0.98-2` and 13,587 on `1.0.104`. The relay control
  below separates routing from the rest on `1.0.104`.
- The as-run cost saving fell further than the token saving (−70.7% to −45.0%). With the bridge, TokenMaster's first
  calls wrote a median of 181 tokens to GitHub's cache; under default routing, without it, they wrote 2,924. The
  bridge was not switched on and off within one run, so its share of the gap was not tested. Back-to-back stock
  sessions also share a cached prefix under default routing: 14 of 15 stock first calls read a median of 9,017 tokens
  from the cache.

### Relay control on Copilot CLI `1.0.104` (same build, account and day)

The gap between PRS-6 and this run mixes routing with client build, account, day, lane location and TokenMaster
commit. A control run repeated PRS-6's evaluation relay (bring-your-own-model mode, `run_prs5_study.Relay`) with this
run's Copilot CLI `1.0.104`, lanes, graphify `0.9.91`, installed TokenMaster files, tasks and orders. The relay sent
Copilot CLI's own stored sign-in for this run's account to the Copilot API that GitHub names for that account,
because PRS-6's OpenCode sign-in no longer exists on this machine. The control and this run then differ in routing.
Copilot CLI posts `/responses` to the local relay, which forwards it over HTTPS, instead of using its own WebSocket
connection. It sends 18 tools instead of 20 in stock and 10 instead of 12 in TokenMaster: default routing adds
`web_fetch` and `semantic_code_search`. And in the TokenMaster arm the bridge's cache-stable system prompt and v6
shaping run, which need a provider URL. The 30 sessions ran on October 27, 23:08–23:20 UTC, about nine hours after
this run's (the protocol expected about two). The run is exploratory: its protocol and reading rule were committed
after a D01 pilot and lane test and before the 30 sessions (`evidence/relay-control-20261027/PROTOCOL.md`, commit
`02f5049`), and the analysis excludes the pilot and the lane test. Audit: all 30 sessions ran `1.0.104` (system prompt
and event log), `gpt-6-astra` answered every call, every call carried GitHub's charge, equal to its token counts at
its own prices, and every results row matched its recount. No problem found.

| `gpt-6-astra`, D01–D15 | Relay, `1.0.98` (PRS-6) | Relay, `1.0.104` (control) | Default routing, `1.0.104` |
| --- | ---: | ---: | ---: |
| Stock raw tokens | 707,799 | 708,801 | 708,928 |
| TokenMaster raw tokens | 293,779 | 364,319 | 372,621 |
| Raw-token change | −58.5% (−64.4%, −52.3%) | −48.6% (−54.1%, −41.9%) | −47.4% (−52.8%, −41.7%) |
| Cold-repriced cost change | −53.5% (−57.0%, −49.8%) | −45.8% (−48.8%, −42.6%) | −45.4% (−48.2%, −42.7%) |
| As-run cost change | −70.7% (−76.6%, −63.4%) | −64.9% (−71.2%, −58.0%) | −45.0% (−49.4%, −40.5%) |
| Model calls, stock → TokenMaster | 55 → 46 | 49 → 44 | 47 → 44 |
| Raw tokens per call, stock / TokenMaster | 12,869 / 6,387 | 14,465 / 8,280 | 15,084 / 8,469 |
| TokenMaster first call: input / cached / written (medians) | 5,906 / 5,723 / 181 | 7,614 / 7,447 / 164 | 7,791 / 4,865 / 2,924 |
| Passed, stock and TokenMaster | 15/15, 15/15 | 15/15, 15/15 | 15/15, 15/15 |

Between runs, resampling the 15 tasks 10,000 times:

- Routing moved TokenMaster's share of stock's raw tokens from 52.6% (default routing) to 51.4% (relay): −1.2 points,
  95% CI −4.9 to +2.0. For cold-repriced cost the difference is −0.4 points (−2.7 to +1.8). TokenMaster's raw tokens
  were 2.2% lower through the relay (−3.2% to −1.4%), and stock's were the same (0.0%, −5.5% to +7.2%).
- The other differences moved it from 41.5% (PRS-6) to 51.4%: +9.9 points (+4.9 to +14.5), and +7.8 points (+4.7 to
  +10.6) for cold-repriced cost. TokenMaster used 24.0% more raw tokens than in PRS-6 (+15.5% to +30.9%), stock the
  same (+0.1%, −7.6% to +8.4%), and stock made 11% fewer calls (−18.0% to −3.9%).
- By the reading rule fixed before the sessions, routing explains none of the 11.1-point raw-token gap or of the
  8.1-point cold-cost gap between PRS-6 and default routing: the routing CIs include 0, and the CIs for the rest
  exclude it. The routing CIs still allow up to 4.9 of the 11.1 points (44%) and 2.7 of the 8.1 (33%); the point
  estimates are 11% and 5%.
- One part of the rest is measured, and it interacts with routing. In the relay environment, Copilot CLI `1.0.104`
  sends two tool definitions that `1.0.98-2` does not, `run_dynamic_workflow` and `dynamic_workflows_manage`: 2,210
  cl100k tokens on every call (about 2,000 GitHub tokens), about a quarter of TokenMaster's first call and a sixth of
  stock's. TokenMaster's lean tool set removes neither. PRS-6's requests carried 16 tools in stock and 8 in
  TokenMaster, the control's 18 and 10. Under default routing, though, `1.0.98-2` already listed both tools (this
  run's pilot, in Copilot CLI's event log; the tool lists are in the control's `SETUP_OBSERVATIONS.md`, section 3), and
  D01's first stock call differed by 65 tokens between the two builds (13,519 vs 13,584). In relay mode, Copilot CLI
  `1.0.104` still sends the two tools and `1.0.98-2` does not. So how the gap splits between routing and the rest
  depends on which build the comparison holds fixed. Taking about 2,000 tokens off each call of the control would put
  TokenMaster at about 45% of stock's raw tokens instead of 51%, some 6 of the 9.9 points; that arithmetic assumes the
  sessions would make the same calls without the two tools, which was not tested.
- Routing does change the as-run cost. Through the relay, TokenMaster's as-run cost was 34.5% lower than under default
  routing (−44.6% to −24.1%), and its saving against stock was −64.9% instead of −45.0%. Its first calls wrote a
  median of 164 tokens to GitHub's cache through the relay and 2,924 under default routing; stock's as-run cost was
  about the same (+2.6%, −1.8% to +7.0%). The bridge's cache-stable system prompt runs only with a provider URL, which
  fits this, but no run switched the bridge on and off by itself.
- The control used 371.0 AI credits ($3.71) by GitHub's charges: a D01 pilot 34.3, a D01 lane test 18.3, the study
  318.4.

Evidence: `evidence/relay-control-20261027/` (`PROTOCOL.md`, `SETUP_OBSERVATIONS.md`, `analysis.json`, `analyze.py`,
`captures_audit.json`, `dead_upstream_probe*.json` and `dead_upstream_probe.py`, and per shard `results.jsonl`,
`setup.json`, `summary.json`, `warmup.json` and per-call `calls.jsonl`). Harness:
`token-master-plugin/evals/relay_control_ab.py`.

### Setup findings

- Copilot CLI loaded `CLAUDE.md` and skills from the ancestor folders of the probe's lanes, which were
  under `%TEMP%`, inside the operator's profile, which holds a `.claude` folder (a `CLAUDE.md` and 101 skill
  entries), `.copilot` (109) and `.agents` (93). From such a lane, `copilot skill list` showed the operator's skills as
  inherited, and `copilot instruction list` showed a `CLAUDE.md`. The probe's stock first call was 23,463 tokens; a
  stock session of the same build from a lane outside the profile sent 13,519, on a task prompt about 60 tokens longer
  (`SETUP_OBSERVATIONS.md`). The study's lanes were outside the profile, and a check before the first session found
  no inherited skill or instruction file.
- PRS-6's lanes were also under `%TEMP%`, written in the 8.3 form (`C:\Users\<SHORT~1>\...`) that Python's
  `tempfile.gettempdir()` returns on this machine. Copilot CLI inherits from that form, and not from the same folder
  written in full. The relay control's probe, which captures the first request without a model call, found the
  operator's `CLAUDE.md` in it from the 8.3 form, and an `available_skills` list of 25 skills where a clean lane lists
  the 2 built-in ones: about 10,300 extra cl100k tokens. That held with `1.0.98-2` and `1.0.104`, and with the
  launcher in place before October 27 (last written May 19, so most likely the one PRS-6 ran). From the long form,
  the first lane test's sessions and `copilot instruction list` found nothing
  (`evidence/relay-control-20261027/SETUP_OBSERVATIONS.md`). PRS-6's stock first calls, 11,194 to 11,205 tokens,
  are within 2.5% of the clean size (about 10,940 for `1.0.98-2`) and far from the inherited one (about 20,250), so
  its sessions did not carry the operator's files. Why not was not tested: PRS-6's build,
  `1.0.98`, is no longer on this machine.
- Under default routing, Copilot CLI's auto-update is on; relay mode turns it off. In the pilot, a session pinned to
  `1.0.98-2` downloaded `1.0.104`, and the next session in the same lane ran `1.0.104`. The study pinned the latest
  release. Setting `COPILOT_AUTO_UPDATE=false` does not help: the launcher then runs its built-in `1.0.49`.
- With graphify `0.9.17`, the only version left on this machine, `impact` found 51 of the 56 answer-key callers (D03:
  1 of 6; `impact_recall-0.9.17.json`). The study installed `0.9.91`, PRS-6's version, in its own environment.
- The probe, the pilot and the study used 488.58 AI credits ($4.89): probe 48.25, pilot 84.19, study 356.14.

Evidence: `evidence/default-routing-20261027/` (`PROTOCOL.md`, `SETUP_OBSERVATIONS.md`, `analysis.json`,
`analyze.py`, `impact_recall*.json`, and per shard `results.jsonl`, `setup.json`, `summary.json` and per-call
`calls.jsonl`). Harness: `token-master-plugin/evals/default_routing_ab.py`.

## Test parameters (October 18–22 exploratory `1.0.78-3` runs)

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

The October 18–22 real-CLI runs on this page used Copilot CLI **1.0.78-3**. Until October 23, 2026,
this page said 1.0.98. That was wrong. On October 26, 2026, the pre-registered PRS-6 study ran
Copilot CLI **1.0.98** ([Pre-registered study PRS-6](#pre-registered-study-prs-6-on-copilot-cli-1098-october-26-2026)).

- In the October 18–22 runs, the harness passed `--no-auto-update`. With that flag, the WinGet
  launcher runs its bundled build, 1.0.78-3, even when a newer package is installed. Without the
  flag, it runs the newest installed package, 1.0.98.
- The harness checked the version with `copilot --version`, without the flag. That printed 1.0.98.
- Copilot CLI writes its version into its own system prompt. All 403 local session captures from the
  Django runs of October 19 and 22 say "Version number: 1.0.78-3". The repository run, PRS-5 and the
  bridge checks of October 18–19 used the same flag.
- The harness now checks the version with the same flags as its sessions (`cli_version` in
  `evals/run_prs5_study.py`). With the October 18–22 flags, the check stops the harness, because
  `CLI_VERSION` names 1.0.98.
- In PRS-6 (October 26), pinning `COPILOT_CLI_DIST_DIR` to `1.0.98` and removing `--no-auto-update`
  ran Copilot CLI `1.0.98`, verified in 176 of 176 session captures (`Version number: 1.0.98`).

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
  (`evidence/copilot-version-probe-20261023/opus-1.0.98-output-limit.txt`). The probe and PRS-6
  used 32,000.
- The pre-registered PRS-6 study on October 26 confirmed these `1.0.98` cache patterns across 176
  live sessions ([Pre-registered study PRS-6](#pre-registered-study-prs-6-on-copilot-cli-1098-october-26-2026)).

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
  - With `claude-opus-5.5` on 1.0.78-3, 44 of 45 stock first calls also read part of the prompt
    from the cache, because Anthropic's layout puts the tool definitions before the system prompt.
    Stock first calls still wrote the system prompt to the cache: a median of 7,474 tokens. Full
    TokenMaster first calls wrote a median of 314. No run isolated the bridge's own effect with
    `claude-opus-5.5`.
  - On Copilot CLI `1.0.98` (PRS-6, 29-task primary benchmark), 28 of 29 stock `gpt-6-astra` first
    calls started warm (median `6,450` cached, `4,882` cache write), vs 27 of 29 TokenMaster
    (`5,721` cached, `322` cache write). With `claude-opus-5.5` on `1.0.98`, 28 of 29 stock first
    calls (median `11,226` cached, `7,265` cache write) and 28 of 29 TokenMaster (`8,762` cached,
    `543` cache write) started warm.
- **A cached prompt does not last.** One probe found it still there after 6.5 minutes and gone
  after 31 minutes. Sessions that start further apart start cold.
- **The cold re-pricing** treats every first call as a cache miss. The tokens that the first call
  read from the cache are re-priced as cache writes. It applies to every version.
- **The bridge runs only in bring-your-own-model mode.** With Copilot CLI's default GitHub routing,
  the cache-stable system prompt does not apply. The October 27 run measured that configuration on
  Django D01–D15: TokenMaster's first calls wrote a median of 2,924 tokens to the cache, against 181
  with the bridge in PRS-6 ([Default GitHub routing](#default-github-routing-on-copilot-cli-10104-october-27-2026)).

| Cost, full TokenMaster vs stock (95% CI) | `gpt-6-astra` | `claude-opus-5.5` |
| --- | ---: | ---: |
| Default routing (`1.0.104`), Django 15 tasks (`D01`–`D15`), as run | −45.0% (−49.4%, −40.5%) | not run |
| Default routing (`1.0.104`), Django 15 tasks (`D01`–`D15`), every first call cold | −45.4% (−48.2%, −42.7%) | not run |
| PRS-6 (`1.0.98`), repository 29 tasks, as run | −50.2% (−59.6%, −42.0%) | −40.1% (−48.2%, −32.3%) |
| PRS-6 (`1.0.98`), repository 29 tasks, every first call cold | −41.5% (−47.7%, −35.5%) | −34.0% (−38.7%, −29.3%) |
| PRS-6 (`1.0.98`), Django 15 tasks (`D01`–`D15`), as run | −70.7% (−76.6%, −63.4%) | −61.2% (−68.2%, −53.8%) |
| PRS-6 (`1.0.98`), Django 15 tasks (`D01`–`D15`), every first call cold | −53.5% (−57.0%, −49.8%) | −46.0% (−48.8%, −43.2%) |
| Exploratory (`1.0.78-3`), Django 45 tasks, as run | −79.9% (−82.0%, −77.6%) | −60.8% (−64.6%, −56.9%) |
| Exploratory (`1.0.78-3`), Django 45 tasks, every first call cold | −49.5% (−51.5%, −47.5%) | −46.0% (−48.0%, −44.0%) |
| Exploratory (`1.0.78-3`), repository 27 tasks, as run | −62.8% (−71.3%, −54.6%) | −51.2% (−59.2%, −43.0%) |
| Exploratory (`1.0.78-3`), repository 27 tasks, every first call cold | −40.8% (−47.1%, −34.6%) | −43.9% (−48.2%, −39.7%) |

Inference: for sessions that start far apart, the cold rows are the better estimate. They are
close to the raw-token saving.

## Result 1: 45 "who calls X?" tasks on Django 5.2 (October 22, Copilot CLI `1.0.78-3`)

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

## Result 2: 27 tasks on this repository (October 19, Copilot CLI `1.0.78-3`)

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
- These are raw `rg` outputs. Copilot's search tool shortens long results, and the models in
  Copilot CLI itself searched with narrower patterns (Result 1). So this table measures lookup output,
  not session cost.
- The same commit fixed a setup gap. `setup.py` left graphify's 9.5 MB `graphify-out/graph.json`
  visible to `rg`. Setup now adds `graphify-out/` to `.gitignore`.

Evidence: `evidence/grep-vs-graph-20261019/`. Commit `319d1b2`.

## Graphify version check (October 22) and `SCHEMA_VERSION = 4` import-alias resolution (October 26)

- Graphify was upgraded from 0.9.84 to 0.9.91. That was the newest version that the company
  package feed served. PyPI was not reachable directly, and the feed did not yet serve 0.9.92
  to 0.9.94.
- On the same Django commit, 0.9.91 built 50,858 nodes and 120,650 links, 33,094 of them calls.
  0.9.84 built 50,879 nodes and 118,194 links, 31,715 of them calls.
- With either version on `SCHEMA_VERSION = 3` (October 22), `impact` found 54 of the 56 answer-key
  callers for tasks D01–D15, because both missed calls through an import alias (in D13, `login` is
  imported as `auth_login`).
- On October 26 (`SCHEMA_VERSION = 4` in `brainspace/symbol_index.py`), import-alias resolution was
  added for `import a as b` and `from a import b as c` (minus shadowed function parameters). With
  `SCHEMA_VERSION = 4`, `impact("django/contrib/auth/__init__.py::login")` finds `auth_login(...)`
  callers in `django/contrib/auth/views.py` (`D13`), bringing `D01`–`D15` caller recall from `54/56`
  to `56/56` ([Pre-registered study PRS-6](#3-django-52-caller-replication-on-1098-with-schema_version--4-import-alias-resolution-d01d15-60-sessions)).

Evidence: `evidence/graphify-upgrade-20261022/` (commit `35bc10b`) and
`evidence/prs6-copilot-1.0.98-20261026/analysis.json`.

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

- **Pre-registered vs exploratory.** PRS-6 on Copilot CLI `1.0.98` (October 26) was pre-registered
  before any study call ([PRS6_PROTOCOL.md](PRS6_PROTOCOL.md), commit `19443fc`). The October 18–22
  runs on `1.0.78-3` were exploratory: no protocol was pre-registered, though the tasks were
  committed before each run except the first 10-task Django run (D01–D10, superseded; `dd1f38a`).
  The task types and the excluded tools were chosen by the team that builds TokenMaster.
- **Scope.** 1 run per task, 2 repositories and 2 models. The Django runs have one task type,
  "who calls X?". The runs on this repository have 27 (`1.0.78-3`) or 29 (`1.0.98`) tasks.
- **Copilot CLI version.** The October 18–22 runs used `1.0.78-3`; PRS-6 on October 26 used
  `1.0.98`. Copilot CLI `1.0.98` sends a smaller fixed prompt, and its stock first call can read
  part of the prompt from the cache when another session ran shortly before
  ([Copilot CLI version](#copilot-cli-version)).
- **Cost depends on timing.** The as-run costs come from back-to-back sessions. See
  [How to read the cost numbers](#how-to-read-the-cost-numbers).
- **Excluded tools.** The 11 tools were chosen because no session called them in the October 18
  runs. On October 19, one stock session (P13) called `task`. Workloads that need subagents
  (`task`), skills, session-store search, SQL or background PowerShell lose these tools.
  `--all-tools` keeps them. Such workloads were not measured.
- **Routing.** All runs except the October 27 default-routing run used bring-your-own-model mode
  through a relay, including the October 27 relay control. The default-routing run used Copilot
  CLI's default GitHub routing on Django D01–D15 with `gpt-6-astra` only. The repository tasks and
  `claude-opus-5.5` were not measured with default routing.
- **Sandbox location.** Copilot CLI loaded `CLAUDE.md` and skills from the operator's profile
  folder when a lane's path was written in its 8.3 form, which is how the October 19–26 runs
  recorded their lanes under `%TEMP%`. PRS-6's stock first calls (October 26) are within 2.5% of a
  clean request's size, so its sessions did not load them; the October 19–22 runs were not checked
  ([Setup findings](#setup-findings)).
- **No test runs.** No Python was on the agents' PATH, so no task asked an agent to run tests.
- **Edit grading.** The edit grader fails any content change outside the allowed paths. In the
  October 19 `1.0.78-3` run, a line-ending-only rewrite outside the allowed paths also failed
  (`H03`, `claude-opus-5.5`). In PRS-6 (`1.0.98`), `same_content()` ignores CRLF-only rewrites.
- **Cost scope.** Cost uses GitHub's per-token prices. It does not count premium requests or
  plan allowances.

## Reproduce

```powershell
$env:BRAINSPACE_TOKENIZER_FILE = "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
$py = ".\.token-master-dev\Scripts\python.exe"

# PRS-6 (Copilot CLI 1.0.98, October 26): recount captures, verify 1.0.98 version and nano_aiu, and compute CIs / Wilcoxon / Holm p.
& $py -B evidence\prs6-copilot-1.0.98-20261026\analyze.py

# Default GitHub routing (Copilot CLI 1.0.104, October 27): audit the committed per-call records, CIs and the hero check.
& $py -B evidence\default-routing-20261027\analyze.py

# Default-routing live run: Copilot CLI's own sign-in, no relay. Run both shards at the same time.
cd token-master-plugin\evals
& $py -B default_routing_ab.py --suite django --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D09,D01,D07,D03,D05,D04,D08,D02,D06,D10 --output <new folder>\django-rare --lanes drr --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 760
& $py -B default_routing_ab.py --suite django --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D12,D11,D14,D13,D15 --output <new folder>\django-common --lanes drc --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 400
cd ..\..

# Relay control (Copilot CLI 1.0.104, October 27): audit the committed per-call records, CIs and the reading rule.
& $py -B evidence\relay-control-20261027\analyze.py

# Relay control live run: PRS-6's relay with Copilot CLI's stored sign-in. Run both shards at the same time.
cd token-master-plugin\evals
& $py -B relay_control_ab.py --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D09,D01,D07,D03,D05,D04,D08,D02,D06,D10 --output <new folder>\relay-rare --lanes drr --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 320
& $py -B relay_control_ab.py --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D12,D11,D14,D13,D15 --output <new folder>\relay-common --lanes drc --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 240
cd ..\..

# Recount tokens and GitHub's charges from the committed 1.0.78-3 per-call records (no model calls).
& $py -B evidence\django-scale-20261022\audit.py evidence\django-scale-20261022

# Confidence intervals and the cold re-pricing for the October 18–22 1.0.78-3 runs.
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

# The 27-task or 29-task run on this repository.
& $py -B quick_copilot_ab.py --model gpt-6-astra --tasks <ids> --repeats 1 --lanes <name> --output <new folder>
```

Live runs need an active GitHub Copilot sign-in in OpenCode and an installed Copilot CLI. The
harness reads the credential in memory and never writes it. It stops unless the Copilot CLI
version that its sessions run equals `CLI_VERSION` in `run_prs5_study.py` (`1.0.98`). Pinning
`COPILOT_CLI_DIST_DIR` to `1.0.98` and omitting `--no-auto-update` runs Copilot CLI `1.0.98`;
passing `--no-auto-update` to the WinGet launcher selects its bundled `1.0.78-3` build instead.

`default_routing_ab.py` needs a Copilot CLI sign-in (`copilot login`) instead of OpenCode's. It copies only the
account names into each lane, and the token stays in Windows Credential Manager. It pins `PACKAGE` (`1.0.104`), keeps
its lanes in `C:\tm-lanes` (`TM_LANES_ROOT`), and stops before the first session if a lane loads skills or
instruction files from outside the study.

`relay_control_ab.py` uses the same Copilot CLI sign-in for the relay. It reads the account's token from Windows
Credential Manager into memory and sends it to the Copilot API that GitHub names for the account. It runs
`default_routing_ab.py`'s package, lanes and lane check, and stops the run if the Copilot API refuses the sign-in or a
session runs another Copilot CLI version.
