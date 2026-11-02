![TokenMasterX for GitHub Copilot. About half the tokens with --lean: up to 53% fewer tokens and up to 54% lower cold-start cost. 9 to 29% fewer tokens with no flags.](assets/tokenmasterx-hero.svg?v=2)

<p align="center">
  <b>GitHub Copilot on about half the tokens with <code>--lean</code>, and 9 to 29% fewer with no flags.</b><br>
  With <code>--lean</code> it drops 13 built-in tool definitions unless the prompt asks for their family; it finds and reads code through a symbol graph instead of grep dumps and whole-file reads, and trims tool output without breaking the provider's prompt cache.<br>
  Its invariants are <a href="#proof-driven-development">theorems checked by Lean 4</a>, held to the code by conformance tests.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> · <a href="#how-it-works">How it works</a> · <a href="#proof-driven-development">Proofs</a> · <a href="#benchmark-summary-github-copilot-cli">Benchmarks</a> · <a href="https://all-the-vibes.github.io/TokenMasterX/">Interactive deck</a>
</p>

<p align="center"><sub>Measured November 1, 2026 under GitHub's default routing, on Copilot CLI 1.0.105 with GPT-6 Astra, on short Django caller lookups. Each saving is against its own stock run on the same day. "Up to" is the best pooled result of any run under default routing: 53% fewer tokens and 54% lower cold-start cost, with 95% CIs of 48 to 57% and 53 to 56%. Runs through an evaluation relay on an older build went as high as 58.5% fewer tokens (table below). The no-flags range is the 95% CI of its run; the point estimate is 19%. The cost figure prices each session's first call as a cache miss; the bill itself fell 47% with <code>--lean</code>. Token counts and charges come from GitHub's own per-call records.</sub></p>

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

### 4. Start Copilot CLI through the launcher

Once `/token-master` has configured your host (or after running `brainspace_setup.py --host copilot` manually), start `copilot` through the installed launcher. Use the runtime's Python: in BYOK mode the launcher's shaping needs its `tiktoken`.

```powershell
& "$HOME\.copilot\token-master-runtime\Scripts\python.exe" "$HOME\.copilot\token-master\brainspace_copilot_bridge.py" -- copilot
```

- **Normal GitHub sign-in:** **Graph Code Navigation** (`tokenmaster-nav`), the **one-shot `view` output hook** and **`/tokenomics`** work in any Copilot CLI session once installed; the launcher adds **Dynamic Tool Routing** (`--excluded-tools`) with `--lean`.
- **BYOK mode (`COPILOT_PROVIDER_BASE_URL` set):** Also activates the local **prompt-cache bridge** (`stable_session_prefix` + wire-level `rg`/`glob` shaping).
- **Lean tool set is opt-in:** By default the launcher sends every built-in Copilot CLI tool. Add `--lean` before `--` to remove 13 auxiliary tool definitions unless the prompt asks for their family. The published savings were measured with the lean tool set on, so they apply with `--lean`. With it, `TOKENMASTER_KEEP_TOOLS=agents,sql` keeps tool families. `--all-tools` is still accepted and changes nothing.

## Uninstall

Remove TokenMaster's Copilot configuration before you remove the plugin, because the uninstall scripts ship inside it:

1. In Copilot CLI, type **`/token-master uninstall`**. It runs `setup.py --host copilot --uninstall` and `brainspace_setup.py --host copilot --uninstall`, which remove only what TokenMaster added: `tokenmaster-nav`, its agent, the `view` hook, and `/tokenomics`.
2. Run `copilot plugin uninstall token-master@token-master`, then `copilot plugin marketplace remove token-master`. If you installed with the older direct command, run `copilot plugin uninstall token-master` instead.
3. Optional, with Copilot closed: delete `$HOME\.copilot\token-master` (launcher and launch log) and `$HOME\.copilot\token-master-runtime`. Also delete the `*.token-master-backup-*` and `*.token-master-owned.json` files that uninstall leaves next to `mcp-config.json`, `settings.json` and `agents\token-master.agent.md`; the backups are full copies of those files, including other servers' settings. In each indexed repository, delete `.token-master` and its `.gitignore` line, and `graphify-out` with its line unless you use Graphify on its own.

If you already uninstalled the plugin, install it again, run step 1, then uninstall it.

---

## How It Works

