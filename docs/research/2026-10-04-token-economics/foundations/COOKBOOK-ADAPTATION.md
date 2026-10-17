# Jev feature discovery: precedent and proposed adaptation

**Reviewed October 4, 2026. No cookbook execution or API calls.**

## Observed precedent

TypeSafe's official autoresearch cookbook generates/revises/drops questions,
uses Jev probabilities as features, and retrains CatBoost on labeled data.
Development cross-validation drives changes; a separate test split reports
results. The example pins `jev-1.12`, not the current documented `jev-1.13.0`.
Its `try_change` accepts `cv_trial <= cv + tolerance`. This is empirical
feature search, not a continual-improvement theorem.

Primary source:
`https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery`

Relevant code anchors are `TYPESAFE_MODEL`, `Split.dev` / `Split.test`,
`encode`, and `try_change`. Documentation-rendering line numbers can change;
this is a live documentation reference, not an immutable repository snapshot.

## Proposed TokenMaster adaptation

Let \(w\) denote fixed Jev weights and \(v\) the fixed target model. Use a
configurable question set \(\theta\) to form:

\[
z_\theta(x)=\operatorname{Jev}_w(x;\theta).
\]

Combine those semantic features with exact code-derived facts:

```text
task kind and declared output requirements
content type, exact length and token estimates
whether source text will be edited verbatim
tool exit status and structured error fields
graph/source version and coverage
cache state and current remaining budget
retrieval availability and scope
```

An external policy \(g_\beta\) chooses only among permitted actions:

\[
a=g_\beta(z_\theta(x),\text{exact features}).
\]

Search can change the questions, thresholds/rules, and representations
without changing either foundation model. A separately trained small
predictor is optional. If the requirement is **no additional model training
at all**, use explicit thresholds and rules for \(g_\beta\).

Candidate questions should be narrow—for example, whether the task appears
to need verbatim text versus a structural view. Code, not Jev, calculates
costs/counts, checks applicability, preserves protected fields, and enforces
permissions. A predicted semantic label does not override these controls.

Build search labels from full-task outcomes under allowed actions:
correctness, complete runtime cost, restoration need, and latency. Do not
define “best action” solely as whatever Jev prefers. A learned predictor is
a search accelerator, not a certificate.

Every changed question set or rule is a new candidate policy. Evaluate the
**complete policy**, including feature-extraction costs, before promotion.
A better predictor score does not automatically imply a better task outcome.

## Separate three data roles

1. **Search/training:** reusable for proposing, fitting and ranking.
2. **Confirmation:** fresh or accessed through a separately justified
   adaptive-inference protocol; decides promotion.
3. **Audit/monitoring:** detects failures and drift; must not silently be
   called an untouched final test after repeated adaptive use.

The acceptance rules are in
`C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\foundations\PROOFS-AND-CONTINUOUS-IMPROVEMENT.md`.

## First experiment

Use a small discrete action space and already-verified transformations.
Compare a fixed deterministic router with Jev-assisted routing. Predeclare
the workload, versions, oracle, cost cap, evaluation budget and decision rule.
Start in isolated evaluation, not automatic production-policy replacement.

This is a proposal. No routing advantage, calibration accuracy, deployment
savings, or model-quality improvement was measured here.
