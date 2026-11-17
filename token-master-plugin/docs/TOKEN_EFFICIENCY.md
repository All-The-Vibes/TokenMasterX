# Token efficiency: definitions, proof and implementation boundary

Implementation contract, October 4, 2026.

This is a **token-only** objective. There are no prices, subscriptions, billing
tables or monetary conversions. Foundation-model weights are unchanged.
Jev may screen policy proposals; it is neither an authorization mechanism nor
the independent outcome oracle.

## 1. The measured quantity

Pin a reference tokenizer \(\tau\), vocabulary digest, tokenizer version,
serialization/extraction protocol \(S\), and observable boundary. For every
model invocation in a task, measure the **whole** materialized input and output:

\[
I_\tau=\sum_j|\tau(S(P_j))|,\qquad
O_\tau=\sum_j|\tau(S(Y_j))|,\qquad
T_\tau=I_\tau+O_\tau,\qquad
P_\tau=\max_j|\tau(S(P_j))|.
\]

The implementation records the vector `(input, output, peak input, calls)`,
not only its sum. It counts the primary model, auxiliary decisions, verification,
recovery-related model calls, retries, and failed attempts. A raw tool result
is not separately added: it counts when it appears in a measured model input.
Replayed history counts again. Cache reuse does not subtract supplied tokens.

`tokens.py` pins `cl100k_base` to vocabulary SHA-256:

```text
223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7
```

Literal strings such as `<|endoftext|>` are ordinary text, not control tokens.
UTF-8 text is not normalized. Whole JSON envelopes are counted after the
declared serialization, including references and any model-visible wrappers.
Do not sum independently tokenized fragments: tokenization is not additive
across fragment boundaries.

The default reference protocol is canonical compact JSON or exact literal
text. Request planning instead preserves JSON insertion order and declares
`json-utf8-compact-v1`; its submitted string must be counted unchanged.
An adapter must pin its actual extraction protocol, not relabel incompatible
boundaries as equivalent.

The optimizer and current real-model study specifically pin
`complete-json-body-text/utf8-ordinary`: count each complete submitted and received
JSON-body **string unchanged**, not a parsed/reserialized approximation.
`evals/verify_savings.py` independently recounts saved strings and checks their
call inventories and outcome bindings. Body metadata/ciphertext are included
in that observable; they are not model-serving tokens. Separate explicit-context
and bridge-reported metrics cannot be mixed with it or substituted after looking
at favorable results. See `OBJECTIVE_SAVINGS.md` for the exploratory pilot.

These are **observable reference tokens**, not a reconstruction of proprietary
chat templates, server-added instructions, hidden reasoning, non-text processing,
FLOPs, latency, or provider-native token counts. Those unknown components are
not zero. Native counters remain separate diagnostics. A transport delta or a
remote state handle is not a fully materialized model input.

The tokenizer loads verified local bytes only. Missing assets can produce
labeled estimates for diagnostics, but never pass an exact guard or create a
reference measurement identity. Downloading the vocabulary is a separate,
explicitly opted-in setup operation.

## 2. Quality and learning overhead

Let \(Q_\theta\in\{0,1\}\) be independently verified task success. The objective is:

\[
J_\tau(\theta)=\frac{\mathbb E T_{\tau,\theta}}
                   {\Pr(Q_\theta=1)}.
\]

The batch report is total runtime tokens—including failed tasks—divided by
verified successes. Zero successes yield an undefined ratio, not zero usage.
Unknown outcomes prevent a defined success-normalized ratio.

Learning/search/confirmation invocations are separate from deployment. For a
**predeclared** deployment horizon, an all-in ratio includes learning tokens in
the numerator and deployment successes in the denominator. It is not defined
until every deployment task and every explicitly sealed learning-run inventory
is present. Each task also has an exact expected-call inventory.

`seal_learning_run(run_id, expected_task_ids)` cannot turn one observed task into
evidence that an entire search finished. It checks the exact recorded inventory,
then forbids further appends. This is still a trusted capture-adapter attestation,
not a way to discover external calls the adapter failed to report.

