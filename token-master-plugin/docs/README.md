# TokenMaster Documentation Index

This directory contains the architecture specifications, mathematical contracts, live benchmark reports, and historical iteration archive for TokenMaster. Every markdown document in this directory is indexed below, along with a few from elsewhere in the repository. The raw study records are under `evidence/`, and older research notes are under `docs/research/`.

---

## 1. Start Here: Current Evidence

- **[Copilot CLI results](COPILOT_CLI_RESULTS.md)**: runs of Copilot CLI itself, October 18 to November 1, 2026.
  - November 1, Copilot CLI 1.0.105 under GitHub's default routing, 15 Django "who calls X?" lookups with `gpt-6-astra`, each run against its own stock arm: with `--lean`, TokenMaster used 52.6% fewer raw tokens than stock, and cost fell 54.4% with every first call re-priced as cold. With no flags, the launcher's default since PR #20 (October 31), it used 19.1% fewer (95% CI 8.5% to 28.7%) and cost fell 13.9%. Both arms passed 15/15 in both runs. The README hero quotes these runs.
  - October 27, Copilot CLI 1.0.104 under default routing, same tasks and model, lean tool set on: 47.4% fewer raw tokens.
  - PRS-6, pre-registered, Copilot CLI 1.0.98, October 26, through the evaluation relay in bring-your-own-model mode: 49.5% (`gpt-6-astra`) and 38.0% (`claude-opus-5.5`) fewer raw tokens on 29 tasks in this repository, and 58.5% and 53.7% on the same 15 Django tasks. Both arms passed every task.
  - October 18 to 22, Copilot CLI 1.0.78-3, exploratory, through the same relay: 53.4% (`gpt-6-astra`) and 51.6% (`claude-opus-5.5`) fewer raw tokens on 45 Django tasks, and 44.8% and 53.5% on 27 tasks in this repository. Correct Django answers: stock 90/90, TokenMaster 88/90. Most of that saving came with the lean tool set; on Django, graphify cut a further 15.4% and 9.8%.
- **[Copilot CLI launcher and bridge](COPILOT_BRIDGE.md)**: how to start Copilot CLI through the launcher; the lean tool set, which is off unless you pass `--lean`, with its prompt rules and optional MD-1 routing; how a `--lean` resume gets the tool list the launcher last gave that session; and what the bridge adds in bring-your-own-model mode.
- **[/tokenomics dashboard](TOKENOMICS.md)**: a ccusage-style report of Copilot CLI tokens, GitHub's charges and estimated TokenMaster savings; its estimate and how it compares with measured A/B results.
- **Pre-registered studies in a replica harness.** PRS-1 to PRS-4 ran a Copilot-CLI-shaped agent with `gpt-6-astra`, not Copilot CLI itself. The PRS-4 agent's fixed prompt was about 3,600 tokens; the CLI itself sends about 13,500.
- **[PRS-4 results](PRS4_RESULTS.md)**: a pre-registered live study on 24 fresh tasks (360 sessions, 3 arms).
  - Under continuous use, v7 plus the cache-stable system prompt lowered billed cost per finished task by 49.8% against stock (95% CI −57.1% to −42.9%).
  - v7 alone lowered it by 18.2%. Every arm passed 120/120.
  - Today the native Copilot route and the Copilot CLI bridge (bring-your-own-model mode) apply the cache-stable system prompt.
