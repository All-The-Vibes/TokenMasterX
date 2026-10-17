# Jev token-efficiency and parity implementation

Started October 4, 2026. Baseline: `426fc853389ddba4bc6e1dd35a28179a895c064f`.
Working branch: `codex/jev-token-efficiency`.

## Contract

Implement the mathematical Jev framework and the bounded parity backlog.
The newer user scope is authoritative: reference-token efficiency and
independently verified outcomes, not prices, billing, credits or monetary ROI.
No foundation-model weight changes. Jev proposes/screens; it never supplies
authorization, truth labels, or its own deployment certificate.

Source requirements:

- `docs/research/2026-10-04-token-efficiency/FRAMEWORK.md`
- `docs/research/2026-10-04-parity/GAP_BACKLOG.md` (G09/G11 monetary language
  replaced by the token-only scope)
- `docs/research/2026-10-04-token-economics/foundations/PROOFS-AND-CONTINUOUS-IMPROVEMENT.md`
- Source-pinned Ponytail/Headroom dossiers and current official host/Jev docs.

## Required delivery matrix

| ID | Required result | Proof needed | Current status |
|---|---|---|---|
| G01 | Actual equality-based recovery validation, honest no-op/fragment/root reporting | Fault-injected missing/wrong/corrupt originals fail; benchmark exits nonzero | Implemented; nine regressions reproduced before repair, then passed |
| G02 | Recovery-required transforms preserve originals on storage/grammar failure | Regression fixtures for all compressors and failure modes | Implemented; exact conservative defaults and failure diagnostics tested |
| G03 | Schema-preserving, capability-aware host output adapters | Envelope tests plus isolated real-host acceptance evidence | Implemented; fresh 11-cell Claude 2.1.289 native envelope matrix and real user-settings install/uninstall lifecycle passed; captured MCP-array bug repaired; other native versions remain unqualified |
| G04 | Final representation token/byte guard; out-of-band telemetry | Wrapper, reference, Unicode and serialized-cap regressions | Implemented; final real MCP result envelope checked, no savings footer |
| G05 | Scoped task discipline and bounded review without suppressing requested depth | Mode lifecycle, no-edit/no-scope-creep/depth-preservation evaluations | State/CLI/templates and compact rendering implemented; bounded real-model explain/fix/abstraction challenges and blinded proof review passed; representative qualification remains open |
| G06 | Task-sensitive structured views and conservative bypasses | Exact text/aggregates/heterogeneous rows/rare errors/patch fixtures | Implemented; Python/Rust grammars exercised, protected intents and rare errors tested |
| G07 | Complete paged/scoped recovery, exact search, integrity and retention | Public-tool reconstruction, corruption/isolation/GC/session tests | Implemented; real stdio MCP reconstructs 200001 Unicode characters across seven pages |
| G08 | Explicit Claude/Copilot/Codex and native Windows integration | Isolated config/MCP/host tests, safe install/uninstall/locking and pinned runtime | Claude/Copilot native MCP passed; Codex CLI transport passed but user-skill no-read isolation failed; separate Desktop state does not prove whole-process isolation, so no unsafe launch was attempted |
| G09 | Harness-neutral complete-reference-token ledger and evaluation protocol | Whole-task accounting, incomplete-trace rejection, learning/runtime separation, outcome gates | Implemented; original pilots plus a source-pinned 24-run four-arm comparison and eight-run retention holdout completed, with raw audits and failures retained; representative/statistical qualification remains open |
| G10 | Graph freshness, provenance, bounded completeness/paging | Post-load edits/index replacement/high fanout/ambiguity tests | Implemented and tested; freshness is explicitly limited to indexed files, inferred edges are not semantically exhaustive |
| G11 | Request-level task/budget/prefix policy, protected roles and tool pairs | Deterministic multi-turn/protocol/safe-budget/recovery tests | Implemented with thin actual-router/CCR adapter and CLI; no implicit host interception |
| G12 | Opt-in advanced Jev engine with deterministic fallback and bounded resources | Actual sanitized Jev calls, disclosure, disable path, privacy and failure tests | Typed client, caps and fallback implemented. The latest real metric screen abstained; deterministic fallback selected a retention neighbor with a lower-token four-task holdout observation. Jev-caused benefit, repeatability and promotion remain unproven |
| M01 | Pinned reference measurement identity and no false exactness | Tokenizer/protocol identity, unknown/native-count separation | Implemented and tested; verified offline vocabulary, ordinary literal encoding, estimates excluded from certificates |
| M02 | Fresh paired certification with cumulative error spending | Proven constants, frozen candidate/incumbent, replay/stopping and strict-gate tests | Strict fixed/anytime implementation independently reviewed; quality-floor/ratio alternatives intentionally not implemented or silently substituted |
| M03 | Bounded policy mutations and durable champion/search lifecycle | Candidate validity, confirmation isolation, atomic promote/rollback, resumability | Implemented; final independent mixed-replay audit approved, 18 focused freshness regressions passed |
| M04 | Real Jev typed-decision client integrated as advisory candidate screening | HTTP/schema/range/timeout/failure/secret-safe tests plus live smoke | Client and real controller-integrated screening passed; sealed learning accounting and reopened promotion verified on a toy primary evaluator |
| M05 | Usable documented CLI/workflow and reproducible token-only experiments | Actual command invocations and saved machine-readable evidence | CLI/request/recovery/mode tools and installed entrypoints verified; final aggregate test receipt tracked below |

