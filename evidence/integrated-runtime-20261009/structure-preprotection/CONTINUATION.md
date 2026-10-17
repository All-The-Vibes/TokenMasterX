# Structural preprotection checkpoint — October 9, 2026

Full R0–R6 goal remains active and unfinished. This continuation completed the
prior full regression and implemented a real pre-compression protection path,
not merely another veto or a rerun of the same model workload.

## Completed previous regression

Exec session `59538` is terminal, exit 0:
**4,676 passed + 19 subtests, three skips, one existing Pydantic warning**.
All 206 snapshotted Python files stayed unchanged. Its evidence is in
`../post-study-guards/full-regression-001/`. Do not restart it.
This is the prior revision, not a full-suite claim for the new code below.

## New implementation

Explicit manual RuntimePolicy strategy:
`headroom_strategy="native-documents-structure-tags-v1"`.
Requires `headroom_structure_guard="document-structure-v1"` and complete
original-input nonexpansion. Old policy IDs/defaults and true-off neighbor
catalog remain unchanged; no automatic promotion/enablement.

- `document_structure.py` now exports exact immutable code-point offsets and
  UTF-8 slice hashes from the **same parser**, with `None` for ambiguity.
  The existing comparison still compares block text, not shifted offsets.
- Parent runtime passes pristine source plus digest-bound descriptors only;
  ambiguous syntax or >256 total spans bypasses before worker startup.
- `headroom.py` uses separate `compress_documents_preprotected` RPC and verifies
  closed span/strategy/hash/typed-index/control echoes.
- Standalone `headroom_worker.py` inserts exact task-owned custom tags, checks
  actual public protect/restore roundtrip, runs the genuine public pipeline,
  rejects missing/duplicate/reordered/changed frames, and strips only its own
  validated delimiters. Native tool names/calls and noneligible bytes stay intact.
- New mode intentionally uses **public preparation validation reads**, with
  access/feedback/TOIN effects explicitly bound and counted separately.
  Only exact pristine source fragments with no internal framing can be retained.
  Immutable handle bindings are never rekeyed/overwritten by the adapter.
  Actual later handler output must still match and is returned unchanged.
- Annotation removal is not credited as original-wire savings; parent fence,
  structure, exact Root and final complete-wire guards all remain.

No private vendor backend access, Root substitution, model weights, dependency,
normal profile, statistical gate or allocation change.

## Tests and actual public API check

- Span + existing grammar slice: 136 passed.
- Initial parent/legacy slice: 172 passed.
- Combined parent/worker/parser/legacy slice: **577 passed** (overlapping).
- Parent typed-index echoes were repaired after five failing-before bool/float
  cases; valid old behavior retained.
- Worker owner reported 280 pure/mocked/dispatcher passes before later review
  findings. These are not genuine neural/vendor efficacy claims.

`public_api_probe.py` / `run_public_api_probe.py` are non-production, frozen
one-shot test drivers. Actual pinned public tag/pipeline/store/handler APIs run
inside the existing network-none/read-only/nonroot image, with explicitly
controlled detector and compressor doubles.

`public-api-runs/`:
- `probe-001`: failed before image process start because driver Cmd/OpenStdin did
  not match the production boundary. Container stayed created, was removed.
- `probe-002`: actual public APIs ran; parent fence guard correctly rejected
  the unrealistic double's rewrite of five-character code. The double was then
  given the pinned compressor's 64-word passthrough floor. Failure retained.
- **`probe-003`: PASS**. Real public API mixed case changes prose, preserves
  table/list/fences, delivers genuine handler bytes, and rejects an overwritten
  handle. Pure annotated-original case reverts and retains raw contamination
  privately. Two local validation reads, zero network attempts, zero real
  primary-model calls; controlled compressor/detector, not learned efficacy.
  Owned cleanup completed. Plan:
  `950f56340ca7a4e209643cba411841748f8c7f57f7bba6d6df3ded587a72910c`.

This public check used worker SHA
`f9b0c4c073422e2f646199fd879e995b4d6fa6f1f268201f5bc9c5e6b3efca89`.
Later fixes require a fresh frozen public check; do not relabel this old pin.
No actual native preprotected qualification or new live-model task has run.

## Independent review findings and current work

`PARENT_REVIEW.md/.json`: parent typed-echo P1 closed.
`WORKER_REVIEW.md/.json`: initially **FAIL** with W1/W2.

### W2 — parent repaired, review closure pending

Eager component startup left worker strategy unselected, so early recovery could
take the old unvalidated route. `HeadroomContainer.retrieve` now rejects new-mode
recovery before **any RPC** unless the cached verified prepare manifest is the
new strategy. Invalid/absent/old manifests do not grant authority.

Five proper failing-before cases include actual RuntimeSession eager readiness;
`early-recovery-red-002.txt` is the clean reproduction (the first red attempt had
one unrelated fake-resource fixture issue). **49 parent/old adapter tests pass**
after the fix, including valid post-prepare recovery and old-mode compatibility.

### W1 and additional effective-protection check — worker owner working

Worker agent `01a121fb-ff4b-7d30-aa65-b32cd95060ca` is fixing:
- KeyboardInterrupt/SystemExit after a validation read currently bypass outer
  Exception-only receipt emission. Best-effort emit known inventories, then
  rethrow the original non-Exception; never reread/retry or let a later emit
  failure mask it. Hard kill/closed pipe remains unknown.
- Parent's `effective-protection-red.json` proves an additional hard-protected
  E message can be changed by the vendor without an error; final original is
  preserved, but the added protection check was missing. Compare every
  `effective_protect` index, not only the original non-E set.

Scope for that agent: worker and `test_headroom_preprotection_worker.py` only.
Collect its final changes/tests before further execution.

Verifier `01a122ca-1ba4-7010-aa40-91cc0ec1fc20` (Ptolemy) has been asked to wait for
these fixes, then close W1/W2/effective-protect and review the full composition.
No production edits by the verifier.

### Native qualifier authoring — no execution

Agent `01a12208-eb65-7a30-a69d-123dd1f1a3ba` is authoring **only**
`structure-preprotection/qualifier/`, copied/adapted from the retained ranged
qualifier. It must preserve the same pinned public documents, ranges, prompt
and max-eight canned schedule (five overview, three exact/status), with the
new explicit policy and all existing failure/interruption/cleanup checks.
It adds span/recovery/feedback/inventory checks and must not edit the old
qualifier/runs or launch prepare/native/Docker/model calls.

## Next actions

1. Collect worker fixes and qualifier authoring; independently close all blockers.
2. Fresh focused/static regression for stable current sources.
3. Fresh frozen actual public-API probe on the repaired worker (old probe retained).
4. Review, freshly install/freeze and run the new **canned native** qualification.
   Real Headroom local inference is separate from zero primary-model inference.
   Require accepted smaller complete wire and actual recovery; no rescue padding,
   changed ranges, selected retries or weakened guards if it does not reduce.
5. Audit exact outputs and update the full-goal checkpoint. Any real-model
   efficacy study remains a separate decision/freeze; none is authorized by a
   green unit test or this mechanism-only check.

The latest real-model outcome remains baseline 2/2 versus candidate 1/2, from
`native-ranged-results/live-runs/live-001/`. Its failed cap-limited task and all
consumed tokens remain unchanged. No useful whole-task saving has been proven.

Native learning's initial-request comparability and exhausted old registries,
native write/debug, feasible independent evaluation, all-in accounting and
release qualification remain required work. Do not complete or narrow the goal.
