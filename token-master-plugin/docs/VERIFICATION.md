# Implementation verification checkpoint

## Latest checkpoint — conservative V3 repair, October 8, 2026

The [repair report](CONSERVATIVE_POLICY_FIX.md) supersedes the status summaries
below while preserving their historical evidence.

- **2,248 tests + 19 subtests passed** across disjoint runs: 2,196 plugin tests,
  51 host-harness tests, and one subsequent installed-copy smoke test. There
  were no test failures/skips and one existing nonfatal Pydantic warning.
- Ruff passes; MyPy with `--check-untyped-defs --follow-imports=skip
  --ignore-missing-imports` passes on the six changed implementation/evaluation
  files. Imported dependency bodies are not claimed type-proven.
- Offline replay: all 69 saved baseline requests remain unchanged; no lossy
  transform or recovery callbacks. This is passthrough evidence, not savings.
- New live run: six reading questions pass in both arms with equal 23 requests
  and 116,883 gateway-reported task tokens. Four deliberate repeated-read
  probes pass in both arms with equal 18 requests and 89,417 versus 80,541
  tokens (9.9% fewer for V3). No recovery calls.
- Independent audit passes: all 20 outcomes regraded, all 82 task captures
  recounted, separate readiness, 41 V3 plans reconstructed, and 47 frozen source
  files plus eight valid derived caches checked. No missing attempts.
- No general savings, fresh production quality, competitor parity, or latency
  claim follows from these bounded diagnostics. Normal profiles, defaults,
  weights, and the older blocked app goal are unchanged.

Evidence: `evidence/conservative-policy-20261008/`.

## Historical checkpoints

Local run begun October 4, 2026, America/Chicago. Baseline commit
`426fc853389ddba4bc6e1dd35a28179a895c064f`; working branch
`codex/jev-token-efficiency`. This is an uncommitted implementation checkpoint,
not a published release or a broad parity claim.

## Checks completed

| Check | Result and boundary |
| --- | --- |
| Original source baseline | 120 tests passed in an isolated `git archive` with provisioned dependencies |
| Previous retention-mechanism plugin and host-harness suites | **1994 tests + 19 subtests passed, zero failures/errors/skips**; stable 121-file Python source/test inventory, one nonfatal MCP/Pydantic warning. `evidence/retention-mechanism-20261008/tests.txt/xml` |
| Previous fresh-replication checkpoint | **1989 tests + 19 subtests passed**, stable 120-file inventory. `evidence/parity-agent-comparison-20261008/replication-tests.txt/xml` |
| Previous comparator/retention checkpoint | **1862 tests + 19 subtests passed**, stable 116-file inventory. `evidence/parity-agent-comparison-20261008/final-tests.txt/xml` |
| Previous scoped-profile checkpoint | **1512 tests + 19 subtests passed**, stable 106-file inventory. `evidence/combined-request-validation-20261008/full-tests.txt/xml` |
| Previous parity-runtime checkpoint | **1500 tests + 19 subtests passed**, stable 106-file inventory. `evidence/parity-runtime-20261008/final-validation/tests.txt/xml` |
| Previous repository-diagnostic checkpoint | **1489 passed**, zero failures/errors/skips; stable 104-file inventory. `evidence/repository-diagnostic-20261007/final-checks/tests.txt/xml` |
| Previous refinement checkpoint | **1372 passed** across disjoint roots: 1332 plugin tests and 40 host-harness tests. `evidence/refinement-20261005/full-tests-final.txt/xml` and `host-tests-final.txt/xml` |
| Earlier native-envelope full suite | **1121 passed, zero failures/errors/skips**; one nonfatal MCP/Pydantic forward-reference warning; `evidence/native-envelopes-20261005/full-tests.txt/xml` |
| Static checks | The earlier core/quality checkpoint passed Ruff, compilation and configured mypy on 38 files plus `pip check`; the changed native work now passes Ruff and configured mypy on seven source files. Mypy does not prove untyped function bodies. |
| Offline savings audit | Raw pilot recounted; all five independent-review findings repaired, nine bypass regressions passed, scoped re-review approved. No population certificate. |
| Earlier integrated implementation suite | **855 passed, zero failures/errors/skips**; one nonfatal MCP/Pydantic forward-reference warning; predates the live-quality/audit additions |
| Earlier follow-up correctness tests | Loader/UTF-8 and rejected-batch replay regressions are included in that 855-test run; source manifest records receipts |
| Earlier production static checks | Ruff, compilation and mypy passed on 30 production files (`--follow-imports=skip --ignore-missing-imports`; not a proof of untyped bodies) |
| Actual benchmark CLI | Synthetic successful log returned `root_exact`, one reference actually retrieved, exit 0; task quality explicitly false |
| Public MCP transport | Exact 200001-character / 558821-byte Unicode original reconstructed across seven pages, full/page hashes verified; exact search and unknown-reference errors exercised |
| Real Jev API | Synthetic Choice, Score and Noul request returned HTTP 200 and passed typed validation |
| Controller-integrated Jev | Real advisory screening plus 128 fresh **toy** paired tasks; saved certificate, sealed learning inventory and reopened promotion exercised |
| Installed entrypoints | Tools and synthetic controller initialization exercised from copied installs under isolated Unicode/space-containing homes for all three configured hosts |

