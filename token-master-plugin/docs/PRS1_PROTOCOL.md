# PRS-1 pre-registration: does TokenMaster reduce tokens on real coding tasks?

**Written:** October 18, 2026, before any study model call.
**Frozen by:** the SHA-256 of this file, the harness (`evals/run_prs1_study.py`) and
the task file (`evals/prs1_tasks.json`), all recorded in the run's `protocol.json`.

## Why this study exists

The October 17 benchmark claims (for example "−83.29%", "−73.19%", "−65.68%") are
**retracted**. Their design inflated savings:

1. Synthetic modules padded with 238 repetitive lines per function, so compaction
   removed ~99% of each file. Real repository files compact ~77% per file.
2. Non-graph arms were told to read 7 files in a fixed order, including decoys.
3. Questions asked only for top-level constants, and the prompt told the model not
   to call recovery.
4. Baseline arms also received two unused recovery tools.
5. The first Headroom adapter never compressed anything; the second overrode
   Headroom's defaults (`exclude_tools`).
6. Prompt caching was ignored. Baseline input was 99.9% cached (prefixes warmed by
   an identical earlier run), while v5 rewrites earlier messages and breaks the cache.

## Question

On real tasks in a real repository, does each TokenMaster component use fewer
provider-reported tokens than an unoptimized agent, at equal task success? How do
Headroom and Ponytail compare under the same conditions?

## Design

- **Model:** `gpt-6-astra` via `https://api.githubcopilot.com/responses`, reasoning
  effort `low`, at most 4,096 output tokens per call and 30 model calls per session.
  Requests are stateless (`store: false`) and carry a per-session `prompt_cache_key`,
  as GitHub Copilot CLI sends.
- **Workspace:** `git archive` of commit `703aa20` paths
  `token-master-plugin/skills/token-master` and `token-master-plugin/docs`
  (201 files, 2.8 MB, real unmodified code and docs). Every session gets a private copy.
- **Harness:** one agent loop for every arm. The base system prompt is the real
  GitHub Copilot CLI 1.0.98 system prompt captured on October 17, 2026, adapted only
  for the session's working directory and session folder, and `apply_patch` → `edit`.
  Base tools: Copilot CLI's captured `view` schema, plus `grep`, `glob` and `edit`
  modeled on Copilot CLI. No shell tool for any arm.
- **Accounting:** every arm runs through TokenMaster's `RuntimeSession`, so capture
  and accounting are identical. Arms without TokenMaster use `RuntimePolicy()` (off),
  which submits requests unchanged.
- **Intent:** `conservative` for every task. This is the production default. No arm
  receives task-type information.

## Arms

| Arm | Difference from baseline |
| --- | --- |
| `baseline` | None. `parallel_tool_calls: false`, held constant for all arms except the next. |
| `baseline_parallel` | `parallel_tool_calls: true` (stock Copilot CLI behavior). Measures the effect of TokenMaster's transport forcing `false`. |
| `ponytail` | Pinned Ponytail ruleset (export of commit `c982cd4`, mode `full`) appended to the system prompt, the way its plugin injects it every turn. |
| `headroom` | Requests pass through `headroom proxy` v0.41.0 with default mode (cache) and default tool exclusions. Telemetry, update checks and downloads are disabled. |
| `graph` | Real `graphify-nav` and `codegraph` MCP servers on prebuilt indexes, exposed with Copilot CLI's `<server>-<tool>` naming, plus the shipped routing agent text appended to the system prompt. |
| `v5` | TokenMaster runtime with `request-policy-v5` (`keep_recent_tool_results=1`, `min_tool_chars=256`, `max_transforms=12`, non-expanding input guard). The runtime adds `retrieve_original` itself. |
| `graph_v5` | `graph` plus `v5`. |

## Tasks

Twelve tasks were authored by a separate agent session that was not told the arms or
the purpose of the study. The category quota was 3 locate, 3 logic, 2 impact, 2 docs
and 2 edit. Expected answers were derived from the snapshot and then verified
independently. Grading is deterministic:

- Question tasks: the first top-level JSON object in the final message that contains
  an expected key. Every expected key must match. Pre-declared normalization:
  - Surrounding whitespace, quotes and backticks are stripped.
  - Strings compare case-insensitively.
  - Paths compare relative to the repository root with `/`. A different root is
    accepted only when the shorter path still has at least two components.
  - A trailing `()` or a module prefix on a bare function name is ignored.
  - Numeric and boolean strings are accepted.
  - Lists are ordered unless declared unordered.
  - Changing any file during a question task fails it.
- Edit tasks: the edited files must equal the expected source at Python AST level
  (JSON by value), and no other file may change. No generated code is executed.

## Schedule

3 repeats × 12 tasks × 7 arms = **252 sessions**. Each repeat block is shuffled with
seed `20261018 + repeat`, and runs with 8 concurrent workers.

## Endpoints

- **Primary:** provider-reported `input_tokens + output_tokens` per session, summed
  over every call, including failed tasks.
- **Secondary:** uncached input, cached input, cache-weighted tokens
  (`uncached + w × cached + output`, `w = 0.1` and `w = 0.5`), output tokens, model
  calls, success rate, and tokens per successful task.

## Analysis

- A pair is a (task, repeat) where both sessions completed (pass or fail).
- Change = `1 − Σ arm / Σ reference` over pairs.
- 95% CI: two-stage cluster bootstrap (tasks, then repeats within a task), 10,000
  resamples, fixed seed.
