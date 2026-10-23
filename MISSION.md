# TokenMaster — Mission

## The thesis

**We are redefining token economics at the harness level.**

The harness is the unit of intervention. Not the model, not the prompt, not the user:
the **harness**, the layer that decides *what context the model sees on every call.*
Today that layer is naive. It hands the model a growing transcript, lets it grep and
read its way to understanding, and pays again for the accumulated context on every
call. We treat that as an engineering defect, not an inevitability to be billed for.
**The model should pay once to understand structure, then never again.**

## What "token economics" means here

A token is work the model is forced to do. What matters is not one call but **the
whole task**, summed over every call, at equal quality. We report two measures, in this order:

```text
raw tokens  = input + output                                        (provider-reported usage)
billed cost = new input + r_read × cache reads + r_write × cache writes + r_out × output
```

- The billed-cost ratios come from GitHub's own price table in each response
  (`copilot_usage`): `gpt-6-astra` 0.1, 1.25 and 5; `claude-opus-5.5` 0.05, 1.25 and 5,
  relative to the price of new input.
- PRS-1 to PRS-3 used an earlier cost formula: uncached input + 0.1 × cached input + 8 × output.

This changes what counts as a win:

- **Fixed overhead is paid on every call.** The real Copilot CLI re-sends about 13,500 tokens of
  system prompt and tool definitions on every call (`gpt-6-astra`). A shorter fixed prompt and
  fewer calls beat smaller tool results.
- **Rewriting earlier messages can cost more than it saves.** It invalidates the provider's
  cache from that point on. In PRS-1, v5 compaction raised cost by 61.6% this way.
- **A graph wins only if it saves more than it adds.** Its tool definitions ride on every call.
  It pays off when it replaces model calls.

## Where we stand (October 22, 2026)