## October 8 live comparator and held-out retention studies

The later exposed-case mechanism mode explicitly distinguishes repeated old
tasks from fresh confirmation and records its order seed. Three predeclared
pairs, with clarified recovery in both arms, reproduced **five versus three
calls** in every pair at unchanged correctness. The incumbent made two genuine
fragment recoveries each time; no wrong Headroom call or re-fetch workaround
occurred. Reference totals were **118010 versus 61213**. Independent audit
verified all six runs, source/control/candidate identities and actual recovery
bytes. This supports the mechanism on the selected exposed case, not
population gain, Jev utility or promotion.

The current 17-item completion audit is
`evidence/retention-mechanism-20261008/completion-audit.json`. The five exercised
native-hook module hashes still match their named historical receipt; four
other modules changed since that snapshot, so a fresh whole-source native run
is not implied. G05/G08/G09/G12 remain incomplete, without weakening their
qualification requirements.

The subsequent replication clarified only the shared recovery descriptions and
wrong-tool error guidance. Tool schemas and actual stores stayed unchanged.
Four new questions passed in both arms with 12 calls each and identical
bridge-reported usage, **35,418 tokens**. Neither arm transformed a request;
the 31-reference-token gap is not evidence of policy savings. The earlier
single-trace retention gain remains unreplicated. Parent audit checked all eight
grades, raw accounting, identical initial requests and 48 frozen source hashes.
The seven guidance regressions and 120 fresh-corpus checks are included in the
current 1989-test suite, not additive counts.

- `evals/run_parity.py` now uses one shared primary loop, common tools and
  original histories for baseline, TokenMaster, pinned Ponytail and pinned
  Headroom. The actual Headroom pipeline and CCR handler run in a fresh
  isolated process per task. Worker source is snapshotted, hash-bound at
  startup and checked again at cleanup.
- Optional diagnostics, inspection-timeout reaping and source-snapshot
  weaknesses were independently reproduced/repaired before the live study.
  The independent recheck approved those three fixes.
- All **24 planned runs / 97 primary attempts including readiness** completed
  visible accounting. TokenMaster and Ponytail each got 6/6 correct;
  baseline and Headroom got 5/6 for different reasons. TokenMaster used more
  primary-reference tokens than Ponytail. An independent audit checked
  source hashes, gold, outcomes, raw counts, histories, RPCs and cleanup.
- One real Jev advisory call used the existing credential process-locally
  and **abstained**, consuming 1260 separately recorded reference learning
  tokens. Deterministic replay reproduced all 28 incumbent inputs and found
  only one activating neighbor: retain two recent results.
- `evals/run_retention.py` tested that frozen neighbor on four independently
  prepared, source-disjoint holdouts with unchanged common controls.
  Both got 4/4 correct; observed reference totals were 100149 versus 62649.
  The effect is concentrated in one case with an incorrect recovery-tool
  selection and source re-fetches in the incumbent. It is not a Jev
  recommendation or a general savings rate.
