# Independent parent review — structure preprotection

## Verdict
**PARTIAL — request changes to parent response-echo validation.** One concrete typed-index receipt defect remains. Other tested parent boundaries pass.

**Worker and recovery NOT approved.** Feynman's in-progress annotation/pipeline/store/handler lane and actual-vendor qualification are outside this review. Backend/API-shaped doubles are not vendor proof. No new real-model study or retroactive change to old evidence.

Completed: **2026-10-10T01:36:35.980897+00:00**. **Review writes finished.**

## Finding P1 · MEDIUM
**Location:** `brainspace/headroom.py:393-394`.

Request indices are strictly typed, but response `eligible_indices` and `protected_indices` are checked with ordinary Python list equality. Five malformed echoes were accepted without poisoning the adapter:

| Expected | Accepted malformed echo |
|---|---|
| eligible `[2]` | `[2.0]` |
| protected `[0,1,3,4]` | `[false,1,3,4]` |
| protected `[0,1,3,4]` | `[0,true,3,4]` |
| protected `[0,1,3,4]` | `[0,1.0,3,4]` |
| eligible `[1]` in a valid assistant/tool-starting history | `[true]` |

Python equates bool/int/float values here. **This proves malformed receipt acceptance, not a final protected-content bypass:** RuntimeSession independently derives eligibility from SourceInfo and reconstructs the candidate from pristine originals.

**Repair:** for the explicit new strategy, require response arrays to be lists with strict integer elements and exact order/values, or compare canonical typed JSON. Add bool/float mutations for both E and its complement. Preserve old strategy serialization/catalog compatibility. No production fix was made by this verifier.

## Evidence

### Contract / strict public validation decision
Read `IMPLEMENTATION_CONTRACT.md`, SHA `046e038dd9c7204daaeb32c407c6c8614766def323a0db0d7b683a4b283bb835`. Its public `CompressionStore.retrieve()` preparation validation intentionally changes upstream access/feedback state. That work must be recorded separately, not disguised as native recovery or free observation.

Every emitted handle must resolve to an exact nonempty UTF-8 contiguous slice of its bound pristine observed result. Contaminated/ambiguous/missing/over-bound fragments reject the message; do not decode annotated originals, rekey vendor handles, or return a substitute Root under a vendor hash. Genuine later recovery must validate and return the raw real-handler fragment unchanged.

These **worker/recovery obligations are not approved by this parent review**. Parent routing/final guards do not replace their proof.

### Focused fresh tests
```text
........................................................................ [ 29%]
........................................................................ [ 58%]
........................................................................ [ 87%]
................................                                         [100%]
248 passed in 6.88s
```

**248 passed in6.88s.** Seven files: old structural parser, offset export, new parent wiring, old document adapter/policy/runtime, structural runtime guards. Existing Python `-B`, no bytecode/cacheprovider/plugin autoload, verified local tokenizer; explicit backend/transport doubles, no HTTP peer or model/Docker/native call.

A concurrent edit changed only the test helper `wire = lambda ...` to an equivalent `def wire(...): return ...`. Reversing those exact bytes recreates its original SHA; no parent production file changed. Fresh rerun of the current parent file: **21 passed in2.86s**. Details/hashes are retained in JSON. Parent-reported wider regression was not broadly re-audited.

### Parser / offsets — PASS
`document_structure.py:99-222` owns a single `_structure_ranges` parser; both acceptance `_structures` and offset export invoke it. Export returns immutable end-exclusive Python code-point ranges and SHA-256 of exact UTF-8 slices. No worker-side Markdown parser was added or imported by this parent API.

Independent LF/CRLF, Unicode-prefix, duplicate-table/list cases verify exact positions, ordered digests and slice-concatenation identity. Tests cover EOF/trailing blanks, fenced structures, nested/unterminated/ambiguous syntax, invalid Unicode and oversized input. **None** means unsupported; **()** means supported with no recognized structures. Fences remain separately protected; this is not broad Markdown semantics or query relevance.

### Explicit policy / old default identities — PASS
`native-documents-structure-tags-v1` requires typed RuntimePolicy, `document-structure-v1` and whole-original nonexpansion. Invalid combinations reject before runtime output construction. Resource resolution forwards this strategy without discovery/warmup.

Old true-off ID remains `runtime-policy-v1:579bf9ab6972b791692d7e41fd7a33f2842c48ad830c377d41be357bf4a9d9b1`; six off neighbors remain, none auto-selecting the new mode. Catalog remains `runtime-policy-neighbors-v4`. Existing policy serialization/neighbor tests pass; exact IDs are in JSON. Selection remains manual and default-off.

### Pristine SourceInfo / before-start skips — PASS
`runtime.py:547-587` authenticates source call/path/result bytes before using the existing parser. Only older successful bound document results are considered, with existing intent/status/exact/newest/frozen-prefix protections.

Independent RuntimeSession probes with explicit backend doubles:

- Text changed after SourceInfo binding: **zero starts/RPCs**, original wire retained.
- Unsupported nested list/fence: **zero starts/RPCs**, original retained.
- Two eligible results with129 spans each: **258 total**, zero starts/RPCs; no per-message budget escape.
- Exactly256 spans are passed without truncation; unchanged double response retains original.
- Accepted case offers pristine messages/query plus separate digest-bound offsets; caller input and tool/call identities unchanged.

