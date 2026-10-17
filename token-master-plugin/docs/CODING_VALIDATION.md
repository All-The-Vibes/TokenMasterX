# Coding validation: measured scoped-profile pilot, repeatability still open

## Newer comparison and retention test — October 8, 2026 UTC

The later four-arm study completed 24 attempts. TokenMaster and Ponytail both
passed 6/6 tasks, but TokenMaster used **224,150** primary reference tokens
against Ponytail's **195,335**. Five extra original-retrieval calls hurt
TokenMaster's result. Baseline and Headroom each completed 5/6 correctly;
Headroom's failure was a captured upstream HTTP 502, not an omitted run.

Jev subsequently abstained on sanitized policy-search metrics. A deterministic
activation audit selected retaining two recent results rather than one. On four
new source-disjoint holdout tasks, both policies passed 4/4; observed reference
usage was **100,149 → 62,649**. The gain is dominated by one trace, including a
wrong recovery-tool selection by the incumbent. No default was promoted and
no Jev-caused gain or typical savings rate is claimed.

The subsequent clarified-recovery replication passed 4/4 in both arms with
12 calls each and **35,418 bridge-reported tokens each**. Neither arm activated
compression; the 31-reference-token difference is not a policy saving.
The earlier 37.4% observation has therefore not been replicated on fresh tasks.

Three separately planned repeats of the **already-exposed active case** then
confirmed a narrower mechanism under clarified tools: retain-1 made five calls,
including two genuine recoveries, while retain-2 made three, in every repeat.
Both remained correct. Their total reference use was **118,010 → 61,213**.
This removes the wrong-tool explanation for that case, but is still not
fresh-task or population evidence.

See `COMPARATOR_RESULTS.md` for the complete boundaries and retained evidence.
The earlier 6.28% scoped-profile pilot below remains a separate experiment;
do not combine its percentage with the later results.

## Current scoped-profile result — October 8, 2026 UTC

**The existing task-discipline plus context-reduction profile completed all four
repository tasks correctly with fewer tokens in one fresh, predeclared study.**
This is a working opt-in request-path pilot, not a production-wide savings claim
or an automatic policy promotion.

| Complete-study metric | Baseline | Scoped TokenMaster |
| --- | ---: | ---: |
| Correct tasks | **4/4** | **4/4** |
| Model calls | **12** | **12** |
| Full API-body reference tokens | **81,530** | **76,410** |
| Bridge-reported input + output tokens | **55,603** | **51,868** |
| Requests actually reduced | 0 | **2** |

The observed reductions are **5,120 reference tokens (6.28%)** and, separately,
**3,735 bridge-reported tokens (6.72%)**. Reference counts tokenize complete
captured JSON bodies, including metadata and ciphertext; they are not a
measurement of proprietary model-serving tokens. Bridge counters are diagnostic
and not independently authenticated upstream.

The navigation case accounts for the gain; the other three cases incur small
instruction overheads. Do not infer that every job benefits. Replaying actual
treatment histories with exact source restored recovers **5,864 reference input
tokens** across three hash-verified source occurrences. That input-only audit
holds the recorded trajectory fixed; it does not predict a counterfactual
model's actions.

The comparison deliberately enables **both** existing task discipline and
recoverable views in the treatment arm. Its instructions therefore differ from
baseline by the declared scope contract. This is not a pure-compression causal
estimate or a measured comparison against upstream Ponytail. Jev and answer
refinement were off; exact/edit/debug protections and recovery checks stayed on.

Evidence: `evidence/combined-request-validation-20261008/live/` and its sibling
`offline-verification.json`. The independent offline pass verified all 37 frozen
source files, re-counted/re-graded all eight task runs, checked both edited files
byte-for-byte, reproduced each arm's declared initial request without inference,
and matched the dispatch journals to captures without changing the originals.
There were **25 attempts including readiness**, **159,057 reference tokens
including readiness**, and **117.687 execution seconds**. Earlier development,
unsuccessful studies and unknown upstream work are not included in those totals.

### Measurement fixes and runnable controls

The v4 runner persists a pending receipt **before** dispatch, then fsyncs the raw
capture before acknowledging it. Unresolved dispatches remain unknown; missing
or inconsistent per-task journals fail the audit. Readiness and task dispatches
also receive study-level exposure receipts. This protects against local process
interruption, not unobservable upstream internal calls.

The v3 outcome oracle requires the exact expected UTF-8 bytes before executing
the trusted patch checks. Extra blank lines, missing final newlines and CRLF
rewrites no longer count as the requested one-change patch. The saved edits in
the previous completed study and all three new context-only repeats were also
checked directly and already matched the exact expected bytes.

The runner exposes `--task-discipline` explicitly and accepts a bounded
`--timeout-seconds` setting from 1 to 90 (default 60). The hard deadline adds
30 seconds; no per-call retry was added. The scoped study used 90/120 seconds,
the same bound in both arms, and the existing 900-second study limit.

