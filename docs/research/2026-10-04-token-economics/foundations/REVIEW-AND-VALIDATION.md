# Review and validation scope

**October 4, 2026.**

## Independent mathematical review

A separate read-only verifier reviewed the propositions and proofs. Verdict:
**PASS under their explicit assumptions.**

The first pass checked the information collision/sufficiency arguments,
proxy-error transfer, paired concentration constants, conditional adaptive
validity, ratio bounds, non-inferiority accumulation, zero-observed-harm
bound, hill-climbing limitations, expected ROI, and total variation.

Its recommended clarifications were applied:

- History-conditional means are explicit.
- Cost bound \(B\) is positive and finite; fixed sample counts are selected
  before observing their confirmation outcomes.
- Adaptive-search ROI is conditioned on completed history.
- Nonnegative break-even and strictly positive savings are distinguished.
- Total variation uses the normalized convention and fixed conditional
  outcome functions.

A second pass checked the new anytime error-spending corollary and its
eventual-passage statement under strict margins. Verdict: **PASS**, with no
material correction required.

The second reviewed snapshot has SHA-256:

`90153cfa2415659970b3286b40e7d2159192f987dff869a0d8a109d150eb257c`

The final proof note adds only the paragraph identifying the TypeSafe
cookbook precedent. Removing that exact paragraph reproduces the reviewed
hash. The mathematical content is unchanged.

This is an independent review of written mathematics, **not Lean/Coq
machine-checked verification**, and not proof that an implementation meets
the hypotheses.

## Numerical checks

`math_checks.py` performs **35 supplementary checks** and writes
`math-checks.json`. They cover constants, error-budget sums, sample counts,
ratio/ROI arithmetic, a local-minimum counterexample, a proxy failure case,
and a small exact-projection fixture.

These checks are not empirical Jev results and are not a substitute for the
proofs. No Jev, target-model, or paid inference call was run.

## Source verification

The integration pass matched all **19 cited Jev source snapshots** to their
recorded hashes. The Jev researcher separately checked 28 downloaded
sources. The foundational-reference memo records five inspected primary
works/source collections; the original Hoeffding paper is bibliographic
provenance only because its full text was inaccessible in that research.

The incorrect initial arXiv pointer was explicitly corrected to
`2609.29769v2`; the unrelated polar-codes paper is not used as Jev evidence.
The source memo preserves the correction rather than hiding it.

## What remains unproved in the real system

- A reliable task-quality oracle for the intended production workload.
- Workload stationarity, independent confirmation, and a valid cost cap.
- Jev calibration or routing quality on TokenMaster's tasks.
- Compliance of any future optimizer implementation with the proof's data
  separation, error allocation, and promotion rules.
- Net savings after search, confirmation, inference, retrieval and maintenance.

Production files and configuration were not changed. No continuous
production optimization job was enabled.
