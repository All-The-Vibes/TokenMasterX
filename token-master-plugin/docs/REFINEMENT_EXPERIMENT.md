# Bounded black-box refinement experiment

October 5, 2026. This is a new, opt-in development experiment, not a release,
population-level qualification, or automatic policy promotion.

## Why this can run now

The existing token-efficiency controller is implemented. Missing representative
workloads and isolated Desktop access limit qualification claims; they need not
block a no-tools experiment with fresh synthetic problems and exact local
oracles. Models receive public synthetic problem text only. No generated code
is executed, no credentials are discovered, and no host settings are changed.

## Predeclared comparison

Use a separate adapter and fresh captures. Do not change the saved pilot's
adapter, checker, policies, or statistical acceptance gates.

| Arm | Schedule | Maximum calls per task |
| --- | --- | ---: |
| single_primary | A solution | 1 |
| single_secondary | B solution | 1 |
| resample_primary | Four independent A solutions, deterministic plurality | 4 |
| refine_primary | A initial, A continuation, A critique, A correction | 4 |
| cross_refine | A initial, A continuation, B critique, A correction | 4 |

Here A and B are explicit model IDs whose availability must pass a recorded
readiness check through the existing loopback bridge. Matching reported IDs is
not independent authentication of the underlying model weights or provider.
If B is unavailable, record that failure and execute only the three A-only
arms. Never silently substitute another model.

### API compatibility, established by the first live probe

The first frozen v1 study received `unsupported_api_for_model` when submitting
`claude-opus-5.5` to the Responses endpoint. It retained the failure and continued
only the declared GPT controls. This is an API incompatibility, not evidence
that the account lacks Claude access.

The separate v2 adapter uses native `/responses` for GPT and native `/messages`
for Claude, on the same already-configured loopback bridge. It retains each
literal wire format and freezes the API mapping in the policy identity.
`reasoning.effort=low` and `output_config.effort=low` are requested respectively;
equal labels do not establish equal compute. No temperature or generation seed
is imposed. The random seed controls task generation/order, not model sampling.

Messages input usage is the sum of its three separately reported input/cache
components. Missing components remain unknown. Native counters remain
bridge-reported, not independently authenticated. Visible text is projected
into the same supplementary reference format across the two APIs; hidden
thinking/signatures are retained in raw captures but not forwarded to a critic.

To preserve the original overall allowance, the intended follow-up selects
`single_primary`, `single_secondary`, and `cross_refine` on four newly generated
tasks: at most 26 calls including two probes. Together with the v1 primary-only
maximum of 74, this is at most 100 attempts, below the original 114 allowance.
The follow-up uses only the remaining portion of the original 1,200-second
combined execution allowance. No follow-up runs after an HTTP 429.

The v2 native readiness request succeeded at HTTP level but correctly failed
its original exact-ID check: request `claude-opus-5.5`, response
`claude-opus-5-5`. V2 retained that failure and ran only its four one-shot GPT
controls. V3 therefore declares this observed request/response mapping
explicitly using `--secondary-reported-model`; there is no automatic name
rewriting, wildcard acceptance or silent model substitution. Both identifiers
remain in evidence, and the mapping is part of the policy identity.

V1 actually used 71 attempts and 797.297 execution seconds; V2 used 6 attempts
and 51.157 seconds. The final planned V3 comparison uses four fresh development
tasks, at most 26 attempts and 350 execution seconds. Combined maxima are
103 attempts and 1,198.454 seconds. Earlier failed probes are retained, not
retroactively marked successful. These phases do not use the same task sample
and must not be pooled into one paired comparison.

The four-stage schedule is an original, small implementation of the *literal*
Algorithm 1 in arXiv:2608.05643v1 with N=1 and D=1. Cross-provider critique is
our modification, not a result established by that paper. It is deliberately
smaller than the earlier N=2 proposal. This tests a whole policy, not a causal
claim that provider diversity itself helps. No author implementation is copied.

The cross arm uses A for the final answer and B for critique; the B-only arm
is a diagnostic control, not an equal-provider-mixture ablation. Jev is off so
that its effects and overhead do not confound this first refinement comparison.

## Frozen controls and stopping rules

