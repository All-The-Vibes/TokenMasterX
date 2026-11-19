# Results: R1 Submodular Knapsack & Marginal Graph-Coverage Brief (`repo-brief-r1-20261118`)

- **Frozen Protocol SHA-256**: `b9ae8cf6742d773ad3e9a9cb97259580df99a889dd55a54a8bdb47111c32075c` (verified intact)
- **Runtime**: `GitHub Copilot CLI 1.0.112.
Run 'copilot update' to check for updates.`, model `gpt-6-astra` (`reasoning_effort=low`), `72` paired live sessions (`24 tasks × 3 arms`), total live spend `$7.9981`
- **Identical `recall.jsonl` Provenance**: `tokenmasterx` `fbf4f4103d6dfbd4…`, `click` `2db4d3ad98b10174…`
- **Structural Brief Coverage (`<= 320` token budget)**:
  - `tokenmasterx`: `v1_warm` = `312t` (`5` distinct modules, `0` entrypoints) vs `r1_warm` = `304t` (`10` distinct modules, `3` entrypoints, `@root=token-master-plugin/skills/token-master/`)
  - `click`: `v1_warm` = `293t` (`7` distinct modules) vs `r1_warm` = `309t` (`11` of `16` core modules = `68.8%`, `@root=src/click/`)
- **Invariants**: `{"protocol_sha256_verified": true, "session_count": 72, "tm_lean_zero_brief_tokens": true, "tm_v1_nonzero_brief_recorded": true, "tm_r1_nonzero_brief_recorded": true, "tm_v1_call1_injected_every_session": true, "tm_r1_call1_injected_every_session": true, "all_briefs_within_320_tokens": true, "tokenomics_brief_subtraction_exact": true}`

## 1. Overall 3-Arm Summary (`N = 24` Paired Tasks per Arm)

| Arm | Pass | Mean Tokens | Median Tokens | Mean Billed USD | Mean Cold USD | Mean Calls | Mean Orient Calls | First-Tool Direct Symbol % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `tm_lean` | `24/24` (`100.0%`) | `35,945.1` | `28,822.5` | `$0.1137` | `$0.1541` | `4.50` | `2.67` | `8.3%` |
| `tm_v1_recall` | `24/24` (`100.0%`) | `34,539.3` | `25,722.5` | `$0.1137` | `$0.1541` | `4.12` | `1.75` | `58.3%` |
| `tm_r1_recall` | `24/24` (`100.0%`) | `30,589.2` | `23,608.5` | `$0.1058` | `$0.1462` | `3.67` | `1.08` | `79.2%` |

## 2. Primary Paired Comparisons & Holm–Bonferroni Hypothesis Tests (`10,000` Bootstrap Draws)

