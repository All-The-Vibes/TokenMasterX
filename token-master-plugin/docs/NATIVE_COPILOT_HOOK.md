# Native Copilot hook — October 9, 2026

> **Update, October 18, 2026:**
> - The hook now applies `request-policy-v6` to whole-file `view` results instead of
>   JSON whitespace compaction.
> - `brainspace_setup.py --host copilot` installs the hook by default.
>   `--no-copilot-output-hook` skips it, and a user's `disableAllHooks` setting still
>   wins.
> - The native lifecycle run below verified the October 9 JSON hook with Copilot CLI 1.0.95.
> - Live checks on October 18, 2026, with Copilot CLI 1.0.78-3, the WinGet launcher's bundled
>   build ([evidence](../../evidence/copilot-bridge-20261018/)). The later checks were labeled as
>   the installed 1.0.98, but they passed `--no-auto-update`, which runs the bundled build
>   (corrected October 23, 2026):
>   - 1.0.78-3 sends `toolArgs` as a JSON string. The hook accepted only an object, so it
>     changed nothing. The hook now parses the string. 1.0.98 was not checked.
>   - After the fix, a plain whole-file view of an 18.0 KB file reached the model as a
>     1,799-character v6 digest instead of 20,112 characters, in both checks. Copilot CLI
>     accepted the hook's result.
>   - 1.0.78-3 refuses plain whole-file views of larger files ("File too large to read at
>     once"). It refused a 22.4 KB file and a 37.3 KB file. v6 read digests
>     therefore apply only to files between v6's 4,000-token read budget and that limit.
>   - In both sessions, the model read the file again with `forceReadLargeFiles` after the
>     digest. v6 never shapes forced reads. In these 2 sessions, the hook saved nothing.

**A real native integration slice, not a full-system savings result.**
The installed conservative JSON `view` hook now runs through the actual
Copilot CLI. This hook does **not** run the full Ponytail/Headroom/Jev profile,
intercept complete requests, or supply whole-task usage accounting.

## What is verified

An isolated **Copilot CLI 1.0.95-0** lifecycle ran:

1. Before installation: a predetermined native `view` read reached the local
   provider with the complete original JSON.
2. Explicit installation: the installer registered the actual copied
   `brainspace_posttooluse.py` in native settings. The next provider-bound
   result contained precisely the expected whitespace-compacted JSON.
3. Uninstallation: the original result returned, the owned hook/MCP registration
   disappeared, unrelated settings were preserved, and package files remained.

All three native executions exited successfully, with two synthetic Responses
requests each. The exact native binary and implementation sources were unchanged.
The owned process trees were closed and temporary directories removed.
The fixture preserved duplicate members, numeric spellings, Unicode, escaping
and whitespace inside strings. Its source file was never changed.

**Six synthetic model-endpoint requests; zero real model calls.** Mock usage
fields are protocol fixtures, not token measurements. There is no task-quality,
task-efficiency, model-obedience or broader-version certificate.

Current-source evidence:
`evidence/integrated-runtime-20261009/native-host-route/installed-hook-002/`.
The passing predecessor `installed-hook-001/` is retained at its older source pins.
The earlier no-hook and observer captures are `probe-002/` and
`hook-observer-001/`. `probe-001/` remains an unqualified failed attempt.

## Exact supported boundary

Contract: `copilot-posttooluse-2026-10-09`.

The observed native input supplies `sessionId`, `timestamp`, `cwd`,
`toolName: "view"`, `toolArgs: {"path": ...}`, and
`toolResult: {"resultType": "success", "textResultForLlm": ...}`.
The output uses native **`modifiedResult`**, not Claude's
`hookSpecificOutput.updatedToolOutput`.

- Successful, unranged, pure-text `view` results only.
- The active CLI path accepts only the conservative JSON operation.
- Exact/edit/debug and other intent overrides bypass, rather than enabling
  lossy views without a native recovery connection.
- Intent is an explicit host setting, not automatically inferred from the
  user's prompt. An opted-in conservative hook can change JSON formatting;
  raw-byte/formatting tasks require the exact override or a disabled hook.
- Unknown/extra schemas, failure/denial/error states, mixed representations,
  ranged reads, unsupported contracts and non-JSON content stay unchanged.
- No recovery footer, storage dependency, model inference or network request is
  introduced by the Copilot hook.
- Both reference tokens and UTF-8 bytes of the complete result envelope must
  decrease; the emitted hook response must also fit its local stdout byte cap.
  These are result-boundary checks, **not a complete-request/task invariant**.
- Missing/corrupt local tokenizer assets fail closed. The installer passes the
  verified vocabulary path explicitly; normal shell caches are unnecessary.

The JSON operation preserves the sequence of all non-whitespace JSON lexemes:
it deletes only JSON whitespace outside strings. That is a deterministic
representation property, not proof that a probabilistic model returns the same
answer. Exact raw-byte text requirements must use the bypass path.

## Explicit installation, no changed defaults

`brainspace_setup.py` now accepts `--copilot-output-hook` **only with
`--host copilot`**. Supply the existing interpreter and verified local tokenizer
as for ordinary installation. The emitted command is exec/argv, not a shell
string, and includes the explicit hook contract.

Copilot installation **without** the new flag remains MCP-only registration.
`brainspace_posttooluse.py --host copilot` without its explicit contract remains
a no-op. Claude behavior and Codex no-op behavior remain unchanged.

Uninstallation removes the owned Copilot hook even when the activation flag is
omitted. The ownership receipt protects edited/foreign entries, neighboring hook
order and pre-existing empty maps. A pre-existing edited/duplicated owned hook
now fails preflight before MCP removal; a regression test reproduced the earlier
partial-uninstall behavior before that repair. Multi-file changes are still not
one atomic transaction against arbitrary concurrent external editors.
The installer does not turn off a user's
`disableAllHooks` choice or bypass machine policy. Registration status is not
proof that a host enabled or accepted the hook.

This work did **not** install into the user's everyday host profile, acquire a
credential, change model weights, add dependencies, or change any optimizer
promotion gate.

Current targeted verification: **297 tests plus 19 subtests** passed with one
existing Pydantic warning and no Python source drift. This covers adapters,
registration, installed entrypoints, JSON guards, native evaluator protocols and
cleanup checks; it is not a rerun of the full plugin suite.

## Native isolation and transport findings

Redirecting homes plus `--no-custom-instructions` was insufficient: the first
probe discovered the user's inherited skill catalog. That failure is retained
with private catalog content redacted, not forwarded to a real model.

The passing runs used absolute `ignoredSkillsLocations` in the temporary
settings, a temporary `COPILOT_CACHE_HOME`, an allowlisted child environment,
offline BYOK, an explicit loopback provider and a single allowed native tool.
No external catalog appeared in native skill events or captured requests.
This is observed configuration/request isolation, **not an OS sandbox or proof
that the process could not access any other local file**.

The synthetic Responses provider also needed a genuine protocol repair:
nonstream requests now return completed JSON; streaming requests have the
argument/text event lifecycle. Old failures are not rewritten as successes.

Official contracts:
- [GitHub native hooks](https://docs.github.com/en/copilot/reference/hooks-reference)
- [Copilot configuration](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)
- [Responses function-call streaming](https://developers.openai.com/api/docs/guides/function-calling)

The pinned official-doc/source review is
`evidence/integrated-runtime-20261009/native-host-route/official-copilot-route.md`.

## Still required for the full goal

Connect the selected full runtime profile, native task/session identity,
actual component lifecycle/recovery and complete model-call accounting into
the intended native route. Then evaluate independently checked ordinary tasks
under a predeclared **feasible** design. Do not report this hook fixture as that
evaluation or reuse synthetic usage as savings.
