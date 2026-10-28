---
name: token-master
description: Configure graph navigation and conservative token-efficiency tools for an explicitly selected host. Use when the user asks to enable or remove TokenMaster, graph routing, recoverable views, or scoped token-efficiency discipline. Not a universal interceptor or a task-quality guarantee.
---

# TokenMaster

Use the smallest requested surface. An informational or explain-only request does
not authorize repository edits or a host installation. Preserve requested depth,
proofs, safety checks and justified reusable abstractions.

## Graph navigation setup

Run the script from this skill directory with the requested repository, explicit
host and an already provisioned pinned runtime:

```text
<runtime-python> setup.py <repo-root> --host claude|codex|copilot --python <runtime-python>
```

For Copilot, then run the second installer from the same directory. Copilot setup is
complete only when both commands succeed; this one installs the `view` output hook,
the launcher and `/tokenomics`:

```text
<runtime-python> brainspace_setup.py --host copilot --python <runtime-python>
```

Both need an already provisioned runtime: an interpreter with the exact pins in the
plugin's `requirements-runtime.txt` and closure lock. Look first in
`<COPILOT_HOME>/token-master-runtime` (`Scripts/python.exe` on Windows, `bin/python`
elsewhere), then in an activated virtual environment. Do not substitute another
interpreter; setup rejects any pinned-version mismatch. `setup.py` also needs the
graph supplier, `graphify`, on PATH; it comes from the `graphifyy` PyPI package.
`brainspace_setup.py` reads OpenAI's `cl100k_base` vocabulary from tiktoken's cache
and verifies its SHA-256; it never downloads. When one of these is missing, stop and
give the user these one-time commands, with `<plugin>` (this skill directory's
grandparent, which holds `requirements-runtime.txt`) and `<COPILOT_HOME>` filled in.
Run them only if the user asks:

```text
uv venv --python 3.12 <COPILOT_HOME>/token-master-runtime
<runtime-python> -m ensurepip
<runtime-python> -m pip install -r <plugin>/requirements-runtime.txt
<runtime-python> -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
uv tool install graphifyy
```

Do not install an unverified similarly named package or silently resolve dependencies
at every launch.

`setup.py` installs one MCP server, `tokenmaster-nav` (`navigation_mcp.py`), with three
tools: `locate` (a symbol or a file's outline), `read_symbol` (one symbol, file or
line range) and `impact` (callers). It builds `.token-master/graph.json` with
graphify and prebuilds `.token-master/symbols.sqlite`; both are gitignored. It also
gitignores graphify's own output folder, `graphify-out/`, so searches skip it. Graph
servers installed by earlier versions (`graphify-nav`, `codegraph`) are removed
when TokenMaster owns them.

Report the actual installer result, not a claim that a host accepted a tool.
Claude/Copilot get a navigation agent; Codex gets native MCP configuration, not a
translated Claude agent or output-replacement hook. Honor the restart guidance
printed for the selected host; for Copilot, end with the launcher command given under
Recoverable views. Never rewrite another host's profile by guessing.

Treat `impact` lines marked `[inferred]` or `[name]` as candidates and verify them
in source; dynamic calls, callbacks and string dispatch are invisible to it.
`locate` and `read_symbol` see edits immediately. The call graph is a build-time
snapshot; its edges from files edited since then are dropped.

## Uninstall

When the user asks to remove TokenMaster, run from this skill directory with the
runtime interpreter, or any Python 3.11 or newer if the runtime is gone; uninstall
needs no pinned packages, repository or `--python`. The second command is for
Copilot only:

```text
<runtime-python> setup.py --host claude|codex|copilot --uninstall
<runtime-python> brainspace_setup.py --host copilot --uninstall
```

Both remove only configuration TokenMaster owns. These scripts ship inside the
plugin, so they must run before `copilot plugin uninstall token-master@token-master`;
tell the user to run that next. The runtime, `<COPILOT_HOME>/token-master/` and each
repository's `.token-master/` and `graphify-out/` stay until the user deletes them.

## Recoverable views

The model-invoked `brainspace_compress` tool defaults to conservative behavior.
Explicit navigation may expose code skeletons; explicit overview may sample
suitable structured content. Exact/edit/debug/aggregate/exhaustive/security tasks
must retain their answer-bearing material. Errors and mixed media pass through.

Use `brainspace_retrieve(ref, offset, limit)` repeatedly at `next_offset` until
`complete=true`. Verify digests when reconstructing originals. Exact search is
available via `brainspace_search`; a bounded snippet is not the full original.
Do not treat a stored original, a shorter view, or a Jev confidence as proof of
successful task completion.