G12 does not mean recreating every Headroom proxy, image engine, dashboard
or hosted service: the referenced backlog explicitly scopes these separately.
The requested Jev path is the advanced opt-in backend being delivered.
Unsupported host/features must remain explicit, not be counted as verified.

**Release qualification remains incomplete.** Mock-provider native transport,
synthetic evaluator success, and source/unit evidence do not establish
representative real-model task-quality/token parity. The implementation goal is
not marked complete while required verification gates remain open.

## Evidence recorded so far

Local, non-secret evidence is in
`evidence/jev-implementation-20261004/` (ignored by the existing packaging rules).
The original commit was extracted into an isolated archive and tested with
the provisioned dependencies: **120 passed**. New tests were observed failing
before each repaired behavior. The **earlier implementation checkpoint passed
855 tests with zero failures/errors/skips**, plus one nonfatal dependency warning. Results are
recorded in `pytest-final.txt` and `pytest-final.xml`; `pytest-current.*` retains
the earlier 834-test run rather than concealing the validation sequence.

- `jev-live-smoke.json`: one real synthetic TypeSafe request, typed validation,
  native diagnostics and separate reference counts; no model-quality claim.
- `mcp-roundtrip.json`: 200001 characters / 558821 UTF-8 bytes reconstructed through
  the public MCP tool, seven pages, full/page hashes and bounded search.
- `native-host-smoke/summary.json`: actual CLI versions, provider-bound acceptance,
  blockers, tested source hashes, and mock-provider-only scope.
- `dev-freeze.txt`: isolated installed versions; runtime closure pins ship with
  the plugin.
- `mypy-final.txt`, `ruff-final.txt`, `pip-check-final.txt`: all 30 production
  files passed configured static checks; dependency consistency passed.
- `jev-screened-controller-smoke.json` and `controller-cli-status.json`: real Jev
  proposal screening followed by 128 fresh toy pairs, a persisted certificate,
  complete learning accounting, and a reopened champion at version 2. Not a
  real primary-language-model quality benchmark.
- Final bounded controller review approved source SHA-256
  `ceb1e25e3f4a8ab3546f94d278f2c984a0250fe36e01d8295bf4a54eb2100ad5`.
  Mixed rejected batches consume unseen sibling call IDs before rejection;
  replay remains blocked after restart and fresh controls still pass.

## Real-model pilot and objective-check continuation

The separate evidence root is `evidence/jev-quality-20261004/`.

- `pilot-frozen-v2/`: eight non-IID synthetic-workspace tasks, two arms, actual
  model actions, generated-code hidden tests and complete bridge-body captures.
  Both arms passed 8/8 after the recorded blinded mathematical review.
- The offline savings checker verifies raw source/call/outcome identities and
  recounts bodies instead of trusting summaries. The exploratory totals are
  104775 → 101117 body-reference tokens; separate bridge-reported diagnostics
  are 45699 → 40776. One navigation case dominates; six cases use more reported
  tokens. No population confidence interval, certificate or policy promotion.
- A later real Jev call reported 3056 reference learning tokens and proposed
  `min_tool_chars: 512 → 384`. The deterministic activation audit observed no
  changed routing on the 27 recorded combined-arm requests; it made no model
  calls and is not a global equivalence proof.
- The independently reviewed WSL sandbox covers the exact limited code-execution
  bundle, not general sandbox certification. Supervisor resource mutation and
  untrusted preflight AST allocation have dedicated regressions.
- Original failed preflights and the intermediate 1023-pass/one-failure test
  receipt are retained. The latter exposed a startup race in the Windows cleanup
  test, repaired with bounded readiness and a retained process handle; current
  aggregate results are tracked in `VERIFICATION.md`.
- The objective-audit continuation now passes **1079 tests** in a fresh full
  run. Independent review closed all five raw-inventory/history/outcome gaps.
  A test-only repair covers either memory exhaustion or the trusted preflight
  deadline without relaxing execution/cleanup checks or production limits.
- The requested arXiv `2608.05643v1` parallel research is complete in the local
  paper dossier. It proposes a separately frozen iterative/multi-model study;
  no new inference route or relaxation of the existing strict joint gate has
  been implemented or authorized by that research.

