# V4: exact JSON payload compaction with original recovery

**Opt-in, new version; not a default or a model-quality certificate.**
V1–V3 behavior and identities remain unchanged.

## Why another policy version?

V3 replaces only repeated identical source reads while their full originals
remain visible. It cannot reduce a unique JSON read. The existing conservative
JSON compressor already supports an inexpensive deterministic operation; V4
connects it to request planning, exact recovery, final transport guards and the
full-runtime controller.

V4 does not invoke the general overview router, sample arrays, truncate strings,
sort keys or reserialize numeric values. It removes JSON grammar whitespace
outside strings. No neural model or additional inference is needed.

## Precisely what is preserved

For accepted JSON payloads, the original ordered sequence of non-whitespace
lexemes is unchanged, including:

- Every member and item, including duplicate object members and their order.
- Every string character and escape spelling.
- Every numeric spelling, exponent and negative zero.
- Booleans, nulls, delimiters and collection cardinality.

Malformed/already compact content remains unchanged. The implementation uses the
existing conservative `compress_json`; parsed objects are never serialized into
the replacement. A dedicated callback is independently checked against the
exact expected compact payload, canonical scoped reference and recovered bytes.

**Presentation limit:** the model-visible result is:

```text
<complete compact JSON payload>
<canonical full-original recovery reference>
```

The JSON payload is preserved under the lexical contract. The **entire annotated
tool string is not standalone JSON**. The original formatting is not present in
the compact payload but remains exactly recoverable. Do not describe this as
byte-identical text or pass the entire annotated string to a JSON parser.

## Deterministic proof obligations

Let \(J\) be accepted JSON text. Let \(L(J)\) denote its ordered grammar tokens,
retaining the exact spelling of strings and numbers. Let \(W\) remove only the
four grammar-whitespace characters outside strings.

1. **Lexical preservation.** The compactor retains complete quoted-string spans
   verbatim and removes only external grammar whitespace. Input validation
   rejects malformed token boundaries. Thus \(L(W(J))=L(J)\). In particular,
   duplicate members and numeric spellings are not collapsed by parsing and
   reserialization. This is stronger than comparing two parsed Python objects.
2. **Exact recovery.** Before acceptance, the scoped root must decode to the
   original UTF-8 bytes: \(R(\operatorname{ref}(J))=J\). A missing, mismatched or
   unverified original rejects the replacement.
3. **Whole-input nonexpansion.** Let \(x\) be the complete original transport
   input and \(y\) the candidate including reference, recovery schema, guidance
   and all wrappers. A non-original candidate is emitted only when
   \(T(y)<T(x)\) and \(|y|_{\mathrm{UTF8}}\le |x|_{\mathrm{UTF8}}\), using the
   pinned exact reference counter. Otherwise the original is emitted. All caps
   still apply.

Therefore semantic consumers that depend on this ordered token stream—not
formatting, positions or parser diagnostics—receive the same JSON payload
information. This is **not** proof that an LLM produces an identical answer,
uses fewer future calls, or has lower complete-task usage. Independent outcomes
and whole-task measurement remain required.

JSON grammar basis: RFC 8259, particularly sections 2, 4, 6 and 7.
Primary specification: `https://www.rfc-editor.org/rfc/rfc8259.html`.
The duplicate-member caveat in section 4 is why the implementation preserves
members/ordering rather than assuming a unique parsed mapping.

## Eligibility and safety

Only older, fully paired string source results with a successful trusted-executor
receipt may change. Receipt identity binds call ID, tool name, path and the
original UTF-8 digest. Model text cannot claim that authority.

Newest results, protected prefixes, exact indices/markers, system/developer/user/
assistant messages, schemas and actual error/interruption flags remain protected.
Exact/edit/debug/unknown intents bypass V4. Words such as `"error"` inside
successfully read JSON remain data; they do not erase real failure metadata.

No original history is deleted. Storage/callback attempts are bounded by the
policy; missing counter/storage/recovery or insufficient final savings means
passthrough. V4 always uses the unaugmented original-input guard, even when a
raw-policy caller omits the older optional guard flag.

## Controller and evidence

The expanded, versioned RuntimePolicy catalog can propose local V4 directly from
true off. It need not first promote an ineffective V3 intermediate. V4 requires
the whole-input guard and cannot change caps, protected invariants, component
pins or the certification gate.

The fixed evaluation keeps six earlier ordinary cases and adds two independently
authored maintainer tasks using exact public repository JSON. No padding,
reformatting, forced repetition/order or favorable-row filtering is allowed.
Actual dispatch/outcome evidence is separate from these implementation proofs.