MCP is model-invoked, not transparent interception. The Claude PostToolUse adapter
has a separate versioned schema and runtime-acceptance gate. Unknown hosts/shapes
are not assumed compatible. No model-visible savings footer is required.

For Copilot, `brainspace_setup.py --host copilot` also installs an output hook by
default; `--no-copilot-output-hook` skips it. The hook applies `request-policy-v6`
to whole-file `view` results: oversized files become outline digests, and folder
listings are folded losslessly. A result that would not fit the hook's 9,000-byte
output cap passes through unchanged. The native Copilot route defaults to the same
policy. For Copilot, setup does not install the `brainspace` MCP server unless
`--brainspace-mcp` is given.

Setup also copies the launcher to `<COPILOT_HOME>/token-master/`. Start Copilot CLI
with `<runtime-python> <COPILOT_HOME>/token-master/brainspace_copilot_bridge.py -- copilot`;
in bring-your-own-model mode its v6 shaping needs the runtime's `tiktoken`.
The launcher excludes 13 built-in tools: 11 that no session called in the October 18 runs,
and two workflow tools that none of the October 27 sessions called. A prompt that asks for one
of these tool families keeps it, and `--all-tools` keeps them all. In bring-your-own-model mode, the
launcher also runs a local bridge
that applies the cache-stable system prompt and v6 shaping. See
`docs/COPILOT_BRIDGE.md` and `docs/COPILOT_CLI_RESULTS.md` for the measured effect
and its limits.

Setup also installs a personal Copilot skill, `/tokenomics`. In an interactive
session it shows Copilot CLI's token usage, GitHub's charges and the estimated
TokenMaster savings by day, week, month or session (`docs/TOKENOMICS.md`). The
savings are estimates; report them as such.

## Scoped discipline

For an explicitly requested task-local mode, state a compact contract:

1. Required result.
2. Non-goals.
3. Evidence needed.
4. Stop condition.
5. Optional advisory output-token budget, without suppressing requested detail.

`brainspace_tools.py` exposes task-local and explicit session-keyed modes. Never
infer that an enable flag from another session applies here. `off` removes only
this mode's owned state; it does not delete unrelated configuration or claim to
erase instructions already in a conversation. The review-only companion is
`token-master-review` and does not authorize edits.

## Evaluation and improvement

Use the token-only reference metric: all observed model inputs and outputs across
the whole task, including failures, retries, auxiliary decisions and recovery.
Keep learning separate; reject partial or nonmaterialized traces rather than
inventing totals. Native counters are diagnostics, not interchangeable units.

`token_efficiency.py` exposes the durable controller and an offline synthetic
fixture. The fixture verifies plumbing, not real language-model performance.
The installed `session` runtime can explicitly select actual pinned Ponytail
instructions and Headroom. `initialize-runtime` / `learn-runtime` connect a
bounded real read-only evaluator; initialization is safety admission only, and
learning compares an enabled local incumbent with a local neighbor, not an
optimizer-off baseline. See `docs/PRODUCT_RUNTIME.md` before using these paths.
For full compositions, `initialize-profile` / `learn-profile` use closed
`RuntimePolicy` data and explicit pinned resources, with a true-off default.
They reuse the strict registry/evaluator and do not promote automatically.
See `docs/PROFILE_LEARNING.md`; Jev abstention is not an improvement judgment.
Opt-in V4 adds lexical JSON payload compaction with exact original recovery;
it is not sampling or a default change. See `docs/LEXICAL_JSON_POLICY.md` and
`docs/LEXICAL_JSON_RESULTS.md` for its presentation contract and limited evidence.
The optional `--require-nonexpanding-input` session guard includes composition
overhead and falls back to the exact original input; it is not a task-savings
or quality certificate and is not enabled globally.
It may omit newly inserted optional guidance while retaining a valid smaller
context; reports distinguish configured and applied instructions. Headroom's
optional `--headroom-time-budget-seconds` is explicit, bounded and profile-bound,
not a hard wall-time guarantee or permission to forward arbitrary environment.
Real candidates need an independent outcome evaluator, fresh confirmation data,
a fixed measurement/regime, valid whole-task bounds and the persisted promotion
gate. Jev is optional advisory screening, network-disabled unless explicitly
configured; never send repository data or secrets as an implicit side effect.

See the plugin's `docs/TOKEN_EFFICIENCY.md` and `docs/IMPLEMENTATION_PLAN.md` for
the proof assumptions, supported boundaries and remaining release qualification.
