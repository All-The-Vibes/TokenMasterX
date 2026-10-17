# Structural preprotection: bounded design review

Date: 2026-10-09. **Design only.** No production/test Python edits, tests, model/native/Docker/network calls, registry/JeV calls, or study reruns. Only this new document is written while the parent regression is active.

## Decision

**Conditionally feasible, not ready as a wrap/strip-only patch.** Prefer an explicit *tagged structural-span strategy* for the particular goal of preserving recognized tables/lists while leaving ordinary surrounding prose eligible for genuine Headroom compression. Keep the existing post-projection structure/fence/source/Root/full-wire gates mandatory. No efficacy or semantic-completeness claim follows.

The implementation must include a **checked recovery projection boundary**, not just a final-view unwrapper. The pinned pure-text route deliberately stores the pre-tag-protection input as `ccr_original`; with adapter-inserted tags, that input is annotated. Vendor recovery otherwise exposes those tags. Do not mutate/rekey vendor entries to hide this fact.

Lossless-only router configuration is the simpler alternative when the requirement is to avoid *all* lossy prose word selection. It does not provide the same opportunity to shorten non-repetitive natural prose and is not a universal Markdown byte-equivalence theorem. Treat it as a separately selected strategy, not a silent fallback or a route-forcing trick.

**Approval boundary:** proceed to implementation only if the parent accepts explicitly versioned recovery projection and its bookkeeping. If “vendor recovery must remain raw-byte-identical to its stored original” is non-negotiable, general tag preprotection is incompatible with that requirement at this pin. Lossless-only/no inserted wrappers is then the bounded public-API option. No inspected public option supplies pristine `ccr_original` separately at the full-pipeline API.

## Source-backed findings

Upstream **V** = `docs/research/2026-10-04-parity/headroom/source/headroom-1cf496612e781ef8d67ff87ee4f78037492f0bc7/`. Product **P** = `token-master-plugin/skills/token-master/`.

| Evidence | Consequence |
|---|---|
| `V/headroom/transforms/content_router.py:2982–3122`: `_compress_mixed` protects custom tags before splitting, supplies `isolate` placeholders, passes any placeholder-bearing section verbatim, rejoins with `"\n\n"` and restores tags. | There is a real upstream structural exemption. It protects selected bytes before lossy work, unlike veto-only acceptance. Reassembly can introduce boundary whitespace. |
| `V/headroom/transforms/tag_protector.py:78–140`; `V/crates/headroom-core/src/transforms/tag_protector.rs:488–599,685–705`: custom-tag blocks are recognized/restored; missing placeholders are discarded; restoration replaces every occurrence. | Lost, duplicated or reordered placeholders require an independent reject rule. Restoration is not a proof that every expected span survived once. The Rust implementation tolerates/matches some nested and malformed combinations; do not infer protection from XML-looking syntax alone. |
| Rust tag protector `:265–286`: sixteen collision-salt attempts, then a fixed fallback prefix. | Do not rely solely on upstream placeholder collision handling against adversarial literal text. |
| Router `:4383–4425,4512–4556`: pure-text protection passes `ccr_original=content`; Kompress `:1620–1649,1874–1898` stores it. | A pure-text vendor entry can contain the injected wrappers even if the visible result was unwrapped. Do not assume the mixed route will always be selected. |
| Router `:2702–2807`; `mixed_content.py:48–64`: content-based selection precedes mixed-path protection. | Wrapping can change routing; it does not guarantee MIXED or the tag-protection branch. Do not inject synthetic fences, force a detector verdict, rename tools or create synthetic tool IDs. A bypassed/lost wrapper causes rejection. |
| `V/headroom/cache/compression_store.py:287–455`: keys normally hash stored original bytes; a conflicting existing key may be overwritten. | A vendor hash is not enough to prove stable fragment identity. Do not overwrite the original under the same key with sanitized bytes. Revalidate exact raw bytes at delivery. |
| Store `:458–558`: `retrieve()` records access and feedback; `get_metadata()` exposes only a 2,000-character original preview. | There is no inspected public, feedback-neutral, complete-original peek. An acceptance audit using `retrieve()` would change upstream feedback and must not be disguised as observation-only. |
| `V/headroom/ccr/response_handler.py:185–260`: actual handler retrieves and serializes `original_content`. | The wrapper boundary must also cover this model-visible string, not only compressed messages. |
| Router `:2174–2182,3748–3760,4323–4335`: `lossless=True` forces relevant marker/lossless settings, stops before lossy dispatch and disables dense elision. | Supported configuration on the real ContentRouter; no standalone compressor is needed. |
| Router `:3700–3740,3165–3255`; `lossless_compaction.py:467–541`: embedded JSON and format-specific folds, with documented ANSI/diff exceptions; mixed reassembly remains. | “Lossless” must be scoped to its actual representation/inverse. Do not replace all existing final checks with a configuration name. |
| `P/brainspace/document_structure.py`: exact recognized spans; nested-fence boundary repaired. Current worker protects non-E messages and uses the public pipeline. | Export offsets from this same parser, not a second Markdown implementation in the mounted worker. Preserve existing grammar and post-check semantics. |

