# Certification planning: check before spending calls

**A read-only planning check, not a certificate or permission to run.**
The strict quality/token rule is unchanged. This command exposes when a
proposed fixed-size trial cannot pass even under the most favorable bounded
observations.

```powershell
python token_efficiency.py --db REGISTRY plan-feasibility --samples 8
python token_efficiency.py --db REGISTRY plan-feasibility --samples 8 --screening
python token_efficiency.py --db REGISTRY plan-feasibility --trial-id 1
```

The entrypoint is
`token-master-plugin/skills/token-master/token_efficiency.py` in this repository,
or the copied `token_efficiency.py` inside an installed package.
`--screening` budgets one declared advisory call; it does not invoke Jev.
An existing-trial report uses its actual saved round and does not re-evaluate it.
Exit zero means the diagnostic completed, not that a trial may run. Read the
arithmetic/allocation statuses and the explicit `authority=false` field.

## Necessary-condition proof

The existing gate allocates round error and a finite-sample radius as:

\[
\alpha_k=\frac{6\alpha}{\pi^2k^2},
\qquad
r=\sqrt{\frac{2\log(2/\alpha_k)}{n}}.
\]

Let \(\bar X\) be the mean candidate-minus-incumbent binary quality difference,
\(D\) the mean incumbent-minus-candidate token saving, \(B\) the declared
per-task token cap, and \(\eta>0\) the required mean token reduction.
The unchanged gate requires:

\[
\bar X\ge r,\qquad D\ge\eta+Br.
\]

Binary outcomes imply \(\bar X\le1\). Nonnegative task token totals bounded by
\(B\) imply \(D\le B\). Hence even the best allowed scalars cannot pass unless:

\[
r\le1,\qquad r\le1-\eta/B.
\]

For \(0<\eta<B\), the second inequality is stronger. Squaring and rearranging
positive quantities gives the necessary sample floor:

\[
n\ \ge\
\left\lceil\frac{2\log(2/\alpha_k)}{(1-\eta/B)^2}\right\rceil.
\]

If \(\eta=B\), no finite \(n\) suffices because \(r>0\). If observed quality is
equal, \(\bar X=0<r\), so **no finite equal-observed-quality trial passes this
particular rule**, regardless of observed token saving.

For \(\alpha=.05,\ k=1,\ B=100{,}000,\ \eta=1\), eight pairs are impossible:
\(r\approx1.02306>1\). Nine pairs are algebraically not ruled out.
**Nine is not a recommended study size:** it would require extreme quality and
token improvements. The bound is not statistical power, attainable outcomes,
freshness, task independence or likely certification.

## Numerical honesty

The implementation reuses the existing `radius`/`round_alpha` functions.
It computes the margin with exact rational arithmetic, then checks the rounded
sample-floor candidate and predecessor using the actual floating-point gate.
Cases near the boundary, reduction-ratio underflow, unsupported integer sizes
or allocation underflow are explicitly reported.

`not_ruled_out` is weaker than “feasible in practice.” Numerical ambiguity is
not rounded into permission or a passing certificate. The log calculation
uses binary64, not a rigorous interval evaluation of transcendental functions.

## Separate allocation and authority checks

The report reads the original registry configuration, exact existing trial or
next AUTOINCREMENT round, consumed candidate slots, baseline reservations,
screening slots and trial reservations. Failed and abandoned reservations stay
spent. For a proposed new trial it reports:

\[
n_{\mathrm{affordable}}=
\left\lfloor
\frac{\mathrm{maxCalls}-\mathrm{allocatedSlots}-\mathrm{screenSlot}}
{\mathrm{callsPerPair}}
\right\rfloor,
\]

bounded by the existing controller sample limit and zero when nothing remains.
These are reserved call slots, not a recount of model calls actually executed.
An existing trial requests no new allocation; that must not be read as authority
for another trial.
Its validated frozen comparison and original incumbent/candidate are reported
separately from the current champion, including an explicit unknown version if
that historical field is unavailable. Typed canonical JSON comparisons reject
boolean/integer/float substitutions rather than relying on Python's coercive
dictionary equality.

Budget, candidate availability, freshness and native comparability are separate.
The latter two remain **UNVERIFIED** by this command.

The snapshot never constructs a controller, migrates a schema, creates a missing
database, checkpoints a WAL, reserves a task or resets spending. WAL, SHM and
rollback-journal sidecars cause explicit refusal. For sidecar-free files it uses
read-only immutable SQLite access and before/after file identity/digest checks.
Ordinary concurrent changes reject without retry. It is not a lock or protection
against hostile change-and-restore, and guarantees no future allocation.

## Effect on new learning commands

New nonsynthetic `learn-runtime` and `learn-profile` calls perform this check
before constructing a Jev screener, opening the mutable controller, freezing
a trial or consuming task IDs. Hard-impossible and numerically indeterminate
plans reject; existing allocation/admission and certification checks remain
authoritative. A second snapshot detects intervening changes before dispatch.

Synthetic demo/confirmation commands and existing-trial evaluation/replay are
not reinterpreted or silently re-certified. No quality margin, token threshold,
error budget, stored identity or old outcome is changed.

## Verified existing-registry result

The read-only command was run against the two existing goal-documented
registries, without creating a new one:

| Registry | Proposed eight-pair arithmetic | New allocation | Candidate capacity |
| --- | --- | --- | --- |
| V4 eight-pair registry | Impossible at next round 2 | Exhausted, 160/160 slots | Unavailable |
| Earlier profile-learning registry | Impossible at next round 3 | Exhausted, 17/17 slots | Unavailable |

Both saved first trials are also arithmetically impossible under their original
round/sample settings. Before/after bytes, size, modification/creation metadata
and absent sidecars match. The command made no inference or Jev call.

Evidence:
`evidence/integrated-runtime-20261009/plan-feasibility/existing-registry-readonly-002/`.
The prior `-I` invocation failed before imports because that mode removes the
script directory from Python's import path; it is retained in `...-001/`, with
unchanged databases. The supported script invocation uses ordinary package
resolution, not a source or gate workaround.

This check prevents known-unwinnable spending. It does **not** resolve native
initial-request comparability, create fresh evaluation tasks, replenish either
registry, establish useful savings or finish the full integrated-runtime goal.
