# R6 Skeletal Class Projection — Round 1 Benchmark Results (`class-skeleton-r6-20261119`)

- **Protocol SHA-256**: `78024855c5cc37768205359d2afa17341036cab208f498089f7b0afea3ede9da` (verified intact)
- **Host / Model**: `GitHub Copilot CLI 1.0.112.` · `gpt-6-astra` (`reasoning_effort=low`)
- **Sample**: `72` live sessions (`24` paired tasks × `3` arms: `stock`, `tm_v1`, `tm_r6`; `12` `TokenMasterX @ dcd73c4a` + `12` `Click 8.1.8 @ 934813e4`)
- **Zero Prompt-Prefix Confound (`tm_v1` vs `tm_r6`)**: R1 `brief.md` tokens identical on `24/24` tasks; Call-1 input tokens mean diff `-0.79` tokens (max `±16` from host timestamp/lane path).

## 1. Overall & Oversized-Class Arm Summary

### 1.1 Oversized-Class Target Stratum (Buckets A + B, `N = 16` paired tasks)

| Arm | Pass | Mean Total Tokens | Mean Uncached Input | Mean `read_symbol` Calls | Mean `read_symbol` Tokens | Mean Tool-Result Tokens | Skeleton Hits | Truncated Reads | Ambiguous Hits | Mean Calls | Mean Billed USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stock` | `16/16` (`100.0%`) | `74,744` | `13` | `0.00` | `0` | `3,060` | `0.00` | `0.00` | `0.00` | `4.44` | `$0.2079` |
| `tm_v1` | `16/16` (`100.0%`) | `35,472` | `13` | `2.75` | `1,180` | `1,552` | `0.00` | `0.06` | `0.31` | `4.19` | `$0.1345` |
| **`tm_r6`** | **`16/16` (`100.0%`)** | **`33,836`** | **`12`** | **`2.44`** | **`984`** | **`1,302`** | **`0.06`** | **`0.00`** | **`0.00`** | **`4.06`** | **`$0.1298`** |

### 1.2 All Tasks Pooled (Buckets A + B + C, `N = 24` paired tasks)

| Arm | Pass | Mean Total Tokens | Median Total Tokens | Mean Uncached Input | Mean `read_symbol` Tokens | Mean Tool-Result Tokens | Mean Calls | Mean Billed USD | Mean Cold USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stock` | `24/24` (`100.0%`) | `71,324` | `69,563` | `13` | `0` | `2,893` | `4.29` | `$0.1952` | `$0.3028` |
| `tm_v1` | `24/24` (`100.0%`) | `32,110` | `26,933` | `11` | `1,364` | `1,626` | `3.79` | `$0.1238` | `$0.1625` |
| **`tm_r6`** | **`24/24` (`100.0%`)** | **`31,137`** | **`24,200`** | **`11`** | **`1,239`** | **`1,469`** | **`3.71`** | **`$0.1216`** | **`$0.1620`** |

## 2. Pre-Registered Hypotheses (`H1..H4`, Holm-Bonferroni Adjusted)

| Hypothesis | Comparison & Metric | Mean Change (`%` [95% Bootstrap CI]) | Wins / Ties / Losses | Raw Wilcoxon `p` | Holm `p` |
|---|---|---:|---:|---:|---:|
| **`H1`** (`N=16` A+B) | `tm_r6` vs `tm_v1` `tool_result_tokens` | `-250` (`-16.1%` [`-37.5%`, `+12.2%`]) | `8W / 2T / 6L` | `0.951538` | `1.000000` |
| **`H2`** (`N=16` A+B) | `tm_r6` vs `tm_v1` `total_tokens` | `-1,636` (`-4.6%` [`-13.8%`, `+5.5%`]) | `9W / 0T / 7L` | `0.463745` | `1.000000` |
| **`H3`** (`N=24` All) | `tm_r6` vs `tm_v1` `total_tokens` | `-973` (`-3.0%` [`-10.1%`, `+4.5%`]) | `11W / 2T / 11L` | `0.708309` | `1.000000` |
| **`H4`** (`N=24` All) | `tm_r6` vs `stock` `total_tokens` | `-40,187` (`-56.3%` [`-62.1%`, `-50.5%`]) | `24W / 0T / 0L` | `0.000000` | `0.000000` |

