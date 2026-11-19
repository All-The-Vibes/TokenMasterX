# Research Direction R2 Live Study Report (`r2-stateful-routing-20261120`)

## 1. Executive Summary

- **Scope:** `16` pre-registered 3-turn workflows × `4` arms = **`64` live sessions (`192` Copilot CLI `GitHub Copilot CLI 1.0.112.
Run 'copilot update' to check for updates.` launches)** on `gpt-6-astra` (`reasoning_effort=low`), base commit `a9275d8`.
- **Pre-registration integrity:** `PROTOCOL.sha256` verified (`bec307b7762e0565...`); `0` aborts; `64/64` (`100%`) single-session continuity across `start` → `--resume <sid>` → `--continue`; `96/96` launches on `tm_locked` & `tm_r2` verified `100%` offline (`router='r2'`, `TOKENMASTER_MD1_ENDPOINT` unset).
- **Zero-network routing latency (H2):** Local R2 router (`24.2 KB` compressed `int16` weights) ran in **`42.584 ms` median** (`78.672 ms` p90, including SQLite warm-cache state lookup) vs cloud `MD-1` **`960.3 ms` median** (`1194.3 ms` p90) — a **`22.6x` live launcher speedup** (Holm $p = 0.000122$).
- **End-to-end savings vs Stock (H1):** `tm_r2` passed **`12/16` (`75.0%`)** workflows vs `stock` **`13/16` (`81.2%`)**, cutting cold-normalized session cost by **`-37.43%`** (95% CI `[-43.041, -31.92]%`, Holm $p = 0.000122$) and total raw tokens by **`-50.44%`**.
- **Escalation & cross-session recall recovery vs Strict Lock (H3):** Across Buckets B + C (`S05`–`S12`), `tm_r2` recalled **`7/8`** mid-session capability shifts (`7/8` native tool executions) vs `tm_locked` **`0/8`** (`0/8` native tool executions; Holm $p = 0.031250$).
- **Pragmatic deixis & warm-cache stability vs Cloud `tm_md1_v1` (H4):** `tm_r2` recorded **`0`** unneeded mid-session tool-list mutations vs **`6`** on `tm_md1_v1`, lifting mean resumed first-call prompt-cache hit rate from **`48.09%`** to **`58.84%`** and changing Turn-2+3 billed cost by **`-26.87%`**.
- **Formal `Gate.lean` + `Bet.lean` certification (`brainspace/certification.py`):** **`decision = 'not_certified'`** (`rule_version = 'harm-margin-max-bet-tokens-v1'`, `harm_count = 1`, `help_count = 0`, `mean_token_saving = 69210.4`, `verified_replay = True`).

---

## 2. Overall 4-Arm Summary (`N = 16` Workflows per Arm)

