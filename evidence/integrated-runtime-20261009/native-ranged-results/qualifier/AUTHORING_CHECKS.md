# Offline authoring verification — 2026-10-09

**Latest pinned-renderer repair: 153 offline tests passed; six Python files
passed syntax checks.** The evidenced 1.0.95 missing-path renderer is handled
without changing tasks or rerunning a protocol. See appended RED/GREEN records.
Earlier counts are historical authoring evidence; parent-owned execution
outcomes are recorded separately below.

Status: **ready for parent review; NOT RELEASED OR EXECUTED**.
Neither `qualify_ranges.py prepare` nor `qualify_ranges.py run` was invoked.
No installed production module, provider socket, native executable, Docker
component, model or dependency installer was invoked by these checks.

## Fresh checks

Working directory: `C:\Users\shyamsridhar\code\TokenMaster`.

```powershell
$q='evidence/integrated-runtime-20261009/native-ranged-results/qualifier'
$old=$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
try {
  python -I -B -m pytest -q -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_checks.py"
  $code=$LASTEXITCODE
} finally {
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=$old
}
```

Final fresh output:

```text
..........................................                               [100%]
42 passed in 0.11s
```

Exit code: 0. Scope: new qualifier's pure checker, script schedule, driver AST
and exact SHA256 equality of the two original public documentation files.
Protocol records and numerical fields in unit tests are deliberately tiny
synthetic fixtures, not observations, token counts or native qualification.

Earlier incremental offline runs: 27 passed in 0.11s; 36 passed in 0.15s.
No failed run was overwritten or represented as native success.

Syntax-only command: pipe this script to `python -I -B -`:

```python
from pathlib import Path
for p in sorted(Path('evidence/integrated-runtime-20261009/native-ranged-results/qualifier').glob('*.py')):
    compile(p.read_bytes(), str(p), 'exec')
    print('syntax PASS', p.name)
```

Output:

```text
syntax PASS checks.py
syntax PASS qualify_ranges.py
syntax PASS test_checks.py
```

No code object was executed, and no bytecode/cache artifact was created.
There is no package build target or new dependency.

## Parent integration update incorporated

The checker now requires the v2 runtime identity
`copilot-native-runtime-view-result-v2`, selected `native-view-result-v2` in
executor/launcher/runtime receipts, and exact native completion text as the
recovery oracle. Argument checks use strict canonical JSON identity, rejecting
boolean/integer and integer/float substitutions. Existing default
`native-full-view-v1` remains a required installed-API signature precondition.

## Remaining evidence / stop condition

This is not installed execution evidence. The parent must review the new files,
finish/regress the production API/launcher/CLI lane, provide a reviewed isolated
installation and dependencies already present, then explicitly release and
invoke the two-stage preparation/run flow from DESIGN.md.

Preparation will create a new output and source/install/resource/authoring
freeze before any runtime/provider launch. Native range formatting, successful
public-pipeline reduction, Root and emitted-fragment round trips, actual
component settlement and original-input nonexpansion remain unverified until
that permitted run. Failure cannot be repaired by changing these pinned tasks
or silently retrying the same output.

## Parent pre-dispatch fixes — RED/GREEN, still no real execution

Scope remains only this `qualifier/` directory. No parent plan, production source,
old runtime evidence or frozen corpus was edited.

Changes:

1. Root request now has exactly `{ref, offset}`. The 32768-character page cap is
   server-owned. `test_driver.py` parses the actual production `_RECOVERY_TOOLS`,
   `RuntimeSession.recovery_tools`, `_recover_content` and CCR `_PAGE_LIMIT`
   definitions; it does not import or execute production.
2. Run records attempted cells before dispatch and retains the mutable per-cell
   outcome during interruption. It records whether native dispatch occurred,
   observed upstream request count and available capture-row counts separately.
   Missing capture evidence is unknown, not zero. Only genuinely undispatched
   schedule entries remain unattempted.
3. Independent metadata writes catch reporting failures without replacing the
   first `BaseException`. Provider shutdown and final validation cannot replace
   the original interrupt either. Failures invalidate acceptance; no further
   cell dispatch, retries or broad cleanup occurs. The exclusive start marker
   prevents restarting after interruption or failed summary persistence.

RED command (environment as above):

```powershell
python -I -B -m pytest -q -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_driver.py"
```

Fresh result before fixes: **7 failed, 1 passed in 0.32s**, exit 1.
Failures proved the unsupported `limit` argument, absent attempted-cell record,
masked original interrupt at four metadata-write boundaries, and failed
persistence handling. The pre-existing non-restart path passed.

GREEN command:

```powershell
python -I -B -m pytest -q -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_checks.py" "$q/test_driver.py"
```

