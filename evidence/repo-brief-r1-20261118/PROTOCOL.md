# Pre-Registered Protocol: Submodular Knapsack & Marginal Graph-Coverage Brief Synthesis (`repo-brief-r1-20261118`)

## 1. Motivation & Algorithmic Hypothesis (`R1`)

PR `#36` (`evidence/repo-brief-20261117/`) demonstrated that Pillar 5's `<= 320`-token architectural & cross-session recall brief cut tokens vs stock by `-44.3%` and vs `tm_lean` by `-20.7%` overall (`-38.4%` on deep subsystem recall), while uncovering three structural failure modes of the sequential fixed-list `v1` synthesizer:

1. **Warm-recall role & module crowd-out**: `v1` emits `Recall:` (up to 5 lines), then `Hub:` (up to 10 lines, `MAX_HUBS_PER_FILE = 2`), and finally `Entry:` until `symbol_index._assemble(..., budget=320)` fills. Once multi-session `recall.jsonl` warms up, `Recall:` + multi-symbol hubs in the same file (`tokens.py` × 3 or `_compat.py` × 2) exhaust the 320-token budget, starving `Entry:` (`entrypoint_count = 0` on `TokenMasterX`) and wiping out secondary core hubs (`RequestPolicy`, `RuntimeSession`, `CCR`; `resolve_color_default`, `BadParameter`, `convert_type`).
2. **Unweighted hit-count & alphabetical recall truncation**: `v1` ranks `recall.jsonl` by unweighted `Counter` with alphabetical `(path, qualname)` tie-breaking (`MAX_RECALL = 5`). Stale earlier-session utility lookups (`parse_json`, `_vocabulary_path`, `strip_ansi`) crowd out active recent low-in-degree islands (`tokenomics.py::estimate`, `testing.py::CliRunner`).
3. **Path-prefix token waste**: `v1` repeats nested monorepo prefixes (`token-master-plugin/skills/token-master/...` = 8–9 BPE tokens/line; `src/click/...` = 2–3 BPE tokens/line) on every symbol line, wasting 25–30% of the 320-token cap on redundant path strings.

**Research Direction `R1` (`BRIEF_SCHEMA = 2`, `--brief-algorithm r1`)** replaces sequential fixed-list assembly with a **two-phase partition-matroid + cost-normalized monotone submodular knapsack solver** in `brainspace/repo_brief.py`:

- **Exact-integer discrete-concave monotone submodular objective $F(S)$** over directed call-graph and module-coverage atoms (`("sym", sid)`, saturating `("mod", path)` and `("dir", parent)`, directed `("in_file", f)` / `("out_file", f)` call-coverage atoms, `("hop", nid)` 1-hop neighborhood coverage, step-recency + low-in-degree island VoI `Recall:` weights, and cross-file out-degree `Entry:` orchestration weights).
- **Phase 1 interleaved partition-matroid floors** (`FLOOR_HUB = FLOOR_RECALL = FLOOR_ENTRY = 3`, `max_per_file = 1`) followed by **Phase 2a strict 1-anchor-per-module density greedy** ($\arg\max_e \Delta(e \mid S) / c(e)$ via exact cross-multiplication, zero floats) and **Phase 2b residual slack fill** (`max_per_file = 2`), all bounded at `<= 320` tokens under both `cl100k_base` and conservative fallback counters (`NavCap.assemble_le`).
- **Lossless collision-free `@root=<prefix>/` path folding** (`fold_brief_path` / `unfold_brief_path`), activated only when the factored solver strictly dominates the unfactored solver ($F(S_{\text{fold}}) > F(S_{\text{raw}})$), with 100% 1-step `SymbolIndex.read` suffix compatibility verified before emission.

Under the identical multi-session `recall.jsonl` and `320`-token cap:
- On **`TokenMasterX` (`204d388`)**: `v1` (`308t`) covers **5 distinct modules** (`0` entrypoints, `tokens.py` repeated 3×, `tokenomics.py::estimate` dropped), whereas `r1` (`304t`) covers **10 distinct modules** (`2.0×` module coverage in 4 fewer tokens, restoring `RequestPolicy`, `RuntimeSession`, `CCR`, `tokenomics.py::estimate`, and all 3 CLI entrypoints).
- On **`Click 8.1.8` (`934813e4`)**: `v1` (`290t`) covers **7 distinct modules** (`_compat.py` repeated 2×, `testing.py::CliRunner` dropped), whereas `r1` (`302t`) covers **11 of 16 core Click modules (`68.8%`)** (restoring `CliRunner`, `resolve_color_default`, `BadParameter`, and `convert_type`).

---

## 2. Experimental Design (`24 Tasks × 3 Arms = 72 Live Sessions`)

### 2.1 Three Matched Arms (Concurrent Per-Task Execution)

All 3 arms execute Copilot CLI `1.0.112` (`gpt-6-astra`, `reasoning_effort = low`) concurrently per task (`ThreadPoolExecutor(max_workers=3)`) in isolated `<COPILOT_HOME>` lanes (`l1`..`l3`) so provider latency and prompt-cache state are strictly matched:

