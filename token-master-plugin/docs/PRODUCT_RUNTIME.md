# Integrated task runtime — implementation checkpoint

**Experimental, explicit, and not globally enabled.** The installed package now
has a persistent execution path connecting request preparation, real component
adapters, model submission, scoped recovery and token accounting. This is not
a claim of general savings, native-host interception, or completed parity.

The separate native JSON hook remains documented in `NATIVE_COPILOT_HOOK.md`.
The new **`native-copilot` entrypoint** now connects the actual native client to
this full runtime, its typed policy/resources and complete-call ledger; see
`NATIVE_FULL_RUNTIME.md`. Its installed protocol checks use a canned upstream,
not a real-model savings benchmark. Explicit ranged-result provenance and compact
Root references now qualify through the native path; see `NATIVE_RANGED_RESULTS.md`.
The subsequent live comparison activates compression but fails one task at its
call cap, so useful whole-task savings remain unproved; see
`NATIVE_RANGED_LIVE_RESULTS.md`. Native learning/evaluator and broader task
qualification remain open. Upstream-default Headroom still excludes native
`view`; explicit document strategies are distinct opt-in policies.

## What is connected

| Component | Runtime connection | Boundary |
| --- | --- | --- |
| Local task discipline | Explicit `TaskContract` or matching `TaskModeStore` session | Local implementation, not Ponytail code |
| Ponytail | Validated pinned full instruction export, applied once in the materialized conversation | Actual upstream instruction content; not its complete host plugin lifecycle |
| Local context reduction | Existing `prepare_request` and separately versioned request policies | V3 default when `backend=local`; no lossy callback in V3 |
| Lexical JSON reduction | Opt-in `request-policy-v4`, using the existing conservative JSON compactor and exact root recovery | Unique eligible JSON reads; all payload lexemes retained; mandatory whole-input guard; annotated result is not standalone JSON |
| Headroom | Actual pinned public compression pipeline and upstream CCR handler in one checked task-lifetime container | Requires already-provisioned image/model assets; no download or fake local substitute |
| Native Headroom documents | Explicit `RuntimePolicy.headroom_strategy="native-documents-v1"` using a configured real upstream pipeline | Older successful exact-bound `.md`/`.markdown`/`.rst`/`.txt` results; ranges need explicit native-view-result-v2; no native tool renaming |
| Compact Headroom Root | Explicit `headroom_root_reference_style="compact-root-v1"` | Exact scoped opaque marker with metadata retained server-side; guarded Headroom only, old defaults and local V4 unchanged |
| Whole original-result recovery | Workspace/session-scoped CCR roots for accepted Headroom changes | Exact observed tool result; not a claim that every tool result is a complete file |
| Model submission | Caller-owned `encode`/`send` boundary; builtin opt-in loopback Responses-compatible gateway adapter | Text/function-call histories only; no ambient credential lookup, redirect, proxy or retry |
| Deployment selection | `Optimizer.deployment_policy(...)` | Rejects synthetic registries, wrong regimes/versions and unvalidated ancestry; does not promote or optimize on the hot path |
| Local-policy learning | `RuntimePairEvaluator` plus the fixed `ReadonlyGatewayHost`; `token_efficiency.py initialize-runtime` / `learn-runtime` | Actual runtime calls and private checks, one bounded iteration; no backend/instruction search or automatic promotion |
| Full-profile learning | Closed `RuntimePolicy` plus explicit `RuntimeResources`, `ProfileLearningManifest`, and `initialize-profile` / `learn-profile` | True-off default, actual components, same strict registry/gates; both arms ready before primary calls; no automatic promotion |
| Accounting | Durable attempts/captures, `TaskTrace`, `TokenLedger` | Complete API-body reference tokens and reported gateway usage remain separate |

The Ponytail instruction source is the pinned `DietrichGebert/ponytail` export,
not the separately installed Codex engineering-suite plugin. Headroom is the
pinned 0.39.1 runtime previously qualified for comparison. Their implementations
are now callable from the installed runtime rather than only evaluation code.

## One session, not chained optimizers

