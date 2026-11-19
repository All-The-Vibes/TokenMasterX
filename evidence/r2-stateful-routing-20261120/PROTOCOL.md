# Pre-Registered Protocol: Cache-Aware Stateful Local Routing & Pragmatic Deixis (`r2-stateful-routing-20261120`)

## 1. Motivation & Research Questions

Earlier TokenMaster studies established two competing constraints for `--lean` tool-surface routing on Copilot CLI `1.0.112`:

1. **Semantic recall requires beyond-regex classification (`md1-live-routing-20261115`, PRs `#32` & `#33`):** Static regexes miss indirect phrasing (`"spin up two helper workers"`, `"run an HTTP listener asynchronously"`, `"consult the CLI manual"`, `"create a temporary table"`). Cloud `Microsoft-Decision-1` (`MD-1`) recovered semantic recall (`96.6%–100%`), but requires an Azure AI Services endpoint + Entra bearer token and adds **`~653 ms` median** (`~765 ms` p90) network latency on every CLI launch.
2. **Mid-session escalation interacts with prompt-cache prefixes and intra-session anaphora (`resume-multiturn-20261116`, PR `#34`):**
   - Keeping `Routing.resume_same_list` strictly locked (`--resume-escalate off`) preserves warm prompt caches across `--resume` and `--continue`, but starves genuine Turn-2/Turn-3 capability shifts (`0%` mid-session escalation recall).
   - Stateless flat-`0.50` escalation (`--resume-escalate v1` + cloud `MD-1`) unlocks genuine mid-session shifts, **but suffers from two systematic failure modes**:
     1. **Pragmatic Deixis Confusion:** Natural intra-session back-references on resumed turns (*"Combine the exact values you recorded in Turn 1 and Turn 2..."*, *"from the previous turn's edit..."*) trigger `session_history` (`session_store_sql`), mutating `--excluded-tools` a second time and invalidating the newly warmed `25k–45k`-token conversation prefix.
     2. **Cache-Blind Flat Thresholding:** A flat `0.50` threshold treats Turn 1 (`0` cached session tokens) identically to a warm resumed launch (`30k+` cached tokens inside the 5-minute TTL), allowing borderline lexical lookalikes (`session cache`, `timeout`, `workflow`) to break warm prefixes when expected cache-rewrite loss exceeds expected miss risk.

**Research Direction R2** replaces both gaps with a self-contained local routing & decision-theoretic escalation stack (`brainspace/local_router.py` + `brainspace/local_router_weights.py`):

1. **Zero-Network Two-Scale Local Router (`--router r2`):** `24.2 KB` compressed (`3,360` active `int16` weights across all 7 capability families), combining global bag-of-ngrams + code-shape indicators (`backticks`, file paths, `snake_case`, `CamelCase`) with max-pooled per-clause scoring and exact Platt probability calibration. Runs in **`~0.31 ms` median** (`>2,000x` faster than cloud `MD-1`) with **zero network calls** and **zero cloud credentials**.
2. **Pragmatic Discourse Deixis Disambiguation (`apply_discourse_deixis`):** On resumed turns (`--resume` / `--continue`), distinguishes intra-session anaphora (*"Turn 1"*, *"first turn"*, *"previous turn"*, *"just recorded"*) from genuine cross-session memory queries (*"older chat"*, *"previous sessions"*, *"Monday"*, *"Tuesday's sync"*, *"past conversations"*, `session_store_sql`), suppressing false `session_history` escalations while preserving true cross-session recall even when both appear in the same sentence.
3. **2-Stage Warm-Cache Bayes Optimal Escalation (`--resume-escalate r2`):** Reads `<COPILOT_HOME>/session-store.db` (`assistant_usage_events`) within Copilot CLI's 5-minute `CACHE_WARM_WINDOW`, computes exact 2-stage cache-rewrite token exposure $\Delta W(s_t, f)$ (accounting for Copilot CLI `1.0.112`'s `<session_context>` split between Launch 2 and Launch 3+), and raises the escalation threshold to:
   $$\tau_f^*(s_t) = \max\!\left(\tau_0,\; \frac{L_{\text{break}}(s_t, f)}{L_{\text{break}}(s_t, f) + L_{\text{miss}}}\right)$$
   satisfying exact monotonicity (`warm_tokens_2 >= warm_tokens_1 => tau_2 >= tau_1`) and strict decay back to $\tau_0 = 0.50$ once the cache cools (`elapsed > 300s`).

