# Live Benchmark Results: Pillar 5 Architectural & Cross-Session Recall Brief (`repo-brief-20261117`)

- **Pre-registered protocol SHA-256**: `8801a680b7384f2e2bbcbc6bc5a42f041be209cc3920a98022233918d7bfed6d` (verified)
- **Runtime**: `GitHub Copilot CLI 1.0.112.`, model `gpt-6-astra` (`reasoning_effort=low`), `24` paired tasks × `4` concurrent arms = **`96` live sessions**
- **Repositories**: `All-The-Vibes/TokenMasterX` (`f4228f7e`, cold `306t` / warm `301t`) + `pallets/click` `8.1.8` (`934813e4`, cold `296t` / warm `288t`)

## 1. Overall Performance Across All 24 Tasks (`N = 24` Pairs / `96` Sessions)

| Arm | Pass | Mean Turns | Mean Total Tok | Mean Uncached In | Mean Out Tok | Mean Billed USD | Mean Cold USD | Mean Orient Calls | 1st-Call Direct Sym |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stock` | `24/24` (`100.0%`) | `4.33` | `70,054` | `13` | `393` | `$0.17610` | `$0.28759` | `3.33` | `0.0%` |
| `tm_lean` | `24/24` (`100.0%`) | `4.88` | `41,253` | `15` | `387` | `$0.12748` | `$0.16787` | `2.75` | `0.0%` |
| `tm_brief` | `24/24` (`100.0%`) | `4.08` | `34,957` | `12` | `360` | `$0.11789` | `$0.15828` | `1.58` | `62.5%` |
| `tm_recall` | `24/24` (`100.0%`) | `4.08` | `35,118` | `12` | `370` | `$0.11736` | `$0.15775` | `1.54` | `62.5%` |

## 2. Breakdown by Pre-Registered Causal Bucket (`n = 8` Tasks / `32` Sessions per Bucket)

| Bucket | Arm | Pass | Mean Turns | Mean Total Tok | Mean Billed USD | Mean Orient Calls | 1st-Call Direct Sym |
|---|---|---:|---:|---:|---:|---:|---:|
| `A_cold_architecture` | `stock` | `8/8` | `5.25` | `85,058` | `$0.20011` | `4.25` | `0.0%` |
| `A_cold_architecture` | `tm_lean` | `8/8` | `5.88` | `53,941` | `$0.16755` | `3.88` | `0.0%` |
| `A_cold_architecture` | `tm_brief` | `8/8` | `4.25` | `37,873` | `$0.13410` | `1.50` | `100.0%` |
| `A_cold_architecture` | `tm_recall` | `8/8` | `4.88` | `43,274` | `$0.14279` | `2.38` | `50.0%` |
| `B_cross_session_recall` | `stock` | `8/8` | `5.00` | `83,028` | `$0.20621` | `4.00` | `0.0%` |
| `B_cross_session_recall` | `tm_lean` | `8/8` | `5.50` | `46,786` | `$0.14131` | `3.25` | `0.0%` |
| `B_cross_session_recall` | `tm_brief` | `8/8` | `5.38` | `47,564` | `$0.14698` | `2.75` | `37.5%` |
| `B_cross_session_recall` | `tm_recall` | `8/8` | `4.75` | `42,656` | `$0.13745` | `1.88` | `75.0%` |
| `C_direct_symbol_control` | `stock` | `8/8` | `2.75` | `42,077` | `$0.12198` | `1.75` | `0.0%` |
| `C_direct_symbol_control` | `tm_lean` | `8/8` | `3.25` | `23,032` | `$0.07360` | `1.12` | `0.0%` |
| `C_direct_symbol_control` | `tm_brief` | `8/8` | `2.62` | `19,435` | `$0.07260` | `0.50` | `50.0%` |
| `C_direct_symbol_control` | `tm_recall` | `8/8` | `2.62` | `19,422` | `$0.07186` | `0.38` | `62.5%` |

## 3. Breakdown by Repository (`n = 12` Tasks / `48` Sessions per Repo)

| Repository | Arm | Pass | Mean Turns | Mean Total Tok | Mean Billed USD | Mean Orient Calls |
|---|---|---:|---:|---:|---:|---:|
| `tokenmasterx` | `stock` | `12/12` | `4.67` | `76,994` | `$0.19462` | `3.83` |
| `tokenmasterx` | `tm_lean` | `12/12` | `5.25` | `47,825` | `$0.14924` | `3.08` |
| `tokenmasterx` | `tm_brief` | `12/12` | `4.25` | `37,564` | `$0.12920` | `1.92` |
| `tokenmasterx` | `tm_recall` | `12/12` | `4.33` | `38,452` | `$0.12943` | `1.67` |
| `click` | `stock` | `12/12` | `4.00` | `63,115` | `$0.15757` | `2.83` |
| `click` | `tm_lean` | `12/12` | `4.50` | `34,681` | `$0.10573` | `2.42` |
| `click` | `tm_brief` | `12/12` | `3.92` | `32,351` | `$0.10659` | `1.25` |
| `click` | `tm_recall` | `12/12` | `3.83` | `31,784` | `$0.10530` | `1.42` |

## 4. Paired Contrasts, 95% Bootstrap CIs & Exact Wilcoxon Tests

| Scope | Contrast (`treat - base`) | Δ Total Tokens (`95% CI`) | % Δ Tokens | Wilcoxon $p$ | Δ Billed USD (`95% CI`) | % Δ USD | Treat Lower/Tie/Higher (Tok) |
|---|---|---:|---:|---:|---:|---:|---:|
| All (N=24) | `tm_recall_vs_stock` | `-34,937` (`[-42,853, -27,340]`) | `-49.9%` | `0.0000` | `$-0.05873` (`[$-0.07276, $-0.04653]`) | `-33.4%` | `24/0/0` |
| All (N=24) | `tm_brief_vs_stock` | `-35,097` (`[-43,791, -26,740]`) | `-50.1%` | `0.0000` | `$-0.05820` (`[$-0.07014, $-0.04707]`) | `-33.1%` | `23/0/1` |
| All (N=24) | `tm_lean_vs_stock` | `-28,801` (`[-38,603, -19,958]`) | `-41.1%` | `0.0000` | `$-0.04861` (`[$-0.06544, $-0.03235]`) | `-27.6%` | `23/0/1` |
| All (N=24) | `tm_brief_vs_tm_lean` | `-6,296` (`[-11,484, -1,202]`) | `-15.3%` | `0.0211` | `$-0.00959` (`[$-0.02166, $+0.00180]`) | `-7.5%` | `17/0/7` |
| All (N=24) | `tm_recall_vs_tm_lean` | `-6,135` (`[-10,961, -1,340]`) | `-14.9%` | `0.0035` | `$-0.01012` (`[$-0.02225, $+0.00096]`) | `-7.9%` | `16/0/8` |
| All (N=24) | `tm_recall_vs_tm_brief` | `+160` (`[-4,926, +4,880]`) | `+0.5%` | `0.4688` | `$-0.00053` (`[$-0.01028, $+0.00900]`) | `-0.4%` | `17/0/7` |
| Bucket A (n=8) | `tm_brief_vs_tm_lean` | `-16,068` (`[-25,509, -7,178]`) | `-29.8%` | `0.0234` | `$-0.03345` (`[$-0.05618, $-0.01364]`) | `-20.0%` | `7/0/1` |
| Bucket A (n=8) | `tm_recall_vs_tm_lean` | `-10,666` (`[-17,520, -4,108]`) | `-19.8%` | `0.0391` | `$-0.02476` (`[$-0.04091, $-0.01028]`) | `-14.8%` | `6/0/2` |
| Bucket B (n=8) | `tm_recall_vs_tm_brief` | `-4,907` (`[-16,598, +6,276]`) | `-10.3%` | `0.3828` | `$-0.00953` (`[$-0.03356, $+0.01567]`) | `-6.5%` | `6/0/2` |
| Bucket B (n=8) | `tm_recall_vs_tm_lean` | `-4,130` (`[-16,169, +8,216]`) | `-8.8%` | `0.3125` | `$-0.00386` (`[$-0.03398, $+0.02176]`) | `-2.7%` | `5/0/3` |
| Bucket C (n=8) | `tm_brief_vs_tm_lean` | `-3,597` (`[-5,571, -832]`) | `-15.6%` | `0.1094` | `$-0.00100` (`[$-0.00417, $+0.00318]`) | `-1.4%` | `5/0/3` |
| Bucket C (n=8) | `tm_recall_vs_tm_lean` | `-3,610` (`[-5,540, -865]`) | `-15.7%` | `0.1094` | `$-0.00174` (`[$-0.00542, $+0.00246]`) | `-2.4%` | `5/0/3` |

## 5. Pre-Registered Primary Hypothesis Family (Holm–Bonferroni $\alpha = 0.05$)

| Hypothesis | Raw Wilcoxon $p$ | Holm–Bonferroni Adjusted $p$ |
|---|---:|---:|
| `H1_tm_recall_vs_stock_total_tokens` | `0.000000` | `0.000000` |
| `H2_bucketA_tm_brief_vs_tm_lean_total_tokens` | `0.023438` | `0.058326` |
| `H3_bucketB_tm_recall_vs_tm_brief_total_tokens` | `0.382812` | `0.382812` |
| `H4_all_tm_recall_vs_tm_lean_billed_usd` | `0.019442` | `0.058326` |

## 6. `/tokenomics` Brief-Overhead Accounting Audit

| Repo | Cold Brief Ref Tok | Empirical Call-1 Δ (`tm_brief - tm_lean`) | Warm Brief Ref Tok | Empirical Call-1 Δ (`tm_recall - tm_lean`) | Mean Fixed Saved (`tm_lean` / `tm_brief` / `tm_recall`) |
|---|---:|---:|---:|---:|---:|
| `tokenmasterx` | `306` | `+306.7` | `301` | `+302.0` | `40,436` / `31,433` / `32,071` |
| `click` | `296` | `+298.4` | `288` | `+288.7` | `34,659` / `29,007` / `28,420` |

## 7. Pre-Registered Product Default Decision

- **Gate outcome**: `enable_by_default = True` -> **`default-on`**
- **All-task (`A+B+C`) net delta vs `tm_lean`**:
  - `tm_brief - tm_lean`: `-6,295.6` total tokens, `$-0.00959` billed USD (`24/24` vs `24/24` pass)
  - `tm_recall - tm_lean`: `-6,135.2` total tokens, `$-0.01012` billed USD (`24/24` vs `24/24` pass)

## 8. Per-Task Outcome Matrix (`24 × 4`)

| Task | Repo | Bucket | Kind | `stock` | `tm_lean` | `tm_brief` | `tm_recall` |
|---|---|---|---|---|---|---|---|
| `T01` | `tokenmasterx` | `A_cold_architecture` | `trace` | PASS (3c, 48,174t) | PASS (5c, 43,593t) | PASS (2c, 16,515t) | PASS (2c, 16,487t) |
| `T02` | `tokenmasterx` | `A_cold_architecture` | `trace` | PASS (4c, 63,702t) | PASS (5c, 39,606t) | PASS (2c, 16,089t) | PASS (5c, 40,793t) |
| `T03` | `tokenmasterx` | `A_cold_architecture` | `edit` | PASS (8c, 132,767t) | PASS (8c, 109,167t) | PASS (6c, 68,112t) | PASS (8c, 86,815t) |
| `T04` | `tokenmasterx` | `A_cold_architecture` | `edit` | PASS (8c, 134,695t) | PASS (6c, 57,116t) | PASS (5c, 47,427t) | PASS (5c, 47,515t) |
| `C01` | `click` | `A_cold_architecture` | `trace` | PASS (4c, 60,925t) | PASS (5c, 38,585t) | PASS (3c, 23,820t) | PASS (3c, 23,805t) |
| `C02` | `click` | `A_cold_architecture` | `trace` | PASS (2c, 30,163t) | PASS (4c, 28,738t) | PASS (2c, 15,045t) | PASS (3c, 22,582t) |
| `C03` | `click` | `A_cold_architecture` | `edit` | PASS (7c, 115,931t) | PASS (7c, 57,745t) | PASS (7c, 60,048t) | PASS (7c, 59,792t) |
| `C04` | `click` | `A_cold_architecture` | `edit` | PASS (6c, 94,106t) | PASS (7c, 56,976t) | PASS (7c, 55,930t) | PASS (6c, 48,406t) |
| `T05` | `tokenmasterx` | `B_cross_session_recall` | `trace` | PASS (3c, 52,632t) | PASS (5c, 53,268t) | PASS (6c, 53,076t) | PASS (2c, 16,715t) |
| `T06` | `tokenmasterx` | `B_cross_session_recall` | `trace` | PASS (5c, 94,265t) | PASS (6c, 43,636t) | PASS (6c, 51,130t) | PASS (4c, 31,327t) |
| `T07` | `tokenmasterx` | `B_cross_session_recall` | `edit` | PASS (5c, 77,669t) | PASS (6c, 49,760t) | PASS (5c, 44,653t) | PASS (5c, 44,067t) |
| `T08` | `tokenmasterx` | `B_cross_session_recall` | `edit` | PASS (7c, 123,397t) | PASS (8c, 77,071t) | PASS (6c, 56,322t) | PASS (8c, 80,245t) |
| `C05` | `click` | `B_cross_session_recall` | `trace` | PASS (2c, 30,418t) | PASS (3c, 21,154t) | PASS (2c, 14,749t) | PASS (2c, 14,717t) |
| `C06` | `click` | `B_cross_session_recall` | `trace` | PASS (3c, 44,509t) | PASS (4c, 32,860t) | PASS (3c, 26,697t) | PASS (3c, 26,685t) |
| `C07` | `click` | `B_cross_session_recall` | `edit` | PASS (8c, 129,294t) | PASS (6c, 48,915t) | PASS (8c, 75,392t) | PASS (8c, 78,299t) |
| `C08` | `click` | `B_cross_session_recall` | `edit` | PASS (7c, 112,039t) | PASS (6c, 47,623t) | PASS (7c, 58,491t) | PASS (6c, 49,196t) |
| `T09` | `tokenmasterx` | `C_direct_symbol_control` | `trace` | PASS (3c, 43,995t) | PASS (3c, 20,868t) | PASS (3c, 21,780t) | PASS (3c, 21,753t) |
| `T10` | `tokenmasterx` | `C_direct_symbol_control` | `trace` | PASS (2c, 31,572t) | PASS (3c, 21,851t) | PASS (3c, 22,755t) | PASS (3c, 22,708t) |
| `T11` | `tokenmasterx` | `C_direct_symbol_control` | `trace` | PASS (3c, 46,711t) | PASS (4c, 28,852t) | PASS (4c, 30,392t) | PASS (4c, 30,376t) |
| `T12` | `tokenmasterx` | `C_direct_symbol_control` | `trace` | PASS (5c, 74,349t) | PASS (4c, 29,108t) | PASS (3c, 22,515t) | PASS (3c, 22,621t) |
| `C09` | `click` | `C_direct_symbol_control` | `trace` | PASS (3c, 48,064t) | PASS (3c, 21,209t) | PASS (2c, 14,866t) | PASS (2c, 14,826t) |
| `C10` | `click` | `C_direct_symbol_control` | `trace` | PASS (2c, 32,333t) | PASS (3c, 20,821t) | PASS (2c, 14,417t) | PASS (2c, 14,385t) |
| `C11` | `click` | `C_direct_symbol_control` | `trace` | PASS (2c, 30,269t) | PASS (3c, 20,769t) | PASS (2c, 14,386t) | PASS (2c, 14,370t) |
| `C12` | `click` | `C_direct_symbol_control` | `trace` | PASS (2c, 29,325t) | PASS (3c, 20,778t) | PASS (2c, 14,367t) | PASS (2c, 14,339t) |

## 9. Mechanistic Findings, Budget Trade-Offs & Limitations

- **Turn-1 direct symbol navigation (`0.0% -> 62.5%`)**: Without `.token-master/brief.md`, `0/24` (`0.0%`) of `tm_lean` sessions called `read_symbol` or `impact` on Turn 1—every session spent its first turn orienting with `locate`, `glob`, or `rg`. With the `<= 306`-token one-shot `hooks.sessionStart` brief, `15/24` (`62.5%`) of `tm_brief` and `tm_recall` sessions jumped directly to `read_symbol`/`impact` on Turn 1 (`8/8 = 100.0%` on Bucket A for `tm_brief`, `6/8 = 75.0%` on Bucket B for `tm_recall`), cutting orientation calls by `-43.9%` (`2.75 -> 1.54`, Wilcoxon $p = 2.7\times 10^{-5}$) and model calls by `-16.2%` (`4.88 -> 4.08`, Wilcoxon $p = 0.0021$).
- **Cold brief vs Cross-session recall (`Bucket A` vs `Bucket B` budget trade-off)**: Under the strict `320`-token `cl100k_base` cap (`symbol_index._assemble`), adding 4 `Recall:` lines on `TokenMasterX` (`301t`) displaced the lower-priority `Entry:` lines (`brainspace_posttooluse.py::main`, `brainspace_copilot_bridge.py::main`). As a result, `tm_brief` (`306t`, with `Entry:` lines retained) outperformed `tm_recall` on entrypoint tasks `T02` (`16,089t` vs `40,793t`) and `T03` (`68,112t` vs `86,815t`), saving `-29.8%` tokens on Bucket A (`53,941 -> 37,873`, raw $p = 0.0234$, Holm $p = 0.0583$) vs `-19.8%` for `tm_recall` (`p = 0.0391`). Conversely, on Bucket B (`B_cross_session_recall`), `tm_recall` doubled Turn-1 direct symbol reads (`37.5% -> 75.0%`) and cut mean tokens `-10.3%` vs `tm_brief` (`47,564 -> 42,656`, `6/0/2` wins, including `-68.5%` on `T05` and `-38.7%` on `T06`), though multi-call edit variance on `T08` and `C07` left $n = 8$ Wilcoxon $p = 0.3828$ statistically nonsignificant (`H3`).
- **Bucket C (`C_direct_symbol_control`) fixed-tax vs skipped-locate effect**: On `TokenMasterX` `T09`–`T11` where `tm_lean` and brief arms made identical model calls, `tm_brief` and `tm_recall` paid the expected `~300t × calls` fixed brief overhead (`+904t` to `+1,540t`). However, on `T12` and all four `click` controls (`C09`–`C12`), the brief's `Layout: src/click (16)` line allowed `tm_brief`/`tm_recall` to resolve `src/click/<module>.py::<qualname>` directly via `read_symbol` in 2 calls instead of calling `locate` first (3 calls), yielding a net `-15.7%` token reduction across Bucket C (`23,032 -> 19,422`).
- **Exact `/tokenomics` brief subtraction**: Reference `cl100k_base` brief counts (`306`, `301`, `296`, `288`) matched empirical `gpt-6-astra` Responses API Call-1 `input_tokens` deltas (`+306.7`, `+302.0`, `+298.4`, `+288.7`) within `0.7–2.4` tokens, confirming that `tokenomics.py`'s per-call `- brief` subtraction neither inflates savings nor misattributes prompt-cache tokens.