```text
trusted host: original history + executor read receipts
    -> frozen session configuration
    -> optional local task contract OR actual Ponytail instructions
    -> no reducer OR local policy OR actual Headroom
    -> protected-content and complete final-wire token/byte checks
    -> exact prepared wire submitted by the transport
    -> reply retained and accounted
    -> host-authorized tools / matching recovery namespace
    -> next request from the ORIGINAL history
    -> finish, separate external outcome check, exact owned-resource cleanup
```

Headroom and the local reducer do not run serially on the same representation.
The session keeps its recovery backend alive across turns. It preserves
system/developer messages, call/result binding, explicit exact/prefix guards,
recent results and original client history.

Guidance is inserted as subordinate user-level execution guidance before the
actual user task, not promoted above system/developer instructions. It is
included in every final-wire count. There is no automatic instruction tax when
no instruction component is selected.

Headroom projections are operator-qualified: protected/newest messages remain
original; eligible older source results require matching successful executor
receipts and exact full-root recovery. Fenced protected text must remain exact.
Unsupported structural changes or final-wire inflation are not accepted.

When the whole-input guard is selected, a shared eligibility check now runs
**before** Headroom startup/preparation. It requires an older, sufficiently
large, unprotected string result with matching successful executor provenance.
With no possible eligible result, the runtime records
`headroom_no_eligible_sources` and does not start/prepare the component.
The profile binds `bound-source-eligibility-before-start-v1`; legacy flag-off
behavior remains unchanged.

The current-call reasoning is simple: every accepted changed index must belong
to the checked eligible set \(E\). If \(E=\varnothing\), no tool-result change can
be accepted, so running the reducer is unnecessary for that request's selected
input. This does **not** prove equivalent future cache/warmup behavior or task
savings. Full-profile learning deliberately readies selected components before
either primary arm so missing resources cannot create a biased comparison.

### Explicit native document mode

Select `headroom_strategy="native-documents-v1"` only through a typed
`RuntimePolicy`, with `backend="headroom"` and
`require_nonexpanding_input=True`. The default `upstream-default-v1` strategy
retains the previous serialized policy and behavior.

This mode uses the actual upstream `TransformPipeline`, preserves the default
stage order, removes only `view` from one copied router exclusion list, disables
system compression and protects every non-eligible message before upstream
work. The effective configuration/stage/guard manifest and eligible indices
are validated across the container boundary. Existing exact Root recovery,
fenced-text preservation, newest/exact/edit/debug protection and final complete
wire checks remain authoritative.

The first live comparison bypassed ranged reads. Explicit native
`source_contract="native-view-result-v2"` now qualifies those observed results;
its complete installed protocol check also verifies compact Root and native
fragment delivery. The later live comparison still does **not** prove efficacy:
one reduced document request was followed by a reread, and the task hit its
fixed four-call cap before a final answer. No automatic/default profile change
follows from mechanism qualification or that failed outcome.

Compact Root selection retains literal full observed-result reconstruction
checks and full-wire nonexpansion. It changes the marker representation, not
the upstream lossy word-selection semantics or the task-quality gate.

## Installed entrypoint

`brainspace_tools.py --workspace WORKSPACE --session OPAQUE_ID session ...`

Required session arguments:

```text
--output NEW_DIRECTORY_OUTSIDE_WORKSPACE
--base-url EXPLICIT_LOOPBACK_GATEWAY
--model CONFIGURED_MODEL
--allow-network
--backend none|local|headroom
```

Optional component selection:

- `--require-nonexpanding-input`: explicit opt-in whole-composition guard,
  including instruction and recovery-schema overhead. See the invariant below.
- `--ponytail-export FILE`: the validated pinned export; no bundled substitute.
- `--contract FILE` or `--use-session-mode`: local task discipline, not combined
  with Ponytail instructions.
- `--policy JSON` or `--optimizer-db DB`: explicit local policy or a validated
  production champion. Registry selection also requires explicit version,
  workload and environment identities.
- `--backend profile --runtime-policy FILE`: typed full composition, with
  explicit pinned resource arguments. Separate legacy composition overrides
  reject; loading a file is not certification. See `PROFILE_LEARNING.md`.
- Headroom requires `--headroom-cache DIR --headroom-assets FILE`.
  Without an explicit empty Docker configuration, the runtime creates one
  within its owned output directory, never reads a normal host config.