## Minimal explicit interface and trust boundary

Suggested names are a design contract, not shipped APIs:

- Parent selection: `structure-preprotection=tagged-spans-v1`, default off. Require explicit document mode, `document-structure-v1` acceptance, and whole-original-input nonexpansion. No normal profile or old policy-ID change.
- New exact-key RPC: `compress_documents_preprotected`. Retain current `id`, `model`, `messages`, `eligible_indices`, `frozen_message_count`, `keep_recent_tool_results`; add closed `span_contract` and `message_spans` fields. Lock the task worker to a new strategy, e.g. `native-documents-structure-tags-v1`, on its first compression operation. Never mix it with the old strategy/store.
- `span_contract="document-structure-v1-offsets-v1"`. Each eligible message has its original text SHA-256 and an ordered array of `{kind,start,end,sha256}`. `kind` is exactly `table` or `ordered-list`; offsets are Python Unicode-code-point positions, end-exclusive. Digests cover exact UTF-8 slices. No source filename or task-word selection rules.
- The parent owns structural detection and completeness: export offsets from the same scan that currently supplies the guard's exact text sequence. Tests must prove offset-slice sequences equal today's recognized-block sequences. Parse ambiguity or bounds overrun means **no changed projection**, not an empty “no structures” result.
- Worker independently validates exact types, E, message identity/digest, UTF-8 encodability, `0 <= start < end <= len(content)`, sorted/disjoint spans, line-aligned boundaries, allowed kinds and slice digests. Reject bool-as-int, duplicate descriptors, stale content, overlap and out-of-E targets. Retain current frame bound and explicit descriptor-count bound; bound failure is no-op/error, never truncation.
- Worker can validate descriptors mechanically without parsing Markdown. It must not claim it independently proved the parent's syntax/completeness. The parent's unchanged final guard reparses pristine input and final output, catching structural omissions even if the descriptor producer is wrong.
- Metadata must come from the trusted parent adapter, never from instructions inside model text. It is not cryptographic proof of native execution; existing receipt binding remains authoritative.

## Annotation and exact inverse