- The full 1862-test run includes the new runner, boundary, corpus and oracle
  regressions. Targeted suites overlap and are not added to that count.
  No normal host profile, foundation-model weight or promoted default changed.

See `COMPARATOR_RESULTS.md` for the numerical results, failure distinctions,
measurement boundary and explicit qualification gaps. Neither a captured
HTTP 502 nor an incomplete serving-usage counter is silently treated as a
successful zero-cost task.

## October 8 scoped-profile pilot and interruption safeguards

- **Real opt-in run:** existing task discipline plus context views completed all
  four pinned repository tasks correctly in each arm, with 12 calls each.
  Full-body reference tokens were **81,530 → 76,410 (6.28% fewer)**; separate
  bridge usage was **55,603 → 51,868 (6.72% fewer)**. The navigation case
  dominates this one-study result. It is not a population savings certificate,
  pure-compression estimate, or upstream competitor comparison.
- **Offline audit:** all 37 frozen files, eight task results, exact patch bytes,
  source recovery, starting request controls and 25 dispatch receipts including
  readiness checked; original evidence unchanged. The scoped instructions were
  the declared treatment difference, not silently assumed identical prompts.
- **Retained repeats:** the preceding three context-only studies include one
  large loss, one large gain and a transport timeout in the third. Their batch
  total stays unknown. No failed run was removed to manufacture a win.
- **Implementation:** `evals/quality/runner.py` persists pending invocation IDs
  before dispatch and flushes captures before acknowledgment.
  `evals/run_repository.py` validates those receipts, retains study-level
  exposure, requires exact patch bytes, and exposes opt-in task discipline and
  bounded timeout controls. No retry, default promotion, weight update, Jev
  call, answer-refinement step or normal host-profile change was introduced.
- **Regression evidence:** seven newly added checks failed before repair.
  The focused preservation/accounting run passed 154 tests; the subsequent
  runner/transport/CLI group passed 61. The full 1512-test run includes those
  overlapping checks; do not add them together. An intermediate error-message
  mismatch is retained in `measurement-green.txt`, despite that filename.
  Ruff passes on the three changed code/test files; configured mypy passes on
  the two evaluation modules and does not prove untyped bodies.
- **Independent repair review:** both original reproductions now reject/retain
  the correct evidence. Eighteen bounded checks and three timeout probes
  passed, including injected failures at five fsync points. That review used
  simulated filesystem/fsync operations, not physical power-loss testing.

`evidence/combined-request-validation-20261008/validation-receipt.json` records
the stable 106-file inventory, 1512 JUnit testcase nodes and 1531 inclusive
test/subtest count. `CODING_VALIDATION.md` gives the exact reproduction command
and the unchanged qualification limits. G05, G08, G09 and G12 remain open;
this checkpoint does not close the full implementation/release goal.

## October 8 comparator-runtime continuation

No production Python or test files changed after the 1512-test receipt.
An official, digest-pinned Headroom image for the original comparison commit
now passes a real isolated native-import check: all 557 installed Python source
files match the attested archive, and both named Rust-extension exports load.
The container ran as UID/GID 65532 with network none, read-only root, dropped
capabilities and bounded resources, then exited 0 and was removed.

That initial inspection is not a newly reproduced native build, an independently
verified publisher signature or a parity benchmark.
No provider/Jev call or normal host-profile change occurred. See
`PARITY_RUNTIME.md` and
`evidence/runtime-route-check-20261008/runtime-output-003/` for observed runtime
versions, actual isolation configuration, source hashes and limitations.

The later `evidence/headroom-model-readiness-20261008/` continuation loaded
the actual upstream-pinned Kompress checkpoint and the correct separately
frozen ModernBERT tokenizer. Five assets were hash-verified. Default-model
activation and the real `headroom.compress` pipeline then ran with network
none/read-only assets: two eligible tool results changed, two pipeline-phase
neural forwards completed, and both complete originals were recovered.
Protected Read controls and the intermediate incorrect route-marker assertion
remain preserved. The alias uses Headroom's estimator; its counts are not
treated as exact serving usage. AST remains default-disabled and optional
semantic relevance is unqualified.