- Optional `--headroom-time-budget-seconds N` accepts integers 1–60 for
  Headroom only. It sets both upstream cooperative compression budgets through
  the checked container environment and binds the selected value into the
  runtime profile. Omission preserves the original regime; no ambient
  environment override is forwarded. This is not a hard total response bound.
- Calls, frames, input/output bytes, output tokens and socket waits are bounded.
  Socket timeout is not an absolute process-wide deadline.

The input is a **trusted host-control JSONL channel**, not model-generated text.
Each frame is a newline-terminated UTF-8 JSON object, at most 1 MiB. Do not pipe
assistant output into this channel.

```json
{"op":"call","request":{"model":"CONFIGURED_MODEL","messages":[{"role":"user","content":"Your task"}]},"intent":"conservative"}
{"op":"observe-read","receipt":{"call_id":"EXECUTOR_CALL_ID","tool_name":"read_file","source_path":"module.py","content_sha256":"EXECUTOR_SHA256","status":"success"}}
{"op":"recover","name":"retrieve_original","args":{"ref":"VALID_SESSION_REFERENCE","offset":0},"tool_call_id":"RECOVERY_CALL_ID"}
{"op":"finish"}
```

These are schema examples, not a ready-made valid conversation. The host supplies
the full original history, real tool calls/results and receipts generated only
after execution. `RuntimeSession.execute_tool(...)` provides an API wrapper for
host-authorized execution; a bare string does not attest successful source reads.
`ExecutedToolResult` supplies an explicit outcome. No shell or arbitrary plugin
executor is enabled by the JSONL service.

Headroom source/document views require an explicit `navigation` or `overview`
intent; exact/edit/debug/conservative requests bypass that lossy path. The
upstream default also excludes `read_file`. A selected component can legitimately
produce no changes; requested backend is not proof of an accepted transformation.

`finish` accepts no model-supplied quality verdict. Exit 0 means protocol,
observed accounting and cleanup completed, **not** that the model answered
correctly. Exit 2 is a control/configuration error; exit 3 is incomplete
accounting, component execution or cleanup.

## Whole-composition input invariant

The API option is `RuntimeSession(require_nonexpanding_input=True)`; the session
CLI flag is `--require-nonexpanding-input`. The default remains off so an explicit
request to apply a full component is not silently changed.

Let \(x\) be the complete unaugmented wire from the caller's original request,
\(y\) the protected composition including guidance, schemas and references,
\(T\) the pinned reference-token counter, and \(B\) UTF-8 byte length. Define
\(K(v,x)\) to mean \(T(v)<T(x)\) and \(B(v)\le B(x)\).

The current guarded strategy, `optional-guidance-selection-v1`, also considers
\(y^{-}\): the same one-time, structurally validated and protected projection
with **only the newly inserted optional guidance** removed. This alternative
exists only when that insertion is identified and the projection changed
eligible context. Original messages and required recovery schemas stay intact.

Emit:

\[
z=\begin{cases}
y,&y=x\ \text{or}\ K(y,x),\\
y^{-},&\text{otherwise, if the eligible }y^{-}\text{ exists and }K(y^{-},x),\\
x,&\text{otherwise}.
\end{cases}
\]

**Proof:** either accepted non-original branch satisfies both inequalities; the
fallback emits the exact original. Therefore \(T(z)\le T(x)\) and
\(B(z)\le B(x)\) for each successfully materialized request. This depends on the
declared deterministic counter/transport boundary, not on model weights.

The fallback is whole-request and atomic: it does not leave behind added
instructions, tool schemas, recovery annotations or transformation credit.
When only optional guidance is omitted, accepted context changes and necessary
recovery tools remain; indices are remapped and the receipt reports
`optional_guidance_elided` with instructions configured but not applied.
No second compressor or model call is made to select that alternative.
Existing output/input/byte caps still apply after the decision. Receipts expose
original, augmented and final measurements plus configured versus actually
applied instructions. Legacy `reference_before` remains the augmented count;
do not mistake it for the unoptimized baseline.

This is **not** a bound on generated output, number of subsequent calls,
task correctness, total task tokens or local neural compute. Headroom execution
is still recorded when a prepared result is reverted. Registry selection with
this new guard is rejected until that composition is separately represented
and qualified; existing controller gates are unchanged.

