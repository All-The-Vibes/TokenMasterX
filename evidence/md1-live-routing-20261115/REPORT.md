# Live 3-Arm Routing Study Report (`md1-live-routing-20261115`)

- **Repository Commit:** `f9750ff` (`All-The-Vibes/TokenMasterX`)
- **Copilot CLI:** `GitHub Copilot CLI 1.0.112.
Run 'copilot update' to check for updates.` (`gpt-6-astra`, reasoning `low`)
- **MD-1 Deployment:** `https://raifoundry.services.ai.azure.com` (`Microsoft-Decision-1` v1, threshold `0.5`)
- **Protocol Freeze SHA-256:** `ab44b2a0444127bea9b25d1dd4f739e38392741025b95c9f5468361d3db47d22` (audit: `PASS`, `45` sessions, `168` billed calls verified)

## 1. Overall Results Across All 15 Paired Tasks (`45` Sessions)

| Metric | `stock` | `tm_regex` (`--lean`) | `tm_md1` (`--lean` + MD-1) |
| --- | ---: | ---: | ---: |
| Task pass rate | 15/15 (100.0%) | 14/15 (93.3%) | 15/15 (100.0%) |
| Needed capability recalled | 15/15 | 10/15 | 15/15 |
| Mean active tools / session | 21.0 | 9.3 | 9.9 |
| Mean `tool_tokens + tool_instructions` | 12,156 | 4,633 | 5,030 |
| Mean first-call input tokens | 14,446 | 7,409 | 7,793 |
| Mean raw tokens / session | 65,380 | 35,807 | 38,285 |
| Total raw tokens (15 tasks) | 980,700 | 537,104 | 574,278 |
| Total cold-start cost (`cold_usd`) | $4.5471 | $2.8546 | $3.0198 |
| Total as-run billed cost (`billed_usd`) | $2.8682 | $2.4238 | $2.5073 |
| Mean session duration (s) | 19.1s | 20.5s | 20.1s |

## 2. Pairwise Statistical Comparisons (`n = 15` Paired Tasks, 10,000 Bootstrap Draws)

| Endpoint | Comparison | Mean Change (%) | 95% Bootstrap CI (%) | Wilcoxon `p` | Holm `p` | Pairs (Lower / Higher / Tie) |
| --- | --- | ---: | --- | ---: | ---: | --- |
| `raw_tokens` | `tm_md1_vs_stock` | -41.4% | [-52.2%, -28.7%] | 0.0001 | 0.0002 | 15/0/0 |
| `raw_tokens` | `tm_regex_vs_stock` | -45.2% | [-54.8%, -35.8%] | 0.0001 | 0.0002 | 15/0/0 |
| `raw_tokens` | `tm_md1_vs_tm_regex` | +6.9% | [-11.9%, +23.2%] | 0.2524 | 0.2524 | 6/9/0 |
| `cold_usd` | `tm_md1_vs_stock` | -33.6% | [-41.9%, -24.4%] | 0.0001 | 0.0002 | 15/0/0 |
| `cold_usd` | `tm_regex_vs_stock` | -37.2% | [-43.3%, -31.4%] | 0.0001 | 0.0002 | 15/0/0 |
| `cold_usd` | `tm_md1_vs_tm_regex` | +5.8% | [-1.3%, +11.9%] | 0.3303 | 0.3303 | 7/8/0 |
| `billed_usd` | `tm_md1_vs_stock` | -12.6% | [-19.7%, -5.5%] | 0.0103 | 0.0308 | 12/3/0 |
| `billed_usd` | `tm_regex_vs_stock` | -15.5% | [-25.9%, -5.0%] | 0.0215 | 0.0431 | 11/4/0 |
| `billed_usd` | `tm_md1_vs_tm_regex` | +3.4% | [-9.2%, +18.0%] | 0.5995 | 0.5995 | 7/8/0 |
| `first_call_input_tokens` | `tm_md1_vs_stock` | -46.1% | [-51.2%, -39.7%] | 0.0001 | 0.0002 | 15/0/0 |
| `first_call_input_tokens` | `tm_regex_vs_stock` | -48.7% | [-53.7%, -42.0%] | 0.0001 | 0.0002 | 15/0/0 |
| `first_call_input_tokens` | `tm_md1_vs_tm_regex` | +5.2% | [+0.8%, +11.6%] | 0.0054 | 0.0054 | 3/12/0 |
| `seconds` | `tm_md1_vs_stock` | +5.1% | [-6.6%, +19.1%] | 0.4212 | 1.0000 | 4/11/0 |
| `seconds` | `tm_regex_vs_stock` | +7.1% | [-4.4%, +26.1%] | 0.3894 | 1.0000 | 5/10/0 |
| `seconds` | `tm_md1_vs_tm_regex` | -1.9% | [-13.2%, +9.4%] | 0.8469 | 1.0000 | 8/7/0 |

