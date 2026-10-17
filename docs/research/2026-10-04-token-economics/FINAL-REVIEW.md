# Integration review

**October 4, 2026.**

An independent read-only verifier reviewed the economic model, local probe
claims, source provenance, selected paper/project attributions, and validation
limitations.

Two material methodology issues were found and corrected:

1. The proposed release gate now requires the **upper** confidence bound of
   candidate-minus-baseline cost to be below zero, not merely a favorable lower
   bound.
2. Additional compression/tool/indexing costs explicitly exclude model calls
   already counted in the normalized usage ledger. Shared model-based work is
   allocated once.

The verifier subsequently reported both findings resolved. The fresh test
rerun also records exact interpreter/command/environment provenance in
`pytest-baseline-run.json`. It remains **110 passed / 10 failed** in the
dependency-limited environment; it is not a green full-suite claim.

The literature appendix was clarified after a primary-source spot check:
the favorable timing examples in *Prompt Compression in the Wild* are
compressor-inclusive time-to-first-token experiments with one generated token,
not full-task speedups. Differing abstract/body/retrieval figures are flagged
rather than merged into one headline.

The integration validator additionally detected that the OSS report's original
hash represented LF-normalized text while the saved file used CRLF. Both hashes
are now explicitly preserved in `oss/validation.json`; no report content was
changed to make the hash match.

`validation.json` records 21 artifact/consistency checks, source hashes, and
limitations. These checks do not establish live host compatibility, billed
savings, production security, or model answer quality.

No production source was edited, no dependencies were installed, and no paid
model evaluation was run in this main research lane. The separately created
parity chat has its own report, upstream probes, and validation.
