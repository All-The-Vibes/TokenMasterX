# Explicit structural preprotection: parent implementation contract

The preceding goal turn made concrete progress. Its full regression is still
running as exec session `59538`; no production/test Python changes are made
until that run is terminal. The full R0–R6 goal is not reduced to this slice.

## Objective

Prevent recognized Markdown tables and ordered lists from entering lossy
compression while leaving surrounding prose eligible for the **actual pinned
Headroom public pipeline**. Retain every existing source/status/intent/newest/
fence/Root/structure/final-wire check. Do not substitute a no-op-only policy,
rename native tools, fabricate tool calls, pad tasks or loosen a quality gate
to make the experiment pass.

The source review in `DESIGN_REVIEW.md` is accepted with the stricter recovery
decision below. No raw vendor recovery will be silently decoded or rekeyed.
No real-model task, Jev screen or registry allocation is authorized by this
implementation contract; later qualification must be separately frozen.

## Explicit decision: public validation reads, not recovery rewriting

The inspected public store has no feedback-neutral complete-original peek.
In this **new explicitly versioned, default-off mode**, preparation may call
the existing public `CompressionStore.retrieve()` to validate newly generated
vendor handles before their view is returned.

This is an intentional change in execution semantics:

- These local preparation reads update upstream access/feedback state.
  They are not observation-only and not model-requested recovery.
- Record them separately as preparation validation, including count, handle,
  source-result digest, raw fragment digest/length, outcome and the known
  feedback-side-effect contract. Never manufacture native tool-call IDs.
- The new profile/worker manifest must bind this behavior. Old strategies keep
  their existing audit-after-task behavior unchanged.
- Do not query private backends, use metadata previews as full content, swap
  stores, mutate vendor entries or reset feedback after the reads.
- Validation overhead and downstream behavioral effects remain part of the
  tested new composition; no all-in savings claim is inferred from a smaller
  final input.

**Acceptance is intentionally stricter than merely stripping final-view tags:**
every newly emitted vendor handle must resolve to an exact, nonempty,
UTF-8-valid contiguous slice of the pristine observed result to which it is
bound, with no adapter wrapper or upstream placeholder residue. If any handle
is missing, ambiguous under the required binding, contaminated, inconsistent
or over bounds, keep that original message rather than publish the projection.
Do not decode an annotated vendor fragment to make it pass.

Raw vendor bytes are preserved. On a later genuine native recovery request,
call the real handler once and verify that its successful `original_content`
still equals the previously validated raw fragment before returning it unchanged.
Reject unknown/unvalidated handles or changed content without exposing an
annotated payload. No substitute full Root is returned under a vendor hash.
Failure responses must be bounded and free of internal generated framing.

This choice admits clean mixed-prose fragments where the public tag route
keeps protected placeholders out of compressors. A pure-text route may store
annotated originals and therefore fail this acceptance check. That is a
retained no-op/rejection, not permission to force a route or drop the check.

## Interface and data contract

Names below are proposed implementation names, not shipped claims:

1. Add default-off preprotection selection bound into RuntimePolicy and the
   actual worker strategy. Require `native-documents-v1`-equivalent document
   eligibility, `document-structure-v1` acceptance and whole-original
   nonexpansion. Preserve all old serialized policy IDs and defaults.
2. Export exact ordered character offsets from the **same** existing structural
   parser. Grammar and current acceptance semantics must remain unchanged.
3. Pass digest-bound offsets through a separately versioned exact-key document
   RPC. Parent owns grammar selection; the standalone mounted worker validates
   closed types, allowed kinds, E membership, original digest, UTF-8 slices,
   bounds, line boundaries, order and nonoverlap. No second Markdown parser.
4. Bound span count, frame size, generated-handle count and retained validation
   bytes. Saturation rejects new projection/validation; it does not evict
   ownership of an already published handle.
5. Keep pristine original messages and query separately. Annotate only eligible
   tool content. Names, call IDs, arguments, protected/noneligible messages and
   native source receipts remain unchanged.

## Annotation and decoding

- Insert only registered custom-tag delimiters around the existing exact spans.
  Do not add synthetic prose, blank lines, code fences, padding or examples.
- Choose stable task-owned occurrence identities, with exact collision checks
  against original content and reserved adapter/upstream-placeholder families.
  Do not rely on probabilistic uniqueness instead of checking.
- Use the pinned public tag protector for a model-free protection roundtrip
  check before the real pipeline. Natural tags are data, never permission to
  remove or reinterpret source.
- Run one genuine public TransformPipeline with its existing stage order and
  hard non-E/system protections. Do not patch detector results, private routing
  functions, ratios or model weights.
- Require each registered frame exactly once, in original occurrence order,
  with its exact original interior. Missing/changed/duplicated/reordered/
  unknown/partial frames reject. Do not append a lost span or trim arbitrary
  whitespace to manufacture acceptance.
- Remove only verified registered delimiters, then apply the current fence and
  structural guards. Extra vendor reassembly whitespace may force passthrough.
- Stash only pristine observed text as the full Root. Compare the complete
  deannotated native request against its complete unaugmented original,
  including Root, vendor markers and guidance. Do not credit removed internal
  annotation as saved original-input tokens.

## Proof obligations and limits

For a valid span sequence, annotate/deannotate identity must satisfy
`D(A(x)) == x` by exact slice concatenation. For an accepted changed projection,
every registered structural slice remains byte-identical and ordered, and the
existing reparsing guard must agree. Vendor successful recovery must equal a
validated pristine source slice; Root recovery must equal the complete observed
tool result. Hash binding retains its existing computational assumptions.

These statements do **not** prove complete query relevance, surrounding prose
semantics, model correctness, fewer later reads, or whole-task savings.
Pre-validation feedback may change future compressor decisions; that is
explicitly part of this new strategy, not silently treated as free observation.

## Fixed verification sequence

1. Pure offset/roundtrip/collision/type/bounds/ordering tests, including Unicode,
   LF/CRLF, duplicates, nested fences, partial structures and hostile frames.
2. Genuine public tag-protection and pipeline/store/handler tests with explicit
   deterministic compressor doubles; no model loading or downloads in these
   offline tests. Prove raw store preservation and wrapper-free accepted
   fragments; test the contaminated pure-text case as a rejection.
3. Real RuntimeSession integration with canned transport: preserve all existing
   guards, distinguish internal annotated counts from the final original-wire
   effect, and preserve known local validation/recovery work.
4. Independent review of source/offset/recovery/feedback boundaries.
5. Only after these gates, freeze any installed native mechanism qualification.
   Keep the existing public documents and all previous failures unchanged;
   no result-dependent padding, rescue reads or selected retries.
6. A later real-model efficacy study remains separate and must retain every
   outcome and full-attempt token cost. No such study is pre-approved here.
