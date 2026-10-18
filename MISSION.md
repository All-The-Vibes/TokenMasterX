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
real cost of finishing the whole task**, summed over every call.

Providers cache exact prompt prefixes and bill cached input at about a tenth of the
normal price. So the unit is cost per finished task, at equal quality:

```text
cost = uncached input + 0.1 × cached input + 8 × output     (provider-reported usage)
```

Raw cumulative tokens are reported too, as a secondary measure. This changes what
counts as a win:

- **New tokens per call matter most.** History that stays byte-identical is re-read
  from the cache cheaply. Smaller, fewer new tool results beat a shorter transcript.
- **Rewriting earlier messages can cost more than it saves.** It invalidates the
  cache from that point on. In PRS-1, v5 compaction raised cost by 61.6% this way.
- **Overhead is paid on every call.** A graph harness wins only if its tool
  definitions and routing text cost less than the reading they replace.

## Where we stand (October 18, 2026)

The evidence comes from pre-registered live studies on this repository:
- Model `gpt-6-astra`, in a harness shaped like Copilot CLI.
- Tasks written by agents that were not told the arms.
- Code, tasks and analysis frozen by hash before any live call.
- Every token recounted from raw captures.

| Study | Sessions | Finding |
| --- | ---: | --- |
| [PRS-1](token-master-plugin/docs/PRS1_RESULTS.md) | 252 | No configuration shipped at the time significantly cut tokens. v5 raised cost by 61.6%. |
| [PRS-2](token-master-plugin/docs/PRS2_RESULTS.md) | 216 | v6 result shaping cut cost by 11.6%. The graph tools as shipped raised it by 12.9%. |
| [PRS-3](token-master-plugin/docs/PRS3_RESULTS.md) | 480 | v7 cut cost by **22.0%** against stock (95% CI −35.4% to −8.9%); v6 cut it by 13.0%. Quality was 120/120 in every arm. v7 against v6 alone: −10.4%, not significant. |
| [PRS-4](token-master-plugin/docs/PRS4_RESULTS.md) | 360 | v7 with a cache-stable system prompt cut billed cost per finished task by **49.8%** against stock (95% CI −57.1% to −42.9%), under continuous use. v7 alone: −18.2%. Quality was 120/120 in every arm. |

**The target of at least 30% savings at equal quality is met under continuous use (PRS-4).**
Isolated sessions, more than about 30 minutes apart, save about 19%. Only the experimental,
read-only native Copilot route applies the cache-stable prompt today.

Earlier claims are superseded:
- **The October 17 savings figures are retracted.** See the retraction in the
  [README](README.md).
- **The Django pilot is unreplicated.** It reported −72% cumulative input tokens
  ([research notes](token-efficient-harness-research.md) §7.10), but:
  - it used 2 runs per cell;
  - it counted raw tokens without the cache discount;
  - it describes its own numbers as directional.

  No pre-registered study has reproduced a saving of that size.

## What we are building

1. **Pay once per tool result (v6).** Shape each tool result once, deterministically,
   when it enters the conversation.
   - Search output and path lists are folded losslessly.
   - Oversized results become digests that say how to fetch the rest.
   - History is never rewritten, so the provider's cache stays valid.
   - It is the default in the native Copilot route and in the Copilot output hook.
2. **Graph over grep (v7).** Answer "where is X", "show me X" and "who calls X" from
   pre-computed structure.
   - The structure is an exact-range symbol index plus graphify's call graph, behind
     three compact tools: `locate`, `read_symbol` and `impact`.
   - Every result stays under 2,400 tokens.
   - `setup.py` installs it as one MCP server, `tokenmaster-nav`.
   - Its clearest gain is on "who calls X" tasks: 52% cheaper than v6 alone, an
     exploratory result.
3. **Routing as a short default.** A graph the model never queries saves nothing,
   but routing text rides on every call.
   - With v7's 66-token hint, the model used the new tools in 89 of 120 sessions.
   - The 1,383-token routing prompt shipped before v7 helped make the graph tools
     more expensive (PRS-2).
4. **Recall over re-establishment (not yet measured).** Reusing what an earlier
   session learned, instead of re-deriving it, remains an idea. No study has
   measured it.

## Open levers (hypotheses, not results, unless marked measured)

1. **First-call caching across sessions: measured in PRS-4 (−38.6% against v7 alone).**
   - Every PRS-3 session's first call wrote about 3,500 tokens to the cache and read
     none. Cause: Copilot CLI puts each session's own folder path inside the system
     message, so no two sessions share a system message.
   - Probes on October 18, 2026 ([evidence](evidence/cache-probe-20261018/results.json)):
     - A byte-identical first request read 3,553 of 3,556 tokens from the cache. A new
       `prompt_cache_key` changed nothing; only the content decides.
     - With only the user message changed, 3,430 tokens came from the cache, so the
       provider keeps a cache entry at the end of the system message.
     - With the folder path moved from the system message to the user message, a
       second session's first call read 3,401 of 3,564 tokens from the cache.
   - The provider's price table (`copilot_usage` in each response) bills a cache write
     at 1.25×, a cache read at 0.1× and output at 5× the input price. At those prices a
     hit saves about 3,900 units per session, about 21% of stock's cost.
   - The saving applies only when another session used the same prefix within the
     cache lifetime. That lifetime is at least 6.5 minutes and less than 31 minutes
     ([evidence](evidence/cache-probe-20261018/ttl.jsonl)).
   - Next step for this lever: bring the cache-stable prompt to a route that users can
     install with full tools. Today only the experimental, read-only native route applies it.
2. **Edit tasks:** v7 cost 9% more than v6 on them.
3. **Output tokens:** v7 already wrote 17% fewer than v6; terser final answers may
   cut more.

## Principles

- **Real cost per finished task, at equal quality.** Not per-turn size, and not
  premium requests.
- **Pre-register, then measure.** Freeze code, tasks and analysis before any live
  call. Use tasks written by someone who does not know the arms. Recount every token
  from raw captures.
- **Publish negatives.** PRS-1 found no win, and PRS-2 found the shipped graph tools
  cost more; both are published. A harness that wins everywhere is measuring an
  artifact.
- **Never rewrite history.** Shape content once, as it enters, and keep earlier
  messages byte-identical.
- **Overhead is a cost.** Every tool definition and instruction is re-sent on every
  call; keep them small.
- **Structure is fungible.** Graphify, our symbol index or something better: the
  value is in getting the model to the cheapest correct answer reliably.

## Non-goals

- **Not a premium-request optimizer.** GitHub Copilot subscriptions bill requests,
  not tokens, and our cost weights are assumptions.
- **Not a universal speedup.** We claim no win where a short grep already answers the
  question.

## How to read this repo through the mission

- [`README.md`](README.md): current evidence, components and how to reproduce.
- `token-master-plugin/docs/PRS*_PROTOCOL.md` and `PRS*_RESULTS.md`: each study's
  pre-registration and results.
- `evidence/prs*-20261018/`: committed study summaries and per-session results.
- [`token-efficient-harness-research.md`](token-efficient-harness-research.md):
  early pilots, including the §7.9 retraction and the §7.10 Django pilot. The PRS
  studies supersede them.
- [`harness-command-design.md`](harness-command-design.md): the original design of
  the routing `/command`.

**One line:** TokenMaster makes the cheapest correct path the default. It shapes each
tool result once, answers structure from a graph, and measures the outcome as real
cost per finished task.
