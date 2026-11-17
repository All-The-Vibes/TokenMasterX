# Certification planning: check before spending calls

**A read-only planning check, not a certificate or permission to run.**
It applies the registry's own quality/token rule unchanged: the strict rule,
or the quality margin and token test the registry was created with. This
command exposes when a proposed fixed-size trial cannot pass even under the
most favorable bounded observations.

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

The strict gate allocates round error and a finite-sample radius as:

\[
\alpha_k=\frac{6\alpha}{\pi^2k^2},
\qquad
r=\sqrt{\frac{2\log(2/\alpha_k)}{n}}.
\]

Let \(\bar X\) be the mean candidate-minus-incumbent binary quality difference,
\(D\) the mean incumbent-minus-candidate token saving, \(B\) the declared
per-task token cap, and \(\eta>0\) the required mean token reduction.
The strict gate requires:

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
equal, \(\bar X=0<r\), so **no finite equal-observed-quality trial passes the
strict rule**, regardless of observed token saving. A quality margin changes
this (next section).

For \(\alpha=.05,\ k=1,\ B=100{,}000,\ \eta=1\), eight pairs are impossible:
\(r\approx1.02306>1\). Nine pairs are algebraically not ruled out.
**Nine is not a recommended study size:** it would require extreme quality and
token improvements. The bound is not statistical power, attainable outcomes,
freshness, task independence or likely certification.

## Margin and bet registries

A registry created with `--quality-margin` or `--token-test max-bet-v1`
(`PROFILE_LEARNING.md`) gets a report for its own gate. The snapshot reads both
settings from the stored configuration; this command has no flag for them.
The report keeps every default key and adds `quality_margin`, `token_test`,
`max_passing_harms`, `equal_quality_minimum_samples` and
`token_minimum_samples`. `gate` names the registry's label,
`controller_sample_limit` is 4,000, and a proposal above 4,000 tasks is refused
with `gate_sample_limit_exceeded`.

- Quality margin \(\delta\): the exact harm count replaces the strict quality
  side. `max_passing_harms` is the largest harm count (tasks the incumbent
  passes and the candidate fails) that passes at \(n\), or null if none does,
  and `equal_quality_minimum_samples` is the smallest \(n\) at which zero harms
  pass. `required_mean_quality_difference` is null, `best_case_quality_lower`
  is \(-\delta\) when zero harms pass at \(n\) and \(-1\) otherwise, and
  `equal_observed_quality_can_pass` is true when some harm count passes. At
  round 1 with \(\alpha=.05\), \(\delta=0.10\) needs 40 tasks and allows at most
  3 harms at \(n=100\) and 5 at \(n=128\); \(\delta=0.05\) needs 82 tasks and
  allows 1 harm at \(n=128\).
- `max-bet-v1`: the exact fixed bet replaces the Hoeffding token side.
  `token_minimum_samples` is the smallest \(n\) at which every task saving
  \(B\) passes (7 at round 1 with \(B=100{,}000\) and \(\eta=1\), 9 at round 2).
  `required_mean_token_saving` is the smallest whole saving that passes when
  every task saves it: 3,326 at \(n=128\), against \(\eta+Br\), about 25,577,
  under Hoeffding. `best_case_normalized_token_upper` is \(-\eta/B\) when that
  best case passes and 1 otherwise.
- Without a margin the quality side stays strict, so a bet plan at round 1
  still needs 9 tasks.

`minimum_samples` is the larger of the quality and token minimums, for example
40 at \(\delta=0.10\) under either token test, with `minimum_samples_reason`
`larger_of_quality_and_token_minimums`. `status` is `mathematically_impossible`
if either side is, else `numerically_indeterminate` if either side is, else
`not_ruled_out`. The harm and bet sides are exact and add no numerical
limitation. A snapshot for a proposed trial uses the next round, so after one
trial a \(\delta=0.10\) registry reports at most 4 passing harms at \(n=128\).

## Numerical honesty

The implementation reuses the existing `radius`/`round_alpha` functions.
It computes the margin with exact rational arithmetic, then checks the rounded
sample-floor candidate and predecessor using the actual floating-point gate.
Cases near the boundary, reduction-ratio underflow, unsupported integer sizes
or allocation underflow are explicitly reported. The harm count and the fixed
bet are decided exactly in integers, as the gate decides them; their minimums
are searched up to 4,000 tasks.

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
not reinterpreted or silently re-certified. This check changes no quality
margin, token test, token threshold, error budget, stored identity or old
outcome; a registry's margin and test are fixed when it is created.

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