Reproduce with a **new** output directory and the existing compatible loopback
bridge; no normal host profile is installed or modified:

```powershell
& "C:\Users\shyamsridhar\code\TokenMaster\.token-master-dev\Scripts\python.exe" `
  "C:\Users\shyamsridhar\code\TokenMaster\token-master-plugin\evals\run_repository.py" `
  --output "C:\Users\shyamsridhar\code\TokenMaster\evidence\my-new-scoped-study" `
  --model gpt-6-astra --allow-network --task-discipline --timeout-seconds 90
```

### Context-only repeats are retained, not selected away

Before this separate scoped-profile study, three context-only repeats were
predeclared in `evidence/token-reduction-repeats-20261008/`. The first used
**39,941 more** bridge-reported tokens; the second used **40,831 fewer**. Both
completed with 4/4 correct in each arm. The third retained a transport timeout
on the last baseline task. Thus **the complete batch's token total is unknown**,
not an average over just the successful studies. Its offline recount reproduces
all three receipts with zero inference calls and no duplicate visible response
IDs; that does not authenticate upstream behavior.

These swings are why one positive scoped-profile run is still a pilot.
Representative repeated benefit, held-out Jev improvement, native Desktop
qualification and competitor parity remain open. No default was promoted.

---

## Earlier context-only result — October 8, 2026 UTC

**The repaired reducer activates and reduces eligible source requests. The
completed four-task comparison did not demonstrate overall token savings.**

All four source-pinned repository tasks passed in both arms. The enabled arm
used more tokens in this realization, mainly because it made four additional
calls in a debugging task where reduction was deliberately bypassed. This is
not evidence that compression caused those extra calls: the model selected
different reads despite identical starting requests.

| Completed-run metric | Baseline | TokenMaster |
| --- | ---: | ---: |
| Correct tasks | **4/4** | **4/4** |
| Model calls | 11 | 15 |
| Requests actually reduced | 0 | **2** |
| Bridge-reported input + output tokens | **47,815** | **87,842** |
| Full-body reference input tokens | 52,568 | 98,064 |
| Full-body reference output tokens | 18,804 | 24,713 |
| Full-body reference total | **71,372** | **122,777** |

That is an observed **83.7% increase in bridge-reported tokens** and a **72.0%
increase in reference tokens**, not a savings result. These four purposively
selected tasks are not an independent population sample or a promotion
certificate. Scope instructions, graph acquisition, Jev and answer refinement
were off; this isolates the context reducer rather than the whole product.

### Where the difference came from

| Task | Baseline calls / bridge tokens | TokenMaster calls / bridge tokens | Reduced requests |
| --- | ---: | ---: | ---: |
| Navigation map | 4 / 26,427 | 4 / 21,947 | **2** |
| Impact traversal | 2 / 4,885 | 2 / 4,885 | 0 |
| Setup diagnosis | 2 / 6,889 | 6 / 51,396 | 0 |
| Narrow `.pyi` fix | 3 / 9,614 | 3 / 9,614 | 0 |

Navigation used **17.0% fewer bridge-reported tokens**. Replaying its actual
treatment histories with exact original source restored required **5,907 more
reference input tokens**. Thus the views removed that input volume while
holding the recorded trajectory fixed. Three source occurrences were recovered
and hash-checked. This is not a prediction about the model's counterfactual
output or future task success.

The setup-diagnosis difference outweighs the navigation reduction. **Do not
discard that case, broaden lossy compression into debugging to make the score
look better, or promote a policy based on the successful navigation slice.**

### Evidence, interruptions and reproduction

The complete replication is
`evidence/repository-diagnostic-20261007/live-v2/`. It contains a frozen
37-file source inventory, fixed public-source fixture, predeclared controls,
all eight task runs and complete raw request/response captures. It made **27
attempts including readiness**, used **195,303 reference tokens including
readiness**, and completed in **151.297 script-execution seconds**.

The preceding `live-v1/` in the same evidence root stopped on a 60-second
transport timeout after four successful task runs and one incomplete attempt.
Its navigation pair used 16.0% fewer bridge tokens, but its whole-study totals
remain **unknown**. That failed attempt and the three unrun cells are retained.
The earlier source-guard pilot also remains preserved at
`evidence/source-read-guard-20261006/live-v1/`.

`offline-verification.json` freshly reproduced the partial five-run summary and
the complete eight-run summary, using separate frozen-module processes and
temporary recovery-store copies. Original evidence was unchanged. Every
available paired first request matched byte-for-byte; every complete capture
was recounted, source recovery checked and source-derived outcome regraded.
The audit does not authenticate upstream internals or turn missing bodies into
zero token use. No aggregate across the interrupted and completed studies can
be called a complete all-in result.

The runnable diagnostic now ships as `evals/run_repository.py`. It requires an
existing compatible loopback bridge, verified local tokenizer and explicit
`--allow-network`; it freezes a new output directory and never retries a call
or overwrites a study. Its revised oracle rejects read-only write attempts even
when final bytes are unchanged. Budget-stopped tasks cannot make a planned
comparison appear complete.

No global policy promotion, normal host-profile change, model-weight update or
monetary calculation followed this result. **The next performance question is
repeatable whole-task efficiency on a fresh, independently graded workload,
not whether the source guard now activates.**

---

## Historical first trial — October 5, 2026: no activation

October 5, 2026. **Do not count this run as demonstrated TokenMaster savings.**

## What was actually tested

The existing request-context reduction policy was compared with no reduction,
using the same `gpt-6-astra` model identifier, instructions, tools, task inputs
and limits. Scope-prompt optimization, Jev, model refinement and extra critics
were all off, so context reduction was the only intended treatment.

The four tasks used actual TokenMaster repository files pinned to commit
`426fc853389ddba4bc6e1dd35a28179a895c064f`, copied into separate private
workspaces:

1. Navigate the graph, setup and router entry points.
2. Trace the real graph-impact traversal and its bounds.
3. Diagnose when setup disables a backend versus only issuing a sparse-graph
   warning.
4. Fix an actual `.pyi` routing gap by making the requested one-line source
   change while preserving everything else.

There was no padded source, synthetic log volume, or forced file-reading
sequence. The model chose which files to read. Tasks 1–3 were checked against
source-derived structured answers. The edit had to match the independently
prepared narrow patch before six trusted function-level behavior checks ran.
The original bug and the expected fix were both verified before inference.
Arbitrary model-generated Python was not executed, and the sandbox was not
weakened.

This tests the explicit stateless bridge adapter, **not** a native Copilot
CLI/Desktop installation, the full graph-acquisition product, or a representative
population of all coding work.

## Result

| Metric | Baseline | Context reduction enabled |
| --- | ---: | ---: |
| Correct repository tasks | **4/4** | **4/4** |
| Model calls | 19 | 15 |
| Requests actually compressed | 0 | **0** |
| Bridge-reported task tokens | 151,012 | 92,309 |
| Full-body reference task tokens | 202,338 | 128,345 |
| Recorded task seconds | 113.812 | 92.125 |

**The raw token difference is not a TokenMaster saving.** The entire 58,703
bridge-reported-token difference came from the patch task: the baseline model
read all five available files before editing, while the other execution read
only the target file. The other three task pairs had identical reported token
totals.

Every paired first request was byte-for-byte identical. No request was
transformed in the enabled arm. Replaying the enabled policy offline against
each of the **34 captured task requests**, preserving each original retrieval
trajectory, removed **zero input tokens**. The smaller aggregate therefore
does not establish a treatment effect; it reflects different model-selected
file reads, not context removed by this policy.

## Why it did nothing

Two current constraints prevented activation:

- Edit/debug intents deliberately bypass reduction, and the newest tool result
  is protected. These are declared safety choices, not hidden savings.
- `_protected` also scans raw tool text for words such as `error` and
  `Exception`. That includes ordinary source code and comments, even when a
  file read succeeded.

Examples from the pinned source:

| File | Line | Ordinary code/text triggering protection |
| --- | ---: | --- |
| `graphify_mcp.py` | 58 | Comment saying “reported as a clear error on load” |
| `setup.py` | 103 | Source of an error-printing function |
| `brainspace/router.py` | 46 | `ERROR` inside a log-detection regular expression |
| `brainspace/tokens.py` | 30 | `except Exception:` |

Consequently, the older source reads needed by the navigation task were also
protected. Passing compressor unit tests does not establish that the whole
request pipeline activates on ordinary repository code.

**The concrete engineering issue is distinguishing actual failed tool results
from successful reads of code that happens to contain error-handling text.**
Simply deleting error protection or enabling lossy edits would not be a
justified repair. Any repair needs targeted preservation tests and another
measured task comparison.

## Evidence and boundaries

Local artifacts are in `evidence/coding-validation-20261005/live-v1/`:

- `manifest.json`: frozen tasks, controls, policy identities and source pin.
- `prelaunch-self-tests.json`: positive/negative grader checks, real original
  bug reproduction and trusted reference-patch checks.
- `runs/`: separate workspaces, actual tool events and full request/response
  captures for all eight task executions.
- `summary.json`: per-task and aggregate counts.
- `verification.json`: fresh offline recount and grading checks for all eight
  executions, 36 matching source hashes, unique call receipts, and identical
  paired initial requests.

The study made **35 model requests including readiness**, completed in
**212.421 script-execution seconds**, and recorded **331,797 full-body reference
tokens including readiness**. It stayed within its declared 65-request,
900-second and 500,000-reference-token stop controls.

Reference counts are reproducible tokenization of captured JSON bodies, not
proprietary serving tokens. Bridge usage is separately reported and not
independently authenticated. Earlier development/review calls and unobserved
upstream work are outside these totals. No monetary calculation or population
certificate was produced.

No production modules, policy defaults, model weights or real host profiles
were changed. The model's patch exists only in the isolated benchmark copies.