| Arm ID | Configuration | `hooks.sessionStart` | `.token-master/brief.md` |
|---|---|---|---|
| `tm_lean` | TokenMaster MCP (`locate`, `outline`, `read_symbol`, `impact`) + `PostToolUse` + `--lean` launcher | Off (`--no-copilot-repo-brief`) | Not injected |
| `tm_v1_recall` | `tm_lean` + `brainspace_sessionstart.py` (`--copilot-repo-brief`) | Active (`source == "new"`) | Frozen PR `#36` `--brief-algorithm v1` brief (`<= 320` tok) from shared multi-session `recall.jsonl` |
| `tm_r1_recall` | `tm_lean` + `brainspace_sessionstart.py` (`--copilot-repo-brief`) | Active (`source == "new"`) | New `--brief-algorithm r1` submodular brief (`<= 320` tok) from the **exact identical** `recall.jsonl` |

**Strict Single-Variable Isolation (`tm_r1_recall` vs `tm_v1_recall`)**: Both brief arms share the exact same repository commit, `.token-master/symbols.db`, `.token-master/graph.json`, `.token-master/recall.jsonl`, `320`-token cap, `hooks.sessionStart` wrapper, MCP server, PostToolUse hook, and `--lean` bridge. Only the brief synthesis algorithm (`v1` vs `r1`) differs.

### 2.2 Two Pinned Repositories (Internal Monorepo + External Open-Source Library)

1. **`tokenmasterx`** (`All-The-Vibes/TokenMasterX` pinned at `204d388ba34765fa2a0f4ccebda08d6fe27c793e`) — nested plugin monorepo (`62` core skill code files, `141` aux repo code files, `134` test files).
2. **`click`** (`pallets/click` `8.1.8` pinned at `934813e4d421071a1b3db3973c02fe2721359a6e`) — external open-source Python CLI framework (`16` core `src/click` modules, `25` example modules, `29` test files).

### 2.3 Multi-Session `recall.jsonl` Construction (Zero Answer Leakage)

Prior to freezing `PROTOCOL.sha256`, each repository's multi-session `recall.jsonl` is generated deterministically via real `symbol_index.dispatch(idx, "read_symbol", ...)` + `repo_brief.record_recall(...)`:
- **Earlier session reads (`3` hits each)**: 4 frequently visited hub/utility helpers (`count_tokens`, `_vocabulary_path`, `RequestPolicy`, `parse_json` on `tokenmasterx`; `echo`, `Context`, `open_stream`, `strip_ansi` on `click`).
- **Recent active session reads (`2` hits each)**: 4 subsystem islands (`bet_passes`, `_copilot_output`, `validate_request`, `estimate` on `tokenmasterx`; `HelpFormatter`, `ProgressBar`, `OptionParser`, `CliRunner` on `click`).
- Because `brief.md` contains only symbol coordinates (`path::Symbol (start-end, ~Nt, ...)`), **zero task answers, defaults, constants, or behavioral semantics appear in either brief**.

### 2.4 Three Balanced Task Buckets (`8` Tasks Each = `24` Tasks; `16` Trace + `8` Code-Edit)

- **Bucket A (`A_warm_crowdout_recovery`, `n = 8`: `T01`–`T04`, `C01`–`C04`; `4` trace + `4` pytest-verified edits)**: Symptom- and behavior-driven tasks targeting CLI orchestrator entrypoints (`setup.py`, `brainspace_setup.py`, `brainspace_tools.py`) and secondary architectural hubs (`RequestPolicy`, `resolve_color_default`, `BadParameter`, `convert_type`) that `v1` crowds out under warm recall while `r1` preserves via partition floors + 1-anchor-per-module saturation.
- **Bucket B (`B_noisy_recall_filtering`, `n = 8`: `T05`–`T08`, `C05`–`C08`; `6` trace + `2` pytest-verified edits)**: Follow-up tasks in active recent subsystem islands (`tokenomics.py`, `CliRunner`) dropped by `v1`'s unweighted hit-count + alphabetical truncation, plus 2-hop cross-subsystem tasks connecting recent islands (`_copilot_output`, `validate_request`, `OptionParser`, `ProgressBar`) to secondary hubs (`RuntimeSession`, `CCR`, `BadParameter`, `resolve_color_default`).
- **Bucket C (`C_prefix_folding_and_direct_control`, `n = 8`: `T09`–`T12`, `C09`–`C12`; `6` trace + `2` pytest-verified edits)**:
  - `@root=` path-resolution stress edits (`T10`, `C10`) requiring `read_symbol` + `edit` + `pytest` on `@root`-folded modules (`brainspace/host_output.py`, `src/click/shell_completion.py`) to verify zero path-prefix confusion.
  - Non-brief leaf module tasks (`compressors/logs_compressor.py`, `hosts/config.py`, `decorators.py`, `termui.py`) and explicitly named non-brief direct controls (`token_ledger.py::CallRecord`, `Command.shell_complete`) to bound fixed overhead vs `tm_lean`.

---