1. Retain pristine messages and the original public query separately. Compute context from pristine history, never from annotation. Annotate only E strings; roles, tool names/IDs/arguments, non-E bytes and frozen boundaries stay unchanged.
2. Worker mints an occurrence-specific, non-HTML custom tag name, for example `tm-structure-<task-nonce>-<counter>`. Use a task-owned nonce and bounded registry; reuse a previously assigned name for the same exact message/span identity to avoid needless annotation/cache churn. Source text never chooses an identifier or authorizes its removal.
3. Before insertion, check collision with the **reserved adapter namespace and upstream `{{HEADROOM_TAG_` family**. Such original literals make this message ineligible for changed annotation; preserve them rather than silently stripping or reinterpreting them. No unpredictable-token scheme replaces exact collision checks.
4. Insert only the exact opening/closing delimiter strings immediately around the existing span: `open + original[start:end] + close`. **Do not insert padding, newlines, fences, headings, sentinel prose or synthetic examples.** This leaves the original span—including its existing trailing blank lines—intact. A following line may share a placeholder line and become conservatively exempt too; accept this as less compression, not a reason to change source layout.
5. Use the published `protect_tags`/`restore_tags` functions for a bounded deterministic preflight in a later authorized implementation/qualification. Require exact roundtrip and that every injected frame is protected as a whole, separately identifiable block with its exact body—not swallowed by a different natural outer tag. Reject ambiguous nesting/overlap. Existing unrelated natural tags are data, not wrappers to remove.
6. Run **one actual public TransformPipeline** with the same prototype stages/order/rollout, observer, router settings except the separately declared mode, and `compress_tagged_content=False`. Do not patch `_compress_mixed`, call a standalone compressor, or force a route. Preflight is not a guarantee that the selected route respects tags.
7. On the returned E string, require every expected opening/closing delimiter **exactly once and in original occurrence order**, with the exact original span between each pair. Reject missing/changed/duplicated/reordered frames, unknown reserved names, dangling delimiters and any residual upstream placeholder family. Do not append a missing span, “repair” structure, or normalize whitespace.
8. Remove only the registered exact delimiter strings at validated positions. Never regex-strip arbitrary XML or `HEADROOM_TAG` text. Reinsert nothing that the result did not actually preserve. Retain a checked annotation/deannotation edit map.
9. Apply existing fence restoration/equality, `document_structure_preserved`, source/call/non-E equality, exact observed-Root stash/retrieval and complete original-input token/byte checks to the **deannotated final view**. All must pass. Extra vendor reassembly blank lines may change captured list boundaries; reject, rather than trim surrounding source whitespace to manufacture acceptance.

No-spans, no-op, wrapper-loss and final-expansion outcomes are first-class receipts. Invalid frames must never reach the native model. Any ledger work already performed remains recorded; structural rejection is not “zero inference.”

## Recovery boundary: raw vendor data and delivered source are different objects

### Mandatory distinction

The genuine store may retain annotated originals. Keep them unchanged for audit. A sanitized delivery is **adapter-decoded observed content**, not byte-identical raw Headroom retrieval and not a full source file. The hash remains the upstream lookup key for its raw encoded entry; do not label it the SHA of the delivered text.

Root recovery remains simpler: stash the pristine observed tool result only, with existing complete metadata and scope checks. Never stash annotated/placeholder text as a Root. A true native reread is a new executor-observed result; apply the same normal source boundary, not synthetic reconstruction.

### Minimal delivery firewall

- Maintain a bounded task-lifetime registry of emitted vendor handles and their candidate message/annotation provenance. Marker syntax alone, and handles appearing in original/model-authored text, do not grant registry membership. Preserve old registered handles across RPCs needed for task recovery; saturation fails closed instead of evicting live ownership.
- Original candidate text containing preexisting upstream retrieval-marker syntax should be treated conservatively as ineligible for this first mode. This avoids claiming source-authored handles as newly generated. On request failure/reversion, retain actual-work evidence and mark provisional associations unaccepted; never manufacture a successful recovery claim from them.
- For a registered retrieval call, invoke the **existing actual CCR handler once**, preserving the real tool-call ID and name. Strictly parse its successful JSON envelope. Failures stay failures; do not turn them into content.
- Validate the returned raw fragment against retained annotation maps. Permit either (a) exact pristine source slices, with no internal namespace, or (b) exact slices of known annotated input whose endpoints do not cut an injected delimiter or frame. For (b), only fully present, registered frames may be decoded; require exact interior bytes, known occurrence order and unambiguous source-origin mapping. Reject partial frames, unknown placeholders, multiple conflicting origin candidates and non-exact/normalized reconstructions.
- The decoded fragment must match its mapped **contiguous pristine observed-result slice literally**. Where an upstream structural producer stores transformed/non-contiguous originals that cannot be proven by this rule, report a bounded recovery-provenance failure. Do not guess provenance or fall back to returning a different full Root under a vendor hash.
- Scan every model-visible string field, not merely `original_content`, for adapter-generated residue. Do not expose raw annotated token/item counts as counts of decoded source. Preserve them, explicitly labeled, in the private raw receipt; retain/omit/recompute model-facing counts only under a tested explicit response schema. Root and vendor recovery namespaces remain distinct.
- Preserve the raw handler response/digest separately from the delivered response/digest, with mapping version, source result digest, source offsets, wrapper occurrences and decision. A worker restart without this task mapping must not decode guessed handles.
- At finish, audit the actual raw store entries separately from decoded projections; label the raw map as raw evidence, not a native recovery body. Do not overwrite historical or default-mode `recoveries` semantics. Native/MCP rendering equality must be verified on the **delivered** payload, with both renderings equal. No added field may accidentally turn source prose into a success-status assertion.