| Arm | Pass | Cold USD (sum / mean) | Turn 2+3 Billed USD (mean) | Raw Tokens (mean) | Resumed 1st-Call Cache Hit | Esc. Recall (`B+C`) | Native Tool Used (`B+C`) | Unneeded Tool Muts | Router Latency Median / p90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stock` | `13/16` (`81.2%`) | `$7.3604` / `$0.4600` | `$0.2255` | `137,216` | `77.77%` | `8/8` | `8/8` | `0` | — |
| `tm_locked` | `11/16` (`68.8%`) | `$4.2221` / `$0.2639` | `$0.1436` | `62,662` | `67.55%` | `0/8` | `0/8` | `0` | `32.169 ms` / `56.668 ms` |
| `tm_md1_v1` | `11/16` (`68.8%`) | `$5.6011` / `$0.3501` | `$0.2319` | `75,627` | `48.09%` | `7/8` | `7/8` | `6` | `960.323 ms` / `1194.335 ms` |
| `tm_r2` | `12/16` (`75.0%`) | `$4.6057` / `$0.2879` | `$0.1696` | `68,006` | `58.84%` | `7/8` | `7/8` | `0` | `42.584 ms` / `78.672 ms` |

---

## 3. Bucket Breakdown (`4` Workflows × `3` Turns per Bucket)

| Bucket | Arm | Pass | Cold USD Mean | Turn 2+3 Billed USD Mean | Raw Tokens Mean | Resumed 1st-Call Cache Hit | Unneeded Muts |
|---|---|---:|---:|---:|---:|---:|---:|
| `A_stable_coding` | `stock` | `3/4` | `$0.4275` | `$0.2028` | `103,562` | `73.82%` | `0` |
| `A_stable_coding` | `tm_locked` | `3/4` | `$0.2663` | `$0.1521` | `60,517` | `61.79%` | `0` |
| `A_stable_coding` | `tm_md1_v1` | `3/4` | `$0.2537` | `$0.1371` | `56,664` | `68.78%` | `0` |
| `A_stable_coding` | `tm_r2` | `3/4` | `$0.2743` | `$0.1552` | `57,376` | `59.97%` | `0` |
| `B_escalation_and_intra_deixis` | `stock` | `4/4` | `$0.4409` | `$0.1819` | `119,052` | `77.36%` | `0` |
| `B_escalation_and_intra_deixis` | `tm_locked` | `4/4` | `$0.2997` | `$0.1501` | `60,634` | `64.66%` | `0` |
| `B_escalation_and_intra_deixis` | `tm_md1_v1` | `4/4` | `$0.5008` | `$0.3546` | `79,428` | `17.23%` | `4` |
| `B_escalation_and_intra_deixis` | `tm_r2` | `4/4` | `$0.3216` | `$0.1830` | `66,446` | `49.38%` | `0` |
| `C_cross_session_recall` | `stock` | `2/4` | `$0.4597` | `$0.2483` | `162,040` | `81.72%` | `0` |
| `C_cross_session_recall` | `tm_locked` | `0/4` | `$0.1670` | `$0.0738` | `34,042` | `72.77%` | `0` |
| `C_cross_session_recall` | `tm_md1_v1` | `0/4` | `$0.3197` | `$0.2254` | `75,970` | `43.13%` | `1` |
| `C_cross_session_recall` | `tm_r2` | `1/4` | `$0.2581` | `$0.1652` | `67,403` | `56.70%` | `0` |
| `D_warm_cache_lookalikes` | `stock` | `4/4` | `$0.5120` | `$0.2689` | `164,212` | `78.19%` | `0` |
| `D_warm_cache_lookalikes` | `tm_locked` | `4/4` | `$0.3226` | `$0.1984` | `95,457` | `71.00%` | `0` |
| `D_warm_cache_lookalikes` | `tm_md1_v1` | `4/4` | `$0.3261` | `$0.2103` | `90,448` | `63.23%` | `1` |
| `D_warm_cache_lookalikes` | `tm_r2` | `4/4` | `$0.2974` | `$0.1748` | `80,798` | `69.32%` | `0` |

---

## 4. Pre-Registered Hypotheses & Holm-Bonferroni Inference

| Hypothesis | Comparison | Metric / Effect | Raw two-sided $p$ | Holm-Bonferroni $p$ | Significant ($\alpha=0.05$) |
|---|---|---|---:|---:|:---:|
| `H1_cold_usd_vs_stock` | `tm_r2 vs stock (N=16)` | cold_usd -37.43% (95% CI [-43.041, -31.92]%) | `0.000031` | `0.000122` | YES |
| `H2_router_latency_vs_md1` | `tm_r2 vs tm_md1_v1 (N=16 workflows / 48 launches)` | median 42.584 ms vs 960.3 ms (22.6x faster) | `0.000031` | `0.000122` | YES |
| `H3_escalation_recall_vs_locked` | `tm_r2 vs tm_locked on Buckets B+C (N=8)` | mid-session capability recall 7/8 vs 0/8 (native tool used 7/8 vs 0/8) | `0.015625` | `0.031250` | YES |
| `H4_resume_cache_hit_vs_md1_v1` | `tm_r2 vs tm_md1_v1 (N=16)` | resumed 1st-call cache hit 58.84% vs 48.09%, unneeded muts 0 vs 6 | `0.116669` | `0.116669` | no |

---

## 5. Per-Workflow Matrix (`S01`–`S16`)

| Task | Bucket | Kind | `stock` | `tm_locked` | `tm_md1_v1` (muts / hit) | `tm_r2` (muts / hit) | `tm_r2` vs `stock` Cold Δ% |
|---|---|---|---|---|---|---|---:|
| `S01` | `A_stable_coding` | `edit` | `PASS` `$0.5477` | `PASS` `$0.3850` | `PASS` `$0.3013` (`0` / `68%`) | `PASS` `$0.3676` (`0` / `37%`) | `-32.9%` |
| `S02` | `A_stable_coding` | `edit` | `PASS` `$0.4201` | `PASS` `$0.2352` | `PASS` `$0.2415` (`0` / `72%`) | `PASS` `$0.2629` (`0` / `68%`) | `-37.4%` |
| `S03` | `A_stable_coding` | `investigate` | `PASS` `$0.3893` | `PASS` `$0.2027` | `PASS` `$0.2260` (`0` / `68%`) | `PASS` `$0.2245` (`0` / `68%`) | `-42.3%` |
| `S04` | `A_stable_coding` | `investigate` | `FAIL` `$0.3529` | `FAIL` `$0.2423` | `FAIL` `$0.2460` (`0` / `67%`) | `FAIL` `$0.2422` (`0` / `67%`) | `-31.4%` |
| `S05` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.4544` | `PASS` `$0.3077` | `PASS` `$0.5808` (`2` / `22%`) | `PASS` `$0.3461` (`1` / `49%`) | `-23.8%` |
| `S06` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.3941` | `PASS` `$0.2551` | `PASS` `$0.5520` (`2` / `15%`) | `PASS` `$0.2650` (`1` / `49%`) | `-32.8%` |
| `S07` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.4843` | `PASS` `$0.3393` | `PASS` `$0.4247` (`2` / `18%`) | `PASS` `$0.3437` (`1` / `49%`) | `-29.0%` |
| `S08` | `B_escalation_and_intra_deixis` | `investigate` | `PASS` `$0.4308` | `PASS` `$0.2966` | `PASS` `$0.4457` (`2` / `14%`) | `PASS` `$0.3317` (`1` / `49%`) | `-23.0%` |
| `S09` | `C_cross_session_recall` | `investigate` | `FAIL` `$0.4175` | `FAIL` `$0.1617` | `FAIL` `$0.5128` (`2` / `0%`) | `FAIL` `$0.3317` (`1` / `24%`) | `-20.6%` |
| `S10` | `C_cross_session_recall` | `investigate` | `FAIL` `$0.5408` | `FAIL` `$0.1657` | `FAIL` `$0.3044` (`1` / `52%`) | `FAIL` `$0.3268` (`1` / `52%`) | `-39.6%` |
| `S11` | `C_cross_session_recall` | `investigate` | `PASS` `$0.4395` | `FAIL` `$0.1731` | `FAIL` `$0.2361` (`1` / `76%`) | `PASS` `$0.2107` (`1` / `79%`) | `-52.1%` |
| `S12` | `C_cross_session_recall` | `investigate` | `PASS` `$0.4408` | `FAIL` `$0.1673` | `FAIL` `$0.2252` (`1` / `44%`) | `FAIL` `$0.1631` (`0` / `72%`) | `-63.0%` |
| `S13` | `D_warm_cache_lookalikes` | `edit` | `PASS` `$0.5988` | `PASS` `$0.3895` | `PASS` `$0.4431` (`0` / `68%`) | `PASS` `$0.3784` (`0` / `62%`) | `-36.8%` |
| `S14` | `D_warm_cache_lookalikes` | `edit` | `PASS` `$0.6546` | `PASS` `$0.4097` | `PASS` `$0.3385` (`0` / `67%`) | `PASS` `$0.3115` (`0` / `67%`) | `-52.4%` |
| `S15` | `D_warm_cache_lookalikes` | `investigate` | `PASS` `$0.4102` | `PASS` `$0.2468` | `PASS` `$0.2486` (`0` / `73%`) | `PASS` `$0.2554` (`0` / `73%`) | `-37.7%` |
| `S16` | `D_warm_cache_lookalikes` | `investigate` | `PASS` `$0.3845` | `PASS` `$0.2444` | `PASS` `$0.2743` (`1` / `45%`) | `PASS` `$0.2444` (`0` / `75%`) | `-36.4%` |

