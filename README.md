# TokenMaster

![TokenMaster — Half the tokens. Half the cold-start cost. Prompt-cache friendly on the real GitHub Copilot CLI.](assets/tokenmaster-hero.svg)

**TokenMaster** cuts the tokens and API cost that **GitHub Copilot CLI** spends on coding tasks—while keeping provider prompt caching and answer quality intact.

Across **554 real Copilot CLI sessions** with **GPT-6 Astra** and **Claude Opus 5.5**, TokenMaster cut **raw tokens by 38% to 58%** and **cold-start cost by 34% to 54%** (up to **80%** back to back), passing **88 of 88** tasks on Copilot CLI `1.0.98`.

---

## Quickstart

### 1. Install the GitHub Copilot CLI plugin

```powershell
copilot plugin marketplace add All-The-Vibes/TokenMasterX
copilot plugin install token-master@token-master

# Or load from a local checkout
copilot --plugin-dir ./token-master-plugin
```

### 2. Prepare the runtime (once)

TokenMaster's MCP server and hook run on their own Python 3.12 environment with exact pinned packages; setup rejects an interpreter whose packages differ from the pins. Setup also needs `graphify` on `PATH` and OpenAI's `cl100k_base` vocabulary in tiktoken's cache. If you set `COPILOT_HOME`, use it in place of `$HOME\.copilot`.

```powershell
$plugin = "$HOME\.copilot\installed-plugins\token-master\token-master"  # or ./token-master-plugin in a checkout
$runtime = "$HOME\.copilot\token-master-runtime"
uv venv --python 3.12 $runtime
& "$runtime\Scripts\python.exe" -m ensurepip
& "$runtime\Scripts\python.exe" -m pip install -r "$plugin\requirements-runtime.txt"
& "$runtime\Scripts\python.exe" -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
uv tool install graphifyy  # the PyPI package that provides the graphify command
```

The `tiktoken` line downloads the 1.7 MB vocabulary once. Setup verifies its SHA-256 and never downloads anything itself. Offline, copy a verified `cl100k_base.tiktoken` to the machine and set `BRAINSPACE_TOKENIZER_FILE` to its path before you start Copilot, or pass it to `brainspace_setup.py` with `--tokenizer-file`.

### 3. Run `/token-master` in your repository