## 3. Validity, Grading & Hygiene Controls

1. **Offline `self-test` before freeze**: `python run.py self-test` verifies on clean git checkouts that all `8` edit tasks fail verification before `reference_patch` and pass `verify_code` + `pytest` after `git apply`, that all `16` trace ground-truth JSON answers match live repository values, and that both `v1` and `r1` briefs satisfy `<= 320` tokens under both `cl100k_base` and fallback estimators with 100% 1-step `SymbolIndex.read` resolution on every emitted symbol line.
2. **Pre-run cache warmup**: 1 lightweight `"Reply with ONLY the word READY."` session per `(arm, repo)` (`6` warmups total) runs immediately before Task 1, recorded in `warmup.json` and excluded from `runs.jsonl`.
3. **Per-task clean tree & frozen `.token-master/` restore**: Before every task launch, each lane runs `git checkout -q -- . && git clean -fdq` and restores its frozen per-arm `.token-master/` template (`tm_cold` without `sessionStart` hook for `tm_lean`; `tm_v1_warm` for `tm_v1_recall`; `tm_r1_warm` for `tm_r1_recall`).

---

## 4. Pre-Registered Endpoints, Statistical Tests & Certification Gates

Per session $i$, harvested from `session-store.db` (`assistant_usage_events`) and `--output-format json`:
- `total_tokens = input_tokens + output_tokens`
- `billed_cost_usd = sum(total_nano_aiu) / 1e9`
- `cold_cost_usd` = `billed_cost_usd` with Call 1 main-agent `cache_read` repriced to `cache_write`
- `model_calls` = LLM turn count in `assistant_usage_events`
- `orientation_calls` = count of exploratory search/read calls (`rg`, `grep`, `glob`, `view`, `tokenmaster-nav-locate`, plus non-pytest shell search calls)
- `direct_symbol_calls` = count of targeted `tokenmaster-nav-read_symbol` + `tokenmaster-nav-impact` calls

### 4.1 Primary Hypothesis Family (Holm–Bonferroni $\alpha = 0.05$, 10,000-draw paired bootstrap 95% CI + exact two-sided Wilcoxon signed-rank)

- **`H1` (Overall Head-to-Head `tm_r1_recall` vs `tm_v1_recall`, $N = 24$ pairs)**: `tm_r1_recall` reduces `total_tokens` and `orientation_calls` vs frozen `tm_v1_recall` under the identical `recall.jsonl` and `320`-token cap without regressing task pass rate ($\Delta\text{pass} \ge 0$).
- **`H2` (Warm Crowd-Out Recovery on Bucket A, $n = 8$ pairs)**: `tm_r1_recall` reduces `total_tokens` and `orientation_calls` vs `tm_v1_recall` on entrypoint and secondary-hub tasks starved by `v1`.
- **`H3` (Noisy Multi-Session Recall Filtering on Bucket B, $n = 8$ pairs)**: `tm_r1_recall` reduces `total_tokens` and `orientation_calls` vs `tm_v1_recall` on active subsystem islands and cross-subsystem traces.
- **`H4` (Overall Net Value `tm_r1_recall` vs No-Brief `tm_lean`, $N = 24$ pairs)**: Across all 3 buckets (including Bucket C controls), `tm_r1_recall` achieves lower `total_tokens` and `billed_cost_usd` than `tm_lean` with zero `@root=` path-resolution failures on Bucket C edits.

### 4.2 Exact Integer Certification Gates (`brainspace/certification.py`, Maintainer PR `#35`)

In addition to paired Wilcoxon and bootstrap inference, `analyze.py` evaluates `brainspace/certification.py` at round $k = 1$, $\alpha = 0.05$ ($\alpha_1 = 6\alpha/\pi^2 \approx 0.030396$), `token_cap = 200_000`, `minimum_token_reduction = 1_000`:
- **Against true-off incumbent `tm_lean` ($N = 24$)**: `GateComparisonSpec(quality_margin=0.20, token_test="max-bet-v1")` exact binomial harm gate (`harm_passes(24, harms, 0.20, alpha_1)`, where `harm_limit = 0` requires zero tasks passed by `tm_lean` and failed by `tm_r1_recall`) + exact integer fixed-bet token gate (`bet_passes(200_000, 1_000, alpha_1, pairs)`).
- **Direct `tm_r1_recall` vs `tm_v1_recall` ($N = 24$)**: exact integer fixed-bet token gate (`bet_passes(200_000, 1_000, alpha_1, pairs)`) + observed `harms` count (`v1` pass & `r1` fail).

### 4.3 Promotion Decision Rule

Keep `--brief-algorithm r1` as `DEFAULT_ALGORITHM` iff `tm_r1_recall` maintains `>= tm_v1_recall` and `>= tm_lean` pass rates, achieves lower mean `total_tokens` and `billed_cost_usd` than both `tm_v1_recall` and `tm_lean` across $N = 24$, and introduces zero `@root=` path errors; otherwise revert `DEFAULT_ALGORITHM` to `"v1"` and preserve `"r1"` behind `--brief-algorithm r1`.