## 3. Bucket Breakdown (`N = 8` per Bucket)

| Bucket | `stock` Tokens (Pass) | `tm_v1` Tokens (Pass) | `tm_r6` Tokens (Pass) | `tm_r6` vs `tm_v1` Tokens (`p`) | `tm_r6` vs `tm_v1` `read_symbol` Tokens |
|---|---:|---:|---:|---:|---:|
| `A_oversized_class_trace` | `50,447` (`8/8`) | `22,806` (`8/8`) | **`20,277` (`8/8`)** | `-11.1%` (`p=0.1953`) | `1,757` → `1,532` (`-12.8%`) |
| `B_oversized_class_edit` | `99,041` (`8/8`) | `48,138` (`8/8`) | **`47,396` (`8/8`)** | `-1.5%` (`p=1.0000`) | `604` → `436` (`-27.8%`) |
| `C_small_symbol_control` | `64,484` (`8/8`) | `25,386` (`8/8`) | **`25,739` (`8/8`)** | `+1.4%` (`p=0.5625`) | `1,731` → `1,748` (`+1.0%`) |

### 3.1 Mechanism-Exposure Post-Hoc Diagnostic (Why Explicit Method-Named Prompts Bypassed Class Reads)

Because Round 1 prompts explicitly named target methods (`Class.method`), `gpt-6-astra` invoked `read_symbol('path::Class.method')` directly on `12/16` Buckets A+B tasks without reading the container class or hitting `@overload` stubs:

| Oversized Subgroup | Tasks (`N`) | `tm_v1` Mean Tokens | `tm_r6` Mean Tokens | `tm_r6` vs `tm_v1` (`p`) |
|---|---:|---:|---:|---:|
| **Mechanism-exposed** (class read or `@overload` hit: `T02, C01, C02, C03`) | `4` | `25,684` | **`20,880`** | **`-18.7%`** (`p=0.2500`) |
| **Method-named bypass** (direct `Class.method` read only) | `12` | `38,735` | `38,155` | `-1.5%` (`p=0.9697`) |

## 4. Exact Integer Certification Gates (`brainspace/certification.py`, Round `k = 1`, `alpha_1 = 0.03039636`)

| Gate Comparison | `N` | Harms (Limit) | `harm_passes` | `max-bet-v1` Wealth | `max-bet-v1` `bet_passes` | Certified vs True-Off |
|---|---:|---:|---|---:|---|---|
| `tm_r6_vs_stock` | `24` | `0` (`<=0` if true-off) | `True` | `1.006521` | `True` | `True` |
| `tm_v1_vs_stock` | `24` | `0` (`<=0` if true-off) | `True` | `0.921135` | `False` | `False` |
| `tm_r6_vs_tm_v1` | `24` | `0` (`<=0` if true-off) | `None` | `0.014996` | `False` | `None` |
| `tm_r6_vs_tm_v1` (Oversized A+B) | `16` | `0` | `None` (active incumbent) | `0.015831` | `False` | `N/A` |

## 5. Per-Task Paired Ledger (`24` Tasks × `3` Arms)

