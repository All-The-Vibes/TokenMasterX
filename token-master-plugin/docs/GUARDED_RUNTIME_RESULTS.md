# Guarded runtime follow-up — October 9, 2026

## Latest complete matched result: repair works mechanically, overall worse

The subsequent optional-guidance-selection study completed all 12 planned runs
with **no provider failures or missing usage**. Both profiles passed all six
unchanged exposed tasks:

| Profile | Passed | Calls | Gateway-reported tokens | Full-body reference tokens |
| --- | ---: | ---: | ---: | ---: |
| True optimizer off | 6/6 | 26 | **39,854** | **87,293** |
| Actual components + repaired guard, explicit 60-second local budget | 6/6 | 27 | **41,809** | **94,810** |

Observed total difference: **1,955 more reported tokens (+4.9%)**, not savings.
The reference total was 7,517 higher (+8.6%). Do not pool this result with prior
studies that used different source versions, profiles or incomplete attempts.

| Task | Off reported tokens / calls | Repaired reported tokens / calls | Accepted transforms |
| --- | --- | --- | ---: |
| Read settings | 2,033 / 3 | 2,033 / 3 | 0 |
| Edit CSV aggregation | 6,090 / 6 | 8,153 / 7 | 0 |
| Debug timestamp ordering | 6,353 / 6 | 6,381 / 6 | 0 |
| Document rollout handoff | 3,476 / 4 | 3,476 / 4 | 0 |
| Jev/controller document handoff | 9,539 / 3 | 9,403 / 3 | 1 |
| Native/source-boundary handoff | 12,363 / 4 | 12,363 / 4 | 0 |

The single genuine changed request used **6,131 instead of 6,282 reference input
tokens: 151 directly removed**, with both task answers correct and three calls
each. That task's reported difference was 136 tokens (about 1.4%). It is one
descriptive result, not a general savings or quality certificate.

The extra edit request occurred in an untransformed protected-intent path.
It explains most of the observed total increase but is not evidence that
compression caused the extra call. Model behavior varied even on unchanged
inputs. No task is removed from the aggregate to make the result favorable.

Ponytail was configured for the treatment and used in the component-preparation
context, but its extra instructions were omitted from primary requests by the
guard. Report “configured” versus “applied” honestly. No model-requested recovery,
policy promotion, global activation or weight change occurred.

The current local prerequisite retained the earlier 20-second failure, then made
one predeclared 60/60-second local-only run. It verified the 6,288→6,140 recorded
input reduction and both recovery namespaces; its cumulative Python ONNX
inventory had 13 unique completed entries, no pending IDs or omissions at
snapshot. The run's total elapsed time was below 60 seconds, so this is **not
proof that increasing the budget caused faster or successful execution**.
Native internals and full all-in compute remain unknown.

Latest raw evidence: `evidence/integrated-runtime-20261009/elision-study/live-001/`.
Its independent audit verified **53 captures, 62 source pins and 39 installed
files**, plus 25 unique completed observed Python ONNX attempts without double
counting revision upserts. Native internals remain unknown.

The final source-stable plugin/host regression passes **3,088 tests plus 19
subtests**, with one existing Pydantic warning. This verifies software checks,
not general model-quality or efficiency claims.

## Earlier three-profile result: no task-efficiency claim

All 18 predeclared runs finished. The guard removed the earlier instruction tax,
but **every submitted request still equaled its original unoptimized input**.
There were no accepted transformations or model-requested recoveries. Differences
in outputs and call counts therefore do not establish a compression benefit.

The four earlier ordinary tasks were retained unchanged. Two independently
authored tasks used complete, exact existing repository documents; they did not
add padding or require duplicate reads. All six tasks received all three profiles
once, with balanced ordering and no selective retries.

| Explicit profile | Passed workflows | Model requests | Full-body reference tokens | Gateway-reported tokens |
| --- | ---: | ---: | ---: | --- |
| Optimizer off | 5/6 | 25 | 76,995 | Unknown total; **30,724 known** |
| Actual Headroom + input guard | 6/6 | 26 | 93,426 | **39,779** |
| Actual Ponytail + Headroom + input guard | 6/6 | 26 | 89,834 | **39,891** |

The missing off result is an upstream HTTP 503/high-demand failure, not a wrong
answer. Its missing native usage remains unknown. The higher guarded completion
count is **not evidence of a policy-caused quality improvement**.

The independent audit verified 77 captures, 59 frozen source pins and 39 installed
files. Input nonexpansion holds on every submitted request. Ponytail was
configured but its instructions were applied to **0/26** combined-profile
requests; silently calling them applied would be incorrect.

This fixed, partly exposed diagnostic is not IID or population evidence.
No gate, default, global host setting, model weight or promotion changed.
Local neural work remains separate; no all-in compute saving is claimed.

Evidence: `evidence/integrated-runtime-20261009/guarded-study/live-001/`.
Independent recount: `independent-audit.py`, `independent-audit.json`,
`independent-audit.md` inside that run.

## What the negative result exposed

On the Jev-document task, the full validated projection was **7,510 reference
input tokens**, versus **6,288** for the original. It included 1,370 tokens of
optional guidance, so the guard correctly rejected the full composition.

The independent audit reconstructed the **same projection without only that
newly inserted guidance**: **6,140 tokens**. There was a 148-token input
opportunity that the original all-or-nothing guard discarded.

This is a deterministic input reconstruction, not another model response or
proof that the smaller input produces the correct answer.

The bounded repair retains the same one-time validated/protected projection
and can consider removing exactly the newly inserted optional guidance.
Original messages and necessary recovery schemas stay intact. It accepts that
alternative only under the same strict complete-wire token/byte check; otherwise
it restores the complete original. Configured versus applied instructions and
changed indices remain explicit. The guarded profile's strategy identity changes.
Legacy flag-off behavior and registry-selection rejection remain unchanged.

Authoring tests and frozen-receipt reconstruction verified selection mechanics.
The later current-installed component and matched task evidence are reported at
the top; this earlier study is never retroactively changed.

## Actual fragment recovery is now verified

A separate fixed chronological replay preserved one task-lifetime container and
replayed all six retained cross-document inputs once. It produced three accepted
views and routed current-task references through both actual runtime handlers:

- Root: **23,925 bytes**, exactly the observed original.
- Actual upstream fragment: **1,818 bytes**, exactly the current post-task store
  content—not the complete original file.

There were zero primary submissions, one container, exact cleanup and unchanged
old evidence. This is component recovery evidence, not new task-quality or
token-efficiency evidence.

Evidence: `evidence/integrated-runtime-20261009/fragment-recovery-001/`.

## Accounting gaps found and repaired separately

Source inspection found that the old per-RPC ONNX slices could omit work starting
between RPCs or miss a later terminal update. A bounded lifetime ledger now uses
stable IDs, locked revisions, immutable snapshots and a cumulative final
inventory. Compatibility updates are **upserts, not additive call totals**.
Pending work and overflow remain incomplete; snapshot completeness is not proof
of process quiescence.

The strict container environment check also now rejects missing, changed,
duplicate or undeclared settings before starting the worker or persisting raw
environment data. It accepts the pinned public regime; it does not enable a
remote compression route or discover credentials.

These repairs do not prove all native neural work is measured. Rust detection
and embedding internals, causal attribution of background work, and complete
all-in compute accounting remain explicitly unqualified.

**The full integrated-product goal remains active.**
