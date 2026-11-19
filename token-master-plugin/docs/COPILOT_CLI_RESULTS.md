# Copilot CLI results (October 18 to November 19, 2026)

These runs used GitHub Copilot CLI and GitHub's Copilot API:

- **Two sequential pre-registered 3-arm R6 skeletal class projection studies on Copilot CLI `1.0.112` (November 19,
  2026):** 150 sessions across Round 1 ($k = 1$, $\alpha_1 = 0.0304$, `24` paired tasks × `3` arms = `72` sessions,
  `evidence/class-skeleton-r6-20261119/`) and Confirmation Round 2 ($k = 2$, $\alpha_2 = 0.0076$, `26` paired tasks × `3`
  arms = `78` sessions with mechanical `forbidden_prompt_identifiers` anti-leakage enforcement,
  `evidence/class-skeleton-r6-discovery-20261119/`), comparing stock Copilot CLI (`stock`), TokenMaster `--lean` + R1
  repo brief + legacy linear-truncating `read_symbol` (`tm_v1`, `--class-skeleton v1`), and TokenMaster `--lean` + R1
  repo brief + skeletal class projection & `@overload` 1-step resolution (`tm_r6`, `--class-skeleton r6`) under default
  GitHub routing across this repository (`dcd73c4a`) and `pallets/click` `8.1.8` (`934813e4`) (`gpt-6-astra`, reasoning
  `low`). Both protocols were hashed before any session.

- **Pre-registered 3-arm R1 submodular repo-brief & recall synthesis study on Copilot CLI `1.0.112` (November 18,
  2026):** 72 sessions (`24` paired tasks × `3` arms: `tm_lean`, `tm_v1_recall` using PR-#36 fixed-slot
  `--brief-algorithm v1`, and `tm_r1_recall` using submodular marginal graph-coverage `--brief-algorithm r1`, both
  synthesized from the exact identical multi-session `recall.jsonl` and `<= 320`-token cap) under default GitHub
  routing across this repository (`204d388b`) and `pallets/click` `8.1.8` (`934813e4`) (`gpt-6-astra`, reasoning `low`,
  16 trace + 8 edit tasks stratified into 8 warm crowd-out recovery, 8 noisy multi-session recall filtering, and 8
  `@root=`-folding + direct-symbol controls). The protocol was hashed before any session
  (`evidence/repo-brief-r1-20261118/`).
- **Pre-registered 4-arm Pillar 5 repo-brief & cross-session recall study on Copilot CLI `1.0.112` (November 17, 2026):**
  96 sessions (`24` paired tasks × `4` arms: `stock`, `tm_lean`, `tm_brief` with cold `.token-master/brief.md`, and
  `tm_recall` with prior-session `Recall:` targets refreshed via `setup.py --refresh-brief`) under default GitHub
  routing across this repository (`f4228f7e`) and `pallets/click` `8.1.8` (`934813e4`) (`gpt-6-astra`, reasoning `low`,
  16 trace + 8 edit tasks stratified into 8 cold architecture, 8 cross-session recall, and 8 direct-symbol controls).
  The protocol was hashed before any session (`evidence/repo-brief-20261117/`).
- **Pre-registered 4-arm multi-turn & resumed-session study on Copilot CLI `1.0.112` (November 16, 2026):** 48 sessions
  (`144` CLI launches: Turn 1 start → Turn 2 `--resume <id>` → Turn 3 `--continue`, `410` API calls) under default
  GitHub routing on this repository (`gpt-6-astra`, reasoning `low`), comparing stock Copilot CLI, pre-PR-#20 per-turn
  resume re-routing (`tm_reroute`), shipped resume tool-list locking (`tm_locked`), and opt-in monotonic resume
  escalation (`tm_escalate`, `TOKENMASTER_RESUME_ESCALATE=1`) across 12 frozen 3-turn workflows (4 stable coding, 4
  mid-session capability escalation, 4 adversarial resume lookalikes). The protocol was hashed before any session
  (`evidence/resume-multiturn-20261116/`).
- **Pre-registered 3-arm MD-1 live routing study on Copilot CLI `1.0.112` (November 15, 2026):** 45 sessions under
  default GitHub routing on this repository (`gpt-6-astra`, reasoning `low`), comparing stock Copilot CLI, `--lean`
  with regex rules only (`tm_regex`), and `--lean` with live Microsoft-Decision-1 routing (`tm_md1`) across 15 frozen
  tasks (5 pure coding, 5 indirect multi-capability phrasings, 5 lookalike coding prompts). The protocol was hashed
  before any session (`evidence/md1-live-routing-20261115/`).
