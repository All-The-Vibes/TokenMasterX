# Independent whole-worker / recovery / preprotection review

## Verdict
**FAIL — request changes before approving the whole composition.** Parent typed-index echo P1 is closed, but two separate worker/composition findings remain:

1. **W2 · HIGH:** eager readiness permits pre-handshake recovery through the legacy unvalidated handler path.
2. **W1 · MEDIUM:** a non-Exception interruption after a public validation read leaves its known inventory only in memory, with no emitted worker receipt.

Completed: **2026-10-10T02:00:07.783997+00:00**. **Report writes finished.** No production edits, old evidence/registry changes, actual provider/Jev/model/native/Docker/network execution. Source and tests match the supplied final pins throughout review.

## Scope and pins
Reviewed against `IMPLEMENTATION_CONTRACT.md` (SHA `046e038dd9c7204daaeb32c407c6c8614766def323a0db0d7b683a4b283bb835`): mechanical span admission, annotation/decoding, public preparation validation with feedback, raw fragment association/recovery, bounded state, dispatcher/failure inventory, parent final-wire integration and old-strategy separation.

- Worker SHA: `f9b0c4c073422e2f646199fd879e995b4d6fa6f1f268201f5bc9c5e6b3efca89`.
- Worker test SHA: `2f710518e05b024d66320801bba4784c19a07ea5266e4c32a277e904983d694e`.
- All **eight** scoped source/test hashes remained unchanged; full maps in JSON.
- Parent closure is appended to `PARENT_REVIEW.md/.json`: explicit list + strict integer response indices reject all five original counterexamples. This closes **P1 only**, not W2's different retrieval ordering boundary.

## Findings

### W2 · HIGH · New-mode early recovery falls through to legacy validation
**Locations:** `headroom.py:421-429`; `headroom_worker.py:1085-1086,1175-1186`; `runtime.py:371,897`.

Parent strategy is selected as `native-documents-structure-tags-v1` at construction. The worker initializes `strategy=None` and does not bind it until the first compression RPC. Its retrieve dispatch is:

- guarded `documents.recover(...)` only when strategy already equals the new strategy;
- otherwise direct legacy `handler._execute_retrieval(...)`.

Parent `HeadroomContainer.retrieve` verifies result call/name but does not require a new-mode handshake or prior validated binding. `RuntimeSession.prepare_components()` can eagerly start the worker before any eligible compression; `recover()` then sees an active Headroom component and reaches this path.

**Independent reproduction:** actual RuntimeSession `prepare_components` -> `recover`, actual parent retrieve method and actual worker dispatcher body, with privileged bootstrap removed and explicit in-memory vendor/resource/transport doubles. Parent declared the new mode; there were **zero preceding compression/validation/primary requests**. Early H retrieval entered the public handler **once** and public store **once**. A seeded unvalidated entry containing `<tm-structure-unvalidated>...` was returned unchanged as the tool content.

This is not a claim that a real fresh worker necessarily contains that entry. The seeded double demonstrates the unchecked return path; the new-mode promise to refuse unvalidated H **before any handler/read** is already violated independently of actual content availability. After a compression handshake, the existing guarded recovery correctly rejects unknown handles; tests cover that narrower ordering only.

**Required repair:** bind the selected strategy before any recovery can dispatch, or explicitly fail closed in the parent new-mode retrieval path until its validated new-mode prepare handshake exists. Preserve old strategy behavior. Add eager-readiness/first-RPC tests for unknown, absent and contaminated seeded entries, requiring zero handler/public-read calls for unvalidated handles. Do not make a warmup read or substitute full Root content to paper over the missing validation.

### W1 · MEDIUM · Non-Exception validation interruption is not durably emitted
**Locations:** `headroom_worker.py:643-685,1229-1242`.

`validate()` correctly appends an event before entering public retrieve. It catches BaseException, marks outcome `exception`, then reraises non-Exception exits. The dispatcher catches only **Exception**, so KeyboardInterrupt/SystemExit bypass its receipt-emission path.

Controlled in-memory probes executed the actual dispatcher loop with no privileged bootstrap or real signal:

| Store failure | Public reads entered | In-memory events | Emitted response/validation receipts |
|---|---:|---:|---:|
| RuntimeError | 1 | 1, exception | 1, counted fallback |
| KeyboardInterrupt | 1 | 1, exception | **0**; propagates |
| SystemExit | 1 | 1, exception | **0**; propagates |

