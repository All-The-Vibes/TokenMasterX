# R6 Skeletal Class Projection — Confirmation Round 2 Results (`class-skeleton-r6-discovery-20261119`)

- **Protocol SHA-256**: `942d7cb6558e75b7921783ddd303b9ab456d995a45101f3bf9b483c916e5be29` (verified intact)
- **Sequential Certification Round**: `k = 2` (`alpha_2 = round_alpha(0.05, 2) = 0.00759909`; cumulative `alpha_1 + alpha_2 = 0.03799545 < 0.05`)
- **Host / Model**: `GitHub Copilot CLI 1.0.112.` · `gpt-6-astra` (`reasoning_effort=low`)
- **Sample**: `78` live sessions (`26` paired tasks × `3` arms: `stock`, `tm_v1`, `tm_r6`; `13` `TokenMasterX @ dcd73c4a` + `13` `Click 8.1.8 @ 934813e4`)
- **Anti-Leakage & Mechanism Exposure**: `0` target method names in any Bucket A/B prompt; `tm_r6` rendered class skeletons on **`13/18`** oversized tasks (`15/18` mechanism-exposed across container reads & `@overload` lookups).
- **Zero Prompt-Prefix Confound (`tm_v1` vs `tm_r6`)**: R1 `brief.md` tokens identical on `26/26` tasks; Call-1 input tokens mean diff `-0.31` tokens (max `±18`).

## 1. Overall & Oversized-Class Arm Summary

### 1.1 Naturalistic Oversized-Class Target Stratum (Buckets A + B, `N = 18` paired tasks)

| Arm | Pass | Mean Total Tokens | Mean Uncached Input | Mean `read_symbol` Calls | Mean `read_symbol` Tokens | Mean Tool-Result Tokens | Skeleton Hits | Truncated Reads | Ambiguous Hits | Mean Calls | Mean Billed USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stock` | `18/18` (`100.0%`) | `79,331` | `14` | `0.00` | `0` | `3,053` | `0.00` | `0.00` | `0.00` | `4.72` | `$0.2127` |
| `tm_v1` | `18/18` (`100.0%`) | `45,118` | `14` | `2.72` | `3,240` | `3,559` | `0.00` | `0.94` | `0.06` | `4.72` | `$0.1635` |
| **`tm_r6`** | **`18/18` (`100.0%`)** | **`43,972`** | **`15`** | **`3.50`** | **`1,950`** | **`2,385`** | **`0.94`** | **`0.00`** | **`0.00`** | **`4.94`** | **`$0.1516`** |

### 1.2 All Tasks Pooled (Buckets A + B + C, `N = 26` paired tasks)

| Arm | Pass | Mean Total Tokens | Median Total Tokens | Mean Uncached Input | Mean `read_symbol` Tokens | Mean Tool-Result Tokens | Mean Calls | Mean Billed USD | Mean Cold USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stock` | `26/26` (`100.0%`) | `73,428` | `66,496` | `13` | `0` | `2,918` | `4.42` | `$0.1976` | `$0.3056` |
| `tm_v1` | `26/26` (`100.0%`) | `39,136` | `33,056` | `13` | `2,756` | `3,001` | `4.19` | `$0.1450` | `$0.1838` |
| **`tm_r6`** | **`26/26` (`100.0%`)** | **`38,219`** | **`32,760`** | **`13`** | **`1,834`** | **`2,149`** | **`4.35`** | **`$0.1361`** | **`$0.1765`** |

## 2. Pre-Registered Hypotheses (`H1..H4`, Holm-Bonferroni Adjusted)

