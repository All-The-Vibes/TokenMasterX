# TokenMaster

A token-efficient code-understanding harness for [Claude Code](https://docs.claude.com/en/docs/claude-code) and GitHub Copilot CLI.

TokenMaster answers structural questions about a codebase — *who calls this function, what breaks if I change it, where does this class inherit from* — by routing them to a **prebuilt code graph** instead of letting the model grep and re-read files turn after turn. The result is a large reduction in *cumulative* context tokens on hard traversal tasks, with no correctness regression.

```
/token-master
```

That command builds the index for the current repository and turns on routing.

---

## The problem it solves

Every token in the context window is re-read and re-reasoned-over on each turn. So the cost that matters is not *tokens sent once* but **cumulative tokens processed to finish a task** — context size summed across every turn until done.

A naive harness saves nothing by being short-per-turn if it takes 40 turns of grep to trace a call graph, because each turn re-processes a larger and larger working set. A graph-routed harness answers the same question in a handful of bounded queries with a small, stable working set — so the cumulative integral collapses.

On Django (992 `.py` files, hard multi-hop tasks) the routed harness measured **−72% cumulative input tokens overall (3.5×), up to −80% (5.0×)** on blast-radius tasks, with no correctness regression — and a negative-control task that correctly came out a wash (grep already answers it in ~3 turns).

This replicated on independent SWE-bench Lite repositories. Across **scikit-learn and sympy** (36 live Copilot runs, three navigation tasks × two repos × two reps × three arms), graphify-routed navigation pooled **−73.1% cumulative input tokens (3.71×)** versus the grep baseline — the multi-repo average landing slightly below the Django-only figure, which is the more honest number to quote. The win concentrates exactly where the thesis predicts: blast-radius impact analysis pooled **~7.8× (−87%)**, because grep balloons to 200k+ tokens tracing change impact while the graph answers in ~27k. Routing held at **12/12** on every graphify cell — the grep-fallback failure mode did not occur once.

## How it works

TokenMaster installs a **routing agent** that prefers graph queries over grep, backed by two interchangeable graph suppliers and the host CLI's own session memory:

| Layer | Supplier | Role |
|-------|----------|------|
| **Semantic-spatial** (default) | [`graphify`](https://github.com/safishamsi/graphify) | Fast, no-LLM structural index. Answers callers / callees / impact / inheritors from inferred edges. The cheap default. |
| **Precise-spatial** (last-mile) | [`@colbymchenry/codegraph`](https://www.npmjs.com/package/@colbymchenry/codegraph) | AST-resolved call edges. The precision escalation: when an inferred edge isn't trustworthy enough — precision-critical impact analysis, or sparse call graphs (common in JS/TS) where name-inference under-connects. Costs more tokens to buy exact edges. |
| **Temporal** | host CLI session memory | Native cross-session recall — no extra server. |

The routing layer is the product; the indexes are interchangeable suppliers. A graph the model never queries saves nothing, so the harness makes the efficient path the *default* one rather than merely offering it.

## Installation

TokenMaster is a Claude Code plugin distributed through a plugin marketplace.

```
/plugin marketplace add shyamsridhar123/TokenMasterX
/plugin install token-master@token-master
```

Then, inside any repository you want to index:

```
/token-master
```

### Prerequisites

- **[`graphify`](https://github.com/safishamsi/graphify)** — the default graph backend. Install with [`uv`](https://docs.astral.sh/uv/):
  ```
  uv tool install graphify
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

> **Note:** The routing agent loads at CLI startup. After the first install, restart Claude Code (or start it with `--agent token-master`) for routing to take effect.

## What gets written

`/token-master` is conservative about your working tree:

- The code graph is stored at `.token-master/graph.json` inside the repo.
- `.token-master/` and `.codegraph/` are added to the repo's `.gitignore`.
- The routing agent and graph server are installed to your user-scope CLI home, not the repo.

## Honest limitations

- **Not a universal speedup.** TokenMaster wins on hard, multi-hop traversal. On short structural questions that grep answers in ~3 turns, it is correctly *neutral*. A harness that "wins everywhere" is measuring an artifact.
- **graphify edges are inferred; codegraph is the last mile.** The default backend infers call edges by name (~0.8 confidence) — fast and cheap, and on well-named Python it answers correctly the large majority of the time. `codegraph` exists to buy the *last mile* of precision: AST-resolved edges for the cases inference can't be trusted on. That precision is not free. On the SWE-bench Lite pilot, codegraph cost **~3–4× more tokens than graphify** and on the simpler caller/inheritor tasks frequently ran *below* the grep baseline; its resolved edge set **diverged from graphify's inferred set on every compared cell** — different, and exact, but not a free upgrade. The takeaway the data supports: **graphify is the default; codegraph is the deliberate escalation when an exact edge is worth paying for**, not an always-on replacement.
- **Sparse call graphs.** On some languages (notably JavaScript/TypeScript) graphify's call graph is sparse; setup detects this and prints a warning pointing you at the `codegraph` backend.
- **Cumulative tokens, not dollars.** TokenMaster optimizes the integral of context size over a task. Billing proxies (premium requests, total token counts) are explicitly *not* the metric.

## Repository layout

```
token-master-plugin/          The plugin (this is the deliverable)
├── .claude-plugin/
│   └── plugin.json            Plugin manifest
└── skills/token-master/
    ├── SKILL.md               The /token-master command
    ├── setup.py               Installer: builds the graph, installs the agent
    ├── graphify_mcp.py        Graph-query MCP server
    └── agent.template.md      The routing agent template

.claude-plugin/
└── marketplace.json           Plugin marketplace manifest (the packager)
```

## License

[MIT](LICENSE)