The parent can label the RPC incomplete, but the known read count/outcome is not delivered from the worker. This falls short of the requested all-attempt inventory across interruptions; it is not a content leak or a proof that unknown compute is zero.

**Required repair:** best-effort emit current preparation/ONNX inventories at the outer termination boundary for non-Exception exits, then preserve cancellation/exit semantics. Never retry the read. Add controlled KeyboardInterrupt/SystemExit regressions. Hard kill/closed-pipe cases still cannot guarantee a receipt and must remain explicitly unknown/incomplete.

## Positive evidence

### Fresh offline suite
```text
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 67%]
........................................................................ [ 90%]
................................                                         [100%]
320 passed in 6.03s
```

**320 passed in6.03s.** Included new parent/worker tests, old document worker/adapter, activity ledger, offset and structural runtime tests. Existing Python `-B`, disabled bytecode/cacheprovider/plugin autoload, verified local reference vocabulary. Vendor pipeline/tag/store/handler modules are explicit doubles; dispatcher tests execute real loop code minus privileged startup. No real public API or model inference was run.

### Parent closure — PASS
Freshly replayed all five previously accepted eligible/protected bool/float response arrays; now every case raises `headroom_document_manifest_mismatch` and latches `failed=true`. No weaker normalization. P1's historical failure remains in the parent report, followed by closure evidence.

### Composition uses public APIs, not a private backend
Source inspection of the pinned local Headroom files confirms:

- `protect_tags`/`restore_tags` expose the expected string + placeholder/original-pair API. The pinned shim is Rust-backed; **it was read, not executed here**.
- Public `CompressionStore.retrieve` intentionally updates access/backend/feedback/TOIN state. The adapter calls this public API and labels those side effects; it does not directly read/write vendor `_backend`, replace stores, reset feedback or rekey entries.
- The existing CCR handler returns `hash`, `original_content`, `original_item_count`. Recovery parses only to validate, then returns the **exact original content string**, not reserialized JSON.

AST checks find no product/tests/evals relative imports or direct private vendor backend access in the standalone worker. The sanctioned existing `_execute_retrieval` handler entry is distinct from private backend manipulation.

### Exact structural framing — PASS in tested ordinary flow
Parent retains grammar/provenance authority; worker uses only mechanical descriptors and exact UTF-8 hashes/line boundaries. Annotation changes eligible tool text only, using registered task occurrence frames. Collision checks reject reserved families, the task nonce and preexisting handles rather than treating natural source literals as authority.

The public-tag preflight checks exact protect/restore roundtrip and that each generated frame is actually hidden once. Decoding requires every registered frame exactly once and in order with its original interior. Missing, duplicated, reordered, changed, partial or unknown frames revert the message; there is no lost-span append, whitespace repair, synthetic prose or forced compressor route. Protected/system messages and original query remain intact. True public pipeline stage order is preserved by composition source; genuine behavior still needs the parent's public-API probe.

### Immutable handle/raw/source association — PASS after handshake
Only a nonempty UTF-8 raw fragment with matching H, no internal framing, and a **unique contiguous occurrence** in pristine observed source can be retained. H maps once to immutable raw bytes + source binding; conflicts never replace it.

Independent cross-RPC probes changed **model, source path, result metadata, and original source text** while retaining H. Each proposal performed the new public validation read, detected `binding_conflict`, reverted its source message and left the prior mapping unchanged. A later genuine recovery of the old raw value remained valid. Provided tests also cover changed raw data, changed tool-call ID, ambiguity, missing entries, malformed raw values and contaminated pure-text routes.

### Recovery call count / byte equality — PASS after handshake, except W2 ordering
Known validated H calls the real handler entry exactly once, with **no wrapper pre-read**. A Unicode raw fragment was returned with its handler JSON string byte-for-byte unchanged; the only additional public read belonged to that handler. Later changed/contaminated vendor raw content produced the constant clean refusal and did not replace the retained binding. Unknown handles after handshake call neither handler nor store. Malformed/extra/duplicate-key/error payloads and raw changes do not leak or trigger a substitute Root.

The early unselected-strategy exception is W2 and blocks a universal recovery claim.

