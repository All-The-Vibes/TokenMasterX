# Design: a `/command` that runs the token-efficient harness automatically

> Mission context: see [`MISSION.md`](./MISSION.md). This command is how we make the
> efficient path the *default* one — operationalizing the routing layer that is the
> actual product. The graph indexes are swappable suppliers of structure; the routing
> is the load-bearing primitive.

Goal: turn the manual sandbox setup (index a repo → wire the graph MCP → nudge Copilot to
route structural questions to graph tools) into a single reusable command, so any repo gets
the proven token savings (−72% overall, up to −80% on blast-radius tasks) without hand-wiring.

## What "this" actually is (3 moving parts)

From `sandbox-scale/tools/runner.py` the harness is exactly three things:

1. **A graph index** over the repo. Built by Graphify (`graphify` CLI) and/or CodeGraph (AST
   call-graph), then written to **`.token-master/graph.json`**. One-time per repo, refreshed when
   code changes.

> **Convention: all harness-generated files live in a single `.token-master/` directory at the repo
> root** — the graph index (`.token-master/graph.json`), any token/run logs, and meter output. It's a
> per-repo build artifact, so the setup step should add `.token-master/` to the repo's `.gitignore`.
> (Graphify writes to `graphify-out/` by default; the `/token-master` setup step relocates the graph
> into `.token-master/` so there's one predictable, hidden home and nothing else litters the repo.)
2. **A graph MCP server** exposing query tools `find / callers / callees / impact / inheritors /
   explain`. In the sandbox this is `graphify_mcp.py` registered via an `mcp-config.json`:
   ```json
   { "mcpServers": { "graphify": { "type": "stdio", "command": "<python>",
       "args": ["graphify_mcp.py"], "env": { "GRAPH_PATH": "<repo>/.token-master/graph.json" } } } }
   ```
3. **A routing nudge** — one paragraph telling Copilot the graph tools exist and to prefer them
   over grep for callers/inheritors/impact/multi-hop questions, then verify against source file:line.
   **This nudge is load-bearing**: proven routing went 0/15 without it → 8/8 with it.

A `/command` that "runs this automatically" must deliver parts 2 and 3 every session, and ensure
part 1 (the index) exists and is fresh.

## The Copilot CLI mechanisms available (what can actually be a `/command`)

**Authoritative correction (source: `github/docs` `…/customize-copilot/add-skills.md`, ref `86bc2ea…`):**
Copilot CLI **does** support custom slash commands — they are **skills**. Per the docs, you invoke a
skill "by including the skill name in your prompt, preceded by a forward slash" (e.g. `/token-master`).
A skill is a folder with a `SKILL.md`; its directory name becomes the slash command. (`/skills list`,
`/skills info`, `/skills reload` are built-in management commands.) `.prompt.md` files are a *VS Code*
feature, not the CLI — that was the source of an earlier error in this doc.

| Mechanism | File location | Invocation | Can register MCP? | Can inject routing prompt? | Can build index? | Verdict |
|-----------|---------------|------------|-------------------|----------------------------|------------------|---------|
| **Skill** | `~/.copilot/skills/NAME/SKILL.md` (+scripts) | **`/NAME` slash command** (also keyword / auto-load) | ➖ (its script can write MCP config / instruct agent) | ✅ procedural steps + resources | ✅ bundled script (`graphify update`) | **The actual `/command` surface** — user-facing on-switch + setup ritual |
| **Custom agent** | `.github/agents/NAME.agent.md` (project) **or** `~/.copilot/agents/NAME.agent.md` (user, cross-repo) | `/agent` picker, explicit instruction, inference, or `copilot --agent NAME` | ✅ `mcp-servers:` frontmatter (**confirmed** schema) | ✅ agent prompt body (≤30k chars) | ⚠️ only by instructing itself to run the indexer | Best host for the **routing + graph MCP** (subagent, own context window) |
| **Plugin** | repo/marketplace/local package | bundles the above; installs skill→`/NAME` + agent + MCP + hooks | ✅ (bundled) | ✅ (bundled) | ✅ (bundled) | **Best productized delivery** — one installable unit (how ATV ships) |
| **Extension** | `.github/extensions/NAME/extension.mjs` (SDK) | tools/hooks/canvas | ✅ as native tools, or via `onSessionStart` | ✅ `additionalContext` hook auto-injects every session | ✅ in JS | Most powerful, heaviest; no `/slash` of its own (pair with a skill) |
| **Prompt file** | `.github/prompts/*.prompt.md` | `/name` in IDE chat | ❌ | ✅ | ❌ | **VS Code only — not a CLI mechanism** |


### Confirmed custom-agent format (authoritative)

Source: `github/docs` → `content/copilot/reference/custom-agents-configuration.md` and
`content/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli.md`
(ref `86bc2ea1fbe8ab7980af235ec9679950342fe810`). Key corrections vs. the earlier draft of this doc:

- **File extension is `.agent.md`** (not plain `.md`). The filename minus `.agent.md` is the
  programmatic agent name (e.g. `token-master.agent.md` → `copilot --agent token-master`).
- **Two locations**: project `.github/agents/` (travels with the repo, needs a git root) **or**
  user `~/.copilot/agents/` (works across *every* repo). On a name clash the **lowest level wins**
  (project overrides user). For a cross-repo harness — and because a folder-backed session may have
  no git root — **user scope `~/.copilot/agents/` is the more reliable home.**
- **`mcp-servers:` frontmatter is confirmed supported** (the doc only excludes it for VS Code/IDE
  agents, not the CLI). YAML shape mirrors the MCP JSON config:
  ```yaml
  ---
  name: token-master
  description: Routes structural code questions to the graph. Use for callers/impact/inheritors.
  tools: ['graphify/*', 'read', 'search', 'execute']
  mcp-servers:
    graphify:
      type: stdio            # 'stdio' is accepted; maps to cloud 'local'
      command: uv
      args: ['run', '--with', 'mcp', 'python', '<abs path>/graphify_mcp.py']
      tools: ['*']
      env:
        GRAPH_PATH: '${GRAPH_PATH:-.token-master/graph.json}'
  ---
  Prompt body = routing rules (part 3) + Step 0 index check. Max 30,000 chars.
  ```
- **Full frontmatter keys**: `name`, **`description` (required)**, `target`, `tools`, `model`,
  `disable-model-invocation`, `user-invocable`, `infer` (retired), `mcp-servers`, `metadata`.
- **Env-var substitution** in `mcp-servers` supports `$VAR`, `${VAR}`, `${VAR:-default}` (and
  `${{ secrets.X }}` / `${{ vars.X }}` for the cloud agent only). So the graph path can default
  cleanly without a hardcoded sandbox path.
- **`tools` aliases**: `read`, `edit`, `search`, `execute` (shell/powershell), `agent`, `web`,
  `todo`. MCP tools are namespaced `server/tool` or `server/*` (e.g. `graphify/*`). Omit `tools`
  or use `['*']` for all; `[]` disables all.
- **Invocation in the CLI**: `/agent` picker, an explicit instruction ("use the token-master
  agent…"), automatic inference from the `description` (unless `disable-model-invocation: true`),
  or programmatically `copilot --agent token-master -p "…"`. **You must restart the CLI to load a
  newly added agent.**
- Prompt files (`.prompt.md` slash commands) are **IDE/Chat only, not the terminal CLI** — but the CLI
  *does* have a slash-command path: **skills** (`/NAME`). The `/token-master` command is a skill.
- Extensions can't define a literal `/slash` command, but an `onSessionStart` hook returning
  `additionalContext` can inject the routing nudge automatically for *every* turn — the most
  "automatic" option, at the cost of writing/maintaining an SDK extension.

## Recommended architecture

**The user-facing `/command` is a skill; the routing engine is an agent + MCP; ship them together as a plugin.**

1. **`/token-master` skill** — `~/.copilot/skills/token-master/SKILL.md` (+ a `setup` script). This is
   the **slash command** the user types. Its job is the on-switch + setup ritual: confirm `graphify` is
   installed, build/refresh the index (`graphify update <repo>`, no LLM), drop the portable
   `graphify_mcp.py` somewhere stable, and ensure the routing agent is registered. The directory name
   (`token-master`) *is* the command (`/token-master`).

2. **`token-master` custom agent + graph MCP** — `~/.copilot/agents/token-master.agent.md` (user scope,
   works on any repo; optionally also commit `.github/agents/token-master.agent.md` as the repo copy).
   This is the routing engine the skill turns on:
   - `mcp-servers:` block registering the graph MCP (**confirmed supported** — see schema above), run
     portably via `uv run --with mcp python <abs>/graphify_mcp.py` (no venv; `uv` already on PATH).
   - `GRAPH_PATH` defaults to repo-relative `.token-master/graph.json` (MCP servers launch with the
     workspace as CWD), so no hardcoded sandbox path is needed.
   - Prompt body = routing rules (part 3) + "Step 0: if `.token-master/graph.json` is missing or stale,
     rebuild with `graphify update <repo>` before answering."
   - `tools:` scoping, e.g. `['graphify/*', 'read', 'search', 'execute']`.
   - Invoke via `/agent → token-master`, inference from `description`, or `copilot --agent token-master`.
     **Restart the CLI after adding it.**

3. **Package as a plugin** (productized delivery) — a plugin bundles the skill (→ `/token-master`), the
   agent, the graph MCP, and any hooks into one installable unit, exactly how ATV ships `atv-skill-*` /
   `atv-pack-*`. This is how an end user gets the whole harness with one install instead of hand-placing
   three artifacts.

This keeps the **slash-command front door** (the skill) separate from the **routing engine** (agent +
MCP), and the plugin makes the whole thing distributable.

## Feasibility, gaps, and risks

- ✅ **MCP + routing via agent profile — CONFIRMED end-to-end (2026-05-31 smoke test).** A project
  agent (`.github/agents/token-master.agent.md`) registering the graph MCP purely via `mcp-servers:`
  frontmatter was run with `copilot --agent token-master --allow-all -p "…"`. The CLI launched the
  server (`uv run --with mcp python graphify_mcp.py`), the model called the `callers` tool, and it
  returned the correct answer. Independently verified by the server's own call log
  (`.token-master/mcp-calls.log` recorded `callers base`). Sandbox: `sandbox-mcp-smoke/`. **The
  agent-frontmatter MCP path is no longer an unknown — it works.**
- ⚠️ **Index build can't live *inside* an agent profile** (frontmatter has no lifecycle hook). It must
  be a self-issued first step in the prompt (`graphify update`), or a separate setup script. Pick one.
- ✅ **`graphify_mcp.py` is now portable** in design: it reads `GRAPH_PATH` (defaulting to
  `<cwd>/.token-master/graph.json`) and lazy-loads, so no hardcoded sandbox path and it registers
  cleanly even before an index exists. Run it with `uv run --with mcp python …` (no venv).
- ⚠️ **Staleness**: graph index drifts as code changes. Need a freshness check (mtime compare) or a
  `graphify watch <repo>` sidecar / `--rebuild` affordance, else routing returns stale callers.
- ⚠️ **Routing is probabilistic**: 8/8 held *with* the nudge on Django; smaller/odd repos may need a
  stronger nudge or tool-name hints. The negative-control task (T3) correctly stayed a wash.
- ✅ **Portability of the win**: the mechanism (graph replaces many grep turns) is repo-agnostic; the
  *magnitude* will vary with task difficulty and repo size.
- ➖ **Extension path** is viable and the most "automatic" (auto-inject every session) but is the most
  code to own; reserve it for if we want zero-friction, always-on routing without `/agent` selection.

## Open decision

Delivery shape is now clear: **`/token-master` skill (slash-command front door) + routing agent + graph
MCP, bundled as a plugin.** The remaining choices are scope and sequencing:

- **Build order:** ship the skill + agent + MCP loose first (fastest to validate), then wrap as a plugin
  for distribution? Or build the plugin from the start?
- **Setup placement:** index build + MCP-script install inside the skill's setup script (cleanest), vs.
  folded into the agent's "Step 0" (one fewer artifact, slightly slower first run).
- **Empirical check — DONE (2026-05-31):** confirmed the CLI launches the agent's `mcp-servers` graph
  tools end-to-end (project agent + frontmatter MCP, verified by the server's own call log). The
  agent-frontmatter path is proven, not assumed. Sandbox: `sandbox-mcp-smoke/`.

## Sources (authoritative)

All facts above are grounded in first-party GitHub docs and verified local tool behavior:

- Custom-agent reference (frontmatter keys, `mcp-servers` schema, env-var substitution, tool aliases,
  precedence): `github/docs` → `content/copilot/reference/custom-agents-configuration.md`
  (ref `86bc2ea1fbe8ab7980af235ec9679950342fe810`).
- **Skills = CLI slash commands** (invoke a skill with `/NAME`; `/skills list|info|reload|add|remove`
  management commands; skill = folder with `SKILL.md`): `github/docs` →
  `content/copilot/how-tos/copilot-cli/customize-copilot/add-skills.md` (same ref). **Corrects an earlier
  error in this doc that claimed the CLI has no custom slash commands** — it does, via skills. `.prompt.md`
  files are a VS Code feature, not the CLI.
- CLI customization surfaces (skills, custom agents, hooks, MCP, plugins) and that plugins bundle them
  into one installable unit: `github/docs` →
  `content/copilot/how-tos/copilot-cli/customize-copilot/overview.md` and `plugins-creating.md` (same ref).
- `.agent.md` extension, project vs. user locations (`.github/agents/`, `~/.copilot/agents/`),
  invocation methods, restart-to-load: `github/docs` →
  `content/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli.md` and
  `content/copilot/concepts/agents/copilot-cli/about-custom-agents.md` (same ref).
- Index builder is LLM-free and fast: local `graphify --help` (`graphify update <path>` rebuilds
  `<path>/graphify-out/graph.json`; `graphify watch <path>` auto-rebuilds). graphify CLI v0.8.13
  global at `~/.local/bin/graphify`; `uv` on PATH at `~/.local/bin/uv.exe`.
- Harness wiring ground truth (MCP config shape, routing nudge, GRAPH_PATH): local
  `sandbox-scale/tools/runner.py` and `sandbox-scale/tools/graphify_mcp.py`.
- Token result this command operationalizes (−72% overall; T1 −80%, T4 −76%): local
  `evidence/` and `token-efficient-harness-research.md` §7.10.
- CLI flags (`--agent`, `--additional-mcp-config`, `mcp` subcommand): local `copilot --help`.
