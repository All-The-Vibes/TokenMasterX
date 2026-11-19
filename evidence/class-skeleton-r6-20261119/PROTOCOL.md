# Pre-Registered Protocol — R6 Skeletal Class Projection vs Truncated Linear Reads (`class-skeleton-r6-20261119`)

## 1. Objective & Research Question

Evaluate **Research Direction R6**: replacing truncated linear prefix dumps on oversized container symbols (`class`, `trait`, `mod` exceeding the 2,400-token `read_symbol` cap) and resolving `@overload` dead-ends in `SymbolIndex.read` (`token-master-plugin/skills/token-master/brainspace/symbol_index.py`), while preserving the Lean 4 `NavCap.assemble_le` whole-output `<= 2,400`-token guarantee (`SCHEMA_VERSION = 5`, `TOOL_SPECS` `nav = 257` unchanged).

Specifically, when an agent calls `read_symbol` on an oversized container (`tokens_of(numbered_body) > 2,400`) or an `@overload`ed method:

1. **Baseline `v1` (`--class-skeleton v1`)**:
   - Emits a linear line-numbered prefix truncated near `2,359–2,400` tokens (typically consumed by class docstrings and partial `__init__`), followed by bare `start-end kind name` member spans without parameter types, return annotations, class attributes, `self.*` state fields, or call-graph edges.
   - Rejects `@overload`ed methods (e.g., `Context.invoke`, `Context.lookup_default`, `BaseCommand.main`, `Parameter.get_default`, `Option.get_default`) with `"matches N symbols; read one of: path::Class.method (s-e) ..."`—suggesting the exact ambiguous string that fails again.
2. **Treatment `r6` (`--class-skeleton r6`, default)**:
   - Renders a compact **container skeleton** assembled via `_assemble(..., BUDGET)` (`369–2,113` tokens across all oversized classes in `TokenMasterX` and `Click 8.1.8`, unconditionally `<= 2,400` tokens under `NavCap.assemble_le`): declaration header + 2-line docstring summary, class-level attributes (`Attrs:`), deduplicated `self.*` state assignments (`State (__init__ ...):`), and every member's single-line clean AST signature (multi-line signatures collapsed, `@overload` clusters deduplicated to `@overload (+k) def ...`), `~tokens`, and top outgoing call edges (`-> self.foo, helper`), with actionable `read_symbol path::Class.<member>` drill-down guidance.
   - Resolves contiguous same-`(path, qualname)` definitions (`@overload` stubs + implementation) in 1 step, and prints actionable `path:start-end` targets for genuinely non-contiguous duplicate definitions.
   - Leaves all callables (`function`, `method`) and all small containers (`<= 2,400` numbered tokens) **byte-identical** to `v1`.

## 2. Experimental Design (`N = 72` Live Sessions)

### 2.1 Pinned Repositories (`C:\tm-lanes\repos`)
- **`tokenmasterx`** (`All-The-Vibes/TokenMasterX`): commit `dcd73c4aa32a85f0423a2a99adf9934b86b4a609` (`12` tasks: `T01..T12`)
- **`click`** (`pallets/click` `8.1.8`): commit `934813e4d421071a1b3db3973c02fe2721359a6e` (`12` tasks: `C01..C12`)

### 2.2 Three Matched Arms on GitHub Copilot CLI `1.0.112` (`gpt-6-astra`, `reasoning_effort = "low"`)
- **`stock`** (`l1`, true-off baseline): Stock Copilot CLI `1.0.112` (`copilot.exe -p ...`) with no `--lean` launcher, no `.token-master/` index or brief, no MCP servers, and no `PostToolUse` / `sessionStart` hooks.
- **`tm_v1`** (`l2`, TokenMaster `v1` class-read baseline): Full TokenMaster stack (`brainspace_copilot_bridge.py --lean` + default R1 `sessionStart` `.token-master/brief.md` + `PostToolUse` view guard + `setup.py --host copilot --class-skeleton v1` + `TOKENMASTER_CLASS_SKELETON=v1`).
- **`tm_r6`** (`l3`, TokenMaster `r6` skeletal class projection): Full TokenMaster stack (`brainspace_copilot_bridge.py --lean` + **byte-identical** R1 `sessionStart` `.token-master/brief.md` + `PostToolUse` view guard + `setup.py --host copilot --class-skeleton r6` + `TOKENMASTER_CLASS_SKELETON=r6`).

**Zero Prompt-Prefix Confound Between `tm_v1` and `tm_r6`**: Both `tm_v1` and `tm_r6` share the exact same `--lean` CLI flags, tool schemas (`nav = 257` tokens), `.token-master/brief.md` (`sha256` verified identical), `.token-master/symbols.sqlite`, and `.token-master/graph.json`. Only the `read_symbol` behavior of `navigation_mcp.py` (`v1` vs `r6`) differs.