| Hypothesis | Comparison & Metric | Mean Change (`%` [95% Bootstrap CI]) | Wins / Ties / Losses | Raw Wilcoxon `p` | Holm `p` |
|---|---|---:|---:|---:|---:|
| **`H1`** (`N=18` A+B) | `tm_r6` vs `tm_v1` `tool_result_tokens` | `-1,174` (`-33.0%` [`-42.0%`, `-20.2%`]) | `15W / 0T / 3L` | `0.001579` | `0.004737` |
| **`H2`** (`N=18` A+B) | `tm_r6` vs `tm_v1` `total_tokens` | `-1,146` (`-2.5%` [`-10.2%`, `+5.3%`]) | `11W / 0T / 7L` | `0.442299` | `0.504208` |
| **`H3`** (`N=26` All) | `tm_r6` vs `tm_v1` `total_tokens` | `-916` (`-2.3%` [`-8.5%`, `+3.9%`]) | `15W / 1T / 10L` | `0.252104` | `0.504208` |
| **`H4`** (`N=26` All) | `tm_r6` vs `stock` `total_tokens` | `-35,208` (`-48.0%` [`-52.8%`, `-43.0%`]) | `25W / 0T / 1L` | `0.000000` | `0.000000` |

## 3. Bucket Breakdown (`10` Bucket A / `8` Bucket B / `8` Bucket C)

| Bucket | `stock` Tokens (Pass) | `tm_v1` Tokens (Pass) | `tm_r6` Tokens (Pass) | `tm_r6` vs `tm_v1` Tokens (`p`) | `tm_r6` vs `tm_v1` `read_symbol` Tokens |
|---|---:|---:|---:|---:|---:|
| `A_oversized_class_trace` | `53,311` (`10/10`) | `31,442` (`10/10`) | **`28,497` (`10/10`)** | `-9.4%` (`p=0.1309`) | `4,374` → `2,468` (`-43.6%`) |
| `B_oversized_class_edit` | `111,856` (`8/8`) | `62,214` (`8/8`) | **`63,316` (`8/8`)** | `+1.8%` (`p=0.8438`) | `1,824` → `1,303` (`-28.5%`) |
| `C_small_symbol_control` | `60,145` (`8/8`) | `25,675` (`8/8`) | **`25,276` (`8/8`)** | `-1.6%` (`p=0.2188`) | `1,665` → `1,571` (`-5.6%`) |

## 4. Exact Integer Certification Gates (`brainspace/certification.py`, Sequential Round `k = 2`, `alpha_2 = 0.00759909`)

| Gate Comparison | `N` | Harms (Limit) | `harm_passes` | `max-bet-v1` Wealth | `max-bet-v1` `bet_passes` | Certified vs True-Off |
|---|---:|---:|---|---:|---|---|
| `tm_r6_vs_stock` | `26` | `0` (`<=0` if true-off) | `True` | `0.207252` | `False` | `False` |
| `tm_v1_vs_stock` | `26` | `0` (`<=0` if true-off) | `True` | `0.181183` | `False` | `False` |
| `tm_r6_vs_tm_v1` | `26` | `0` (`<=0` if true-off) | `None` | `0.003710` | `False` | `None` |
| `tm_r6_vs_tm_v1` (Oversized A+B) | `18` | `0` | `None` (active incumbent) | `0.003801` | `False` | `N/A` |

## 5. Per-Task Paired Ledger (`26` Tasks × `3` Arms)

