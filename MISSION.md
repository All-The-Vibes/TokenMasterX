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

- **Fixed overhead is paid on every call.** Copilot CLI re-sends about 13,500 tokens of
  system prompt and tool definitions on every call (`gpt-6-astra`). A shorter fixed prompt and
  fewer calls beat smaller tool results.
- **Rewriting earlier messages can cost more than it saves.** It invalidates the provider's
  cache from that point on. In PRS-1, v5 compaction raised cost by 61.6% this way.
- **A graph wins only if it saves more than it adds.** Its tool definitions ride on every call.
  It pays off when it replaces model calls.

## Where we stand

Current results are in the [README](README.md#benchmark-summary-github-copilot-cli) and in
[COPILOT_CLI_RESULTS.md](token-master-plugin/docs/COPILOT_CLI_RESULTS.md), with each study's
pre-registration and results under `token-master-plugin/docs/PRS*_PROTOCOL.md` and
`PRS*_RESULTS.md`. Two earlier claims are superseded: the October 17 figures are retracted
([report](token-master-plugin/docs/V5_ISOLATED_SANDBOX_SAVINGS_REPORT.md)), and the early −72%
Django pilot was never replicated
([research notes](docs/research/token-efficient-harness-research.md) §7.10).

## What we are building

1. **Send less fixed overhead (lean tool set, opt-in).** With `--lean`, the TokenMaster launcher
   removes 13 built-in Copilot CLI tools: 11 that no session called in the October 18 runs, and two
   workflow tools that none of the October 27 sessions called. Since October 30 it is off by
   default: without `--lean`, the launcher sends every built-in tool.
   - Unless the prompt, a flag or `TOKENMASTER_KEEP_TOOLS` keeps them, their definitions and the system-prompt text
     about them leave every call.
   - In a probe on Copilot CLI 1.0.78-3, the `gpt-6-astra` system prompt fell from 7,216 to
     5,117 tokens.
   - Most of the Copilot CLI saving came with this change. The published results were measured with
     it on, so they apply with `--lean`.
   - One later stock session called `task`, one of the removed tools. Without `--lean`, every tool
     stays for work that needs subagents, skills or background PowerShell.
2. **One system prompt for every session in a folder (bridge).** Copilot CLI writes each session's
   folder into its system prompt, so no two sessions send the same system prompt.
   - In bring-your-own-model mode, the bridge moves that line to the first user message. The
     system prompt still names the working folder, so only sessions in the same folder share it.
   - On Django with `gpt-6-astra` (Copilot CLI 1.0.78-3, one folder per version), 44 of 45
     TokenMaster first calls then read the prompt from the cache. No stock first call did.
   - On 1.0.98, stock first calls read part of the prompt from the cache when another stock
     session ran shortly before, so this lever saves less there.
   - This lowers cost, not raw tokens.
3. **Graph over grep (v7).** Answer "where is X", "show me X" and "who calls X" from
   pre-computed structure.
   - The structure is an exact-range symbol index plus graphify's call graph, behind
     three compact tools: `locate`, `read_symbol` and `impact`.
   - Every result stays under 2,400 tokens.
   - `setup.py` installs it as one MCP server, `tokenmaster-nav`.
   - On Copilot CLI, it saved model calls. On 45 Django tasks, it cut a further 15.4%
     (`gpt-6-astra`) and 9.8% (`claude-opus-5.5`) of the raw tokens that TokenMaster without
     graphify used.
   - Without a model, a repository-wide `rg` for "who uses X" printed 128,279 tokens for 40
     Django symbols; `impact` returned 8,401. Copilot's search tool shortens long results, and
     the models in Copilot CLI itself searched with narrower patterns, so this is lookup output, not
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

## Principles

- **Raw tokens first, then billed cost, per finished task, at equal quality.** Not per-turn
  size, and not premium requests.
- **Test on the client itself.** A replica harness can mislead: Copilot CLI's own fixed
  prompt was almost 4 times the size of the PRS-4 agent's.
- **Pre-register, then measure.** Freeze code, tasks and analysis before any live
  call. Use tasks written by someone who does not know the arms. Recount every token
  from raw records. Label exploratory runs as exploratory.
- **Publish negatives.** PRS-1 found no win, and PRS-2 found the shipped graph tools
  cost more; both are published. Before the lean tool set, TokenMaster saved cost on Copilot
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
- [`COPILOT_CLI_RESULTS.md`](token-master-plugin/docs/COPILOT_CLI_RESULTS.md): the Copilot CLI
  runs, their method and limits.
- `token-master-plugin/docs/PRS*_PROTOCOL.md` and `PRS*_RESULTS.md`: each study's
  pre-registration and results.
- `evidence/`: committed summaries and per-session results. The Copilot CLI runs are in
  `evidence/django-scale-20261022/` and `evidence/copilot-lean-*-20261019/`; the PRS studies are
  in `evidence/prs*-20261018/`, except PRS-5 (`evidence/prs5-20261019/`) and PRS-6
  (`evidence/prs6-copilot-1.0.98-20261026/`).
- [`token-efficient-harness-research.md`](docs/research/token-efficient-harness-research.md):
  early pilots, including the §7.9 retraction and the §7.10 Django pilot. The later studies
  supersede them.
- [`harness-command-design.md`](docs/history/harness-command-design.md): the original design of
  the routing `/command`.

**One line:** TokenMaster makes the cheapest correct path the default. It sends less fixed
overhead on every call, answers structure from a graph, shapes each tool result once, and
measures the outcome in raw tokens and billed cost per finished task.
