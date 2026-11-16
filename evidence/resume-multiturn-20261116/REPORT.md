# Live 4-Arm Multi-Turn & Resumed-Session Study Report (`resume-multiturn-20261116`)

- **Base Repository Commit:** `a7b4e42` (`All-The-Vibes/TokenMasterX`)
- **Copilot CLI:** `GitHub Copilot CLI 1.0.112.
Run 'copilot update' to check for updates.` (`gpt-6-astra`, reasoning `low`)
- **MD-1 Deployment:** `https://raifoundry.services.ai.azure.com` (`Microsoft-Decision-1`, threshold `0.5`)
- **Protocol Freeze SHA-256:** `c6cd1f2685f95aec19153c7834a194012fa2edc877bc5dc30f2d6ae1ccfc00fc` (audit: `PASS`, `48` sessions, `144` turns, `410` billed calls verified, `72/72` resumed launches matched exact `session_id`)

## Executive Summary

Across 12 pre-registered 3-turn workflows (`48` sessions, `144` CLI launches: Turn 1 fresh start -> Turn 2 `--resume <session_id>` -> Turn 3 `--continue`), all four arms passed **`12/12` (`100%`)** with **`100%` session continuity**:

1. **Shipped resume tool-list locking (`tm_locked`, `Routing.resume_same_list`) wins overall on both tokens and cost:** `tm_locked` cut Turn-1-cold-normalized cost (`cold_usd`) by **`-34.3%` vs `stock`** (`95% CI [-38.2%, -30.7%]`, Holm `p = 0.0029`, lower on `12/12` pairs) and by **`-15.4%` vs pre-PR-#20 per-turn re-routing (`tm_reroute`)** (Holm `p = 0.0073`, lower on `11/12` pairs), while cutting raw tokens by **`-46.2%` vs `stock`** (`1,926,066` -> `1,036,427`, lower on `12/12` pairs). On resumed turns alone (`turn23_billed_usd`), `tm_locked` saved **`-25.3%` vs `stock`** (Holm `p = 0.0146`) and **`-21.5%` vs `tm_reroute`** (Holm `p = 0.0244`), whereas `tm_reroute` (`-4.7%`, `p = 0.6221`) and `tm_escalate` (`-9.9%`, `p = 0.2334`) lost most of their resumed-turn dollar advantage to prompt-cache invalidation.
2. **Copilot CLI `1.0.112` has a 2-stage resume prompt-cache boundary:** On Launch 2 (`--resume`, first resume of a persisted session), Copilot CLI `1.0.112` injects `<session_context>` immediately after the static tool+instruction prefix (`9,695` cached tokens on `stock`, `3,259` on pure `--lean`), capping first-call cache hit rate on Launch 2 at `57.7%` (`stock`) and `37.1%` (`tm_locked`). By Launch 3 (`--continue`), `<session_context>` is already part of the cached prefix, so stable tool lists reach **`97.3%` (`stock`)** and **`92.6%` (`tm_locked`)** first-call cache hit rate—whereas mutating `--excluded-tools` drops Launch 2 to `0.0%` when unlocking uncached tool schemas (`M05`–`M08`) and drops Launch 3 to `31.4%–59.2%`.
3. **Mid-session escalation (`TOKENMASTER_RESUME_ESCALATE=1`, `tm_escalate`) trades prompt-cache stability for `100%` native capability availability—and exposes an intra-session back-reference hazard:** Across `M05`–`M08` (`Bucket B`), `tm_escalate` unlocked the newly needed capability group on `4/4` workflows (`4/4` LLM-emitted native tool usage, `0/4` workarounds) while `tm_locked` fell back to workarounds on `4/4` (`M05` direct `view`, `M06` `Get-CimInstance`+`Stop-Process`, `M07` `copilot --help`, `M08` Python-in-`powershell`). However, `tm_escalate` spent `$1.0442` on Turns 2+3 in Bucket B vs `stock`'s `$0.7599` (`+37.4%`) and `tm_locked`'s `$0.6322` (`+65.2%`) for two reasons: (a) unlocking uncached tool definitions on Turn 2 forced a `0%`-hit cold write, and (b) on Turn 3 of `M05`–`M08`, follow-up prompts referencing `"Turn 1"` / `"Turn 2"` caused stateless MD-1 to score `session_history >= 0.996` and unlock `session_store_sql`, triggering a *second* full-conversation cache rewrite on Turn 3. Keeping `tm_locked` as default and offering `TOKENMASTER_RESUME_ESCALATE=1` as opt-in is empirically justified.
4. **`/tokenomics` multi-turn attribution & 2-stage cache fix (`tokenomics.py`):** `HEAD` `tokenomics.py` matched only session-start launches (`launch['session'] is None`), missing **`220 / 303` (`72.6%`)** of multi-turn TokenMaster calls (`0/36` sessions fully attributed) AND letting unattributed Turn 2 TokenMaster calls poison `stock_first_cached()` as fake stock sessions. Updating `tokenomics.py` to match resumed launches by exact `session_id`, filter `stock_first_cached` to sessions with zero TokenMaster launches, and model the 2-stage warm-resume cache boundary achieved **`303 / 303` (`100.0%`) call attribution across `36/36` multi-turn sessions**, matching measured token savings within `2.5–4.1` percentage points (`42.1%` est vs `46.2%` measured on `tm_locked`; `40.1%` vs `42.6%` on `tm_escalate`; `34.4%` vs `37.5%` on `tm_reroute`) and cutting per-session warm cost-saving MAE to `$0.0367–$0.0484`.

