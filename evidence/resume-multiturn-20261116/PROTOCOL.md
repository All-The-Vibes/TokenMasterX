# Pre-Registered Protocol — Multi-Turn & Resumed-Session Routing Study (`resume-multiturn-20261116`)

## 1. Research Questions & Motivation

Single-turn evaluations (`md1-live-routing-20261115`, `PRS-6`) start every Copilot CLI launch with a fresh session (`-p ...`). Real developer workflows routinely span multiple resumed CLI launches via `--resume <session-id>` and `--continue`. In multi-turn `--lean` sessions, three coupled questions govern cost, capability recall, and observability:

1. **Prompt-cache preservation across resumed turns (PR #20 `recorded_tools`):** On a fresh `--lean` launch, the launcher selects `--excluded-tools`. Before PR #20, resuming with `--resume` or `--continue` re-ran `select_excluded_tools(command)` from scratch (and self-triggered `session_store_sql` whenever `--resume` / `--continue` appeared in argv), mutating the tool definitions sent at the front of the provider request and invalidating the cached prompt prefix on resumed turns. How much real cache-read retention and billed nano-AIU cost does `recorded_tools` save across 3-turn sessions compared with per-turn re-routing (`tm_reroute`) and unmodified stock CLI (`stock`)?
2. **Mid-session capability escalation without false cache breaks (`TOKENMASTER_RESUME_ESCALATE=1`):** Strict `recorded_tools` locking (`tm_locked`, default `--lean` path preserving `Routing.resume_same_list`) guarantees zero tool-list cache breaks on resumed turns, but withholds auxiliary tool families (`agents`, `background_shell`, `copilot_docs`, `sql`, `session_history`, `workflows`) if Turn 1 was plain coding and Turn 2 asks for a richer capability. Does opt-in monotonic escalation (`TOKENMASTER_RESUME_ESCALATE=1` + live `Microsoft-Decision-1`, `tm_escalate`) recover Turn-2 capability recall while (a) keeping Turn 3 cache-warm via monotonic intersection (`prev_excluded & new_excluded`) and `resume_keeps_history=False`, and (b) avoiding false-positive cache breaks on coding turns and adversarial lookalike prompts?
3. **Multi-turn `/tokenomics` attribution (`tokenomics.py`):** Prior to this study (`a7b4e42`), `tokenomics.estimate()` required `launch["start"] <= session_start <= launch["end"]`, classifying every resumed `--resume` / `--continue` TokenMaster launch as `stock` with zero credited savings. How accurately does session-ID-matched resumed attribution (plus warm-window cache-rewrite accounting when `--excluded-tools` changes mid-session) track ground-truth paired savings against `stock`?

## 2. Experimental Arms (4 Paired Conditions)

All four arms run against identical isolated repo trees (`git archive HEAD` at `a7b4e42`), identical model (`gpt-6-astra`), identical reasoning effort (`low`), identical CLI build (`GitHub Copilot CLI 1.0.112` under default GitHub routing with `--disable-builtin-mcps`), and neutral lane paths (`C:\tm-lanes\resume-multiturn-20261116\lanes\l1..l4`) to prevent path-length token bias:

| Arm | Lane | Launcher Configuration | Multi-Turn Tool-List Policy |
| --- | --- | --- | --- |
| `stock` | `l1` | Unmodified Copilot CLI `1.0.112` (no launcher, no `tokenmaster-nav`) | All 20 built-in tools on Turns 1, 2 (`--resume`), and 3 (`--continue`) |
| `tm_reroute` | `l2` | `brainspace_copilot_bridge.py --lean` + `tokenmaster-nav` + live MD-1 (`Decision-1`), prior `launches.jsonl` archived before Turns 2 & 3 | Pre-PR-#20 counterfactual: re-runs `select_excluded_tools(command)` from scratch on every turn |
| `tm_locked` | `l3` | `brainspace_copilot_bridge.py --lean` + `tokenmaster-nav` + live MD-1 (`Decision-1`), `TOKENMASTER_RESUME_ESCALATE` unset | Shipped default (`Routing.resume_same_list`): Turns 2 & 3 replay Turn 1's exact `recorded_tools(session)` |
| `tm_escalate` | `l4` | `brainspace_copilot_bridge.py --lean` + `tokenmaster-nav` + live MD-1 (`Decision-1`), `TOKENMASTER_RESUME_ESCALATE=1` | Monotonic escalation: Turns 2 & 3 use `recorded_tools(session) & select_excluded_tools(cmd, resume_keeps_history=False)` |

## 3. Stratified 3-Turn Workflow Matrix (`12 workflows × 4 arms = 48 sessions = 144 CLI launches`)

Every workflow executes **three sequential CLI launches** on the same lane and session:
- **Turn 1:** Fresh session (`copilot -p <turn_1_prompt> ...`), capturing `session_id` from `session-store.db`.
- **Turn 2:** Explicit resume (`copilot --resume <session_id> -p <turn_2_prompt> ...`).
- **Turn 3:** Implicit latest-session resume (`copilot --continue -p <turn_3_prompt> ...`).

The 12 workflows are stratified into three equal buckets (`4` workflows per bucket):

- **Bucket A (`A_stable_coding`, `M01`–`M04`):** Three-turn pure repository coding, editing, and unit-test workflows (`3` edit+test workflows: `M01` `v6_shaping.unfold_paths`, `M02` `exact_reuse.has_exact_reuse_marker`, `M04` `tokenomics --limit`; `1` cross-module audit synthesis: `M03`). Zero auxiliary tools are needed on any turn, and zero prompts match any `CAPABILITY_GROUPS` regex.
- **Bucket B (`B_mid_session_escalation`, `M05`–`M08`):** Turn 1 is pure repo inspection (`0` auxiliary tools needed); Turn 2 (`--resume`) escalates in natural language (`0` `CAPABILITY_GROUPS` regex matches) to a distinct auxiliary capability family (`M05`: `agents`, `M06`: `background_shell`, `M07`: `copilot_docs`, `M08`: `sql`); Turn 3 (`--continue`) synthesizes Turn 1 + Turn 2 results into a final verified JSON payload (`0` new auxiliary tools needed).
- **Bucket C (`C_adversarial_resume`, `M09`–`M12`):** Three-turn pure repo inspection and editing (`M09`–`M11` investigate, `M12` `tokenomics --min-calls` edit+test) where Turn 1 has clean phrasing and Turns 2 & 3 contain adversarial `CAPABILITY_GROUPS` regex trap phrases (`workflow`, `previous sessions`, `session-store.db`, `in the background`, `run a sql query`, `copilot cli settings`, `subagents`, `prior sessions`, `query with sql`) while needing zero auxiliary tools.

Within each workflow `M01`–`M12`, execution order of the four arms is counterbalanced by a deterministic Latin-square schedule seeded by `SHA256("resume-multiturn-20261116:" + task_id)` so cross-arm temporal provider drift and warm-cache ordering cancel across workflows.

## 4. Primary & Secondary Endpoints

### Primary Endpoints
1. **End-to-end 3-turn workflow pass rate & session continuity:** Deterministic grading after Turn 3 (`100%` exact JSON schema/value match + clean git working tree for `investigate`; allowed-file diff + assertion script + `pytest` pass for `edit`), plus exact session continuity (`Turn 1 session_id == Turn 2 session_id == Turn 3 session_id`).
2. **Total 3-turn raw tokens (`input_tokens + output_tokens`), Turn-1-cold-normalized nano-AIU (`cold_nano_aiu`), and billed nano-AIU (`billed_nano_aiu`):** Summed across all model calls (main-agent + subagent) of all 3 turns in `<COPILOT_HOME>/session-store.db` (`assistant_usage_events`). Note: `cold_nano_aiu` normalizes **only Turn 1's very first main-agent call** to cold cache (`cache_read -> cache_write`) to eliminate cross-session prefix-warmth noise while **preserving real intra-session cache hits and misses on Turn 2 (`--resume`) and Turn 3 (`--continue`) verbatim**.
3. **Resumed-turn prompt-cache hit rate (`Turns 2 + 3` first main-agent call `cache_read / (cache_read + cache_write)`):** Directly measures whether resuming preserved or invalidated the provider's cached prefix at each CLI launch boundary.
4. **Bucket B Turn-2 capability escalation recall & native target-tool usage:** Fraction of `M05`–`M08` workflows where Turn 2 (`--resume`) kept the required auxiliary capability family (`needed_recalled_t2`) and invoked the native target tools (`target_tool_used_t2`) without shell workarounds.
5. **Bucket A & C resumed false-escalation / cache-break rate:** Count of Turn 2 and Turn 3 launches in `M01`–`M04` and `M09`–`M12` that mutated `--excluded-tools` (`tool_list_changed_on_resume`).

### Secondary Endpoints
- **`/tokenomics` multi-turn accuracy:** Comparison of legacy `tokenomics.py` (`a7b4e42`, where resumed launches count as `stock`) vs updated `tokenomics.py` (session-ID resume matching + warm-window tool-mutation penalty) against ground-truth paired `stock - tm_locked` and `stock - tm_escalate` token and nano-AIU savings across all 12 workflows.
- **Regex-only escalation counterfactual on Bucket C:** Offline replay showing how many Bucket C resumed launches would have falsely mutated `--excluded-tools` under `TOKENMASTER_RESUME_ESCALATE=1` without MD-1's per-family veto.

## 5. Statistical Plan, Audit Gates & Guardrails

- **Paired inference:** 10,000-draw paired bootstrap 95% confidence intervals (`seed = 20261116`), exact paired Wilcoxon signed-rank two-sided p-values across workflows, and Holm-Bonferroni multiplicity adjustment across the primary pairwise comparisons (`tm_locked vs stock`, `tm_escalate vs stock`, `tm_locked vs tm_reroute`, `tm_escalate vs tm_reroute`, `tm_escalate vs tm_locked`).
- **Hard audit gates (`analyze.py`):**
  1. `PROTOCOL.sha256` matches `PROTOCOL.md` and `setup.json` (`prepared_at < first_workflow_started_at`).
  2. All `48` sessions (`144` turns) present, `copilot_version == "1.0.112"`, `recharged_nano_aiu == total_nano_aiu` within rounding (`<= 1,000` nano-AIU per call), and single `session_id` across all 3 turns of every workflow.
  3. Zero `md1-token.json` credential files remaining on disk after study completion.
- **Hard budget guardrail:** Cumulative billed spend across all live launches capped at `$25.00` (`25,000,000,000` nano-AIU); `CreditBudget` aborts before launching any turn if exceeded.