Independent review confirmed the saved result and found an overly permissive
substring check in the readiness verifier. The future gate now requires
whole-original equality and complete changed-source coverage. Eight additional
**evidence-helper** regressions pass; they are not added to the 1512 plugin-test
count. The stronger offline check revalidates recorded hashes without claiming
an inference or retrieval rerun. This remains a component readiness result,
not primary-model task quality, general savings or parity.

## October 7–8 closeout: mathematics, Jev and actual context reduction

- **Standalone rejected-batch replay repair:** the independent review found
  that direct registry submissions forgot already-reported IDs on rejection.
  The additive `reported_calls` table now commits exposure before validating
  accepted observations. Twenty-two regressions cover rejection, collision
  ordering, restart, malformed submissions, concurrent owners and legacy data.
  The three focused mathematics suites passed **221 tests**. A parent rerun
  of both original reproductions retained all 200 sibling IDs per case, accepted
  no partial observations, blocked replay after reopening, and accepted genuinely
  fresh synthetic controls. Existing mathematical identities/certificates were
  not rewritten. Old lost IDs cannot be reconstructed; all writers must use the
  patched code.
- **Jev response compatibility:** the official structured Score response was
  initially rejected. Ninety-nine client tests now pass, including matching
  object/array rubrics and rejecting changed JSON types. One authorized synthetic
  live request returned HTTP 200 with object legends, recording 160 reference
  learning tokens separately from 362 vendor-reported tokens. The key was not
  printed or stored in a repository file. This is schema/transport evidence,
  not an independently correct primary-task outcome.
- **Truthful repository diagnostic:** missing responses retain known-call
  subtotals and unknown whole-task totals. Missing/duplicate inventory,
  budget exhaustion and read-only write attempts have regressions. Nineteen
  focused diagnostic tests pass; final Ruff checks cover six changed files and
  configured mypy covers the three changed production/evaluation modules.
- **Live result, including the negative aggregate:** the completed replication
  passed 4/4 tasks in each arm but used 47,815 → 87,842 bridge-reported tokens.
  Navigation alone reduced two requests and used 17.0% fewer bridge tokens;
  extra reads in an uncompressed debugging task dominated the total. No overall
  gain, population certificate or promotion is claimed. The earlier timed-out
  run remains partial, not silently discarded.
- **Offline verification:** all 13 attempted task runs across the new partial
  and complete studies were recounted/regraded. Both 37-file source inventories
  matched; initial paired requests matched; original evidence was unchanged.
  `evidence/repository-diagnostic-20261007/offline-verification.json` records the
  boundaries. Intermediate audit-helper errors (a legitimate absent lazy CCR
  database and a missing declared tool-list override) were fixed; their logs
  remain, and no model calls were repeated for that offline repair.
- **Parity analysis:** `PARITY_ANALYSIS.md` provides the token-only current
  capability mapping and exact upstream source links. The October 7 public-source
  refresh preserves the original comparison SHAs while documenting later tips.
  It is not a live head-to-head competitor benchmark.

The outstanding representative/behavioral, competitor-comparison and isolated
Codex Desktop gates below remain open. These concrete repairs and measurements
do not redefine the full goal as complete.

## October 8 comparator/native-runtime preparation

The pinned Ponytail default `full` instruction builder was executed unchanged
in an inspected non-root, read-only, network-none container. Its recursive Git
tree and five relevant blobs matched; no fallback was used. The raw result is
1,274 reference instruction tokens, not a measured task-saving percentage.
The exact container was removed and the public image preserved.

All 2,542 archived Headroom source files matched the pinned archive. Its
release-mode native build could not start successfully because the declared
Maturin wheel download failed TLS at the official Python file host. The
source-declared dependencies and ML assets are not qualified; no reduced or
missing-model comparator was silently substituted.