See `OBJECTIVE_SAVINGS.md` for the reproduction command, raw count semantics,
learning exclusions, and the distinction between audit consistency and a proof
of improved expected efficiency.

## Native-envelope continuation

`evidence/native-envelopes-20261005/final-matrix/` records a fresh **11/11**
native Claude 2.1.289 matrix under one source inventory. Successful Read, Grep,
Bash, fixed PowerShell-via-Bash and MCP JSON text transformations reached the
correlated provider-bound result. Glob, images, mixed MCP content, structured
MCP strings and intentional failures remained unchanged.

The actual native MCP success payload is a bare content array, not the
dictionary previously assumed by unit tests. The repaired production adapter
handles only successful pure-text arrays; failures, mixed content and
unsupported shapes stay passthrough. Captured fixtures and regression tests
cover this boundary.

`final-install-lifecycle/` validates actual native **user settings** rather than
an observer-substituted hook. Installation supplies the bundled tokenizer with
no ambient child tokenizer path, produces the exact expected native result,
and uninstall restores the baseline result. Complete configurations are checked
immediately across install and uninstall, permitting only owned changes; the
unrelated hook and MCP configuration survive. All homes are temporary.

Independent review closed verifier gaps involving status/native-block loss,
false success from matching failures, omitted helper source hashes, and
install-time corruption of unrelated configuration. See `NATIVE_ENVELOPES.md`.
This is transport evidence, not a new real-model or whole-task savings study.

The fresh Windows isolation preflight is in
`evidence/windows-isolation-20261005/availability.md`. No accessible proven
disposable Windows environment was established; feature/VM queries requiring
privileges remain unknown. No real Desktop instance or user profile was
modified to force a pass. G08's Desktop/isolation gate remains open.

## Execution lanes

1. Parent: baseline/runtime, credential resolution, benchmark/router/wrappers,
   Jev client, optimizer integration, request policy, end-to-end validation.
2. Compressor lane: compressor safety and task-sensitive views only.
3. Recovery lane: CCR scoping/integrity/paging/search/retention only.
4. Mathematics lane: neutral token ledger and independent promotion
   certificates only.
5. Host/graph lane: isolated configuration/runtime packaging and graph
   freshness/completeness only.

Write regression tests before changing the unsafe behavior. Keep lane write
sets disjoint; integrate in dependency order. No new dependency category is
needed: use the standard library and dependencies already used by the project.
Install those existing requirements only into an isolated development runtime.

## Safety and credential handling

The user authorized using an existing Jev credential. Locate it from the
specified memory/secure environment without printing, checking it into files,
putting it in command arguments or leaking it to logs. Do not create a new
account/key. Live requests use synthetic/sanitized fixtures, not repository
contents or secrets. No changes to real CLI homes, global routing or live
production configuration during tests.

## Completion evidence

Maintain test/run evidence and a final requirement-by-requirement audit.
Passing unit tests alone does not close host integration or task-quality
requirements. No completion claim while any required item is incomplete or
only indirectly supported. Keep the persistent goal active across turns.

## October 7–8 continuation

The implementation now includes the independently reproduced standalone
rejected-batch call-exposure repair, documented structured Jev responses, and
a reusable source-pinned repository diagnostic with explicit incomplete/budget
accounting and a write-sensitive independent oracle. The full current suite
passes **1,489 tests** with no failures/errors/skips; the 104-file Python
inventory was stable across the run. A separate real synthetic Jev request
exercised object-valued rubric legends without persisting the user key.

The repository comparison finally completed all four tasks in both arms, but
**did not show an overall token win**: 47,815 baseline versus 87,842 enabled-arm
bridge-reported tokens. The navigation task reduced two requests and used 17.0%
fewer bridge tokens; additional reads in a bypassed debugging task outweighed
that reduction. Interrupted studies remain visible with unknown totals.
`CODING_VALIDATION.md`, `PARITY_ANALYSIS.md` and `VERIFICATION.md` contain the
current evidence and limits.

This closes the concrete source-read activation and reporting work, not the
representative behavioral/head-to-head, held-out advanced-engine gain, or
isolated Codex Desktop gates. The full goal is still unproven and remains active.

The later October 8 continuation verified the actual pinned Ponytail instruction
builder and authenticated all 2,542 Headroom archive files. It added a bounded
isolated Linux Codex transport runner using existing fixtures. The combined
suite now passes **1,500 tests and 19 subtests** with a stable 106-file Python
inventory. Official Python wheel-host TLS failures prevented the Headroom
native/runtime setup and Linux native MCP test from reaching qualification.
`PARITY_RUNTIME.md` records the failed attempts, cleanup and exact prerequisite.
No disabled-component comparator, certificate bypass or normal-profile change
was used to close those missing gates.