## 3. Bucket-Stratified Breakdown (`5` Tasks per Bucket)

| Bucket | Arm | Pass | Capability Recalled | Native Tool Used | Shell Workarounds | Avg False-Keep Tools | Mean Schema+Instr Toks | Mean Raw Toks | Total Cold USD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `A_pure_coding` | `stock` | 5/5 | 5/5 | 0/5 | 0/5 | 13.0 | 12,156 | 73,216 | $1.7450 |
| `A_pure_coding` | `tm_regex` | 5/5 | 5/5 | 0/5 | 0/5 | 0.0 | 3,649 | 39,524 | $1.0943 |
| `A_pure_coding` | `tm_md1` | 5/5 | 5/5 | 0/5 | 0/5 | 0.0 | 3,649 | 40,701 | $1.1518 |
| `B_multi_capability` | `stock` | 5/5 | 5/5 | 5/5 | 0/5 | 11.0 | 12,156 | 66,618 | $1.3067 |
| `B_multi_capability` | `tm_regex` | 4/5 | 0/5 | 1/5 | 3/5 | 0.0 | 3,649 | 29,902 | $0.7042 |
| `B_multi_capability` | `tm_md1` | 5/5 | 5/5 | 5/5 | 0/5 | 0.0 | 4,839 | 30,201 | $0.7255 |
| `C_adversarial_lookalike` | `stock` | 5/5 | 5/5 | 0/5 | 0/5 | 13.0 | 12,156 | 56,307 | $1.4953 |
| `C_adversarial_lookalike` | `tm_regex` | 5/5 | 5/5 | 0/5 | 0/5 | 3.8 | 6,601 | 37,995 | $1.0561 |
| `C_adversarial_lookalike` | `tm_md1` | 5/5 | 5/5 | 0/5 | 0/5 | 3.8 | 6,601 | 43,954 | $1.1424 |

## 4. MD-1 Routing Scores & Pre-Launch Latency (`15` Frozen Prompts)

- **Latency:** mean `650.1 ms`, median `628.4 ms`, p90 `702.9 ms`, max `898.6 ms`.

| Task | Bucket | Needed | Regex Kept | MD-1 Standalone | `v0.3.0` Union Kept | Latency (ms) | Top MD-1 Group Scores |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `A01` | `A_pure_coding` | `[]` | `[]` | `[]` | `[]` | 899 | skills=0.016, copilot_docs=0.001, workflows=0.001 |
| `A02` | `A_pure_coding` | `[]` | `[]` | `[]` | `[]` | 631 | skills=0.042, background_shell=0.001, workflows=0.001 |
| `A03` | `A_pure_coding` | `[]` | `[]` | `[]` | `[]` | 605 | skills=0.042, workflows=0.002, session_history=0.001 |
| `A04` | `A_pure_coding` | `[]` | `[]` | `[]` | `[]` | 624 | skills=0.003, workflows=0.001, agents=0.001 |
| `A05` | `A_pure_coding` | `[]` | `[]` | `[]` | `[]` | 680 | skills=0.037, workflows=0.001, agents=0.000 |
| `B01` | `B_multi_capability` | `['agents']` | `[]` | `['agents']` | `['agents']` | 628 | agents=1.000, skills=0.012, background_shell=0.011 |
| `B02` | `B_multi_capability` | `['session_history']` | `[]` | `['session_history']` | `['session_history']` | 573 | session_history=0.999, skills=0.003, sql=0.002 |
| `B03` | `B_multi_capability` | `['background_shell']` | `[]` | `['background_shell']` | `['background_shell']` | 599 | background_shell=0.999, copilot_docs=0.006, skills=0.005 |
| `B04` | `B_multi_capability` | `['copilot_docs']` | `[]` | `['copilot_docs']` | `['copilot_docs']` | 645 | copilot_docs=0.999, session_history=0.003, skills=0.003 |
| `B05` | `B_multi_capability` | `['sql']` | `[]` | `['sql']` | `['sql']` | 685 | sql=0.999, session_history=0.010, skills=0.010 |
| `C01` | `C_adversarial_lookalike` | `[]` | `['workflows']` | `[]` | `['workflows']` | 603 | skills=0.020, workflows=0.012, agents=0.001 |
| `C02` | `C_adversarial_lookalike` | `[]` | `['session_history']` | `[]` | `['session_history']` | 678 | session_history=0.005, skills=0.004, copilot_docs=0.003 |
| `C03` | `C_adversarial_lookalike` | `[]` | `['background_shell', 'sql']` | `[]` | `['background_shell', 'sql']` | 715 | skills=0.014, sql=0.012, background_shell=0.002 |
| `C04` | `C_adversarial_lookalike` | `[]` | `['agents', 'copilot_docs']` | `[]` | `['agents', 'copilot_docs']` | 578 | copilot_docs=0.053, skills=0.018, workflows=0.003 |
| `C05` | `C_adversarial_lookalike` | `[]` | `['agents', 'session_history', 'workflows']` | `[]` | `['agents', 'session_history', 'workflows']` | 608 | skills=0.023, workflows=0.009, session_history=0.005 |