An offline recorded-input check matched all 18 previously submitted combined
wires before applying the guard and restored every unaugmented original exactly.
It removed the 24,660 reference-input-token instruction overhead on that fixed
set of inputs, with **zero provider requests**. It did not rerun Headroom, retest
task outcomes, or establish future task-level savings. Evidence:
`evidence/integrated-runtime-20261008/composition-input-replay-002/`
(repeated after typing-only cleanup; earlier replay also retained).

A later current-installed local check exercised the improved selection on the
three recorded Jev-document inputs. With the explicitly declared 60-second local
budget, the final input fell from **6,288 to 6,140 reference tokens**, with exact
Root and actual upstream-fragment recovery, 13 completed observed Python ONNX
runs, and zero primary requests. Its earlier default-budget attempt timed out
and is retained as a failure. This is an input/component result, not another task
answer, a causal speed result or general token savings.
Evidence: `evidence/integrated-runtime-20261009/elision-validation/`.

## Real read-only learning entrypoint

`token_efficiency.py` retains the explicitly synthetic demo commands. The new
runtime commands use installed production modules, not the synthetic responder:

```text
token_efficiency.py --db NEW_DB initialize-runtime
  --manifest TASKS_JSON --output NEW_ADMISSION_DIRECTORY
  --base-url LOOPBACK --model MODEL --allow-network

token_efficiency.py --db SAME_DB learn-runtime
  --manifest SAME_TASKS_JSON --output NEW_TRIAL_DIRECTORY
  --base-url SAME_LOOPBACK --model SAME_MODEL --allow-network
  --task-id CONTENT_DERIVED_ID
```

These are argument outlines, not multiline shell syntax. Use the task IDs
returned by initialization. Repeat `--task-id` for a predeclared batch. Keep
all common options and source versions identical; changed files, task/gold data,
model, limits, tokenizer or environment identity do not silently enter the old
comparison. Use a new output directory each time. Reused task IDs are rejected
by the durable controller, including failed/interrupted attempts.

The manifest is data only:

```json
{"schema_version":1,"tasks":[
  {"prompt":"Read note.txt and return {\"value\":NUMBER}.",
   "files":{"note.txt":"The value is 7.\n"},
   "expected":{"value":7},"intent":"exact"}
]}
```

The built-in host exposes bounded list/read/recover/answer operations, not shell,
write, arbitrary plugin imports or user-provided checker code. Expected answers
stay outside model workspaces and messages. A private checker compares typed
JSON values and owned file bytes after each sealed/closed runtime. These are
checks for the declared cases, not a claim of broad semantic-quality evaluation.

Important distinctions:

- **Initialization is safety admission only.** It performs no model calls and
  does not establish baseline task accuracy. The default admitted policy is
  enabled conservative V3; `--policy` can select another explicit local policy.
- **The comparison is enabled local incumbent versus local neighbor**, not
  optimizer-off versus TokenMaster. This learning path does not learn whether
  to enable Ponytail or Headroom; those remain separate explicit runtime choices.
- One iteration proposes, freezes, reserves, executes both bounded arms, recounts
  raw captures and applies the existing strict controller gate. It never retries
  selected tasks or promotes a result. Deterministic ordering is the default.
- `--jev` separately authorizes one advisory screen of generated **policy
  settings only**. `TYPESAFE_API_KEY` must already exist in that process.
  No key search, task source, expected answer or repository dump is sent.
  Abstention/failure retains deterministic ordering. Screening tokens and
  incomplete usage remain in the controller's learning accounting.
- Known used-task and exhausted-budget requests are rejected before screening;
  the preflight is not a reservation and the final transactional gates remain.
- Extra Jev receipts are persisted only after controller accounting.
  Authentication headers are never recorded. Remote error bodies, escaped
  response metadata and reflected configured secrets are withheld from raw
  receipts, without discarding incurred counts/hashes. Withheld bytes cannot be
  independently recounted from that receipt; this limitation remains explicit.
- A fixed/exposed task manifest is not automatically an independent population
  sample. An internal `not_certified` result is not a product failure, and an
  internal gate result cannot establish unverified sampling assumptions.
- Each pair shares the reserved task identity but receives distinct native
  runtime/call IDs. Wrong-model replies, missing captures and checker
  infrastructure failures must not become quality evidence; their incurred
  costs and consumed IDs remain visible.

