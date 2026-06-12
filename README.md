# TokenMaster

<p align="center">
  <img src="assets/tokenmaster-hero.svg?v=2" alt="TokenMaster — a single bright graph-routed query path cutting through a faint tangle of brute-force search edges" width="100%">
</p>

**A new cost model for code-understanding agents.** TokenMaster re-engineers *token economics at the harness layer* — the layer that decides what the model re-reads on every single turn — for [Claude Code](https://docs.claude.com/en/docs/claude-code) and GitHub Copilot CLI.

The thesis in one line: **the model should pay once to understand a codebase's structure, then never again.** Today's harnesses violate this on every turn — they hand the model a growing transcript and let it grep its way to understanding, re-paying for the entire accumulated context turn after turn. TokenMaster makes that re-derivation *economically illegal*: structural questions get routed to a **prebuilt code graph** answered in one bounded query, so the cumulative token bill collapses instead of compounding.

It attacks the bill on **two complementary fronts**: a **routing layer** (below) that collapses the cost of re-deriving structure, and **[Headroom](#headroom--the-compression-layer)**, a compression layer that shrinks the raw tool outputs sitting in the transcript. Different token populations, so the wins compound. Routing is the headline; Headroom is the multiplier.

### Baseline vs TokenMaster, measured

Same CLI. Same model. Same task. The only variable is whether TokenMaster's routing agent is on.

> **-73% input tokens. 3.71x more efficient overall. Up to 7.8x on blast-radius analysis.**
> **12 / 12 tasks answered from the graph. Zero correctness regressions.**
> >
> *Pooled across scikit-learn + sympy. 36 live GitHub Copilot runs.* [*Full breakdown below.*](#by-the-numbers)

```text
/token-master
```

That one command builds the index for the current repository and turns on routing.

---

## Why token economics, not token *count*

Start with the one fact everything else follows from: **the model has no memory between turns.** To continue a task, the harness re-sends the *entire* transcript every turn — every file read, every tool result, every message so far — and the model re-reads and re-reasons over all of it before doing anything new.

So a token is not paid for once. It is paid for **every turn it stays in the context window.** The cost that matters is not *tokens sent* but the **total tokens processed, summed across every turn** until the task is done.

### Same answer, two bills

The task: *"who calls `load_config`?"* The context carried forward grows each turn, so every turn re-pays for the ones before it.

```text
GREP its way there                       GRAPH lookup
turn 1  grep            2,000            turn 1  query graph   2,500
turn 2  read auth.py    6,000            turn 2  answer        3,000
turn 3  read server    11,000            ──────────────────────────
turn 4  read handlers  17,000            TOTAL PROCESSED       5,500
turn 5  grep narrower  19,000
turn 6  read config    24,000
turn 7  answer         26,000
──────────────────────────
TOTAL PROCESSED       105,000
```

Same answer. **105,000 vs 5,500 tokens processed.** The grep total is not 26,000 — it is the *sum of all seven turns*, because turn 7 re-read what turn 1 saw, six times over.

### It is the area under the curve

Plot context size per turn and measure the area. A turn that looks cheap on its own is a trap; what costs you is the whole shaded region.

```text
context
  │              ___________   grep: climbs AND runs long
  │           __/              -> big area, expensive
  │        __/
  │     __/
  │  __/
  │ /__________   graph: stays low AND ends fast -> tiny area
  └──────────────────────────► turns
```

### Offering the graph is not enough — you have to enforce it

Left alone, the model defaults to grep out of habit: in TokenMaster's own runs it reached for the graph **0 / 15 times** until it was actively routed there. So TokenMaster does not merely *offer* the cheap path — it makes the prebuilt graph the **default** for structural questions ("who calls X," "what breaks if I change Y"). Offering saves nothing; enforcing is what collapses the area under the curve — and that collapse is exactly the `-73%` headline above.

## By the numbers

First proven on **Django** (992 `.py` files, hard multi-hop tasks), then **replicated on independent SWE-bench Lite repos** to rule out single-repo luck. One measurement throughout: cumulative input tokens to finish a structural task, **the baseline agent vs the same setup with TokenMaster on**.

> **Baseline** = the stock agent, no routing layer. It answers structural questions by reading and re-reading files, turn after turn. **TokenMaster** routes those same questions to a prebuilt graph. Identical model (`claude-sonnet-4.5`), identical prompts, identical correctness oracle. The routing agent is the only thing that changes.

### Pooled headline

*36 live GitHub Copilot runs. 2 repos x 3 tasks x 2 reps x 3 arms.*

|  | Baseline | **TokenMaster** | Delta |
| --- | :---: | :---: | :---: |
| Cumulative input tokens | baseline | **-73.1%** | **3.71x fewer** |
| Tasks answered from the graph | n/a | **12 / 12** | never fell back |
| Correctness vs AST oracle | pass | **pass** | no regression |

### Where the win lives

The harder the traversal, the bigger the collapse. Caller lookups save 3-5x; blast-radius analysis ("what breaks if I change this?") is where the baseline agent detonates, re-reading files across the whole repo to trace impact, and where one bounded graph query wins biggest:

```text
Cumulative input tokens to finish the task   (lower is better)

"Who calls X?"  -  reverse dependency lookup
  scikit-learn  Baseline    █████████                      69,609
  scikit-learn  TokenMaster ███                            21,215   3.3x fewer
  sympy         Baseline    ██████████████                107,954
  sympy         TokenMaster ███                            21,189   5.1x fewer

"What breaks if I change this?"  -  blast radius
  scikit-learn  Baseline    ███████████████████████████   203,481
  scikit-learn  TokenMaster ████                           26,908   7.6x fewer
  sympy         Baseline    ████████████████████████████  210,214
  sympy         TokenMaster ████                           26,830   7.8x fewer
```

On blast radius, the baseline balloons past **200,000 tokens** tracing impact by hand; TokenMaster answers from the graph in **\~27,000** - an order-of-magnitude saving, repeated across two unrelated codebases.

### Honest negatives — the proof the method is real

A harness that wins *everywhere* is measuring an artifact. TokenMaster doesn't:

- **Inheritor lookup on sympy ran -44%** - the graph query cost more than the baseline on that one task. Reported, not hidden.
- **Negative control** (a question the baseline already nails in \~3 turns) correctly came out a **wash** - no traversal needed, no win claimed.

> **Provenance.** Every figure above comes from the project's live A/B/C benchmark harness
> (`run_nav.py` -> `score_nav.py`), reproduced verbatim from its generated report. The benchmark
> sandbox and raw reports are kept out of this repo by design (research and scratch stay on disk).
> Django origin figures: **-72% overall (3.5x), up to -80% (5.0x)**.

## How it works

TokenMaster installs a **routing agent** that prefers graph queries over grep, backed by two interchangeable graph suppliers and the host CLI's own session memory:

| Layer | Supplier | Role |
| --- | --- | --- |
| **Semantic-spatial** (default) | [`graphify`](https://github.com/safishamsi/graphify) | Fast, no-LLM structural index. Answers callers / callees / impact / inheritors from inferred edges. The cheap default. |
| **Precise-spatial** (last-mile) | [`@colbymchenry/codegraph`](https://www.npmjs.com/package/@colbymchenry/codegraph) | AST-resolved call edges. The precision escalation: when an inferred edge isn't trustworthy enough — precision-critical impact analysis, or sparse call graphs (common in JS/TS) where name-inference under-connects. Costs more tokens to buy exact edges. |
| **Temporal** | host CLI session memory | Native cross-session recall — no extra server. |

The routing layer is the product; the indexes are interchangeable suppliers. Routing is the load-bearing primitive — in early tests the model queried the graph **0/15 times** without an explicit nudge and **8/8** with it. A graph the model never queries saves nothing, so TokenMaster's job is not to *offer* the efficient tool but to make it the path of least resistance.

## Headroom — the compression layer

Routing collapses the cost of *re-deriving structure*. But there is a second token population it never touches: the **raw tool outputs** — directory listings, test logs, file dumps — that land in the transcript and then get re-sent on every subsequent turn. Headroom is the layer that attacks *those*.

It is deliberately a **complement, not a competitor**: routing shrinks what the model re-reads to *understand the codebase*; Headroom shrinks what the model re-reads from its *own tool results*. Disjoint populations, so the savings **compound** rather than overlap. The same "area under the curve" logic from above applies — a tool output that is 6x smaller is 6x smaller *every turn it lingers in context*, not just once.

### How it stays lossless

The risk with compressing tool output is obvious: throw away the one line that mattered. Headroom's escape hatch is the **CCR** (Content-addressed, Cached, Reversible store). A compressor may drop detail from what the model *sees*, but only after handing the original to CCR, which stores it verbatim under `sha256(content)` and returns a stable placeholder:

```text
[[HR:9f3a2b1c4d5e|log; pytest run; 412L]]
```

If the model ever needs the dropped detail, it calls `headroom_retrieve` with that placeholder and gets the **exact original bytes** back. Content-addressing buys two things at once: identical content stashes once (free dedup), and the placeholder is byte-identical across turns — so it never perturbs the provider's prompt-cache prefix. (That last point is the whole reason compression and caching don't collide: a placeholder carrying a timestamp or hit-counter would silently evict the cache every turn. Headroom's are derived only from content.)

### By the numbers, measured

Every figure below is the real compressor run over a **real artifact** — actual repo source, a live `pytest -v` capture, a real serialized directory listing, the real README — measured in `tiktoken cl100k_base` tokens (the same proxy the engine ships). Reproduce with `python sandbox_headroom/measure_impact.py`.

```text
Tokens in -> out, per content type   (lower out is better)

JSON   dir listing, 200 files   769  ->   92      88.0%   8.36x
log    live pytest -v run     2,838  ->  475      83.3%   5.97x
code   real ccr/router/mcp    5,172  -> 3,345     35.3%   1.55x
prose  README + research doc 20,169  -> 20,067     0.5%   1.01x   <- honest negative
```

The shape is the point. **Structured, repetitive output (JSON, logs) compresses 6-8x** because its redundancy is mechanical and safe to elide. **Code compresses ~1.5x** — signatures and docstrings kept, bodies stashed. **Prose barely moves** (0.5%): natural language has little safe-to-drop redundancy, so Headroom defaults to near-lossless whitespace normalization and leaves the lossy ML path off. A layer that claimed to squeeze prose like it squeezes a directory listing would be lying; this one reports the 0.5% and moves on.

**Benchmark it on your own code** — these numbers are not a brochure, they're a command. The same harness that produced the table ships with the plugin; point it at *your* files, logs, or piped output:

```bash
# your own files (type auto-detected per file):
uv run --with mcp --with tiktoken python headroom_benchmark.py path/to/big.json server.log ./src

# or pipe a real command's output straight in:
pytest -v | uv run --with mcp --with tiktoken python headroom_benchmark.py --stdin --hint=pytest
```

It measures in real `tiktoken` tokens, verifies lossless recovery on every placeholder it stashes, and prints the per-type table plus the area-under-curve projection below. Run with no arguments for an instant demo over Headroom's own files. `--json` emits machine-readable output for your own dashboards.

### Where the win actually lives: per-turn, not per-output

A single compressed output is re-sent every turn it stays in context, so its saving is **multiplied by the turns it survives**. The live pytest log above, left in a 10-turn task:

```text
turns in context     raw cumulative    compressed     tokens saved
        1                  2,838             475           2,363
        3                  8,514           1,425           7,089
        5                 14,190           2,375          11,815
       10                 28,380           4,750          23,630
```

One log. 23,630 tokens saved across ten turns — and it round-trips losslessly the moment the model asks for it.

### Two delivery paths, both verified on the real host

| Host | Mode | What's verified |
| --- | --- | --- |
| **Claude Code** | Full — auto-compress **hook** + model-invoked tools | PostToolUse hook rewrote a real `3,226 -> 98` token output (**97.0%**) with the buried `ValueError` **preserved**, via the verified `updatedToolOutput` field |
| **GitHub Copilot CLI** | MCP-only — model-invoked `compress` / `retrieve` | The **real `copilot` binary** spawned the server via `uv` and invoked `headroom_compress` end-to-end: `8,299 chars -> 303`, tool footer `2,075 -> 55` tokens (**97.3%**) |

### Honest limitations — Headroom edition

- **Copilot is MCP-only.** GitHub Copilot CLI has no documented output-rewriting hook, so it gets the model-invoked `headroom_compress` / `headroom_retrieve` tools but **not** transparent auto-compression. Claude Code gets the full layer. This is a real capability gap, surfaced in the installer summary rather than hidden.
- **Prose is the weakest lever.** As the table shows, ~0%. The optional LLMLingua-style ML path exists but is off by default because it trades lossless-ness for a marginal prose gain — the wrong trade for tool output.
- **Tiny inputs can't be compressed profitably.** Placeholder + footer overhead would dominate, so a centralized *never-expand* guard returns the original unchanged whenever compression wouldn't strictly shrink it. Compression must never *cost* tokens.
- **Token proxy, not the host tokenizer.** Numbers are `tiktoken cl100k_base`; the host model's exact tokenizer differs in absolute counts, but compression *ratios* are stable across tokenizers, and ratios are what's reported.

> **Provenance.** Compression figures come from `headroom_benchmark.py` (the same self-serve tool shipped with the plugin — real artifacts, real tokenizer); the dual-host figures from `sandbox_headroom/verify_dual_host.py` plus a live `copilot -p` run against a sandboxed `COPILOT_HOME` (the real `~/.copilot` is never touched). 104 unit tests cover the four compressors, the router, and the never-expand invariant (enforced in tokens, not characters — a distinction the benchmark itself surfaced).



## Installation

TokenMaster supports two host CLIs — **Claude Code** and **GitHub Copilot CLI**. Install the
routing agent for whichever you use (the prerequisites below are shared). `/token-master` builds
the per-repo graph and installs the host-appropriate routing agent into your user-scope CLI home.

### Claude Code

TokenMaster is distributed as a Claude Code plugin through a plugin marketplace:

```javascript
/plugin marketplace add shyamsridhar123/TokenMasterX
/plugin install token-master@token-master
```

Then, inside any repository you want to index:

```javascript
/token-master
```

The installer writes the routing agent to `~/.claude/agents/token-master.md` and registers the
graph MCP server in `~/.claude.json`. After the first install, **restart Claude Code** (or start it
with `claude --agent token-master`) for routing to take effect.

### GitHub Copilot CLI

Copilot CLI reads the **same plugin marketplace** as Claude Code, so installation is the same two
commands. In an interactive `copilot` session:

```javascript
/plugin marketplace add shyamsridhar123/TokenMasterX
/plugin install token-master@token-master
```

(Equivalently, from your shell: `copilot plugin marketplace add shyamsridhar123/TokenMasterX`
followed by `copilot plugin install token-master@token-master`.)

Then, inside any repository you want to index:

```javascript
/token-master
```

This builds the per-repo graph and writes the routing agent — with its MCP servers declared inline —
to `~/.copilot/agents/token-master.agent.md`. After the first install, **restart Copilot** (or start
it with `copilot --agent token-master`) for routing to take effect.

> **If you have *both* Claude Code and Copilot CLI installed**, the `/token-master` installer can't
> tell which CLI launched it and defaults to Claude Code. Force the Copilot target by setting
> `TOKEN_MASTER_HOST=copilot` in your environment before running `/token-master`. As a manual
> alternative you can run the installer directly and pass the host explicitly:
> >
> \`\`\`
> python token-master-plugin/skills/token-master/setup.py <repo-root> --host=copilot
> \`\`\`

### Prerequisites

- [**`graphify`**](https://github.com/safishamsi/graphify) — the default graph backend. Install with [`uv`](https://docs.astral.sh/uv/):

```javascript
  uv tool install graphifyy
```

- **`uv`** — the routing agent launches the graph server through it.
- **`node` + `npm`** *(optional)* — only needed for the precise `codegraph` escalation backend. Without them, TokenMaster runs graphify-only and still works.

If a prerequisite is missing, `/token-master` tells you exactly what to install, then re-run it.

## Usage

After setup, just ask structural questions normally:

- *"Who calls `force_str`?"*
- *"What breaks if I change the signature of this method?"*
- *"What inherits from `BaseValidator`?"*

The agent answers them from the graph. To confirm routing is active, ask a known structural question and check that the answer comes from a graph tool call rather than a grep sweep.

Re-run `/token-master` whenever the code has changed enough that the graph is stale.

> **Note:** The routing agent loads at CLI startup. After the first install, restart your host CLI
> (or start it with `--agent token-master`) for routing to take effect. The setup summary prints the
> exact restart command for your host.

## What gets written

`/token-master` is conservative about your working tree:

- The code graph is stored at `.token-master/graph.json` inside the repo.
- `.token-master/` and `.codegraph/` are added to the repo's `.gitignore`.
- The routing agent and graph server are installed to your user-scope CLI home, not the repo.

## Honest limitations

- **Not a universal speedup.** TokenMaster wins on hard, multi-hop traversal. On short structural questions that grep answers in \~3 turns, it is correctly *neutral*. A harness that "wins everywhere" is measuring an artifact.
- **graphify edges are inferred; codegraph is the last mile.** The default backend infers call edges by name (\~0.8 confidence) — fast and cheap, and on well-named Python it answers correctly the large majority of the time. `codegraph` exists to buy the *last mile* of precision: AST-resolved edges for the cases inference can't be trusted on. That precision is not free. On the SWE-bench Lite pilot, codegraph cost **\~3-4x more tokens than graphify** and on the simpler caller/inheritor tasks frequently ran *below* the baseline; its resolved edge set **diverged from graphify's inferred set on every compared cell** — different, and exact, but not a free upgrade. The takeaway the data supports: **graphify is the default; codegraph is the deliberate escalation when an exact edge is worth paying for**, not an always-on replacement.
- **Sparse call graphs.** On some languages (notably JavaScript/TypeScript) graphify's call graph is sparse; setup detects this and prints a warning pointing you at the `codegraph` backend.
- **Cumulative tokens, not dollars.** TokenMaster optimizes the integral of context size over a task. Billing proxies (premium requests, total token counts) are explicitly *not* the metric.

## Repository layout

```text
token-master-plugin/          The plugin (this is the deliverable)
├── .claude-plugin/
│   └── plugin.json            Plugin manifest
└── skills/token-master/
    ├── SKILL.md               The /token-master command
    ├── setup.py               Installer: builds the graph, installs the host agent
    ├── graphify_mcp.py        Graph-query MCP server
    ├── agent.template.claude.md    Routing agent template (Claude Code format)
    ├── agent.template.copilot.md   Routing agent template (Copilot CLI format)
    │
    ├── headroom_setup.py      Headroom installer (dual-host: hook+MCP / MCP-only)
    ├── headroom_mcp.py        Compression MCP server (compress/retrieve/stats)
    ├── headroom_posttooluse.py    Claude Code auto-compress hook
    ├── headroom_benchmark.py  Self-serve benchmark — measure on your own files
    └── headroom/              The compression engine
        ├── ccr.py             Content-addressed reversible store (the escape hatch)
        ├── router.py          ContentRouter — type detection + never-expand guard
        ├── tokens.py          tiktoken-or-heuristic token meter
        ├── benchmark.py       Benchmark core (file/dir/stdin, JSON, area-under-curve)
        ├── compressors/       json / code / logs / prose compressors
        └── tests/             104 unit tests

sandbox_headroom/             Isolated verification harnesses (never touch real config)
├── measure_impact.py         Real-artifact compression measurement (README numbers)
├── mcp_stdio_smoke.py        MCP protocol conformance via the official client
└── verify_dual_host.py       Dual-host install + end-to-end checks

.claude-plugin/
└── marketplace.json           Plugin marketplace manifest (the packager)

assets/
├── generate_art.py            Deterministic, dependency-free SVG generator
└── tokenmaster-hero.svg       The hero image above (reproducible from a seed)
```

The hero image is generative: it *is* the thesis. The faint tangle is brute-force
search sprawl — context re-read turn after turn — and the single bright path is one
bounded graph-routed query. Regenerate or remix it with:

```bash
python assets/generate_art.py --seed 42
```

## License

[MIT](LICENSE)