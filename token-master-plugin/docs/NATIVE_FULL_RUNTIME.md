# Native full-runtime route — October 9, 2026

**Experimental, explicit, read-only, and not a savings certificate.**
`brainspace_tools.py native-copilot` now connects the actual Copilot CLI to the
existing `RuntimeSession`, typed full policy, actual Ponytail/Headroom components,
task-scoped recovery and transport ledger. It does not implement a second
optimizer or import evaluation runners into production.

## One execution path

```text
owned native Copilot process
  -> original native Responses request
  -> immutable native-envelope projection
  -> existing RuntimeSession + RuntimePolicy + RuntimeResources
  -> selected actual instruction component and one reducer
  -> whole-wire checks and native metadata restoration
  -> existing explicit loopback model gateway
  -> captured reply; real tool IDs registered before delivery
  -> native tool execution / native MCP recovery
  -> trusted JSONL execution events and exact content binding
  -> same runtime on the next request
  -> complete journals, separate outcome check, exact cleanup
```

The separate first-exposure JSON hook is **disabled** in this route. A result is
not compressed twice by independent hooks and request reducers.

The native bridge exposes only `view`, `tokenmaster-retrieve_original` and
`tokenmaster-headroom_retrieve` in its first qualified client configuration.
Native shell/write/edit execution and a native learning-host adapter are still
outside this qualification; ordinary edit/debug validation remains required.

## What is connected and observed

- Copilot CLI **1.0.95-0**, with the actual executable hash checked before launch.
- Native Responses metadata, block/cache annotations, IDs, assistant phases and
  opaque reasoning are retained. Unknown/stateful/multimodal inputs reject rather
  than having their fields silently discarded.
- Only eligible tool-result text and the known optional user-guidance insertion
  may change through the planner. Native recovery names are normalized internally
  only after their real registrations are verified; original native schemas and
  names return on the wire.
- Tool provenance uses actual `toolCallId` values from trusted native
  `tool.execution_start` / `tool.execution_complete` events, matched to issued
  upstream calls, arguments and the exact next-request output. The ID-less hook
  payload is not used to invent identities.
- A Root/Headroom recovery RPC requires a unique issued, observed-started,
  still-pending native call. Claims are one-use and atomic. A terminal old call
  cannot authorize recovery or make a newer valid call falsely ambiguous.
- Every upstream submission uses the existing runtime capture/ledger path.
  Rejected authenticated HTTP requests are recorded separately as known
  unsubmitted work, not fabricated zero-token model calls.
- HTTP handlers queue work; actual runtime/model/component operations execute
  on the owning main thread. Native processes start suspended, enter a private
  Windows Job Object, then resume. Cleanup and earlier interruptions survive
  observation-close and summary-persistence failures.

## Installed functional qualification

The native client—not a replacement model loop—executed these fixed protocol
flows through a copied installed package and a **synthetic upstream provider**:

| Selection | Native upstream requests | Observed mechanism |
| --- | ---: | --- |
| True optimizer off | 2 | Native read, matched successful source receipt, unchanged context |
| Local V4 | 4 | Two source reads, two actual accepted request transformations, native MCP retrieval reaching the next request as the exact observed original |
| Actual Ponytail + actual Headroom | 4 | Pinned instructions on the upstream wire; actual task-lifetime Headroom worker and local inference; three matched native source reads |

All original failures remain in the evidence. The first bridge probe correctly
stopped before inference because its initial gate incorrectly required *zero*
skills: the stock native client has two built-ins. The corrected gate accepts
only those exact built-ins under the owned, versioned cache, never arbitrary
personal/project catalogs. A later local flow remained incomplete until its
actual dual-text native MCP result shape was qualified.

The rows use different fixed functional flows. Their request or token totals
must **not** be compared as a matched efficiency experiment.

**These are transport/component checks: zero real model calls, no quality
certificate, no measured whole-task token savings and no promotion.** Synthetic
usage fields are never offered as provider token measurements.
Current-source copies and source-stable verification are indexed by
`evidence/integrated-runtime-20261009/native-full-profile/CONTINUATION.md`.

## Why the upstream-default combined fixture emitted no Headroom reduction

The actual pinned upstream diagnostics mark native `view` results
`protected:excluded_tool_verbatim`. Its only changed messages in this fixture
were proposed system-prompt reductions, which the runtime correctly restored.
Thus **zero Headroom changes were accepted**, despite genuine component execution.
The one upstream fragment reference belonged to protected content and was never
emitted as an accepted model-facing context view.