The new isolated Codex Linux sidecar reuses the existing MCP/mock-provider
verification path. Its offline boundary/correlation tests pass, and the
official pinned CLI archive matches its upstream digest. However, locked
runtime wheel downloads failed from both Docker and the host, so actual native
MCP execution was not reached. Normal TLS validation was preserved, no real
model calls were made, and exact-resource cleanup was verified.

The final full run passed **1,500 tests and 19 subtests**. JUnit contains 1,500
testcase elements and reports 1,519 inclusive test/subtest results; these are
the same run, not counts to add again. `PARITY_RUNTIME.md` records source pins,
commands, missing runtime gates and the dependency prerequisite. A successful
Linux CLI run would still not qualify native Windows or Desktop.

The runtime is Windows CPython 3.12, MCP 1.27.2 and tiktoken 0.14.0, with pinned
Python/Rust tree-sitter grammars. `pip check` passed. Exact runtime closure pins
ship separately; other platforms and mutated runtimes require fresh validation.

## Native hosts: transport, not reasoning quality

| Host/version | Narrow result |
| --- | --- |
| Claude Code 2.1.289 | Fresh 11-cell native envelope matrix passed, including accepted Read/Grep/Bash/PowerShell-via-Bash/MCP text changes and exact bypass controls. Actual temporary user-settings install/uninstall passed. Earlier native MCP list/call/retrieve also passed. |
| Copilot CLI 1.0.88-2 | Native MCP stats/retrieval passed under isolated offline BYOK with a loopback mock provider. |
| Codex CLI 0.147.0 | Native MCP transport passed, but strict user-skill isolation did not: this build discovered the OS-user catalog despite redirected homes. Catalog text was redacted from saved evidence. |
| Codex Desktop | Untested. The real desktop profile was not changed. CLI/configuration support is not Desktop runtime evidence. |

The added evidence is version- and fixture-scoped; it is not an all-version
acceptance claim. PowerShell is exercised through Claude's Bash tool, not a
separate PowerShell hook API. Unknown shapes, errors and mixed media pass through.
The native MCP bare-array repair and full provider-result checks are described
in `NATIVE_ENVELOPES.md`.

The native harness used synthetic actions and a loopback provider, copied no
real authentication and cleaned its temporary homes/processes. Environment
redirection is not an OS sandbox. No unsupported global skill-disable setting
was used to manufacture a passing Codex isolation result.

## Mathematical review and adversarial repairs

Independent review checked the bounded-difference constants, fixed/anytime
spending, persistent reservations, immutable comparisons, token-cap rejection
and known holdout replay exclusions. The proof remains conditional on truthful
capture, independent tasks, oracle fidelity, a valid whole-task cap and a stable
regime; source review cannot establish those external assumptions.

The review also drove concrete regression repairs:

- No “lossless” result without actual equality-based retrieval.
- No complete all-in learning metric from a merely present unfinished run.
- Explicit baseline-validation traces and pre-reserved call allowances.
- Durable call ownership across learning runs; rejected evidence cannot be
  sealed into apparently complete totals.
- Sanitized out-of-band storage, internal-transform and loader failure reasons.

The final mixed rejected-batch replay exclusion was independently approved:
18 focused regressions passed, both collision orders stayed blocked after
restart, rejected runs remained unsealable, and fresh positive controls still
certified and promoted. Reviewed source SHA-256:
`ceb1e25e3f4a8ab3546f94d278f2c984a0250fe36e01d8295bf4a54eb2100ad5`.
This approval covers the bounded accounting/freshness repair, not deployment
or universal task-quality safety.

## Live screening receipt

The actual Jev screening call contributed **853 input + 332 output reference
tokens**. The independent synthetic responder contributed 256 fixture calls.
Combined learning inventory: 106481 reference tokens, with the baseline's
explicit zero-call check and all three learning-run inventories sealed.

The 128-pair constructed fixture certificate had:

```text
quality-difference lower bound:       0.7442358338299995
normalized-token-difference upper:   -0.19252379769718697
```

The saved certificate permitted the demonstrated policy update from
`min_tool_chars=1024` to `896`; reopening and registry-only promotion produced
champion version 2. This deliberately favorable toy workload is **not real
language-model quality evidence**. Its baseline has no demonstrated positive
success probability, so the conditional tokens-per-success ratio theorem must
not be quoted as an empirical ratio improvement for this fixture.

