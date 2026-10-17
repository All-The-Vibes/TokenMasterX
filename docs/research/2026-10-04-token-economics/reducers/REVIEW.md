# Direct harness mechanisms: RTK, TOON, and Context Mode

**Observed October 4, 2026.** This supplements the eight-candidate OSS study with three especially relevant GitHub implementations. Source was inspected, not installed or executed. Stars are a time-specific adoption signal, not a quality score.

## Snapshot and provenance

| Repository | Stars / forks | Inspected source SHA | Release observation | License at inspected revision |
|---|---:|---|---|---|
| `rtk-ai/rtk` | 82,363 / 5,241 | `c356374fc1c9cff132c02484d2b9195c796b8e8f` | Latest designated release `v0.51.0`, October 2; inspected default branch is `develop`, and its Cargo manifest says `0.49.0` | Apache-2.0 |
| `toon-format/toon` | 25,454 / 1,123 | `0b615d8da1fcfaa64534a26e65fe842f97220e85` | `v4.1.1`, August 5; inspected package manifest also says 4.1.1 | MIT |
| `mksglu/context-mode` | 25,380 / 1,815 | `a83c20165125850473e9344421cf7f374201f0fe` | `v1.0.169`, June 29; head has October 4 changes | **Elastic License 2.0**, despite GitHub's generic `NOASSERTION` metadata |

All three were non-archived. Default-head dates were October 3, October 3, and October 4 respectively. These are head-source observations, not certification that every published binary or package contains the inspected code.

`summary.json`, each repository's `metadata.json`/`tree.json`, and `source-index.json` preserve primary API metadata, selected file URLs, full SHA pins, local paths, and content hashes. Twenty-one source/manifests/test files were retrieved.

## 1. RTK: prevent verbose command results from entering context

### What the implementation does

The inspected pytest wrapper adds bounded reporting options when the user has not supplied them, parses output with a state machine, and presents failures and a summary rather than the full test stream. It explicitly requests expected-failure/unexpected-pass reporting. A nonzero exit that otherwise looks like “no tests” falls back to a truncated raw view rather than silently claiming success.

Evidence:

```text
rtk-ai/rtk@c356374fc1c9cff132c02484d2b9195c796b8e8f:
  src/cmds/python/pytest_cmd.rs:20-71      command setup and fallback
  src/cmds/python/pytest_cmd.rs:77-160     parser states and failure retention
  src/cmds/python/pytest_cmd.rs:358-426    inspected success/failure assertions
```

Recovery hints dispatch to configurable SQLite or legacy tee storage. SQLite mode stores failures/truncations, not every successful output; the test explicitly checks that a successful run creates no database. This is a useful recovery pattern, not a universal exact-retention guarantee.

```text
src/core/tee.rs:17-66,69-105,129-142
```

### Accounting caution

The token estimator calls `text.len()` and divides by four. In Rust this length is UTF-8 bytes, despite nearby comments describing characters. It is a cheap proxy, not native provider usage. Per-command accounting allows negative savings rather than pretending every transform wins.

```text
src/core/tracking.rs:607-636,1779-1806
```

### Transfer to TokenMaster

**Recommended pattern:** origin-tool-specific reducers, fallback behavior, bounded views, and recovery references. Compare with existing Brainspace generic log processing rather than stacking both blindly.

**Acceptance tests:** retain exact failure IDs, traceback/cause lines, warnings relevant to the task, exit status, unexpected passes, and a recoverable original whenever material content is omitted. Include colored output, non-English text, Windows encodings, malformed output, zero-test runs, and oversized failures.

**Boundary:** RTK runs/wraps real commands. Auto-rewriting must not broaden approved command permissions or alter argument semantics. The inspected manifest requires Rust 1.91 when building this head and includes bundled SQLite; no learned compressor is required for this parser. Existing command/network behavior is not eliminated by filtering its output.

## 2. TOON: factor repeated structure, but choose by data shape

### What the implementation does

The tabular classifier verifies a consistent field set across rows, classifies primitive columns, and recursively permits uniform nested object columns. Nonuniform inputs fail that tabular classification rather than being silently flattened into the same table.