For a paired comparison, record `PairedObservation.learning_trace(spec)` once.
This composite contains both policy runs. Recording it and the individual runs
would double-count; recording two individual traces with the same task ID is
rejected.

## 3. Conditional improvement theorem

Fix the task distribution, model/environment, outcome oracle, measurement,
incumbent \(a\), candidate \(b\), and a valid bound:

\[
0\le T_{\tau,\theta}\le B_\tau<\infty,\qquad \eta_\tau>0.
\]

The cap must be enforced for the **entire task** under both policies, including
retries and recovery. Observations above it are rejected, never clipped. Merely
observing small samples does not prove a bound on future runs.

After freezing the policies and protocol, draw \(n_k\) fresh independent paired
tasks for round \(k\). Define:

\[
X_i=Q_{b,i}-Q_{a,i}\in[-1,1],\qquad
Z_i=(T_{\tau,b,i}-T_{\tau,a,i})/B_\tau\in[-1,1].
\]

Allocate a single lifetime error budget:

\[
\alpha_k=\frac{6\alpha}{\pi^2k^2},\qquad
r_k=\sqrt{\frac{2\log(2/\alpha_k)}{n_k}}.
\]

**Strict promotion gate** (the default)

\[
\bar X-r_k\ge0,\qquad
\bar Z+r_k\le-\eta_\tau/B_\tau.
\]

### Proof

For independent variables in an interval of width 2, one-sided Hoeffding gives:

\[
\Pr(\bar X-\mathbb E X\ge r)\le e^{-nr^2/2},
\qquad
\Pr(\mathbb E Z-\bar Z\ge r)\le e^{-nr^2/2}.
\]

At the specified radius, each bad event is at most \(\alpha_k/2\).
Consequently, with probability at least \(1-\alpha_k\), passing the gate implies:

\[
q_b\ge q_a,\qquad
\mathbb E T_{\tau,b}\le\mathbb E T_{\tau,a}-\eta_\tau.
\]

This bound holds conditional on previous search history, provided the new
policies are frozen and the new confirmation tasks are genuinely fresh.
Since \(\sum_{k=1}^{\infty}\alpha_k=\alpha\), a union bound across all rounds
gives simultaneous validity of every promoted update with probability at
least \(1-\alpha\).

If the true incumbent success probability is positive:

\[
\frac{\mathbb E T_{\tau,b}}{q_b}
\le\frac{\mathbb E T_{\tau,a}-\eta_\tau}{q_a}
<\frac{\mathbb E T_{\tau,a}}{q_a}.
\]

Thus the gate improves the declared expected reference tokens per verified
success, under these assumptions—not universal correctness or internal compute.

### Opt-in gates for new profile registries

`initialize-profile` can create a registry with a quality margin, the
fixed-bet token test, or both (`--quality-margin`, `--token-test max-bet-v1`;
see `PROFILE_LEARNING.md`). The settings are stored in the registry's
configuration and gate label and copied into every frozen comparison. They
cannot be added to an existing registry. A registry created without them, and
every registry that already exists, keeps the strict gate above byte for byte.

| `--quality-margin` | `--token-test` | Registry gate label |
| --- | --- | --- |
| 0 (default) | `hoeffding-v1` (default) | `strict-paired-hoeffding-v1` |
| \(0<\delta<1\) | `hoeffding-v1` | `harm-margin-hoeffding-tokens-v1` |
| 0 | `max-bet-v1` | `strict-quality-max-bet-tokens-v1` |
| \(0<\delta<1\) | `max-bet-v1` | `harm-margin-max-bet-tokens-v1` |

Each setting replaces only its own side of the gate, and both sides must pass.
Rounds under either setting are fixed, with at most 4,000 tasks, and each side
still spends \(\alpha_k/2\). Both tests are decided exactly in integers; the
stored \(\delta\), \(\eta\) and \(\alpha_k\) enter as exact fractions.