| Pairing | Metric | Base Mean | Treat Mean | Mean Diff `[95% CI]` | % Change `[95% CI]` | Lower/Tie/Higher | Wilcoxon `p` |
|---|---|---:|---:|---:|---:|---:|---:|
| `tm_r1_vs_tm_v1` | `total_tokens` | `34,539.2917` | `30,589.2500` | `-3,950.0417` `[-7,449.1938, -1,186.7354]` | `-11.44%` `[-20.51%, -3.66%]` | `14/0/10` | `0.068007` |
| `tm_r1_vs_tm_v1` | `billed_cost_usd` | `0.1137` | `0.1058` | `-0.0079` `[-0.0144, -0.0029]` | `-6.96%` `[-12.20%, -2.71%]` | `13/0/11` | `0.041742` |
| `tm_r1_vs_tm_v1` | `cold_cost_usd` | `0.1541` | `0.1462` | `-0.0079` `[-0.0143, -0.0029]` | `-5.13%` `[-8.98%, -2.00%]` | `13/0/11` | `0.043253` |
| `tm_r1_vs_tm_v1` | `model_calls` | `4.1250` | `3.6667` | `-0.4583` `[-0.9167, -0.0833]` | `-11.11%` `[-20.39%, -2.78%]` | `7/16/1` | `0.046875` |
| `tm_r1_vs_tm_v1` | `orientation_calls` | `1.7500` | `1.0833` | `-0.6667` `[-1.1667, -0.2500]` | `-38.09%` `[-61.91%, -17.14%]` | `8/16/0` | `0.007812` |
| `tm_r1_vs_tm_lean` | `total_tokens` | `35,945.1250` | `30,589.2500` | `-5,355.8750` `[-10,004.9594, -1,400.1094]` | `-14.90%` `[-26.21%, -4.16%]` | `14/0/10` | `0.052641` |
| `tm_r1_vs_tm_lean` | `billed_cost_usd` | `0.1137` | `0.1058` | `-0.0079` `[-0.0163, -0.0009]` | `-6.92%` `[-13.65%, -0.85%]` | `14/0/10` | `0.049061` |
| `tm_r1_vs_tm_lean` | `cold_cost_usd` | `0.1541` | `0.1462` | `-0.0079` `[-0.0161, -0.0010]` | `-5.11%` `[-10.02%, -0.66%]` | `14/0/10` | `0.049061` |
| `tm_r1_vs_tm_lean` | `model_calls` | `4.5000` | `3.6667` | `-0.8333` `[-1.3750, -0.3750]` | `-18.52%` `[-28.57%, -9.28%]` | `13/10/1` | `0.001465` |
| `tm_r1_vs_tm_lean` | `orientation_calls` | `2.6667` | `1.0833` | `-1.5833` `[-2.2083, -1.0417]` | `-59.38%` `[-76.79%, -42.65%]` | `18/6/0` | `0.000008` |
| `tm_v1_vs_tm_lean` | `total_tokens` | `35,945.1250` | `34,539.2917` | `-1,405.8333` `[-5,269.4781, +1,653.0417]` | `-3.91%` `[-14.05%, +4.85%]` | `9/0/15` | `0.899570` |
| `tm_v1_vs_tm_lean` | `billed_cost_usd` | `0.1137` | `0.1137` | `+0.0000` `[-0.0075, +0.0064]` | `+0.04%` `[-6.49%, +5.87%]` | `7/0/17` | `0.422341` |
| `tm_v1_vs_tm_lean` | `cold_cost_usd` | `0.1541` | `0.1541` | `+0.0000` `[-0.0077, +0.0064]` | `+0.03%` `[-4.86%, +4.22%]` | `7/0/17` | `0.422341` |
| `tm_v1_vs_tm_lean` | `model_calls` | `4.5000` | `4.1250` | `-0.3750` `[-0.7917, +0.0000]` | `-8.33%` `[-17.21%, +0.00%]` | `9/12/3` | `0.119141` |
| `tm_v1_vs_tm_lean` | `orientation_calls` | `2.6667` | `1.7500` | `-0.9167` `[-1.3750, -0.5000]` | `-34.38%` `[-50.79%, -20.31%]` | `15/8/1` | `0.000366` |

### Pre-Registered Hypothesis Family (`Holm-Bonferroni`, `alpha = 0.05`)

| Hypothesis | Raw Wilcoxon `p` | Holm–Bonferroni Adjusted `p` |
|---|---:|---:|
| `H1_r1_vs_v1_overall_tokens` | `0.068007` | `0.210564` |
| `H2_r1_vs_v1_bucket_A_tokens` | `0.148438` | `0.218750` |
| `H3_r1_vs_v1_bucket_B_tokens` | `0.109375` | `0.218750` |
| `H4_r1_vs_lean_overall_tokens` | `0.052641` | `0.210564` |

## 3. Exact Integer Certification Gates (`brainspace/certification.py`, PR `#35`)

Evaluated at `alpha = 0.05`, round `k = 1` (`alpha_1 = 0.030396`), `token_cap = 200,000`, `minimum_token_reduction = 1,000`, `quality_margin = 0.2` (`harm_limit(n=24) = 0`):

| Comparison | Harms (`inc pass, cand fail`) | `harm_passes` | `max-bet-v1` `bet_passes` | Certified |
|---|---:|---:|---:|---:|
| `tm_r1_vs_tm_lean` | `0` | `True` | `False` | `False` |
| `tm_v1_vs_tm_lean` | `0` | `True` | `False` | `False` |
| `tm_r1_vs_tm_v1` | `0` | `None` | `False` | `None` |

## 4. Bucket Breakdown (`8` Paired Tasks per Bucket)