The learning receipt covers only this declared screening/fixture run. It does
not include this development conversation or unobserved engineering-agent
tokens. No deployment success ratio or project-wide all-in benefit is claimed.
The separate API smoke is a separate validation run, not silently folded into
that ledger. User credentials were process-local and not saved in source/config.

## Real-model exploratory evidence

`evidence/jev-quality-20261004/pilot-frozen-v2/` contains the source-frozen
real-model study: eight non-IID synthetic-workspace tasks and two arms. Both
arms passed 8/8 after the recorded arm-blinded mathematical review. Seven cases
per arm used deterministic/executable graders; the two harmonic-sum proofs
were reviewed by the principal assistant, not a human or formal proof checker.

The offline audit recomputes 104775 baseline versus 101117 combined full-body
reference tokens (**3.49% lower**). Separate bridge-reported totals are 45699
versus 40776 (**10.77% lower**); these were not the predeclared primary metric
and are not independently authenticated upstream counters. One navigation case
dominates; six cases consumed more reported tokens. Calls increased 25 → 27
and recorded wall time 74.234s → 88.343s. No statistical certificate or promotion
was produced. See `OBJECTIVE_SAVINGS.md` for the runnable checker and caveats.

The WSL execution boundary was independently reviewed with 137 focused
sandbox/oracle tests and six canaries. The exact reviewed bundle digest is
`e7d033a9922d7bf1f6c3b3942accd4fea93fa539118133780b2d3cb53db5401e`.
This is a bounded user/mount/network/PID-namespace and syscall/resource-limit
check, not general sandbox certification or an aggregate WSL/kernel memory cap.

The earlier invalid study and preflight adjudications remain saved. The
intermediate full-suite receipt `tests-final.txt/xml` in this new evidence root
contains **1023 passes and one failure**, a startup-readiness race in the Windows
private-job cleanup test. Its repair retains the real timeout and exact process
handle proof; it does not weaken cleanup assertions. Subsequent current-suite
receipts are separate, not overwrites of that failure.

The first objective continuation full run then had **1076 passes and one
failure** (`tests-objective-final.txt/xml`): the large-AST test incorrectly
required the memory limit to trigger before the concurrently enforced deadline.
A direct probe recorded a trusted preflight timeout, no candidate execution,
zero capabilities, the unchanged 256 MiB/3-second limits, authenticated reaping
and scoped cleanup. The test now accepts either documented bounded termination,
but rejects unexplained signals, missing receipts, execution or failed cleanup.
Separate injected memory-fault and stalled-validator cases exercise both paths.
Six focused tests passed, followed by the clean **1079-test full rerun**.
No production sandbox code or resource limit changed for this repair.

Independent savings-audit review approved source SHA-256
`98f4dd1be152f0668b3c92b6a919a012301dead3958b0b221dae0c19176ce214`.
Its final review includes 20 focused tests and 12 additional controls; these
overlap the integrated suite and are not added to its test count. The reviewed
pilot's evidence digest remains
`673749b407bac18d3ae89af0b25813abc30c6ba98d2a82f8d79a47d15a839bd3`.

## Parallel paper research

The arXiv `2608.05643v1` applicability research and pinned associated-code audit
are complete in the local `docs/research/2026-10-05-paper-2608.05643/` dossier.
Its integrity check verified 99 source/derivative hashes, 56 links, 14 paper
anchors and 21 pinned source links. These are artifact/link counts, not 99
independent publications or a reproduction of the experiments.

Black-box refinement is a candidate policy, not demonstrated token savings.
The paper and later associated code differ in schedules, reward-model use and
accounting. No cross-provider experiment, implementation, weight update, host
configuration change or gate relaxation was performed in that research lane.

## Subsequent refinement implementation and live experiments

The separate exploratory implementation and experiments are now complete;
see `REFINEMENT_EXPERIMENT.md` and `REFINEMENT_RESULTS.md`. This supersedes
"not implemented/tested" for the small refinement policy, not the research
lane's historical scope or the outstanding representative qualification gates.

