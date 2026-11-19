# Research Direction R2 Confirmation Study Report — Round `k = 2` (`r2-stateful-routing-confirm-20261120`)

## 1. Executive Summary

- **Scope:** `32` pre-registered fresh 3-turn workflows (`C01`–`C32`, `max_jaccard = 0.533 < 0.55` vs all `113` prior prompts) × `3` arms = **`96` live sessions (`288` `GitHub Copilot CLI 1.0.112` launches)** on `gpt-6-astra` (`reasoning_effort=low`), base commit `a9275d8`.
- **Pre-registration & offline integrity:** `PROTOCOL.sha256` verified (`7e4034d15391c410...`), `local_router.py` (`0d31ba26701ed627...`) and `local_router_weights.py` (`7cbf4f71ab5d5616...`, payload `3e9c577ba4f7dae8...`) frozen prior to task generation; `0` aborts; `96/96` (`100%`) single-session continuity across `start` → `--resume <sid>` → `--continue`; `96/96` launches on `tm_r2` verified `100%` offline (`router='r2'`).
- **Shared two-round `Gate.lean` + `Bet.lean` certification (`brainspace/certification.py`):** Excluding `65` search/distillation prompts (`CASES`+`HELD_OUT`), replaying Round `k = 1` (`S01`–`S16`, $\alpha_1 = 0.030396$, `not_certified`), and evaluating Confirmation Round `k = 2` (`C01`–`C32`, $\alpha_2 = 0.007599$, cumulative $\alpha_1 + \alpha_2 = 0.037995 < 0.05$) yields **`decision = 'not_certified'`** (`harm_count = 2` vs limit `1`, `help_count = 0`, `mean_token_saving = 61,362.2`, `max_bet_v1_wealth = 1.0162 >= 1.0` (`max_bet_v1_passes = True`), `verified_replay = True`).
- **End-to-end savings vs Stock (H1):** `tm_r2` passed **`26/32` (`81.2%`)** workflows vs `stock` **`28/32` (`87.5%`)**, cutting cold-normalized session cost by **`-37.87%`** (95% CI `[-40.914, -33.912]%`, Holm $p = 2.79e-09$) and total raw tokens by **`-50.11%`**.
- **Zero-network routing latency vs Cloud `MD-1` (H2):** Local `tm_r2` ran in **`36.487 ms` median** (`70.429 ms` p90, including SQLite warm-cache lookup) vs cloud `MD-1` **`914.5 ms` median** (`1121.9 ms` p90) — a **`25.1x` live launcher speedup** (Holm $p = 1.86e-09$).
- **Warm-cache preservation & Turn 2+3 savings vs Cloud `tm_md1_v1` (H3 & H4):** `tm_r2` recorded **`0`** unneeded mid-session tool-list mutations vs **`6`** on `tm_md1_v1`, lifting mean resumed first-call prompt-cache hit rate from **`58.22%`** to **`65.19%`** (Holm $p = 0.183783$) and cutting Turn-2+3 billed USD by **`-24.97%`** (Holm $p = 0.012170$).

---

## 2. Overall 3-Arm Summary (`N = 32` Workflows per Arm)

