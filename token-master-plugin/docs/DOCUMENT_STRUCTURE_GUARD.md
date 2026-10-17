# Exact document-structure acceptance guard

**Explicit opt-in; a necessary preservation check, not a task-quality guarantee.**
This is a post-study change. It does not repair, regrade or replace the failed
real-model result in `NATIVE_RANGED_LIVE_RESULTS.md`.

Select in a typed RuntimePolicy:

```json
{
  "headroom_structure_guard": "document-structure-v1"
}
```

The complete policy must also select Headroom, `native-documents-v1` and
`require_nonexpanding_input=true`. The default `"none"` is omitted from
serialization, retaining existing policy IDs and behavior.

This initial contract is **manual opt-in**. The existing true-off neighbor set
and catalog are unchanged; the guard is not advertised as autonomously selected,
statistically qualified or globally enabled.

## What it prevents

The saved failed document projection omitted a config table's layout and the
ordered model-catalog search list. The model subsequently reread that region
and hit its fixed call cap. A correctly extracted query did not prevent that
loss: the actual pinned mixed-prose Kompress path does not use the forwarded
query. That path-specific source finding is not a claim about every upstream
compression strategy.

The new guard rejects a changed projection unless recognized pipe-table and
ordered-list blocks remain exact, in the same order and multiplicity. It does
not repair the projection, invent missing text or perform another model call.

The runtime applies it after existing fenced-code restoration/checks and before
Root creation. Rejection keeps the original result, with
`headroom_structure_guard_reversion` when no accepted result remains. Optional
guidance, exact recovery and final unaugmented-input token/byte checks continue
to operate as before.

## Exact, bounded contract

`brainspace/document_structure.py` defines the supported grammar in its module
docstring; it is not a complete Markdown parser.

- Supported pipe tables require a header, a valid delimiter row and consistent
  row structure. Complete original line slices are compared, not normalized cells.
- Supported ordered lists retain exact numbered items, qualified indented
  continuations/subitems and their intervening/trailing blank lines.
- Unsupported/ambiguous wrappers, malformed table/list boundaries, bare CR,
  invalid fences, invalid UTF-8 strings and declared size/line-limit violations
  reject changed text.
- A nested indented fence cannot silently terminate list protection. Only the
  declared column-zero fence after a blank separator may end a list block.
- Complete code fences are opaque to this checker. The separate existing
  `protected_text_preserved` requirement still protects their content.
- LF/CRLF and Unicode are retained exactly. Exact valid input/output identity
  passes even when the syntax would be unsupported for a change.

Conservative false positives are intentional. Pipe-bearing prose, quoted
examples or valid Markdown outside the documented subset can force passthrough.
No filesystem reread, task-specific filenames, oracle terms, model inference or
new parser dependency is used.

## Deterministic invariant and proof

Let \(E(x)\) extract the ordered sequence of `(kind, exact block text)` for a
supported document, and let \(E(x)=\bot\) mean unsupported/ambiguous syntax.
The checker accepts valid UTF-8 strings precisely when:

\[
x=y
\quad\text{or}\quad
E(x)\ne\bot,\ E(y)\ne\bot,\ E(x)=E(y).
\]

If a changed projection is accepted, equality of finite sequences gives equal
length, equal kinds and equal exact text at every position. Thus each recognized
table/list block has the same bytes, order and multiplicity. If rejected, the
runtime keeps the original result. In either branch, those recognized structures
are preserved. Existing fence, provenance, recovery and complete-wire checks
are additional requirements, not consequences of this proof.

The known Root marker is added as separate recovery framing afterward; it is
not misparsed as a source table or credited as preserved source content.

**What this does not prove:** that every task-relevant relationship was selected,
that a structure remains associated with the same surrounding heading/prose,
that unprotected prose retains its meaning, or that the model's output or total
call count stays unchanged. Exact structural preservation is not general
semantic equivalence.

## Verification and remaining limits

The saved failed projection is rejected; the original passes. Tests cover
changed/deleted/reordered/duplicated structures, partial and ambiguous syntax,
Unicode/CRLF, code fences, nested fences, bounds, unchanged defaults and actual
RuntimeSession acceptance/rejection with a synthetic backend.

An independent review reproduced a nested-fence boundary defect. It was fixed
with failing-before regressions, and the reviewer confirmed that the actual
runtime now rejects that counterexample **before creating any recovery entry**.
The report retains both the original finding and its closure.

Evidence:
`evidence/integrated-runtime-20261009/native-ranged-results/STRUCTURE_GUARD_REVIEW.md`.
These checks add a real runtime acceptance condition. They are not another
real-model run, a corrected answer, whole-task savings or release qualification.
