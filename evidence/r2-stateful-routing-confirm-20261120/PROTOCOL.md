# Pre-Registered Confirmation Protocol (Round `k = 2`) — Zero-Network Local R2 Router, Symmetric Pragmatic Deixis & Warm-Cache Bayes Escalation (`r2-stateful-routing-confirm-20261120`)

## 1. Rationale, Sequential Alpha-Spending Budget, and Anti-Leakage Invariant

In **Round 1 (`evidence/r2-stateful-routing-20261120`, $k = 1$, $\alpha_1 = \text{round\_alpha}(0.05, 1) = 0.03039636$, $16$ workflows × $4$ arms = $64$ live sessions / $192$ Copilot CLI `1.0.112` launches)**:
- **`tm_r2` vs `stock` (H1):** Cut cold-normalized session cost **`-37.43%`** (`$0.2879` vs `$0.4600`, 95% CI `[-43.04%, -31.92%]`, Holm $p = 0.000122$) and raw tokens **`-50.44%`** (`68,006` vs `137,216`).
- **`tm_r2` vs `tm_md1_v1` latency (H2):** **`42.584 ms` median** (`57.099 ms` p90, including SQLite warm-cache lookup, `100%` offline) vs cloud `MD-1` **`960.323 ms` median** (`22.55x` faster, Holm $p = 0.000122$).
- **`tm_r2` vs `tm_locked` capability recall (H3):** Recalled **`7/8` (`87.5%`)** mid-session capability shifts vs **`0/8` (`0%`)** on `tm_locked` (`Holm p = 0.03125`), rescuing `S11` where both `tm_locked` and `tm_md1_v1` failed.
- **`tm_r2` vs `tm_md1_v1` warm-cache stability (H4):** **`0` unneeded mid-session tool-list mutations** across all 16 workflows vs **`6`** on `tm_md1_v1`, lifting resumed first-call prompt-cache hit rate from **`48.09%`** to **`58.84%`** (`49.38%` vs `17.23%` on Bucket B; Turn 2+3 billed USD **`-26.87%`**; raw Wilcoxon $p = 0.1167$ at $N = 16$ due to 8 ties).
- **Post-run trace diagnosis & Round 1 gate closure:** Formal Round 1 (`B = 500,000`, `N = 16`) closed as `not_certified` (`harm_count = 1` on `S12` vs `harm_limit = 0` at $N = 16$, and overly loose `B = 500,000` diluted `69,210` mean token savings below the $N = 16$ `max-bet-v1` threshold). Trace inspection identified three exact causes:
  1. **Asymmetric pragmatic deixis on `S12` Turn 3:** `apply_discourse_deixis` suppressed intra-session anaphora (`-6.0` nats) when no cross-session marker matched, but did not apply a symmetric positive logit shift when explicit cross-session markers (`"Query earlier sessions in session_store_sql..."`) appeared alongside a long JSON-schema tail, letting L2-normalized bag-of-n-grams dilute `p(session_history)` to `0.433 < tau* = 0.619`.
  2. **March 2026 seed timestamps in `S09`/`S10`:** Copilot CLI `1.0.112`'s `session_store_sql` instructs the model to query `substr(created_at, 1, 10) >= date('now', '-7 days')` first; static `2026-03-*` seed dates caused valid 7-day queries to return 0 rows on `S09`/`S10` across arms.
  3. **Oracle constant typo in `S04`:** `S04` hardcoded `"strict-gate-v1"` instead of `certification.STRICT_GATE == "strict-paired-hoeffding-v1"`, failing all 4 arms identically (`0/4`).