### Bounds and side-effect accounting — PASS for ordinary exceptions
Owned bounds:256 spans/RPC,128 handles,8MiB retained exact UTF-8 fragment bytes,2048 frame identities,1024 validation attempts,4MiB frames/fragments, bounded worker request loop. Saturation reverts new proposals/validation without evicting earlier bindings. Independent handle saturation caused zero additional public reads and retained old H authority.

Events are appended **before** side-effecting preparation reads and carry RPC/message/source binding, handle, raw digest/length when available, outcome and elapsed time. IDs are `preparation-validation-*`, never manufactured native tool-call IDs. Counts are cumulative, not additive snapshots; access/feedback/telemetry/TOIN effects and unknown publication are explicitly labeled.

A second-handle RuntimeError after a first validation retained both events (`validated_candidate`, `exception`), both entered reads and the earlier binding while reverting the message. Exception text was not exposed. Ordinary final-scan errors and oversized response tests preserve validation receipts. Non-Exception termination gap is W1.

Late `finish` reads preserve the old post-task raw audit semantics. New-mode raw audit is explicitly labeled as possibly annotated and **not native delivery**, not a complete-store census. No early audit, private peek or content decoding is substituted for actual validation/recovery.

### Validated candidate is not publication — PASS end-to-end with doubles
Independent composition connected actual RuntimeSession -> actual parent prepare/echo validator -> actual DocumentPipeline/preprotection logic with vendor and transport doubles.

The worker produced a changed `validated_candidate`, performed one public validation read and retained its inventory. The parent complete-wire guard **reverted to the complete unaugmented original**:493 reference input tokens before and after, zero accepted transformations and zero native recovery calls. Validation work remained recorded, `publication=unknown_no_parent_ack`, and no generated tags/offset metadata appeared in the model wire. This proves internal annotation removal is not credited as original-wire savings and a worker validation does not falsely assert parent publication.

### Old strategies — PASS within bounded compatibility checks
Independent actual-dispatcher probes of `compress` and `compress_documents` show no new preparation validation reads, no custom-tag preflights, no new validation fields and no handler calls during prepare. Old facade/public-document paths remain distinct; strategy switches reject before a second incompatible invocation. No old strategy IDs/catalog/default were changed by this review.

## Reproduce the two blockers without privileged execution
Use existing Python `-B` with source skill and tests on `sys.path`; all vendor modules must be installed as the explicit `test_headroom_preprotection_worker.vendor` fixture doubles. Do **not** run `headroom_worker.main()` bootstrap or import a real vendor runtime for this reproduction.

- **W2:** `vendor = vendor_fixture.__wrapped__(pytest.MonkeyPatch())`; seed H in the fake store; use `run_rpc_loop([{"id":"early", "op":"retrieve", "hash":H, "tool_call_id":"native-early"}], vendor)` before any compression. It returns a successful raw legacy result. A parent adapter with `strategy=PREPROTECTION_STRATEGY`, no manifest handshake, and its real `retrieve` method forwards that content. The JSON report also records the stronger RuntimeSession eager-start reproduction.
- **W1:** compile only the actual dispatcher loop (as the supplied `run_rpc_loop` harness does), with an externally retained `emit` collector and recorded DocumentPipeline instance. Set fake public retrieve to raise KeyboardInterrupt or SystemExit; catch that only in the outer verifier harness. One read/event remains in state but the emit collector is empty. RuntimeError control returns a counted fallback. Full case results are in `independent_exception_boundary_probe`.

All counterexamples are in-memory/fresh temporary fixtures. They do not claim actual fresh-container seeded content, make OS signals, or access old registries.

## Gaps / stop condition
W1 and W2 need repair and explicit regressions before whole-composition approval. Actual pinned public tag/pipeline/store/handler qualification remains pending; main's controlled public-API probe was not run by this reviewer. No real-model/native efficacy, statistics, all-in savings or promotion claim.

Sources/tests remained unchanged; no production edits or old evidence operations were performed. Parent echo closure is complete; whole-worker review stops with these two actionable counterexamples, not an approval inferred from320 passing tests.


---
## Follow-up: effective hard protection and controlled public-API evidence

Completed **2026-10-10T02:19:43.747549+00:00**. **FAIL for whole-composition approval: W1/W2 remain open; W3 is independently confirmed.** Parent P1 remains closed. This addendum supersedes the earlier "public API pending" gap only for the bounded controlled cases below; it does not erase earlier findings or failures.