- **[PRS-4 protocol](PRS4_PROTOCOL.md)**: the pre-registered design, goal rule and red-team fixes.
- **[PRS-5 protocol](PRS5_PROTOCOL.md)**: a pre-registered real-CLI study. It stopped after 10 of 32 sessions on October 18, 2026; its partial data are evidence, not a result.
- **[PRS-6 protocol](PRS6_PROTOCOL.md)**: the pre-registered study on Copilot CLI 1.0.98 itself, with `gpt-6-astra` and `claude-opus-5.5`, committed (`19443fc`) on October 26, 2026 before any study call. Its results are in [Copilot CLI results](COPILOT_CLI_RESULTS.md#pre-registered-study-prs-6-on-copilot-cli-1098-october-26-2026).
- **[PRS-3 results](PRS3_RESULTS.md)**: a pre-registered live study on 24 fresh tasks (480 sessions, 4 arms).
  - v7 graph-first navigation lowered cost by 22.0% against stock (95% CI −35.4% to −8.9%), with 120/120 passed.
  - v6 replicated at −13.0%.
  - v7's extra saving over v6 (−10.4%) is not significant.
- **[PRS-3 protocol](PRS3_PROTOCOL.md)**: the design, predictions and decision rules, plus the v7 freeze record and two code reviews.
- **[PRS-2 results](PRS2_RESULTS.md)** and **[protocol](PRS2_PROTOCOL.md)**: v6 lowered cost by 11.6% on 12 fresh tasks. The graph tools as shipped raised it by 12.9%.
- **[PRS-1 results](PRS1_RESULTS.md)**: a pre-registered live study on 12 real tasks (252 sessions, 7 arms).
  - No TokenMaster configuration significantly reduced total tokens.
  - `request-policy-v5` raised cache-weighted cost by 61.6%.
  - Every TokenMaster arm passed 36/36.
- **[PRS-1 protocol](PRS1_PROTOCOL.md)**: the design, arms, endpoints and decision rules, frozen before the run, plus every change made before it.
- **[Root README](../../README.md)**: overview, quickstart, the benchmark table and a summary of the proofs with the two commands that check them. The commands that reproduce the benchmark results are in [Copilot CLI results](COPILOT_CLI_RESULTS.md#reproduce).
- **[Proofs](../../proofs/README.md)**: TokenMaster's core rules stated as theorems about a model of the code and checked by Lean 4, a proof checker. It lists what each proof assumes, which of those assumptions the conformance tests check against the real Python and which remain assumptions, and the gaps that writing the proofs found, both fixed and open.
- **[Interactive deck](https://all-the-vibes.github.io/TokenMasterX/)**: the results, the proofs and the install steps on GitHub Pages. `site/src/build.py` generates it from `site/src` into `site/index.html` ([how to build and publish it](../../site/src/README.md)).
- **[Single-slide summary](../../docs/tokenmaster-v5-slide.html)**: a one-screen view of the October 18 to 22 exploratory runs on Copilot CLI 1.0.78-3, led by the 45-task Django run of October 22. Its TokenMaster arms used the lean tool set that `--lean` now turns on. Its figures predate PRS-6 (October 26) and the default-routing runs of October 27 and November 1, and the slide still lists default routing and a pre-registered study as not yet measured. [Copilot CLI results](COPILOT_CLI_RESULTS.md) and the [interactive deck](https://all-the-vibes.github.io/TokenMasterX/) have the current figures.
- **[Retracted: V5 isolated sandbox report](V5_ISOLATED_SANDBOX_SAVINGS_REPORT.md)**: why the October 17 numbers were withdrawn.
- **[Mission](../../MISSION.md)**: the thesis that the harness, the layer that decides what context the model sees on every call, is where token cost should be cut; how raw tokens and billed cost are counted; and what TokenMaster builds: the opt-in lean tool set, one system prompt per folder in bring-your-own-model mode, graph navigation (v7) and one-time v6 shaping. Recall across sessions is listed too, but it is still an idea that no study has measured.
- **[Changelog](../../CHANGELOG.md)**: chronological release and engineering log.

---

## 2. Core Engine, Guards & Mathematical Contracts

- **[Product Runtime Architecture](PRODUCT_RUNTIME.md)** — How `RuntimeSession` connects request planning (`prepare_request`), `CCR` SQLite recovery (`recovery.sqlite`), non-expanding wire guards, and `TokenLedger`.
- **[Token Efficiency & Promotion Gate](TOKEN_EFFICIENCY.md)** — Formal reference-token accounting (`cl100k_base`), quality-normalized cost per verified success, and statistical promotion rules.
- **[Document Structure Guard](DOCUMENT_STRUCTURE_GUARD.md)** — Code-point parser and preservation invariants for Markdown pipe tables, ordered lists, and fenced code blocks.
- **[Source Read Guard](SOURCE_READ_GUARD.md)** — Executor-bound SHA-256 read receipts (`SourceReadInfo`) preventing unverified text from being treated as recoverable file reads.
- **[Objective Savings Verification](OBJECTIVE_SAVINGS.md)** & **[Evaluation Protocol](EVALUATION_PROTOCOL.md)** — Offline recount, paired-order randomization, and invariant checking rules.
- **[Verification Matrix](VERIFICATION.md)** — Complete map of unit, integration, and qualifier test suites.
- **[Jev Advisory Screening Contract](JEV_CONTRACT.md)** & **[Plan Feasibility](PLAN_FEASIBILITY.md)** — Read-only feasibility checks and bounds for candidate policy search.

---

## 3. Host Adapters, Sandbox Isolation & Research Provenance

- **[Native Copilot Full Runtime](NATIVE_FULL_RUNTIME.md)** — `brainspace_tools.py native-copilot` bridge connecting `copilot.exe` in a Windows Job Object to `RuntimeSession`.
- **[Native Copilot Hook](NATIVE_COPILOT_HOOK.md)**: the Copilot CLI `postToolUse` hook on `view` results. Its October 9 lifecycle run verified the earlier JSON whitespace version. Since October 18, 2026 the hook applies `request-policy-v6` to whole-file views, and `brainspace_setup.py --host copilot` installs it by default. `--no-copilot-output-hook` skips it, and so does `disableAllHooks` in the Copilot settings.
- **[Native Envelopes (Claude Code & Copilot)](NATIVE_ENVELOPES.md)** & **[Host Contract](../evals/hosts/CONTRACT.md)** — Host tool envelope schemas and bypass rules.
- **[Windows Isolation Feasibility](WINDOWS_ISOLATION_FEASIBILITY.md)** — Windows Job Object, profile redirection, and loopback proxy isolation design.
- **[Harness Command Design (superseded)](../../docs/history/harness-command-design.md)**: the original May 2026 design of the `/token-master` command, kept for history.
- **[Token-Efficient Harness Research (superseded)](../../docs/research/token-efficient-harness-research.md)** & **[Research Provenance](RESEARCH_PROVENANCE.md)**: literature review and external tool audits (`Graphify`, `CodeGraph`, `Headroom`, `Ponytail`).

---

## 4. Historical Lab Archive (`v1`–`v4` Iterations)

All earlier experiments—including negative and neutral trials that motivated `request-policy-v5`—are preserved unchanged for auditability:

- **[Conservative V3 Policy (`request-policy-v3`)](CONSERVATIVE_POLICY_FIX.md)** — Exact duplicate-read reuse (`9.9%` on forced repeats, `0%` on unique reads).
- **[Lexical JSON V4 Policy (`request-policy-v4`)](LEXICAL_JSON_POLICY.md)** & **[V4 Results](LEXICAL_JSON_RESULTS.md)** — Lossless JSON whitespace compaction (`1.43%` whole-suite reduction).
- **[Native Document Results](NATIVE_DOCUMENT_RESULTS.md)**, **[Native Ranged Results](NATIVE_RANGED_RESULTS.md)**, & **[Native Ranged Live Results](NATIVE_RANGED_LIVE_RESULTS.md)** — Pre-`v5` Headroom document-only trials showing why unguarded table/list loss caused extra re-reads.
- **[Guarded Runtime Results](GUARDED_RUNTIME_RESULTS.md)**, **[Parity Runtime](PARITY_RUNTIME.md)**, **[Parity Analysis](PARITY_ANALYSIS.md)**, **[Integration Parity Status](INTEGRATION_PARITY_STATUS.md)**, & **[Comparator Results](COMPARATOR_RESULTS.md)** — Earlier Headroom + Ponytail parity benchmarks.
- **[Profile Learning](PROFILE_LEARNING.md)**, **[Refinement Experiment](REFINEMENT_EXPERIMENT.md)**, & **[Refinement Results](REFINEMENT_RESULTS.md)** — Bounded hill-climbing controller studies across `v1`–`v4`.
- **[Controlled Scorecard](CONTROLLED_SCORECARD.md)**, **[Integrated Runtime Scorecard](INTEGRATED_RUNTIME_SCORECARD.md)**, **[Coding Validation](CODING_VALIDATION.md)**, **[Implementation Plan](IMPLEMENTATION_PLAN.md)**, **[Active Evaluation Goal](ACTIVE_EVALUATION_GOAL.md)**, & **[October 16, 2026 Working Handoff](HANDOFF-2026-10-16.md)**.