## 5. Per-Task Live Session Ledger (`45` Sessions)

| Task | Bucket | Pass (`S / R / M`) | Calls (`S / R / M`) | Raw Tokens (`S / R / M`) | Cold USD (`S / R / M`) | Native Cap Tool (`S / R / M`) |
| --- | --- | --- | --- | --- | --- | --- |
| `A01` | `A_pure_coding` | Y / Y / Y | 3 / 3 / 3 | 47,468 / 22,894 / 23,046 | $0.2620 / $0.1355 / $0.1384 | - / - / - |
| `A02` | `A_pure_coding` | Y / Y / Y | 2 / 2 / 2 | 32,057 / 16,934 / 16,145 | $0.2390 / $0.1409 / $0.1316 | - / - / - |
| `A03` | `A_pure_coding` | Y / Y / Y | 2 / 2 / 2 | 35,235 / 19,317 / 19,313 | $0.2810 / $0.1735 / $0.1735 | - / - / - |
| `A04` | `A_pure_coding` | Y / Y / Y | 5 / 5 / 5 | 99,960 / 59,804 / 59,695 | $0.4495 / $0.3113 / $0.3092 | - / - / - |
| `A05` | `A_pure_coding` | Y / Y / Y | 7 / 6 / 5 | 151,359 / 78,670 / 85,305 | $0.5135 / $0.3332 / $0.3992 | - / - / - |
| `B01` | `B_multi_capability` | Y / Y / Y | 6 / 2 / 6 | 45,179 / 14,084 / 33,731 | $0.2149 / $0.1220 / $0.1461 | Y / W / Y |
| `B02` | `B_multi_capability` | Y / N / Y | 6 / 4 / 3 | 88,618 / 27,210 / 24,753 | $0.2838 / $0.1183 / $0.1325 | Y / - / Y |
| `B03` | `B_multi_capability` | Y / Y / Y | 6 / 5 / 6 | 89,376 / 36,346 / 43,766 | $0.2921 / $0.1698 / $0.1599 | Y / Y / Y |
| `B04` | `B_multi_capability` | Y / Y / Y | 4 / 8 / 3 | 65,075 / 58,233 / 25,992 | $0.2755 / $0.1855 / $0.1539 | Y / W / Y |
| `B05` | `B_multi_capability` | Y / Y / Y | 3 / 2 / 3 | 44,840 / 13,638 / 22,763 | $0.2404 / $0.1086 / $0.1331 | Y / W / Y |
| `C01` | `C_adversarial_lookalike` | Y / Y / Y | 3 / 3 / 3 | 46,513 / 27,520 / 27,776 | $0.2562 / $0.1628 / $0.1609 | - / - / - |
| `C02` | `C_adversarial_lookalike` | Y / Y / Y | 3 / 3 / 3 | 46,150 / 27,100 / 27,515 | $0.2393 / $0.1473 / $0.1504 | - / - / - |
| `C03` | `C_adversarial_lookalike` | Y / Y / Y | 2 / 2 / 2 | 30,025 / 16,084 / 16,082 | $0.2152 / $0.1214 / $0.1214 | - / - / - |
| `C04` | `C_adversarial_lookalike` | Y / Y / Y | 2 / 2 / 2 | 33,156 / 23,173 / 23,179 | $0.2545 / $0.1847 / $0.1847 | - / - / - |
| `C05` | `C_adversarial_lookalike` | Y / Y / Y | 6 / 5 / 6 | 125,689 / 96,097 / 125,217 | $0.5301 / $0.4399 / $0.5249 | - / - / - |

## 6. Key Behavioral & Architectural Findings

