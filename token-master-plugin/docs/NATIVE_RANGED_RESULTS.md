# Native ranged reads and compact recovery — October 9, 2026

**The real native mechanism passes; the subsequent real-model workload does
not.** See `NATIVE_RANGED_LIVE_RESULTS.md`: baseline completes 2/2 tasks,
candidate 1/2, with the document task budget-stopped before a final answer.
The complete `native-004` qualification below uses actual Copilot, Headroom and
native recovery, but canned primary-model replies.

## What changed

1. **Ranged reads can supply trusted source results.** Explicit
   `--source-contract native-view-result-v2` supports successful `view_range`
   results and the native boolean `forceReadLargeFiles` option. The default
   `native-full-view-v1` contract is unchanged.
2. **History binds to actual execution.** Issued names/arguments and observed
   view results are checked before model submission. A receipt covers the exact
   observed result—not a complete file or a fresh filesystem read. Failed reads
   and directories never acquire successful-file authority.
3. **Root references can be compact.** Explicit
   `headroom_root_reference_style="compact-root-v1"` stores provenance metadata
   server-side instead of repeating it in model context. The default
   `annotated-v1` style retains existing V2 marker bytes and old policy IDs.
4. **The real missing-file rendering is qualified.** For the specific observed
   Copilot 1.0.95-0 failure, the adapter matches its issued-path error sentence
   under the exact error/telemetry conditions and records the rendering contract.
   It does not infer arbitrary error wrappers or turn failure into source
   authority. Foreign/parent/alternate-stream paths reject before metadata probes.

The document worker accepts the same strict argument shapes. Native names are
not rewritten. Newest, exact/edit/debug, source, fence and complete-input guards
remain in place.

## Why compact references were needed

The retained `native-002` run reached real Headroom but submitted no changes:

| Same third request | Reference input tokens | UTF-8 bytes |
| --- | ---: | ---: |
| Original | 6,850 | 30,086 |
| Projection without recovery — diagnostic only, never admissible | 6,726 | 29,527 |
| Projection with the old Root reference, without Ponytail | 6,887 | 29,841 |

The verbose reference added **161 marginal tokens**, exceeding the projection's
124-token reduction. The request was 245 bytes smaller but **37 tokens larger**.
The existing token guard correctly rejected it.

The compact format is:

```text
[[BR:<64 lowercase hexadecimal characters>|r=1]]
```

It is a 75-character opaque reference. **Pass the complete marker to recovery;
its ID is not a content hash.** Its identity binds a version/domain, full scope,
content hash and canonical complete metadata. Lookup uses an exact scoped,
minted reference and verifies metadata, full content and lengths. Metadata stays
available under the recovery response's `metadata` field.

Compact issuance is root-only. Fragment behavior, old references, character
paging, leases and explicit garbage collection remain. Corrupt/deeply nested
metadata fails closed without repairing or overwriting the stored row.

## Actual installed qualification

`native-004` completed the unchanged scripted schedule:

| Cell | Canned primary requests | Accepted changes | Native recoveries | Result |
| --- | ---: | ---: | ---: | --- |
| Overview, partial/EOF document reads | 5 | 3 | 2 | Pass: compact Root and upstream fragment delivered |
| Exact reading plus a genuine missing-file failure | 3 | 0 | 0 | Pass: exact and failed outputs unchanged |

The three accepted requests directly remove **73, 16 and 16 reference input
tokens**, respectively: **105 total**, including the complete wire and recovery
framing. They remove 482, 381 and 381 UTF-8 bytes. Ponytail is configured but
omitted by the guard on those requests; it is not credited with the reductions.

There were **zero real primary-model calls**. Local Headroom/neural work did
occur and is recorded separately. Hidden/native-internal compute remains
unknown. These are request-level mechanism results, not a whole-task A/B test,
answer-quality result, all-in saving or promotion certificate.

All preceding artifacts remain:

- `native-001`: prepared, never executed; pre-dispatch oracle repairs required
  a new freeze.
- `native-002`: three canned calls; range admission worked, but reference
  overhead prevented every accepted change. Exact cell unattempted.
- `native-003`: overview passed, exact cell failed because the missing-file
  rendering was not supported. Seven canned calls plus one rejected native
  primary attempt; not a successful overall qualification.
- `native-004`: fresh installed source, full eight-call protocol passes.

## Guarantees and limits

The runtime still checks literal reconstructed text equality before accepting
a projection. Recovery roots mean the **complete observed tool result**, which
may be a fragment of a file. It does not reread the file to reconstruct a range.

Opaque reference hashes provide computational binding under their cryptographic
assumptions, not unconditional collision-free identity or an OS security boundary.
Literal equality checks verify the particular original/reconstructed strings.

The unchanged final-wire guard proves nonexpansion under the pinned reference
token counter and UTF-8 byte boundary. It does **not** prove fewer subsequent
calls, shorter outputs, unchanged answer quality or lower total compute.

The versioned policy catalog is now `runtime-policy-neighbors-v4`, including a
direct guarded document/compact-root choice from true off. Default policy IDs,
existing registries, consumed tasks, mathematical gates and normal profiles are
unchanged.

## Still required

The changed-code real-model comparison used the same new adapter for both
configurations, preserved the exposed corpus, predeclared limits/order/outcomes
and counted every attempt. It finished negative: one directly reduced input,
followed by a source reread and a call-cap stop without an answer. Read
`NATIVE_RANGED_LIVE_RESULTS.md`; no extra call or replacement run was used.

Native learning also has two independently verified unresolved constraints:
its current evaluator requires identical initial requests, while native
workspaces/time/session context differ; the existing controller allocations are
exhausted. No normalization, gate relaxation or replacement registry has been
silently introduced. Native write/debug, broader validation and release work
remain in the full active goal.

Evidence:
`evidence/integrated-runtime-20261009/native-ranged-results/`.
The source/driver reviews, all failed runs, exact audits and regression logs
are retained there. Native learning's separate read-only diagnosis is
`native-learning-design/COMPARABILITY_AUTHORITY.md` in the parent directory.

The frozen ranged/compact implementation used in the live study passed
**4,475 tests plus 19 subtests**, with three skips and one existing Pydantic
warning. All 201 snapshotted Python source files remained unchanged. Later
post-study guards require their own verification and are not covered by that
old full-suite result. Overlapping test counts must not be added.
Software verification is not a task-efficiency certificate.

The independent native-004 audit also confirms all eight raw protocol chains
and the 105-token/1,244-byte input reduction. It preserves earlier failed
qualifications and does not certify the later real-model outcome.
