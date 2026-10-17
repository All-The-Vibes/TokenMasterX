# Native tool-envelope qualification

**Newer separate cell:** `NATIVE_COPILOT_HOOK.md` records the explicitly enabled
Copilot CLI 1.0.95-0 conservative JSON `view` hook and actual temporary-settings
installation lifecycle. It does not retroactively extend the Claude matrix below
or establish native full-profile efficiency.

This is a **transport check**, not a language-model quality benchmark. The actual
installed Claude CLI talks to a local synthetic provider and runs predetermined
tools in temporary configuration/workspace directories. Mock usage numbers are
protocol fixtures, never measured tokens.

The final source-checked matrix passes **11/11** cells, and the separate real
user-settings install/uninstall lifecycle passes. The integrated suite passes
**1,121 tests**. Local receipts are under
`evidence/native-envelopes-20261005/final-matrix/`,
`final-install-lifecycle/` and `full-tests.txt/xml`.

## What was missing

Claude Code **2.1.289** supplies an unstructured successful MCP result to
`PostToolUse` as a **bare content array**. The original adapter accepted a
`CallToolResult`-shaped dictionary only, so the native MCP text case produced no
override even though the dictionary unit tests passed.

The captured regression now covers the actual shape. Contract
`claude-posttooluse-2026-10-05` accepts a nonempty, pure-text MCP array only with
an explicit `PostToolUse` event. It preserves the array, block metadata, order
and other fields. Mixed-media/unknown blocks, error or interruption flags,
failure events, empty arrays and structured strings remain passthrough.

The native failure capture uses `PostToolUseFailure`, an `error` string and no
`tool_response`. The native structured-result capture uses a string. Neither
is guessed to be the successful text-array form.

Captured, sanitized fixtures and provenance hashes ship in
`evals/hosts/fixtures/`. Real error fixtures contain valid pretty JSON that
would otherwise be eligible; an unparseable prefix does not manufacture a
passing error-bypass test.

## Matrix and limits

| Case | Native tool | Expected behavior |
| --- | --- | --- |
| Pretty JSON file | Read | Compact eligible text; preserve file metadata |
| JSON content search, line numbers disabled | Grep | Compact content; preserve search metadata |
| Fixed isolated Python fixture read | Bash | Compact stdout; preserve other fields |
| Fixed `Get-Content -LiteralPath` read | Bash launching PowerShell | Same stdout contract; `-NoProfile` and UTF-8 |
| File enumeration | Glob | Exact passthrough |
| Valid synthetic PNG | Read | Exact image-result passthrough |
| Predetermined nonzero command with stderr | Bash | Preserve failure, stdout and diagnostic |
| Unstructured JSON text | Fixture MCP | Preserve native content-array shape |
| Text plus image | Fixture MCP | Exact mixed-media passthrough |
| `isError=true` with valid JSON text | Fixture MCP | Preserve failure and diagnostic |
| Structured plus text representations | Fixture MCP | Passthrough; never change one representation alone |

The PowerShell row is **PowerShell output carried by Claude's Bash tool**.
It is not evidence for a separate PowerShell hook protocol or a Copilot output
replacement hook. The original Copilot cell covered model-invoked MCP only;
the newer named `view` hook qualification is documented separately above.

The declared contract identifier selects a schema contract; it does not detect
every future host version. Receipts pin the tested native version and executable,
installed adapter/router/source files, runtime dependencies and vocabulary.
Unsupported declared contracts and unsupported shapes fail closed. An untested
future native binary is not automatically qualified by these receipts.
The matrix's native-render verifier itself accepts the recorded **2.1.289**
version only; a different version requires separate qualification.

## Proof performed per case

1. Run without the hook, then with the real copied hook through a transparent
   test observer, using the same files and predetermined action.
2. Correlate the observer and the **target provider-bound tool result** by call
   ID. Do not count a matching string in a schema or unrelated message.
3. For transforms: require an actual override, equal parsed JSON values,
   unchanged non-text hook fields, and the **complete expected provider result**.
   Only the observed version-specific text rendering may change: Read's numbered
   tab-separated lines, literal Grep/Bash text, or pure-MCP text plus its native
   newline. Every native-added block, suffix, status and other field is frozen.
   The complete target-result reference serialization must also shrink.
4. For bypasses: require the intended event, status, native shape and fixture
   contents—not two matching permission errors. Require no override and the
   exact same complete provider-bound result as the no-hook run.
5. Require clean native exits, unchanged fixture bytes/executable, stable source
   hashes and removal of the owned temporary state.

Source inventories include the executed isolation/cleanup implementation and
the installer's `hosts/*.py` helpers, not just the top-level runner.

Reference counts here cover **one complete native tool-result JSON object** under
the pinned tokenizer. They do not cover an entire model request or task, include
no real model output, and cannot establish production token savings.

## Reproduce safely

From the repository root, with the existing development runtime and a verified
local vocabulary:

```powershell
.\.token-master-dev\Scripts\python.exe -X utf8 `
  token-master-plugin/evals/hosts/native_envelopes.py `
  --tokenizer-file <verified-local-cl100k_base.tiktoken> `
  --output <new-evidence-directory>
```

Use `--cases` to select named cells. The output directory must be new. Evidence
includes source/plan manifests, native executions, raw provider requests, hook
observations and per-cell results. Failed cases remain recorded; a smaller
output alone cannot turn a failed or missing acceptance check into a pass.

The harness never acquires credentials, installs/updates native CLIs, changes
normal host configuration, launches Desktop or runs arbitrary model-supplied
commands. It uses a dummy credential only against loopback, disables nonessential
traffic, and denies proxy CONNECT requests. These are not an OS firewall or a
proof of no possible external filesystem read.

The existing Codex Desktop/user-skill isolation gate remains separate and open;
the Windows preflight found no **accessible proven** disposable Windows
environment. Permission-denied feature/VM queries are unknown, not evidence
that no VM exists.

## Actual installed-settings lifecycle

The separate `evals/hosts/native_install_lifecycle.py` runs **before install →
installed → after uninstall** through the native CLI's real `user` settings
source. It does not substitute the observer for the installed hook, and its
child environment contains no ambient tokenizer path/cache. An unrelated
synthetic hook checks settings-driven vocabulary propagation and remains active
through all three phases.

The check requires successful native reads, the complete expected installed
result, exact restoration of the original result after uninstall, unchanged
fixture files and preservation of unrelated settings/MCP entries. Configuration
comparisons occur immediately across the installer/uninstaller operation:
native CLI preference/counter writes between CLI runs are not falsely attributed
to uninstall. Field fingerprints record those boundaries without dumping native
preference values.

```powershell
.\.token-master-dev\Scripts\python.exe -X utf8 `
  token-master-plugin/evals/hosts/native_install_lifecycle.py `
  --tokenizer-file <verified-local-cl100k_base.tiktoken> `
  --output <another-new-evidence-directory>
```

This still uses temporary homes and a synthetic provider. It is not an
installation into the user's actual profile or a model-quality experiment.