- Test: exact Wilcoxon signed-rank test on per-task mean differences, Holm-adjusted
  across 7 pre-declared comparisons: each of the 6 other arms against `baseline`, and
  `graph_v5` against `graph`.
- **Verdict rules:**
  - "Fewer tokens" only if the CI lower bound is above 0 and Holm p < 0.05.
  - "More tokens" only if the CI upper bound is below 0 and Holm p < 0.05.
  - Otherwise, "no significant difference".
- Success counts are always reported. A saving counts as "at equal quality" only if
  the arm's passes are at least the reference's.

## Failures and exclusions

- **Infrastructure failures:** HTTP 429/5xx, or no provider response after the
  gateway's retries. These are re-run once at the end, whatever the arm. A failure
  that persists is excluded pairwise and reported.
- **Everything else counts as a task failure, with all its tokens:** wrong answers,
  missing JSON, call-cap exhaustion, provider 4xx (for example context overflow),
  component or harness errors. A submitted call without provider usage is counted
  with the cl100k size of its request, flagged as an estimate, never as zero.
  Failure reasons are reported per arm.
- **Gateway:** retries only HTTP 429/5xx and network errors. Total budget is 70 s,
  and no retry starts after 30 s, which keeps it inside the client's 90 s timeout.
  Every upstream attempt is logged per arm.
- **Warm-up:** before the first session, each arm's endpoint receives one tiny
  request ("Reply with OK."). It is logged but not counted. The study aborts if any
  warm-up fails. Headroom gets 60 s after its health check to finish its background
  model warm-up.
- **Budget stop:** 80M provider tokens. Sessions not run are reported.
- **No selective re-runs.** Results are never re-run in place.

## Predictions recorded before the run

- `v5`: fewer raw tokens. A smaller or reversed effect on cache-weighted tokens,
  because it rewrites earlier messages. Possible extra calls on edit and logic tasks.
- `graph`: a small effect either way. `codegraph_explore` returns verbatim source.
- `headroom`: about zero, because its defaults pass `view` output through verbatim.
- `ponytail`: slightly more tokens from instruction overhead.
- `baseline_parallel`: fewer calls and tokens than `baseline`.

## Limitations declared in advance

1. One model, one repository, 12 tasks. The results are not representative of all work.
2. The harness is shaped like Copilot CLI but is not `copilot.exe`. The native
   harness exposes only `view`, so search and edit would be impossible there.
   Reasoning items are not replayed between turns (same in every arm).
3. Graph arms keep the `edit` tool (the shipped agent restricts tools to
   read/search/execute) and do not see `graphify-out/` (`setup.py` leaves it in place).
   codegraph 1.6.2 lists only `codegraph_explore`, although the agent text names 8 tools.
4. GitHub Copilot subscriptions bill premium requests, not tokens. Token results
   matter for per-token API billing, context limits and rate limits.
5. The author of `request-policy-v5` also built this harness. Mitigations: blind task
   authoring, this pre-registration, a deterministic oracle, raw captures for every
   call, and an analysis that recounts tokens from the raw captures.
6. v5 compacts only `view` results that the runtime binds as source reads. `grep`,
   `glob` and MCP outputs (including `codegraph_explore`, which returns source) are
   never compacted. v5's exact-reuse step lists only `read_file` and `fetch_artifact`
   (`exact_reuse._TOOLS`). A duplicate `view` is therefore compacted lossily instead
   of being replaced by an exact-reuse marker. Both are tested as implemented, not fixed.
7. One `headroom proxy` instance serves every Headroom session concurrently, the way
   a user runs it.

## Checks and changes before the study run

- **Draft smoke run** (7 dummy sessions in a discarded draft directory) found a
  thread race in the tokenizer's lazy load. Fix: the tokenizer loads once before
  worker threads start.
- **Headroom mechanism probe** (offline; a fake upstream records what the real proxy
  forwards; no model calls):
  - `view` output passes through byte-identical, for both code and JSON.
  - `grep` JSON is folded losslessly (47,163 → 24,655 characters); `grep` code is unchanged.
  - A non-excluded tool (`fetch_data`) is compressed: code 24,000 → 9,349 and
    JSON 47,163 → 17,217 characters.
  - Compressed bytes are identical on the newest and later turns.
  - So Headroom is active on `/v1/responses`. A near-zero effect in this study would
    reflect its defaults, not a broken adapter.
- **Independent red-team review** of the harness, before any study call. The fixes are:
  - Ponytail is moved from a runtime-inserted user message to the system prompt.
  - Failed calls are counted with an estimate instead of 0.
  - The gateway budget is cut from 85 s to 70 s.
  - Grading uses top-level JSON only, the stricter path rule and case-insensitive
    strings, and fails question tasks that edit files.
  - Wilcoxon ties are computed float-safe.
  - Verdicts use paired pass counts.
  - MCP pipe errors become tool errors, MCP process trees are killed on close, and
    workspace cleanup handles read-only files.
- **Not changed:** the product's v5 code, even where the review found gaps (limitation 6).

## Smoke test

One dummy task per arm, which is not in the task set, checks mechanics before the
run. Its results are not analyzed. If any harness change follows, `prepare` is
re-run into a new directory and the change is disclosed.