| Bucket | Arm | Pass | Mean Tokens | Mean Billed USD | Mean Calls | Mean Orient Calls | First Direct % |
|---|---|---:|---:|---:|---:|---:|---:|
| `A_warm_crowdout_recovery` | `tm_lean` | `8/8` | `46,217.8` | `$0.1387` | `5.62` | `3.75` | `0.0%` |
| `A_warm_crowdout_recovery` | `tm_v1_recall` | `8/8` | `45,370.9` | `$0.1400` | `5.25` | `2.88` | `25.0%` |
| `A_warm_crowdout_recovery` | `tm_r1_recall` | `8/8` | `38,752.9` | `$0.1265` | `4.50` | `1.50` | `75.0%` |
| `B_noisy_recall_filtering` | `tm_lean` | `8/8` | `34,400.0` | `$0.1105` | `4.38` | `2.62` | `0.0%` |
| `B_noisy_recall_filtering` | `tm_v1_recall` | `8/8` | `31,466.9` | `$0.1071` | `3.75` | `1.38` | `75.0%` |
| `B_noisy_recall_filtering` | `tm_r1_recall` | `8/8` | `28,276.8` | `$0.1005` | `3.38` | `0.88` | `87.5%` |
| `C_prefix_folding_and_direct_control` | `tm_lean` | `8/8` | `27,217.6` | `$0.0919` | `3.50` | `1.62` | `25.0%` |
| `C_prefix_folding_and_direct_control` | `tm_v1_recall` | `8/8` | `26,780.1` | `$0.0941` | `3.38` | `1.00` | `75.0%` |
| `C_prefix_folding_and_direct_control` | `tm_r1_recall` | `8/8` | `24,738.1` | `$0.0905` | `3.12` | `0.88` | `75.0%` |

### Bucket-Level `tm_r1_recall vs tm_v1_recall` & `tm_r1_recall vs tm_lean` Token Effects

| Bucket | Pairing | Mean Token Diff `[95% CI]` | % Token Change `[95% CI]` | Lower/Tie/Higher | Wilcoxon `p` |
|---|---|---:|---:|---:|---:|
| `A_warm_crowdout_recovery` | `tm_r1_vs_tm_v1` | `-6,618.0` `[-15,584.4, +154.3]` | `-14.59%` `[-33.44%, +0.41%]` | `6/0/2` | `0.148438` |
| `A_warm_crowdout_recovery` | `tm_r1_vs_tm_lean` | `-7,464.9` `[-14,348.2, -750.5]` | `-16.15%` `[-30.60%, -1.80%]` | `6/0/2` | `0.109375` |
| `B_noisy_recall_filtering` | `tm_r1_vs_tm_v1` | `-3,190.1` `[-6,149.0, -957.3]` | `-10.14%` `[-22.34%, -2.24%]` | `5/0/3` | `0.109375` |
| `B_noisy_recall_filtering` | `tm_r1_vs_tm_lean` | `-6,123.2` `[-17,979.9, +2,096.8]` | `-17.80%` `[-45.51%, +5.67%]` | `5/0/3` | `0.460938` |
| `C_prefix_folding_and_direct_control` | `tm_r1_vs_tm_v1` | `-2,042.0` `[-6,153.8, +20.4]` | `-7.62%` `[-16.93%, +0.10%]` | `3/0/5` | `0.460938` |
| `C_prefix_folding_and_direct_control` | `tm_r1_vs_tm_lean` | `-2,479.5` `[-6,682.2, +634.7]` | `-9.11%` `[-18.23%, +2.86%]` | `3/0/5` | `0.742188` |

## 5. Repository Generalization (`tokenmasterx` vs External `pallets/click`)

| Repo | Arm | Pass | Mean Tokens | Mean Billed USD | Mean Calls | Mean Orient Calls |
|---|---|---:|---:|---:|---:|---:|
| `tokenmasterx` | `tm_lean` | `12/12` | `35,055.1` | `$0.1147` | `4.33` | `2.50` |
| `tokenmasterx` | `tm_v1_recall` | `12/12` | `33,311.6` | `$0.1143` | `3.92` | `1.83` |
| `tokenmasterx` | `tm_r1_recall` | `12/12` | `28,450.0` | `$0.1027` | `3.42` | `0.92` |
| `click` | `tm_lean` | `12/12` | `36,835.2` | `$0.1127` | `4.67` | `2.83` |
| `click` | `tm_v1_recall` | `12/12` | `35,767.0` | `$0.1131` | `4.33` | `1.67` |
| `click` | `tm_r1_recall` | `12/12` | `32,728.5` | `$0.1090` | `3.92` | `1.25` |

## 6. Per-Task Audit Table (`24 Tasks × 3 Arms = 72 Sessions`)