---

## 6. Maintainer PR `#35` Proof-Backed Certification (`Gate.lean` + `Bet.lean`)

- **Rule version:** `harm-margin-max-bet-tokens-v1` (`quality_margin = 0.25`, `token_test = 'max-bet-v1'`, `token_cap = 500,000`, `minimum_token_reduction = 5,000`)
- **Sample size:** `n = 16` paired 3-turn workflows (`S01`–`S16`), `alpha_round = 0.030396`
- **Quality gate (`Gate.lean`):** `harm_count = 1` (limit `0`), `help_count = 0`, `quality_difference_lower = -1.000000`
- **Token savings gate (`Bet.lean`):** `mean_token_saving = 69,210.4` tokens (`max_bet_v1_wealth = 0.1009` vs threshold `1.0`, `normalized_token_difference_upper = 1.000000`)
- **Registry decision (`tm_r2` vs `stock`):** **`not_certified`** (`verified_replay = True`)

| Pairing | Harms | Helps | Harm Passes (`δ=0.25`) | Mean Token Saving | `max-bet-v1` Wealth | `max-bet-v1` Passes | Gate Certified |
|---|---:|---:|---|---:|---:|---|---|
| `tm_r2_vs_stock` | `1` | `0` | `False` | `69,210.4` | `0.1009` | `False` | `False` |
| `tm_locked_vs_stock` | `2` | `0` | `False` | `74,553.6` | `0.1159` | `False` | `False` |
| `tm_md1_v1_vs_stock` | `2` | `0` | `False` | `61,588.8` | `0.0813` | `False` | `False` |
| `tm_r2_vs_tm_md1_v1` | `0` | `1` | `None` | `7,621.6` | `0.0164` | `False` | `None` |