### Public API limitation and acceptance claim

Do **not** inspect `get_metadata().original_content_preview` as if it were complete, access `_backend`, swap the singleton, monkeypatch storage, or read full entries early through `retrieve()` without disclosing feedback changes. This design performs full validation when a real retrieval occurs and audits after the task, preserving current no-early-audit behavior.

Consequently the initial mode can promise **no internal-wrapper leakage on any successful delivered view/recovery**, not that every vendor marker is always immediately redeemable or that the raw store is wrapper-free. TTL/missing/unsupported provenance remains an explicit failure. Root remains the separately validated complete observed-result path. If parent requires complete raw-fragment provenance validation *before accepting a view*, that stronger requirement is a blocking design decision: the inspected public store has no non-feedback full peek. Either explicitly version/account for validation reads or obtain a suitable upstream API; do not quietly satisfy it through private state.

## Tag route versus lossless-only

| Dimension | Tagged-span mode | Public `ContentRouterConfig(lossless=True)` |
|---|---|---|
| Structural goal | Prevent selected tables/lists reaching lossy work, then verify exact spans | Avoid lossy dispatch broadly; final structure/fence check still required |
| Natural prose | Remains eligible for actual Kompress; may shrink, no promise | Repetition/format folding or passthrough; less opportunity on non-repetitive prose |
| Query fidelity | No completeness proof for selection or surrounding prose | Avoids this word-dropping class, but representation changes/inverse interpretation are not an answer-quality proof |
| Recovery risk | Annotated raw entries require the checked decoding boundary above | No adapter-wrapper contamination; native transforms/CCR behavior still must be inspected |
| Minimal effort | Parser-offset export + new RPC/strategy + frame checks + recovery mapping/evidence | Separate configured router profile and full-stage/guard manifest |
| Appropriate choice | Conditional research/implementation choice for the stated structural-plus-prose objective | Lower-complexity control or alternative when lossy surrounding prose is not acceptable |

Do not combine both silently: that would stop Kompress on prose and make the meaning of the treatment unclear. Neither permits threshold tuning, task-specific exceptions, synthetic read patterns or weakening the fixed quality/nonexpansion conditions.

## Offline, model-free evaluator contract

No evaluation is run by this review. After the parent releases the source freeze:

