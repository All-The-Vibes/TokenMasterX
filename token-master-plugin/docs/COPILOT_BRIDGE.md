# Copilot CLI launcher and bridge

`brainspace_copilot_bridge.py` starts GitHub Copilot CLI for TokenMaster. It does up to two
things:

1. **Lean tool set.** The launcher removes 13 built-in Copilot CLI tools: 11 that no session called
   in the October 18 runs, and `run_dynamic_workflow` and `dynamic_workflows_manage`, which Copilot
   CLI sends under default routing and, from 1.0.104, in every mode, and which none of the 60
   sessions of October 27 called. A prompt that asks for one of these tool families (a subagent, a
   workflow, a skill, ...) keeps it. Their definitions and the system-prompt text about them then
   leave every model call. This works with Copilot CLI's normal GitHub routing and with
   bring-your-own-model mode.
2. **Bridge.** In bring-your-own-model (BYOK) mode only, the launcher also starts a local bridge.
   The bridge applies two deterministic rewrites to every model request: the cache-stable system
   prompt and v6 shaping.

Copilot CLI runs measured the launcher and bridge in BYOK mode, with graph navigation
installed. Against stock Copilot CLI, they used about half the raw tokens
([COPILOT_CLI_RESULTS.md](COPILOT_CLI_RESULTS.md)).

## Install and run

1. Install TokenMaster for Copilot:
   `python brainspace_setup.py --host copilot --python <runtime> --tokenizer-file <cl100k_base.tiktoken>`.
   - This step copies the launcher and the verified tokenizer to `<COPILOT_HOME>/token-master/`.
   - It also installs the v6 output hook for whole-file `view` results.
   - It does not install the `brainspace` MCP server for Copilot. `--brainspace-mcp` adds it.
2. Optional: install graph navigation for a repository with
   `python setup.py <repo> --host copilot --python <runtime>`. This step needs graphify.
3. Start Copilot CLI through the launcher:
   `python <COPILOT_HOME>/token-master/brainspace_copilot_bridge.py -- copilot [args...]`.
   Plain `copilot` stays unchanged.
4. Optional: type `/tokenomics` in an interactive session for the usage and savings dashboard
   ([TOKENOMICS.md](TOKENOMICS.md)).

The launcher appends a start record and an end record for each Copilot CLI launch to
`<COPILOT_HOME>/token-master/launches.jsonl`: time, folder, whether the lean tool set, the bridge and the navigation
tools were on, and the names of the tools that the lean tool set excluded. The records hold no prompt text.
`/tokenomics` uses them to tell TokenMaster sessions from stock sessions, and to credit only the tools a launch
removed.

## Lean tool set

- The launcher adds `--excluded-tools` with these tools: `session_store_sql`, `task`,
  `read_agent`, `write_agent`, `list_agents`, `skill`, `sql`, `read_powershell`,
  `stop_powershell`, `list_powershell`, `fetch_copilot_cli_documentation`, `run_dynamic_workflow`
  and `dynamic_workflows_manage`. A prompt given with `-p`, `--prompt`, `-i` or `--interactive` that
  matches a tool family's intent keeps that family (for the workflow tools: the word "workflow"; for the
  subagent tools: a request for subagents), and so does `TOKENMASTER_KEEP_TOOLS` with the family's name.
  A prompt that starts a skill keeps `skill`, and keeping `skills` (or `skill`) also keeps the workflow
  and subagent tools. Copilot CLI 1.0.95-3 to 1.0.104 accept all 13 names, including builds that do not
  send the workflow tools.
- A prompt starts a skill when it holds one of these:
  - a slash command that names an installed skill, in any case, at the start of the prompt or after a
    space, quote, backtick or bracket: `/review-pr 123`, ``run `/review-pr` on 123``, `/plugin:skill`;
  - "use", "using", "load", "invoke", "run" or "apply", then a name and "skill", as in
    `use the humanizer skill`;
  - an installed skill's name right after one of those verbs, with or without "the", "my" or "our"
    in between: `run humanizer on the README`, `use the humanizer on README.md`;
  - "use the skill tool" (or another of those verbs), or `skill://`.

  Before it looks for skill and agent names, the launcher drops each negated invocation: "not", "n't",
  "never", "without", "dont" or "avoid", then one of those verbs or "ask", then a name. So
  `do not use the review skill` and ``never run `/review-pr` `` keep nothing, while the other families
  still see the whole prompt: `never run the workflow on main` keeps the workflow tools. Paths and
  routes keep nothing (`/src/app.py`, `POST /users`, `the /login route`), and so does an installed
  skill's name used as a plain word (`fix the infinite loop in parser.py` with a `loop` skill
  installed). Some prompts still keep the skill tools without starting a skill, for example
  `the asyncio run loop hangs` and `use pdf export` when `loop` and `pdf` are installed. With the 127
  skills that Copilot CLI listed on the test machine, the 145 coding prompts in this repository's evals
  kept the skill tools twice under the earlier rules (both times for `loop`) and never under these
  ([evidence/skill-trigger-20261029](../../evidence/skill-trigger-20261029/corpus_check.py)).
