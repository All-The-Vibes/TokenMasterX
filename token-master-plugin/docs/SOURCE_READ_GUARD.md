# Successful-source-read guard repair

October 6, 2026. Scope: the request-context reducer, not answer refinement.

## Failure reproduced

The existing v1 guard treats words such as `error` and `Exception` anywhere in
a tool result as a failure. This protects unknown text but also blocks ordinary
successful source reads. The recorded repository trial changed no requests.

## Repair contract, before editing

1. Keep existing v1 policy identities and behavior unchanged. Add an explicit
   v2 policy identity for the new handling; do not reinterpret old certificates.
2. Accept source-read metadata only as an out-of-band, typed argument supplied
   by the trusted tool executor. Bind it to the call ID, tool name, exact UTF-8
   content hash and filename. Text claiming its own success is not metadata.
3. Skip the failure-word heuristic only for a matching, explicitly successful
   source read. Actual failure/status flags, exact-content markers, protected
   instructions, tool pairing, the newest result and edit/debug bypasses remain.
4. Pass the source filename to the existing code compressor. It still requires
   supported syntax, navigation intent, recoverable originals and a smaller
   final serialized request. Do not weaken its parsing or recovery checks.
5. Add tests before the change: successful source containing error-handling
   text must become eligible; missing/stale/forged/failure metadata and exact
   content must not. Verify Python/Rust filename handling and policy identity.
6. Replay the saved request bodies offline. Report the original intent and
   recency constraints honestly; do not relabel a changed adapter as the same
   old experiment. Then run a fresh paired repository diagnostic with frozen
   sources, explicit metadata and the same correctness checks.

No provider keys, model weights, global host profiles, production defaults or
statistical promotion gates are changed. Source metadata is an adapter contract,
not cryptographic proof that an executor reported truthfully.

## Interrupted-study reporting contract

The first live v2 trial proved activation on its completed navigation pair but
stopped after a transport deadline. The evaluator correctly marks missing usage
unknown; the repository-specific auditor still raised on that partial inventory.
Before another run:

1. Preserve all original receipts and the partial result; never overwrite or
   silently retry the timed-out attempt.
2. Independently recount every complete captured call, including the prefix of
   a failed task. Separate known subtotals from unknown whole-task totals.
3. Report missing task runs and incomplete calls without treating either as
   zero token use. Reject missing, duplicate or contradictory inventories.
4. Freeze the source, tasks, model, controls and comparison order before new
   inference. Explicitly require network opt-in; keep real host settings intact.
5. Authenticate the fixed public-source fixture before any trusted reference
   code executes. Generated edits still require exact equality to that patch.
6. Record budget stops and distinguish an unsubmitted task from a completed
   comparison. A read-only task fails on a write attempt even when final bytes
   are unchanged; the revised repository oracle has a new version identity.

The reusable repository diagnostic is `evals/run_repository.py`. Its result is
descriptive evidence, not a representative parity or promotion certificate.
