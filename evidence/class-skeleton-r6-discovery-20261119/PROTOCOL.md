# Pre-Registered Confirmation Protocol (Round `k = 2`) — R6 Skeletal Class Projection on Naturalistic Class-Discovery & Behavioral Edit Tasks (`class-skeleton-r6-discovery-20261119`)

## 1. Rationale, Sequential Alpha-Spending Budget, and Anti-Leakage Invariant

In **Round 1 (`evidence/class-skeleton-r6-20261119`, $k = 1$, $\alpha_1 = \text{round\_alpha}(0.05, 1) = 0.03039636$, $72$ live sessions, $72/72$ PASS)**:
- End-to-end `tm_r6` cut pooled tokens **`-56.3%`** vs true-off `stock` (`71,324 -> 31,137` tokens, `24W/0T/0L`, Holm `p < 1e-6`) and **passed both exact PR `#35` integer gates** (`harm_passes = True`, `max-bet-v1` `wealth = 1.006521 >= 1.0`, `gate_certified = True`), whereas `tm_v1` fell just below the `max-bet-v1` threshold (`wealth = 0.921135 < 1.0`, `gate_certified = False`).
- However, post-run session-trace audit revealed a clear prompt-design confound on the head-to-head `tm_r6` vs `tm_v1` comparison: `12/16` Buckets A+B prompts explicitly hand-fed target method names (`"Modify CCR.stats"`, `"Inspect CCR ... specifically stats, gc_report, and migrate_legacy"`, `"Modify MultiCommand.format_commands"`), allowing `gpt-6-astra` to jump straight to `read_symbol("path::Class.method")` without ever reading the container class. On the `4/16` mechanism-exposed tasks (`T02`, `C01`, `C02`, `C03`) where container reads or `@overload` lookups occurred, `tm_r6` cut tokens **`-18.7%`** vs `tm_v1` (`25,684 -> 20,880` tokens), compared to `-1.5%` on the `12` method-named bypass tasks.

Rather than altering Round 1 (which remains frozen under `evidence/class-skeleton-r6-20261119/PROTOCOL.sha256`), this study pre-registers **Confirmation Round `k = 2`** under `brainspace/certification.py`'s exact sequential alpha-spending schedule (`round_alpha(alpha, k) = alpha * 6 / (pi^2 * k^2)`):
- **Round `k = 2` sequential budget**: $\alpha_2 = \text{round\_alpha}(0.05, 2) = 0.00759909$ (cumulative spending $\alpha_1 + \alpha_2 = 0.037995 < 0.05$).
- **Exact minimum sample size at `k = 2`**: `harm_minimum_samples(0.20, alpha_2) = 25` (`harm_limit(26, 0.20, alpha_2) = 0`) and `bet_minimum_samples(200_000, 1_000, alpha_2) = 9`. We therefore pre-register **`N = 26` paired tasks × `3` arms = `78` live sessions** (`13` `TokenMasterX` + `13` `Click`).
- **Mechanical Anti-Leakage Invariant (`forbidden_prompt_identifiers`)**: Every Bucket A (`D01..D05`, `K01..K05`) and Bucket B (`D06..D09`, `K06..K09`) oversized-class task specifies `forbidden_prompt_identifiers` listing all target method names, and `run.py self-test` mechanically enforces via word-boundary regex `\b<ident>\b` that **zero** target method names appear in `prompt`. Tasks describe the target class and behavioral contract naturally so the agent must discover the relevant methods on the container class.

## 2. Experimental Design (`N = 78` Live Sessions: `26` Tasks × `3` Arms)

### 2.1 Pinned Repositories (`C:\tm-lanes\repos`)
- **`tokenmasterx`** (`All-The-Vibes/TokenMasterX`): commit `dcd73c4aa32a85f0423a2a99adf9934b86b4a609` (`13` tasks: `D01..D13`)
- **`click`** (`pallets/click` `8.1.8`): commit `934813e4d421071a1b3db3973c02fe2721359a6e` (`13` tasks: `K01..K13`)