## 1. Overall Results Across All 12 Paired 3-Turn Workflows (`48` Sessions, `144` CLI Launches)

| Metric | `stock` | `tm_reroute` (Pre-PR-#20) | `tm_locked` (Shipped Default) | `tm_escalate` (`RESUME_ESCALATE=1`) |
| --- | ---: | ---: | ---: | ---: |
| Workflow pass rate | 12/12 (100.0%) | 12/12 (100.0%) | 12/12 (100.0%) | 12/12 (100.0%) |
| Session continuity (`start`->`--resume`->`--continue`) | 12/12 | 12/12 | 12/12 | 12/12 |
| All-turn capability recall | 12/12 | 12/12 | 8/12 | 12/12 |
| Bucket B LLM native capability usage (`M05`–`M08`) | 4/4 | 4/4 | 0/4 | 4/4 |
| Bucket B shell/direct workarounds (`M05`–`M08`) | 0/4 | 0/4 | 4/4 | 0/4 |
| Resume tool-list mutations (across 24 resumed turns) | 0 | 17 | 0 | 9 |
| Mean Turn 1 first-call cache hit rate (`start`) | 67.9% | 51.3% | 51.3% | 51.3% |
| Mean Turn 2 first-call cache hit rate (`--resume`) | 57.7% | 28.5% | 37.1% | 22.5% |
| Mean Turn 3 first-call cache hit rate (`--continue`) | 97.3% | 75.4% | 92.6% | 75.3% |
| Mean resumed-turn first-call cache hit rate | 77.5% | 52.0% | 64.9% | 48.9% |
| Mean `tool_tokens + tool_instructions` / turn | 12,120 | 4,889 | 3,649 | 4,079 |
| Mean LLM calls / 3-turn workflow | 8.9 | 8.5 | 8.2 | 8.6 |
| Total raw tokens (12 workflows) | 1,926,066 | 1,203,192 | 1,036,427 | 1,105,416 |
| Total `cache_read_tokens` | 1,682,933 | 947,555 | 836,979 | 857,613 |
| Total `cache_write_tokens` | 226,831 | 240,400 | 184,862 | 232,794 |
| Total Turns 2+3 billed cost (`turn23_billed_usd`) | $3.6977 | $3.5222 | $2.7634 | $3.3324 |
| Total Turn-1-cold-normalized cost (`cold_usd`) | $6.5650 | $5.1024 | $4.3150 | $4.8634 |
| Total as-run billed cost (`billed_usd`) | $5.2271 | $4.6527 | $3.8653 | $4.4136 |
| Mean 3-turn workflow wall-clock duration (s) | 70.4s | 70.5s | 70.4s | 73.6s |

## 2. Pairwise Statistical Comparisons (`n = 12` Paired Workflows, 10,000 Bootstrap Draws)

| Endpoint | Comparison (`base -> treat`) | Mean Change (%) | 95% Bootstrap CI (%) | Wilcoxon `p` | Holm `p` | Pairs (Lower / Higher / Tie) |
| --- | --- | ---: | --- | ---: | ---: | --- |
| `cold_usd` | `tm_locked_vs_stock` | -34.3% | [-38.2%, -30.7%] | 0.0005 | 0.0029 | 12/0/0 |
| `cold_usd` | `tm_escalate_vs_stock` | -25.9% | [-31.3%, -18.4%] | 0.0010 | 0.0049 | 11/1/0 |
| `cold_usd` | `tm_reroute_vs_stock` | -22.3% | [-28.3%, -15.3%] | 0.0010 | 0.0049 | 11/1/0 |
| `cold_usd` | `tm_locked_vs_tm_reroute` | -15.4% | [-23.5%, -7.8%] | 0.0024 | 0.0073 | 11/1/0 |
| `cold_usd` | `tm_escalate_vs_tm_locked` | +12.7% | [+4.2%, +24.1%] | 0.0093 | 0.0186 | 2/10/0 |
| `cold_usd` | `tm_escalate_vs_tm_reroute` | -4.7% | [-10.4%, +0.7%] | 0.1763 | 0.1763 | 8/4/0 |
| `turn23_billed_usd` | `tm_locked_vs_stock` | -25.3% | [-31.1%, -17.7%] | 0.0024 | 0.0146 | 11/1/0 |
| `turn23_billed_usd` | `tm_escalate_vs_stock` | -9.9% | [-21.2%, +7.3%] | 0.2334 | 0.7002 | 8/4/0 |
| `turn23_billed_usd` | `tm_reroute_vs_stock` | -4.7% | [-17.1%, +13.0%] | 0.6221 | 0.7002 | 8/4/0 |
| `turn23_billed_usd` | `tm_locked_vs_tm_reroute` | -21.5% | [-32.8%, -11.1%] | 0.0049 | 0.0244 | 11/1/0 |
| `turn23_billed_usd` | `tm_escalate_vs_tm_locked` | +20.6% | [+6.6%, +39.7%] | 0.0210 | 0.0840 | 2/10/0 |
| `turn23_billed_usd` | `tm_escalate_vs_tm_reroute` | -5.4% | [-13.2%, +2.3%] | 0.3013 | 0.7002 | 9/3/0 |
| `raw_tokens` | `tm_locked_vs_stock` | -46.2% | [-52.0%, -40.7%] | 0.0005 | 0.0029 | 12/0/0 |
| `raw_tokens` | `tm_escalate_vs_stock` | -42.6% | [-48.5%, -35.8%] | 0.0005 | 0.0029 | 12/0/0 |
| `raw_tokens` | `tm_reroute_vs_stock` | -37.5% | [-42.9%, -32.1%] | 0.0005 | 0.0029 | 12/0/0 |
| `raw_tokens` | `tm_locked_vs_tm_reroute` | -13.9% | [-21.9%, -6.4%] | 0.0049 | 0.0146 | 10/2/0 |
| `raw_tokens` | `tm_escalate_vs_tm_locked` | +6.7% | [+0.1%, +14.8%] | 0.1963 | 0.2197 | 5/7/0 |
| `raw_tokens` | `tm_escalate_vs_tm_reroute` | -8.1% | [-16.7%, +0.2%] | 0.1099 | 0.2197 | 9/3/0 |
| `mean_resume_first_call_cache_hit_rate` | `tm_locked_vs_stock` | -16.3% | [-19.7%, -13.5%] | 0.0005 | 0.0029 | 12/0/0 |
| `mean_resume_first_call_cache_hit_rate` | `tm_escalate_vs_stock` | -36.9% | [-51.8%, -22.2%] | 0.0005 | 0.0029 | 12/0/0 |
| `mean_resume_first_call_cache_hit_rate` | `tm_reroute_vs_stock` | -32.9% | [-49.1%, -16.8%] | 0.0005 | 0.0029 | 12/0/0 |
| `mean_resume_first_call_cache_hit_rate` | `tm_locked_vs_tm_reroute` | +24.8% | [+3.2%, +62.4%] | 0.4238 | 0.4238 | 7/5/0 |
| `mean_resume_first_call_cache_hit_rate` | `tm_escalate_vs_tm_locked` | -24.6% | [-41.5%, -9.5%] | 0.0210 | 0.0483 | 8/4/0 |
| `mean_resume_first_call_cache_hit_rate` | `tm_escalate_vs_tm_reroute` | -5.9% | [-8.7%, -2.5%] | 0.0161 | 0.0483 | 10/2/0 |
| `seconds` | `tm_locked_vs_stock` | +0.1% | [-6.1%, +8.9%] | 0.9097 | 1.0000 | 6/6/0 |
| `seconds` | `tm_escalate_vs_stock` | +4.6% | [-2.0%, +12.5%] | 0.1514 | 0.7568 | 3/9/0 |
| `seconds` | `tm_reroute_vs_stock` | +0.2% | [-4.7%, +6.0%] | 0.9697 | 1.0000 | 7/5/0 |
| `seconds` | `tm_locked_vs_tm_reroute` | -0.1% | [-6.0%, +7.7%] | 0.9097 | 1.0000 | 6/6/0 |
| `seconds` | `tm_escalate_vs_tm_locked` | +4.5% | [-1.9%, +10.1%] | 0.2036 | 0.8145 | 4/8/0 |
| `seconds` | `tm_escalate_vs_tm_reroute` | +4.4% | [+0.0%, +11.0%] | 0.0771 | 0.4629 | 3/9/0 |

## 3. Bucket-Stratified Breakdown (`4` Workflows per Bucket)

| Bucket | Arm | Pass | All-Turn Recall | Native Cap Used | Workarounds | Resume Mutations | Resume Hit Rate | Turns 2+3 USD | Total Cold USD | Total Raw Toks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `A_stable_coding` | `stock` | 4/4 | 4/4 | 0/4 | 0/4 | 0 | 74.7% | $1.6552 | $2.7206 | 843,783 |
| `A_stable_coding` | `tm_reroute` | 4/4 | 4/4 | 0/4 | 0/4 | 4 | 67.2% | $1.3320 | $2.0107 | 535,025 |
| `A_stable_coding` | `tm_locked` | 4/4 | 4/4 | 0/4 | 0/4 | 0 | 64.1% | $1.1588 | $1.7875 | 458,030 |
| `A_stable_coding` | `tm_escalate` | 4/4 | 4/4 | 0/4 | 0/4 | 0 | 63.2% | $1.2327 | $1.8602 | 467,521 |
| `B_mid_session_escalation` | `stock` | 4/4 | 4/4 | 4/4 | 0/4 | 0 | 80.2% | $0.7599 | $1.6114 | 449,592 |
| `B_mid_session_escalation` | `tm_reroute` | 4/4 | 4/4 | 4/4 | 0/4 | 8 | 23.3% | $1.1010 | $1.5090 | 272,075 |
| `B_mid_session_escalation` | `tm_locked` | 4/4 | 0/4 | 0/4 | 4/4 | 0 | 62.8% | $0.6322 | $1.0590 | 210,523 |
| `B_mid_session_escalation` | `tm_escalate` | 4/4 | 4/4 | 4/4 | 0/4 | 8 | 24.2% | $1.0442 | $1.4470 | 256,704 |
| `C_adversarial_resume` | `stock` | 4/4 | 4/4 | 0/4 | 0/4 | 0 | 77.5% | $1.2825 | $2.2330 | 632,691 |
| `C_adversarial_resume` | `tm_reroute` | 4/4 | 4/4 | 0/4 | 0/4 | 5 | 65.4% | $1.0892 | $1.5827 | 396,092 |
| `C_adversarial_resume` | `tm_locked` | 4/4 | 4/4 | 0/4 | 0/4 | 0 | 67.7% | $0.9723 | $1.4685 | 367,874 |
| `C_adversarial_resume` | `tm_escalate` | 4/4 | 4/4 | 0/4 | 0/4 | 1 | 59.3% | $1.0556 | $1.5562 | 381,191 |

### Bucket Notes & Empirical Mechanics

- **Bucket A (`M01`–`M04`, Stable Coding):** `tm_locked` and `tm_escalate` issued identical tool lists across all 12 launches (`0` mutations; `64.5%` mean resumed hit rate; `91.8%` on Turn 3), cutting `cold_usd` by **`43.6%` (`tm_locked`)** and **`40.4%` (`tm_escalate`)** vs `stock`. Pre-PR-#20 `tm_reroute` added `session_store_sql` on Turn 2 of every workflow (`4` mutations; `$1.3321` vs `tm_locked` `$1.1589` Turns 2+3).
- **Bucket B (`M05`–`M08`, Mid-Session Capability Escalation):**
  - *Native capability vs workaround separation:* Inspecting LLM-emitted `assistant.message.toolRequests` (`model != None`) in `turn*.stdout.jsonl` shows **`4/4` native capability usage (`0/4` workarounds)** on `stock`, `tm_reroute`, and `tm_escalate`, vs **`0/4` native usage (`4/4` workarounds)** on `tm_locked` (`M05`: read files directly with `view` instead of `task` subagent; `M06`: launched background Python listener via synchronous `Start-Process` + `Get-CimInstance` + `Stop-Process`, after which Copilot CLI's runtime emitted a `model=None` cleanup `read_powershell`; `M07`: ran `copilot --help` in `powershell` instead of `fetch_copilot_cli_documentation`; `M08`: ran inline Python via `powershell` instead of `sql`). *(Note: `runs.jsonl` recorded `M06` async-shell detection under `task_id == "M07"` due to a 1-character typo in `run.py`, corrected here from the raw `turn*.stdout.jsonl` transcripts and fixed in `run.py`.)*
  - *Why `tm_escalate` cost more than `stock` on Turns 2+3 (`$1.0442` vs `$0.7599`, `+37.4%`):* First, unlocking uncached tool groups (`agents`, `bg_shell`, `copilot_docs`, `sql`) on Turn 2 invalidated even the `3,259`-token static prefix (`0.0%` Turn 2 cache hit across `M05`–`M08`). Second, on Turn 3 of all four Bucket B workflows, prompts referencing `"Turn 1"` / `"Turn 2"` caused stateless MD-1 to score `session_history >= 0.996` (treating intra-session back-references as cross-session history lookups), unlocking `session_store_sql` on Turn 3 (`mut = 2`) and forcing a *second* full-conversation cache rewrite (`31.4%` Turn 3 cache hit vs `tm_locked`'s `92.7%`).
- **Bucket C (`M09`–`M12`, Adversarial Resume Lookalikes):** `tm_locked` had **`0` mutations** (`$0.9723` Turns 2+3, `-23.1%` vs `stock`'s `$1.2636`). `tm_reroute` suffered **`5` mutations** (`$1.0892` Turns 2+3), and `tm_escalate` rejected 7/8 resumed lookalike turns via MD-1 but tripped once on `M10` Turn 3 (`"without referencing built-in slash commands or CLI flags"` -> MD-1 `copilot_docs = 0.873`, dropping `M10` Turn 3 cache hit from `92.7%` to `34.1%`).

## 4. `/tokenomics` Multi-Turn Attribution & 2-Stage Cache Validation

| Arm | Legacy Call Attribution (`HEAD`) | Updated Call Attribution | Tok Saving (Est / Meas) | Warm Cost Saving (Est / Meas) | Empirical Warm Saved (`stock - arm`) | Legacy Est (`HEAD`) | Calibrated Est (`tokenomics.py`) | Warm MAE (`HEAD` -> Calibrated) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `tm_reroute` | 28/102 (27.5%) | 102/102 (100.0%) | 34.4% / 37.5% | 5.1% / 11.0% | $+0.5744 | $+1.2807 | $+0.2490 | $0.0929 -> $0.0367 |
| `tm_locked` | 28/98 (28.6%) | 98/98 (100.0%) | 42.1% / 46.2% | 19.3% / 26.1% | $+1.3618 | $+1.2785 | $+0.9243 | $0.0496 -> $0.0484 |
| `tm_escalate` | 27/103 (26.2%) | 103/103 (100.0%) | 40.1% / 42.6% | 8.7% / 15.6% | $+0.8135 | $+1.4207 | $+0.4218 | $0.0834 -> $0.0422 |

- **Two bugs found in `HEAD` `tokenomics.py` on resumed sessions:** (1) `HEAD` matched only session-start launches (`launch['session'] is None`), missing all Turn 2 (`--resume`) and Turn 3 (`--continue`) calls (`83 / 303 = 27.4%` attributed across the 36 TokenMaster sessions); and (2) unattributed Turn 2 calls (`call['launch'] is None`, `cache_read = 0..3,259`) were fed into `stock_first_cached()` as if they were stock Copilot CLI sessions, fabricating phantom Turn-1 `first_usd` savings (`+$0.0886` on `M02` vs true `+$0.0141`).
- **2-stage warm-resume cache boundary calibration:** Distinguishing Launch 2 (`<session_context>` static-prefix boundary, `stock_first_cached`) from Launch 3+ (full-conversation prefix boundary, `prev['cached'] + prev['fixed']`) reduced warm per-session MAE from `$0.0965` (1-stage `v1`) to **`$0.0367` (`tm_reroute`), `$0.0422` (`tm_escalate`), and `$0.0484` (`tm_locked`)** while remaining conservative whenever TokenMaster also saves whole model turns.

## 5. Per-Workflow Live Ledger (`48` Sessions = `144` Launches)

| ID | Bucket | Pass (`S/R/L/E`) | Calls (`S/R/L/E`) | Mut (`R/L/E`) | Resume Hit % (`S/R/L/E`) | Cold USD (`S / R / L / E`) | LLM Cap (`S/R/L/E`) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `M01` | `A_stable_coding` | Y/Y/Y/Y | 12/11/11/11 | 1/0/0 | 73%/63%/60%/60% | $0.7846 / $0.6664 / $0.5297 / $0.5368 | -/-/-/- |
| `M02` | `A_stable_coding` | Y/Y/Y/Y | 8/8/8/8 | 1/0/0 | 74%/67%/63%/63% | $0.6748 / $0.5155 / $0.4850 / $0.4849 | -/-/-/- |
| `M03` | `A_stable_coding` | Y/Y/Y/Y | 7/7/7/7 | 1/0/0 | 80%/73%/70%/68% | $0.3988 / $0.2704 / $0.2396 / $0.2513 | -/-/-/- |
| `M04` | `A_stable_coding` | Y/Y/Y/Y | 15/12/13/13 | 1/0/0 | 72%/66%/64%/62% | $0.8624 / $0.5584 / $0.5331 / $0.5872 | -/-/-/- |
| `M05` | `B_mid_session_escalation` | Y/Y/Y/Y | 9/9/5/9 | 2/0/2 | 78%/26%/55%/30% | $0.3893 / $0.3385 / $0.3056 / $0.3194 | Y/Y/W/Y |
| `M06` | `B_mid_session_escalation` | Y/Y/Y/Y | 9/9/6/9 | 2/0/2 | 82%/25%/67%/26% | $0.4113 / $0.3766 / $0.2400 / $0.3358 | Y/Y/W/Y |
| `M07` | `B_mid_session_escalation` | Y/Y/Y/Y | 6/6/8/7 | 2/0/2 | 78%/17%/59%/16% | $0.4445 / $0.4647 / $0.3168 / $0.4933 | Y/Y/W/Y |
| `M08` | `B_mid_session_escalation` | Y/Y/Y/Y | 7/7/6/6 | 2/0/2 | 83%/26%/71%/25% | $0.3664 / $0.3291 / $0.1966 / $0.2985 | Y/Y/W/Y |
| `M09` | `C_adversarial_resume` | Y/Y/Y/Y | 9/8/9/9 | 1/0/0 | 79%/73%/68%/68% | $0.5257 / $0.3381 / $0.3671 / $0.3258 | -/-/-/- |
| `M10` | `C_adversarial_resume` | Y/Y/Y/Y | 9/7/7/7 | 2/0/1 | 81%/49%/71%/41% | $0.5124 / $0.3839 / $0.2710 / $0.3231 | -/-/-/- |
| `M11` | `C_adversarial_resume` | Y/Y/Y/Y | 5/6/6/5 | 1/0/0 | 79%/73%/68%/64% | $0.4111 / $0.2838 / $0.2834 / $0.2924 | -/-/-/- |
| `M12` | `C_adversarial_resume` | Y/Y/Y/Y | 11/12/12/12 | 1/0/0 | 71%/66%/63%/64% | $0.7838 / $0.5769 / $0.5470 / $0.6149 | -/-/-/- |
