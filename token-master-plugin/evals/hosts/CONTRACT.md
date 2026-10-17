# Native host mock-provider transport smoke

Contract date: October 4, 2026. This is **not a model-quality evaluation**, a
real-provider certification, or evidence of billed/reference token savings.
Mock usage fields are synthetic protocol placeholders.

## Safety and scope

- Discover installed native CLIs; never update or install them.
- Allowlist the child environment. Do not inherit provider keys, OAuth tokens,
  custom `NODE_OPTIONS`, Python import paths, or user host configuration.
- Create distinct temporary HOME/USERPROFILE, host config, AppData, cache,
  workspace, vocabulary, and CCR locations. Validate ownership before cleanup.
- Acquire no assets or credentials. Require an already-local verified vocabulary.
- Point provider APIs to a loopback mock, use only a dummy credential, block
  proxy CONNECT requests, and disable nonessential traffic. Copilot additionally
  uses its documented offline mode. These controls are **not an OS firewall**.
- The original smoke runs only predetermined Read/MCP actions over synthetic
  data. The separate native-envelope matrix also uses fixed Grep/Glob reads,
  a fixed isolated Python read, a fixed no-profile PowerShell read through
  Bash, and one predetermined stderr/nonzero-exit control. The mock never
  interprets prompts or chooses arbitrary commands.
- Bound native processes and hook subprocesses. On Windows, a private
  kill-on-close Job Object contains CLI descendants, including MCP servers.
- Never start, reconfigure, or interact with a running desktop app.

## Evidence cells

### Claude `hook`

The actual CLI calls Read on synthetic pretty JSON. A test observer invokes the
actual installed hook with `--host claude`, records its input/output, and forwards
the output unchanged. Assertions require:

1. The hook emitted a changed, structured `updatedToolOutput` result.
2. Original and replacement JSON have identical parsed values.
3. The replacement appears in the next provider-bound request.
4. The original raw content does not appear in any subsequent request.
5. The native process exits successfully.

This validates the tested **Read text schema** only. It does not certify Bash,
PowerShell, Grep, mixed-media, every MCP result shape, or future host versions.
The newer separate matrix in `native_envelopes.py` covers those named additional
cells at its recorded version; see `../../docs/NATIVE_ENVELOPES.md`. Do not
reinterpret the older `hook` smoke receipt as covering the new matrix.

### Claude/Codex/Copilot `mcp`

The harness pre-seeds an explicitly scoped synthetic reference using the real
CCR implementation. The native host advertises/discovers the real server's
schemas, invokes `brainspace_stats`, then invokes public `brainspace_retrieve`.
The captured next provider request must contain a successful, complete page
whose content exactly equals the fixture. This proves native list/call/retrieve
transport, **not native model-selected compression quality**.

Codex may defer tools: the mock implements client `tool_search_call`, consumes
the resulting namespace schemas, and issues the namespace-qualified calls.
Codex's `Wall time: ... / Output:` wrapper is parsed explicitly when examining
its provider-bound MCP output.

### Codex Desktop

Always `blocked`, runtime acceptance false. Configuration support and a CLI
transport test are not Desktop runtime evidence.

## Windows Codex isolation caveat

The tested Codex CLI 0.147.0 discovers the OS-user `.agents/skills` catalog even
with redirected HOME/USERPROFILE/CODEX_HOME. The harness flags this observation
and redacts the non-fixture catalog from saved requests (retaining a SHA-256).
If observed, its overall status stays **blocked** and runtime acceptance stays
false even if the narrower transport assertions pass. No real authentication
is copied or supplied. Closing strict user-skill isolation requires a verified
supported isolation mechanism or a separate OS account/sandbox; do not rename,
delete, or change the user's real skills to force a passing test.

## Running

From the repository root, use the pre-provisioned `.token-master-dev` Python:

```powershell
$python = ".token-master-dev/Scripts/python.exe"
$eval = "token-master-plugin/evals/hosts/native_host_smoke.py"
$out = "evidence/jev-implementation-20261004/native-host-smoke"
& $python -X utf8 $eval --inventory --output $out
& $python -X utf8 $eval --host claude --scenario hook --tokenizer-file $verifiedLocalVocabulary --output $out
& $python -X utf8 $eval --host claude --scenario mcp --tokenizer-file $verifiedLocalVocabulary --output $out
& $python -X utf8 $eval --host codex --scenario mcp --tokenizer-file $verifiedLocalVocabulary --output $out
& $python -X utf8 $eval --host copilot --scenario mcp --tokenizer-file $verifiedLocalVocabulary --output $out
& $python -X utf8 $eval --host codex-desktop --scenario mcp --tokenizer-file $verifiedLocalVocabulary --output $out
```

Results follow `result.schema.json`. Exit 0 means the scoped cell passed;
exit 1 means failed/blocked. Record every cell, including unsupported ones.
Artifacts include CLI version/exit/timeout, installed-file digests, captured
provider requests, hook observations, assertions and explicit limitations.
Host configuration, workspace and store directories are removed after each run.

## Official contracts consulted

- https://code.claude.com/docs/en/hooks?plain=1 — exec-form `command` + `args`;
  built-in output-shape validation for `updatedToolOutput`. No minimum version
  or replacement-value cap is established by that section.
- https://code.claude.com/docs/en/env-vars?plain=1 — `ANTHROPIC_BASE_URL`.
- https://developers.openai.com/codex/config-advanced/ — custom Responses provider.
- https://developers.openai.com/codex/mcp/ and
  https://developers.openai.com/codex/config-reference/ — MCP launch and startup.
- https://developers.openai.com/api/docs/guides/tools-tool-search — client tool
  search calls, namespaced deferred tools and `tool_search_output`.
- Installed official `copilot help providers` and `copilot help environment`
  for CLI 1.0.88-2 — BYOK, no GitHub authentication requirement, offline mode.