| Task | Repo | Bucket | Kind | `tm_lean` Tok (Calls/Orient) | `tm_v1_recall` Tok (Calls/Orient) | `tm_r1_recall` Tok (Calls/Orient) | `r1 - v1` Tok |
|---|---|---|---|---:|---:|---:|---:|
| `T01` | `tokenmasterx` | `A` | `trace` | `21,952` (`3/2`) | `22,647` (`3/2`) | `29,638` (`4/2`) | `+6,991` |
| `T02` | `tokenmasterx` | `A` | `trace` | `38,060` (`5/3`) | `49,453` (`6/4`) | `16,084` (`2/0`) | `-33,369` |
| `T03` | `tokenmasterx` | `A` | `edit` | `56,734` (`6/4`) | `50,746` (`5/3`) | `47,321` (`5/0`) | `-3,425` |
| `T04` | `tokenmasterx` | `A` | `edit` | `65,939` (`7/4`) | `63,199` (`6/3`) | `59,785` (`6/3`) | `-3,414` |
| `T05` | `tokenmasterx` | `B` | `trace` | `23,338` (`3/2`) | `33,266` (`4/2`) | `24,443` (`3/0`) | `-8,823` |
| `T06` | `tokenmasterx` | `B` | `edit` | `38,052` (`5/3`) | `38,592` (`5/3`) | `38,020` (`5/3`) | `-572` |
| `T07` | `tokenmasterx` | `B` | `trace` | `57,745` (`7/5`) | `23,121` (`3/1`) | `15,140` (`2/0`) | `-7,981` |
| `T08` | `tokenmasterx` | `B` | `trace` | `21,957` (`3/2`) | `23,083` (`3/1`) | `15,313` (`2/0`) | `-7,770` |
| `T09` | `tokenmasterx` | `C` | `edit` | `39,990` (`5/3`) | `36,259` (`4/1`) | `36,258` (`4/1`) | `-1` |
| `T10` | `tokenmasterx` | `C` | `trace` | `21,239` (`3/1`) | `22,160` (`3/1`) | `22,178` (`3/1`) | `+18` |
| `T11` | `tokenmasterx` | `C` | `trace` | `21,314` (`3/1`) | `22,250` (`3/1`) | `22,247` (`3/1`) | `-3` |
| `T12` | `tokenmasterx` | `C` | `trace` | `14,341` (`2/0`) | `14,963` (`2/0`) | `14,973` (`2/0`) | `+10` |
| `C01` | `click` | `A` | `trace` | `28,656` (`4/3`) | `22,309` (`3/0`) | `22,342` (`3/0`) | `+33` |
| `C02` | `click` | `A` | `trace` | `28,989` (`4/2`) | `30,256` (`4/2`) | `22,796` (`3/1`) | `-7,460` |
| `C03` | `click` | `A` | `edit` | `54,343` (`7/5`) | `57,785` (`7/4`) | `57,772` (`7/4`) | `-13` |
| `C04` | `click` | `A` | `edit` | `75,069` (`9/7`) | `66,572` (`8/5`) | `54,285` (`6/2`) | `-12,287` |
| `C05` | `click` | `B` | `trace` | `32,971` (`4/1`) | `27,369` (`3/0`) | `26,855` (`3/0`) | `-514` |
| `C06` | `click` | `B` | `edit` | `57,397` (`7/5`) | `67,769` (`7/4`) | `67,853` (`7/4`) | `+84` |
| `C07` | `click` | `B` | `trace` | `22,090` (`3/2`) | `15,472` (`2/0`) | `15,494` (`2/0`) | `+22` |
| `C08` | `click` | `B` | `trace` | `21,650` (`3/1`) | `23,063` (`3/0`) | `23,096` (`3/0`) | `+33` |
| `C09` | `click` | `C` | `edit` | `63,454` (`7/6`) | `65,199` (`8/5`) | `48,778` (`6/4`) | `-16,421` |
| `C10` | `click` | `C` | `trace` | `21,203` (`3/1`) | `14,764` (`2/0`) | `14,766` (`2/0`) | `+2` |
| `C11` | `click` | `C` | `trace` | `22,224` (`3/1`) | `24,076` (`3/0`) | `24,121` (`3/0`) | `+45` |
| `C12` | `click` | `C` | `trace` | `13,976` (`2/0`) | `14,570` (`2/0`) | `14,584` (`2/0`) | `+14` |

## 7. Promotion Decision

- **`keep_r1_as_default`**: `True` (Bucket C `@root=`-folded edit pass check: `True`)