1. **Pure span contract:** original guarded grammar and new offset output must agree exactly for every accepted parse. Exercise duplicate tables/lists, mixed LF/CRLF, astral Unicode/code-point offsets, orphan/nested fences, trailing blanks, EOF, unsupported syntax, forged/stale descriptors, bool offsets, overlap, reorder and bounds. No source file is reread to populate spans.
2. **Annotation inverse:** `decode(annotate(text, spans), registry) == text` literally. Require exact original span SHA and byte equality before/after. Check adjacent spans, same bytes at distinct positions, natural tags/nesting, all reserved collisions, duplicate/drop/reorder/change of frames, partial delimiters and fallback placeholder strings. Deliberate duplicate text must not create ambiguous recovery provenance.
3. **Actual public tag path, separately authorized:** use the pinned public tag protector/router/pipeline with controlled deterministic compressor doubles and real store/handler where needed, not only a mock product Backend. Forbid model loading, downloads, external APIs and provider callbacks. Test MIXED and pure TEXT, no-route/no-op, HTML/alternate-route rejection, missing placeholders, CRLF and extra blank-line joins. A double establishes adapter mechanics, **not real neural efficacy**; any native Rust helper execution needed for this qualification must be separately authorized, not smuggled into this read-only lane.
4. **Raw-store provenance fixture:** deliberately exercise pure TEXT where `ccr_original` contains injected frames; prove raw entry stays annotated, actual handler is called, decoded successful delivery contains none of the internal material and matches exact pristine slice bytes. Also exercise clean MIXED prose fragments. Capture both raw and delivered hashes; never compare a sanitized result against itself as the oracle.
5. **Hostile recovery:** unknown/unissued handle, overwritten raw entry, same handle/different source, two possible origins, truncated frame, marker in literal source, placeholder past character 2,000, expired/missing entry, foreign task, restart and registry saturation. No successful contaminated/native response; failed provenance never returns a substitute Root while pretending it is a fragment. Verify native JSON/text rendering equivalence on delivered bytes.
6. **Policy/manifest isolation:** default old RPC/results/IDs unchanged; new strategy locked across task; include span grammar/version, wrapper codec, collision policy, decoding provenance mode, stage/router/observer settings, no-custom-hook/discovery selection, and full guard policy in canonical manifest/hash. Per-request spans/digests/occurrence names belong in receipts, not the task-stable manifest. Hash rechecks do not replace literal comparisons.
7. **Actual acceptance composition:** real RuntimeSession/CCR with canned transport: unchanged instructions/calls/non-E/newest/frozen/exact/error cases; pristine Root paged recovery including Unicode/CRLF; structure rejection before Root issuance; whole-original final wire remains strictly nonexpanding with all wrappers removed. Compare annotation overhead, raw upstream proposal, deannotated projection and final complete wire separately.
8. **Negative-evidence use:** retained live-001 is an exposed regression input, not a fresh efficacy case. Demonstrate its recognized spans can be wrapped/unwrapped exactly and its old lossy submitted projection remains rejected. Do not change source documents, prompt, ranges, padding, call cap or retry schedule. New real-pipeline/native and later quality qualification remain distinct parent decisions; no inference is authorized here.

Record actual observed local work with the existing lifetime ledger; deterministic preprocessing is additional CPU work, not evidence of free optimization. No proof of model correctness, general Markdown semantics, statistical promotion or task savings arises from span equality or successful wrapper roundtrip.

## Current product source pins inspected read-only

- `P/brainspace/document_structure.py`: `c9c862a729dc581c42b5b0ee482943c26630c2f3a845a179cdc72e380c3d7b28`
- `P/brainspace/headroom_worker.py`: `1d6e43463b7fc7a0351d14e2fcbd99554b4a8bf660497beb848cd29c635edb9d`
- `P/brainspace/protected_text.py`: `4406825058e81b7c76c3d2ecfc4de76d08e4636d9ad950b6c7a51c1c4444136f`

These are inspection snapshots, not authority to overwrite concurrently changing files. Existing failed study evidence and installed pins remain untouched.

---

## Addendum: assessment of the parent's stricter implementation contract

Read-only assessment of `IMPLEMENTATION_CONTRACT.md`, 2026-10-09. This addendum supersedes the earlier suggested *recovery decoding* route for the selected implementation. **Selected mode must never decode, rekey, replace or repair raw vendor entries or successful vendor recovery payloads.** View deannotation remains a separate adapter step.

### Verdict

**No demonstrated design-level blocking counterexample to the stricter variant as stated**, provided “retained raw fragment” means an immutable, exact validation record and every delivery boundary uses it. This is a source review, not implementation approval or a passing execution probe. No production/test Python or running regression was touched.