Fresh final output: **57 passed in 0.20s**, exit 0.
An intermediate run after the initial repairs passed 50 tests in 0.20s.
Additional cases cover simultaneous save failures, provider shutdown failure,
later final-validation interruption, original SystemExit precedence, unknown
missing-capture counts, unchanged main-thread 5+3/global-eight-call allocation,
summary-write failure plus non-restart, and failure before a second dispatch
without corrupting the first cell's completed outcome.

The syntax-only command above passed all four files:
`checks.py`, `qualify_ranges.py`, `test_checks.py`, `test_driver.py`.
An explicit filesystem check reported `mock output created: False`.

The new tests exercise the guarded driver's `run`/`invoke` functions with all
runtime/provider/installed-import/tokenizer/filesystem boundaries mocked in
memory. This is **not** a real preparation, native invocation, network listener,
token measurement or canned-protocol run. Real invocation remains unperformed
and awaits parent review, freeze and release.

## Final reviewer hold: failed-view text — RED/GREEN, no protocol execution

Read the final finding in the parent's `native-ranged-results/REVIEW.md` and the
current production `native_events.py` failed-view binding. No production or
review-report file was edited.

`checks.observed` now returns exact string text or rejects the event:

- Valid plain `result.content` takes precedence, with the supported
  `content`/optional-string-`detailedContent` failure schema.
- For strictly failed native views only, omitted or null `result` permits the
  literal string `data.error.message`. No guessed prefix or text normalization.
- Missing/unsupported error text and malformed non-null results raise ValueError;
  a malformed result cannot fall through to otherwise valid error text.
- Successful error-only results do not acquire a failure-text fallback.
- Successful native MCP rendered `content`, including detailed/MCP block
  representations, is preserved. Both Root and vendor-recovery paths are tested.
- `assess` no longer has a None-based exception to observed-result equality.
  Failure status remains false; expected source receipts still count only the
  successful partial view, never the failed view.

RED command (same isolated pytest environment as above):

```powershell
python -I -B -m pytest -q --tb=line -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_checks.py" -k 'failed_view_observed or error_only or failed_result or failed_text or native_mcp_rendering'
```

Before the checker repair: **32 failed, 4 passed, 42 deselected in 0.32s**,
exit 1. This reproduced omitted-result None bypasses, explicit-null
AttributeError, altered/prefixed delivery passing, and unsupported failed
representations not rejecting.

GREEN command:

```powershell
python -I -B -m pytest -q -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_checks.py" "$q/test_driver.py"
```

Fresh complete result: **95 passed in 0.27s**, exit 0. Both omitted and explicit
null results pass only with literal matching text. Assess-level altered and
`Error: `-prefixed delivery regressions cover plain/omitted/null shapes; the
other records intentionally agree so only native observed text exposes the
change. Unsupported forms, non-null fallback attempts, whitespace/CRLF/Unicode,
empty literal strings, and successful MCP rendering are covered.

Fresh syntax checks passed `checks.py`, `qualify_ranges.py`, `test_checks.py` and
`test_driver.py`; `mock output created: False`. All driver-path calls remained
offline mocks. No native, model, Docker, network listener, real prepare/run,
dependency installation or token measurement occurred.

Only qualifier files changed. Per the parent's update, prepared
`runs/native-001` and its frozen plan were left untouched. The parent owns its
retained/never-started annotation and the future fresh freeze of `native-002`;
neither action was performed in this authoring lane.

## Explicit compact Root-reference opt-in — offline authoring only

New parent evidence supersedes the earlier future-run note: the parent reports
`native-002` ran three canned calls with real Headroom, but its annotated Root
cost 161 reference tokens against a 124-token projection benefit. The complete
wire grew by 37, correctly reverted, and produced zero recoveries; the exact cell
was unattempted. This lane did not rerun, amend, rescore or inspect old run outputs
to reshape tasks. `native-001`/`native-002` remain untouched. The parent will
supply a fresh install and fresh plan after review.

Qualifier-only changes:

- `prepare --root-reference-style` accepts `annotated-v1` and `compact-root-v1`,
  default annotated. The value enters installed typed RuntimePolicy as
  `headroom_root_reference_style`, and is frozen in `plan.root_reference_style`.
  Policy JSON comes from `policy.to_dict`; a source-backed AST test confirms
  the actual serializer's annotated omission. Plan/policy mismatch rejects.
- Known compact `[[BR:<64hex>|r=1]]` and existing annotated V2 Root formats are
  recognized without changing reference bytes. Unknown/malformed and cross-style
  substitutions reject. Toy-only unit markers were replaced by structurally
  valid annotated fixtures; public sources were not edited.
- Reports include selected style and delivered ref. Scheduling a marker,
  including before interruption, does not set `native_root_lookup_verified`.
  Actual native recovery and exact original observed-result equality remain
  required. A different opaque ref or fresh whole-file content fails.