Do not rename `view` to another tool to manufacture activation, relax the
newest/exact/edit/debug/source/fence guards, or present configured/executed
components as savings. A source-reviewed **new explicit policy** is needed
before qualifying old overview-document views through the supported upstream
configuration. See `HEADROOM_NATIVE_VIEW_OPTIONS.md` in that evidence directory.

Native Root recovery was exercised in that default-policy fixture. Its fragment
was not accepted, so that fixture did not qualify native fragment delivery.
Earlier custom-host fragment evidence remains separate.

## Explicit document strategy and real-model result

The new default-off `RuntimePolicy.headroom_strategy="native-documents-v1"`
uses the actual upstream public pipeline with a configured router that no
longer excludes `view`. It admits only exact-bound successful older text
documents under overview/navigation intent; other messages remain protected
inside the upstream pipeline as well as at the final parent boundary. The
native tool is not renamed and the upstream-default policy is unchanged.

The installed `native-documents/native-002` scripted flow now verifies four
accepted reductions and exact native Root and upstream-fragment delivery.
This is mechanism qualification with six synthetic upstream requests and zero
real model calls, not a savings benchmark.

The separate frozen real-model `live-002` comparison passed two tasks in both
configurations, with seven calls each. **None of the candidate requests changed.**
The native client used ranged document reads, which receive no source receipt
under the current provenance contract; exact-code reads remain protected.
The nonexpansion guard omitted Ponytail and preserved the original inputs.
Its small between-run token difference is not attributable to the optimizer.
See `NATIVE_DOCUMENT_RESULTS.md` for every attempt, accounting and limitations.

### Subsequent ranged/compact support

The default source contract remains `native-full-view-v1`. Explicit
`--source-contract native-view-result-v2` now admits valid ranged native file
results as complete **observed tool results**, not complete files. It also
binds issued names/arguments and observed view output before reuse in history.
The configured worker accepts the same strict boolean force flag and integer
range contract.

Typed policy `headroom_root_reference_style="compact-root-v1"` shortens the Root
marker while retaining full scoped provenance server-side, exact reconstruction,
paging and all final-wire guards. Defaults and old policy identities remain.
`NATIVE_RANGED_RESULTS.md` records the source-qualified eight-request installed
mechanism pass and preserves its preceding failed qualifications.

The separate real-model comparison is **negative**: baseline completes 2/2,
candidate 1/2. One 107-reference-token reduced input is followed by a source
reread and a call-cap rejection without a final answer. It is not a wrong final
answer or reliable whole-task savings; all 15 model calls including readiness
are retained in `NATIVE_RANGED_LIVE_RESULTS.md`.

## Controls and accounting

Nonstreaming HTTP, a single-call response policy, output limit and configured
reasoning effort are common transport controls, fixed equally for off/treatment.
Their addition to the native request is recorded and **not credited as
optimization**. The standard runtime guard still compares the selected final
wire with its own complete unaugmented baseline.

Model/call/reference/native-usage units stay separate. Reference counts include
observable complete JSON bodies, not a claim to authenticate hidden serving
tokens or compute. Native usage events do not get added again to the same API
calls. Local Python ONNX activity is recorded separately; native-internal/all-in
coverage remains explicitly unknown.

Known local bridge credentials are blocked in literal and decoded JSON body
keys/values before dispatch or raw-body capture. They are not provider credentials
and are never forwarded to the upstream gateway. Native environment/state lives
under the new owned output directory; no normal profile is installed or modified.
Directory exclusions use the actual Windows OS-profile path, not a potentially
redirected `HOME`. This is not an OS filesystem/network sandbox.

## Explicit entrypoint

Global `--workspace` and `--session` precede `native-copilot`. Supply an explicit
qualified executable, gateway/model, network opt-in, new output directory,
existing verified tokenizer and prompt. A closed `--runtime-policy` JSON file
selects the full composition; omission is **true off**. Actual components require
their already-provisioned resource arguments.

`--help` lists the supported flags. No dependency, model asset or credential is
downloaded/discovered. Exit 0 means operational completion and retained
accounting/cleanup, **not a correct answer or a certified efficient policy**.

Remaining full-goal work: native outcome/evaluator/learning coupling,
task-relevant structural/prose fidelity, native write/debug scope, feasible
independent ordinary-task evaluation and remaining all-in/release coverage. The earlier
1.43% V4-only and 4.9%-worse combined results are unchanged; neither is replaced
by the scripted mechanism check or the no-transform native comparison.
