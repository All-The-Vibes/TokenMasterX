# Measured comparator and retention results

> **Historical comparator results below.** The subsequent
> [conservative V3 repair](CONSERVATIVE_POLICY_FIX.md) matches baseline on the six
> reading questions and reduces task tokens by 9.9% on four deliberate
> repeated-read probes. That is not a new competitor-parity or production claim.
> The earlier [four-configuration scorecard](CONTROLLED_SCORECARD.md) retains
> all 120 audited runs and its unsuccessful retained-two candidate.
> Do not mix percentages or accounting boundaries across these studies.

October 8, 2026 UTC. **These are bounded exploratory results, not production
parity, a general savings percentage, or a statistical promotion certificate.**
No prices, model-weight changes or normal host-profile changes were involved.

## Matched mechanism repeats: the recovery effect survives clearer tools

Three further paired repeats reused the **already-exposed installed-demo case**,
with the clarified recovery instructions in both arms and predeclared order
seeds 0, 1 and 2. These are mechanism checks, not fresh holdout or population
confirmation.

| Repeat | Correct, both arms | Calls, retain 1 → 2 | Reference tokens, retain 1 → 2 |
| --- | ---: | ---: | ---: |
| 1 | 1/1 | 5 → 3 | 39,314 → 20,434 |
| 2 | 1/1 | 5 → 3 | 39,410 → 20,406 |
| 3 | 1/1 | 5 → 3 | 39,286 → 20,373 |
| Total | 3/3 | **15 → 9** | **118,010 → 61,213** |

Every incumbent run made **two genuine `retrieve_original` calls** after the
initial two file reads. Every candidate run retained both original results and
answered after those same initial reads. There were no wrong Headroom-tool
calls or `fetch_artifact` workarounds. Thus the observed recovery overhead is
not explained solely by the earlier tool-name confusion.

The candidate still did not compress these two recent results. The local
mechanism is **avoiding unnecessary lossy views and their recovery overhead**,
not compressing more aggressively. All six outcomes remained correct.

The fixed batch retains all three repeats; no failed run was replaced.
`evidence/retention-mechanism-20261008/offline-audit.json` rechecks frozen
sources, raw counts, outcomes, identical paired first requests and observed
tool sequences. This supports repeatability on one selected case only.
No population interval, automatic promotion or Jev-caused benefit is claimed.

## Latest replication: no new savings evidence

The recovery-tool descriptions were clarified equally in both arms: TokenMaster
`[[BR:...]]` references belong to `retrieve_original`, while Headroom markers
belong to `headroom_retrieve`. Schemas and recovery implementations were not
changed or silently cross-routed.

Four new independently prepared questions then compared the same retained-1
and retained-2 policies. Six of eight source files were previously unused;
two overlap the earlier retention corpus. This is question novelty, not a claim
of complete source or statistical independence.

| Policy | Correct | Calls | Primary reference tokens | Bridge-reported tokens |
| --- | ---: | ---: | ---: | ---: |
| Retain one | 4/4 | 12 | 62,072 | **35,418** |
| Retain two | 4/4 | 12 | 62,041 | **35,418** |

**Neither policy transformed any request in that fresh-task replication.** There were no
recovery calls. The 31-reference-token difference is captured output/metadata
variation, not policy savings. This run **does not replicate the earlier 37.4%
effect on new tasks**, nor does an inactive comparison disprove that mechanism.

All eight attempts are retained, including readiness: **25 primary attempts /
125,257 reference tokens**. The frozen-source parent audit regraded all eight
outcomes, checked 48 source hashes and identical first-request pairs, and
confirmed that guidance changes preserve common schemas.

Evidence: `evidence/parity-agent-comparison-20261008/recovery-replication-001/`
and `recovery-replication-parent-audit.json`.

## Same-boundary four-arm comparison

Six independently prepared, source-backed coding/document tasks were run in
each arm. All 24 planned runs are present. Source fixtures came from TokenMaster
commit `426fc853389ddba4bc6e1dd35a28179a895c064f`, not invented padding.
The model label, tools, task inputs, limits and original-client-history
convention were shared. Instructions/transforms differed only by declared arm:

- **Baseline:** common instructions and tools, no optimization.
- **TokenMaster:** scoped-task instructions and source-aware v2 request views.
- **Ponytail:** actual pinned `getPonytailInstructions("full")` export.
- **Headroom:** actual pinned public request pipeline, warmed local model, and
  actual upstream CCR handler in a fresh isolated process per task.

| Arm | Correct | Primary calls | Primary API-body reference tokens |
| --- | ---: | ---: | ---: |
| Baseline | 5/6 | 23 | 164,264 |
| TokenMaster | **6/6** | 28 | **224,150** |
| Ponytail | **6/6** | 23 | **195,335** |
| Headroom | 5/6 | 22 | 150,253 |

**TokenMaster did not win this comparison.** Ponytail achieved the same observed
6/6 correctness with fewer calls and fewer reference tokens.

The failures are different and remain counted:

- Baseline answered `graphify-nav` rather than `graphify` for the default backend
  in one document-contract field. The other fields matched.