All 3 arms for a given task run concurrently across isolated `USERPROFILE` / `COPILOT_HOME` lanes (`l1`, `l2`, `l3`) with identical task prompts and clean `git checkout` / `git clean` worktrees before and after every session.

### 2.3 Task Stratification (`24` Paired Tasks = `8` per Bucket, `14` Trace + `10` Edit)
- **Bucket A — `A_oversized_class_trace` (`8` tasks: `T01..T04`, `C01..C04`)**: Read-only multi-method, attribute, state, and `@overload` trace tasks on oversized classes (`> 2,400` numbered tokens: `CCR`, `RuntimeSession`, `CertificationRegistry`, `HeadroomContainer`, `NativeRuntime`, `Context`, `BaseCommand`, `MultiCommand`, `Parameter`, `Option`, `CliRunner`, `ProgressBar`), graded by exact JSON dictionary equality (`json_matches`) + clean worktree.
- **Bucket B — `B_oversized_class_edit` (`8` tasks: `T05..T08`, `C05..C08`)**: Surgical behavioral feature/bugfix edits inside oversized classes (`CCR.stats`, `CertificationRegistry.budget`, `NativeRuntime.http_summary`, `Optimizer.status`, `CliRunner.make_env`, `MultiCommand.format_commands`, `Parameter.get_error_hint`, `ProgressBar.format_pct`), graded by clean allowed-path diff + behavioral `verify_code` + repository `pytest` suite (`pytest_targets`).
- **Bucket C — `C_small_symbol_control` (`8` tasks: `T09..T12`, `C09..C12`; `6` trace + `2` edit)**: Negative-control tasks targeting classes and functions `<= 2,400` numbered tokens (`RuntimePolicy`, `NativeBridge`, `_solve_submodular_knapsack`, `bet_passes`, `HelpFormatter`, `ShellComplete`, `Choice`, `LazyFile`, `format_filename`), where `tm_v1` and `tm_r6` `read_symbol` outputs are byte-identical (`skel=False`).

## 3. Pre-Registered Hypotheses & Statistical Plan

All tests use fixed random seed `20261119`, `10,000` paired task-bootstrap resamples for 95% confidence intervals, exact two-sided Wilcoxon signed-rank `p`-values, and **Holm-Bonferroni** family-wise error control ($\alpha = 0.05$) across the four primary/co-primary hypotheses `H1..H4`:

- **`H1` (Mechanism — Oversized-Class Tool Payload Tokens, Buckets A+B, $N = 16$)**: `tm_r6` reduces cumulative `tool_result_tokens` (and `read_symbol_tokens`) relative to `tm_v1` on oversized-class tasks (`A_oversized_class_trace` + `B_oversized_class_edit`).
- **`H2` (Primary Head-to-Head — Oversized-Class Session `total_tokens`, Buckets A+B, $N = 16$)**: `tm_r6` reduces total session tokens (`total_tokens = input_tokens + output_tokens`) relative to `tm_v1` on oversized-class tasks (`A+B`, $N = 16$).
- **`H3` (Pooled Head-to-Head — All-Task `total_tokens`, Buckets A+B+C, $N = 24$)**: Across all 24 tasks (`16` oversized-class + `8` small-symbol negative controls), `tm_r6` reduces `total_tokens` relative to `tm_v1` while maintaining non-inferior task pass rate (`pass_rate(tm_r6) >= pass_rate(tm_v1)` or paired harms within `harm_limit(24, 0.20, alpha_round)`).
- **`H4` (End-to-End vs True-Off Stock — `tm_r6` vs `stock` `total_tokens`, $N = 24$)**: Across all 24 tasks, `tm_r6` reduces `total_tokens` relative to `stock` and passes the exact PR `#35` integer certification gate (`brainspace/certification.py`: `harm_passes(24, harms, 0.20, round_alpha(0.05, 1))` AND `bet_passes(200_000, 1_000, round_alpha(0.05, 1), pairs)`).

### Secondary & Diagnostic Checks (Reported Without Multiplicity Hiding)
- Bucket-by-bucket (`A`, `B`, `C`) and repository-by-repository (`tokenmasterx`, `click`) paired comparisons on `total_tokens`, `uncached_input_tokens`, `billed_cost_usd`, `cold_cost_usd`, `model_calls`, `read_symbol_calls`, `read_symbol_tokens`, `tool_result_tokens`, `class_skeleton_hits`, `truncated_read_hits`, and `ambiguous_read_hits`.
- Verification on Bucket C (`C_small_symbol_control`, $N = 8$) that `tm_r6` preserves small-symbol parity (`0` regressions on small-symbol reads).
- Pre-flight `run.py self-test` verifying live MCP stdio `v1` vs `r6` behavior, byte-identical Bucket C symbol outputs, zero answer leakage in `.token-master/brief.md`, and all 10 `reference_patch` + `pytest` edit checks before freezing `PROTOCOL.sha256`.
