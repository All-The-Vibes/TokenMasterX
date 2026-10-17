# Full-runtime policy learning

**Experimental and opt-in.** This extends the existing controller; it does not
replace its quality gate, reset its budgets, or enable a policy globally.
A bounded installed live check has completed; broad qualification remains open.

## What was missing

`initialize-runtime` / `learn-runtime` compare enabled local `RequestPolicy`
neighbors. They cannot represent an optimizer-off baseline or choose actual
Headroom/Ponytail compositions. Those commands retain their existing meaning.

The new, separately named `initialize-profile` / `learn-profile` commands use
`RuntimePolicy`. Its default is **true optimizer off**: no reducer and no
Ponytail instructions. Instruction-only, local and Headroom configurations are
distinct; “configured” does not imply that an instruction or transform was
actually applied.

## Closed policy data and explicit resources

`RuntimePolicy` contains:

- One backend: `none`, `local`, or `headroom`.
- A nested validated `RequestPolicy`, enabled only for the local backend.
- No guidance or the actual pinned Ponytail instruction component.
- The known composition guard and optional bounded Headroom time budget.
- Fixed execution/component identities.

There are no commands, imports, resource paths, credentials or arbitrary plugin
names in policy JSON. Inactive settings are validated, not silently repurposed.
Neighborhoods are finite and deterministic; they cannot alter the model, oracle,
measurement, safety invariants, component pins or wire caps.

`RuntimeResources` separately binds an explicitly supplied Ponytail export,
Headroom cache and asset receipt. Its portable identity contains content
identities, not machine-specific paths or instruction text. It validates exact
asset sizes/digests and confined cache links; it does not download, warm a model
or discover credentials. The actual checked worker validates its mapped assets
again. Resource checks are not an atomic defense against a hostile filesystem
writer; the host must keep the inputs read-only.

Legacy `RequestPolicy` serialization/IDs, neighbor ordering, optimizer config
serialization and registry schema remain unchanged. The controller dispatches
only the two known policy types and rejects mixed-family trials/history.

## One real execution and accounting path

`RuntimeSession(runtime_policy=..., runtime_resources=...)` derives its actual
execution settings from that policy. Separate legacy composition overrides are
rejected. The policy ID is assigned **before** session receipts or calls; no
captured trace is relabeled afterward.

`ProfileLearningManifest` freezes the resource identity and profile catalog in a
separate versioned regime. The existing `RuntimePairEvaluator` constructs and
readies both selected components before either primary arm runs, then reuses
those exact sessions/workers. Missing resources cannot become a local/off
fallback or silently penalize only the second arm.

The existing checker and complete capture recount remain authoritative. Headroom
profiles require a complete observed Python ONNX inventory at the declared
snapshot. This does not certify native detector/embedding internals or hidden
provider computation. Those units are not added to reference tokens.

Failed/interrupted work must preserve native IDs, known costs, component
receipts and exact owned cleanup. Cleanup attempted is not the same as cleanup
settled. No controller/evaluator path retries primary inference to replace a
failed task.

## User-facing commands

Argument outline (not multiline shell syntax):

```text
token_efficiency.py --db NEW_DB initialize-profile
  --manifest TASKS_JSON --output NEW_ADMISSION_DIRECTORY
  --base-url LOOPBACK --model MODEL --allow-network
  --ponytail-export PINNED_EXPORT
  --headroom-cache EXISTING_CACHE --headroom-assets VERIFIED_RECEIPT

token_efficiency.py --db SAME_DB learn-profile
  --manifest SAME_TASKS_JSON --output NEW_TRIAL_DIRECTORY
  --base-url SAME_LOOPBACK --model SAME_MODEL --allow-network
  --ponytail-export SAME_EXPORT
  --headroom-cache SAME_CACHE --headroom-assets SAME_RECEIPT
  --task-id CONTENT_DERIVED_TASK_ID
```

Use initialization's task IDs. A batch repeats `--task-id`. Keep common options,
source versions and resource identities fixed. Reused tasks and exhausted
budgets are rejected before screening; final transactional checks remain.

- Optional `--policy FILE` on initialization selects an explicit RuntimePolicy;
  omission is true off. Admission exercises materialization with primary
  transport disabled. It is **safety-only, not model-quality evidence**.
- Optional `--jev` makes one advisory policy-settings-only screen using an
  already configured `TYPESAFE_API_KEY`. Task source and private gold are not
  sent. Abstention/failure retains deterministic ordering, with overhead counted.
- Optional `--candidate-id ID` instead selects one already-proposed neighbor.
  It cannot be combined with Jev, bypass neighbor membership, or supply a
  certificate. The choice is recorded before evaluation.
- Neither learning command promotes. Existing explicit `promote`/`rollback`
  operations still read the registry's actual evidence and enforce its gates.
- Full-profile CLI resources are explicit so the search space cannot quietly
  shrink when a component is unavailable.