---

## 2. Experimental Arms (4 Isolated Parallel Lanes)

All 4 arms run against identical git checkouts of `All-The-Vibes/TokenMasterX` at commit `a9275d8` (`HEAD`), pinned to **Copilot CLI `1.0.112`**, model **`gpt-6-astra`**, `reasoning_effort = low`, `--disable-builtin-mcps --allow-all-tools --no-ask-user --output-format json`. Every workflow runs 3 sequential CLI launches sharing one conversation:
- **Turn 1 (`start`):** `copilot -p "<T1>" ...`
- **Turn 2 (`resume`):** `copilot --resume <session_id> -p "<T2>" ...`
- **Turn 3 (`continue`):** `copilot --continue -p "<T3>" ...`

| Arm | CLI Invocation | Cloud MD-1 Endpoint | Routing & Resume Policy |
|---|---|---|---|
| `stock` | Stock `copilot` (`all` built-in tools) | None | Baseline stock Copilot CLI `1.0.112` (`0` tools excluded). |
| `tm_locked` | `brainspace_copilot_bridge.py --lean --router r2 --resume-escalate off -- copilot ...` | **Unset / Offline** | Zero-network R2 local router on Turn 1 + strict `Routing.resume_same_list` lock on Turns 2 & 3. |
| `tm_md1_v1` | `brainspace_copilot_bridge.py --lean --router md1 --resume-escalate v1 -- copilot ...` | Live Azure `Microsoft-Decision-1` (`https://raifoundry.services.ai.azure.com`) | PR `#34` cloud `MD-1` + stateless flat-`0.50` monotonic resume escalation. |
| `tm_r2` | `brainspace_copilot_bridge.py --lean --router r2 --resume-escalate r2 -- copilot ...` | **Unset / Offline** (`md1-token.json` absent) | **Full R2 candidate:** zero-network local router + pragmatic discourse deixis + 2-stage warm-cache Bayes threshold $\tau_f^*(s_t)$. |

---

## 3. Pre-Registered Workflow Suite (`16` 3-Turn Workflows = `64` Sessions = `192` CLI Launches)

All 48 prompts in `tasks.json` were verified prior to execution to have **zero exact matches** and **strictly `< 0.50` word-Jaccard similarity** against both the 566-prompt distillation corpus and all 73 `evals/md1_routing_eval.py` benchmark prompts. Local router weights (`WEIGHTS_SHA256 = 3e9c577ba4f7dae8...`) are frozen prior to `PROTOCOL.sha256`.

1. **Bucket A — `A_stable_coding` (`S01`–`S04`: 2 `edit` + 2 `investigate`, `0` aux tools needed on all 3 turns):**
   Pure repository inspection, multi-turn helper implementation, and Python verification (`v6_shaping.py`, `repo_brief.py`, `symbol_index.py`, `certification.py`, `native_transport.py`).
2. **Bucket B — `B_escalation_and_intra_deixis` (`S05`–`S08`: 4 workflows, Turn-2 indirect shift + Turn-3 intra-session anaphora):**
   - Turn 1: pure repository coding inspection (`needed_groups = []`).
   - Turn 2 (`--resume <sid>`): indirect semantic capability shift without regex trigger words:
     - `S05` (`agents`): *"Spin up two separate helper workers in parallel..."* (`task`)
     - `S06` (`background_shell`): *"Start a short-lived local Python HTTP listener asynchronously ... read its output ... shut the listener down..."* (`read_powershell`, `stop_powershell`)
     - `S07` (`copilot_docs`): *"Consult the built-in Copilot CLI reference manual..."* (`fetch_copilot_cli_documentation`)
     - `S08` (`sql`): *"Create a temporary table `tool_costs(name TEXT, weight INT)` in the built-in SQLite scratchpad database..."* (`sql`)
   - Turn 3 (`--continue`): natural intra-session anaphoric synthesis (*"Combine the exact values you recorded in Turn 1 and Turn 2..."*, *"what you found in the first turn and second turn..."*).