**Quality margin.** Let \(H\) be the number of tasks the incumbent passes and
the candidate fails. The quality side passes when

\[
\Pr[\mathrm{Bin}(n_k,\delta)\le H]\le\alpha_k/2.
\]

With tasks drawn independently from the pool, \(H\sim\mathrm{Bin}(n_k,h)\) for
the harm rate \(h\). If \(h\ge\delta\), \(H\) is stochastically at least
\(\mathrm{Bin}(n_k,\delta)\), so a pass has probability at most
\(\alpha_k/2\). Since \(q_b-q_a=\Pr(\text{gain})-h\ge-h\), a pass gives
\(q_b\ge q_a-\delta\) outside that event. The incumbent must be true off: a
`RuntimePolicy` whose backend and instruction are both `none`. The controller
checks this at initialization, preflight, proposal and freeze, and again on
every saved certificate it reads for promotion, rollback or deployment, against
that trial's frozen incumbent. Every margin trial is therefore compared with
true off itself, and margins never add up along a promotion chain: when the
chain's certificates are correct, every champion is at most \(\delta\) below
true off. After a promotion the registry runs no further margin trial until it
rolls back to true off. The certificate stores \(-\delta\) as its quality bound
on a pass and \(-1\) otherwise. The harm count ignores gains, so a candidate
that improves quality but has a few harms can fail a margin round that the
strict gate would pass. Under a margin the ratio step above does not follow:
tokens per success need not improve, and margin certificates say so.

**Fixed-bet token test.** The token side passes when

\[
\frac{\alpha_k}{2}\prod_{i=1}^{n_k}\frac{B+T_{\tau,a,i}-T_{\tau,b,i}}{B+\eta_\tau}\ge1.
\]

Every factor is nonnegative because every total lies in \([0,B]\). For
independent tasks the expected product is \(\prod_i(B+\mu_i)/(B+\eta_\tau)\),
where \(\mu_i\) is task \(i\)'s expected saving. If the average of the
\(\mu_i\) is at most \(\eta_\tau\), the AM-GM inequality bounds this by 1, and
Markov's inequality bounds a false pass by \(\alpha_k/2\). No task order,
variance estimate or tuning parameter enters. The claim is the same
\(\mathbb E T_{\tau,b}\le\mathbb E T_{\tau,a}-\eta_\tau\), with each task's
total counted at most \(B\); it equals the uncapped claim only where every run,
not only the observed ones, stays within \(B\). The certificate stores
\(-\eta_\tau/B\) as its token bound on a pass and \(1\) otherwise, so the shared
pass rule decides as the exact test did. With the same saving on every task,
the bet passes from 3,326 reference tokens per task at \(B=100{,}000\),
\(\eta_\tau=1\) and \(n=128\), where the Hoeffding side needs a mean saving of
\(\eta_\tau+Br_k\), 25,577.

### Optional stopping

A fixed round commits its sample size before evaluation and closes after its
one complete look. For the implemented anytime mode, allocate
\(\alpha_k/[n(n+1)]\) to look \(n\), yielding:

\[
r_{k,n}=\sqrt{\frac{2\log(2n(n+1)/\alpha_k)}{n}}.
\]

Because \(\sum_{n\ge1}1/[n(n+1)]=1\), the same lifetime error budget holds over
all looks. Rechecking a fixed-sample bound after every sample is not equivalent.
The anytime mode is strict-gate only: `start_round` refuses an anytime round
under a quality margin or the fixed bet before it spends any error.

### What this does not prove

- Equal observed quality differences are inconclusive under the strict
  zero-regression gate at every finite sample size. A tolerated decline exists
  only as the opt-in quality margin above, fixed when the registry is created
  and stated in every certificate it issues; there is no quality-floor rule.
- Jev probabilities are not outcome labels, calibrated correctness, or proof.
- Unique task IDs prevent known replay; they do not establish statistical
  independence or detect relabeled duplicate tasks outside the registry.