| Arm | Pass | Cold USD (sum / mean) | Turn 2+3 Billed USD (mean) | Raw Tokens (mean) | Resumed 1st-Call Cache Hit | Esc. Recall (`B+C`) | Native Tool Used (`B+C`) | Unneeded Tool Muts | Router Latency Median / p90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stock` | `28/32` (`87.5%`) | `$13.3155` / `$0.4161` | `$0.1810` | `122,465` | `80.38%` | `16/16` | `16/16` | `0` | — |
| `tm_md1_v1` | `27/32` (`84.4%`) | `$9.8181` / `$0.3068` | `$0.1852` | `68,834` | `58.22%` | `14/16` | `14/16` | `6` | `914.472 ms` / `1121.905 ms` |
| `tm_r2` | `26/32` (`81.2%`) | `$8.2733` / `$0.2585` | `$0.1390` | `61,103` | `65.19%` | `13/16` | `13/16` | `0` | `36.487 ms` / `70.429 ms` |

---

## 3. Bucket Breakdown (`8` Workflows × `3` Turns per Bucket)

| Bucket | Arm | Pass | Cold USD Mean | Turn 2+3 Billed USD Mean | Raw Tokens Mean | Resumed 1st-Call Cache Hit | Esc. Recall | Unneeded Muts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `A_stable_coding` | `stock` | `8/8` | `$0.3790` | `$0.1647` | `102,901` | `81.13%` | — | `0` |
| `A_stable_coding` | `tm_md1_v1` | `8/8` | `$0.2461` | `$0.1282` | `58,702` | `71.36%` | — | `0` |
| `A_stable_coding` | `tm_r2` | `8/8` | `$0.2208` | `$0.1142` | `49,000` | `67.62%` | — | `0` |
| `B_escalation_and_intra_deixis` | `stock` | `6/8` | `$0.3865` | `$0.1498` | `110,602` | `80.53%` | `8/8` | `0` |
| `B_escalation_and_intra_deixis` | `tm_md1_v1` | `6/8` | `$0.3975` | `$0.2742` | `76,140` | `41.56%` | `8/8` | `4` |
| `B_escalation_and_intra_deixis` | `tm_r2` | `6/8` | `$0.2711` | `$0.1475` | `60,739` | `59.83%` | `7/8` | `0` |
| `C_cross_session_recall` | `stock` | `7/8` | `$0.3580` | `$0.1504` | `103,776` | `82.47%` | `8/8` | `0` |
| `C_cross_session_recall` | `tm_md1_v1` | `6/8` | `$0.2489` | `$0.1500` | `57,381` | `56.56%` | `6/8` | `1` |
| `C_cross_session_recall` | `tm_r2` | `5/8` | `$0.2171` | `$0.1180` | `51,390` | `66.00%` | `6/8` | `0` |
| `D_warm_cache_lookalikes` | `stock` | `7/8` | `$0.5410` | `$0.2593` | `172,581` | `77.38%` | — | `0` |
| `D_warm_cache_lookalikes` | `tm_md1_v1` | `7/8` | `$0.3348` | `$0.1884` | `83,113` | `63.40%` | — | `1` |
| `D_warm_cache_lookalikes` | `tm_r2` | `7/8` | `$0.3252` | `$0.1760` | `83,282` | `67.29%` | — | `0` |

---

## 4. Pre-Registered Hypotheses & Holm-Bonferroni Inference (`N = 32`)

| Hypothesis | Comparison | Metric / Effect | Raw two-sided $p$ | Holm-Bonferroni $p$ | Significant ($\alpha=0.05$) |
|---|---|---|---:|---:|:---:|
| `H1_cold_usd_vs_stock` | `tm_r2 vs stock (N=32)` | cold_usd -37.87% (95% CI [-40.914, -33.912]%) | `9.31e-10` | `2.79e-09` | YES |
| `H2_router_latency_vs_md1` | `tm_r2 vs tm_md1_v1 (N=32 workflows / 96 launches)` | median 36.487 ms vs 914.5 ms (25.1x faster) | `4.66e-10` | `1.86e-09` | YES |
| `H3_resume_cache_hit_vs_md1_v1` | `tm_r2 vs tm_md1_v1 (N=32)` | resumed 1st-call cache hit 65.19% vs 58.22%, unneeded muts 0 vs 6 | `0.183783` | `0.183783` | no |
| `H4_turn23_billed_usd_vs_md1_v1` | `tm_r2 vs tm_md1_v1 (N=32)` | turn23_billed_usd -24.97% (95% CI [-38.162, -9.044]%) | `0.006085` | `0.012170` | YES |

---

## 5. Per-Workflow Matrix (`C01`–`C32`)

| Task | Bucket | Kind | `stock` | `tm_md1_v1` (muts / hit) | `tm_r2` (muts / hit) | `tm_r2` vs `stock` Cold Δ% | `tm_r2` vs `md1_v1` T2+3 Δ% |
|---|---|---|---|---|---|---:|---:|
| `C01` | `A_stable_coding` | `investigate` | `PASS` `$0.3076` | `PASS` `$0.1579` (`0` / `74%`) | `PASS` `$0.1975` (`0` / `48%`) | `-35.8%` | `+59.6%` |
| `C02` | `A_stable_coding` | `investigate` | `PASS` `$0.3141` | `PASS` `$0.1818` (`0` / `72%`) | `PASS` `$0.1650` (`0` / `73%`) | `-47.5%` | `-13.9%` |
| `C03` | `A_stable_coding` | `investigate` | `PASS` `$0.3407` | `PASS` `$0.2780` (`0` / `79%`) | `PASS` `$0.1894` (`0` / `70%`) | `-44.4%` | `-21.2%` |
| `C04` | `A_stable_coding` | `investigate` | `PASS` `$0.3116` | `PASS` `$0.1622` (`0` / `73%`) | `PASS` `$0.1625` (`0` / `73%`) | `-47.9%` | `+0.1%` |
| `C05` | `A_stable_coding` | `edit` | `PASS` `$0.4559` | `PASS` `$0.3464` (`0` / `70%`) | `PASS` `$0.2766` (`0` / `69%`) | `-39.3%` | `-30.0%` |
| `C06` | `A_stable_coding` | `edit` | `PASS` `$0.4492` | `PASS` `$0.2760` (`0` / `68%`) | `PASS` `$0.2606` (`0` / `69%`) | `-42.0%` | `-8.1%` |
| `C07` | `A_stable_coding` | `edit` | `PASS` `$0.4146` | `PASS` `$0.2509` (`0` / `70%`) | `PASS` `$0.2487` (`0` / `69%`) | `-40.0%` | `-1.8%` |
| `C08` | `A_stable_coding` | `edit` | `PASS` `$0.4383` | `PASS` `$0.3156` (`0` / `64%`) | `PASS` `$0.2659` (`0` / `68%`) | `-39.3%` | `-18.9%` |
| `C09` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.3315` | `PASS` `$0.2554` (`1` / `76%`) | `PASS` `$0.3847` (`1` / `47%`) | `+16.1%` | `+84.5%` |
| `C10` | `B_escalation_and_intra_deixis` | `investigate` | `FAIL` `$0.3737` | `FAIL` `$0.2179` (`1` / `78%`) | `FAIL` `$0.2385` (`1` / `77%`) | `-36.2%` | `+5.3%` |
| `C11` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.3797` | `PASS` `$0.3457` (`1` / `50%`) | `PASS` `$0.2710` (`1` / `49%`) | `-28.6%` | `-34.1%` |
| `C12` | `B_escalation_and_intra_deixis` | `investigate` | `FAIL` `$0.4876` | `FAIL` `$0.6764` (`2` / `19%`) | `FAIL` `$0.2897` (`0` / `65%`) | `-40.6%` | `-76.2%` |
| `C13` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.3727` | `PASS` `$0.3063` (`2` / `60%`) | `PASS` `$0.2309` (`1` / `70%`) | `-38.0%` | `-49.3%` |
| `C14` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.3747` | `PASS` `$0.5002` (`2` / `0%`) | `PASS` `$0.2479` (`1` / `49%`) | `-33.9%` | `-62.6%` |
| `C15` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.3592` | `PASS` `$0.5021` (`2` / `0%`) | `PASS` `$0.2100` (`1` / `72%`) | `-41.5%` | `-74.0%` |
| `C16` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.4130` | `PASS` `$0.3757` (`1` / `49%`) | `PASS` `$0.2962` (`1` / `49%`) | `-28.3%` | `-30.5%` |
| `C17` | `C_cross_session_recall` | `investigate` | `PASS` `$0.3330` | `FAIL` `$0.1549` (`1` / `73%`) | `PASS` `$0.2460` (`1` / `49%`) | `-26.1%` | `+139.7%` |
| `C18` | `C_cross_session_recall` | `investigate` | `PASS` `$0.3303` | `PASS` `$0.3041` (`2` / `22%`) | `PASS` `$0.1814` (`1` / `79%`) | `-45.1%` | `-56.8%` |
| `C19` | `C_cross_session_recall` | `investigate` | `PASS` `$0.3295` | `PASS` `$0.2171` (`1` / `83%`) | `PASS` `$0.1800` (`1` / `79%`) | `-45.4%` | `-29.2%` |
| `C20` | `C_cross_session_recall` | `investigate` | `PASS` `$0.3394` | `PASS` `$0.1904` (`1` / `78%`) | `PASS` `$0.1931` (`1` / `78%`) | `-43.1%` | `+0.6%` |
| `C21` | `C_cross_session_recall` | `investigate` | `PASS` `$0.3669` | `PASS` `$0.2579` (`1` / `49%`) | `FAIL` `$0.1753` (`0` / `73%`) | `-52.2%` | `-50.7%` |
| `C22` | `C_cross_session_recall` | `investigate` | `PASS` `$0.3492` | `PASS` `$0.2539` (`1` / `48%`) | `PASS` `$0.2617` (`1` / `48%`) | `-25.0%` | `+5.1%` |
| `C23` | `C_cross_session_recall` | `investigate` | `FAIL` `$0.4121` | `FAIL` `$0.2856` (`1` / `48%`) | `FAIL` `$0.2922` (`1` / `50%`) | `-29.1%` | `+1.1%` |
| `C24` | `C_cross_session_recall` | `investigate` | `PASS` `$0.4031` | `PASS` `$0.3271` (`1` / `52%`) | `FAIL` `$0.2071` (`0` / `72%`) | `-48.6%` | `-51.9%` |
| `C25` | `D_warm_cache_lookalikes` | `investigate` | `FAIL` `$0.3956` | `FAIL` `$0.2074` (`0` / `71%`) | `FAIL` `$0.2002` (`0` / `72%`) | `-49.4%` | `-5.2%` |
| `C26` | `D_warm_cache_lookalikes` | `investigate` | `PASS` `$0.3696` | `PASS` `$0.2346` (`0` / `67%`) | `PASS` `$0.2295` (`0` / `67%`) | `-37.9%` | `-3.0%` |
| `C27` | `D_warm_cache_lookalikes` | `investigate` | `PASS` `$1.0181` | `PASS` `$0.5549` (`0` / `57%`) | `PASS` `$0.5592` (`0` / `60%`) | `-45.1%` | `-8.3%` |
| `C28` | `D_warm_cache_lookalikes` | `investigate` | `PASS` `$0.3867` | `PASS` `$0.3182` (`1` / `39%`) | `PASS` `$0.2397` (`0` / `67%`) | `-38.0%` | `-40.3%` |
| `C29` | `D_warm_cache_lookalikes` | `edit` | `PASS` `$0.4475` | `PASS` `$0.2474` (`0` / `69%`) | `PASS` `$0.2738` (`0` / `68%`) | `-38.8%` | `+12.6%` |
| `C30` | `D_warm_cache_lookalikes` | `edit` | `PASS` `$0.5831` | `PASS` `$0.3715` (`0` / `71%`) | `PASS` `$0.3722` (`0` / `71%`) | `-36.2%` | `+0.2%` |
| `C31` | `D_warm_cache_lookalikes` | `edit` | `PASS` `$0.6691` | `PASS` `$0.4695` (`0` / `62%`) | `PASS` `$0.4540` (`0` / `62%`) | `-32.2%` | `-0.2%` |
| `C32` | `D_warm_cache_lookalikes` | `edit` | `PASS` `$0.4579` | `PASS` `$0.2750` (`0` / `71%`) | `PASS` `$0.2729` (`0` / `71%`) | `-40.4%` | `-2.2%` |

---

## 6. Shared Two-Round Proof-Backed Certification (`Gate.lean` + `Bet.lean`)

- **Rule version:** `harm-margin-max-bet-tokens-v1` (`quality_margin = 0.25`, `token_test = 'max-bet-v1'`, `token_cap = 300,000`, `minimum_token_reduction = 2,500`)
- **Holdout exclusion:** `65` search/distillation prompts (`CASES` + `HELD_OUT`) permanently excluded before Round 1
- **Round `k = 1` replay (`S01`–`S16`, `n = 16`):** `alpha_1 = 0.030396`, `decision = 'not_certified'`
- **Round `k = 2` confirmation (`C01`–`C32`, `n = 32`):** `alpha_2 = 0.007599`, cumulative family-wise `alpha_1 + alpha_2 = 0.037995 < 0.05`
- **Quality gate (`Gate.lean`):** `harm_count = 2` (limit `1`), `help_count = 0`, `quality_difference_lower = -1.000000`
- **Token savings gate (`Bet.lean`):** `mean_token_saving = 61,362.2` tokens (`max_bet_v1_wealth = 1.0162` vs threshold `1.0`, `normalized_token_difference_upper = -0.008333`)
- **Registry decision (`tm_r2` vs `stock`, `k = 2`):** **`not_certified`** (`verified_replay = True`)

| Pairing | Harms | Helps | Harm Limit | Harm Passes (`δ=0.25`) | Mean Token Saving | `max-bet-v1` Wealth | `max-bet-v1` Passes | Gate Certified |
|---|---:|---:|---:|---|---:|---:|---|---|
| `tm_r2_vs_stock` | `2` | `0` | `1` | `False` | `61,362.2` | `1.0162` | `True` | `False` |
| `tm_md1_v1_vs_stock` | `1` | `0` | `1` | `True` | `53,630.7` | `0.4995` | `False` | `False` |
| `tm_r2_vs_tm_md1_v1` | `2` | `1` | `None` | `None` | `7,731.5` | `0.0063` | `False` | `None` |

---

## 7. Forensic Discrepancy Breakdown

- **`C17` (`tm_r2` PASS vs `tm_md1_v1` FAIL):** Turn 2 (`"Search our earlier sessions in session_store_sql ..."`) triggered `_CROSS_SESSION_DEIXIS` (`earlier sessions`) on `tm_r2`, recalling `session_store_sql` and recovering `watermark_pct=82, backoff_ms=250`, whereas cloud `MD-1` missed `session_history` (`0.54 < 0.55`).
- **`C21` & `C24` (`stock` + `tm_md1_v1` PASS vs `tm_r2` FAIL — the `2` `Gate.lean` harms vs limit `1`):** Turn 3 phrased cross-session recall as `"Query our past sessions in \`session_store_sql\` ..."` (`C21`) and `"Use \`session_store_sql\` to check our prior history ..."` (`C24`). Both fell outside `_CROSS_SESSION_DEIXIS`'s `(earlier|prior|previous|recent) (sessions|work|conversations|chats)` lexical set (`past sessions` / `prior history`) while embedding the snake_case tool identifier `session_store_sql` inside a long multi-field JSON output specification that diluted bag-of-n-grams cosine score below the warm-cache escalation threshold (`0.619`).
- **`C10`, `C12`, `C23`, `C25` (`FAIL` across all 3 arms — `0` differential harms):** Model-side multi-turn carry-forward omissions on `gpt-6-astra` (`reasoning_effort=low`) where Turn 3 omitted Turn-1 constants (`C10`, `C23`, `C25`) or SQL aggregate columns (`C12`) identically under `stock`, `tm_md1_v1`, and `tm_r2`.
