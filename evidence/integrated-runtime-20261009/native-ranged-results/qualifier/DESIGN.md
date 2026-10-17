# Ranged-result installed qualifier — authoring-only handoff

**This revised qualifier has not been run. Parent review and invocation required.** No native process,
Docker, provider socket, real model, dependency installer or measurement was
started while authoring this directory. This qualifier is protocol evidence,
never efficacy, quality, task savings or promotion evidence.

The parent reports that earlier `native-002` reached real Headroom in three
canned requests but reverted a candidate whose complete wire grew by 37
reference tokens (161-token annotated Root versus 124-token projection benefit).
It had zero recoveries and did not dispatch the exact cell. This is a retained
non-passing result, not evidence that compact references work. Old run outputs
were not inspected for task reshaping or modified by this follow-up.

The parent subsequently reports `native-003`: overview passed in five canned
calls with actual compact Root/native Root/fragment recovery; exact failed after
two canned calls because missing-file delivery differs from literal error.message.
Retain that run as **overall failed, seven canned calls, zero real-model calls**.
This revision fixes only the evidenced missing-path renderer before a future
fresh `native-004` full schedule. It does not remove or bypass the failed exact
cell or retroactively relabel `native-003`.

Only this new `qualifier/` directory is authored. The parent's `../PLAN.md`,
production code, earlier qualifiers and all previous evidence remain untouched.

## Scope and fixed scripted schedule

Use an explicitly supplied **already isolated, installed** TokenMaster package.
Do not use a normal host profile. This script does not install/uninstall anything
or create dependencies. Its `prepare` command requires a successful installation
receipt, checks installed entrypoints and all mappable installed Python sources
against the current checkout, and pins the complete installed inventory.

Sources are the complete pinned upstream `wiki/filesystem-contract.md` and
`wiki/persistent-installs.md` at
`1cf496612e781ef8d67ff87ee4f78037492f0bc7`. Their fixed SHA256s are in `checks.py`.
They are copied unchanged with their original filenames and suffixes to two
separate owned temporary workspaces. No padding, renaming, source reconstruction
or post-result source tuning. Document commands are data, never authority.

| Session | Primary request | Canned action |
|---|---:|---|
| overview | 1 | Native `view`, filesystem-contract.md, `view_range: [3,159]`, `forceReadLargeFiles: true` |
| overview | 2 | Native `view`, persistent-installs.md, `view_range: [30,-1]` |
| overview | 3 | If the now-old partial result has an accepted Root ref: native `tokenmaster-retrieve_original`, exactly `{ref, offset}`, offset 0 |
| overview | 4 | If that accepted result emits a new upstream fragment marker: native `tokenmaster-headroom_retrieve` for its first marker |
| overview | 5 at most | Canned final text; the preceding recovery result is visible in this request |
| exact | 1 | Same native partial view of filesystem-contract.md |
| exact | 2 | Native `view` of the deliberately absent `missing-status-control.md`, range `[1,-1]` |
| exact | 3 | Canned final text; old partial and genuine failure result are both present |

The missing path is not a synthesized document. It tests genuine native failure
status. Successful partial/EOF arguments are passed unchanged, under the native
name `view`. No output is renamed into a document and no historical call is
rewritten. An absent reduction/ref ends the canned schedule and fails the gate;
there is no rescue read, retry, enlarged source, or policy substitution.

**Global maximum: 8 submitted primary requests, including failed calls.**
Recovery MCP operations and the owned native version probe are retained
separately, not hidden or counted as real-model calls. Five plus three are fixed
session caps; unused overview calls are not transferred to the exact session.
The exact/status controls occur only after a successful overview qualification.
On failure they remain explicitly unattempted.

The EOF result is newest when the partial result first becomes eligible. The
exact session makes the successful partial older than a subsequent failed tool
result. Status is also exact-protected; this is not an isolated test attributing
passthrough solely to the status guard. Directory, malformed-range, replay and
edit/debug tests remain the production unit/regression lane, not extra scripted
requests here. Only the first emitted upstream fragment is recovered; if none is
emitted, report not-emitted (never claim exercised fragment recovery).

Root recovery's 32768-character page cap belongs to the server. It is **not**
a client `limit` argument: production `RuntimeSession.recovery_tools` exposes
exactly `ref` and `offset`, and `_recover_content` requires that same key set.
The offline regression reads both the production schema and dispatch AST plus
the CCR page-cap definition; it does not validate an invented interface.

## Explicit Root-reference policy selection

`prepare --root-reference-style` accepts exactly `annotated-v1` (default) or
`compact-root-v1`. It constructs the installed typed RuntimePolicy with
`headroom_root_reference_style` set to that choice. The typed serializer still
omits the default annotated field; the qualifier does not inject it into policy
JSON or manufacture a policy ID. `plan.root_reference_style` separately freezes
either choice and must agree with the policy, where absence means annotated.

