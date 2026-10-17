# Integrated runtime: honest checkpoint — October 9, 2026

**Current real-model evidence:** see `NATIVE_RANGED_LIVE_RESULTS.md`. Ranged-read
support and compact Root references now activate real compression, but the
candidate fails the fixed workload: baseline **2/2** versus candidate **1/2**.
The candidate document task reread source and hit the predeclared four-call cap
without a final answer. Totals are 37,498 baseline versus 37,304 candidate
reported tokens; a lower incomplete-attempt subtotal is **not a savings result**.

The preceding no-op native comparison remains in `NATIVE_DOCUMENT_RESULTS.md`:
both 2/2, 38,127 versus 37,457 reported tokens, but no applied optimizer effect.

The earlier eight-task local-V4 result was 1.43% lower **without Ponytail or
Headroom execution** (`LEXICAL_JSON_RESULTS.md`). The earlier six-task combined
profile used **4.9% more** reported tokens (`GUARDED_RUNTIME_RESULTS.md`).
These different experiments are kept separate, and all earlier evidence below
is preserved.

## Bottom line

The installed runtime and real learning connection execute. **No tested combined
configuration has established reliable whole-task savings at preserved task
success. None is qualified for automatic use.** No default, model weight or
global host configuration was changed.

The comparison below used one predeclared pair per authored workflow. It is not
a representative workload, statistical quality certificate, or general parity
claim. Every planned run is retained, including the provider failure.

## What “baseline” means here

**Optimizer off:** the same installed runtime, gateway/model, tool definitions,
task files, limits and independent outcome checks, with no Ponytail guidance,
no Headroom reducer and no local request optimizer.

**Combined:** the actual pinned Ponytail instructions plus the actual pinned
Headroom integration. Headroom remains bypassed on protected exact/edit/debug
intents. Being configured does not mean compression ran or saved anything.

## Four ordinary workflows — all eight runs retained

Gateway-reported input plus output tokens, not monetary amounts:

| Workflow | Off: outcome / calls / tokens | Combined: outcome / calls / tokens |
| --- | --- | --- |
| Read settings | Pass / 3 / 1,952 | Upstream HTTP 503 / 2 / unknown; 1,847 known |
| Edit CSV aggregation | Pass / 6 / 5,778 | Pass / 6 / 13,519 |
| Debug timestamp ordering | Pass / 6 / 6,220 | Pass / 6 / 14,271 |
| Document handoff | Pass / 4 / 3,607 | Pass / 4 / 8,735 |
| **Entire fixed schedule** | **4/4 / 19 / 17,557** | **3/4 / 18 / unknown; 38,372 known** |

- The incomplete read task failed because the gateway reported upstream high
  demand. This is a failed end-to-end attempt, **not a wrong answer or proof of
  a policy-caused quality regression**. Its missing usage is not zero.
- All 37 request/response bodies are retained. Their separately measured
  reference totals are **57,391 off** and **82,751 combined**.
  Reference-body counts are not interchangeable with gateway-native counts.
- There were **zero accepted transformations in either arm**. Headroom actually
  executed only on the combined document workflow; its local neural work is
  separate and not assumed free or fully inventoried.
- Both edit/debug arms executed ordinary Python inside the existing isolated
  Linux boundary. The parent compared observed behavior with private expected
  results. No generated program ran on the Windows host. These finite checks
  are not a proof against arbitrary malicious or test-aware programs.
- The combined configuration's known token subtotal already exceeds the entire
  off total. Dropping the failed task or reporting its shorter run as a saving
  would be misleading.
- Independent raw audit verified all **37 captures and 50 source pins** and
  reran four isolated coding checks. No additional model inference was used.
  Same-request recounts isolate **1,370 reference input tokens of added guidance
  per combined request: 24,660 in total**. This is measured instruction overhead,
  not a forecast of model behavior after removing it.

“Calls” here means requests at the observed gateway boundary, including the
captured HTTP failure; hidden provider-internal calls are not authenticated.

The concrete efficiency problem was unearned instruction overhead: full Ponytail
guidance was added even when the reducer changed nothing. Existing per-transform
guards compared against an already augmented request, not the original off
request.

The repair is now implemented as explicit `--require-nonexpanding-input`.
An offline check of all 18 recorded combined inputs matched the old augmented
wires and restored their original unaugmented wires exactly, removing the
24,660 reference-input-token tax on those fixed inputs. It made **zero provider
requests**, did not rerun Headroom or task outcomes, and is **not a new live
savings result**. Existing defaults are unchanged. The input-only invariant and
its proof are in `PRODUCT_RUNTIME.md`.

Evidence: `evidence/integrated-runtime-20261008/ordinary-workflows-live-001/`.
The frozen plan and authored cases are in `ordinary-workflows-20261009/`.
The independent report and rerun receipts are `independent-ordinary-audit.*`
inside the live run.

## Real Jev / local-policy learning connection

A separate installed diagnostic connected the CLI, real runtime, existing
gateway, independent private checker and one real Jev screen:

| Component | Calls | Full-body reference tokens | Gateway-native tokens |
| --- | ---: | ---: | ---: |
| Enabled local incumbent | 3 | 6,467 | 1,839 |
| Local neighbor | 2 | 4,397 | 1,333 |
| Jev screen | 1 | 1,294 | Separate native units |
| **Learning inventory** | **6** | **12,158** | Not a mixed-provider sum |

Both answers were correct. Jev returned HTTP 200 and **abstained**; deterministic
proposal ordering continued. The existing gate returned `not_certified` and the
incumbent was unchanged. No policy was promoted.

Neither policy transformed a request. The candidate skipped the incumbent's
`list_files` call; that observed difference cannot establish a policy benefit.
This was an **enabled-incumbent versus neighbor** diagnostic, not the off
comparison above. The fixed exposed task is not fresh IID confirmation.

Independent audit verified raw recounts, private outcomes, unique call IDs,
unchanged installed bytes and the sealed learning inventory. Jev-native usage
was 1,712 input / 359 output, kept separate from the primary gateway's units.
No claim covers hidden provider-internal calls.

Evidence and audit: `evidence/integrated-runtime-20261008/installed-learning-001/`.

## Software verification and still-open requirements

- Full plugin/host regression: **2,861 passed + 19 subtests**, one existing
  Pydantic warning; no Python source changed during that run.
- The final combined learning-path check passed **157 tests**, also with
  unchanged sources. This overlaps the full suite; do not add the counts.
- Follow-on typing corrections passed 164 targeted checks and clean static
  analysis. The composition-guard authoring slice passed 68 tests, including
  29 new cases. These overlap other checks and are not added to the full count.
  Parent cross-module regression then passed **264 tests**, followed by
  **108 applicable checks** after a final typing cleanup. Strict MyPy across
  seven involved entrypoint/modules and Ruff pass. A separate reviewer found no
  blocker in the guard or unknown-usage preservation.
- The final recorded-input replay is `composition-input-replay-002/`; its
  pre-cleanup predecessor is retained. Both made zero provider calls and
  neither is live task-savings evidence.
- Earlier document failures remain failures. Their accepted projections and
  exact full-original recovery are mechanism evidence, not savings.
- The separate upstream-fragment handler probe did not exercise retrieval:
  the fresh projected view failed the final-wire guard. It made zero primary
  provider requests, recorded local neural activity, and cleaned its owned
  container. Do not claim handler qualification from it.
- Broader/native-host routing, task-quality-preserving efficiency, complete
  all-in overhead coverage and release qualification remain open.

**The corrected goal remains active, not complete.**