- Document hashes, native actions/ranges/arguments, prompt, 5+3/global-eight-call
  schedule, main-thread ownership, protection/recovery guards and strict
  complete-wire acceptance remain unchanged. No padding, ratio tuning, retries,
  promotion or required winning result.

RED command (existing isolated pytest environment):

```powershell
python -I -B -m pytest -q --tb=line -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_root_styles.py"
```

Before implementation: **22 failed, 1 passed in 0.38s**, exit 1. The single
passing test compared examples against the actual production CCR pattern
definitions using AST/literal parsing only.

GREEN command:

```powershell
python -I -B -m pytest -q -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_checks.py" "$q/test_driver.py" "$q/test_root_styles.py"
```

Fresh final result: **122 passed in 0.54s**, exit 0. An intermediate complete
run passed 118 tests in 0.59s. No real prepare, native, Docker, model, network or
storage-backed CCR lookup was invoked. Typed-policy construction uses a spy;
actual serializer/marker definitions are read as AST. Mocked driver tests retain
main-thread, interruption, non-restart and zero lookup-credit-without-delivery
checks.

Fresh syntax checks passed `checks.py`, `qualify_ranges.py`, `test_checks.py`,
`test_driver.py`, `test_root_styles.py`; `mock output created: False`.
No new output or freeze was created. Compact lookup and benefit remain unverified
until the parent's reviewed fresh-install protocol invocation.

## Native-003 evidenced missing-path renderer — offline repair

The parent's newer terminal evidence supersedes the previous pending-run note:
overview passed five canned calls with real compact Root/native Root/fragment
recovery, but exact failed after two canned calls because actual missing-file
delivery was not literal event.error.message. Retain **overall failure, seven
canned calls, zero real-model calls**. No old result is upgraded and the exact
cell remains part of the unchanged future full schedule.

Read only native-003's frozen plan, exact native-process.json and last received
native-ingress request. The completion was success=false/rte=false with omitted
result, `{message: "Path does not exist", code: "failure"}`, and telemetry command
view, viewType unknown, resolvedPathAgainstCwd string "false". Model-bound text
was exactly `Path {issued_absolute_path} does not exist. Please provide a valid path.`

Selected decoded records were copied into the new qualifier-only fixture
`fixtures/native-003-missing-path.json`; this is neither a new run nor a public
task-source change. Fixture provenance records the renderer label and these
original SHA256s, rechecked unchanged after all offline tests:

| Original native-003 file | SHA256 |
|---|---|
| plan.json | d59cc6424236fbc6a71388849e292457ea50ee29095dd3d10cfc417a6be707d3 |
| exact/run/native-process.json | 9a443a340bf7b77b2ac3c56c61cdc2bb5342be412b21c83da298978c26705e41 |
| exact/run/native-ingress.jsonl | 8c3806faf1fdafc9ecb44fa1950204aa94d684c07678317458ca88137c49b6d5 |

`checks.observed` now applies only the pinned
`native-view-missing-path-1.0.95-v1` renderer under those exact conditions, with
the bounded absolute Windows path from frozen action arguments already matched
to native start. It performs no filesystem lookup or text/path normalization.
Unknown cases still reject or mismatch; plain native result.content and other
literal failure messages retain their previous semantics. Failure remains
failure with no extra source receipt.

New `test_missing_path_renderer.py` has 31 cases: captured omitted/null results,
assess-level acceptance without source authority, wrong event/delivery path,
code/message/telemetry/status flags, string-versus-boolean telemetry, exact
punctuation/spacing, generic Error-prefix and literal-only rejection for this
known case, invalid path shapes/length/NUL, plain-result precedence, and a
filesystem-access prohibition around renderer execution.

RED command (existing isolated pytest environment):

```powershell
python -I -B -m pytest -q --tb=line -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_missing_path_renderer.py"
```

The first RED attempt encountered a test-isolation error: a global Path-method
mock also blocked pytest's failure reporting (exit 3; 5 failures and 25 passes
reported before the internal error). Narrowed that mock to a context restored
before assertion reporting, without weakening the filesystem prohibition.
Fresh complete RED result: **6 failed, 25 passed in 0.15s**, exit 1.

GREEN command:

```powershell
python -I -B -m pytest -q -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q/test_checks.py" "$q/test_driver.py" "$q/test_root_styles.py" "$q/test_missing_path_renderer.py"
```

Fresh result: **153 passed in 0.51s**, exit 0. Syntax compilation passed all six
Python files. Original evidence hashes above matched, and
`mock output created: False`. No native/Docker/model/network/prepare/run or token
measurement was invoked in this repair lane.

Only qualifier files changed. Documents, ranges, prompt, schedule, selected style
interface, reduction/protection/recovery guards and global-eight-call bound are
unchanged. `native-003` remains frozen and failed. Parent review and a fresh
install/freeze precede any `native-004` full-schedule invocation.
