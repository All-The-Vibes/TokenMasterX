# PRS-3 pre-registration: does graph-first TokenMaster (v7) lower cost further?

**Written:** October 18, 2026, before any PRS-3 study call.
**Frozen by:** `prepare` records the SHA-256 of all of the following in `protocol.json`:

- this file
- the harness `evals/run_prs3_study.py`, plus the shared `evals/run_prs1_study.py` and
  `evals/run_prs2_study.py`
- the task file `evals/prs3_tasks.json`
- every product module a session can import (`brainspace/**/*.py` except tests, and
  `graphify_mcp.py`)
- the navigation index built for the study (graphify's `graph.json` and `symbols.sqlite`)
- the visible workspace of both templates

`smoke` and `run` refuse to start if any of them changed after `prepare`.

## Why this study exists

[PRS-2](PRS2_RESULTS.md) showed two things:

- `request-policy-v6` lowers cost by 11.6% on fresh tasks, at equal quality.
- Graph tools as shipped *raise* cost by 12.9%. Every call carried six tool definitions
  (1,165 tokens) and a 1,383-token routing text, and `codegraph_explore` returned source
  dumps of about 5,000 tokens.

## Treatment: v7, graph-first navigation (`brainspace/symbol_index.py`)

- **Two sources of facts.**
  - A local SQLite index, built with the standard library, supplies the symbols: Python
    classes, functions, methods and constants (via `ast`), Markdown sections and JSON keys.
    Each symbol has its exact line range, a one-line signature and its token size.
  - graphify's graph supplies resolved call edges.
  - The index re-parses changed files on every call, so edits are seen at once.
- **Three compact tools**, with terse descriptions (269 tokens in total):
  - `locate(query)` returns `path:lines kind name ~tokens | signature`, or a file's outline.
  - `read_symbol(target)` returns exactly one symbol, file or line range, with line
    numbers. Anything that would exceed 2,400 tokens is shortened:
    - a symbol or range returns its first lines plus a list of its members;
    - a whole file returns its outline.
  - `impact(symbol, depth)` lists callers:
    - Call sites resolved by graphify's call graph come first, unmarked; graph guesses
      are marked `[inferred]`.
    - Call sites the graph missed are always added, found by name and marked `[name]`.
    - Calls on objects of unknown type are counted instead of listed when a name has
      more than 25 of them.
    - Graph edges from files edited since the graph was built are dropped, because their
      line numbers are stale; name matches cover those files.
    - Test callers come last.
- **Results always fit.** Every result stays under 2,400 tokens, so v6 never cuts one.
  v6 cuts results of unfamiliar tools above 3,000 tokens.
- **No source dumps and no routing essay.** A two-sentence hint (66 tokens) is appended
  to the system prompt.
- **v6 shaping still applies** to every tool result, and grep, glob, view and edit
  remain available.

## Arms

| Arm | Description |
| --- | --- |
| `stock` | Copilot-CLI-shaped agent with parallel tool calls and no TokenMaster |
| `tm6` | `stock` plus `request-policy-v6` (the PRS-2 winner) |
| `tm6_hint` | `tm6` plus one sentence of the same advice tm7's hint gives, without the tools (24 tokens): "Whole-file views and broad grep cost far more tokens than targeted searches and ranged views; read only what the task needs." |
| `tm7` | `tm6` plus the three navigation tools and their two-sentence hint |

`tm6_hint` is an attribution arm. It separates the tools from the advice that comes with
them.

Everything else is unchanged from PRS-2: the logical working directory, system prompt,
base tools, oracle, gateway, retries and warm-up.

## Tasks

- 24 new tasks, M01–M24, all confirmatory. Two separate agent sessions wrote them
  (M01–M12 and M13–M24).
  - Neither session was told about the arms or the purpose of the study.
  - Both sessions were told to avoid the 24 topics used by PRS-2.
  - The second session was also told to avoid the topics of the first.
- The quota is 6 locate, 6 logic, 4 impact, 4 docs and 4 edit tasks.
- Every expected answer is verified independently before `prepare`.
- The PRS-2 tasks are not reused. The v7 design drew on tool usage seen on them, so they
  are exposed.

## Schedule

24 tasks × 4 arms × 5 repeats = **480 sessions**.

- Each repeat block is shuffled with seed `20261020 + repeat`.
- The run uses 8 concurrent workers.
- PRS-2 used 7.5M tokens for 217 sessions, so the 60M token cap is far above the expected
  use.

## Endpoints and analysis

The endpoints are identical to PRS-2:

- **Primary endpoint:** `cost = uncached input + 0.1 × cached input + 8 × output` per session.
- **Secondary endpoints:** cost with the cached weight at 0.25; cost with the output
  weight at 4; cost with a 0.25× cache-write premium; raw tokens; uncached input; model
  calls; success rate.
- **Statistics:** pairs, ratio of sums, a two-stage cluster bootstrap 95% CI (10,000
  resamples), and an exact Wilcoxon test on per-task means. The Wilcoxon test is computed
  by dynamic programming and gives the same p-values as the PRS-1/PRS-2 code.
- **Holm correction**, applied within each family:
  - **Primary family:** `tm6` vs `stock`, `tm7` vs `stock`, `tm7` vs `tm6`.
  - **Attribution family:** `tm6_hint` vs `tm6`, `tm7` vs `tm6_hint`.

### Diagnostics

These are reported, but no verdict depends on them:

- the share of each arm's first-call input that was served from cache, which checks that
  prompt caching treats the arms alike;
- navigation tool calls per session, which shows whether the model actually used the tools.

## Verdict rules and success criteria

The verdict rules are unchanged from PRS-2:

- **"Lower cost":** the CI upper bound is below 0 and the Holm-adjusted p is below 0.05.
- **"Higher cost":** the CI lower bound is above 0 and the Holm-adjusted p is below 0.05.
- **Otherwise:** "no significant cost difference".
- **Quality:** paired passes must be at least the reference's.

Success criteria:

- **v7 works:** `tm7` vs `stock` shows "lower cost" at equal quality.
- **Graph-first adds value over v6:** `tm7` vs `tm6` shows "lower cost" at equal quality.
- **Value beyond the advice:** `tm7` vs `tm6_hint` shows "lower cost".
- **The goal of at least 30% savings:** judged against the `tm7` vs `stock` point estimate
  and CI. It is never assumed to be met.

## Failures and exclusions

These rules are the same as PRS-1 and PRS-2:

- Infrastructure failures are re-run once, regardless of arm. A harness failure before
  the first model call counts as an infrastructure failure. A session that still fails
  for infrastructure after its re-run is excluded from the pairs, and the count is
  reported.
- Every other failure counts, with all of its tokens.
- Calls without provider-reported usage are estimated and flagged.
- There are no selective re-runs.
- A navigation tool error is returned to the model as an error result, as an MCP server
  would report it. It is never treated as a harness failure.

## Predictions recorded before the run

- **`tm6` vs `stock`:** between −8% and −18% cost, replicating PRS-2.
- **`tm7` vs `stock`:** between −15% and −30% cost, at equal quality.
- **`tm7` vs `tm6`:** between −5% and −15% cost. The largest gains should come on impact
  and locate tasks; logic tasks may still need file views.
- **`tm6_hint` vs `tm6`:** between −5% and +5%. The advice alone should do little.
- **`tm7` vs `tm6_hint`:** between −5% and −15%.
- **Diagnostics:**
  - most `tm7` sessions make at least one navigation call;
  - the first-call cached shares of the arms lie within 10 percentage points of each other.
- **Risk:** the model may ignore the new tools and keep viewing whole files, which would
  leave `tm7` close to `tm6`.

## Limitations

1. One model, one repository and 24 tasks. The harness is shaped like Copilot CLI but is
   not `copilot.exe`.
2. The cost weights are assumptions. GitHub Copilot subscriptions bill premium requests,
   not tokens.
3. Power is limited. 24 task clusters can miss an effect of about 5%. A
   "no significant difference" verdict is not evidence of no effect.
4. Prompt caching may not treat the arms alike. `stock` and `tm6` send identical prefixes,
   while each of `tm6_hint` and `tm7` has its own. The first-call diagnostic shows the
   size of any difference.
5. Name matches in `impact` are unverified and can include unrelated methods of the same
   name. They are marked `[name]`.
6. The symbol index covers Python, Markdown and JSON. Other languages fall back to grep
   and view.
7. The author of v7 also built this harness. Mitigations:
   - blind tasks;
   - this pre-registration;
   - frozen hashes;
   - two independent code reviews;
   - raw captures of every call, and an analysis that recounts every token from them;
   - v7 frozen before any task prompt was read (see below).

## Smoke test

One dummy task per arm checks the mechanics. It is not analyzed. If any change follows,
`prepare` is re-run and the change is disclosed here.

## Checks and changes before the run

1. **First independent review** (code reviewer subagent). It found 0 critical, 1 high,
   11 medium and 14 low issues. All were fixed before v7 was frozen. The main fixes:
   - Unlisted-call counts for different names were added together, and all of them were
     reported under the first symbol. Each name now gets its own count.
   - A non-callable symbol could hide callables with the same name.
   - Results could exceed the budget through long headings, single huge lines or echoed
     arguments.
   - Graph line numbers were stale after edits.
   - Hidden files could be read.
   - A logical-root edge case.
   - The run did not re-check the protocol, tasks and index hashes.
   - The protocol text did not match the code.

   It also named three risky assumptions. Responses:
   - **Power:** 24 fresh tasks instead of 12 fresh plus 12 exposed, and 5 repeats instead
     of 3.
   - **Prompt caching treating the arms alike:** the first-call diagnostic.
   - **Attribution:** the `tm6_hint` arm.
2. **Borrowed from `google-research/harness2`:**
   - A leak check: `prepare` refuses to start if a task's text is readable in the
     workspace.
   - A test that caps the always-on tool definitions below 400 tokens.
3. **Second independent review** of the fixes found 0 critical, 0 high, 3 medium and
   6 low issues. All were fixed except one test gap: the three-name limit of the
   "Not listed" note has no test. The fixes:
   - A graph file recorded without a hash (it was edited during the build) now counts as
     stale.
   - A harness failure before the first model call cost nothing. It would have been
     paired as a cheap failure, and only tm7 does setup work before that call. It now
     counts as an infrastructure failure (see Failures and exclusions).
   - The exact Wilcoxon test is computed by dynamic programming. Enumerating 2^24 sign
     patterns would have taken 10–30 minutes. The harness self-test checks that the
     p-values match the PRS-1/PRS-2 implementation exactly on 325 random inputs,
     including ties and zeros.
   - `protocol.json` gets its own hash file, checked before `run`.
   - Smaller v7 fixes: `self.x.name()` no longer counts as a qualified call, while
     `Owner.method()` does; paths are matched in their canonical spelling; huge
     unindexed files are read only in part; long titles are found by their full text.
4. **v7 freeze:** at 2026-10-18T16:34:07Z, before any task prompt or answer was read.
   - `brainspace/symbol_index.py` SHA-256:
     `ec0608ca1028cacfcd3f1fb31580a307e28945409247281a1030977b93be1984`
   - `tests/test_symbol_index.py` SHA-256:
     `07a6c4dbd5a7369bf34bc3c8f0ad4e40667c5c2db4bd810c1ec6ae32ab26e4b1`

   Up to this point, the only task information seen was the authors' summary tables:
   task id, category and the file names each task needs. On the real snapshot after
   the freeze:
   - all 5,298 stress calls stayed at 2,415 tokens or less;
   - `impact` found 99.4% of the call sites that a grep for calls finds.
5. **Task verification**, done after the v7 freeze:
   - **Call sites** were resolved to their enclosing functions with Python's `ast` on the
     snapshot: M01, M03, M07, M08, M13, M15, M19 and M20.
   - **Logic chains** were read end to end:
     - M04: transport reasons and `model_calls` accounting.
     - M05: the benchmark's recovery status.
     - M06: with round index 1 (`initialize` starts no round), the radius is 1.023 for
       8 tasks, above the 0.99999 margin, and 0.9645 for 9. Each task needs 16 call
       slots, out of 256.
     - M16: log overview windows.
     - M17: lease release and cascade deletes.
     - M18: policy reasons.
   - **Docs figures** were matched line by line: M09, M10, M21 and M22.
   - **Edit oracles** passed the frozen `validate_tasks`: each replacement is unique,
     not a no-op, and parses.
   - **All 24 expected answers held.** Two corrections were made before `prepare`:
     - **M14 (d)** was reworded to "the installer-side helper (not the setup entry
       point) that ... verifies its SHA-256", because `brainspace_setup.py::main` was a
       second defensible answer.
     - **M16:** the grader strips whitespace from answers but not from expected values,
       so the expected `"full log: "` could never match. It is now `"full log:"`. The
       prompt now also assumes that the compressor's own length check passes; without
       that, short lines produce no overview.