3. **Bucket C — `C_cross_session_recall` (`S09`–`S12`: 4 workflows with seeded March 2026 `session-store.db`):**
   - Each workflow seeds 4 prior March 2026 sessions in `<COPILOT_HOME>/session-store.db` (`sessions` + `turns` + FTS5 `search_index`) before Turn 1.
   - Turn 1 (& Turn 2 for `S09`, `S10`, `S12`) perform pure code reads (`needed_groups = []`), warming a multi-turn cache prefix.
   - The recall turn (`Turn 2` on `S11`; `Turn 3` on `S09`, `S10`, `S12`) asks a genuine cross-session memory question (*"older chat from Monday"*, *"previous sessions ... Tuesday's sync"*, *"past conversations"*, *"earlier sessions in `session_store_sql`"*) combined with Turn-1/Turn-2 values (forbidding shell reads of `.db` files).
   - Directly counter-tests `apply_discourse_deixis`: blanket suppression of `session_history` on resumed turns would fail Bucket C!
4. **Bucket D — `D_warm_cache_lookalikes` (`S13`–`S16`: 2 `edit` + 2 `investigate`, `0` aux tools needed on all 3 turns):**
   Multi-turn coding edits & inspections touching domain lookalikes (`session cache fields`, `prompt_cache_key`, `database tables`, `workflow-v1`, `timeout settings`, `CAPABILITY_GROUPS`, `run_dynamic_workflow`, `read_agent`) across warm Turn-2 and Turn-3 caches.

---

## 4. Pre-Registered Hypotheses, Statistical Tests & Formal Certification

### Primary & Co-Primary Inferential Hypotheses (Holm-Bonferroni adjusted at $\alpha = 0.05$, $N = 16$ paired workflows unless noted)

- **H1 (End-to-End Cost & Token Reduction vs Stock, $N = 16$):** `tm_r2` significantly reduces Turn-1 cold-normalized session cost (`cold_usd`) and total raw tokens (`raw_tokens = input_tokens + output_tokens`) relative to `stock` (two-sided exact Wilcoxon signed-rank test + 10,000-draw paired bootstrap 95% CI), while achieving non-inferior task pass rate.
- **H2 (Zero-Network Routing Latency Speedup vs Cloud MD-1, $N = 48$ paired launches):** `tm_r2` reduces per-launch launcher routing latency (`router_ms` recorded in `launches.jsonl`) by at least `10x` relative to `tm_md1_v1` with `0` cloud HTTP calls (paired exact Wilcoxon signed-rank across all 16 workflows' mean `router_ms`).
- **H3 (Mid-Session Escalation & Cross-Session Recall Recovery vs Strict Lock, $N = 8$, Buckets B + C):** `tm_r2` recovers mid-session capability recall (`needed_recalled` and native `target_tool_used` / task pass rate across `S05`–`S12`) where `tm_locked` is starved by `Routing.resume_same_list`.
- **H4 (Resumed-Turn Cache Stability & False-Escalation Suppression vs Stateless Cloud `tm_md1_v1`, $N = 16$):** Across non-escalating resumed turns (Bucket B Turn 3 intra-session anaphora + Buckets A & D Turns 2–3), `tm_r2` eliminates unnecessary mid-session tool-list mutations (`unneeded_tool_mutations`) and preserves higher resumed first-call prompt-cache hit rates / lower Turn-2+3 billed cost (`turn23_billed_usd`) than `tm_md1_v1`.

### Maintainer PR `#35` Exact Integer Proof-Backed Certification (`Gate.lean` + `Bet.lean`)

Using `brainspace/certification.py` (`GateComparisonSpec`):
- Incumbent: `stock-copilot-cli-1.0.112`
- Candidate: `tm-r2-local-stateful-v1`
- Sample size: $n = 16$ paired 3-turn workflows (`S01`–`S16`)
- Parameters: `alpha = 0.05`, `round_index = 1`, `quality_margin = 0.25` (exact binomial non-inferiority gate in `Gate.lean`; at $n = 16$, $0.75^{16} = 0.01002 \le \alpha_1/2 = 0.01520$), `token_test = "max-bet-v1"`, `token_cap = 500_000`, `minimum_token_reduction = 5_000`.