Round 1 remains frozen and unmodified under `evidence/r2-stateful-routing-20261120/PROTOCOL.sha256`. After implementing symmetric cross-session pragmatic deixis (`CROSS_SESSION_LOGIT_SHIFT = 3.0` with non-quoted literal guards in `brainspace/local_router.py`), freezing `local_router.py` (`0d31ba26701ed627008ec4afbea93880bb70eeb3046afc27ca52ea5999899159`) and `local_router_weights.py` (`7cbf4f71ab5d5616c7a29b225708d3e7db6134df3246095723960ab4752a94ec`), and programmatically generating 32 fresh 3-turn workflows (`C01`–`C32`, `max_jaccard = 0.533 < 0.55` against all 113 prior prompts in `CASES`, `HELD_OUT`, and `S01`–`S16`), this study pre-registers **Confirmation Round `k = 2`** in a shared `CertificationRegistry`:
- **Sequential error-spending budget (`brainspace/certification.py`):** $\alpha = 0.05$, Round $k = 1$ spent $\alpha_1 = 0.03039636$ (`not_certified`), and Round $k = 2$ receives $\alpha_2 = \text{round\_alpha}(0.05, 2) = 0.00759909$ (cumulative spending $\alpha_1 + \alpha_2 = 0.03799545 < 0.05$).
- **Exact Round `k = 2` sample size & gate parameters (`Gate.lean` + `Bet.lean`):** `N = 32` paired 3-turn workflows (`8` per bucket), `quality_margin = 0.25` (`harm_minimum_samples(0.25, alpha_2) = 19`, `harm_limit(32, 0.25, alpha_2) = 1`), `token_test = "max-bet-v1"`, `token_cap = 300,000`, `minimum_token_reduction = 2,500` (`bet_minimum_samples(300_000, 2_500, alpha_2) = 9`).

---

## 2. Experimental Design (`96` Live Sessions / `288` Launches: `32` Workflows × `3` Arms)

### 2.1 Three Competitive Matched Arms on GitHub Copilot CLI `1.0.112` (`gpt-6-astra`, `reasoning_effort = "low"`)
Because both PR `#34` (`evidence/resume-multiturn-20261116/`) and Round 1 (`evidence/r2-stateful-routing-20261120/`, `0/8` vs `7/8`, Holm $p = 0.03125$) already proved deterministic `--resume-escalate off` (`tm_locked`) cannot recover mid-session capability shifts, Confirmation Round 2 concentrates full $N = 32$ power across the three live competitive arms:
1. **`stock` (`l1`, true-off incumbent):** Unmodified GitHub Copilot CLI `1.0.112` across Turn 1 (`start`), Turn 2 (`--resume <sid>`), and Turn 3 (`--continue`), with all built-in tools active and zero TokenMaster hooks, briefs, or MCP servers.
2. **`tm_md1_v1` (`l2`, cloud `MD-1` + stateless flat-`0.50` escalation baseline):** Full TokenMaster stack (`--lean --router md1 --resume-escalate v1`) calling live Azure Foundry `Microsoft-Decision-1` over HTTPS on every launch and escalating any capability family with `score >= 0.50`.
3. **`tm_r2` (`l3`, zero-network local R2 + symmetric pragmatic deixis + warm-cache Bayes `tau*` candidate):** Byte-identical TokenMaster workspace and `.token-master/brief.md` (`--lean --router r2 --resume-escalate r2`), running `100%` offline (`TOKENMASTER_MD1_ENDPOINT` unset and `md1-token.json` absent, enforced at runtime).

### 2.2 Four Balanced 3-Turn Workflow Buckets (`C01`–`C32`, `8` Workflows per Bucket)
Every workflow runs `Turn 1 (start)` → `Turn 2 (--resume <sid>)` → `Turn 3 (--continue)` in an isolated git worktree and isolated `COPILOT_HOME` (`C:\tm-lanes\r2-stateful-routing-confirm-20261120`):
- **Bucket A — `A_stable_coding` (`C01`–`C08`: `4` read-only trace + `4` bounded code-edit):** Pure repository inspection and pure-helper code edits requiring zero auxiliary capability families across all 3 turns (`needed_groups = []`).
- **Bucket B — `B_escalation_and_intra_deixis` (`C09`–`C16`):** Turn 1 pure coding (`[]`), Turn 2 genuine mid-session capability shift (`2` `agents`, `3` `sql`, `2` `background_shell`, `1` `copilot_docs`), and Turn 3 intra-session anaphora synthesis (`"during Turn 1 and Turn 2"`, `"first turn and second turn"`, `"earlier in this session"`, `needed_groups = []`).
- **Bucket C — `C_cross_session_recall` (`C17`–`C24`):** `8` seeded prior sessions dynamically stamped `18h..96h` before `now` (strictly inside `session_store_sql`'s 7-day SQL window AND strictly `>= 18h` older than Turn 1's newly created session so `--continue` resolves deterministically). `C17`–`C20` escalate `session_history` on Turn 2 followed by intra-session Turn 3 synthesis; `C21`–`C24` perform 2-turn code reads followed by Turn 3 cross-session recall with explicit multi-key JSON output schemas.
- **Bucket D — `D_warm_cache_lookalikes` (`C25`–`C32`: `4` trace + `4` edit):** Multi-turn coding workflows whose Turn 2 & Turn 3 prompts contain dense domain-vocabulary lookalikes (`workflow`, `agent`, `background`, `sql`, quoted `'session_store_sql'`, `'session_history'`, `'workflow_v1'`, `'background_worker_v0'`) plus intra-session anaphora (`"from the previous turn"`, `"Turn 2's function"`, `"earlier in this session"`), where zero auxiliary capabilities are needed (`needed_groups = []`).