| Task | Repo | Bucket | Kind | `stock` Tokens (Pass) | `tm_v1` Tokens / `rs_tok` (Pass) | `tm_r6` Tokens / `rs_tok` / `skel` (Pass) | `r6 - v1` Tokens |
|---|---|---|---|---:|---:|---:|---:|
| `D01` | `tokenmasterx` | `A` | `trace` | `46,364` (✓) | `27,700` / `3,838` (✓) | **`25,035`** / `2,374` / `1` (✓) | `-2,665` |
| `D02` | `tokenmasterx` | `A` | `trace` | `46,808` (✓) | `46,415` / `3,669` (✓) | **`32,224`** / `635` / `0` (✓) | `-14,191` |
| `D03` | `tokenmasterx` | `A` | `trace` | `55,555` (✓) | `27,810` / `3,418` (✓) | **`27,216`** / `3,131` / `1` (✓) | `-594` |
| `D04` | `tokenmasterx` | `A` | `trace` | `78,420` (✓) | `33,154` / `5,917` (✓) | **`34,938`** / `2,856` / `2` (✓) | `+1,784` |
| `D05` | `tokenmasterx` | `A` | `trace` | `96,395` (✓) | `32,959` / `5,798` (✓) | **`36,703`** / `2,772` / `2` (✓) | `+3,744` |
| `K01` | `click` | `A` | `trace` | `50,364` (✓) | `28,028` / `3,657` (✓) | **`25,514`** / `2,366` / `1` (✓) | `-2,514` |
| `K02` | `click` | `A` | `trace` | `30,759` (✓) | `24,528` / `2,008` (✓) | **`16,616`** / `1,942` / `0` (✓) | `-7,912` |
| `K03` | `click` | `A` | `trace` | `49,718` (✓) | `33,923` / `6,703` (✓) | **`27,833`** / `3,671` / `2` (✓) | `-6,090` |
| `K04` | `click` | `A` | `trace` | `47,236` (✓) | `27,647` / `3,283` (✓) | **`25,594`** / `2,863` / `1` (✓) | `-2,053` |
| `K05` | `click` | `A` | `trace` | `31,491` (✓) | `32,257` / `5,449` (✓) | **`33,296`** / `2,072` / `2` (✓) | `+1,039` |
| `D06` | `tokenmasterx` | `B` | `edit` | `85,166` (✓) | `52,858` / `2,755` (✓) | **`46,998`** / `1,322` / `1` (✓) | `-5,860` |
| `D07` | `tokenmasterx` | `B` | `edit` | `103,412` (✓) | `50,506` / `2,584` (✓) | **`56,148`** / `2,160` / `1` (✓) | `+5,642` |
| `D08` | `tokenmasterx` | `B` | `edit` | `81,804` (✓) | `55,298` / `2,386` (✓) | **`52,783`** / `897` / `0` (✓) | `-2,515` |
| `D09` | `tokenmasterx` | `B` | `edit` | `99,223` (✓) | `77,866` / `3,022` (✓) | **`61,832`** / `2,448` / `1` (✓) | `-16,034` |
| `K06` | `click` | `B` | `edit` | `137,472` (✓) | `64,827` / `97` (✓) | **`82,312`** / `1,459` / `1` (✓) | `+17,485` |
| `K07` | `click` | `B` | `edit` | `110,522` (✓) | `56,551` / `295` (✓) | **`64,948`** / `295` / `0` (✓) | `+8,397` |
| `K08` | `click` | `B` | `edit` | `158,639` (✓) | `69,735` / `1,056` (✓) | **`72,207`** / `945` / `0` (✓) | `+2,472` |
| `K09` | `click` | `B` | `edit` | `118,613` (✓) | `70,067` / `2,393` (✓) | **`69,298`** / `899` / `1` (✓) | `-769` |
| `D10` | `tokenmasterx` | `C` | `trace` | `62,332` (✓) | `16,381` / `1,922` (✓) | **`16,381`** / `1,922` / `0` (✓) | `+0` |
| `D11` | `tokenmasterx` | `C` | `trace` | `75,772` (✓) | `16,688` / `2,178` (✓) | **`16,692`** / `2,178` / `0` (✓) | `+4` |
| `D12` | `tokenmasterx` | `C` | `trace` | `62,355` (✓) | `24,383` / `1,196` (✓) | **`24,389`** / `1,196` / `0` (✓) | `+6` |
| `D13` | `tokenmasterx` | `C` | `edit` | `70,636` (✓) | `49,832` / `3,268` (✓) | **`46,949`** / `2,516` / `0` (✓) | `-2,883` |
| `K10` | `click` | `C` | `trace` | `29,993` (✓) | `16,113` / `1,669` (✓) | **`16,101`** / `1,669` / `0` (✓) | `-12` |
| `K11` | `click` | `C` | `trace` | `33,019` (✓) | `15,566` / `857` (✓) | **`15,574`** / `857` / `0` (✓) | `+8` |
| `K12` | `click` | `C` | `trace` | `33,337` (✓) | `15,895` / `1,371` (✓) | **`15,861`** / `1,371` / `0` (✓) | `-34` |
| `K13` | `click` | `C` | `edit` | `113,719` (✓) | `50,545` / `859` (✓) | **`50,261`** / `859` / `0` (✓) | `-284` |

## 6. Exploratory Payload & Cost Decomposition (`tm_r6` vs `tm_v1`)