The fixed read-only host optionally exposes `fetch_artifact` for actual scoped
Markdown reads in profile mode. It has no file writes, shell tool or dynamic
checker loading. Gold stays outside model workspaces and inputs. Other trusted
hosts can use the same evaluator interface, but their permissions and independent
outcome checks remain their responsibility.

For direct trusted-host sessions, `brainspace_tools.py ... session --backend
profile --runtime-policy FILE` derives composition from that file, with explicit
resource arguments. Loading a policy file is not a certification or promotion
claim.

## Mathematical boundary

The strict paired quality/token test, lifetime error allocation, complete-task
bounds, independent-outcome requirement, task/call exclusion and registry-only
certificate checks are unchanged. A typed runtime policy widens the eligible
action space; it does not strengthen statistical assumptions.

Fixed/exposed cases are not fresh IID confirmation. Equal observed successes
remain inconclusive under the existing strict gate. Jev confidence is not a
truth label. A hill climb can keep the incumbent and can miss a global optimum.

**Plan feasibility before inference:** the actual fixed-look gate requires
`mean_quality_difference >= r` and `mean_token_saving >= minimum_reduction + B*r`,
where `r = sqrt(2*log(2/alpha_k)/n) > 0`. Thus **no finite equal-observed-quality
sample can pass this particular gate**. Repeating all-pass trials cannot turn
them into a certificate. Some sufficiently strong positive quality difference
is necessary under the current rule; the gate has not been relaxed.

The saved eight-pair V4 diagnostic had `alpha=.05`, `k=1`, `n=8` and
`r=1.0230566646800021 > 1`. It was arithmetically incapable of certification
for any allowed observations, and its reserved candidate/call allowances are
spent. Its 1.43% reported-token reduction remains descriptive evidence only.
Do not open another registry to reset spending or rerun exposed cases until
a favorable outcome appears. Derivation and current registry evidence:
`evidence/integrated-runtime-20261009/native-host-route/quality-gate-feasibility.md`.

The most recent complete six-task deployment comparison remains **4.9% worse
overall**; this controller extension does not turn it into a successful update.

See `TOKEN_EFFICIENCY.md`, `PRODUCT_RUNTIME.md`,
`GUARDED_RUNTIME_RESULTS.md` and `ACTIVE_EVALUATION_GOAL.md`.

## Installed live diagnostic — October 9, 2026

The new user-facing commands ran from a copied install, not evaluation imports:

| Frozen trial | Arm | Primary calls | Gateway tokens | Reference tokens |
| --- | --- | ---: | ---: | ---: |
| Screened proposal | True off | 2 | 3,456 | 6,935 |
| Screened proposal | Actual Ponytail, no reducer | 3 | 7,829 | 13,255 |
| Explicit Headroom neighbor | True off | 2 | 5,000 | 8,414 |
| Explicit Headroom neighbor | Actual Headroom, no instructions | 2 | 5,000 | 8,446 |

All four answers passed the private checks. The actual Jev call returned HTTP
200 and **abstained**; deterministic ordering selected Ponytail. The second
explicit Headroom trial followed a predeclared candidate-identity branch, not a
performance-dependent retry. Do not call either choice a favorable Jev judgment.

The controller retained ten unique API calls: nine primary and one advisory
screen, totaling **38,759 reference tokens**, including **1,709** for Jev.
Gateway primary usage was 21,285 tokens. Jev's native 2,572 input / 234 output
counts are separate units and are not added to gateway counters.

Headroom used the same worker from pre-readiness through finalization and
reported 12 completed observed Python ONNX entries. No request was compressed.
Native-internal computation remains outside the complete API-body boundary.
Neither one-sample trial certified; true off remained incumbent version 1.
No policy, host configuration or model weights were promoted/changed.

This proves the new connection and its recorded decisions, not savings,
independence, calibrated Jev confidence or a population-quality guarantee.
The task sources were fixed/exposed; failed attempts would have remained
retained. Evidence: `evidence/integrated-runtime-20261009/profile-learning/installed-live-001/`.

The independent audit verifies all ten API calls, 41 installed files, 31 runtime
sources, five assets, actual policy IDs, both-arm readiness ordering and cleanup.
Final regression: **3,355 passed plus 19 subtests**, one existing Pydantic warning,
no source drift. These software checks and this small live diagnostic are not
general performance or quality evidence.

## Why the existing theorem still applies conditionally

The theorem consumes opaque frozen policy identities, bounded whole-task
observations and independent binary outcomes. It does not depend on the policy
being a `RequestPolicy` rather than a `RuntimePolicy`. Closed type dispatch
therefore changes the declared action set, not the distributions' bounds,
error allocation or promotion inequalities.

The same caveats remain: source/resource pins do not establish task independence
or authenticate hidden serving internals; a complete captured API trace is not
complete all-in computation. No new unconditional quality claim follows from
supporting a richer policy type.
