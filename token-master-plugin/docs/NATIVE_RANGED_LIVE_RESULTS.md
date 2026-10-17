# Repaired native profile: real-model result — October 9, 2026

**The candidate failed this fixed workload. It is not a successful token-saving
configuration.** Optimization now actually activates, but the document task
requested another file read and exhausted its fixed call budget without
producing a final answer.

## Same workload and limits

The exposed corpus, prompts, public files, private checker, model, low reasoning,
2,048-token output limit, four-call per-task cap and balanced order were frozen
before inference. Both configurations used the same new
`native-view-result-v2` adapter and native recovery schemas.

- **Baseline:** optimizer off; no local reducer, Headroom or Ponytail guidance.
- **Candidate:** guarded configured Headroom document mode, actual pinned
  Ponytail selection, compact exact-root references and 60-second cooperative
  Headroom budget. Configured instructions are not automatically applied.

Plan SHA256:
`9cc7e8c466820c462dbb0469fab6579e10c83b206390d35710138cc33cd8517f`.
No selective retries, extra allowance, registry reset, Jev screen or promotion.

## Every attempted task

Reported tokens are complete observed gateway input plus output; not money.

| Task | Baseline result / calls / reported tokens | Candidate result / calls / reported tokens |
| --- | --- | --- |
| Document handoff | Pass / 4 / 22,889 | **No final answer; call cap reached** / 4 / 22,701 |
| Exact source reading | Pass / 3 / 14,609 | Pass / 3 / 14,603 |
| **Entire two-task workload** | **2/2 complete and correct / 7 / 37,498** | **1/2 complete and correct / 7 / 37,304** |

All four planned attempts are retained. The incomplete candidate's known usage
is included, not discarded or treated as zero. The 194-token lower subtotal is
**not a saving at equal task success**.

Readiness is separate: **one call, 3,438 reported tokens**. The complete
experiment used **15 model requests and 78,240 reported tokens**, plus one
locally rejected fifth request in the candidate document session that was not
sent to the model.

Reference-body counts are separate: **51,815 baseline task tokens; 51,461
candidate task tokens; 5,212 readiness tokens**. These are not added to gateway
usage and do not authenticate hidden serving/native-internal work.

## What actually happened

The candidate read the answer schema, the filesystem guide and the installation
guide. Its fourth model request contained one accepted compression of the
older filesystem guide:

| Complete fourth-request input | Reference tokens | UTF-8 bytes |
| --- | ---: | ---: |
| Unaugmented original | 8,650 | 37,709 |
| Submitted compressed request | 8,543 | 37,073 |
| **Direct reduction** | **107** | **636** |

That reduction includes the compact Root reference and complete native wire.
Ponytail was omitted by the guard, so it is not credited for this result.

The fourth model response did not answer. It requested a native `view` of
filesystem-guide lines **62–100**. That read succeeded. The client then asked
for a fifth model request, which exceeded the predeclared four-call cap and
was rejected locally. There is no final answer or grading artifact for that
attempt; it must not be called an incorrect final answer or a provider outage.

There were no explicit Root/vendor recovery tool calls. **There was an
additional ordinary source read**, which is distinct from a recovery-tool
counter of zero.

## Evidence-fidelity diagnosis

The saved compressed guide removed the config-table structure and the ordered
model-catalog search list, including the prose explaining that providers check
both locations in order. The extra requested range contains that section.
The public question explicitly requires the documented search order.

This is a concrete structural information loss and a matching subsequent
read request. It does **not** establish causation from one pair, prove why the
model chose to reread, or show whether another request would have yielded a
correct answer. No additional call is made to find out or replace the failure.

Exact byte recovery and a nonexpanding input do not imply equivalent task
quality. Even this small input reduction was not useful within the declared
whole-task budget.

## Interpretation and next boundary

Keep this candidate opt-in and unpromoted. Do not increase the finished study's
cap, delete the failure, change the oracle, force a read order or substitute a
component-only reduction for the workload outcome.

The next implementation needs source-backed treatment of task-relevant
relations—especially tables and ordered evidence—before another efficacy
experiment. Any preservation invariant must state what it actually proves;
neither word overlap nor exact recovery alone proves semantic equivalence.

This is one exposed, authored pair per task, not fresh IID confirmation,
repeatability, a population-quality estimate or a production certificate.
The earlier V4-only 1.43%-lower result, combined 4.9%-worse result and no-op
native diagnostic remain separate.

Evidence:
`evidence/integrated-runtime-20261009/native-ranged-results/live-runs/live-001/`.
The independent raw audit passes the accounting/retention claim and confirms
the candidate's failed workload result. It recounts all 15 captures, regrades
all three complete task answers, verifies zero applied Ponytail instructions,
and checks all **1,376 original run files unchanged**. No further inference
was used. Cleanup is verified from retained receipts, not fresh process probes;
local/native-internal compute coverage remains incomplete.

`failure-diagnosis.json` records exact ordered-list/table checks and the extra
read; `DESIGN_LIMITS.md` distinguishes the valid equal-budget negative outcome
from unproved general quality or causal effects.

The protocol qualification and software regression remain valid for their own
narrower claims; they do not turn this negative live result into success.
