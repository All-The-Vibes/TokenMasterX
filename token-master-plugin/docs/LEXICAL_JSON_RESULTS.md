# V4 ordinary-workflow diagnostic — October 9, 2026

## Full workload, not only favorable cases

The production controller evaluated true off versus its direct local-V4
neighbor on eight fixed tasks. Six prior ordinary tasks were unchanged; two
independently authored tasks used exact public repository JSON.

| Policy | Correct outcomes | Model requests | Gateway-reported tokens | Full-body reference tokens |
| --- | ---: | ---: | ---: | ---: |
| True off | **8/8** | **32** | **58,156** | **121,939** |
| Local V4 | **8/8** | **32** | **57,323** | **120,472** |

Observed difference over the entire workload:

- **833 fewer gateway-reported tokens: 1.43% lower.**
- **1,467 fewer reference tokens: 1.20% lower.**
- No missing usage, failed task, selective retry or omitted case.
- No Jev, Ponytail or Headroom execution in this comparison. It tests the local
  deterministic policy available within the same integrated runtime/controller.
- No automatic promotion. The unchanged strict gate returned `not_certified`.

These are fixed/exposed diagnostics, not IID or representative production
evidence. This result does not establish a general improvement or override the
older 4.9%-worse study with a different profile/workload.

## Every task

All rows passed in both arms. Counts include every request through the declared
boundary, including complete model outputs.

| Task | Off tokens / calls | V4 tokens / calls | Accepted changes |
| --- | ---: | ---: | ---: |
| Read settings | 2,033 / 3 | 2,033 / 3 | 0 |
| Edit CSV aggregation | 5,969 / 6 | 5,951 / 6 | 0 |
| Debug timestamp ordering | 6,351 / 6 | 6,430 / 6 | 0 |
| Document rollout handoff | 3,476 / 4 | 3,476 / 4 | 0 |
| Jev/controller handoff | 9,539 / 3 | 9,539 / 3 | 0 |
| Native/source-boundary handoff | 12,363 / 4 | 12,363 / 4 | 0 |
| Windows JSON maintainer handoff | 9,495 / 3 | 8,865 / 3 | 1 |
| libc/SDK JSON maintainer handoff | 8,930 / 3 | 8,666 / 3 | 1 |

Differences on unchanged inputs are model/output/identifier variation; do not
credit them to compression. The JSON-task subtotal is not substituted for the
full-workload comparison.

## Direct, deterministic input effect

The two changed requests used complete compact JSON payloads plus exact original
recovery references. No member/item/string/number was sampled or reserialized.

| Changed request | Original reference input | Final reference input | Direct removal |
| --- | ---: | ---: | ---: |
| Windows maintainer, request 3 | 6,588 | 5,663 | **925** |
| libc/SDK maintainer, request 3 | 5,073 | 4,646 | **427** |
| **Total on those fixed inputs** | | | **1,352** |

These figures include recovery annotations and the complete transport envelope.
They are not the same metric as gateway-native counts or total output/call
behavior. The full annotated tool string is not standalone JSON; its payload is
lexically preserved, and the original bytes remain recoverable.

The six original controls had no accepted transformation. Newest/exact/edit/debug
protections were not relaxed, and no extra read was required to activate V4.
Neither arm requested recovery during this run.

## Controller and claim boundaries

The actual `Optimizer.freeze/evaluate` path reserved all eight pairs in one
intact registry. The 160 reserved slots are capacity, not observed calls; the
host also enforced the original per-case bounds. There were 64 observed primary
calls across both arms and **242,411** complete-body reference tokens of learning
work. Verification used private JSON checks and the existing isolated Python
behavioral checks, not model self-grading.

The strict zero-regression statistical gate remains unchanged. Equal observed
successes on eight exposed cases cannot supply its population assumptions or
its finite-sample lower bound. `not_certified` is therefore retained, not treated
as permission to weaken the gate.

No monetary conversion, model-weight update, default activation, global host
change, new dependency or general all-in compute claim is made.

Evidence:
`evidence/integrated-runtime-20261009/lossless-json/live-001/`.
Frozen contract/inputs and the independently authored source/gold are in the
parent `lossless-json/` directory.

The independent raw audit verified **64 captures, 26 source pins and 41 installed
files**, saved private outcome checks and all eight durable observations. It
independently compared payload lexemes, checked exact original SQLite root bytes
read-only, and confirmed databases/leases were unchanged.

The deterministic input effect is **1,352 reference tokens**. The remaining
115-reference-token difference and changes on untransformed controls are not
credited to V4. The audit confirms zero recovery, advisory or local-neural calls
in this study, the unchanged off incumbent and `not_certified`.
Final software regression passed **3,476 tests plus 19 subtests**, with one
existing Pydantic warning and no Python source drift. Ruff and strict MyPy pass
for the changed implementation. Those software checks do not establish
repeatability, fresh/IID sampling or production-wide savings.
