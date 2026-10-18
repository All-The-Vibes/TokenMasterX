# PRS-2 pre-registration: does cache-native TokenMaster (v6) lower real cost?

**Written:** October 18, 2026, before any PRS-2 study call.
**Frozen by:** SHA-256 of this file, `evals/run_prs2_study.py`, the shared
`evals/run_prs1_study.py`, `evals/prs2_tasks.json` and every product source the run
uses (including `brainspace/v6_shaping.py`). All are recorded in `protocol.json`.
The run refuses to start if any of them changed after `prepare`.

## Why this study exists

[PRS-1](PRS1_RESULTS.md) found that no TokenMaster configuration reduced tokens.
v5 raised cache-weighted cost by 61.6%, because it rewrote history the provider had
already cached.

Two findings shape this study.

**Where the cost of stock PRS-1 sessions went** (cached input priced at 10% of
uncached input, output priced at 8×):

| Cost component | Share of cost |
| --- | ---: |
| New tool output, paid at full price once | about 38% |
| Uncached first-call prefix (system prompt and tools) | 19% |
| Cached re-reads of earlier messages | 24% |
| Output tokens | 18% |

Of the new tool-output tokens, 82% came from results longer than 1,000 tokens.
Exact duplicate reads made up 0%.

**How this provider caches** (a 5-call probe): it caches exact prefixes. The cache
key makes no difference. Changing any earlier message drops the cache from that
point on.

## Treatment: `request-policy-v6`

- **Deterministic shaping.** Each tool result is shaped by a pure function of
  (tool name, arguments, content). It produces the same bytes on every later
  request, so history never changes and the provider's cache stays valid.
- **Lossless folding.** Search output is grouped by file, and path lists are
  grouped by directory.
- **Budgets** (cl100k tokens):
  - search and list results: 1,500
  - full file reads: 4,000
  - all other tools: 3,000

  A result over budget becomes a digest that states what was omitted and how to
  fetch it. Every tool notice (for example "[File truncated ...]") is kept verbatim.
  Ranged reads, forced reads, explicit `head_limit` searches and error results are
  never shortened.
- **Per-message acceptance.** A shaped result is used only if it is strictly smaller
  on its own, so whether a message is shaped never depends on the rest of the
  request.
- **No prompt guidance.** v6 cannot be combined with prompt guidance such as
  Ponytail, because guidance inserted mid-session would shift cached history.
- **Nothing hidden, nothing added.** v6 hides nothing that cannot be re-fetched,
  so it adds no recovery tool and no instructions.
- **Parallel tool calls** are allowed through a new transport flag. The default is
  unchanged.
- **Tuning disclosure.** The budgets were chosen from PRS-1 development data. An
  offline replay cut new tool-output tokens by 32%. That makes the PRS-1 tasks
  "exposed" for v6, so the confirmatory analysis uses 12 new tasks.

## Arms

| Arm | Description |
| --- | --- |
| `stock` | Copilot-CLI-shaped agent with parallel tool calls and no TokenMaster. This is the realistic reference. |
| `tm6` | `stock` plus the TokenMaster runtime with `request-policy-v6`. |
| `tm6_graph` | `tm6` plus the `graphify-nav` and `codegraph` MCP tools and the shipped routing agent text. |

## Realism changes from PRS-1

- **Same working directory.** Every session sees the same logical working directory
  (`C:\work\tokenmaster`), mapped to its own private copy, as repeat sessions in one
  repository do. The session-folder line stays unique per session, as Copilot CLI
  writes it.
- **Parallel tool calls everywhere.** Every arm uses parallel tool calls, as stock
  Copilot CLI does.

## Tasks

- **Primary (confirmatory):** 12 new tasks, N01–N12. They were written by a separate
  agent session that was not told the arms or the purpose of the study, and each
  answer was then verified independently. The quota is 3 locate, 3 logic, 2 impact,
  2 docs and 2 edit tasks.
- **Secondary (exposed):** the 12 PRS-1 tasks, T01–T12, reported separately.

Grading and the oracle are unchanged from PRS-1.

## Schedule

24 tasks × 3 arms × 3 repeats = **216 sessions**. Each repeat block is shuffled
with seed `20261019 + repeat`, and the run uses 8 concurrent workers.

## Endpoints

- **Primary:** cost per session on the primary task set, computed from
  provider-reported usage as
  `cost = uncached input + 0.1 × cached input + 8 × output`.
  This matches GPT-5-class list-price ratios.