- The slash command needs `skill`. In prompt mode (`-p`), Copilot CLI 1.0.104 passes it to the model
  as text, and lists the installed skills in its system prompt only while `skill` is kept, so without
  `skill` the model cannot load the skill. In an interactive session in a terminal, Copilot CLI puts
  the skill's text into the prompt itself; its changelog says skill commands work mid-input from
  1.0.44 and in any case from 1.0.71. Keeping `skill` adds 438 cl100k tokens a call with three skills
  installed and about 3,990 with the test machine's 128 skills, of which Copilot CLI listed 20; almost
  all of it is the list of skills. With the workflow and subagent tools, a prompt that starts a skill
  costs about 5,150 to 8,700 tokens a call with no custom agents installed, and about 11,000 with the
  operator's agents listed in `task` (`gpt-6-astra`, Responses API, BYOK mode;
  [evidence/skill-trigger-20261029](../../evidence/skill-trigger-20261029/probe.py)).
- The launcher reads installed skill names where Copilot CLI looks for them, at any depth:
  `.github/skills`, `.agents/skills` and `.claude/skills` in the working folder (or the `-C` folder) and
  each folder above it up to the repository root, except `~/.claude/skills`; `.claude/commands`, whose
  files Copilot CLI 1.0.105 loads as skills; `<COPILOT_HOME>/skills`; `~/.agents/skills` while
  `COPILOT_HOME` is unset; installed plugins; the `.github/skills` folder of each `--add-dir` folder and
  the `skills` folder of each `--plugin-dir` folder; the folders of `copilot skill add`
  (`skillDirectories` in `<COPILOT_HOME>/settings.json`) and of `COPILOT_SKILLS_DIRS`, which separates
  them with commas; and Copilot CLI's built-in skills. In six setups it found every skill that
  `copilot skill list` (Copilot CLI 1.0.105) showed, and 1 to 7 names more, which count only after a
  slash or a verb. It reads the folders only for a prompt with a slash command or one of those verbs,
  in under 0.4 s here
  ([evidence/skill-trigger-20261029](../../evidence/skill-trigger-20261029/scan_check.py)).
- Custom-agent names follow the same rule. An installed agent's name keeps the subagent tools right
  after one of those verbs or "ask", with or without "the", "my" or "our" in between
  (`ask the auditor to check this diff`), or right before "agent" (`the auditor agent`). A name that
  only appears in the prompt, or follows a negation, keeps nothing.
- Some flags and commands keep a family by themselves. `--agent` keeps the subagent tools. `--fleet`
  keeps them and `sql`, and so does `/fleet` at the start of a prompt: fleet mode tells the model to
  dispatch subagents with `task` and to track them in the `sql` tool's `todos` table. `/review`,
  `/security-review` and `/research` at the start of a prompt keep the subagent tools: in an
  interactive Copilot CLI 1.0.104 session each tells the model to use `task` with the agent type of the
  same name (`code-review` for `/review`). The same text later in a prompt, as in
  `POST /review returns 500`, keeps nothing. `/rubber-duck` is unconfirmed and keeps nothing: it sent no
  request in that probe. `--resume`, `-r` (also `-r ID` and `-rID`) and `--continue` keep session
  history.
- The launcher sees only the prompt it is given. Prompts typed later in an interactive session, and a
  prompt piped on stdin, keep nothing: pass `--all-tools` or set `TOKENMASTER_KEEP_TOOLS` for those.
- A skill may hand work to a subagent, so a prompt that starts one keeps the four subagent tools.
  Measured on Copilot CLI 1.0.104 with `gpt-6-astra` over the Responses API in BYOK mode, that adds
  about 2,670 cl100k tokens to every call with no custom agents installed: about 1,690 for the tool
  definitions and about 985 for the subagent instructions Copilot CLI adds to its system prompt.
  `task` lists the installed custom agents, so the cost grows with them: about 5,010 tokens a call
  with the operator's agents
  ([evidence/skill-agents-cost-20261029](../../evidence/skill-agents-cost-20261029/probe.py)).
- The model keeps its shell, search, read and edit tools. In the measured runs, `gpt-6-astra`
  kept `powershell`, `rg`, `glob`, `view` and `apply_patch`. `claude-opus-5.5` kept
  `powershell`, `grep`, `glob`, `view`, `create` and `edit`. The TokenMaster navigation tools
  stay when they are installed.
- The launcher leaves the command unchanged in four cases:
  - You pass `--all-tools` to the launcher.
  - You already pass `--available-tools` or `--excluded-tools` to Copilot CLI.
  - You run a Copilot CLI subcommand.
  - The command's program is not named `copilot`, for example `-- npx @github/copilot`.
- In a probe with one lookup task per model on Copilot CLI 1.0.78-3, the lean tool set cut the
  system prompt from 7,216 to 5,117 cl100k tokens (`gpt-6-astra`). The session used 27,255 → 13,702 raw tokens
  (`gpt-6-astra`) and 42,544 → 19,434 (`claude-opus-5.5`).
