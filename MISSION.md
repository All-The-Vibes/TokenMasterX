# TokenMaster — Mission

## The thesis

**We are redefining token economics at the harness level.**

The harness is the unit of intervention. Not the model, not the prompt, not the user —
the **harness**: the layer that decides *what context the model sees on every turn.*
Today that layer is naive. It hands the model a growing transcript and lets it grep its
way to understanding, re-paying for the entire accumulated context on every single turn.
We treat that as an economic defect to be engineered away, not an inevitability to be
billed for. Our work is to attack that waste structurally: \*\*the model should pay once to
understand structure, then never again.\*\*

## What "token economics" means here

A token is not a billing line — it is **work the model is forced to do.** Every token in
the context window is re-read, re-attended, and re-reasoned-over on each turn. The cost
that matters is therefore not *tokens sent once* but \*\*cumulative tokens processed to
finish a task\*\* — context size summed across every turn until done.

This reframing is the whole project. It changes what counts as a win:

- The naive harness "saves" nothing by being short-per-turn if it takes 40 turns of
  grep, because each turn re-processes a larger and larger working set.
- A graph-routed harness that answers the same question in 3–13 turns with a small,
  stable working set wins **even if any single turn looks comparable** — because the
  cumulative integral collapses.

We proved this on Django (992 `.py` files, hard multi-hop tasks): \*\*−72% cumulative
input tokens overall (3.5×), up to −80% (5.0×) on blast-radius tasks\*\*, with no
correctness regression and a negative-control task that correctly came out a wash. That
last point is the mission in miniature — \*\*we win by changing the economics of hard
traversal, and we honestly win nothing when traversal isn't needed.\*\*

## What we are actually building

A harness layer that \*\*routes the model away from re-derivation and toward
pre-computed structure\*\*:

1. **Spatial economics — graph over grep.** Pre-index the repo into a queryable
   structure (call graph / knowledge graph) so "who calls this, what breaks if I change
   it, where does this inherit from" is *one bounded query*, not an unbounded
   re-reading loop. This is where the 3.5–5× lives.
2. **Temporal economics — recall over re-establishment.** Don't re-read history to
   rebuild context across sessions. Read the harness's own memory of what was already
   understood. (claude-mem's insight, collapsed to a thin layer because Copilot already
   maintains the store.)
3. **Routing as the load-bearing primitive.** A graph the model never queries saves
   nothing — routing was 0/15 without an explicit nudge and 8/8 with it. The harness's
   job is not to *offer* efficient tools but to \*make the efficient path the default
   one.\* The routing layer is the product; the indexes are interchangeable suppliers.

Graphify and CodeGraph supply the **graph structure** (point 1); claude-mem supplies the **memory-recall pattern** (point 2). We use these three concepts as building blocks for the routing layer — the economic discipline we impose at the harness level: the model should never pay twice to understand the same thing.

## Principles

- **Cumulative tokens, not per-turn tokens, not dollars.** We optimize the integral of
  context size over a task. Billing proxies (premium requests, `total_tokens`) are
  explicitly *not* the metric and have misled us before.
- **Honest negatives are the proof of an honest method.** If a task doesn't need
  traversal, the harness must come out neutral — and ours did (+4% on the control). A
  harness that "wins everywhere" is measuring an artifact.
- **Routing is mandatory, structure is fungible.** Whether structure comes from
  Graphify, CodeGraph, or something we write next, the value is in reliably routing the
  model to it. Treat indexes as swappable.
- **The harness owns the context budget.** Every token the model sees is a decision the
  harness made. We are accountable for that budget the way an operator is accountable
  for spend.

## Non-goals

- Not a billing/premium-request optimizer — token economics ≠ invoice economics.
- Not a universal speedup — we explicitly do **not** claim wins on short structural
  questions that grep answers in \~3 turns.

## How to read this repo through the mission

- `token-efficient-harness-research.md` — the evidence base (§7.10 is the controlling
  result that grounds every claim above).
- `harness-command-design.md` — operationalizing the routing layer into a reusable
  `/command`.
- `evidence/` — the reproducible measurement of the cumulative-token reduction.
- `sandbox-scale/` — where routing and scale were proven in isolation.

**One line:** TokenMaster makes re-derivation economically illegal at the harness level —
the model pays once to understand structure, then never again.