- Headroom's exact-source task stopped on a captured adapter error reporting
  upstream HTTP 502 / WinError 10054. Its lower total is therefore not the cost
  of six successful completions. Aggregate bridge-reported usage for Headroom
  is unknown, not zero.

TokenMaster made **five model-requested original-retrieval calls** in two trace
tasks: three complete files and two exact function/body fragments. Its views
removed useful detail that the model then fetched again. This observed
trajectory explains the extra calls; it is not a universal causal estimate.

Headroom's primary model made no retrieval calls in this study. Its post-task
audits recovered 22 exact **fragments**, not whole files. Those audit reads
occurred after the primary task ended so they could not change the observed
retrieval-feedback policy.

### Counting and verification boundaries

The primary measurement is pinned `cl100k_base` over complete captured primary
API JSON bodies. It includes schema/instruction/response metadata and is not
authenticated model-serving usage. Internal Headroom estimates for
`gpt-6-astra` were not substituted for that measurement.

All arms received the same eight tool schemas, including both recovery tools.
This is an explicit shared-harness experiment, not a comparison of native
Desktop installations. Headroom's AST path stayed default-disabled; optional
semantic relevance was not silently enabled. Local Python ONNX activity and
startup time were recorded separately; native detector inference is not fully
inventoried. Cross-runtime wall times are descriptive, not isolated algorithm
speed measurements.

The 96 task calls account for 734,002 reference tokens. Readiness adds one call
and 1,119 tokens: **97 attempts / 735,121 primary-reference tokens**.

An independent audit verified 42 frozen source hashes, all 24 outcomes, 192
input/output counts and hashes, the source gold, control/history differences,
seven Headroom worker identities/cleanup receipts and 29 RPC pairs. Its local
tokenizer library was 0.12.0 rather than the run's 0.14.0, using identical
verified vocabulary bytes; every stored count matched. That is an independent
recount, not a full dependency replay.

Evidence:
`evidence/parity-agent-comparison-20261008/live-001/` and
`independent-study-audit.md`.

## Jev screening and bounded neighbor search

The existing user-supplied credential was used process-locally for **one**
authorized Jev call containing sanitized metrics and valid policy neighbors.
It returned HTTP 200 and **abstained**. It did not recommend the later candidate
and did not certify quality.

That screening call consumed **1,260 reference learning tokens**, separately
from **2,065 vendor-reported tokens**. Public request/response bodies, hashes and
a sealed learning inventory were retained without the credential.

The deterministic fallback then replayed all 28 incumbent request histories.
All incumbent requests reproduced exactly. Four neighbor settings changed no
request. The only activating neighbor was:

```text
keep_recent_tool_results: 1 -> 2
```

It changed five recorded requests and retained 1,314 additional input reference
tokens on those same trajectories. That audit did **not** predict whole-task
savings: retaining more input can be worthwhile only if it avoids later work.
The candidate was frozen before the parent inspected the independent holdout.

Evidence: `jev-retention-screen/`, `neighbor-activation.json`, and
`retention-candidate.json` under the same evidence root.

## Fresh retention holdout

Four independently prepared, source-disjoint tasks compared the incumbent with
that one neighbor. Instructions, tools, model, budgets and all other policy
fields remained the same.

| Policy | Correct | Primary calls | Primary reference tokens | Bridge-reported tokens |
| --- | ---: | ---: | ---: | ---: |
| Keep one recent result | **4/4** | 15 | **100,149** | 66,918 |
| Keep two recent results | **4/4** | 12 | **62,649** | 37,306 |

The observed difference is **37,500 fewer reference tokens (37.4%)** in this
small holdout. **Do not advertise it as typical savings.** Nearly the entire
difference came from one activated two-file trace:

- The incumbent compressed earlier evidence, called the wrong recovery tool
  (`headroom_retrieve`), then fetched both source files again through
  `fetch_artifact`.
- The candidate retained the two originals and answered after the initial
  reads. It did not invoke a recovery tool.
- The other three cases had no transformations; their bridge-reported totals
  were identical. Tiny reference differences reflect different captured
  outputs/metadata, not a demonstrated policy effect.

The shared recovery-tool inventory contributed an ambiguity in that observed
incumbent trajectory. This is a real result under the declared harness, not
proof that the same magnitude will hold in a TokenMaster-only native setup.
Nor is it evidence of Jev-caused improvement: **Jev abstained; the candidate
came from the deterministic fallback.**

This study made **28 attempts including readiness**, with **163,929 primary
reference tokens**. Earlier search, verification and Jev learning are additional
overheads; no net project-wide learning savings are asserted.

Evidence: `evidence/parity-agent-comparison-20261008/retention-live-001/`.

## Decision

Keep the successful neighbor as an **opt-in tested candidate**, not a promoted
default. The strict joint quality/token gate is unchanged. These small,
purposively selected trials do not qualify for a population certificate.

The remaining requirements are broader behavioral/depth qualification,
unqualified native Windows/Desktop/locked-runtime cells, representative
replication of the comparator results, and independently demonstrated utility
from advanced Jev screening. The implementation goal remains incomplete.