1. **Pure-Coding Schema Savings Hold Live (`Bucket A`, `15/15` pass across all arms):**
   - When all 13 auxiliary tools are pruned (`8` active tools instead of `21`), Copilot CLI `1.0.112`'s `promptCacheBreakState` confirms static schema + tool-instruction overhead drops from **`12,156` tokens/call** (`9,394` `tool_tokens` + `2,762` `tool_instructions`) to **`3,649` tokens/call (`-70.0%`, `-8,507` tokens/call)**.
   - Across `A01`–`A05`, raw session tokens fall **`-46.0%`** (`tm_regex`) and **`-44.4%`** (`tm_md1`) and cold-start cost falls **`-37.3%`** and **`-34.0%`** with `5/5` task accuracy.

2. **Regex-Only `--lean` Breaks Natural Multi-Capability Workflows (`Bucket B`, `0/5` capability recall on `tm_regex` vs `5/5` on `tm_md1`):**
   - **`B02` (`session_history`) fails outright on `tm_regex`:** Without `session_store_sql`, `tm_regex` searches repo files and returns `Unknown`, whereas `tm_md1` (`session_history = 0.999`) recalls `session_store_sql` and passes in `3` calls (`24,753` tokens vs `stock`'s `88,618`, **`-72.1%`**).
   - **`B04` (`copilot_docs`) thrashes on `tm_regex`:** Stripping `fetch_copilot_cli_documentation` forces `tm_regex` into `8` shell/search calls (`58,233` tokens, `25.9s`), whereas `tm_md1` (`copilot_docs = 0.999`) finishes cleanly in `3` calls (`25,992` tokens, `19.3s` — **`-55.4%` fewer tokens than `tm_regex`** and **`-60.1%` fewer than `stock`**).
   - **`B01` (`agents`) & `B05` (`sql`) silently violate workflow constraints on `tm_regex`:** Stripping `task` (`B01`) prevents helper subagent delegation (`0` subagent calls vs `4` on `stock` and `tm_md1`), and stripping `sql` (`B05`) prevents creating the requested `headroom_suite` table in the built-in session SQLite database.
   - **`B03` (`background_shell`) exposes a split-schema hazard in `tm_regex`:** Even when `read_powershell` and `stop_powershell` are excluded from `active_tools`, `powershell`'s own description still instructs the model to use them. Unable to read `READY:<port>` from its async shell cleanly, `tm_regex` scraped OS-wide `Get-NetTCPConnection` and `Win32_Process` tables across sibling processes (`36.9s`, `$0.1698`) before hallucinating an unlisted `read_powershell` call at cleanup; `tm_md1` (`background_shell = 0.999`) completed cleanly via `read_powershell` + `stop_powershell` in `26.9s` (`$0.1599`).

3. **Architectural Discovery on Adversarial Lookalikes (`Bucket C`): `v0.3.0`'s Additive `regex | md1` Union Leaks False Positives That Standalone MD-1 Rejects (`0/5` vs `5/5`):**
   - Standalone `Microsoft-Decision-1` (`MD-1 Standalone`) achieved **`15/15` (`100%`) exact family classification** across all three buckets: `>= 0.999` on every true Bucket B capability and `<= 0.053` on every Bucket A and Bucket C distractor (`0/5` false-keep prompts on Bucket C), with **`628 ms` median** (`703 ms` p90) one-time pre-launch HTTP latency.
   - However, `brainspace_copilot_bridge.py` (`lines 324–328`) runs `CAPABILITY_GROUPS` regex matching unconditionally and **only unions** `md1_families(prompt_text)` (`# opt-in; only ever adds families`), rendering the `false` criteria in `MD1_QUESTIONS` (`lines 120–160`) dead code whenever any regex matches. Consequently, `v0.3.0`'s `tm_md1` inherited all `5/5` regex false positives on `C01`–`C05`, inflating schema + tool-instruction overhead from **`3,649` -> `6,601` tokens/call (`+80.9%`)** (and up to `10,345` tokens/call on `C05`, nearly erasing `--lean` savings).
   - **Recommended `v0.3.1` fix (`~10` lines in `select_excluded_tools`):** Keep deterministic hard signals unconditional (`--agent`, `--fleet`, `--resume`/`--continue`, `/slash` commands, `TOKENMASTER_KEEP_TOOLS`, and literal installed skill/agent names), but when `md1_scores(prompt_text)` returns a score for `family`, let MD-1 decide that family instead of `CAPABILITY_GROUPS` regexes, falling back to regexes only when MD-1 is unset or unreachable.