| Stratum | Metric | `tm_v1` Mean | `tm_r6` Mean | `%` Change [95% CI] | Wins / Ties / Losses | Exact Wilcoxon `p` (unadjusted) |
|---|---|---:|---:|---:|---:|---:|
| `Bucket A` (`N=10` trace) | `read_symbol_tokens` | `4,374` | `2,468` | `-43.6%` [`-54.7%`, `-30.3%`] | `10W / 0T / 0L` | `0.001953` |
| `Bucket A` (`N=10` trace) | `billed_cost_usd` | `$0.1405` | `$0.1154` | `-17.8%` [`-23.4%`, `-12.1%`] | `10W / 0T / 0L` | `0.001953` |
| `Oversized A+B` (`N=18`) | `read_symbol_tokens` | `3,240` | `1,950` | `-39.8%` [`-49.7%`, `-26.5%`] | `16W / 1T / 1L` | `0.000381` |
| `Oversized A+B` (`N=18`) | `billed_cost_usd` | `$0.1635` | `$0.1516` | `-7.3%` [`-15.1%`, `+1.6%`] | `14W / 0T / 4L` | `0.073685` |
| `Bucket B` (`N=8` edit) | `read_symbol_tokens` | `1,824` | `1,303` | `-28.5%` [`-49.9%`, `+14.0%`] | `6W / 1T / 1L` | `0.109375` |
| `Bucket C` (`N=8` control) | `read_symbol_tokens` | `1,665` | `1,571` | `-5.6%` [`-13.9%`, `+0.0%`] | `1W / 7T / 0L` | `1.000000` |
| `Pooled All` (`N=26`) | `read_symbol_tokens` | `2,756` | `1,834` | `-33.5%` [`-43.1%`, `-20.8%`] | `17W / 8T / 1L` | `0.000252` |
| `Pooled All` (`N=26`) | `billed_cost_usd` | `$0.1450` | `$0.1361` | `-6.2%` [`-12.4%`, `+0.6%`] | `17W / 1T / 8L` | `0.029578` |

### Why Payload & Billed Cost Improved Sharply While Raw `total_tokens` Attenuated

1. **Cached-prefix accounting vs billed cost in 2-step skeleton discovery (`Bucket A`, `N=10`)**: In `tm_r6`, reading an oversized class (`~966–1,080` skeleton tokens vs `2,391–2,399` truncated `tm_v1` tokens) followed by a surgical `Class.method` lookup (`~250–400` tokens) cut `read_symbol` payload **`-43.6%`** (`10W / 0T / 0L`, `p = 0.001953`) and **reduced actual billed USD cost on `10/10` (`100%`) of Bucket A tasks (`-17.8%`, `10W / 0T / 0L`, `p = 0.001953`)**. On `3/10` tasks (`D04`, `D05`, `K05`), executing that second surgical `Class.method` lookup added one cached-prefix API turn (`3 → 4` calls), which adds `~11k` cheap *cached* prefix tokens to raw `total_tokens` (`sum(input_tokens + output_tokens)`) even as billed USD cost fell (`$0.1614 → $0.1373`, `$0.1595 → $0.1310`, `$0.1490 → $0.1206`). Net raw `total_tokens` on Bucket A still improved **`-9.4%`** (`31,442 → 28,497t`, `7W / 0T / 3L`).
2. **Edit + `pytest` loop variance (`Bucket B`, `N=8`)**: Multi-step edit + test sessions span `6–9` API calls (`~62k` cumulative tokens) where `read_symbol` represents `<3%` of cumulative tokens (`1,824 → 1,303t`, `-28.5%`); normal 1-turn `edit`/`pytest` variance dominated cumulative `total_tokens` (`+1.8%`, `4W / 0T / 4L`), while `TokenMasterX` edits (`D06..D09`) improved `-8.7%` (`59,132 → 54,440t`).
3. **Small-symbol parity (`Bucket C`, `N=8`)**: Below `max_lines = 120`, `read_symbol_tokens` tied identically on `7/8` tasks (`1W / 7T / 0L`, `p = 1.0000`), confirming zero small-symbol overhead.