## Measurement and failure rules

- Every dispatched or unresolved model attempt is reserved before submission.
  Complete failed HTTP responses count. Missing bodies/counters remain unknown.
  A durable no-submission receipt can resolve an unsubmitted reservation.
- Captures include the actual full transmitted/received body text, not separately
  added prompt/tool estimates. Final transport wrappers and instructions count.
- Lost capture or acknowledgment writes cannot seal a complete ledger.
  Cancellation preserves unresolved work, stops further calls and cleans up
  owned resources without retrying the model.
- Recovery attempts remain counted even if their terminal journal write fails.
  Component/tool inventory then becomes incomplete; valid primary-token
  subtotals remain available.
- Runtime-owned tool counts and external executor read receipts are distinct.
  A host must route its full task through the runtime to claim full task coverage;
  the library cannot discover omitted external calls.
- Headroom local neural activity has separate receipts and incomplete native
  inference visibility. It is **not free or silently counted as zero**. A complete
  primary API-token trace is not complete all-in compute accounting.
- Python ONNX observations now use stable lifetime event/session IDs, locked
  revisions and a cumulative final inventory. Per-RPC compatibility records are
  revision upserts, not additive calls. Pending attempts, event/frame overflow
  and native detector/embedding internals remain explicit gaps; a complete
  snapshot is not proof of process quiescence or complete hardware work.
- Effective container environment is validated against its exact declared
  public profile before startup or raw configuration persistence. Credentials,
  proxies, remote/backend overrides and unknown settings are rejected.
  The optional finite time-budget values are separately declared and receipted.
- Captures contain supplied task/tool content and are not anonymized. Use
  approved private storage and sanitized verification inputs. Credentials are
  not discovered, added to prompts, or stored by credential setup here.

## Verified so far and remaining work

A copied installed runtime completed a real combined Ponytail + Headroom
source-reading flow through the existing configured gateway: three model
requests, two actual source reads, the correct independently checked answer, and
confirmed cleanup of its exact container. Both actual upstream components ran.
Headroom intentionally made no changes to those `read_file` results. This proves
that execution connection, **not compression savings**.

The next document activation check is retained as a failure: three model
requests, an incorrect default-backend answer, and no accepted transformations.
Its raw receipts show an upstream ratio/cache bypass for README and a fence
language normalization on the newest template result. These are not relabeled
as a success or silently retried.

A subsequent retained cross-document flow made six model requests and used
54,085 gateway-reported tokens. It accepted five changed results across three
requests, preserved final code fences, and returned exact full-original bytes
on two model-requested recoveries and one verification-only recovery. The answer
was still wrong. An offline UTF-8 audit corrected a Windows driver decoding
mistake without rerunning the model or changing the failed summary. Accepted
compression/recovery therefore has mechanism evidence, not task-savings proof.

A separate fixed chronological replay subsequently verified both recovery
namespaces from an actually accepted current-task view: an exact 23,925-byte
Root and a distinct 1,818-byte fragment returned by the actual upstream handler.
All six recorded inputs were replayed once with primary network authority off.
The container and attach client were cleaned up; old failed probes remain
unchanged. This closes that component-handler check, not task quality or
efficiency. Evidence: `evidence/integrated-runtime-20261009/fragment-recovery-001/`.

The subsequent installed real-evaluator/Jev diagnostic completed with both
answers correct, one Jev abstention and no promotion. The ordinary read/edit/
debug/document off-versus-combined schedule is also complete: off passed 4/4,
combined passed 3/4 with one upstream HTTP 503. Both coding workflows passed
isolated behavioral checks in both arms. No request was compressed. The measured
instruction overhead made the selected combination worse, not a savings result.
See `INTEGRATED_RUNTIME_SCORECARD.md` for complete known/unknown usage and the
independent audits; do not remove the failed attempt.

Remaining acceptance includes live qualification of the guarded composition,
demonstrated quality-preserving efficiency, complete all-in overhead accounting
and native routing/release
qualification. The active goal remains unfinished.

Evidence root: `evidence/integrated-runtime-20261008/`.
Authoritative delivery contract: `ACTIVE_EVALUATION_GOAL.md`.