- **Default setup and `--lean` on Copilot CLI `1.0.105` (November 1, 2026):** two runs under default GitHub routing on
  the same day, build, tasks and model, each with its own stock arm: TokenMaster as the launcher starts it by default
  (no `--lean`, every built-in tool kept), and with `--lean`. Django D01-D15 with `gpt-6-astra`, 30 sessions each;
  each protocol was frozen and hashed before its sessions
  ([Default setup and `--lean`](#default-setup-and---lean-on-copilot-cli-10105-november-1-2026)). The README hero
  quotes these runs.
- **Default GitHub routing on Copilot CLI `1.0.104` (October 27, 2026):** the first run without the evaluation
  relay. Copilot CLI signed in and routed every request itself, and its own per-call records gave the tokens and
  GitHub's charges. Django D01–D15 with `gpt-6-astra`, 30 sessions; the protocol was committed before the sessions
  ([Default GitHub routing](#default-github-routing-on-copilot-cli-10104-october-27-2026)). A relay control on the
  same client build, account and day followed it.
- **Pre-registered study PRS-6 on Copilot CLI `1.0.98` (October 26, 2026):** pre-registered before
  any study call ([PRS6_PROTOCOL.md](PRS6_PROTOCOL.md), commit `19443fc`, evidence in
  `evidence/prs6-copilot-1.0.98-20261026/analysis.json`). Pinning `COPILOT_CLI_DIST_DIR` to `1.0.98`
  and removing `--no-auto-update` ran Copilot CLI `1.0.98`, verified in 176 of 176 session
  captures (`Version number: 1.0.98`, 0 recount mismatches, `total_nano_aiu` matching calculated USD
  to `$0.0001`).
- **Exploratory runs on Copilot CLI `1.0.78-3` (October 18–22, 2026):** used Copilot CLI `1.0.78-3`,
  the bundled build of the WinGet launcher, not the installed `1.0.98` that this page named until
  October 23, 2026 ([Copilot CLI version](#copilot-cli-version)). Those runs had no pre-registered
  protocol.
- **Earlier replica studies (PRS-1 to PRS-4):** used a Copilot-CLI-shaped harness instead, with a
  fixed prompt of about 3,600 tokens ([PRS4_RESULTS.md](PRS4_RESULTS.md)).

## Summary

### Pre-registered 3-arm R6 skeletal class projection studies — Round 1 & Confirmation Round 2 (Copilot CLI `1.0.112`, November 19, 2026)

- **150 live sessions across two sequential pre-registered rounds (`150/150` passed, `0` harms across all arms;
  `gpt-6-astra`, default GitHub routing, identical R1 `brief.md` and `±0.3–0.8`-token Call-1 prompt parity between `tm_v1`
  and `tm_r6` across this repository `@ dcd73c4a` and `pallets/click` `8.1.8 @ 934813e4`):**
  - **Round 1 ($k = 1$, $\alpha_1 = 0.03039636$, `24` paired tasks × `3` arms = `72` sessions,
    `evidence/class-skeleton-r6-20261119/`):** all three arms passed **24/24** (`72/72`). Pooled (`N = 24`), `tm_r6` cut
    raw tokens **`−56.3%` vs `stock`** (`71,324 → 31,137`, 95% CI `−62.6%` to `−50.4%`, `24W/0T/0L`, Holm $p < 10^{-6}$)
    and passed **both** PR `#35` exact integer certification gates against `stock` (`harm_passes = True`, `max-bet-v1`
    wealth **`1.006521 >= 1.0`**, `gate_certified = True`), whereas `tm_v1` (`32,110` mean tokens) fell short on
    `max-bet-v1` (`wealth = 0.921135 < 1.0`, `gate_certified = False`). Head-to-head `tm_r6` vs `tm_v1` was `−4.6%` on
    oversized classes (`35,472 → 33,836`, $p = 0.464$) and `−3.0%` pooled ($p = 0.708$) because `12/16` Round 1 prompts
    explicitly named target methods (`Class.method`), letting `gpt-6-astra` jump straight to `read_symbol("path::Class.method")`
    without reading the container class; on the `4/16` mechanism-exposed tasks (`T02`, `C01`, `C02`, `C03`), `tm_r6` cut
    raw tokens **`−18.7%` vs `tm_v1`** (`25,684 → 20,880`) vs **`−1.5%`** (`38,735 → 38,155`) on bypassed tasks.
  - **Confirmation Round 2 ($k = 2$, $\alpha_2 = 0.00759909$, cumulative $\alpha_1 + \alpha_2 = 0.0380 < 0.05$, `26`
    paired tasks × `3` arms = `78` sessions, `evidence/class-skeleton-r6-discovery-20261119/`):** mechanical word-boundary
    `forbidden_prompt_identifiers` guards verified `0` target-method names in all `18` oversized-class prompts (`10`
    `Bucket A` naturalistic class-discovery traces, `8` `Bucket B` behavioral edits, `8` `Bucket C` small-symbol negative
    controls), raising container-skeleton / `@overload` exposure from `25%` (`4/16`) to **`83.3%` (`15/18`; `13/18`
    direct class skeletons)**. All three arms passed **26/26** (`78/78`).
  - **Pre-registered Round 2 hypotheses (`H1..H4`, Holm-Bonferroni adjusted) & cost decomposition:**
    - **`H1` (`N = 18` oversized `tool_result_tokens`, `tm_r6` vs `tm_v1`) passed Holm significance:** `3,559 → 2,385`
      (**`−33.0%`**, 95% CI `−42.0%` to `−20.2%`, `15W/0T/3L`, raw Wilcoxon $p = 0.001579$, **Holm $p = 0.004737$**);
      `read_symbol` payload tokens fell **`−39.8%`** (`3,240 → 1,950`, `16W/1T/1L`, $p = 0.000381$; `−33.5%` pooled
      across `N = 26`, `17W/8T/1L`, $p = 0.000252$), eliminating truncated linear reads (`0.94 → 0.00` per task) and
      duplicate-name ambiguity errors (`0.06 → 0.00`).
    - **`H4` (`N = 26` pooled `total_tokens`, `tm_r6` vs `stock`) passed Holm significance:** `73,428 → 38,219`
      (**`−48.0%`**, 95% CI `−52.8%` to `−43.0%`, `25W/0T/1L`, **Holm $p < 10^{-6}$**), with `harm_passes = True` (`0`
      harms vs limit `<= 0` at $\alpha_2$).
    - **Naturalistic class-discovery (`Bucket A`, `N = 10`) billed cost vs raw cached-prefix tokens:** on `Bucket A`,
      `tm_r6` cut `read_symbol` tokens **`−43.6%`** (`4,374 → 2,468`, `10W/0T/0L`, exact Wilcoxon $p = 0.001953$), cut
      **as-run billed USD cost on `10/10` (`100%`) tasks (`$0.1405 → $0.1154`, `−17.8%`, `10W/0T/0L`, $p = 0.001953$;
      cold-repriced `−11.9%`, $p = 0.001953$)**, and cut pooled billed USD cost **`−6.2%` across all `N = 26` tasks
      (`$0.1450 → $0.1361`, `17W/1T/8L`, $p = 0.0296$)**. However, on `3/10` trace tasks (`D04`, `D05`, `K05`), following
      the `~966–1,080`-token skeleton with a second surgical `Class.method` call (`3 → 4` API calls) added ~`11k` cheap
      *cached* prefix tokens to raw `input + output` even while lowering billed USD cost (`$0.1614 → $0.1373`, `$0.1595 →
      $0.1310`, `$0.1490 → $0.1206`), leaving raw `total_tokens` at `−9.4%` on `Bucket A` (`31,442 → 28,497`, $p = 0.131$)
      and leaving **`H2` (`−2.5%` on `A+B`, Holm $p = 0.504`)** and **`H3` (`−2.3%` pooled, Holm $p = 0.504`)**
      nonsignificant once `6–9`-call `Bucket B` edit/`pytest` variance (`+1.8%`, `4W/0T/4L`) was pooled in.
    - **Small-symbol parity (`Bucket C`, `N = 8`):** below `max_lines = 120`, `read_symbol` tokens tied identically on
      `7/8` tasks (`1W/7T/0L`, $p = 1.0000`), confirming zero small-symbol overhead.

### Pre-registered 3-arm R1 submodular repo-brief & recall synthesis study (Copilot CLI `1.0.112`, November 18, 2026)

- **24 paired tasks (`T01`–`T12` on this repository + `C01`–`C12` on `pallets/click` `8.1.8`; `Bucket A` warm crowd-out
  recovery, `Bucket B` noisy multi-session recall filtering, `Bucket C` `@root=` path-folding & direct-symbol controls;
  16 trace + 8 `pytest`-verified edits), 72 sessions (`gpt-6-astra`, default GitHub routing,
  `evidence/repo-brief-r1-20261118/`):** all three arms passed **24/24** (`72/72` sessions; `0` harms against `tm_lean`
  and `tm_v1_recall`, passing `brainspace.certification.harm_passes` at `quality_margin = 0.20`, $\alpha_1 = 0.0304$).
  - **Structural coverage under realistic multi-session `recall.jsonl` (`<= 320` tokens):** from identical 8-symbol,
    20-query `recall.jsonl` logs, fixed-slot `v1` collapsed to **5 distinct modules and 0 entrypoints** (`312t`) on this
    repository and **7 distinct modules** (`293t`) on Click, stalling at **`−3.9%` raw tokens vs `tm_lean` (`862,683 →
    828,943`, Wilcoxon $p = 0.900$)** and **`+0.04%` billed cost (`$2.73 → $2.73`)**. R1 (`BRIEF_SCHEMA = 2`, exact-integer
    monotone submodular marginal graph-coverage solver with `FLOOR_HUB = FLOOR_RECALL = FLOOR_ENTRY = 3`, strict
    1-anchor-per-module Phase 2a, recency + low-in-degree island VoI recall filtering, core-vs-auxiliary layout, and
    lossless `@root=<prefix>/` folding) expanded coverage to **10 distinct modules and 3 entrypoints in fewer tokens
    (`304t`)** here and **11 of 16 core modules (`68.8%`, `309t`)** on Click.
  - **`tm_r1_recall` vs `tm_v1_recall` (same `recall.jsonl`, same `<= 320t` budget):** raw tokens `828,943` →
    **`734,142` (−11.4%; 95% CI −20.5% to −3.7%; `−3,950` tokens/session; lower on 14 of 24 tasks; raw Wilcoxon $p =
    0.0680$)**, as-run billed cost `$2.73` → **`$2.54` (−7.0%; 95% CI −12.2% to −2.7%; Wilcoxon $p = 0.0417$)**,
    cold-repriced cost `$3.70` → **`$3.51` (−5.1%, Wilcoxon $p = 0.0433$)**, model calls `99` → **`88` (−11.1%,
    $p = 0.0469$, 7 lower / 16 ties / 1 higher)**, and orientation calls `42` → **`26` (−38.1%, Wilcoxon $p = 0.0078$,
    8 lower / 16 ties / 0 higher)**, raising Turn-1 direct `read_symbol`/`impact` jumps from **`58.3%` (`14/24`) to
    `79.2%` (`19/24`)** (`8.3%` on `tm_lean`). Token reductions held across both repositories (`−14.6%` here, `−8.5%` on
    Click) and all three buckets (`−14.6%` on `Bucket A`, `−10.1%` with 95% CI `−22.3%` to `−2.2%` on `Bucket B`, and
    `−7.6%` on `Bucket C` with `100%` edit pass safety on `@root=`-folded targets including `−25.2%` on `C09`).
  - **`tm_r1_recall` vs `tm_lean`:** raw tokens `862,683` → **`734,142` (−14.9%; 95% CI −26.2% to −4.2%; raw Wilcoxon
    $p = 0.0526$)**, billed cost `$2.73` → **`$2.54` (−6.9%, Wilcoxon $p = 0.0491$)**, model calls `108` → **`88`
    (−18.5%, $p = 0.0015$)**, and orientation calls `64` → **`26` (−59.4%, $p = 8.0 \times 10^{-6}$, 18 lower / 6 ties /
    0 higher)**—recovering the full ~15% Pillar 5 win in multi-session recall regimes where `v1` stalled.
  - **Honest limits & certification power:** on 10 of 24 tasks where `r1` and `v1` followed identical 2–3-call tool
    trajectories, deterministic brief-length deltas (`+16` tokens on Click vs `−8` tokens here) created `+2` to `+45`
    token differences that count against rank-sum symmetry, leaving two-sided Wilcoxon $p = 0.0680$ (`Holm p = 0.2106`)
    conservative at $n = 24$ even though bootstrap 95% CIs exclude zero across tokens, cost, calls, and orientation. Under
    PR `#35`'s worst-case `max-bet-v1` bounded-token e-process (`token_cap = 200,000`, `minimum_token_reduction = 1,000`),
    `bet_minimum_samples = 235` tasks are needed before a ~`4k–5k` mean token saving can pass `bet_passes` (`False` at
    $n = 24$).

### Pre-registered 4-arm Pillar 5 repo-brief & cross-session recall study (Copilot CLI `1.0.112`, November 17, 2026)

- **24 paired tasks (`T01`–`T12` on this repository + `C01`–`C12` on `pallets/click` `8.1.8`; `Bucket A` cold
  architecture, `Bucket B` cross-session recall, `Bucket C` direct-symbol controls; 16 trace + 8 `pytest`-verified
  edits), 96 sessions (`gpt-6-astra`, default GitHub routing, `evidence/repo-brief-20261117/`):** all four arms passed
  **24/24** (`96/96` sessions).
  - **`--lean` + cross-session recall brief (`tm_recall`, `301t` / `288t` via `hooks.sessionStart`):** raw tokens
    `1,681,304` → **`842,824` (−49.9%; 95% CI −55.6% to −44.3%; Wilcoxon $p = 1.19 \times 10^{-7}$, Holm $p < 0.0001$;
    lower on 24 of 24 tasks vs `stock`)**, cold-repriced cost `$6.90` → **`$3.79` (−45.1%)**, as-run billed cost `$4.23`
    → **`$2.82` (−33.4%)**. Against `tm_lean` (`990,069` tokens, `$3.06`), `tm_recall` cut raw tokens **`−14.9%`
    (95% CI −26.6% to −3.2%; Wilcoxon $p = 0.0035$; lower on 16 of 24 tasks)** and billed cost **`−7.9%` (raw Wilcoxon
    $p = 0.0194$, Holm $p = 0.0583$)**.
  - **`--lean` + cold architectural brief (`tm_brief`, `306t` / `296t`):** raw tokens `1,681,304` → **`838,974`
    (−50.1% vs `stock`; −15.3% vs `tm_lean`, Wilcoxon $p = 0.0211$, lower on 17 of 24 tasks)**, cold-repriced cost
    `$6.90` → **`$3.80` (−45.0%)**, as-run billed cost `$4.23` → **`$2.83` (−33.1% vs `stock`, −7.5% vs `tm_lean`)**.
  - **Turn-1 navigation mechanism & causal buckets:** without `.token-master/brief.md`, **0 of 24 (`0.0%`)** `tm_lean`
    sessions called `read_symbol` or `impact` on Turn 1; with the brief (`tm_brief`, `tm_recall`), **15 of 24 (`62.5%`)**
    did (`8/8 = 100%` on `Bucket A` under `tm_brief`; `6/8 = 75%` on `Bucket B` under `tm_recall`), cutting orientation
    calls by **43.9%** (`2.75 → 1.54`, Wilcoxon $p = 2.7 \times 10^{-5}$) and model calls by **16.2%** (`4.88 → 4.08`,
    $p = 0.0021$). On `Bucket C` controls, the brief's `Layout: src/click (16)` line let `tm_brief`/`tm_recall` skip an
    initial `locate` call on `T12` and `C09`–`C12`, yielding a net **−15.7%** token reduction (`23,032 → 19,422`) rather
    than a pure overhead tax.
  - **Honest limits & `/tokenomics` verification:** under the strict `320`-token cap on this repository, adding four
    `Recall:` lines displaced the `Entry:` lines (`brainspace_posttooluse.py::main`, `brainspace_copilot_bridge.py::main`),
    so `tm_brief` saved more than `tm_recall` on `Bucket A` (−29.8% vs −19.8% against `tm_lean`), while on `Bucket B`
    `tm_recall` lowered mean tokens −10.3% vs `tm_brief` (`47,564 → 42,656`, 6 of 8 tasks) with $n = 8$ Wilcoxon
    $p = 0.3828$ nonsignificant due to multi-call edit variance. Across all 48 brief sessions, `cl100k_base` brief
    counts (`306`, `301`, `296`, `288`) matched empirical Call-1 API `input_tokens` deltas (`+306.7`, `+302.0`,
    `+298.4`, `+288.7`) within **0.7 to 2.4 tokens**.

### Pre-registered 4-arm multi-turn & resumed-session study (Copilot CLI `1.0.112`, November 16, 2026)

- **12 paired 3-turn workflows (`M01`–`M04` stable coding, `M05`–`M08` mid-session capability escalation, `M09`–`M12`
  adversarial resume lookalikes), 48 sessions / 144 CLI launches (`gpt-6-astra`, default GitHub routing,
  `evidence/resume-multiturn-20261116/`):** all four arms passed **12/12** with **12/12** session continuity across
  `start` → `--resume <id>` → `--continue`.
  - **Shipped `--lean` resume lock (`tm_locked`, `Routing.resume_same_list`):** raw tokens `1,926,066` → **`1,036,427`
    (−46.2%; 95% CI −52.0% to −40.7%; Holm $p = 0.0029$; lower on 12 of 12 workflows)**. Turn-1-cold-normalized cost
    `$6.57` → **`$4.32` (−34.3%; 95% CI −38.2% to −30.7%; Holm $p = 0.0029$; lower on 12 of 12 workflows; −15.4% vs
    `tm_reroute`, Holm $p = 0.0073$)**. As-run cost `$5.23` → **`$3.87` (−26.1%)**, and resumed-turns-only cost
    (`Turns 2+3`) `$3.70` → **`$2.76` (−25.3%, Holm $p = 0.0146$)**.
  - **Opt-in monotonic escalation (`tm_escalate`, `TOKENMASTER_RESUME_ESCALATE=1`):** raw tokens `1,926,066` →
    **`1,105,416` (−42.6%)**, cold-normalized cost **`$4.86` (−25.9%)**, as-run cost **`$4.41` (−15.6%)**. Recalled
    **12/12** capability groups across all turns and used native tools on **4/4** mid-session escalations (`M05`–`M08`,
    `0/4` workarounds vs `4/4` workarounds under `tm_locked`), while paying prompt-cache rewrite costs when tools
    unlocked (`$1.04` vs `$0.76` stock on `M05`–`M08` Turns 2+3, exacerbated on Turn 3 when prompts referencing
    `"Turn 1"` / `"Turn 2"` triggered `session_history` in stateless MD-1).
  - **Pre-PR-#20 per-turn re-routing (`tm_reroute`):** raw tokens **`1,203,192` (−37.5%)**, cold-normalized cost
    **`$5.10` (−22.3%)**, and resumed-turn cost **`$3.52` (−4.7%, $p = 0.62$)** due to **17** resume tool-list
    mutations across 24 resumed turns.
  - **2-stage Copilot CLI `1.0.112` resume cache boundary:** `--resume` (Launch 2) injects `<session_context>` right
    after the static tool+instruction prefix (`57.7%` stock and `37.1%` `tm_locked` first-call cache hit), whereas
    `--continue` (Launch 3) caches **97.3% (`stock`)** and **92.6% (`tm_locked`)** of the entire multi-turn transcript
    when `--excluded-tools` stays fixed.

### Pre-registered 3-arm MD-1 live routing study (Copilot CLI `1.0.112`, November 15, 2026)

- **15 tasks on this repository (`A01`–`A05` pure coding, `B01`–`B05` indirect multi-capability phrasings, `C01`–`C05`
  lookalike coding prompts), 45 sessions (`gpt-6-astra`, default GitHub routing, `evidence/md1-live-routing-20261115/`):**
  - **`--lean` + live MD-1 (`tm_md1`):** raw tokens `980,700` → **`574,278` (−41.4%; 95% CI −52.2% to −28.7%; Wilcoxon
    $p = 0.0001$, Holm $p = 0.0002$; lower on 15 of 15 tasks)**. Cold-repriced cost `$4.55` → **`$3.02` (−33.6%; 95% CI
    −41.9% to −24.4%)**. As-run cost `$2.87` → **`$2.51` (−12.6%)**. Passed **15/15** and recalled **15/15** needed
    capabilities (including **5/5** indirect phrasings on Bucket B with 0 shell workarounds; MD-1 pre-launch latency
    628 ms median, 703 ms p90).
  - **`--lean`, regex only (`tm_regex`):** raw tokens `980,700` → **`537,104` (−45.2%; 95% CI −54.8% to −35.8%; lower
    on 15 of 15 tasks)**. Cold-repriced cost `$4.55` → **`$2.85` (−37.2%; 95% CI −43.3% to −31.4%)**. As-run cost
    `$2.87` → **`$2.42` (−15.5%)**. Passed **14/15**, recalling **0/5** indirect phrasings on Bucket B (`B02` failed
    without `session_store_sql`, `B04` thrashed across 8 calls without `fetch_copilot_cli_documentation`, and 3 of 5
    Bucket B sessions fell back to shell workarounds).
  - **Bucket breakdown & union finding (commit `f9750ff`):** on pure coding (`Bucket A`), Copilot CLI `1.0.112`'s
    `promptCacheBreakState` confirmed that removing all 13 auxiliary tools cut `tool_tokens + tool_instructions` from
    12,156 to 3,649 tokens/call (−70.0%). On lookalike coding prompts (`Bucket C`), standalone MD-1 rejected all 5
    distractors (`score <= 0.053`), but `f9750ff`'s `select_excluded_tools` took `regex | md1`, keeping unneeded tools
    on 5/5 prompts (6,601 tokens/call). Letting MD-1's per-family score replace the keyword rule when MD-1 answers
    drops Bucket C false keeps to 0/5 (`15/15` exact family match across `A01`–`C05`).

### Default setup and `--lean` (Copilot CLI `1.0.105`, November 1, 2026)

- **With `--lean`:** raw tokens `702,831` → **`333,094` (−52.6%; 95% CI −56.5% to −48.5%; lower on 15 of 15
  tasks)**. Cold-repriced cost `$3.74` → **`$1.71` (−54.4%; 95% CI −56.0% to −52.6%)**. As-run cost `$2.29` →
  **`$1.21` (−47.3%)**.
- **Default setup, no flags:** raw tokens `768,899` → **`621,988` (−19.1%; 95% CI −28.7% to −8.5%; lower on 13 of 15
  tasks)**. Cold-repriced cost `$3.85` → **`$3.32` (−13.9%; 95% CI −17.1% to −10.6%)**. As-run cost `$2.40` →
  **`$1.81` (−24.4%)**.
- Both savings are "lower" by the rule each protocol froze before its sessions. Both arms passed 15/15 in both runs.
- The two savings come from different places. `--lean` cuts the fixed prompt of every request: the median first
  call fell from 13,589 to 6,034 input tokens, and Copilot CLI counted 1,945 tokens of tool definitions against
  stock's 7,819. Without `--lean` the request is slightly larger (8,200 tokens of tool definitions) and the saving
  comes from fewer calls (51 → 43) through `tokenmaster-nav`, which all 15 sessions used.
- Limits: 15 short "who calls X?" lookups of 2 to 4 calls each, one model, one build. The two stock arms, configured
  the same, differed by 8.6% in raw tokens, so the task bootstrap understates session-to-session noise; against the
  other run's stock arm, `--lean` saves 56.7% and the default setup 11.5%.

### Default GitHub routing (Copilot CLI `1.0.104`, October 27, 2026)

- Django D01–D15 with `gpt-6-astra` and no relay, 30 sessions: raw tokens `708,928` → **`372,621` (−47.4%; 95% CI
  −52.8% to −41.7%; lower on 15 of 15 tasks)**. Cold-repriced cost `$3.75` → **`$2.05` (−45.4%; 95% CI −48.2% to
  −42.7%)**. As-run cost `$2.30` → **`$1.26` (−45.0%)**. Passed **15/15 stock, 15/15 TokenMaster**.
- The README's earlier headline figures, up to 58% fewer tokens and up to 54% lower cold-start cost (the top of its 38%
  to 58% and 34% to 54% ranges) with no drop in pass rate, came from PRS-6's relay run on these tasks. Under default
  routing on `1.0.104`, 58% and 54% did not hold: the 95% CIs end at 52.8% and 48.2%. The pass-rate claim held, and
  both results fall inside those ranges. Since November 1 the README quotes the `1.0.105` runs above instead; with
  `--lean`, raw tokens fell 52.6% and cold-start cost 54.4%.
- Compared with PRS-6's relay run on the same tasks and model, stock used the same raw tokens (`708,928` vs
  `707,799`) and TokenMaster used 27% more (`372,621` vs `293,779`). In this run each call carried a larger fixed
  prompt than in PRS-6, in both versions. Stock made fewer calls than in PRS-6 (47 vs 55); TokenMaster made about as
  many (44 vs 46).
- A relay control on `1.0.104`, with this run's client build, account, lanes and day, cut raw tokens by 48.6% (95% CI
  41.9% to 54.1%) and cold-repriced cost by 45.8%, against 47.4% and 45.4% under default routing. By the rule fixed
  before its sessions, routing explains none of the gap to PRS-6's 58.5% (its 95% CI allows at most 4.9 of the 11.1
  points). The gap lies in the other differences between the runs (client build, TokenMaster commit, day, account,
  lane location), and client build and routing interact. Routing does change the as-run cost: −64.9% through the
  relay, −45.0% under default routing
  ([Relay control](#relay-control-on-copilot-cli-10104-same-build-account-and-day)).

### Pre-registered study PRS-6 (Copilot CLI `1.0.98`, October 26, 2026)

- **Primary confirmatory benchmark (this repository, 29 tasks: `P01`–`P24` + `H01, H02, H03, H05, H06`, 116 sessions):**
  - **`gpt-6-astra`:** raw tokens `2,449,067` → **`1,237,510` (−49.5%; 95% CI −55.9% to −42.3%;
    Wilcoxon $p < 0.0001$, Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Cold-repriced cost
    `$8.91` → **`$5.21` (−41.5%; 95% CI −47.7% to −35.5%; Holm $p < 0.0001$; lower on 28 of 29
    tasks)**. As-run cost (back to back) `$6.83` → **`$3.40` (−50.2%; 95% CI −59.6% to −42.0%)**.
    Passed **29/29 stock, 29/29 TokenMaster**.
  - **`claude-opus-5.5`:** raw tokens `2,672,316` → **`1,655,797` (−38.0%; 95% CI −44.7% to
    −31.3%; Wilcoxon $p < 0.0001$, Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Cold-repriced
    cost `$4.23` → **`$2.79` (−34.0%; 95% CI −38.7% to −29.3%; Holm $p < 0.0001$; lower on 28 of 29
    tasks)**. As-run cost (back to back) `$2.72` → **`$1.63` (−40.1%; 95% CI −48.2% to −32.3%)**.
    Passed **29/29 stock, 29/29 TokenMaster**.
- **Django 5.2 caller replication (`D01`–`D15`, 15 tasks per model, 60 sessions, `SCHEMA_VERSION = 4` import-alias resolution):**
  - `brainspace/symbol_index.py` (`SCHEMA_VERSION = 4` in this run, 5 since PR #14) resolves `import a as b` and
    `from a import b as c` (minus shadowed function parameters), bringing `D01`–`D15` caller recall
    from `54/56` to `56/56` (including `D13`, where `login` is imported as `auth_login`).
  - **`gpt-6-astra` (`D01`–`D15`):** raw tokens `707,799` → **`293,779` (−58.5%; 95% CI −64.4% to
    −52.3%; lower on 15 of 15 tasks)**; cold-repriced cost `$3.40` → **`$1.58` (−53.5%)**; as-run
    cost `$2.36` → **`$0.69` (−70.7%)**; passed **15/15 vs 15/15**.
  - **`claude-opus-5.5` (`D01`–`D15`):** raw tokens `989,925` → **`457,875` (−53.7%; 95% CI −57.8%
    to −48.9%; lower on 15 of 15 tasks)**; cold-repriced cost `$1.81` → **`$0.98` (−46.0%)**;
    as-run cost `$1.11` → **`$0.43` (−61.2%)**; passed **15/15 vs 15/15**.

### Exploratory runs (Copilot CLI `1.0.78-3`, October 18–22, 2026)

- **Django, 45 "who calls X?" tasks (`1.0.78-3`):** full TokenMaster used 53.4% fewer raw tokens
  than stock Copilot CLI with `gpt-6-astra` (95% CI −57.1% to −49.1%). With `claude-opus-5.5`, it
  used 51.6% fewer (95% CI −55.7% to −47.2%). It used fewer raw tokens on all 45 tasks with each
  model.
- **Cost at GitHub's prices depends on how close together the sessions run (`1.0.78-3`, Django 45-task):**
  - As run, with sessions back to back: 79.9% lower (`gpt-6-astra`) and 60.8% lower
    (`claude-opus-5.5`).
  - Re-priced as if every session started with a cold cache: 49.5% and 46.0% lower.
  - Read [How to read the cost numbers](#how-to-read-the-cost-numbers) before you quote a cost
    saving.
- **Correct answers (`1.0.78-3`, Django 45-task):** stock 90 of 90; full TokenMaster 88 of 90.
- **This repository, 27 tasks (`1.0.78-3`):** full TokenMaster used 44.8% fewer raw tokens with
  `gpt-6-astra` and 53.5% fewer with `claude-opus-5.5`.
- **Where the saving comes from (`1.0.78-3`):** most of it came with the lean tool set. On Django,
  graphify navigation cut a further 15.4% (`gpt-6-astra`) and 9.8% (`claude-opus-5.5`) of the raw
  tokens that TokenMaster without graphify used. That is 8.5 and 5.3 percentage points of stock's
  tokens.
- **Copilot CLI version:** the October 18–22 exploratory runs used `1.0.78-3`. On October 26, the
  pre-registered PRS-6 study measured Copilot CLI `1.0.98`
  ([Pre-registered study PRS-6](#pre-registered-study-prs-6-on-copilot-cli-1098-october-26-2026) and
  [Copilot CLI version](#copilot-cli-version)).

## Default setup and `--lean` on Copilot CLI `1.0.105` (November 1, 2026)

Since PR #20 the launcher sends every built-in tool unless it is started with `--lean`, and no earlier run measured
that default. Two exploratory runs on November 1 measure it and `--lean` on one build. Each repeats the October 27
default-routing run (same harness, Django tasks and orders, model, flags, account and lane checks) with the TokenMaster
arm set one way, and each has its own stock arm, run at the same time. Each protocol was written and its SHA-256
recorded before its sessions: `evidence/default-nolean-20261101/PROTOCOL.md`, with one amendment before any session
that raised the install step's timeout after both shards' graphify indexing ran past it, and
`evidence/lean-20261101/PROTOCOL.md`.

| Parameter | Value |
| --- | --- |
| Session start times | November 1, 2026: 16:12 to 16:20 UTC (default setup), 20:54 to 21:02 UTC (`--lean`) |
| Client | Copilot CLI `1.0.105` in all 60 sessions, read from each session's event log |
| Routing | Copilot CLI's default GitHub routing with its own sign-in. No `COPILOT_PROVIDER_BASE_URL`, no relay. |
| Model and flags | `gpt-6-astra` with `--reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps --output-format json` |
| Arms | Stock; TokenMaster `e28d1ad` (`setup.py` with graphify `0.9.91`, `brainspace_setup.py`) started through the launcher without `--lean` (first run) or with it (second run). The launch records (`launches.jsonl`) show `"lean": false` on all 15 starts of the first run and `"lean": true` with the same 13 excluded tools on all 15 of the second. |
| Harness | `token-master-plugin/evals/default_routing_ab.py` at `e28d1ad`, through each folder's `run.py` |
| Measurement and statistics | As on October 27: Copilot CLI's own per-call records, paired bootstrap over tasks (10,000 resamples, seed 20261022), exact Wilcoxon, Holm over raw tokens and cold-repriced cost |
| Audit | All 60 sessions: version, model, one Copilot session per run, GitHub's charge equal to its token counts and to the CLI's own total, results recounted from the per-call records. No problem found. |

| Django D01-D15, `gpt-6-astra`, `1.0.105` | Stock | TokenMaster | Change (95% CI) | Wilcoxon / Holm $p$ |
| --- | ---: | ---: | ---: | ---: |
| Default setup: raw tokens | 768,899 | **621,988** | **−19.1%** (−28.7%, −8.5%; lower on 13/15) | $p = 0.0020$ / $0.0020$ |
| Default setup: cost, every first call cold | $3.85 | **$3.32** | **−13.9%** (−17.1%, −10.6%; lower on 15/15) | $p < 0.0001$ / $0.0001$ |
| Default setup: cost, as run | $2.40 | **$1.81** | **−24.4%** (−35.5%, −8.5%) | $p = 0.0067$ |
| Default setup: model calls | 51 | 43 | −15.7% (−25.0%, −5.7%) | $p = 0.035$ |
| `--lean`: raw tokens | 702,831 | **333,094** | **−52.6%** (−56.5%, −48.5%; lower on 15/15) | $p < 0.0001$ / $0.0001$ |
| `--lean`: cost, every first call cold | $3.74 | **$1.71** | **−54.4%** (−56.0%, −52.6%; lower on 15/15) | $p < 0.0001$ / $0.0001$ |
| `--lean`: cost, as run | $2.29 | **$1.21** | **−47.3%** (−49.4%, −44.9%) | $p < 0.0001$ |
| `--lean`: model calls | 47 | 50 | +6.4% (−2.1%, +15.2%) | $p = 0.375$ (n.s.) |
| Passed, stock and TokenMaster | | | 15/15 and 15/15 in both runs | |

What the numbers show:

- `--lean` cuts the fixed prompt of every request. The median first call fell from 13,589 to 6,034 input tokens, and
  Copilot CLI counted 1,945 tokens of tool definitions against stock's 7,819. The number of calls barely moved. These
  sessions had 3 to 4 calls; a per-request saving should be a smaller share of a longer session, which was not
  measured.
- The default setup sends a slightly larger request than stock (8,200 tokens of tool definitions, with
  `tokenmaster-nav` added and nothing removed) and saves through fewer calls (51 → 43). All 15 sessions used
  `tokenmaster-nav` (21 calls). Each of these tasks asks the question `impact` answers in one call, so other work
  should save less.
- Between the runs, on the same day and build, the `--lean` saving exceeds the default setup's by 33.5 points of raw
  tokens (95% CI 24.0 to 43.2) and 40.5 points of cold-repriced cost (36.7 to 44.1). That is a comparison across two
  runs. The two stock arms, configured the same, differed by 8.6% in raw tokens (768,899 vs 702,831): stock took a
  fourth call on D03, D04, D12 and D15 in the earlier run. The bootstrap resamples tasks only, so these CIs understate
  session-to-session noise. Against the other run's stock arm, `--lean` saves 56.7% and the default setup 11.5%.
- The cold-repriced cost prices each session's first call as a cache miss. GitHub's charges as run fell 47.3% with
  `--lean` and 24.4% in the default setup.
- The runs used 421.6 AI credits ($4.22) and 349.6 ($3.50). A first attempt at the default-setup run stopped during
  setup, before any session, when graphify's index in both shards ran past the 900-second install timeout.

Evidence: `evidence/default-nolean-20261101/` and `evidence/lean-20261101/` (`PROTOCOL.md`, `PROTOCOL.sha256`, `run.py`,
`analyze.py`, `analysis.json`, and per shard `results.jsonl`, `setup.json`, `summary.json`, `launches.jsonl` and
per-call `calls.jsonl`).

## Pre-registered study PRS-6 on Copilot CLI `1.0.98` (October 26, 2026)

### 1. Protocol and version verification

- Pre-registered before any study call ([PRS6_PROTOCOL.md](PRS6_PROTOCOL.md), commit `19443fc`).
- Pinning `COPILOT_CLI_DIST_DIR` to `1.0.98` and removing `--no-auto-update` ran Copilot CLI
  `1.0.98`, verified in 176 of 176 session captures (`Version number: 1.0.98`, 0 recount mismatches,
  `total_nano_aiu` matching calculated USD to `$0.0001`).
- Evidence: `evidence/prs6-copilot-1.0.98-20261026/analysis.json` and `capture_audit.json`.

### 2. Primary confirmatory benchmark (this repository, 29 tasks, 116 sessions)

- **Tasks:** 29 tasks per model (`P01`–`P24` + `H01, H02, H03, H05, H06`).
- **Session start times:** October 26, 2026, 16:59–17:05 UTC.
- **Workload floor:** both models met the pre-registered 2,000,000 raw-token stock workload floor
  (`2,449,067` for `gpt-6-astra`, `2,672,316` for `claude-opus-5.5`).

| 29 tasks per model (`1.0.98`) | Stock | Full TokenMaster | Change (95% CI) | Wilcoxon / Holm $p$ |
| --- | ---: | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,449,067 | **1,237,510** | **−49.5%** (−55.9%, −42.3%) | $p < 0.0001$ / $< 0.0001$ |
| `gpt-6-astra` cost, every first call cold | $8.91 | **$5.21** | **−41.5%** (−47.7%, −35.5%) | $p < 0.0001$ / $< 0.0001$ |
| `gpt-6-astra` cost, as run (back to back) | $6.83 | **$3.40** | **−50.2%** (−59.6%, −42.0%) | $p < 0.0001$ |
| `gpt-6-astra` model calls | 171 | 143 | −16.4% (−25.1%, −6.0%) | $p = 0.0083$ |
| `gpt-6-astra` passed | 29/29 | **29/29** | — | — |
| `claude-opus-5.5` raw tokens | 2,672,316 | **1,655,797** | **−38.0%** (−44.7%, −31.3%) | $p < 0.0001$ / $< 0.0001$ |
| `claude-opus-5.5` cost, every first call cold | $4.23 | **$2.79** | **−34.0%** (−38.7%, −29.3%) | $p < 0.0001$ / $< 0.0001$ |
| `claude-opus-5.5` cost, as run (back to back) | $2.72 | **$1.63** | **−40.1%** (−48.2%, −32.3%) | $p < 0.0001$ |
| `claude-opus-5.5` model calls | 127 | 137 | +7.9% (−0.8%, +17.2%) | $p = 0.136$ (n.s.) |
| `claude-opus-5.5` passed | 29/29 | **29/29** | — | — |

Details by model:

- **`gpt-6-astra`:**
  - Raw tokens: `2,449,067` → **`1,237,510` (−49.5%; 95% CI −55.9% to −42.3%; Wilcoxon $p < 0.0001$,
    Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Meets the 2,000,000 raw-token workload floor.
  - Cold-repriced cost: `$8.91` → **`$5.21` (−41.5%; 95% CI −47.7% to −35.5%; Holm $p < 0.0001$;
    lower on 28 of 29 tasks)**.
  - As-run cost (back to back): `$6.83` → **`$3.40` (−50.2%; 95% CI −59.6% to −42.0%)**. On
    `1.0.98`, 28 of 29 stock first calls started warm (median `6,450` cached, `4,882` cache write),
    vs 27 of 29 TokenMaster (`5,721` cached, `322` cache write).
  - Calls: `171` → `143` (−16.4%); `tokenmaster-nav` used in 29 of 29 sessions (`124` calls).
  - Passed: **29/29 stock, 29/29 TokenMaster**.
- **`claude-opus-5.5`:**
  - Raw tokens: `2,672,316` → **`1,655,797` (−38.0%; 95% CI −44.7% to −31.3%; Wilcoxon $p < 0.0001$,
    Holm $p < 0.0001$; lower on 27 of 29 tasks)**. Meets the 2,000,000 raw-token workload floor.
  - Cold-repriced cost: `$4.23` → **`$2.79` (−34.0%; 95% CI −38.7% to −29.3%; Holm $p < 0.0001$;
    lower on 28 of 29 tasks)**.
  - As-run cost (back to back): `$2.72` → **`$1.63` (−40.1%; 95% CI −48.2% to −32.3%)**. Warm first
    calls: 28 of 29 stock (median `11,226` cached, `7,265` cache write) and 28 of 29 TokenMaster
    (`8,762` cached, `543` cache write).
  - Calls: `127` → `137` (+7.9%, not significant, $p = 0.136$); `tokenmaster-nav` used in 6 of 29
    sessions (`8` calls).
  - Passed: **29/29 stock, 29/29 TokenMaster** (including `H03`, now that `same_content()` ignores
    CRLF-only rewrites).

### 3. Django 5.2 caller replication on `1.0.98` with `SCHEMA_VERSION = 4` import-alias resolution (`D01`–`D15`, 60 sessions)

- **Session start times:** October 26, 2026, 17:34–17:56 UTC (15 tasks per model, 60 sessions).
- **Import-alias resolution (`SCHEMA_VERSION = 4`):** `brainspace/symbol_index.py`
  (`SCHEMA_VERSION = 4` in this run, 5 since PR #14) now resolves `import a as b` and `from a import b as c` (minus shadowed
  function parameters), so `impact("django/contrib/auth/__init__.py::login")` finds
  `auth_login(...)` callers in `django/contrib/auth/views.py` (`D13`), bringing `D01`–`D15` caller
  recall from `54/56` to `56/56`.

| 15 Django tasks per model (`1.0.98`) | Stock | Full TokenMaster | Change (95% CI) |
| --- | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 707,799 | **293,779** | **−58.5%** (−64.4%, −52.3%; lower on 15/15) |
| `gpt-6-astra` cost, every first call cold | $3.40 | **$1.58** | **−53.5%** (−57.0%, −49.8%) |
| `gpt-6-astra` cost, as run (back to back) | $2.36 | **$0.69** | **−70.7%** (−76.6%, −63.4%) |
| `gpt-6-astra` passed | 15/15 | **15/15** | — |
| `claude-opus-5.5` raw tokens | 989,925 | **457,875** | **−53.7%** (−57.8%, −48.9%; lower on 15/15) |
| `claude-opus-5.5` cost, every first call cold | $1.81 | **$0.98** | **−46.0%** (−48.8%, −43.2%) |
| `claude-opus-5.5` cost, as run (back to back) | $1.11 | **$0.43** | **−61.2%** (−68.2%, −53.8%) |
| `claude-opus-5.5` passed | 15/15 | **15/15** | — |

- **`gpt-6-astra` (`D01`–`D15`):** Raw tokens `707,799` → **`293,779` (−58.5%; 95% CI −64.4% to
  −52.3%; lower on 15 of 15 tasks)**; cold-repriced cost `$3.40` → **`$1.58` (−53.5%)**; as-run
  cost `$2.36` → **`$0.69` (−70.7%)**; passed **15/15 vs 15/15**.
- **`claude-opus-5.5` (`D01`–`D15`):** Raw tokens `989,925` → **`457,875` (−53.7%; 95% CI −57.8% to
  −48.9%; lower on 15 of 15 tasks)**; cold-repriced cost `$1.81` → **`$0.98` (−46.0%)**; as-run
  cost `$1.11` → **`$0.43` (−61.2%)**; passed **15/15 vs 15/15**.

## Default GitHub routing on Copilot CLI `1.0.104` (October 27, 2026)

The runs of October 18 to 26 and the relay control below sent Copilot CLI's requests through the evaluation relay in
bring-your-own-model mode. This run did not, and neither did the two November 1 runs above. Copilot CLI signed in with
its own stored login and sent every request to GitHub's Copilot API itself. Without a provider URL, the TokenMaster
launcher added the lean tool set (since October 31 it does so only
with `--lean`), and `tokenmaster-nav` and the v6 `view` hook loaded. The bridge does not run, so there is no
cache-stable system prompt and no request shaping.

The protocol and its decision rule were committed before the 30 study sessions
(`evidence/default-routing-20261027/PROTOCOL.md`, commit `1c84310`). The run is exploratory: unlike PRS-6, the
protocol was written after a probe and a pilot, which the analysis excludes.

### Setup

| Parameter | Value |
| --- | --- |
| Session start times | October 27, 2026, 14:19–14:30 UTC |
| Client | Copilot CLI `1.0.104`, the latest release, read from each session's own event log (30 of 30) |
| Routing | Copilot CLI's default GitHub routing with its own sign-in, a GitHub Enterprise Cloud account with data residency. No `COPILOT_PROVIDER_BASE_URL`, no relay. |
| Model | `gpt-6-astra` with PRS-6's flags (`--reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps --output-format json`) |
| Tasks | Django 5.2 commit `9e7cc2b6`, D01–D15, in PRS-6's two shards and orders, run at the same time |
| Versions | Stock; full TokenMaster `v0.2.0` (`setup.py` with graphify `0.9.91`, `brainspace_setup.py`, the launcher) |
| Measurement | Copilot CLI's own record of each model call (`session-store.db`, table `assistant_usage_events`): GitHub's token counts, GitHub's charge (`total_nano_aiu`) and GitHub's per-token prices. `tokenomics.py` reads the same table. |
| Isolation | One Copilot home and profile per version, outside the operator's profile folder. Before the first session, `copilot skill list` and `copilot instruction list` checked that neither version loaded skills or instruction files from outside the study. |
| Statistics | As in PRS-6: paired bootstrap over tasks, 10,000 resamples, seed 20261022; exact Wilcoxon; Holm over raw tokens and cold-repriced cost |
| Audit | All 30 sessions: version, model, one Copilot session per run, GitHub's charge equal to its token counts times its prices and to the CLI's own running total, results recounted from the per-call records. No problem found. |

### Results

| 15 Django tasks, `gpt-6-astra` | Stock | Full TokenMaster | Change (95% CI) | Wilcoxon / Holm $p$ |
| --- | ---: | ---: | ---: | ---: |
| Raw tokens | 708,928 | **372,621** | **−47.4%** (−52.8%, −41.7%; lower on 15/15) | $p < 0.0001$ / $p = 0.0001$ |
| Cost, every first call cold | $3.75 | **$2.05** | **−45.4%** (−48.2%, −42.7%; lower on 15/15) | $p < 0.0001$ / $p = 0.0001$ |
| Cost, as run (back to back) | $2.30 | **$1.26** | **−45.0%** (−49.4%, −40.5%) | $p < 0.0001$ |
| Model calls | 47 | 44 | −6.4% (−14.6%, +2.2%) | $p = 0.375$ (n.s.) |
| Passed | 15/15 | **15/15** | | |

`tokenmaster-nav` was used in 15 of 15 TokenMaster sessions (27 calls). The lean tool set removed the same 11 tools
for every prompt. With graphify `0.9.91`, `impact` finds all 56 answer-key callers of D01–D15
(`impact_recall-0.9.91.json`).

### The README hero numbers of October 27 under default routing

`PROTOCOL.md` fixed the rule before the sessions: a hero number holds if the 95% CI of the reduction reaches it.

| README claim | Default routing, D01–D15 | Holds |
| --- | --- | --- |
| Up to 58% fewer tokens | 47.4% fewer (95% CI 41.7% to 52.8%) | No |
| Up to 54% lower cold-start cost | 45.4% lower (95% CI 42.7% to 48.2%) | No |
| No drop in pass rate | 15/15 stock, 15/15 TokenMaster | Yes |

TokenMaster used 52.6% of stock's raw tokens and 54.6% of its cold-repriced cost, close to half of each. The 58% and
54% figures of that README were relay-mode results. This check tested them on `1.0.104`; since November 1 the README
quotes the `1.0.105` runs, where `--lean` cut raw tokens by 52.6% and cold-repriced cost by 54.4% under default
routing ([Default setup and `--lean`](#default-setup-and---lean-on-copilot-cli-10105-november-1-2026)).

### Compared with the relay run (PRS-6, same tasks and model)

| `gpt-6-astra`, D01–D15 | Relay (PRS-6, `1.0.98`) | Default routing (`1.0.104`) |
| --- | ---: | ---: |
| Stock raw tokens | 707,799 | 708,928 |
| TokenMaster raw tokens | 293,779 | 372,621 |
| Raw-token change | −58.5% (−64.4%, −52.3%) | −47.4% (−52.8%, −41.7%) |
| Cold-repriced cost change | −53.5% (−57.0%, −49.8%) | −45.4% (−48.2%, −42.7%) |
| As-run cost change | −70.7% (−76.6%, −63.4%) | −45.0% (−49.4%, −40.5%) |
| Model calls, stock → TokenMaster | 55 → 46 | 47 → 44 |
| Stock first call: input / cached / written (medians) | 11,200 / 6,450 / 4,749 | 13,587 / 9,017 / 4,569 |
| TokenMaster first call: input / cached / written (medians) | 5,906 / 5,723 / 181 | 7,791 / 4,865 / 2,924 |
| `tokenmaster-nav` used | 15 of 15 sessions (23 calls) | 15 of 15 sessions (27 calls) |
| Passed, stock and TokenMaster | 15/15, 15/15 | 15/15, 15/15 |

What the numbers show:

- Stock used the same raw tokens with both routings; TokenMaster used 27% more under default routing. The smaller
  saving is on the TokenMaster side.
- Each call carried more tokens under default routing: stock 15,084 per call (relay 12,869) and TokenMaster 8,469
  (relay 6,387). Stock made 8 fewer calls than in PRS-6; TokenMaster made 2 fewer. Stock's fewer calls offset its
  larger calls, and TokenMaster's did not.
- The two runs differ in routing, and also in Copilot CLI build (`1.0.104` vs `1.0.98`), account (Copilot CLI's own
  sign-in vs the relay's), day, TokenMaster commit (`v0.2.0` vs `19443fc`) and lane location. In this run's pilot,
  stock first calls under default routing were 13,519 tokens on `1.0.98-2` and 13,587 on `1.0.104`. The relay control
  below separates routing from the rest on `1.0.104`.
- The as-run cost saving fell further than the token saving (−70.7% to −45.0%). With the bridge, TokenMaster's first
  calls wrote a median of 181 tokens to GitHub's cache; under default routing, without it, they wrote 2,924. The
  bridge was not switched on and off within one run, so its share of the gap was not tested. Back-to-back stock
  sessions also share a cached prefix under default routing: 14 of 15 stock first calls read a median of 9,017 tokens
  from the cache.

### Relay control on Copilot CLI `1.0.104` (same build, account and day)

The gap between PRS-6 and this run mixes routing with client build, account, day, lane location and TokenMaster
commit. A control run repeated PRS-6's evaluation relay (bring-your-own-model mode, `run_prs5_study.Relay`) with this
run's Copilot CLI `1.0.104`, lanes, graphify `0.9.91`, installed TokenMaster files, tasks and orders. The relay sent
Copilot CLI's own stored sign-in for this run's account to the Copilot API that GitHub names for that account,
because PRS-6's OpenCode sign-in no longer exists on this machine. The control and this run then differ in routing.
Copilot CLI posts `/responses` to the local relay, which forwards it over HTTPS, instead of using its own WebSocket
connection. It sends 18 tools instead of 20 in stock and 10 instead of 12 in TokenMaster: default routing adds
`web_fetch` and `semantic_code_search`. And in the TokenMaster arm the bridge's cache-stable system prompt and v6
shaping run, which need a provider URL. The 30 sessions ran on October 27, 23:08–23:20 UTC, about nine hours after
this run's (the protocol expected about two). The run is exploratory: its protocol and reading rule were committed
after a D01 pilot and lane test and before the 30 sessions (`evidence/relay-control-20261027/PROTOCOL.md`, commit
`02f5049`), and the analysis excludes the pilot and the lane test. Audit: all 30 sessions ran `1.0.104` (system prompt
and event log), `gpt-6-astra` answered every call, every call carried GitHub's charge, equal to its token counts at
its own prices, and every results row matched its recount. No problem found.

| `gpt-6-astra`, D01–D15 | Relay, `1.0.98` (PRS-6) | Relay, `1.0.104` (control) | Default routing, `1.0.104` |
| --- | ---: | ---: | ---: |
| Stock raw tokens | 707,799 | 708,801 | 708,928 |
| TokenMaster raw tokens | 293,779 | 364,319 | 372,621 |
| Raw-token change | −58.5% (−64.4%, −52.3%) | −48.6% (−54.1%, −41.9%) | −47.4% (−52.8%, −41.7%) |
| Cold-repriced cost change | −53.5% (−57.0%, −49.8%) | −45.8% (−48.8%, −42.6%) | −45.4% (−48.2%, −42.7%) |
| As-run cost change | −70.7% (−76.6%, −63.4%) | −64.9% (−71.2%, −58.0%) | −45.0% (−49.4%, −40.5%) |
| Model calls, stock → TokenMaster | 55 → 46 | 49 → 44 | 47 → 44 |
| Raw tokens per call, stock / TokenMaster | 12,869 / 6,387 | 14,465 / 8,280 | 15,084 / 8,469 |
| TokenMaster first call: input / cached / written (medians) | 5,906 / 5,723 / 181 | 7,614 / 7,447 / 164 | 7,791 / 4,865 / 2,924 |
| Passed, stock and TokenMaster | 15/15, 15/15 | 15/15, 15/15 | 15/15, 15/15 |

Between runs, resampling the 15 tasks 10,000 times:

- Routing moved TokenMaster's share of stock's raw tokens from 52.6% (default routing) to 51.4% (relay): −1.2 points,
  95% CI −4.9 to +2.0. For cold-repriced cost the difference is −0.4 points (−2.7 to +1.8). TokenMaster's raw tokens
  were 2.2% lower through the relay (−3.2% to −1.4%), and stock's were the same (0.0%, −5.5% to +7.2%).
- The other differences moved it from 41.5% (PRS-6) to 51.4%: +9.9 points (+4.9 to +14.5), and +7.8 points (+4.7 to
  +10.6) for cold-repriced cost. TokenMaster used 24.0% more raw tokens than in PRS-6 (+15.5% to +30.9%), stock the
  same (+0.1%, −7.6% to +8.4%), and stock made 11% fewer calls (−18.0% to −3.9%).
- By the reading rule fixed before the sessions, routing explains none of the 11.1-point raw-token gap or of the
  8.1-point cold-cost gap between PRS-6 and default routing: the routing CIs include 0, and the CIs for the rest
  exclude it. The routing CIs still allow up to 4.9 of the 11.1 points (44%) and 2.7 of the 8.1 (33%); the point
  estimates are 11% and 5%.
- One part of the rest is measured, and it interacts with routing. In the relay environment, Copilot CLI `1.0.104`
  sends two tool definitions that `1.0.98-2` does not, `run_dynamic_workflow` and `dynamic_workflows_manage`: 2,041
  cl100k tokens on every call as Copilot CLI sends them (about 1,840 GitHub tokens; an earlier count of 2,210 used
  JSON re-serialized with spaces), about a quarter of TokenMaster's first call and a seventh of
  stock's. TokenMaster's lean tool set removed neither in these runs (it removes both since this run, and only with
  `--lean` since October 31; the November 1 `--lean` run measured that set under default routing on `1.0.105`, but no
  relay run has measured it). PRS-6's requests carried 16 tools in stock and 8 in
  TokenMaster, the control's 18 and 10. Under default routing, though, `1.0.98-2` already listed both tools (this
  run's pilot, in Copilot CLI's event log; the tool lists are in the control's `SETUP_OBSERVATIONS.md`, section 3), and
  D01's first stock call differed by 65 tokens between the two builds (13,519 vs 13,584). In relay mode, Copilot CLI
  `1.0.104` still sends the two tools and `1.0.98-2` does not. So how the gap splits between routing and the rest
  depends on which build the comparison holds fixed. Taking about 1,840 tokens off each call of the control would put
  TokenMaster at about 46% of stock's raw tokens instead of 51%, about 5.6 of the 9.9 points; that arithmetic assumes
  the sessions would make the same calls without the two tools, which was not tested.
- Routing does change the as-run cost. Through the relay, TokenMaster's as-run cost was 34.5% lower than under default
  routing (−44.6% to −24.1%), and its saving against stock was −64.9% instead of −45.0%. Its first calls wrote a
  median of 164 tokens to GitHub's cache through the relay and 2,924 under default routing; stock's as-run cost was
  about the same (+2.6%, −1.8% to +7.0%). The bridge's cache-stable system prompt runs only with a provider URL, which
  fits this, but no run switched the bridge on and off by itself.
- The control used 371.0 AI credits ($3.71) by GitHub's charges: a D01 pilot 34.3, a D01 lane test 18.3, the study
  318.4.

Evidence: `evidence/relay-control-20261027/` (`PROTOCOL.md`, `SETUP_OBSERVATIONS.md`, `analysis.json`, `analyze.py`,
`captures_audit.json`, `dead_upstream_probe*.json` and `dead_upstream_probe.py`, and per shard `results.jsonl`,
`setup.json`, `summary.json`, `warmup.json` and per-call `calls.jsonl`). Harness:
`token-master-plugin/evals/relay_control_ab.py`.

### Setup findings

- Copilot CLI loaded `CLAUDE.md` and skills from the ancestor folders of the probe's lanes, which were
  under `%TEMP%`, inside the operator's profile, which holds a `.claude` folder (a `CLAUDE.md` and 101 skill
  entries), `.copilot` (109) and `.agents` (93). From such a lane, `copilot skill list` showed the operator's skills as
  inherited, and `copilot instruction list` showed a `CLAUDE.md`. The probe's stock first call was 23,463 tokens; a
  stock session of the same build from a lane outside the profile sent 13,519, on a task prompt about 60 tokens longer
  (`SETUP_OBSERVATIONS.md`). The study's lanes were outside the profile, and a check before the first session found
  no inherited skill or instruction file.
- PRS-6's lanes were also under `%TEMP%`, written in the 8.3 form (`C:\Users\<SHORT~1>\...`) that Python's
  `tempfile.gettempdir()` returns on this machine. Copilot CLI inherits from that form, and not from the same folder
  written in full. The relay control's probe, which captures the first request without a model call, found the
  operator's `CLAUDE.md` in it from the 8.3 form, and an `available_skills` list of 25 skills where a clean lane lists
  the 2 built-in ones: about 10,300 extra cl100k tokens. That held with `1.0.98-2` and `1.0.104`, and with the
  launcher in place before October 27 (last written May 19, so most likely the one PRS-6 ran). From the long form,
  the first lane test's sessions and `copilot instruction list` found nothing
  (`evidence/relay-control-20261027/SETUP_OBSERVATIONS.md`). PRS-6's stock first calls, 11,194 to 11,205 tokens,
  are within 2.5% of the clean size (about 10,940 for `1.0.98-2`) and far from the inherited one (about 20,250), so
  its sessions did not carry the operator's files. Why not was not tested: PRS-6's build,
  `1.0.98`, is no longer on this machine.
- Under default routing, Copilot CLI's auto-update is on; relay mode turns it off. In the pilot, a session pinned to
  `1.0.98-2` downloaded `1.0.104`, and the next session in the same lane ran `1.0.104`. The study pinned the latest
  release. Setting `COPILOT_AUTO_UPDATE=false` does not help: the launcher then runs its built-in `1.0.49`.
- With graphify `0.9.17`, the only version left on this machine, `impact` found 51 of the 56 answer-key callers (D03:
  1 of 6; `impact_recall-0.9.17.json`). The study installed `0.9.91`, PRS-6's version, in its own environment.
- The probe, the pilot and the study used 488.58 AI credits ($4.89): probe 48.25, pilot 84.19, study 356.14.

Evidence: `evidence/default-routing-20261027/` (`PROTOCOL.md`, `SETUP_OBSERVATIONS.md`, `analysis.json`,
`analyze.py`, `impact_recall*.json`, and per shard `results.jsonl`, `setup.json`, `summary.json` and per-call
`calls.jsonl`). Harness: `token-master-plugin/evals/default_routing_ab.py`.

## Test parameters (October 18–22 exploratory `1.0.78-3` runs)

| Parameter | Django run | Repository run |
| --- | --- | --- |
| Session start times | October 23, 2026, 03:10–03:47 UTC (October 22, 22:10–22:47 local time, UTC−5) | October 19, 2026, 19:38–19:45 UTC (14:38–14:45 local time) |
| Client | Copilot CLI 1.0.78-3, the real binary: the WinGet launcher's bundled build, which `--no-auto-update` selects. The installed package was 1.0.98 ([Copilot CLI version](#copilot-cli-version)). | Same |
| Models and API format | `gpt-6-astra` over OpenAI Responses; `claude-opus-5.5` over Anthropic Messages | Same |
| Copilot CLI command | `copilot -p <task> --model <model> --reasoning-effort low --allow-all-tools --no-ask-user --no-auto-update --disable-builtin-mcps --output-format json`. The TokenMaster versions ran the same command through the launcher, which adds `--excluded-tools` (the lean tool set). Every version ran with Copilot CLI's built-in MCP servers off. | Same |
| Routing | Offline bring-your-own-model mode (`COPILOT_OFFLINE=true`, `COPILOT_PROVIDER_BASE_URL`). Copilot CLI sent each request to a local evaluation relay. The relay forwarded it unchanged to `api.githubcopilot.com`. Provider limits: 200,000 prompt tokens and 16,000 output tokens. | Same |
| Repository | Django 5.2, `git archive` of commit `9e7cc2b6`; 2,818 Python files | This repository, snapshot `703aa20` |
| Tasks | 45 questions of the form "Which non-test functions or methods call X directly?": 25 rare names, 20 common names | 27: P01–P24 (locate 6, logic 6, impact 4, docs 4, edit 4), plus H02 and H05 (questions) and H03 (edit) |
| Versions | Stock; TokenMaster without graphify; full TokenMaster | Stock; full TokenMaster |
| Graphify | 0.9.91 | 0.9.84 |
| Runs per task and version | 1 | 1 |
| Sessions | 270 | 108 |
| Order | One shuffled task order (seed 20261019), the same for every version | Two halves of 13 and 14 tasks; one shuffled order per half (seed 20261020), the same for both versions |
| Concurrency and timing | 4 processes at the same time: for each model, one with stock and full TokenMaster in parallel, one with TokenMaster without graphify. Within each version, sessions ran back to back. | 4 processes at the same time: one per model and half, each with stock and full TokenMaster in parallel. Sessions ran back to back. |
| Session limits | 1,500-second timeout; one re-run for each infrastructure failure. No session needed one. | Same |
| Isolation | Each version had its own Copilot home and profile. Each session started from a fresh copy of the repository, with Copilot's session history cleared. No Python was on the agents' PATH. | Same |
| Grading | The JSON answer must list exactly the answer-key callers (paths normalized, order ignored). Any file change fails the task. | Questions: the same rule. Edits: in P-tasks, each edited file must match the expected file (Python files by syntax tree); H03 runs its own check script. Any change outside the allowed files fails. |
| Raw tokens | Input plus output tokens, as GitHub's API reported them | Same |
| Cost | GitHub's prices per 1M tokens. `gpt-6-astra`: $10 new input, $1 cached input, $12.50 cache write, $50 output. `claude-opus-5.5`: $4, $0.20, $5 and $20. | Same |
| Statistics | Paired bootstrap over tasks, 10,000 resamples, seed 20261022 | Same |

Definitions:
- **Stock:** Copilot CLI with no TokenMaster component.
- **TokenMaster without graphify:** `brainspace_setup.py --host copilot` only. Copilot CLI started
  through the TokenMaster launcher ([COPILOT_BRIDGE.md](COPILOT_BRIDGE.md)). It had the lean tool
  set, and the bridge applied the cache-stable system prompt and v6 shaping.
- **Full TokenMaster:** the same, plus `setup.py`. That step builds the graphify graph and installs
  the `tokenmaster-nav` server (`locate`, `read_symbol`, `impact`).
- **Evaluation relay:** it added the GitHub Copilot credential to each request. It recorded
  GitHub's usage counts and GitHub's own charge (`copilot_usage`) for each call. TokenMaster does
  not ship it.

For the Django run, a separate recount from the raw per-call records gave the same token totals.
GitHub's own per-call charges added up to the same costs.

## Copilot CLI version

The October 18–22 real-CLI runs on this page used Copilot CLI **1.0.78-3**. Until October 23, 2026,
this page said 1.0.98. That was wrong. On October 26, 2026, the pre-registered PRS-6 study ran
Copilot CLI **1.0.98** ([Pre-registered study PRS-6](#pre-registered-study-prs-6-on-copilot-cli-1098-october-26-2026)).

- In the October 18–22 runs, the harness passed `--no-auto-update`. With that flag, the WinGet
  launcher runs its bundled build, 1.0.78-3, even when a newer package is installed. Without the
  flag, it runs the newest installed package, 1.0.98.
- The harness checked the version with `copilot --version`, without the flag. That printed 1.0.98.
- Copilot CLI writes its version into its own system prompt. All 403 local session captures from the
  Django runs of October 19 and 22 say "Version number: 1.0.78-3". The repository run, PRS-5 and the
  bridge checks of October 18–19 used the same flag.
- The harness now checks the version with the same flags as its sessions (`cli_version` in
  `evals/run_prs5_study.py`). With the October 18–22 flags, the check stops the harness, because
  `CLI_VERSION` names 1.0.98.
- In PRS-6 (October 26), pinning `COPILOT_CLI_DIST_DIR` to `1.0.98` and removing `--no-auto-update`
  ran Copilot CLI `1.0.98`, verified in 176 of 176 session captures (`Version number: 1.0.98`).

A probe on October 23 sent one short prompt per model, version and tool set
(`evidence/copilot-version-probe-20261023/`):

| Model | Copilot CLI | Stock first call | Lean tool set first call | Removed by the lean tool set |
| --- | --- | ---: | ---: | ---: |
| `gpt-6-astra` | 1.0.78-3 | 13,507 | 6,732 | 6,775 (50.2%) |
| `gpt-6-astra` | 1.0.98 | 11,083 | 5,525 | 5,558 (50.1%) |
| `claude-opus-5.5` | 1.0.78-3 | 20,723 | 9,171 | 11,552 (55.7%) |
| `claude-opus-5.5` | 1.0.98 | 18,104 | 8,377 | 9,727 (53.7%) |

- On both versions, the lean tool set removes the same 11 tools: 16 tools become 5 with
  `gpt-6-astra`, and 17 become 6 with `claude-opus-5.5`. It removes about half of the first call.
- On 1.0.98, stock first calls can read part of the prompt from GitHub's cache. When another 1.0.98
  stock session ran shortly before, they read 6,450 tokens (`gpt-6-astra`) and 11,226
  (`claude-opus-5.5`), in both folders tested. On 1.0.78-3, stock `gpt-6-astra` first calls read
  nothing. So the bridge saves less on 1.0.98.
- The bridge makes a new session warm only in the same working folder. On 1.0.98, a TokenMaster
  session in the same folder as the one before wrote 99 tokens (`gpt-6-astra`) and 207
  (`claude-opus-5.5`) to the cache on its first call. In another folder, it wrote 2,874 and 4,034.
  Stock sessions after another stock session wrote about 4,632 and 6,879.
- With `claude-opus-5.5`, 1.0.98 asked for 32,000 output tokens and stopped when the provider limit
  was 16,000, the value of the October runs
  (`evidence/copilot-version-probe-20261023/opus-1.0.98-output-limit.txt`). The probe and PRS-6
  used 32,000.
- The pre-registered PRS-6 study on October 26 confirmed these `1.0.98` cache patterns across 176
  live sessions ([Pre-registered study PRS-6](#pre-registered-study-prs-6-on-copilot-cli-1098-october-26-2026)).

## How to read the cost numbers

- **Raw tokens do not depend on timing.** Cost does, because GitHub's prompt cache prices tokens
  differently.
  - `gpt-6-astra`: a cache read costs 0.1× and a cache write 1.25× the price of new input.
  - `claude-opus-5.5`: a cache read costs 0.05× and a cache write 1.25×.
- **In these runs, sessions ran back to back.** A new session could read an earlier session's
  prompt from GitHub's cache if the prompt was identical.
  - Stock Copilot CLI 1.0.78-3 writes each session's folder into its system prompt. With
    `gpt-6-astra`, no stock first call read from the cache (0 of 45 in the Django run). Each stock
    session wrote its prompt to the cache again, at 1.25×. Those first-call writes cost $7.65 of
    the $11.55 stock total; all stock cache writes cost $9.33.
  - The TokenMaster bridge moves the session-folder line, so every session in the same working
    folder sends the same prompt. The system prompt also names the working folder, and the bridge
    leaves that line in place. In the Django run, all sessions of a version used the same folder.
    In each TokenMaster version, 44 of 45 `gpt-6-astra` first calls read the prompt from the cache.
  - With `claude-opus-5.5` on 1.0.78-3, 44 of 45 stock first calls also read part of the prompt
    from the cache, because Anthropic's layout puts the tool definitions before the system prompt.
    Stock first calls still wrote the system prompt to the cache: a median of 7,474 tokens. Full
    TokenMaster first calls wrote a median of 314. No run isolated the bridge's own effect with
    `claude-opus-5.5`.
  - On Copilot CLI `1.0.98` (PRS-6, 29-task primary benchmark), 28 of 29 stock `gpt-6-astra` first
    calls started warm (median `6,450` cached, `4,882` cache write), vs 27 of 29 TokenMaster
    (`5,721` cached, `322` cache write). With `claude-opus-5.5` on `1.0.98`, 28 of 29 stock first
    calls (median `11,226` cached, `7,265` cache write) and 28 of 29 TokenMaster (`8,762` cached,
    `543` cache write) started warm.
- **A cached prompt does not last.** One probe found it still there after 6.5 minutes and gone
  after 31 minutes. Sessions that start further apart start cold.
- **The cold re-pricing** treats every first call as a cache miss. The tokens that the first call
  read from the cache are re-priced as cache writes. It applies to every version.
- **The bridge runs only in bring-your-own-model mode.** With Copilot CLI's default GitHub routing,
  the cache-stable system prompt does not apply. The October 27 run measured that configuration on
  Django D01–D15: TokenMaster's first calls wrote a median of 2,924 tokens to the cache, against 181
  with the bridge in PRS-6 ([Default GitHub routing](#default-github-routing-on-copilot-cli-10104-october-27-2026)).

| Cost, full TokenMaster vs stock (95% CI) | `gpt-6-astra` | `claude-opus-5.5` |
| --- | ---: | ---: |
| Default routing (`1.0.105`), `--lean`, Django 15 tasks (`D01`–`D15`), as run | −47.3% (−49.4%, −44.9%) | not run |
| Default routing (`1.0.105`), `--lean`, Django 15 tasks (`D01`–`D15`), every first call cold | −54.4% (−56.0%, −52.6%) | not run |
| Default routing (`1.0.105`), no flags, Django 15 tasks (`D01`–`D15`), as run | −24.4% (−35.5%, −8.5%) | not run |
| Default routing (`1.0.105`), no flags, Django 15 tasks (`D01`–`D15`), every first call cold | −13.9% (−17.1%, −10.6%) | not run |
| Default routing (`1.0.104`), Django 15 tasks (`D01`–`D15`), as run | −45.0% (−49.4%, −40.5%) | not run |
| Default routing (`1.0.104`), Django 15 tasks (`D01`–`D15`), every first call cold | −45.4% (−48.2%, −42.7%) | not run |
| PRS-6 (`1.0.98`), repository 29 tasks, as run | −50.2% (−59.6%, −42.0%) | −40.1% (−48.2%, −32.3%) |
| PRS-6 (`1.0.98`), repository 29 tasks, every first call cold | −41.5% (−47.7%, −35.5%) | −34.0% (−38.7%, −29.3%) |
| PRS-6 (`1.0.98`), Django 15 tasks (`D01`–`D15`), as run | −70.7% (−76.6%, −63.4%) | −61.2% (−68.2%, −53.8%) |
| PRS-6 (`1.0.98`), Django 15 tasks (`D01`–`D15`), every first call cold | −53.5% (−57.0%, −49.8%) | −46.0% (−48.8%, −43.2%) |
| Exploratory (`1.0.78-3`), Django 45 tasks, as run | −79.9% (−82.0%, −77.6%) | −60.8% (−64.6%, −56.9%) |
| Exploratory (`1.0.78-3`), Django 45 tasks, every first call cold | −49.5% (−51.5%, −47.5%) | −46.0% (−48.0%, −44.0%) |
| Exploratory (`1.0.78-3`), repository 27 tasks, as run | −62.8% (−71.3%, −54.6%) | −51.2% (−59.2%, −43.0%) |
| Exploratory (`1.0.78-3`), repository 27 tasks, every first call cold | −40.8% (−47.1%, −34.6%) | −43.9% (−48.2%, −39.7%) |

Inference: for sessions that start far apart, the cold rows are the better estimate. They are
close to the raw-token saving.

## Result 1: 45 "who calls X?" tasks on Django 5.2 (October 22, Copilot CLI `1.0.78-3`)

- **Task:** "We're about to change the signature of X. Which non-test functions or methods
  call it directly?"
  - The answer keys come from Django's syntax trees. Calls are resolved through each file's
    imports.
  - 25 tasks use rare names. 20 tasks use common names: for these, a repository-wide
    `rg -n -w <name>` returns 2,496 to 507,193 tokens.
  - The tasks were committed before the run (`0516a82`). We checked 10 answer keys by hand
    against `rg` (D04, D11–D15, D31, D32, D33 and D45). For every failed answer, the other
    versions passed with the same key.

| 45 tasks per model | Stock | TokenMaster without graphify | Full TokenMaster |
| --- | ---: | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,417,452 | 1,331,990 (−44.9%) | **1,127,277 (−53.4%)** |
| `gpt-6-astra` cost, as run | $11.55 | $3.37 (−70.8%) | **$2.33 (−79.9%)** |
| `gpt-6-astra` cost, every first call cold | $11.55 | $6.74 (−41.6%) | **$5.83 (−49.5%)** |
| `claude-opus-5.5` raw tokens | 3,457,179 | 1,855,563 (−46.3%) | **1,673,646 (−51.6%)** |
| `claude-opus-5.5` cost, as run | $3.31 | $1.48 (−55.2%) | **$1.30 (−60.8%)** |
| `claude-opus-5.5` cost, every first call cold | $6.14 | $3.39 (−44.8%) | **$3.31 (−46.0%)** |
| Correct answers, both models | 90/90 | 88/90 | 88/90 |

Change in raw tokens (95% CI):

| Comparison | `gpt-6-astra` | `claude-opus-5.5` |
| --- | ---: | ---: |
| Full vs stock | −53.4% (−57.1%, −49.1%) | −51.6% (−55.7%, −47.2%) |
| Without graphify vs stock | −44.9% (−49.7%, −39.1%) | −46.3% (−50.9%, −40.8%) |
| Full vs without graphify | −15.4% (−21.7%, −8.1%) | −9.8% (−18.4%, −0.8%) |
| Full vs without graphify, rare names | −22.5% (−29.6%, −14.6%) | +1.8% (−6.5%, +10.1%) |
| Full vs without graphify, common names | −8.1% (−17.3%, +2.9%) | −20.4% (−32.6%, −6.0%) |

Observations:

- Full TokenMaster used fewer raw tokens than stock on 45 of 45 tasks, with each model.
- Graphify reduced the number of model calls: 162 to 143 (`gpt-6-astra`) and 174 to 150
  (`claude-opus-5.5`).
- The models used the navigation tools in 45 of 45 (`gpt-6-astra`) and 26 of 45
  (`claude-opus-5.5`) full-TokenMaster sessions.
- Search output, counted once for each request that re-sent it, was 7.2% of stock
  `gpt-6-astra` tokens and 2.0% of stock `claude-opus-5.5` tokens.
- For `format` (D31), a bare repository-wide `rg` returns 507,193 tokens. The whole stock session
  used 58,880 (`gpt-6-astra`) and 89,408 (`claude-opus-5.5`) tokens. The local captures show why:
  the models searched for `dateformat` rather than `format`, limited searches to single files,
  or asked for file names only. Copilot's search tool also limits the length of its results.
- The 4 wrong answers were model errors:
  - D28, full, `gpt-6-astra`: named the public `changeform_view` and `delete_view` instead of
    the private methods that make the call.
  - D45, without graphify, `gpt-6-astra`: left out 4 admin callers.
  - D06, without graphify, `claude-opus-5.5`: named `_as_sql` instead of `as_sql`.
  - D45, full, `claude-opus-5.5`: added `smart_urlquote`, which calls the standard library's
    `urlencode`.

Evidence: `evidence/django-scale-20261022/` (`tasks.json`, `summary.json`, `analysis.json`,
`audit.json`, per-session `results.jsonl`, per-call `calls.jsonl`). Commits `0516a82`,
`5d27601` and `f3e6c36`.

Two smaller Django runs earlier on October 22 used 15 of these tasks with graphify 0.9.84
(`dd1f38a`, `d34b5c3`). The 45-task run repeated those 15 tasks and supersedes them.

## Result 2: 27 tasks on this repository (October 19, Copilot CLI `1.0.78-3`)

- **Tasks:** the 24 PRS-4 tasks P01–P24, which no real-CLI run had used before, plus the heavier
  PRS-5 tasks H02, H03 and H05.

| 27 tasks per model | Stock | Full TokenMaster |
| --- | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,404,853 | **1,326,925 (−44.8%; 95% CI −52.6% to −37.4%)** |
| `gpt-6-astra` cost, as run | $9.05 | **$3.37 (−62.8%)** |
| `gpt-6-astra` cost, every first call cold | $9.05 | **$5.36 (−40.8%)** |
| `claude-opus-5.5` raw tokens | 3,048,966 | **1,419,061 (−53.5%; 95% CI −58.8% to −48.3%)** |
| `claude-opus-5.5` cost, as run | $2.75 | **$1.34 (−51.2%)** |
| `claude-opus-5.5` cost, every first call cold | $4.49 | **$2.52 (−43.9%)** |
| Passed | 27/27 and 27/27 | 27/27 and 26/27 |

- Full TokenMaster used fewer raw tokens on 27 of 27 tasks (`gpt-6-astra`) and 26 of 27
  (`claude-opus-5.5`).
- Warm first calls: `gpt-6-astra` stock 0 of 27, TokenMaster 25 of 27; `claude-opus-5.5` stock 27
  of 27, TokenMaster 26 of 27.
- The one failure (H03, `claude-opus-5.5`) rewrote one extra file with CRLF line endings and no
  content change. The grader fails any change outside the allowed paths.
- In P13, stock `gpt-6-astra` called `task`, one of the 11 tools that the lean tool set removes.
  It started a subagent. The stock session used 124,403 raw tokens in 8 calls; TokenMaster used
  38,154 in 4 calls. Both passed.
- The confidence intervals were recomputed on October 22 with the bootstrap in the parameter
  table (`evidence/copilot-lean-analysis-20261022/`). Commit `c5681a7` reported slightly different
  intervals from an earlier, quicker computation.

Evidence: `evidence/copilot-lean-{astra,opus}-{a,b}-20261019/`. Commit `c5681a7`.

## Why the saving happens

- **Fixed overhead dominates.** Copilot CLI re-sends its system prompt and tool definitions on
  every model call. In the Django run, a stock first call sent 13,605 (`gpt-6-astra`) and
  20,871 (`claude-opus-5.5`) input tokens (medians).
- **The lean tool set removes auxiliary built-in tools.** No session called them in the October 18 runs,
  from which the list was chosen. Their definitions and the system-prompt text about them leave
  every call. One later stock session called `task` (P13, above). The 11 tools are
  `session_store_sql`, `task`, `read_agent`, `write_agent`, `list_agents`, `skill`, `sql`,
  `read_powershell`, `stop_powershell`, `list_powershell` and `fetch_copilot_cli_documentation`.
  Every TokenMaster arm from October 19 to October 27 removed these 11. After the relay control, the launcher also
  removes the two workflow tools (`run_dynamic_workflow`, `dynamic_workflows_manage`), 13 tools in all, and since
  October 31 only with `--lean`. The November 1 `--lean` run removed all 13; the November 1 default-setup run removed
  none.
  - A probe ran one lookup task per model on October 19. The tools sent fell from 16 to 5
    (`gpt-6-astra`) and from 17 to 6 (`claude-opus-5.5`).
  - The system prompt fell from 7,216 to 5,117 cl100k tokens (`gpt-6-astra`) and from 5,931 to
    3,833 (`claude-opus-5.5`).
  - The session used 27,255 → 13,702 and 42,544 → 19,434 raw tokens. Both answers were
    correct. One task per model shows the mechanism, not an average
    (`evidence/lean-tools-20261019/`).
- **Graph navigation saves model calls.** `impact` answers "who calls X" in one compact result.
  Each call that it saves would have re-sent at least the fixed overhead. With TokenMaster, a
  first call sent a median of 7,097 (`gpt-6-astra`) and 9,862 (`claude-opus-5.5`) input tokens.
- **The cache-stable system prompt lowers cost, not raw tokens.** See
  [How to read the cost numbers](#how-to-read-the-cost-numbers). It explains why the as-run cost
  saving with `gpt-6-astra` is larger than its raw-token saving.

## Grep and graph lookups without a model (October 19)

A script compared the tokens that each lookup returns, with no model calls. It sampled 40
random functions and classes per repository. It ran Copilot CLI's own `rg` and counted cl100k
tokens.

| Question | Repository | Raw `rg` output | Graph tool |
| --- | --- | ---: | ---: |
| Who uses X? | This repository (162 Python files) | 20,282 | `impact` 12,792 |
| Who uses X? | Django 5.2 (2,818 Python files) | 128,279 | `impact` 8,401 |
| Where is X defined? | Django 5.2 | 992 | `locate` 2,116 |

- The largest single Django `rg` output was 115,555 tokens. The largest `impact` result was
  2,325.
- These are raw `rg` outputs. Copilot's search tool shortens long results, and the models in
  Copilot CLI itself searched with narrower patterns (Result 1). So this table measures lookup output,
  not session cost.
- The same commit fixed a setup gap. `setup.py` left graphify's 9.5 MB `graphify-out/graph.json`
  visible to `rg`. Setup now adds `graphify-out/` to `.gitignore`.

Evidence: `evidence/grep-vs-graph-20261019/`. Commit `319d1b2`.

## Graphify version check (October 22) and `SCHEMA_VERSION = 4` import-alias resolution (October 26)

- Graphify was upgraded from 0.9.84 to 0.9.91. That was the newest version that the company
  package feed served. PyPI was not reachable directly, and the feed did not yet serve 0.9.92
  to 0.9.94.
- On the same Django commit, 0.9.91 built 50,858 nodes and 120,650 links, 33,094 of them calls.
  0.9.84 built 50,879 nodes and 118,194 links, 31,715 of them calls.
- With either version on `SCHEMA_VERSION = 3` (October 22), `impact` found 54 of the 56 answer-key
  callers for tasks D01–D15, because both missed calls through an import alias (in D13, `login` is
  imported as `auth_login`).
- On October 26 (`SCHEMA_VERSION = 4` in `brainspace/symbol_index.py`), import-alias resolution was
  added for `import a as b` and `from a import b as c` (minus shadowed function parameters). With
  `SCHEMA_VERSION = 4`, `impact("django/contrib/auth/__init__.py::login")` finds `auth_login(...)`
  callers in `django/contrib/auth/views.py` (`D13`), bringing `D01`–`D15` caller recall from `54/56`
  to `56/56` ([Pre-registered study PRS-6](#3-django-52-caller-replication-on-1098-with-schema_version--4-import-alias-resolution-d01d15-60-sessions)).

Evidence: `evidence/graphify-upgrade-20261022/` (commit `35bc10b`) and
`evidence/prs6-copilot-1.0.98-20261026/analysis.json`.

## Earlier exploratory runs (October 18)

These runs came before the lean tool set. TokenMaster then saved cost, but not reliably raw
tokens. Their costs are as run, with sessions back to back.

| Commit | Tasks | Model | Raw tokens | Cost | Passed (stock, TokenMaster) |
| --- | --- | --- | ---: | ---: | --- |
| `763d451` | H01, H04, H06, H07, H08 × 2 | `gpt-6-astra` | −16.6% | −25.3% | 9/10, 9/10 |
| `5524197` | H02, H03, H05 × 2 | `gpt-6-astra` | +7.6% | −14.3% | 6/6, 6/6 |
| `5524197` | H02, H03, H05 × 2 | `claude-opus-5.5` | +2.4% | −19.8% | 6/6, 6/6 |

- The `763d451` run used the 5 tasks that motivated its fix, so it is not an unbiased test.
- PRS-5, a pre-registered real-CLI study, stopped after 10 of 32 sessions on October 18. Its
  partial data are kept as evidence, not as a study result. In them, the `brainspace` MCP
  server's 5 tools got no calls, and each model call carried about 500 tokens of their
  definitions. Copilot setup now skips that server.

## Limits

- **Pre-registered vs exploratory.** PRS-6 on Copilot CLI `1.0.98` (October 26) was pre-registered
  before any study call ([PRS6_PROTOCOL.md](PRS6_PROTOCOL.md), commit `19443fc`). The October 18–22
  runs on `1.0.78-3` were exploratory: no protocol was pre-registered, though the tasks were
  committed before each run except the first 10-task Django run (D01–D10, superseded; `dd1f38a`).
  The October 27 and November 1 runs were exploratory too: each committed or hashed its protocol and
  decision rule before its sessions.
  The task types and the excluded tools were chosen by the team that builds TokenMaster.
- **Scope.** 1 run per task, 2 repositories and 2 models. The Django runs have one task type,
  "who calls X?". The runs on this repository have 27 (`1.0.78-3`) or 29 (`1.0.98`) tasks.
- **Copilot CLI version.** The October 18–22 runs used `1.0.78-3`; PRS-6 on October 26 used
  `1.0.98`; the two October 27 runs used `1.0.104`; the two November 1 runs, which the README hero
  quotes, used `1.0.105`. Copilot CLI `1.0.98` sends a smaller fixed prompt, and its stock first call can read
  part of the prompt from the cache when another session ran shortly before
  ([Copilot CLI version](#copilot-cli-version)).
- **Cost depends on timing.** The as-run costs come from back-to-back sessions. See
  [How to read the cost numbers](#how-to-read-the-cost-numbers).
- **Excluded tools.** With `--lean` the launcher removes 13 tools: the 11 that no session called in
  the October 18 runs, and the two workflow tools, which none of the 60 sessions of October 27
  called. On October 19, one stock session (P13) called `task`. The launcher keeps a family when the
  prompt given with `-p` or `-i`, a flag such as `--agent` or `--resume`, an installed skill or agent
  that the prompt names, `TOKENMASTER_KEEP_TOOLS` or the opt-in MD-1 router asks for it. Its keyword
  rules miss some phrasings, and an interactive session started without a prompt keeps only what its
  flags and `TOKENMASTER_KEEP_TOOLS` keep, so workloads that need subagents (`task`), agent
  workflows, skills, session-store search, SQL or background PowerShell can lose these tools.
  Since October 31 the launcher removes them only with `--lean`. Such workloads were not measured.
- **Routing.** All runs except the October 27 default-routing run and the two November 1 runs used
  bring-your-own-model mode through a relay, including the October 27 relay control. Those three
  runs used Copilot CLI's default GitHub routing on Django D01–D15 with `gpt-6-astra` only. The
  repository tasks and `claude-opus-5.5` were not measured with default routing.
- **Sandbox location.** Copilot CLI loaded `CLAUDE.md` and skills from the operator's profile
  folder when a lane's path was written in its 8.3 form, which is how the October 19–26 runs
  recorded their lanes under `%TEMP%`. PRS-6's stock first calls (October 26) are within 2.5% of a
  clean request's size, so its sessions did not load them; the October 19–22 runs were not checked
  ([Setup findings](#setup-findings)).
- **No test runs.** No Python was on the agents' PATH, so no task asked an agent to run tests.
- **Edit grading.** The edit grader fails any content change outside the allowed paths. In the
  October 19 `1.0.78-3` run, a line-ending-only rewrite outside the allowed paths also failed
  (`H03`, `claude-opus-5.5`). In PRS-6 (`1.0.98`), `same_content()` ignores CRLF-only rewrites.
- **Cost scope.** Cost uses GitHub's per-token prices. It does not count premium requests or
  plan allowances.

## Reproduce

```powershell
# Live runs only: a verified cl100k_base.tiktoken (README, Quickstart step 2). The harnesses' default path under
# evidence/controlled-scorecard-20261008/ is not in the repository; the audit and analysis scripts do not read the file.
$env:BRAINSPACE_TOKENIZER_FILE = "<path to cl100k_base.tiktoken>"
$py = ".\.token-master-dev\Scripts\python.exe"

# PRS-6 (Copilot CLI 1.0.98, October 26): recount captures, verify 1.0.98 version and nano_aiu, and compute CIs / Wilcoxon / Holm p.
& $py -B evidence\prs6-copilot-1.0.98-20261026\analyze.py

# Default setup and --lean (Copilot CLI 1.0.105, November 1): audit the committed per-call records, CIs and decisions.
& $py -B evidence\default-nolean-20261101\analyze.py
& $py -B evidence\lean-20261101\analyze.py

# Their live runs: as the default-routing live run below, through each folder's run.py, with --lanes dnr/dnc and
# --budget-credits 430/280 (default setup) or --lanes dlr/dlc and 370/250 (--lean). Set GRAPHIFY_NO_AUTO_REFRESH=1.
& $py -B evidence\default-nolean-20261101\run.py --suite django --repo <Django 9e7cc2b6 checkout> --tasks-file evidence\django-scale-20261022\tasks.json --tasks D09,D01,D07,D03,D05,D04,D08,D02,D06,D10 --output <new folder>\django-rare --lanes dnr --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 430

# Default GitHub routing (Copilot CLI 1.0.104, October 27): audit the committed per-call records, CIs and the hero check.
& $py -B evidence\default-routing-20261027\analyze.py

# Default-routing live run: Copilot CLI's own sign-in, no relay. Run both shards at the same time.
cd token-master-plugin\evals
& $py -B default_routing_ab.py --suite django --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D09,D01,D07,D03,D05,D04,D08,D02,D06,D10 --output <new folder>\django-rare --lanes drr --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 760
& $py -B default_routing_ab.py --suite django --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D12,D11,D14,D13,D15 --output <new folder>\django-common --lanes drc --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 400
cd ..\..

# Relay control (Copilot CLI 1.0.104, October 27): audit the committed per-call records, CIs and the reading rule.
& $py -B evidence\relay-control-20261027\analyze.py

# Relay control live run: PRS-6's relay with Copilot CLI's stored sign-in. Run both shards at the same time.
cd token-master-plugin\evals
& $py -B relay_control_ab.py --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D09,D01,D07,D03,D05,D04,D08,D02,D06,D10 --output <new folder>\relay-rare --lanes drr --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 320
& $py -B relay_control_ab.py --repo <Django 9e7cc2b6 checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --tasks D12,D11,D14,D13,D15 --output <new folder>\relay-common --lanes drc --graphify <graphify 0.9.91>\Scripts\graphify.exe --budget-credits 240
cd ..\..

# Recount tokens and GitHub's charges from the committed 1.0.78-3 per-call records (no model calls).
& $py -B evidence\django-scale-20261022\audit.py evidence\django-scale-20261022

# Confidence intervals and the cold re-pricing for the October 18–22 1.0.78-3 runs.
& $py -B evidence\django-scale-20261022\analyze.py
& $py -B evidence\copilot-lean-analysis-20261022\analyze.py

# Rebuild the 45 Django tasks from a Django 5.2 checkout.
& $py -B evidence\django-scale-20261022\make_tasks_scale.py <django checkout>

# Live run for one model: run both commands at the same time.
cd token-master-plugin\evals
& $py -B django_ab.py --repo <django checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --output <new folder>\astra-ab --variant ab --lanes djc --model gpt-6-astra
& $py -B django_ab.py --repo <django checkout> --tasks-file ..\..\evidence\django-scale-20261022\tasks.json --output <new folder>\astra-lean --variant lean --lanes dja --model gpt-6-astra

# Then summarize the four run folders.
& $py -B ..\..\evidence\django-impact-20261019\summarize.py <new folder> <evidence folder>

# The 27-task or 29-task run on this repository.
& $py -B quick_copilot_ab.py --model gpt-6-astra --tasks <ids> --repeats 1 --lanes <name> --output <new folder>
```

Live runs need an active GitHub Copilot sign-in in OpenCode and an installed Copilot CLI. The
harness reads the credential in memory and never writes it. It stops unless the Copilot CLI
version that its sessions run equals `CLI_VERSION` in `run_prs5_study.py` (`1.0.98`). Pinning
`COPILOT_CLI_DIST_DIR` to `1.0.98` and omitting `--no-auto-update` runs Copilot CLI `1.0.98`;
passing `--no-auto-update` to the WinGet launcher selects its bundled `1.0.78-3` build instead.

`default_routing_ab.py` needs a Copilot CLI sign-in (`copilot login`) instead of OpenCode's. It copies only the
account names into each lane, and the token stays in Windows Credential Manager. It pins `PACKAGE` (`1.0.104`), keeps
its lanes in `C:\tm-lanes` (`TM_LANES_ROOT`), and stops before the first session if a lane loads skills or
instruction files from outside the study.

`relay_control_ab.py` uses the same Copilot CLI sign-in for the relay. It reads the account's token from Windows
Credential Manager into memory and sends it to the Copilot API that GitHub names for the account. It runs
`default_routing_ab.py`'s package, lanes and lane check, and stops the run if the Copilot API refuses the sign-in or a
session runs another Copilot CLI version.