### 2.2 Three Matched Arms on GitHub Copilot CLI `1.0.112` (`gpt-6-astra`, `reasoning_effort = "low"`)
- **`stock`** (`l1`, true-off baseline): Stock Copilot CLI `1.0.112` (`copilot.exe -p ...`) with no `--lean` launcher, no `.token-master/` index or brief, no MCP servers, and no hooks.
- **`tm_v1`** (`l2`, TokenMaster `v1` truncated linear class-read baseline): Full TokenMaster stack (`brainspace_copilot_bridge.py --lean` + default R1 `sessionStart` `.token-master/brief.md` + `PostToolUse` view guard + `setup.py --host copilot --class-skeleton v1` + `TOKENMASTER_CLASS_SKELETON=v1`).
- **`tm_r6`** (`l3`, TokenMaster `r6` skeletal class projection + `@overload` resolution): Full TokenMaster stack (`brainspace_copilot_bridge.py --lean` + **byte-identical** R1 `sessionStart` `.token-master/brief.md` + `PostToolUse` view guard + `setup.py --host copilot --class-skeleton r6` + `TOKENMASTER_CLASS_SKELETON=r6`).

### 2.3 Task Stratification (`26` Paired Tasks: `10` Bucket A + `8` Bucket B + `8` Bucket C; `16` Trace + `10` Edit)
- **Bucket A — `A_oversized_class_trace` (`10` tasks: `D01..D05`, `K01..K05`)**: Naturalistic class-discovery and behavioral trace tasks on oversized classes (`> 2,400` numbered tokens: `CCR`, `RuntimeSession`, `Optimizer`, `NativeEventCollector` + `NativeRuntime`, `CertificationRegistry` + `ReadonlyGatewayHost`, `Context`, `BaseCommand` + `MultiCommand`, `Parameter` + `Option`, `OptionParser`, `CliRunner` + `ProgressBar`), with **zero** target method names in the prompt. Graded by exact JSON dictionary equality (`json_matches`) + clean worktree.
- **Bucket B — `B_oversized_class_edit` (`8` tasks: `D06..D09`, `K06..K09`)**: Naturalistic behavioral edits on oversized classes (`CCR`, `CertificationRegistry`, `NativeEventCollector`, `Optimizer`, `CliRunner`, `MultiCommand`, `Parameter`, `ProgressBar`) specified by class responsibility and return contract, with **zero** target method names in the prompt. Graded by clean allowed-path diff + behavioral `verify_code` + repository `pytest` suite (`pytest_targets`).
- **Bucket C — `C_small_symbol_control` (`8` tasks: `D10..D13`, `K10..K13`; `6` trace + `2` edit)**: Small-symbol negative controls (`<= 2,400` numbered tokens: `RuntimePolicy`, `NativeBridge`, `_solve_submodular_knapsack` + `bet_passes`, `HelpFormatter`, `ShellComplete` + `Choice`, `LazyFile` + `format_filename`), where `tm_v1` and `tm_r6` `read_symbol` outputs are byte-identical (`skel=False`).

## 3. Pre-Registered Hypotheses & Statistical Plan

All tests use fixed random seed `20261119`, `10,000` paired task-bootstrap resamples for 95% CIs, exact two-sided Wilcoxon signed-rank `p`-values, and **Holm-Bonferroni** family-wise error control ($\alpha = 0.05$) across `H1..H4`, plus the sequential Round `k = 2` ($\alpha_2 = \text{round\_alpha}(0.05, 2) = 0.00759909$) exact integer certification gate:

- **`H1` (Mechanism — Oversized-Class Tool-Result Tokens, Buckets A+B, $N = 18$)**: `tm_r6` reduces cumulative `tool_result_tokens` (and `read_symbol_tokens`) relative to `tm_v1` on naturalistic oversized-class tasks (`A_oversized_class_trace` + `B_oversized_class_edit`).
- **`H2` (Primary Head-to-Head — Oversized-Class Session `total_tokens`, Buckets A+B, $N = 18$)**: `tm_r6` reduces total session tokens (`total_tokens = input_tokens + output_tokens`) relative to `tm_v1` on naturalistic oversized-class tasks (`A+B`, $N = 18$).
- **`H3` (Pooled Head-to-Head — All-Task `total_tokens`, Buckets A+B+C, $N = 26$)**: Across all 26 tasks (`18` oversized-class + `8` small-symbol negative controls), `tm_r6` reduces `total_tokens` relative to `tm_v1` while maintaining non-inferior task pass rate (`pass_rate(tm_r6) >= pass_rate(tm_v1)` or paired harms `<= harm_limit(26, 0.20, alpha_2)`).
- **`H4` (End-to-End vs True-Off Stock + Sequential Round `k = 2` Gate, $N = 26$)**: Across all 26 tasks, `tm_r6` reduces `total_tokens` relative to `stock` and passes `brainspace/certification.py` at sequential Round `k = 2` (`harm_passes(26, harms, 0.20, round_alpha(0.05, 2))` AND `bet_passes(200_000, 1_000, round_alpha(0.05, 2), pairs)`).