- Eight fresh seeded tasks across four exact-answer families. They are a
  non-IID development challenge suite, not a representative population sample.
  Correlated task variants and internal calls are not independent observations.
- Generate and freeze problems, protected gold answers, source hashes, policy
  identities, tokenizer identity and randomized task/arm order before inference.
- Exact integer/rational answer checking is deterministic. Gold answers and
  checks are not included in model requests, critiques, voting or selection.
- Request a concise explanation and a machine-readable answer; grade the final
  numeric answer only. This does not certify the explanation or a proof.
- Carry only the stage dependencies prescribed by the policy, not accumulated
  conversation history. No tools, remote conversation, learned memory, feedback
  from the oracle, retry, fallback answer or model-based selector.
- Plurality uses canonical exact rational answers. Ties choose the earliest
  sample index, never the fastest response or the correct gold answer.
- A malformed answer, failed stage, refused or truncated response fails the
  policy; earlier answers are not silently carried forward.
- Sequential model execution, at most 114 submitted generation attempts:
  two readiness probes plus 8 * (1 + 1 + 4 + 4 + 4). Unused capacity is not
  reallocated to outcome-driven trials.
- Per call: explicit output-token request limit, input-reference-token and
  wire-byte limits, and a local subprocess deadline. A killed client cannot
  establish upstream cancellation or recover unobserved usage.
- Whole-study elapsed-time and observed-reference-token stop thresholds prevent
  starting further calls. A completed response can cross the observed-token
  threshold; preserve the overrun rather than clipping it. This is **not** a
  proven hard cap on proprietary/hidden model computation.
- Failed and incomplete calls remain in the inventory. Missing output or usage
  stays unknown. An explicit HTTP 429 stops the study without retries or provider
  switching. A partial run is not compared as though every arm completed.

## Measurements and decision

Recount complete captured HTTP text with the pinned offline tokenizer. Also
report explicit visible-context reference counts and bridge-reported usage
separately. The common reference is not a provider's native tokenizer, hardware
work, or money. Heterogeneous bridge token totals are a labeled raw sum, not
model-independent compute. Do not subtract cached tokens or double-count
reasoning details.

Report final answer accuracy, wrong-to-correct/correct-to-wrong transitions
within refinement, every attempted call, task stopwatch time, failures,
reference-token totals, per-model bridge counts, and tokens per correct task
(including tokens spent on failed tasks). Readiness overhead is separate and
included in the experiment's all-in accounting. Here "all-in" means this
scripted experiment, not the project's earlier studies, coding/review model
calls or unobserved upstream internals. Net project-wide learning savings
remain unknown; they are not inferred from this run.

An offline audit must reconstruct prompts, dependency order, extraction,
selection, outcome checks and counts from frozen source and raw captures.
Passing that audit establishes internal consistency, not truthful upstream
usage or representative performance.

Do not tune on these outputs and call them a fresh holdout. Do not claim a
statistical certificate or promote a policy from this experiment. If refinement
adds tokens without improving correctness, retain one-shot behavior and report
that negative result.

## Local entrypoint

`evals/run_refinement.py --output NEW_DIRECTORY` prepares a frozen source,
problem and policy manifest **without making a network call**.

Explicit `--allow-network` executes the frozen experiment against the already
configured credential-free loopback bridge. Model IDs, task count, seed,
output-token bound and time/call/reference stop limits are command-line
arguments. It will not discover credentials or configure a new provider.
`--secondary-api` selects the explicit native transport (Messages by default);
`--secondary-reported-model` pins a separately observed native response ID;
`--arms` selects a predeclared subset before freezing, never after inspecting
that study's outcomes. A prior study remains immutable.

To recount a saved run with its original checker, invoke its frozen copy of
`source/token-master-plugin/evals/run_refinement.py --output ABSOLUTE_RUN_DIRECTORY
--audit-only`. The offline audit does not send requests, rerun failed model
calls, regenerate answers or issue a promotion certificate.
When invoking a frozen checker outside its launcher, set the process-local
`BRAINSPACE_TOKENIZER_FILE` to that run's `cl100k_base.tiktoken`; it is a
public vocabulary file, not a credential. This avoids relying on an ambient
tokenizer cache. The checker verifies its content hash before accepting counts.