Recognition is closed to two known Root forms at the start of the delivered
projection: the existing annotated V2 Root with full digest/scope and original
encoded metadata fields, or `[[BR:<64 lowercase hex>|r=1]]`. The compact ID is
opaque: CCR binds scope, content digest and full metadata; it is not treated as
a bare content hash. The scheduler copies the complete marker unchanged into
the existing `tokenmaster-retrieve_original` action `{ref, offset}`.

Unknown versions, malformed IDs, unsupported fields, fragment annotations and
the other known style do not qualify as the selected Root style. Prior toy unit
markers such as `[[BR:ref]]` are rejected; fixtures now use structurally valid
annotated Roots. Genuine annotated-v1 compatibility remains. Public sources,
filenames, ranges, prompt, schedule and ratio/full-wire guards are unchanged.

Reports include `selected_root_reference_style`, `delivered_root_ref` (null if
none) and `native_root_lookup_verified`. Recognition or scheduling alone leaves
verification false. Passing lookup still requires actual native start/completion
and delivered Root result, exact equality with the previous observed range-result
text, and all existing source/protection/full-wire checks. No compact lookup or
savings claim follows from these offline tests. Non-reducing candidates still
fail without rescue reads, task reshaping or retries.

## Gate and oracle

Require all of:

1. Installed API supports `source_contract`, default remains
   `native-full-view-v1`, installed CLI exposes `--source-contract`, and the
   invocation explicitly supplies `native-view-result-v2`.
2. Native result identifies `copilot-native-runtime-view-result-v2`; native
   executor and launcher retain the selected contract. Exactly two successful
   source receipts in overview and one in exact; the failure acquires none.
3. Real native start/completion pairs match the issued names, complete arguments
   and turn. Successful views have file telemetry and nonempty observed text.
   Preparation originals match the exact observed native range-result text.
   Failed views must also match exact observed text: accept a supported plain
   `result.content`, or, only when top-level `success` is strictly false and
   `result` is absent/null, normally the literal string `data.error.message`.
   The sole derived-text exception is the pinned missing-path renderer below.
   Never guess `Error:` prefixes, trim whitespace, normalize line endings, or fall back from a
   malformed non-null result. Missing/unsupported failed representations reject;
   no `None` sentinel may skip comparison. Failure remains failure and grants
   no source receipt. Successful MCP native rendering remains unchanged.
4. Nonempty partial content actually appears at an eligible index in
   `compress_documents` RPC to configured Headroom's pinned public pipeline.
   Worker replies identify `native-documents-v1` and the pinned upstream commit,
   disable system-message compression and preserve all protected messages.
5. The partial result actually changes, reaches the canned upstream, and is
   accepted in a **smaller complete original-input wire**: strict reference
   decrease and strict UTF-8-byte decrease, matching wire digests, accepted
   captures and provider requests. A rejected candidate or smaller inner text
   alone cannot pass. Canned provider usage constants are not measurements.
6. Actual native Root recovery starts/completes and delivers JSON whose decoded
   `content` equals the **exact prior observed native partial result**, including
   native formatting. The oracle never slices/re-reads the original file as the
   recovery answer. File bytes are used only for provenance/integrity.
7. If a new fragment marker is emitted, a native fragment recovery is required;
   compare decoded native delivery with the worker's actual returned JSON and
   stored `original_content`, not a locally fabricated fallback.
8. Newest, exact and failure controls remain unchanged. All source/install/resource
   pins survive. Native process tree, reader threads, bridge queue, stdout/stderr
   and secret config cleanup settle; Headroom cleanup reports `complete: true`.

The retained per-cell `run/` contains native ingress/events, runtime preparations,
captures, source/executor receipts, worker RPC/replies and cleanup. Provider
requests/actions, per-cell checks and failures are written even when invocation
fails. Interruptions propagate only after installed API cleanup and driver
evidence handling. There is no runtime subprocess wrapper or outer timeout.

### Pinned failed-view renderer

`native-view-missing-path-1.0.95-v1` is backed by the selected decoded records in
`fixtures/native-003-missing-path.json`, with original plan/process/ingress SHA256s.
Only `view`, top-level `success is False`, `rte is False`, absent/null result,
`error.message == "Path does not exist"`, `error.code == "failure"`, and telemetry
properties `command == "view"`, `viewType == "unknown"`,
`resolvedPathAgainstCwd == "false"` enable this rendering. The last value is a
string, not boolean false. The unchanged frozen action path must also be a
nonempty absolute Windows path of at most 4096 characters without NUL.

After exact start/action argument matching, the expected text is exactly:
`Path {issued_absolute_path} does not exist. Please provide a valid path.`
No path reread, resolution, normalization or filesystem existence check occurs.
Other supported error-only shapes remain literal text; malformed shapes reject,
and any unknown rendered delivery mismatches. Plain result.content remains
authoritative when present. The failure does not acquire source authority.

