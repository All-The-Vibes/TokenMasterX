# Structural preprotection qualifier — new authoring-only slice

**Not prepared or executed. Parent review/release is required.** This directory
is a new copy/adaptation of `native-ranged-results/qualifier`, not an edit to that
qualifier or its runs/audits. `ORIGIN.json` freezes the old inventory and the
exact pure grammar snapshots used here. Only files below this directory are
owned by this authoring lane.

Read contract: `../IMPLEMENTATION_CONTRACT.md`; finalized interfaces inspected
in `brainspace/headroom_worker.py`, `headroom.py`, `runtime.py`,
`runtime_policy.py`, `document_structure.py` and `protected_text.py`.
The parent reports public-API controlled probe003 passed. That probe is not
neural/native-flow evidence, not a release gate bypass, and is not rerun here.
The parent's worker reviewer remains independent; this lane does not contact
agents, modify production, or declare their review complete.

## Exact change from the old qualifier

| Surface | Old | This new qualifier |
|---|---|---|
| Worker strategy | `native-documents-v1` | `native-documents-structure-tags-v1` |
| Structure guard | no explicit structure selection | required `document-structure-v1` |
| Root style | annotated or compact option | compact only; no implicit fallback |
| Worker operation | `compress_documents` | exact-key `compress_documents_preprotected` |
| Span authority | none | parser-owned observed-text offsets and UTF-8 digests; `document-structure-v1-offsets-v1` |
| Acceptance | original native controls | all original controls plus exact structures, unwrapped-candidate linkage, framing rejection and raw validation/recovery evidence |
| Validation accounting | no preparation-store contract | cumulative public-store validation reads, feedback side effects and unknown publication explicitly separated from native recovery |
| Interpretation | protocol-only | still protocol-only; candidate validation is not publication or efficacy |

The installed typed policy is exactly Headroom/Ponytail, 60-second cooperative
Headroom budget, original-input nonexpansion true, the strategy/guard above and
`headroom_root_reference_style="compact-root-v1"`. Both sessions explicitly use
`source_contract="native-view-result-v2"`. Existing production defaults and old
policy serialization are not changed.

## Unchanged public sources and scripted requests

No new task or source text. Use the same byte-exact pinned public files:

- `wiki/filesystem-contract.md` —
  `6a679ec6a586eaff8c805d63860c4c14a666ab6ddca1e42ce0c20363e42f5e2c`
- `wiki/persistent-installs.md` —
  `2500c1ef0f3ab389dbbd72fdb28968c1586291d87919b2a1719a7a6fc2055ea0`

Upstream snapshot: `1cf496612e781ef8d67ff87ee4f78037492f0bc7`.
The driver copies complete originals, with unchanged filenames and contents,
to owned public temporary workspaces. No padding, renamed tools, query-tuned
fixtures, larger sources, injected instructions or fallback read.

The original prompt, model `gpt-6-astra`, reasoning `low`, native timeout 360,
transport timeout 60 and primary request sequence are unchanged:

1. Overview `view` filesystem-contract.md with `[3,159]` and
   `forceReadLargeFiles: true`.
2. Overview `view` persistent-installs.md with `[30,-1]`.
3. If actually emitted on the accepted older partial result, native Root
   recovery via exactly `{ref, offset: 0}`. 32768 is the server page cap, not a
   client `limit`.
4. First newly emitted upstream fragment recovery, if any.
5. Canned final request, including recovery delivery.
6. Exact session: the same partial `view`.
7. Exact missing-file `view` with `[1,-1]`.
8. Exact canned final request.

Five overview plus three exact requests are **caps**, not a requirement to
manufacture a fragment or use all calls. Global maximum eight canned primary
requests, including failures. No retries or transfer of unused budget. An
overview failure retains exact as genuinely unattempted. The exact/status
control is also exact-protected, not isolated attribution of a status guard.
Native Root recovery is exact observed range-result text, not whole-file bytes.
The pinned missing-path renderer repair and successful MCP rendering paths are
retained unchanged.

## New mechanical checks

### Spans and public pipeline contract

- Exact operation keys, strict eligible-index types/order, newest/frozen
  exclusions and exactly one descriptor for every eligible message.
- Recompute complete descriptors using exact copies of the **same existing
  pure grammar**, not a second Markdown parser. Offsets are end-exclusive
  Python code points; source/slice/digest echoes are UTF-8 SHA256. No source file
  reread supplies a recovery answer.
- Require actual strategy/manifest digest, stable task manifest, public
  ContentRouter with tagged compression disabled, no custom extension route,
  exact declared preprotection/feedback/bounds contracts and typed echoes.
- Check annotation receipts (original digest/length, frame count and distinct
  annotated digest), effective protection and candidate/fallback decisions.
  The receipts attest internal annotation; this qualifier does not capture or
  independently replay hidden neural work.
- Worker-returned views must be unwrapped. No generated `<tm-`, `tm-structure`
  or upstream `headroom_tag` placeholder family may reach candidate/native
  delivery. Protected messages and original native call identities stay exact.