Before-start claims apply to **ordinary lazy invoke**. Existing explicit `prepare_components()` readiness can intentionally start components independently; no claim it is a free task-specific skip.

### Request frames / indices / hashes — PASS
Parent reuses only pure `preprotection_indices` mechanical validation. Eleven descriptor attacks fail before RPC: boolean index, original/span digest mismatch, boolean/negative offset, overlap/duplication/reversed sequence, extra entry/span fields, unknown kind and missing descriptor.

Additional probes reject oversized4,194,304-byte frames, boolean request eligibility/prefix/recent controls and Unicode offset/hash mismatch, all with zero RPCs. Bounds, exact line boundaries, order/nonoverlap and original/slice digests are checked. The256-total-span check is before lazy startup; full serialized-frame bound is before RPC, **not asserted before all startup work**.

### Response echoes / lifetime config — PASS except P1
Wrong span contract/hash, wrong E values, extra control keys, bool substitutions for prefix/recent values reject and latch failure. A changed effective manifest with a recomputed correct digest also rejects on the second call because its first accepted canonical form is task-pinned.

Control-dict equality is typed JSON. Returned E/complement array equality is the incomplete typed boundary in P1.

### Final wire / Root / fences / structure — PASS with doubles
Descriptors and span-contract controls stay in internal RPC kwargs, not model request fields. Extra response diagnostics are not forwarded: adapter output is exactly `model` + `messages`. Prepared requests contain no `message_spans`/`span_contract` metadata; inputs remain unchanged.

The accepted shortened view has a compact Root whose stored original equals the **pristine observed tool text**, not annotated text. Complete final input tokens are lower than the complete unaugmented original. System and newest results stay unchanged. Lost fence content, changed table/list cells and full-wire expansion revert to the original. Frozen strategy assignment fails; simulated resource drift fails before worker startup/primary send.

This proves the parent does not introduce generated frames and retains old final guards. It **does not prove** the in-progress worker always removes its own frames or validates raw vendor recovery; those remain separate.

## Reproduce P1 (no network/vendor/container)
With the source skill and its `tests` directory on `sys.path`, use existing Python `-B`:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from test_headroom_preprotection_parent import MODE, adapter_request, adapter_response, descriptors
from test_headroom_document_adapter import adapter
with TemporaryDirectory(prefix="parent-echo-repro-") as tmp:
    chat = adapter_request()
    spans = descriptors(chat, [2])
    item = adapter(Path(tmp), strategy=MODE)  # __new__, no container startup
    reply = adapter_response(chat, spans)
    reply["protected_indices"] = [False, 1, 3, 4]
    item.rpc = lambda *args, **kwargs: reply  # explicit API-shaped double
    assert item.prepare(chat, eligible_indices=[2], frozen_message_count=1,
                        message_spans=spans) == chat  # P1: malformed echo accepted
    assert item.failed is False
```

JSON contains all cases, test output, source/dependency hashes and runtime observations.

## Preservation / stop condition
All **five parent production files** and the span test file are byte-unchanged. The sole parent test-helper lambda-to-def edit is explicitly reconciled and freshly tested. The reused pure-worker validator dependency ASTs remained stable; full worker source is owned by the other lane and is not approved or pinned by this review.

Only `PARENT_REVIEW.md/.json` were written durably; new temporary fixtures were isolated/closed. No production edit, provider/Jev/native/Docker/network/dependency action, old registry operation, old audit write, reset or promotion occurred. Stop with P1 returned to the parent; do not silently absorb worker/recovery work.

## Gaps
- P1 typed index echoes need repair/retest.
- Actual worker/public pipeline/store/handler and preparation-validation feedback accounting remain unqualified here.
- No actual vendor or real-model efficacy run performed or approved.

## Risks
Recognized structure preservation does not establish surrounding-prose semantics, model accuracy or fewer follow-up reads. Preparation validation changes vendor state and costs work; smaller final input is not all-in savings. Independent worker evidence is still required.


---
## Parent echo closure — latest parent verdict PASS

2026-10-10T01:45:52.457370+00:00. P1 is closed: `headroom.py:393-398` now requires actual lists with strict integer elements before comparing both eligibility and protected-index arrays. No numeric normalization was introduced. All five original bool/float counterexamples were independently replayed against fresh API-shaped doubles and now raise `headroom_document_manifest_mismatch` with `failed=true`.

Fresh combined offline suite: **320 passed in6.03s**, including the new parent regressions, worker doubles, old document worker/adapter and activity-ledger tests. Parent behavior is clear under this scope. Earlier counterexamples remain historical evidence. **This closure does not approve the whole worker/recovery composition**; see separate WORKER_REVIEW. No production or old evidence/registry changes by the reviewer. Parent closure writes finished.


### Whole-composition follow-up — not covered by P1 closure
2026-10-10T02:00:07.783997+00:00: P1 typed-index echo remains **closed/PASS**. Separate WORKER_REVIEW is **FAIL**: W2 shows eager-start recovery before first compression reaches the legacy unvalidated worker path and parent forwards its raw content; W1 loses current validation inventory on non-Exception exits. Do not interpret parent echo closure as whole-recovery approval. See WORKER_REVIEW for counterexamples and bounded fixes. No production edits by reviewer.