An attempted-cell record is appended **before dispatch**, then updated in place
with native-dispatch status, observed primary-request count, capture-row counts
and a partial/failed/interrupted outcome. The run summary separately lists
`attempted_cells` and `remaining_unattempted_cells`; an exception cannot erase
an attempted cell. Missing capture files have unknown (`null`) counts, not zero.
Failure before the next dispatch does not reclassify an earlier completed cell.

Every metadata save is attempted independently. The first operational
`BaseException` retains precedence over provider shutdown, capture inspection,
final validation and later reporting failures. Later failures are annotated on
that exception and, where storage permits, in `reporting_failures`. A failed
write invalidates acceptance, stops further dispatch and cannot return success.
If all reporting fails, the original exception still propagates; no additional
calls, broad cleanup or metadata rewrite/retry is attempted. `summary.json` is
the result surface, with no terminal-summary print that could mask propagation.
Incomplete/failed writes are not acceptance evidence; successful driver exit
and complete evidence are both required. The exclusive `started.json` remains
the one-shot boundary even when result persistence fails.

## Two-stage parent invocation — examples, NOT executed here

The parent previously prepared `runs/native-001`, followed by the
`native-002` and `native-003` executions summarized above. All old runs, plans and
results remain immutable. The parent owns retention/status annotations. This fix requires a
fresh install and **new** output/freeze after review; do not re-seal or rerun
any old output to absorb changed qualifier bytes.

Use the existing development interpreter. Supply a **fresh reviewed isolated
install** in repository evidence; the existing install receipt is mandatory.
There is no default output, package, native executable or remote provider URL.

```powershell
$q = 'evidence/integrated-runtime-20261009/native-ranged-results/qualifier'
$out = 'evidence/integrated-runtime-20261009/native-ranged-results/runs/<new-id>'
python -I -B "$q/qualify_ranges.py" prepare --output $out `
  --package <isolated-installed-home/token-master> `
  --install-receipt <isolated-install.json> `
  --native-executable <qualified-absolute-copilot.exe> `
  --tokenizer-file <verified-local-cl100k_base.tiktoken> `
  --ponytail-export <pinned-ponytail.json> `
  --headroom-assets <verified-headroom-assets.json> `
  --headroom-cache <existing-model-cache> `
  --root-reference-style compact-root-v1
```

Omit `--root-reference-style` to retain annotated-v1; compact is never selected
automatically based on a previous result.

`prepare` only validates/hashes local installed inputs, allocates public
workspaces, and writes a **new** `plan.json` plus `plan-seal.json`. It never
creates the canned provider or calls runtime. Review and retain the seal before
any inference/protocol launch. It also freezes authoring files, production
sources, executable/interpreter, vocabulary, resource manifest, original public
documents, copied workspace inventories and exact action arguments.

In a separate fresh interpreter, after parent review:

```powershell
python -I -B "$q/qualify_ranges.py" run --output $out --execute-reviewed-canned-protocol
```

This explicitly gated command starts the canned **loopback-only** upstream and
invokes installed `run_native_copilot` synchronously on the driver main thread.
There is no input for an external model endpoint, credential or arbitrary tool.
The installed runtime owns native/Docker lifetime and cancellation. The driver
never wraps runtime in `subprocess.run`, a worker thread or an outer process
watchdog. `started.json` is an exclusive one-shot marker; no restart into the same
output. Failures and unused schedule entries remain evidence, not erased history.

Public workspaces and the installed package are deliberately retained for audit,
including on preparation failure or uncertain process settlement. The driver
does not recursively delete files or globally stop processes/containers. Owned
runtime process/config/component cleanup is mandatory for a pass. This is not
an OS-sandbox certificate; the parent's native isolation review still applies.

## Offline authoring checks

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -I -B -m pytest -q -p no:cacheprovider --noconftest `
  -c "$q/pytest.ini" "$q/test_checks.py" "$q/test_driver.py" `
  "$q/test_root_styles.py" "$q/test_missing_path_renderer.py"
```

Tests import the standard-library checker and guarded driver, use tiny explicitly
synthetic in-memory protocol records, inspect production recovery/driver AST,
and check two document hashes. Driver-path tests call `run`/`invoke` only with
runtime, provider, installed imports, tokenizer, filesystem and metadata writes
replaced by offline mocks. No real provider is constructed and no actual
`prepare`/`run` workflow, token counting or native/Docker/network/model code is
invoked. The in-memory fake output path is never created on disk.
Syntax-check local Python with `compile(source_bytes, filename, "exec")`, not
execution of the driver. No dependencies need to be installed.

Passing these tests means the **authoring/checker slice** is ready for review,
not that a real installed qualifier has passed. Parent integration can still
fail on live schema/version differences, unavailable installed resources,
non-reducing natural document output, Root/fragment delivery or cleanup.