1. **Dynamic Tool Routing (`brainspace_copilot_bridge.py --lean`)** — Opt-in. Stock Copilot CLI sends JSON schemas for SQL scratchpads, session-store SQL, background job managers, subagents, agent workflows, skills, and CLI docs on every turn (~5,500 to ~11,500 tokens/call). With `--lean`, TokenMaster removes those 13 tools via `--excluded-tools`, and keeps a family when your prompt, flags (`--agent`, `--resume`) or installed skills and agents ask for it. Those are keyword rules, and they miss some phrasings. Without `--lean`, every built-in tool is sent.
2. **Graph Code Navigation (`tokenmaster-nav`)** — Combines [Graphify](https://github.com/safishamsi/graphify) call edges with a local SQLite AST index into 3 compact tools (`locate`, `read_symbol`, `impact`), capped under 2,400 tokens. Answers "who calls X?" in one turn instead of dumping 100k+ tokens of `rg`. Covers Python and Rust today.
3. **Cache-Safe Output Shaping (`request_policy.py`)** — Folds `rg`/`glob` output losslessly and compacts oversized `view` reads **once** when appended. Never rewrites earlier messages, so the provider's prompt cache stays valid.
4. **Cache-Stable BYOK Bridge (`stable_session_prefix`)** — Moves the per-session `Session folder:` UUID out of the system prompt in BYOK mode so sessions in the same folder share the cached prompt on call 1.

The invariants behind these four are proved in Lean 4. See [Proof-driven development](#proof-driven-development).

---

## Proof-driven development

The savings in this README are measurements. The invariants behind the mechanisms are proved. Each invariant is stated as a theorem in Lean 4 ([`proofs/`](proofs/README.md)), checked by Lean's kernel, and then held to the Python by conformance tests. Code and proofs change in the same pull request: [#18](https://github.com/All-The-Vibes/TokenMasterX/pull/18), [#19](https://github.com/All-The-Vibes/TokenMasterX/pull/19) and [#20](https://github.com/All-The-Vibes/TokenMasterX/pull/20), the last three to change routing, each updated the proofs write-up and the conformance tests.

| Claim | Main Lean theorems |
| :--- | :--- |
| The BYOK bridge never changes bytes the provider already cached | `Cache.bridge_prefix_stable`, `Cache.cache_prefix_kept` |
| With policy v6 and no guidance, the runtime never changes an earlier message, unless shaping would pass a `max_input_tokens` cap | `Cache.shaping_prefix_stable` |
| Shaping never makes a tool result bigger, in tokens or in bytes | `Shaping.guard_never_expands`, `Shaping.request_bytes_never_grow` |
| Policies v1 to v4 never grow a request or touch a protected message | `Policy.greedy_never_expands`, `Policy.protected_unchanged` |
| The `rg` and glob folds are lossless | `Folds.unfoldPaths_foldPaths`, `Folds.unfold_foldSearchChecked` |
| Routing runs only with `--lean`, drops only auxiliary tools, and keeps every family whose trigger fires | `Routing.default_excludes_nothing`, `Routing.excluded_subset_lean`, `Routing.fired_family_kept` |
| A resume keeps its session's tool list | `Routing.resume_same_list`, `Routing.resume_chain_keeps_first_list` |
| Sessions in one folder share a system prompt | `SessionPrefix.system_same_across_sessions` |
| Navigation results stay under 2,400 tokens | `NavCap.assemble_le` |
| The measurement method has the properties the protocol relies on | `Measurement.cold_term_is_coldened_charge`, `Measurement.resample_within_task_range`, `Measurement.hero_monotone` |

### How it is validated

- **Lean's kernel checks every proof.** A clean `lake build` passes on Lean 4.35.0 with the core library only. No theorem depends on `sorry`, and the only axioms in use are `propext`, `Classical.choice` and `Quot.sound`. The 24 numbered theorems in the write-up rest on 46 public theorems and 27 private lemmas in 8 files.
- **29 conformance tests run the real Python.** [`test_proof_conformance.py`](token-master-plugin/skills/token-master/tests/test_proof_conformance.py) calls the code on generated inputs and on the recorded study data, and each test names the theorem it supports.
- **Every assumption is written down.** The write-up lists the 15 hypotheses the models take from the code, and marks each as tested, read from the code, or assumed.
- **Gaps are recorded as findings.** Writing the proofs found 8 gaps between a claim and the code. 5 are fixed, including navigation results that reached 2,401 tokens against a 2,400-token cap. 3 are open and published, and two of them have a test that reproduces them.

A proof covers a model of the code, not the Python itself, which is why the conformance tests and the assumptions table exist. The [benchmarks](#benchmark-summary-github-copilot-cli) below are the measured savings. The [interactive deck](https://all-the-vibes.github.io/TokenMasterX/#proofs) walks through the proofs claim by claim.

To check it yourself, install Lean 4 with [elan](https://github.com/leanprover/elan), then run:

```bash
cd proofs && lake build
cd token-master-plugin/skills/token-master && python -m pytest tests/test_proof_conformance.py
```

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

## Benchmark Summary (GitHub Copilot CLI)

All runs used the `copilot.exe` binary against GitHub's Copilot API. The November 1 rows ran under Copilot CLI's default GitHub routing and read each call's tokens and charge from Copilot CLI's own per-call records; the older rows went through an evaluation relay and were checked against GitHub's per-call `copilot_usage` bills. Every TokenMaster run had the lean tool set on except the **no flags** row, which measures the launcher's default since it made `--lean` opt-in. **Cold Cost** prices every session's first call as a cache miss; **Back-to-Back Cost** runs sessions consecutively in one folder.

| Benchmark | CLI Version | Model | Raw Tokens (`Stock → TM`) | Cold Cost | Back-to-Back Cost | Passed (`Stock vs TM`) |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| **Django 5.2 (15 tasks), default routing, `--lean`, Nov 1** | `1.0.105` | `gpt-6-astra` | **−52.6%** (`703k → 333k`) | **−54.4%** (`$3.74 → $1.71`) | **−47.3%** (`$2.29 → $1.21`) | **15/15 vs 15/15** |
| **Django 5.2 (15 tasks), default routing, no flags, Nov 1** | `1.0.105` | `gpt-6-astra` | **−19.1%** (`769k → 622k`) | **−13.9%** (`$3.85 → $3.32`) | **−24.4%** (`$2.40 → $1.81`) | **15/15 vs 15/15** |
| **This Repo (29 tasks, pre-registered)** | `1.0.98` | `gpt-6-astra` | **−49.5%** (`2.45M → 1.24M`) | **−41.5%** (`$8.91 → $5.21`) | **−50.2%** (`$6.83 → $3.40`) | **29/29 vs 29/29** |
| **This Repo (29 tasks, pre-registered)** | `1.0.98` | `claude-opus-5.5` | **−38.0%** (`2.67M → 1.66M`) | **−34.0%** (`$4.23 → $2.79`) | **−40.1%** (`$2.72 → $1.63`) | **29/29 vs 29/29** |
| **Django 5.2 (15 tasks, pre-registered)** | `1.0.98` | `gpt-6-astra` | **−58.5%** (`708k → 294k`) | **−53.5%** (`$3.40 → $1.58`) | **−70.7%** (`$2.36 → $0.69`) | **15/15 vs 15/15** |
| **Django 5.2 (15 tasks, pre-registered)** | `1.0.98` | `claude-opus-5.5` | **−53.7%** (`990k → 458k`) | **−46.0%** (`$1.81 → $0.98`) | **−61.2%** (`$1.11 → $0.43`) | **15/15 vs 15/15** |
| **Django 5.2 (45 tasks, exploratory)** | `1.0.78-3` | `gpt-6-astra` | **−53.4%** (`2.42M → 1.13M`) | **−49.5%** (`$11.55 → $5.83`) | **−79.9%** (`$11.55 → $2.33`) | **45/45 vs 44/45** |
| **Django 5.2 (45 tasks, exploratory)** | `1.0.78-3` | `claude-opus-5.5` | **−51.6%** (`3.46M → 1.67M`) | **−46.0%** (`$6.14 → $3.31`) | **−60.8%** (`$3.31 → $1.30`) | **45/45 vs 44/45** |

---

## Experimental Status & Documentation

> **Experimental Disclaimer:** TokenMaster is an experimental research toolkit, not an official GitHub product. Default GitHub routing applies Graph Navigation (`tokenmaster-nav`) and the `view` output hook, and Dynamic Tool Routing only with `--lean`; the prompt-cache bridge requires BYOK mode (`COPILOT_PROVIDER_BASE_URL`). With `--lean`, in interactive TUI sessions started without `-p`, set `TOKENMASTER_KEEP_TOOLS` or leave out `--lean` if you need subagents, agent workflows or background PowerShell polling mid-session.

All full experimental reports, pre-registered protocols, negative results (`v1`–`v5`), and raw evidence live under `token-master-plugin/docs/` and `evidence/`:

- **[Copilot CLI Results (`1.0.105`, `1.0.98` & `1.0.78-3`)](token-master-plugin/docs/COPILOT_CLI_RESULTS.md)** · **[Pre-Registered `1.0.98` Protocol (PRS-6)](token-master-plugin/docs/PRS6_PROTOCOL.md)**
- **[Interactive deck](https://all-the-vibes.github.io/TokenMasterX/)** (results, proofs, install) · **[Lean 4 proofs](proofs/README.md)**
- **[Launcher & BYOK Bridge Guide](token-master-plugin/docs/COPILOT_BRIDGE.md)** · **[`/tokenomics` Dashboard & Estimator Validation](token-master-plugin/docs/TOKENOMICS.md)**
- **[Replica Studies & Negative Results](token-master-plugin/docs/README.md):** [PRS-4](token-master-plugin/docs/PRS4_RESULTS.md) · [PRS-3](token-master-plugin/docs/PRS3_RESULTS.md) · [PRS-2](token-master-plugin/docs/PRS2_RESULTS.md) · [PRS-1 (why history rewriting fails)](token-master-plugin/docs/PRS1_RESULTS.md)
- **[15-Minute Demo Script](docs/DEMO_SCRIPT.md)**
