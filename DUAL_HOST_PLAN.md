# TokenMaster — Dual-Host (Claude Code + Copilot) Implementation Handoff

> Status: in progress. This document captures the approved plan, the host-format facts verified on
> this machine, and the exact edits, so the work is fully traceable.

## Why this change

TokenMaster is branded for **both Claude Code and GitHub Copilot CLI** (README line 3, MISSION.md),
but the two halves of the repo disagree on the target host:

- **Installer + runtime templates are Copilot-only.** `setup.py` writes the agent + MCP server into
  `$COPILOT_HOME` (`~/.copilot/`), prints "Restart Copilot", and the agent template uses Copilot's
  custom-agent format (MCP servers declared *inline* in the agent frontmatter via `mcp-servers:`).
  `SKILL.md` describes Copilot session memory / `copilot --resume`.
- **README install section is Claude-Code-only.** `/plugin marketplace add` + `/plugin install`,
  "restart Claude Code", `--agent token-master`.

Net effect: a Claude Code user follows the README, installs the plugin, runs `/token-master` — and
the installer silently provisions a **Copilot** home that Claude Code never reads. A Copilot user
has no documented install path at all.

**Decided outcome (user):** support *both, properly* — a host-aware installer plus per-host docs.
**Decided architecture (user):** *symmetric installer* — one `setup.py` that detects/selects the
host and emits the correct format into the correct home.

## Host-format facts (VERIFIED on this machine)

| | Copilot (current) | Claude Code |
|---|---|---|
| Agent home | `~/.copilot/agents/token-master.agent.md` | `~/.claude/agents/token-master.md` |
| Agent frontmatter | `name`, `description`, `tools: ['graphify-nav/*', ...]`, **inline `mcp-servers:` block** | `name`, `description`, `tools` (comma-string), optional `model`/`disallowedTools` — **NO inline MCP block** |
| Frontmatter evidence | current `agent.template.copilot.md` | `~/.claude/agents/explore.md`, `code-reviewer.md` |
| MCP wiring | inline in agent frontmatter | top-level `mcpServers` key in **`~/.claude.json`** |
| MCP stdio schema | `command` / `args` / `env` (inline) | `{ "command", "args", "env" }` — matches existing `context7` entry in `~/.claude.json` |

Existing `~/.claude.json` `mcpServers` already holds: `microsoft-docs` (http), `context7` (stdio),
`telegram-apikey`, `agentmemory`. Claude Code user-scope MCP config lives in `~/.claude.json`, NOT
`~/.claude/settings.json`.

The MCP **server itself** (`graphify_mcp.py`) and its launch command (`uv run --with mcp python
<script>`, `GRAPH_PATH=.token-master/graph.json`) are host-agnostic — only the *declaration format
and location* differ.

## The edits (5 tasks)

1. **`setup.py`** — host selection (`--host=` / `TOKEN_MASTER_HOST` / autodetect / default `claude`);
   `_copilot_home()` → `_host_home(host)`; branch agent emission (Copilot inline template →
   `~/.copilot/agents/token-master.agent.md`; Claude template + `~/.claude.json` mcpServers merge →
   `~/.claude/agents/token-master.md`); host-correct summary line.
2. **Templates** — `agent.template.md` → `agent.template.copilot.md` (done); add
   `agent.template.claude.md` (Claude frontmatter, no inline MCP, Claude-flavored memory section).
3. **`SKILL.md`** — host-neutral wording.
4. **`README.md`** — dual install paths (Claude Code + Copilot CLI), fix line-75 contradiction.
5. **`graphify_mcp.py`** — soften hard "Copilot" comment mentions to "the host CLI".

## Reuse (not re-implemented)
- `graphify update` build + relocate to `.token-master/graph.json`
- `_ensure_codegraph` / codegraph index / sparse-graph gate
- `_strip_codegraph_from_template` (Copilot as-is; Claude variant for the no-inline-MCP case)
- path-substitution block (`__UV__`/`__MCP_SCRIPT__`/`__NODE__`/`__CG_SHIM__`)

## Verification
1. Copilot regression: `python setup.py <repo> --host=copilot` → inline-MCP agent in `~/.copilot`, summary "Restart Copilot".
2. Claude path: `python setup.py <repo> --host=claude` → Claude-frontmatter agent (no inline MCP) in `~/.claude/agents`, `graphify-nav` in `~/.claude.json` mcpServers, summary "Restart Claude Code".
3. codegraph-absent: no `codegraph` in tools, no codegraph mcpServers entry.
4. Live routing (Claude): restart, "who calls X?" answered from a `graphify-nav` MCP call.
5. Idempotency: re-run → no duplicates.
6. README Copilot path is followable without reading source.