Start `copilot` in the repository and type **`/token-master`**. It indexes the repository with [Graphify](https://github.com/Graphify-Labs/graphify), which takes a few minutes on a large repository the first time. Then it runs two installers with the runtime: `setup.py` wires up `tokenmaster-nav`, and `brainspace_setup.py` adds the `view` output-shaping hook, the launcher, and `/tokenomics`. Approve the commands when Copilot asks. Besides `$HOME\.copilot`, they write `.token-master/` and `graphify-out/` in the repository and add any missing `.gitignore` lines for them.

Type **`/tokenomics`** anytime to view your token usage, GitHub charges, and TokenMaster savings.

### 4. Start Copilot CLI with dynamic tool routing (recommended)

Once `/token-master` has configured your host (or after running `brainspace_setup.py --host copilot` manually), start `copilot` through the installed launcher so unused auxiliary tool schemas are pruned automatically. Use the runtime's Python: in BYOK mode the launcher's shaping needs its `tiktoken`.

```powershell
& "$HOME\.copilot\token-master-runtime\Scripts\python.exe" "$HOME\.copilot\token-master\brainspace_copilot_bridge.py" -- copilot
```

- **Normal GitHub sign-in:** Applies **Dynamic Tool Routing** (`--excluded-tools`), **Graph Code Navigation** (`tokenmaster-nav`), the **one-shot `view` output hook**, and **`/tokenomics`**.
- **BYOK mode (`COPILOT_PROVIDER_BASE_URL` set):** Also activates the local **prompt-cache bridge** (`stable_session_prefix` + wire-level `rg`/`glob` shaping).
- **Keep all built-in tools:** Pass `--all-tools` before `--` (or set `TOKENMASTER_KEEP_TOOLS=agents,sql`).

## Uninstall

Remove TokenMaster's Copilot configuration before you remove the plugin, because the uninstall scripts ship inside it:

1. In Copilot CLI, type **`/token-master uninstall`**. It runs `setup.py --host copilot --uninstall` and `brainspace_setup.py --host copilot --uninstall`, which remove only what TokenMaster added: `tokenmaster-nav`, its agent, the `view` hook, and `/tokenomics`.
2. Run `copilot plugin uninstall token-master@token-master`, then `copilot plugin marketplace remove token-master`. If you installed with the older direct command, run `copilot plugin uninstall token-master` instead.
3. Optional, with Copilot closed: delete `$HOME\.copilot\token-master` (launcher and launch log) and `$HOME\.copilot\token-master-runtime`. Also delete the `*.token-master-backup-*` and `*.token-master-owned.json` files that uninstall leaves next to `mcp-config.json`, `settings.json` and `agents\token-master.agent.md`; the backups are full copies of those files, including other servers' settings. In each indexed repository, delete `.token-master` and its `.gitignore` line, and `graphify-out` with its line unless you use Graphify on its own.

If you already uninstalled the plugin, install it again, run step 1, then uninstall it.

---

## How It Works

1. **Dynamic Tool Routing (`brainspace_copilot_bridge.py`)** — Stock Copilot CLI sends JSON schemas for SQL scratchpads, session-store SQL, background job managers, subagents, skills, and CLI docs on every turn (~5,500 to ~11,500 tokens/call). TokenMaster inspects your prompt, flags (`--agent`, `--resume`), and installed skills/agents—keeping the capabilities your task needs and pruning the rest via `--excluded-tools`.
2. **Graph Code Navigation (`tokenmaster-nav`)** — Combines [Graphify](https://github.com/safishamsi/graphify) call edges with a local SQLite AST index into 3 compact tools (`locate`, `read_symbol`, `impact`), capped under 2,400 tokens. Answers "who calls X?" in one turn instead of dumping 100k+ tokens of `rg`.
3. **Cache-Safe Output Shaping (`request_policy.py`)** — Folds `rg`/`glob` output losslessly and compacts oversized `view` reads **once** when appended. Never rewrites earlier messages, so the provider's prompt cache stays valid.
4. **Cache-Stable BYOK Bridge (`stable_session_prefix`)** — Moves the per-session `Session folder:` UUID out of the system prompt in BYOK mode so sessions in the same folder share the cached prompt on call 1.

---

## `/tokenomics` — `ccusage` for Copilot CLI

Track your measured Copilot CLI tokens, GitHub billing (`total_nano_aiu`), and estimated TokenMaster savings locally from `<COPILOT_HOME>/session-store.db`:

```powershell
# Run directly in any terminal (spends 0 model tokens)
python $HOME\.copilot\token-master\tokenomics.py
python $HOME\.copilot\token-master\tokenomics.py session --since 20261020
```

Or type `/tokenomics` inside an interactive Copilot CLI session.

```text
┌──────────┬───────────────┬──────────────┬────────────┬──────────────┬────────────────┬───────────────┐
│ Session  │ Models        │ Total Tokens │ Cost (USD) │ TokenMaster  │ Saved Tokens ≈ │ Saved (USD) ≈ │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 579e5c15 │ • gpt-6-astra │       22,278 │      $0.15 │ -            │              - │             - │
│ 9b2700f4 │ • gpt-6-astra │       16,847 │      $0.09 │ lean+bridge  │         16,674 │         $0.01 │
│ 5690993e │ • gpt-6-astra │       16,844 │      $0.02 │ lean+bridge  │         16,674 │         $0.07 │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ Total    │               │       55,969 │      $0.26 │ 2/3 sessions │         33,348 │         $0.08 │
└──────────┴───────────────┴──────────────┴────────────┴──────────────┴────────────────┴───────────────┘
```

---

## Benchmark Summary (Real GitHub Copilot CLI)

All runs used the real `copilot.exe` binary against `api.githubcopilot.com`, verified against GitHub's per-call `copilot_usage` bills. **Cold Cost** prices every session's first call as a cache miss; **Back-to-Back Cost** runs sessions consecutively in one folder.

| Benchmark | CLI Version | Model | Raw Tokens (`Stock → TM`) | Cold Cost | Back-to-Back Cost | Passed (`Stock vs TM`) |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| **This Repo (29 tasks, pre-registered)** | `1.0.98` | `gpt-6-astra` | **−49.5%** (`2.45M → 1.24M`) | **−41.5%** (`$8.91 → $5.21`) | **−50.2%** (`$6.83 → $3.40`) | **29/29 vs 29/29** |
| **This Repo (29 tasks, pre-registered)** | `1.0.98` | `claude-opus-5.5` | **−38.0%** (`2.67M → 1.66M`) | **−34.0%** (`$4.23 → $2.79`) | **−40.1%** (`$2.72 → $1.63`) | **29/29 vs 29/29** |
| **Django 5.2 (15 tasks, pre-registered)** | `1.0.98` | `gpt-6-astra` | **−58.5%** (`708k → 294k`) | **−53.5%** (`$3.40 → $1.58`) | **−70.7%** (`$2.36 → $0.69`) | **15/15 vs 15/15** |
| **Django 5.2 (15 tasks, pre-registered)** | `1.0.98` | `claude-opus-5.5` | **−53.7%** (`990k → 458k`) | **−46.0%** (`$1.81 → $0.98`) | **−61.2%** (`$1.11 → $0.43`) | **15/15 vs 15/15** |
| **Django 5.2 (45 tasks, exploratory)** | `1.0.78-3` | `gpt-6-astra` | **−53.4%** (`2.42M → 1.13M`) | **−49.5%** (`$11.55 → $5.83`) | **−79.9%** (`$11.55 → $2.33`) | **45/45 vs 44/45** |
| **Django 5.2 (45 tasks, exploratory)** | `1.0.78-3` | `claude-opus-5.5` | **−51.6%** (`3.46M → 1.67M`) | **−46.0%** (`$6.14 → $3.31`) | **−60.8%** (`$3.31 → $1.30`) | **45/45 vs 44/45** |

---

## Experimental Status & Documentation

> **Experimental Disclaimer:** TokenMaster is an experimental research toolkit, not an official GitHub product. Default GitHub routing applies Dynamic Tool Routing, Graph Navigation (`tokenmaster-nav`), and the `view` output hook; the prompt-cache bridge requires BYOK mode (`COPILOT_PROVIDER_BASE_URL`). In interactive TUI sessions started without `-p`, pass `--all-tools` or `TOKENMASTER_KEEP_TOOLS` if you need subagents or background PowerShell polling mid-session.

All full experimental reports, pre-registered protocols, negative results (`v1`–`v5`), and raw evidence live under `token-master-plugin/docs/` and `evidence/`:

- **[Real Copilot CLI Results (`1.0.98` & `1.0.78-3`)](token-master-plugin/docs/COPILOT_CLI_RESULTS.md)** · **[Pre-Registered `1.0.98` Protocol (PRS-6)](token-master-plugin/docs/PRS6_PROTOCOL.md)**
- **[Launcher & BYOK Bridge Guide](token-master-plugin/docs/COPILOT_BRIDGE.md)** · **[`/tokenomics` Dashboard & Estimator Validation](token-master-plugin/docs/TOKENOMICS.md)**
- **[Replica Studies & Negative Results](token-master-plugin/docs/README.md):** [PRS-4](token-master-plugin/docs/PRS4_RESULTS.md) · [PRS-3](token-master-plugin/docs/PRS3_RESULTS.md) · [PRS-2](token-master-plugin/docs/PRS2_RESULTS.md) · [PRS-1 (why history rewriting fails)](token-master-plugin/docs/PRS1_RESULTS.md)
- **[15-Minute Demo Script](docs/DEMO_SCRIPT.md)** · **[Interactive HTML Demo Deck](docs/tokenomics-demo-slide.html)**