### W3 · MEDIUM · Fallback-added effective protection is not checked
`headroom_worker.py:907-916,931-948,954-958` adds E4 to `effective_protect` after tag preflight fails and passes that set to the pipeline. The post-pipeline equality loop instead checks the original `protect`. A synthetic pipeline can therefore change E4 without raising. Its existing fallback decision skips projection and leaves **every final message exactly equal to pristine input**.

Fresh independent in-memory reproduction against unchanged worker SHA `f9b0c4c073422e2f646199fd879e995b4d6fa6f1f268201f5bc9c5e6b3efca89`:

| Tag preflight | Injected mutation | E4 effectively protected | Result |
|---|---|---|---|
| lost | none | yes | exact original fallback |
| lost | E4 content | yes | **no exception**, exact original fallback |
| lost | original protected index0 | yes | `ValueError: pipeline changed protected message` |

Each case runs one explicit pipeline double, zero public reads/handler calls, and leaves its request unchanged. The JSON addendum contains executable reproduction code and full outputs. This confirms the parent's `effective-protection-red.json` independently.

**Impact:** incomplete before-return hard-protection enforcement, **not a demonstrated model-content bypass**. Do not claim that mutated E4 reaches the model, or that this probe proves a real vendor violation. Required owner repair: check the complete `effective_protect` set and add hostile-pipeline tests for fallback-added protections. No production edit was made here.

### Recorded public-API qualification: probe003 bounded PASS
Read-only inspection of frozen scripts, plans/seals, stdout, validation events, guard receipts, container records and cleanup. **No probe was rerun and no Docker/vendor/model/network operation was performed by this reviewer.**

- All three plan seals and worker/probe snapshots match. All frozen workers match current `f9b0...ca89`. All seven probe003 plan source hashes match current files. Later harness-only drift in001/002 is explicitly retained; it is not product drift during execution.
- **001 remains FAIL:** no probe output, terminal container state `created`, owned removal recorded. Logged creation omits stdin-open and uses the wrong strict command shape. This supports the pre-start boundary diagnosis; the receipt records only `ValueError`, not the exact failing validator field, and no inspect snapshot survives.
- **002 remains FAIL:** container exit0 did not pass the parent gate. Fresh pure guard replay reproduces mixed fence/structure rejection. The raw5-byte `x = 1` slice is independently digest/length verified as a compressed validated fragment. The changed double in003 preserves short content; no product gate was weakened.
- **003:** frozen code imports the actual public tag/pipeline/store/handler while explicitly replacing detection and learned compression. Mixed candidate passes independently replayed fence/structure guards; the accepted6931-byte raw fragment is a unique pristine contiguous slice with matching source binding, SHA and UTF-8 length. Handler equality and hostile explicit-hash overwrite refusal are assertions in the passing frozen script. Pure-text contamination performs one public validation read and returns the exact original. The public tag roundtrip is also asserted in that script.
- Known003 preparation work: **two public validation reads total**, one in each independent case-local store (`validated_candidate`, `contaminated`). Feedback-side-effect scope and `publication=unknown_no_parent_ack` are preserved. No accumulation across independent stores or publication inference.
- The saved003 boundary has the pinned image/revision, nonroot identity, readonly root/binds, network-none, strict command and stdin settings. All three cleanup records match the exact CID plus successful recorded owned removal. This is evidence review, not a new live cleanup inspection.

**Limits:** raw handler JSON is not separately saved; delivery/refusal is evidenced by frozen assertions and successful execution. `raw_entry_preservation=true` is a literal report field, not an instrumented store census. The public probe does not execute the complete RuntimeSession native wire/Root/size guard or prove all routing branches, neural efficacy, task quality, or savings. It exercises post-handshake recovery and ordinary completion, so it **does not close W1 or W2**. A current worker repair will need fresh scoped verification; do not retroactively relabel these frozen runs.

### Integrity and stop condition
All **55** scoped source/test/contract/probe/receipt files have matching before/after hashes in the JSON addendum. Original review history is preserved (Markdown appended; existing JSON fields retained). Only `WORKER_REVIEW.md/.json` were written; parent review, production, old audits, registries and original probe artifacts were not changed.

**Review writes finished.** Hand back W3 to the owner for repair; whole-composition approval remains withheld for W1/W2/W3. No further runtime qualification was authorized or performed.