Public preparation-validation reads explicitly acknowledge the feedback effects that blocked an observation-only full-entry check. Requiring their returned raw content to be a pristine contiguous source slice excludes annotated pure-text entries rather than laundering them through decoding. Later checking the actual handler result prevents those entries from escaping through recovery.

The following are concrete implementation traps and mandatory negative cases—not claims that the as-yet-unwritten implementation already contains them.

### 1. Same handle must never be rebound to replacement content

**Source-supported counterexample if rebinding is allowed:**

1. Preparation validates handle H → clean fragment A, binds it to source result S1, and its view becomes usable.
2. A later pipeline operation stores H → B, or another producer supplies the same `explicit_hash`. The public store permits overwrite even for different originals (`V/headroom/cache/compression_store.py:416–445`); this does not require the adapter to mutate private state.
3. A naive new preparation check sees B inside S2 and updates the registry to H → B.
4. A genuine recovery of the earlier H now returns B and passes comparison to the *new* registry entry.

This violates retained-reference identity. Do not dismiss it as mathematically impossible because normal keys are truncated SHA-256; explicit keys and upstream replacement behavior are inspected facts. It is an identity/integrity requirement, not a predicted natural hash-collision rate.

**Required invariant:** once H is successfully validated, its exact raw UTF-8 text is immutable for the task. Store its length/digest for receipts, but compare actual bytes on subsequent validation/delivery. Never replace A with B. On conflict, reject the new projection; keep the old validation record. If the current vendor store no longer matches that record, subsequent recovery fails closed. Missing/expired/failed handles are not grounds to return cached text while pretending the vendor handler succeeded.

The new-mode test must model an overwrite at the public store surface and prove both that the second view is refused and that the first handle is not silently rebound. No real-model collision search or production store mutation is needed.

### 2. “New handle” must mean new binding, not just unseen hash

A validated H → A in one source does not authorize exposing H inside another message without checking that message's pristine source binding. A naive global `if H in registry: skip validation` lets a new association bypass the exact-slice requirement.

Keep content identity immutable and separately bind the candidate source result/call/message identity. The simplest bounded rule is to reject a conflicting new origin rather than invent multi-origin authority. If multiple origins are deliberately supported, retain all explicitly checked bindings, never overwrite one. Exact same bytes occurring twice are not a license to choose an arbitrary source offset; reject under the stated unambiguous-binding policy unless occurrence anchors prove one mapping.

Also distinguish newly generated marker occurrences from markers already present in pristine/model text. Parser recognition is not issuance. A conservative preexisting-marker bypass remains appropriate for the first mode. Old registered references already in protected history need not be revalidated as a different new source simply because they are scanned again.

### 3. Validate the handler's actual returned payload, not a separate pre-read

The source provides the correct seam:

- `CompressionStore.retrieve()` returns a snapshot after recording access (`:458–518`).
- `CCRResponseHandler._execute_retrieval()` embeds that snapshot's `original_content` in its result (`V/headroom/ccr/response_handler.py:185–243`).

For a known validated handle, call the actual handler once and then strictly check **that returned result**: success is literally true, tool name and real call ID match, payload JSON has a bounded supported shape, payload hash equals the requested handle, and `original_content` is UTF-8-valid and literally equal to retained raw A. Return the original successful result/content unchanged after validation; do not parse and reserialize it unnecessarily.

Do not perform `retrieve(H)` as a recovery pre-check and then call the handler: a replacement between reads would leave the delivered object unchecked and create an extra feedback event. Comparing the actual result avoids that check/use gap. Upstream replacement *after* the handler snapshot does not change the immutable text already being checked/delivered.

Reject unknown/unvalidated handles before the handler; no fabricated native ID is needed. For vendor failures, reject malformed or potentially contaminated error strings and return a bounded adapter error instead. Source `response_handler.py:258–274` embeds `str(exception)` in an error payload; blindly forwarding that path would defeat the contract's failure-framing hygiene. Never return A from the adapter cache or a full Root as a successful substitute vendor recovery.