- **Trade-off:** a workload that needs subagents (`task`), skills, session-store search, SQL,
  background PowerShell or agent workflows loses those tools when its prompt does not ask for them,
  for example in an interactive session started without `-p`. Use `--all-tools` for it. No run
  measured such a workload. In the October 19 runs, one stock `gpt-6-astra` session (P13) called
  `task`; with the lean tool set, the same task passed without it.

## Bridge (bring-your-own-model mode)

- The bridge starts when a provider URL is set: `--upstream`, or the `COPILOT_PROVIDER_BASE_URL`
  that was set before the launcher started.
- The launcher starts the bridge on `127.0.0.1`. It sets `COPILOT_PROVIDER_BASE_URL` to the
  bridge for the Copilot CLI process only.
- Two provider formats are supported:
  - `COPILOT_PROVIDER_TYPE=openai` (the default) with the Responses wire API. The launcher sets
    `COPILOT_PROVIDER_WIRE_API=responses`.
  - `COPILOT_PROVIDER_TYPE=anthropic` (Anthropic Messages).
- The bridge changes each model request in two ways:
  1. **Cache-stable system prompt.** The bridge moves Copilot CLI's `Session folder:` line from
     the system prompt to the first user message. Every session in the same working folder then
     sends the same system prompt; the system prompt also names that folder. A new session's first
     call there can read the prompt from the provider's cache.
  2. **v6 shaping.** The bridge shapes grep, glob and whole-file view results with
     request-policy-v6. Other tool results, such as shell output, pass through unchanged.
- Both changes are deterministic. The bridge applies them again on every call, so each call of a
  session sends the same bytes for its earlier messages. The provider's prefix cache stays valid.
- The bridge does not read, store or add credentials. It forwards the client's headers,
  including `Authorization`, to the upstream.
- With `--log <file>`, the bridge writes one JSON line per model request. The line holds usage
  numbers and hashes only. It holds no request or response content.
- To run the bridge without Copilot CLI, omit `-- copilot`. The bridge then prints the base URL
  to use.

## Requirements and limits

- **Without a provider URL, the launcher applies only the lean tool set.** Copilot CLI keeps its
  normal GitHub routing, which has no setting for its API URL. The cache-stable system prompt and
  the bridge's v6 shaping need BYOK mode. Graph navigation and the v6 `view` hook still work.
  No run measured this configuration.
- v6 shaping needs the verified cl100k tokenizer. Without it, the bridge still applies the
  cache-stable system prompt, and it prints a warning.
- The cache saving needs another session with the same system prompt within the provider's cache
  lifetime. Probes put that lifetime between 6.5 and 31 minutes. In the 45-task Django run, the
  sessions ran back to back. Re-priced as if every first call missed the cache, the
  `gpt-6-astra` cost saving fell from 79.9% to 49.5%
  ([COPILOT_CLI_RESULTS.md](COPILOT_CLI_RESULTS.md#how-to-read-the-cost-numbers)).
- With `claude-opus-5.5`, stock first calls already read the tool block from the cache, because
  Anthropic's layout puts the tool definitions before the system prompt. They still wrote the
  system prompt to the cache: a median of 7,474 tokens, against 314 for TokenMaster first calls.
  No run isolated the bridge's own effect with `claude-opus-5.5`.
- Copilot CLI keeps the unshaped results in its own history. The bridge changes only what the
  provider receives.
- The bridge does not supply credentials for any provider. The measured runs used the GitHub
  Copilot API through an evaluation relay that added the credential. TokenMaster does not ship
  that relay.

## Evidence

- **Copilot CLI runs, October 18–22, 2026** ([COPILOT_CLI_RESULTS.md](COPILOT_CLI_RESULTS.md)).
  These runs are exploratory.
  - Django, 45 "who calls X?" tasks: −53.4% raw tokens with `gpt-6-astra` and −51.6% with
    `claude-opus-5.5`, against stock. Correct answers: stock 90/90, TokenMaster 88/90.
  - This repository, 27 tasks: −44.8% and −53.5% raw tokens.
- **Live checks, October 18, 2026** ([evidence](../../evidence/copilot-bridge-20261018/)). These are
  functional checks with one session per task, not a savings study.
  - Without the bridge, 6 sessions sent 6 different system-prompt prefixes, and no first call
    read from the cache.
  - With the bridge, each later session's first call read 13,406 to 13,410 of about 13,550 input
    tokens from the cache.
  - Through the bridge, Copilot CLI made correct one-line edits, and an interactive session in a
    terminal ended normally with `/exit`.
- **PRS-4, a pre-registered study in a Copilot-CLI-shaped harness** ([PRS4_RESULTS.md](PRS4_RESULTS.md)).
  Its prompt was about 3,600 tokens, not the CLI's own. Under continuous use, the two bridge
  rewrites with v7 cut billed cost per finished task by 49.8% (95% CI −57.1% to −42.9%).