| Task | Repo | Bucket | Kind | `stock` Tokens (Pass) | `tm_v1` Tokens / `rs_tok` (Pass) | `tm_r6` Tokens / `rs_tok` / `skel` (Pass) | `r6 - v1` Tokens |
|---|---|---|---|---:|---:|---:|---:|
| `T01` | `tokenmasterx` | `A` | `trace` | `61,931` (✓) | `15,824` / `1,408` (✓) | **`15,814`** / `1,408` / `0` (✓) | `-10` |
| `T02` | `tokenmasterx` | `A` | `trace` | `48,753` (✓) | `28,304` / `3,874` (✓) | **`23,995`** / `1,825` / `0` (✓) | `-4,309` |
| `T03` | `tokenmasterx` | `A` | `trace` | `67,146` (✓) | `32,616` / `1,542` (✓) | **`23,933`** / `1,542` / `0` (✓) | `-8,683` |
| `T04` | `tokenmasterx` | `A` | `trace` | `69,475` (✓) | `16,178` / `1,288` (✓) | **`23,859`** / `1,288` / `0` (✓) | `+7,681` |
| `C01` | `click` | `A` | `trace` | `46,248` (✓) | `23,520` / `1,080` (✓) | **`15,814`** / `1,193` / `0` (✓) | `-7,706` |
| `C02` | `click` | `A` | `trace` | `32,370` (✓) | `25,352` / `2,601` (✓) | **`26,937`** / `2,641` / `1` (✓) | `+1,585` |
| `C03` | `click` | `A` | `trace` | `46,732` (✓) | `25,562` / `1,838` (✓) | **`16,774`** / `1,934` / `0` (✓) | `-8,788` |
| `C04` | `click` | `A` | `trace` | `30,922` (✓) | `15,093` / `427` (✓) | **`15,089`** / `427` / `0` (✓) | `-4` |
| `T05` | `tokenmasterx` | `B` | `edit` | `71,702` (✓) | `35,657` / `356` (✓) | **`47,602`** / `1,514` / `0` (✓) | `+11,945` |
| `T06` | `tokenmasterx` | `B` | `edit` | `122,509` (✓) | `58,504` / `1,743` (✓) | **`43,852`** / `191` / `0` (✓) | `-14,652` |
| `T07` | `tokenmasterx` | `B` | `edit` | `69,651` (✓) | `31,911` / `247` (✓) | **`32,001`** / `247` / `0` (✓) | `+90` |
| `T08` | `tokenmasterx` | `B` | `edit` | `134,007` (✓) | `55,954` / `1,935` (✓) | **`44,698`** / `984` / `0` (✓) | `-11,256` |
| `C05` | `click` | `B` | `edit` | `97,101` (✓) | `48,178` / `97` (✓) | **`48,624`** / `97` / `0` (✓) | `+446` |
| `C06` | `click` | `B` | `edit` | `113,408` (✓) | `48,830` / `295` (✓) | **`56,480`** / `295` / `0` (✓) | `+7,650` |
| `C07` | `click` | `B` | `edit` | `105,192` (✓) | `57,894` / `108` (✓) | **`57,387`** / `108` / `0` (✓) | `-507` |
| `C08` | `click` | `B` | `edit` | `78,761` (✓) | `48,179` / `49` (✓) | **`48,522`** / `49` / `0` (✓) | `+343` |
| `T09` | `tokenmasterx` | `C` | `trace` | `77,376` (✓) | `16,381` / `1,922` (✓) | **`16,369`** / `1,922` / `0` (✓) | `-12` |
| `T10` | `tokenmasterx` | `C` | `trace` | `75,776` (✓) | `16,684` / `2,178` (✓) | **`16,684`** / `2,178` / `0` (✓) | `+0` |
| `T11` | `tokenmasterx` | `C` | `trace` | `62,215` (✓) | `24,371` / `1,196` (✓) | **`24,404`** / `1,158` / `0` (✓) | `+33` |
| `T12` | `tokenmasterx` | `C` | `edit` | `70,638` (✓) | `47,054` / `2,516` (✓) | **`50,682`** / `3,969` / `0` (✓) | `+3,628` |
| `C09` | `click` | `C` | `trace` | `29,945` (✓) | `16,089` / `1,669` (✓) | **`16,089`** / `1,669` / `0` (✓) | `+0` |
| `C10` | `click` | `C` | `trace` | `33,833` (✓) | `16,700` / `2,134` (✓) | **`15,540`** / `857` / `0` (✓) | `-1,160` |
| `C11` | `click` | `C` | `trace` | `61,076` (✓) | `15,853` / `1,371` (✓) | **`15,863`** / `1,371` / `0` (✓) | `+10` |
| `C12` | `click` | `C` | `edit` | `105,010` (✓) | `49,958` / `859` (✓) | **`50,282`** / `859` / `0` (✓) | `+324` |