### Accepted complete native wire

All old accepted-wire checks remain: nonempty eligible original actually reaches
the configured pipeline; it changes, its complete transmitted wire is strictly
smaller in reference count and UTF-8 bytes than its complete original, and
capture digests/actual provider bodies agree. No annotation-local count or
worker candidate alone can pass.

For each accepted partial-result projection, remove **only its verified exact
Root prefix** for structural parsing; compare the actual remaining view to the
original ordered structures. The accepted result must contain recognized
tables **and** an ordered list, unchanged in bytes/order/multiplicity. Existing
fence preservation must also pass. Compare the actual native view with a
returned unwrapped candidate allowing only the already-supported parent fence
formatting restoration. The evidence itself is never edited/repaired.

A no-op, unsupported native rendering, changed structure, missing frame evidence
or rejected full-wire candidate fails the qualification. Do not reshape the
documents/ranges/prompt or relax ratios/guards to make it pass.

### Raw public-store validation versus actual native recovery

Preparation records are local public `CompressionStore.retrieve()` reads with
documented access/feedback/telemetry/TOIN side effects, **not** model-requested
recovery or invented native tool IDs. Validate:

- cumulative attempts/delta boundaries and final inventory (never sum repeated
  cumulative snapshots);
- handle, RPC/message association, exact source binding, source digest,
  unique contiguous pristine raw slice, UTF-8 length/digest and task bounds;
- immutable association of a validated handle with raw text/source;
- `publication == "unknown_no_parent_ack"` and
  `candidate_publication == "unknown_no_parent_ack"`.

Reports expose `candidate_not_claimed_published`, validation attempts, public
retrieve entries, validated candidate handles, retained raw bytes,
native-requested fragment recoveries and post-task audit handle count
**separately**. Failure paths retain best-effort unverified counts plus raw
receipts; absent evidence stays unknown rather than fabricated zero.

Every native-published vendor marker must have the same validated source
binding. If a fragment is requested, require its actual worker retrieval reply
and native start/completion/delivery. Parse the JSON envelope only; never
deannotate/decode/rekey `original_content` to make it pass. The decoded string
must equal the previously validated pristine slice and unchanged stored value.

A raw post-task store audit may retain contaminated rejected candidates. That
private diagnostic is not publication and is not erased. Only validated,
wrapper-free raw fragments may appear in successful native delivery. Validation
of an unissued candidate is not a native recovery credit or proof of publication.

## Preparation, installation and lifecycle

The future parent invocation supplies an explicit fresh reviewed isolated
installation and successful install receipt. No installation or dependency
download is implemented in this driver. Installed required entrypoints/worker/
structure guard must match current source; all other mappable installed Python
files are checked too. A stale grammar snapshot fails and is never auto-refreshed.

`prepare` requires a new explicit child under this lane's `runs/`. It freezes
source/installed/qualifier/resource inventories, policy/style/guard/span contract,
native/interpreter/vocabulary pins, original/copy document bytes, exact actions
and the implementation contract. It creates no provider or runtime. `run` is
separate, one-shot and explicitly gated. Its only upstream is the canned
loopback provider.

The **installed API owns the main thread**. There is no outer runtime subprocess
wrapper/watchdog. The installed runtime owns its exact process/container/config
cleanup. A pass still requires native process-tree/readers/queue/EOF/secret-config
settlement and Headroom cleanup `complete: true`. Public workspaces, installation,
failed attempts and all raw receipts remain retained for audit; no broad deletion.

Attempt registration precedes dispatch. Partial outcomes/capture counts survive
interruptions and later cells remain unattempted. Each report write is attempted
independently. The first cancellation wins over ordinary errors; an existing
cancellation cannot be masked by later reporting failure. A failed report write
cannot turn the run into a pass. The exclusive start marker prevents restart.

## Parent-only future commands — NOT invoked here

```powershell
$q='evidence/integrated-runtime-20261009/structure-preprotection/qualifier'
$out='evidence/integrated-runtime-20261009/structure-preprotection/runs/<new-id>'
python -I -B "$q/qualify_ranges.py" prepare --output $out `
  --package <fresh-isolated-installed-home/token-master> `
  --install-receipt <successful-isolated-install.json> `
  --native-executable <qualified-absolute-copilot.exe> `
  --tokenizer-file <verified-local-vocabulary> `
  --ponytail-export <pinned-ponytail.json> `
  --headroom-assets <verified-headroom-assets.json> `
  --headroom-cache <existing-model-cache> `
  --root-reference-style compact-root-v1
# Fresh interpreter, only after parent review/release:
python -I -B "$q/qualify_ranges.py" run --output $out --execute-reviewed-canned-protocol
```

Only that future run can provide neural/native preprotection qualification.
Offline checker tests and the earlier public-API double probe cannot establish
that the real compressor chooses a safe useful route, that a candidate survives
all guards, or that Root/fragment recovery and cleanup succeed. Even a future
pass is protocol evidence, not efficacy, model quality, IID/representative
sampling, whole-task/all-in savings or promotion.