- Native Responses and Messages adapters, explicit requested/reported model
  mappings, bounded stateless policies, exact seeded task oracles, frozen
  captures and an offline checker are implemented without changing the old
  quality adapter or production optimizer.
- Eight-task GPT comparison: one-shot **8/8**, 5909 bridge-reported tokens;
  four-stage refinement **7/8**, 23785 tokens. One correct initial answer
  became wrong. No policy promotion is justified by this result.
- Four different fresh mixed-provider tasks: GPT one-shot **3/4**, Claude
  one-shot **2/4**, GPT with Claude critique **2/4**. Output-limit failures
  remain failures. These are policy outcomes under declared bounds, not
  universal model rankings or cross-provider compute equivalence.
- Across three frozen compatibility/experiment phases: **99 attempts** and
  **1067.188 execution seconds**, including readiness; **563651 full-body
  reference tokens**. Complete native usage across failed probes is unknown.
  No monetary objective, weight change, live-profile change or default-policy
  promotion occurred. Jev was off to isolate the refinement effect.
- All three offline audits passed and reproduced exactly without network
  calls; 35 frozen source-file hashes across the studies matched.
- Ruff passes on the new implementation/tests; configured mypy passes on five
  implementation files. The current disjoint plugin/host suites pass
  **1332 + 40 = 1372** tests.

The initial current plugin-suite attempt had 1326 passes and six failures in
test-only capture-rewriting helpers: the helpers passed the new `api` metadata
to the `Reply` constructor. Filtering by actual dataclass fields repaired the
fixtures without weakening audit assertions or modifying captured results.
Six focused regressions passed, followed by the clean 1332-test rerun and the
40-test host suite. The initial failed receipt is retained as `full-tests.txt/xml`;
it is not overwritten by the passing `full-tests-final.txt/xml`.

The optimizer remains at the independently reviewed SHA-256
`ceb1e25e3f4a8ab3546f94d278f2c984a0250fe36e01d8295bf4a54eb2100ad5`.
Representative task/behavioral qualification and isolated Desktop acceptance
remain open; these narrow experiments do not establish production parity,
net project-wide learning savings, or perpetual improvement.

## Reproduction and remaining release gates

Raw local receipts, including `pytest-final.txt`/`pytest-final.xml`, are in
`evidence/jev-implementation-20261004/`, intentionally
ignored by the repository's existing packaging policy. Runnable evaluation
scripts ship under `evals/`, and the exact definitions/proof ship in
`docs/TOKEN_EFFICIENCY.md`.

The unclosed gates are representative independently graded real-model task
evaluation and behavioral qualification beyond the bounded challenges, strict Codex isolation, Desktop
runtime validation, and native versions/protocols outside the named matrix. Follow
`EVALUATION_PROTOCOL.md`; do not relax the strict quality gate merely because
equal-quality samples remain inconclusive.

No model weights changed. No monetary objective, real host-profile installation,
commit, push or production deployment is part of this checkpoint.

## Native-envelope closeout

The fresh `final-matrix/` run passes **11/11** cells. It uses one checked source
inventory, the recorded native executable, only temporary configurations and
predetermined fixture actions. `final-install-lifecycle/` also passes: real
user-source settings supply the tokenizer with no ambient child path; the
installed hook changes the complete expected native result; uninstall restores
it while preserving every unrelated configuration field across both operations.
Unrelated hook activity and temporary cleanup are verified.

Initial missed MCP overrides, verifier false-positive probes and the early
lifecycle comparison failure remain in the evidence root. Independent review
closed all findings; 68 focused tests passed before the clean 1121-test full
run. These counts overlap and must not be added together. The production
adapter SHA-256 is
`91aa939bcb1b3dd211823e4d291b2834c94c0473b951ed41e3ebbb83f26d0047`.

Current Windows availability evidence still does not establish an accessible,
proven disposable Windows environment. Sandbox executables were not found;
feature-state and Hyper-V VM queries requiring privileges remain unknown.
Nothing here closes the Codex Desktop/user-skill isolation or representative
real-model comparison gates.