**The real Copilot CLI (exploratory, not pre-registered).** Copilot CLI 1.0.98, `gpt-6-astra`
and `claude-opus-5.5`, GitHub's Copilot API, reasoning effort `low`. Each run used offline
bring-your-own-model mode through a relay, 1 run per task and version, and back-to-back
sessions. The full parameter table and method are in
[COPILOT_CLI_RESULTS.md](token-master-plugin/docs/COPILOT_CLI_RESULTS.md#test-parameters).

| Run | Sessions | Finding |
| --- | ---: | --- |
| Django 5.2, 45 "who calls X?" tasks (October 22) | 270 | Full TokenMaster used **53.4%** (`gpt-6-astra`, 95% CI −57.1% to −49.1%) and **51.6%** (`claude-opus-5.5`, −55.7% to −47.2%) fewer raw tokens than stock, and fewer on all 45 tasks with each model. Cost fell 79.9% and 60.8% as run, with sessions back to back; 49.5% and 46.0% with every first call re-priced as cold. Correct answers: stock 90/90, TokenMaster 88/90. Graphify cut a further 15.4% and 9.8% on top of TokenMaster without graphify. |
| This repository, 27 tasks (October 19) | 108 | Full TokenMaster used **44.8%** (`gpt-6-astra`) and **53.5%** (`claude-opus-5.5`) fewer raw tokens. Cost fell 62.8% and 51.2% as run; 40.8% and 43.9% with every first call cold. Passed: stock 54/54, TokenMaster 53/54. |

**Pre-registered studies in a replica harness.** These ran a Copilot-CLI-shaped agent with
`gpt-6-astra`, not the real Copilot CLI. Its fixed prompt was about 3,600 tokens.

| Study | Sessions | Finding |
| --- | ---: | --- |
| [PRS-1](token-master-plugin/docs/PRS1_RESULTS.md) | 252 | No configuration shipped at the time significantly cut tokens. v5 raised cost by 61.6%. |
| [PRS-2](token-master-plugin/docs/PRS2_RESULTS.md) | 216 | v6 result shaping cut cost by 11.6%. The graph tools as shipped raised it by 12.9%. |
| [PRS-3](token-master-plugin/docs/PRS3_RESULTS.md) | 480 | v7 cut cost by **22.0%** against stock (95% CI −35.4% to −8.9%); v6 cut it by 13.0%. Quality was 120/120 in every arm. v7 against v6 alone: −10.4%, not significant. |
| [PRS-4](token-master-plugin/docs/PRS4_RESULTS.md) | 360 | Under continuous use, v7 with the cache-stable system prompt cut billed cost per finished task by **49.8%** against stock (95% CI −57.1% to −42.9%). v7 alone: −18.2%. Quality was 120/120 in every arm. Raw tokens fell 14.0%. |

**The target of at least 30% savings is met on the real Copilot CLI, in exploratory runs, with
answer quality close to stock.** Raw tokens fell 44.8% to 53.5%. Cost fell 51.2% to 79.9% with
sessions back to back, and 40.8% to 49.5% with every first call re-priced as cold. TokenMaster gave
2 fewer correct answers of 90 on Django and 1 fewer of 54 on this repository; all were model
errors. A pre-registered real-CLI study has not yet confirmed the result. PRS-5, the first
attempt, stopped after 10 of 32 sessions.

Earlier claims are superseded:
- **The October 17 savings figures are retracted.** See the retraction in the
  [README](README.md).
- **The early Django pilot is unreplicated.** It reported −72% cumulative input tokens
  ([research notes](token-efficient-harness-research.md) §7.10), but:
  - it used 2 runs per cell;
  - it counted raw tokens without the cache discount;
  - it describes its own numbers as directional.

  The October 22 Django runs above are a separate test with a different method.

## What we are building

1. **Send less fixed overhead (lean tool set).** The TokenMaster launcher removes 11 built-in
   Copilot CLI tools that no session called in the October 18 runs.
   - Their definitions and the system-prompt text about them leave every call.
   - In a probe, the `gpt-6-astra` system prompt fell from 7,216 to 5,117 tokens.
   - Most of the real-CLI saving came with this change.
   - One later stock session called `task`, one of the removed tools. `--all-tools` keeps every
     tool for work that needs subagents, skills or background PowerShell.
2. **One system prompt for every session (bridge).** Copilot CLI writes each session's folder
   into its system prompt, so no two sessions send the same system prompt.
   - In bring-your-own-model mode, the bridge moves that line to the first user message.
   - On Django with `gpt-6-astra`, 44 of 45 TokenMaster first calls then read the prompt from
     the cache. No stock first call did.
   - This lowers cost, not raw tokens.
3. **Graph over grep (v7).** Answer "where is X", "show me X" and "who calls X" from
   pre-computed structure.
   - The structure is an exact-range symbol index plus graphify's call graph, behind
     three compact tools: `locate`, `read_symbol` and `impact`.
   - Every result stays under 2,400 tokens.
   - `setup.py` installs it as one MCP server, `tokenmaster-nav`.
   - On the real CLI, it saved model calls. On 45 Django tasks, it cut a further 15.4%
     (`gpt-6-astra`) and 9.8% (`claude-opus-5.5`) of the raw tokens that TokenMaster without
     graphify used.
   - Without a model, a repository-wide `rg` for "who uses X" printed 128,279 tokens for 40
     Django symbols; `impact` returned 8,401. Copilot's search tool shortens long results, and
     the models in the real CLI searched with narrower patterns, so this is lookup output, not
     session cost.
4. **Pay once per tool result (v6).** Shape each tool result once, deterministically,
   when it enters the conversation.
   - Search output and path lists are folded losslessly.
   - Oversized results become digests that say how to fetch the rest.
   - History is never rewritten, so the provider's cache stays valid.
   - It runs in the bridge, the Copilot output hook and the native Copilot route.
5. **Recall over re-establishment (not yet measured).** Reusing what an earlier
   session learned, instead of re-deriving it, remains an idea. No study has
   measured it.

## Open levers (hypotheses, not results, unless marked measured)

1. **Copilot CLI's default GitHub routing.** Without a provider URL, the launcher applies only
   the lean tool set; graph navigation and the v6 `view` hook still work, but the bridge does
   not. No run has measured that configuration.
2. **A pre-registered real-CLI study.** It needs fresh blind tasks, both models, and tasks that
   run tests. The harness gaps to fix first:
   - give the agents a Python and test runner;
   - grade line-ending-only changes fairly.
3. **Import aliases in `impact`.** Calls through an alias, such as `login` imported as
   `auth_login`, are invisible to it. Hypothesis: resolving them would save follow-up searches.
4. **Edit tasks:** in PRS-3 (replica harness), v7 cost 9% more than v6 on them.
5. **Output tokens:** in PRS-3, v7 already wrote 17% fewer than v6. Terser final answers may
   cut more.
6. **First-call caching across sessions: measured.**
   - PRS-4 (replica harness): −38.6% billed cost against v7 alone, under continuous use.
   - Real CLI, `gpt-6-astra`: 44 of 45 warm first calls through the bridge, 0 of 45 for stock.
   - The saving needs another session with the same system prompt within the cache lifetime.
     One probe found the cached prompt still there after 6.5 minutes and gone after 31 minutes
     ([evidence](evidence/cache-probe-20261018/ttl.jsonl)).
   - With `claude-opus-5.5`, stock first calls already read the tool block from the cache. They
     still wrote the system prompt to it (median 7,474 tokens; TokenMaster: 314). No run isolated
     the bridge's own effect with `claude-opus-5.5`.

## Principles

- **Raw tokens first, then billed cost, per finished task, at equal quality.** Not per-turn
  size, and not premium requests.
- **Test on the real client.** A replica harness can mislead: the real Copilot CLI's fixed
  prompt was almost 4 times the size of the PRS-4 agent's.
- **Pre-register, then measure.** Freeze code, tasks and analysis before any live
  call. Use tasks written by someone who does not know the arms. Recount every token
  from raw records. Label exploratory runs as exploratory.
- **Publish negatives.** PRS-1 found no win, and PRS-2 found the shipped graph tools
  cost more; both are published. Before the lean tool set, TokenMaster saved cost on the real
  CLI but not reliably raw tokens; that is published too. A harness that wins everywhere is
  measuring an artifact.
- **Never rewrite history.** Shape content once, as it enters, and keep earlier
  messages byte-identical.
- **Overhead is a cost.** Every tool definition and instruction is re-sent on every
  call; keep them small.
- **Structure is fungible.** Graphify, our symbol index or something better: the
  value is in getting the model to the cheapest correct answer reliably.

## Non-goals

- **Not a premium-request optimizer.** We measure tokens and GitHub's per-token charge, not
  premium-request counts or plan allowances.
- **Not a universal speedup.** We claim no win where a short grep already answers the
  question.

## How to read this repo through the mission

- [`README.md`](README.md): current evidence, components and how to reproduce.
- [`COPILOT_CLI_RESULTS.md`](token-master-plugin/docs/COPILOT_CLI_RESULTS.md): the real Copilot
  CLI runs, their method and limits.
- `token-master-plugin/docs/PRS*_PROTOCOL.md` and `PRS*_RESULTS.md`: each study's
  pre-registration and results.
- `evidence/`: committed summaries and per-session results. The real-CLI runs are in
  `evidence/django-scale-20261022/` and `evidence/copilot-lean-*-20261019/`; the PRS studies are
  in `evidence/prs*-20261018/`, except PRS-5 (`evidence/prs5-20261019/`).
- [`token-efficient-harness-research.md`](token-efficient-harness-research.md):
  early pilots, including the §7.9 retraction and the §7.10 Django pilot. The later studies
  supersede them.
- [`harness-command-design.md`](harness-command-design.md): the original design of
  the routing `/command`.

**One line:** TokenMaster makes the cheapest correct path the default. It sends less fixed
overhead on every call, answers structure from a graph, shapes each tool result once, and
measures the outcome in raw tokens and billed cost per finished task.