- **Secondary:**
  - cost with the cached weight raised to 0.25
  - cost with the output weight lowered to 4
  - cost plus a 0.25× premium on cache writes
  - raw tokens (input + output)
  - uncached input
  - number of model calls
  - success rate
  - per-category totals

## Analysis

The analysis machinery is the same as PRS-1:

- A pair is one (task, repeat) where both sessions completed.
- The change is measured as a ratio of sums over pairs.
- 95% confidence intervals come from a two-stage cluster bootstrap with 10,000
  resamples.
- Significance uses an exact Wilcoxon test on per-task means.
- Holm correction is applied across the 3 comparisons (tm6 vs stock,
  tm6_graph vs stock, tm6_graph vs tm6) on the primary endpoint within the
  primary set.
- The secondary set gets the same tests, with its own Holm correction, and is
  labeled exposed.

## Verdict rules

- **"Lower cost":** the CI upper bound is below 0 and the Holm-adjusted p is below 0.05.
- **"Higher cost":** the CI lower bound is above 0 and the Holm-adjusted p is below 0.05.
- **Otherwise:** "no significant cost difference".
- **Quality:** a cost result counts as "at equal quality" only when the arm's paired
  pass count is at least the reference's.

**TokenMaster "works"** only if `tm6` or `tm6_graph` shows "lower cost" against
`stock` on the primary set, at equal quality. The point estimate and CI are judged
against the goal of at least 30% savings; the goal is never assumed to be met.

## Failures and exclusions

These rules are the same as PRS-1:

- Infrastructure failures are re-run once, regardless of arm.
- Every other failure counts, with all of its tokens.
- Calls without provider-reported usage are estimated and flagged.
- There are no selective re-runs.
- Token cap: 60M.

## Predictions recorded before the run

- **`tm6` vs `stock`:**
  - cost between −8% and −20%
  - raw tokens lower
  - model calls similar or slightly higher, because narrower re-queries cost calls
  - equal quality
- **`tm6_graph` vs `stock`:** cheaper on impact tasks and more expensive elsewhere;
  the overall direction is uncertain.
- **Secondary set:** the same directions.

## Limitations

1. One model, one repository and 24 tasks.
2. The harness is shaped like Copilot CLI but is not `copilot.exe`.
3. The cost weights are assumptions. GitHub Copilot subscriptions bill premium
   requests, not tokens.
4. The v6 budgets were tuned on PRS-1 data. This is why the primary set is new.
5. The author of v6 also built this harness. Mitigations: blind tasks, this
   pre-registration, frozen hashes, an independent review, raw captures for every
   call, and an analysis that recounts every token from those captures.
6. The native Copilot transport still forces sequential tool calls. v6 is tested
   only through the controlled harness.

## Smoke test

One dummy task per arm checks the mechanics. It is not analyzed. If any change
follows, `prepare` is re-run and the change is disclosed.

## Checks and changes before the run

- **Task verification.** Every N01–N12 answer was re-derived from the snapshot.
  N04, N05 and N06 were checked by executing the snapshot's own code. N06 gives the
  same result whether or not its `D:` paths exist.
- **Independent review.** Two `oracle` review attempts returned no text. A
  `cavecrew-reviewer` then reported 1 critical issue and 10 risks, and found nothing
  wrong in the cost formula, CI orientation, Holm correction, paired passes or
  imports. These were fixed before freezing:
  - Digests now keep tool notices. The critical issue was that tm6 could not see a
    file continued past the 20KB cut.
  - Search folding takes headers only from real match paths, so context lines can no
    longer invent files.
  - `fold_paths` refuses to fold anything it cannot keep exactly.
  - Outlines skip indented comments, use headings only for docs, mark cut lines
    `[cut]` and say where they stop.
  - Digest notes count files accurately and state exact omitted spans.
  - Per-message acceptance, as described in the treatment section.
  - v6 rejects prompt guidance.
  - Tool errors never reveal the private workspace path (which names the arm).
- **Not changed:** errors are detected by their `Error` prefix, which every harness
  error has. Whether `copilot.exe` numbers full-file views is unknown, because this
  harness returns raw text for them.
- **Development estimate after the fixes:** replaying PRS-1's stock sessions shows
  33% fewer new tool-output tokens. This is a mechanism estimate, not a result.