### 2.3 Deterministic Programmatic Oracle (`r2-deterministic-oracle-v1`)
All expected constants in `tasks.json` were computed programmatically by importing the target Python modules at `HEAD`, and all 8 `edit` workflows (`C05`–`C08`, `C29`–`C32`) are verified by `run.py self-test` to fail before `reference_patch` and pass cleanly after `git apply` touching only `allowed_paths`. Every workflow requires `session_continuity_ok == True` (`len(session_ids) == 1` across all 3 turns).

---

## 3. Pre-Registered Hypotheses & Formal Certification Plan

All frequentist comparisons use fixed random seed `20261121`, `10,000` paired workflow-bootstrap resamples for 95% CIs, exact two-sided Wilcoxon signed-rank `p`-values, and **Holm-Bonferroni** family-wise error control ($\alpha = 0.05$) across `H1`–`H4`:

1. **`H1` (`tm_r2` vs `stock` cold-normalized session USD, $N = 32$):** `tm_r2` reduces cold-normalized 3-turn session cost (`cold_usd`) relative to `stock`.
2. **`H2` (`tm_r2` vs `tm_md1_v1` live launcher routing latency, $N = 32$ workflows / $96$ launches per arm):** Zero-network `tm_r2` reduces per-workflow mean launcher routing latency (`mean_router_ms`, including SQLite warm-cache lookup) relative to cloud `MD-1` (`tm_md1_v1`).
3. **`H3` (`tm_r2` vs `tm_md1_v1` warm-cache preservation, $N = 32$):** Symmetric pragmatic deixis + warm-cache Bayes escalation (`tm_r2`) increases resumed first-call prompt-cache hit rate (`mean_resume_first_call_cache_hit_rate` across Turns 2 & 3) relative to stateless flat-`0.50` cloud `MD-1` (`tm_md1_v1`) by eliminating false mid-session tool-list mutations.
4. **`H4` (`tm_r2` vs `tm_md1_v1` resumed Turn 2+3 billed USD, $N = 32$):** `tm_r2` reduces cumulative resumed-turn billed cost (`turn23_billed_usd`) relative to `tm_md1_v1`.

### Shared Two-Round Proof-Backed Certification (`Gate.lean` + `Bet.lean`)
`analyze.py` instantiates a single durable SQLite `CertificationRegistry` (`alpha = 0.05`, `trusted_oracle_id = "r2-deterministic-oracle-v1"`, `gate = "margin-250000ppm-max-bet-v1"`):
1. Permanently excludes all search/distillation prompts (`CASES` and `HELD_OUT` in `md1_routing_eval.py`) via `exclude_tasks`.
2. Replays Round `k = 1` (`S01`–`S16`, `n = 16`, `token_cap = 500,000`, `minimum_token_reduction = 5,000`, `quality_margin = 0.25`) from `../r2-stateful-routing-20261120/runs.jsonl`, consuming $\alpha_1 = 0.03039636$ (`decision == "not_certified"`).
3. Submits and certifies Confirmation Round `k = 2` (`C01`–`C32`, `n = 32`, `token_cap = 300,000`, `minimum_token_reduction = 2,500`, `quality_margin = 0.25`, `token_test = "max-bet-v1"`) at $\alpha_2 = 0.00759909$, requiring both `harm_passes(32, harms, 0.25, alpha_2)` (`harms <= 1`) and `bet_passes(300_000, 2_500, alpha_2, pairs)` (`wealth >= 1.0`), plus idempotent replay verification (`reg.certify(2, spec_r2)`).