### 4. Preparation reads have non-rollback side effects even on rejection

`record_access` increments retrieval counts (`compression_store.py:188–200`); `retrieve()` queues/logs feedback and calls `process_pending_feedback()` before returning (`:458–518`). Feedback processing also accesses telemetry and TOIN (`:974–1085`). “No Jev/model call” is not “no local learning/state effect.”

Record each internal validation attempt **before** entering the public retrieve boundary, with a distinct internal ID—not a native tool-call ID—then its success/miss/exception/over-bound outcome. If the getter raises after recording access, or a later span/final-wire guard reverts the view, that work and its possible side effects still happened. Never decrement counters, clear feedback or label the validation zero-work because no view was accepted.

The pinned network-none/task-owned environment remains necessary; the new strategy must not assume upstream feedback is globally side-effect-free. Bind the validation-read behavior to the manifest/profile. Old strategies retain their existing late audit and do not acquire these reads.

### 5. Bounds and publication state must not undermine old handles

Reserve registry capacity conservatively before new validation where possible; inspect returned size/type before retaining bytes. If a read exceeds the retention budget, record its attempted side effects and reject. Do not truncate retained raw text or evict older validated ownership to fit a new proposal. Snapshot comparison needs the full bounded raw fragment, not a preview.

There are two different events: worker returns a validated **candidate**, and parent accepts/publishes the final native wire. Until there is an explicit parent acknowledgement, a worker can only label its record `validated_candidate`, not `published`. Retaining all successful validation records for the task is safe and simple; disclose rejected/unpublished candidate overhead. If a publication-specific allowlist is desired, add an explicit bounded acknowledgement rather than inferring publication from RPC success. This is a lifecycle/accounting distinction, not permission to alter the frozen policy or to discard validated records.

Every handle in a newly proposed message must pass before that message is returned as a projection. If one fails, return the whole pristine original message; do not remove only the offending marker. Other independently valid messages may remain candidates under the existing gates.

### 6. The stronger variant still cannot promise raw-store hygiene or prose fidelity

Rejected pure-text annotation may already exist in the actual store. The guarantee is **no successful contaminated delivery**, not “no internal annotation was ever stored.” Preparation reads and the final audit must retain truthful raw provenance privately. Annotated entries must never populate Root or a model-facing recovery body.

Whole-message fallback does not cancel ongoing/background upstream work. Validate recovery again against retained bytes as above; retain existing worker lifetime inventory and cutoff semantics.

Unchanged table/list spans still do not protect unrecognized surrounding prose, order relations outside those spans, or arbitrary query relevance. This variant improves prevention for recognized structure and may leave genuine mixed-prose compression available; neither safety of every natural-language assertion nor useful compression is established by this source assessment.

### Required additions to the already specified evaluator

In addition to `IMPLEMENTATION_CONTRACT.md`:

- H→A validated, public overwrite H→B, attempted rebinding, then old-handle recovery: no reassignment or successful wrong delivery.
- Same H in a different pristine message; same fragment at multiple offsets; preexisting source marker: no automatic ownership reuse.
- Public getter increments state then raises; missing/expired/oversized reads; later final-wire rejection: validation attempts remain recorded, with no rollback/reset/false model-recovery credit.
- Handler returns wrong hash, wrong real ID/name, nonboolean success, invalid/duplicate-key JSON, changed raw content, contaminated error text: no successful delivery; handler invocation count stays one for an admitted recovery and zero for an unvalidated handle.
- Registry saturation and parent-reverted candidates: older validation records survive and no candidate is falsely marked published.
- Contaminated pure-TEXT entry: raw entry remains unchanged, full message falls back, no native/vendor successful payload contains its framing. Clean MIXED fragment: literal pristine-slice validation and unchanged actual-handler delivery.

**Parent alignment:** these are refinements of the selected strict invariants, not a new recovery-decoding design. No additional empirical claim or live qualification is authorized. The original failed studies and all installed source pins remain retained.
