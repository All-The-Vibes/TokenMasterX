# TokenMaster Documentation Index

This directory contains the architecture specifications, mathematical contracts, live benchmark reports, and historical iteration archive for TokenMaster. Every markdown document in the repository is indexed below.

---

## 1. Start Here: Current Evidence

- **[PRS-4 results](PRS4_RESULTS.md)**: v7 plus a cache-stable system prompt, 360 sessions, 3 arms; −49.8% per finished task under continuous use.
- **[PRS-4 protocol](PRS4_PROTOCOL.md)**: the pre-registered design, goal rule and red-team fixes.
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
- **[Root README](../../README.md)**: overview, results table and reproduction commands.
- **[Single-slide summary](../../docs/tokenmaster-v5-slide.html)**: a one-screen view of the PRS-4 results.
- **[Retracted: V5 isolated sandbox report](V5_ISOLATED_SANDBOX_SAVINGS_REPORT.md)**: why the October 17 numbers were withdrawn.
- **[Mission & Thesis](../../MISSION.md)**: the spatial (graph routing) and temporal (context compaction) thesis.
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
- **[Native Copilot Hook](NATIVE_COPILOT_HOOK.md)** — Explicit `postToolUse` JSON view hook contract.
- **[Native Envelopes (Claude Code & Copilot)](NATIVE_ENVELOPES.md)** & **[Host Contract](../evals/hosts/CONTRACT.md)** — Host tool envelope schemas and bypass rules.
- **[Windows Isolation Feasibility](WINDOWS_ISOLATION_FEASIBILITY.md)** — Windows Job Object, profile redirection, and loopback proxy isolation design.
- **[Dual-Host Installer Plan](../../DUAL_HOST_PLAN.md)** & **[Harness Command Design](../../harness-command-design.md)** — Symmetric setup for Claude Code (`~/.claude`), GitHub Copilot CLI (`~/.copilot`), and Codex (`~/.codex`).
- **[Token-Efficient Harness Research](../../token-efficient-harness-research.md)** & **[Research Provenance](RESEARCH_PROVENANCE.md)** — Literature review and external tool audits (`Graphify`, `CodeGraph`, `Headroom`, `Ponytail`).

---

## 4. Historical Lab Archive (`v1`–`v4` Iterations)

All earlier experiments—including negative and neutral trials that motivated `request-policy-v5`—are preserved unchanged for auditability:

- **[Conservative V3 Policy (`request-policy-v3`)](CONSERVATIVE_POLICY_FIX.md)** — Exact duplicate-read reuse (`9.9%` on forced repeats, `0%` on unique reads).
- **[Lexical JSON V4 Policy (`request-policy-v4`)](LEXICAL_JSON_POLICY.md)** & **[V4 Results](LEXICAL_JSON_RESULTS.md)** — Lossless JSON whitespace compaction (`1.43%` whole-suite reduction).
- **[Native Document Results](NATIVE_DOCUMENT_RESULTS.md)**, **[Native Ranged Results](NATIVE_RANGED_RESULTS.md)**, & **[Native Ranged Live Results](NATIVE_RANGED_LIVE_RESULTS.md)** — Pre-`v5` Headroom document-only trials showing why unguarded table/list loss caused extra re-reads.
- **[Guarded Runtime Results](GUARDED_RUNTIME_RESULTS.md)**, **[Parity Runtime](PARITY_RUNTIME.md)**, **[Parity Analysis](PARITY_ANALYSIS.md)**, **[Integration Parity Status](INTEGRATION_PARITY_STATUS.md)**, & **[Comparator Results](COMPARATOR_RESULTS.md)** — Earlier Headroom + Ponytail parity benchmarks.
- **[Profile Learning](PROFILE_LEARNING.md)**, **[Refinement Experiment](REFINEMENT_EXPERIMENT.md)**, & **[Refinement Results](REFINEMENT_RESULTS.md)** — Bounded hill-climbing controller studies across `v1`–`v4`.
- **[Controlled Scorecard](CONTROLLED_SCORECARD.md)**, **[Integrated Runtime Scorecard](INTEGRATED_RUNTIME_SCORECARD.md)**, **[Coding Validation](CODING_VALIDATION.md)**, **[Implementation Plan](IMPLEMENTATION_PLAN.md)**, **[Active Evaluation Goal](ACTIVE_EVALUATION_GOAL.md)**, & **[October 16, 2026 Working Handoff](HANDOFF-2026-10-16.md)**.