```text
toon-format/toon@0b615d8da1fcfaa64534a26e65fe842f97220e85:
  packages/toon/src/encode/tabular.ts:6-36,39-77
  packages/toon/src/encode/encoders.ts
  packages/toon/test/decode-security.test.ts:7-37
```

The inspected decoder tests check that prototype-like keys remain ordinary data rather than mutating object prototypes. Tests were read, not run.

### The baseline changes the conclusion

**Publisher benchmark, not reproduced here:** its mixed-structure token report totals **264,734 TOON tokens versus 260,451 compact-JSON tokens**: TOON is **1.6% larger**. For its tabular feature flags, TOON is **32.8% smaller** than compact JSON; for its semi-uniform logs, it is **19.9% larger**.

The same project's separate 244-question/four-model comprehension report gives 72.2% TOON accuracy versus 71.4% pretty-JSON accuracy, with overlapping reported uncertainty intervals. Do not turn that small difference into a universal correctness improvement, or substitute pretty JSON for the strongest compact baseline.

```text
benchmarks/results/token-efficiency.md:6-50
benchmarks/results/retrieval-accuracy.md:1-32,36-51
```

### Transfer to TokenMaster

**Recommended experiment:** add a shape-gated representation candidate next to existing JSON compression, not a global format replacement. Compare compact JSON, a stable table/CSV when lossless for the shape, and TOON. Count format instructions and metadata in the complete prompt. Preserve exact values, types, null/missing distinctions, column identity, escaping, and cardinality.

Use this as a model-facing view only where the consumer supports it. Do not replace mandatory JSON tool-call/API schemas with TOON. The reference package is TypeScript/ESM and MIT; adopting it into the Python plugin introduces a runtime boundary. Study the format/spec first and evaluate whether the current compressor already captures most of the repeated-key benefit.

## 3. Context Mode: execute and index outside the conversation

### What the implementation does

The content store chunks evidence and uses SQLite FTS5/BM25 to retrieve exact text. It puts a 4,096-byte cap on persisted chunks and has tests around oversized-content handling. The executor writes code to a temporary directory but runs processes with an explicit project working directory, platform-specific launch handling, timeouts, and a constructed environment.

```text
mksglu/context-mode@a83c20165125850473e9344421cf7f374201f0fe:
  src/store.ts:1-8,149-162,475-478
  src/executor.ts:282-310,409-449
  src/security.ts:154-174
  tests/store-bytecap.test.ts
  tests/executor/win-sandbox-782-788.test.ts:81-112,137-160
```

The inspected path-containment tests cover outside-project paths, traversal, prefix siblings, and escaping symlinks. They also explicitly test fail-open behavior when no project root is known and approved outside-project reads. Those are policy choices to review, not evidence of unconditional isolation.

```text
tests/security/project-boundary-852.test.ts:43-100
```

### Transfer to TokenMaster

**Recommended pattern:** let deterministic code answer aggregate/filtering questions outside the prompt; index large raw results and return query-specific slices with continuation/provenance. This is often more fundamental than deleting tokens from a blob after acquisition.

**Safety:** a subprocess/temp directory is not, by itself, an OS-level security boundary. Validate filesystem/network/resource isolation for untrusted execution and preserve host approval semantics. Exact-text BM25 retrieval can still miss semantically related evidence; use nonliteral and temporal-revision test cases.

**Licensing gate:** the inspected LICENSE is ELv2 and contains hosted/managed-service restrictions. This is source-available code with restrictions, not a permissive-MIT dependency merely because it is public on GitHub. Get an appropriate license review before copying, bundling, or offering its functionality as a hosted service. Architectural study does not authorize wholesale source reuse.

```text
LICENSE:1-28,43-49
package.json:1-7,61-85
```

## Recommendation across the three

The best near-term idea is **small, task-specific tool interfaces that produce the needed evidence directly**. Combine this with accurate metering, stable context assembly, and complete scoped recovery.

Use RTK as the command-reducer reference; TOON as a selectively chosen representation; Context Mode as an out-of-band execution/retrieval reference subject to license and safety gates. None independently proves lower end-to-end billed cost or equal task quality for TokenMaster.
