---
name: token-master-review
description: A task-local, bounded review for unnecessary complexity in a specified change or component. Use when explicitly requested; preserve required abstractions, safety and user-requested depth.
---

# Bounded complexity review

Review only the named change or component. Default to findings, not edits; an
explain-only request authorizes no filesystem changes. This invocation does not
enable a persistent session mode or authorize a repository-wide audit.

1. Establish a compact task contract: **required result, non-goals, evidence,
   stop condition, advisory output-token budget**. Use the request and existing
   context; ask only if an ambiguity materially changes scope or safety.
2. Read the changed code, its direct callers and relevant tests. Identify
   concrete unnecessary behavior, duplicated existing functionality or speculative
   infrastructure. Do not equate fewer lines with better maintainability.
3. Preserve explicitly requested reusable abstractions, architecture, deep proofs,
   safety checks and required evidence. Recommend the smallest justified fix,
   not an unrelated rewrite. Do not add dependencies to simplify a local review.
4. Report actionable findings with file/line evidence, impact and a bounded
   alternative. If editing was requested, lock affected behavior with regression
   tests, make focused edits and run the relevant checks.
5. Stop after the agreed scope is reviewed and required verification is complete.
   State gaps rather than extending into optional audits, debt inventories or
   token-saving claims. Retain requested detail and safety caveats over the budget.

Task-local invocation and session enable/off/status are different operations.
Session persistence, if supplied by the host integration, must use an explicit
session key; off removes only that session's mode state. Recorded state does not
prove model obedience, quality improvement or automatic request interception.