- A changed workload, model, oracle, tokenizer, serialization or capture boundary
  invalidates the old comparison. Frozen identities are not proof that an
  external service truly remained unchanged.
- A local hill climb does not find a global optimum. With a fixed positive
  minimum improvement and a stable regime, promotions along a chain **without
  rollbacks** are finite:
  on the simultaneous-validity event, at most
  \(\lfloor\mathbb E T_{\tau,\theta_0}/\eta_\tau\rfloor\) such drops can occur.
- Recovery fidelity is not semantic sufficiency. A shorter view can still cause
  an incorrect answer or extra recovery calls.
- The SQLite registry and configured Python evaluator are trusted local
  infrastructure, not a security sandbox against someone editing those files.

## 4. Controller invariants

```text
explicit validated baseline
  -> bounded, immutable safe-policy neighbors
  -> optional advisory Jev screening on declared search data
  -> freeze incumbent/candidate/oracle/measurement/regime
  -> reserve fresh confirmation inventory and spend round budget
  -> execute independently evaluated full paired tasks
  -> persist the certificate under the registry's gate
  -> atomically promote only the still-current incumbent
```

The controller reads certificates from its own intact registry, not caller
JSON. Concurrent promotion uses a current-version check in the transaction.
Rejected, cancelled and interrupted trials do not recycle error allocations or
task reservations. Reopening the same registry resumes its state; deleting or
restoring it to reset spending breaks the theorem's assumptions.

Direct `CertificationRegistry.submit` also durably records reported call
ownership before accepting a batch. Rejection cannot free known call IDs for a
different task, including valid siblings of an invalid/colliding observation.
Accepted observations remain atomic; correcting a submission under its same
original valid reservation remains allowed. The additive exposure table does
not recover IDs lost by old unpatched writers or revalidate old certificates.
Every writer must enforce this contract.

Rollback is an explicit operational escape hatch to a prior validated policy,
not an improvement theorem. Bounded search can return the incumbent unchanged.
Run-time Jev decisions, if an adapter adds them, belong in deployment totals;
proposal screening belongs in learning totals.

The included synthetic evaluator exercises the real planner, tokenizer,
independent label oracle, ledger, durable controller, and promotion gate. Its
deliberately favorable toy responder is **not a language model benchmark**.
Passing it does not establish a useful saving on an actual user's workloads.

## 5. Parity scope

Ponytail-inspired scope discipline is advisory: a task contract preserves the
requested result, non-goals, evidence, stopping condition and requested depth.
Task-local invocation is ephemeral; persistent state is explicitly session-keyed.
State transitions do not prove a model obeyed the instructions.

Headroom-inspired safety here covers explicit structured views, full recovery,
protected conversation fields/prefixes, bounded request planning, and honest
whole-task evaluation. It does not clone a proxy, dashboard, hosted service,
streaming/multimodal engine, or universally intercept every harness.

Graph queries enumerate indexed **candidate** relationships with source/index
fingerprints and paging. They do not certify inferred edges as complete or
correct. Freshness covers indexed files, not unindexed newly created files.

## 6. Implementation map

| Contract | Implementation |
| --- | --- |
| Reference identity and final envelope guard | `brainspace/tokens.py` |
| Complete call/task/learning inventories | `brainspace/token_ledger.py` |
| Fresh fixed/anytime confirmation, exact harm and bet tests, error spending | `brainspace/certification.py` |
| Immutable policies, protected request structure | `brainspace/request_policy.py` |
| Durable bounded search, champion and rollback | `brainspace/optimizer.py` |
| Advisory network decisions only | `brainspace/jev.py` |
| Task/session mode lifecycle | `brainspace/task_mode.py` |
| Scoped paged exact recovery | `brainspace/ccr.py` |
| Native result-schema adapter | `brainspace/host_output.py` |

Paths are relative to `skills/token-master/` inside this plugin.
