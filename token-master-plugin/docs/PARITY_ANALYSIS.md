# Token-only parity: TokenMaster, Ponytail and Headroom

**Source refresh: October 7, 2026 UTC.**
This contains a capability/implementation analysis and a later bounded
head-to-head study, **not a claim of production parity**. Prices, billing,
credits and monetary ROI are outside its scope.

`COMPARATOR_RESULTS.md` records the October 8 four-arm experiment. TokenMaster
and Ponytail each passed 6/6, but Ponytail used fewer primary-reference tokens
(195,335 versus 224,150). The baseline's wrong answer and Headroom's HTTP 502
remain counted. A separate retention-neighbor holdout observed lower use at
4/4 correctness in both arms, but the effect is concentrated in one trace;
Jev abstained and no policy was promoted.

## Decision

Keep three separate mechanisms:

1. **Task discipline:** finish the requested work without unnecessary changes,
   tools or unsolicited output; preserve requested depth and verification.
2. **Context acquisition:** fetch the right code/graph evidence instead of
   repeatedly reading unrelated material.
3. **Context reduction:** make eligible transmitted content smaller, retain
   protected content and provide exact recovery when a view omits information.

Ponytail primarily addresses the first mechanism. Headroom primarily addresses
the third through a larger request/proxy pipeline. TokenMaster implements a
bounded combination, including its own graph tools. Their effects overlap:
**multiply neither advertised reduction percentages nor independently measured
ratios from different task trajectories**.

The Jev controller is separate again. It can screen policy candidates; it
cannot authorize compression, label its own results correct, or certify its
own promotion. Its output is not a mathematical proof.

An October 8 scoped-profile pilot exercised TokenMaster's existing task
discipline and context views together: 4/4 correct in both arms, 12 calls each,
81,530 → 76,410 full-body reference tokens. It was independently re-counted
from frozen captures. The navigation case dominates the gain and repeatability
remains open; this is **not** an upstream Ponytail/Headroom comparison. The
earlier negative and interrupted context-only repeats remain recorded in
`CODING_VALIDATION.md`.

The later runtime check found and inspected an official Headroom OCI image for
the **same comparison commit**, not a newer release: 557 installed Python files
matched the attested archive and the native Rust extension imported successfully
under non-root/network-none isolation. The source-pinned Kompress model and
actual public request pipeline subsequently compressed eligible text-tool
fixtures offline, with complete original recovery. Recent Read results were
deliberately protected. This is activation evidence, not a head-to-head result.
The default-disabled AST path, estimated `gpt-6-astra` counter, unqualified
optional relevance routes and exact provenance are recorded in `PARITY_RUNTIME.md`.

## Compared versions

The original comparison remains pinned to these immutable source trees:

| Project | Comparison SHA | Metadata at that tree |
| --- | --- | --- |
| Ponytail | `c982cd411abb53323c4baa1baa3c2f020b8d0b08` | 4.10.3 |
| Headroom | `1cf496612e781ef8d67ff87ee4f78037492f0bc7` | 0.39.1 |
| TokenMaster regression fixture | `426fc853389ddba4bc6e1dd35a28179a895c064f` | Original source; **not** this dirty implementation branch |

Those upstream metadata versions are not release-tag identities: Ponytail's
v4.10.3 tag resolves to `ef8ca48fed2321ab6668b2a954f23b1af97d7f6d`;
Headroom's v0.39.1 tag resolves to
`d13e1966f820220b482a33c30bde1e926743939a`.

The October 7 refresh found later default-branch tips:
Ponytail `552acd5efd0aeae2583a12efe39373d2f076f25e` (4.13.0;
54 commits ahead of the comparison pin) and Headroom
`5a516b54afd50156521638645a9063992e395a7b` (0.40.0;
67 commits ahead). These are drift observations, not replacements for the
frozen comparison. Latest non-prerelease tags observed were v4.13.0 and
v0.40.0 respectively. [P0] [H0]

## Capability-by-capability findings

| Capability | Pinned upstream evidence | TokenMaster implementation | Verification boundary |
| --- | --- | --- | --- |
| Requested scope, reuse and short defaults | Ponytail explicitly preserves requested reports, necessary validation and nontrivial checks. Its review skill does not certify correctness or security. [P1] [P2] | `brainspace/task_mode.py`, scoped host templates and `token-master-review/SKILL.md` | Mode/CLI tests and bounded model challenges exist. Representative maintainability/depth qualification remains open. |
| Mode state | Pinned Ponytail uses project/shared state; sanitized project paths can collide and same-repo sessions share mode. A later tip changes path hashing. [P3] | Explicit task/session scopes and owned enable/off state | Tests cover isolation and disable behavior. Do not claim identical lifecycle semantics or deterministic model obedience. |
| Code acquisition | Ponytail advises reading relevant callers; it is not a generic code-graph acquisition implementation. [P1] | `graphify_mcp.py`: indexed provenance, freshness checks, paging and ambiguity reporting | Tests cover changed indexed files and high fanout. Inferred/dynamic edges are not semantically exhaustive. |
| Source and tool-result views | Headroom has content routing and conditional protection. Its pinned error fast path does not protect every error-looking output of every size. [H1] | `brainspace/router.py`, task-sensitive compressors, explicit request policy | Exact/edit/debug-sensitive inputs bypass reduction. v2 source receipts bind successful reads to call, tool, path and content hash; words such as `Exception` no longer automatically block a verified source read. |
| Request and role protection | Headroom treats message/role/protocol state as part of the transform boundary. [H1] [H4] | `brainspace/request_policy.py`, `brainspace/pipeline.py` | Protected instructions, stable prefix, recent results, tool pairing and final serialized size have tests. Callers must actually send the checked representation. |
| Size guards | Headroom's library can restore original messages on measured inflation; its pipeline does not universally swallow exceptions. [H2] | Final representation token/byte guard, out-of-band diagnostics | Unit and native-envelope checks exist. A smaller isolated text fragment is not accepted as proof of a smaller final request. |
| Recovery | Headroom stores originals with expiry; retrieval can miss, recovery rounds are bounded, and unresolved inline markers remain explicit. [H3] | `brainspace/ccr.py`: scoped originals, integrity, paged retrieval, bounded exact search and retention | Public MCP reconstruction of a 200,001-character Unicode original was verified. Storage recovery is not proof that the model will retrieve omitted information when needed. |
| Real host transport | Ponytail emits host-specific envelopes and separately exposes instructions through MCP. Headroom has broader HTTP/stream/proxy handlers. [P4] [H4] | Claude result adapters; model-invoked MCP; explicit request adapter; opt-in native Copilot conservative JSON `view` hook | Claude 2.1.289 envelope/lifecycle and older Copilot MCP tests are retained. A separate Copilot 1.0.95-0 actual settings lifecycle now verifies its named JSON hook; see `NATIVE_COPILOT_HOOK.md`. Native full-profile execution, broader tools and Desktop remain unqualified. Codex strict user-skill isolation remains open. |
| Advanced model-backed decisions | Headroom's broader semantic/proxy/multimodal surface is not replicated here. | Opt-in, bounded Jev client plus deterministic candidate neighborhood, fallback and optimizer | Real sanitized/synthetic Jev calls and toy controller integration exist. Held-out real-primary improvement from Jev remains unproven. |
| Whole-task efficiency | Neither source code nor a provider confidence field establishes a local whole-task gain. | Complete reference-token ledger, independent outcomes, frozen comparisons and durable promotion state | Bridge counters and reference tokenization remain separate. Incomplete captures make whole-task totals unknown. No current population savings certificate is asserted. |

The installed Codex Ponytail bundle is also a distinct artifact from the
upstream runtime: the original inventory found bundle 2.0.0 pinned to upstream
4.9.0, `356918eba965ee1eac64bd3a7f0dd02108350de5`. Installation or skill
availability alone does not prove an always-on hook is active.

## What the mathematics guarantees—and what it does not

The shipped specialization is defined and proved in `TOKEN_EFFICIENCY.md`.
For a frozen candidate and incumbent, use fresh independently evaluated task
pairs, binary independently verified outcomes, complete reference-token traces,
and a predeclared whole-task bound \(B\). Both paired differences have range
width **2**, after token differences are divided by \(B\).

The fixed-look radius is
\[
r_{k,n}=\sqrt{\frac{2\log(2/\alpha_k)}{n}},
\qquad \alpha_k=\frac{6\alpha}{\pi^2k^2}.
\]
Each of the two one-sided bounds receives \(\alpha_k/2\). The anytime version
additionally spends \(\alpha_k/[n(n+1)]\) across looks.

Promotion requires **both** a nonnegative lower quality-difference bound and a
token-difference upper bound at most \(-\eta/B\), with \(\eta>0\).
Under the stated sampling/capture assumptions, the summed error budget covers
adaptive rounds. It does not prove task independence, truthful upstream
accounting, universal semantic equivalence, a global optimum, or perpetual
improvement. Equal observed quality can correctly remain inconclusive.

The independent October 7 review checked the constants and guarded optimizer
path and found a standalone-registry rejected-batch replay gap. The repair now
commits reported-call exposure separately from accepted observations. On
October 8 UTC, the parent reran both original reproductions: each retained all
200 reported sibling call IDs, accepted no partial observations, and rejected
cross-task replay after restart. Genuinely fresh synthetic controls still
passed. The constants and strict gate were not weakened.

The additive exposure table cannot reconstruct IDs forgotten by an older
implementation. All writers must use the patched code; legacy certificates are
not rewritten or retroactively revalidated by adding the table. Corrections
within the same original valid reservation remain supported.

Jev confidence describes its returned probability distribution, not measured
task-success probability. Official Jev guidance explicitly keeps exact
mathematics outside the model. The pinned `jev-1.13.0` remains documented;
structured Score response compatibility is covered by offline client tests.
A separate authorized synthetic Jev call also returned HTTP 200 with object
legends at both levels. That verifies the response compatibility path, not
real-primary task quality. See `JEV_CONTRACT.md`. [J1]

## What the coding experiment actually established

**Latest complete replication: no overall token win.** On October 8 UTC,
both arms passed all four tasks, but the enabled arm used 87,842 bridge-reported
tokens versus 47,815 for baseline. Navigation reduced two requests and used
17.0% fewer bridge tokens; additional model-selected reads in an uncompressed
debugging task outweighed that reduction. The observation does not establish
that compression caused the extra reads. See `CODING_VALIDATION.md` for the
per-task table, reference counts and full receipts.

The complete replication had 27 attempts including readiness, with all
response bodies captured and 195,303 reference tokens in that declared study.
Its four paired starting requests matched exactly. A fresh offline audit
recounted/regraded all eight runs and recovered the original source using
temporary store copies, without modifying the saved evidence.

### Earlier pilot, retained rather than substituted for the full result

The original four-task test passed in both arms but transformed **zero**
requests. Its lower treatment total was not attributable to compression.

After the successful-source guard repair, the completed navigation pair
showed:

| Observation | Baseline | TokenMaster |
| --- | ---: | ---: |
| Correct source-derived answer | Yes | Yes |
| Model calls | 4 | 4 |
| Bridge-reported input + output tokens | 26,427 | 21,861 |
| Actually reduced requests | 0 | 2 |

That is **17.3% fewer bridge-reported tokens for this one pair**. Separately,
restoring the exact source in the captured treatment histories increased the
reference-tokenized inputs by **5,993 tokens**; three source occurrences were
recovered and hash-checked. This distinguishes a real transformation from a
model merely choosing fewer reads.

A later call timed out. The study-wide totals and overall four-task claim
remain unavailable; the timeout and unrun task are retained in
`evidence/source-read-guard-20261006/live-v1/partial-summary.json`.
The reusable `evals/run_repository.py` diagnostic retains complete-call
subtotals, marks unknown whole-task totals, lists missing runs and performs no
automatic retry. A subsequent run must be a new frozen experiment, not an edit
to that receipt.

## Remaining qualification work

The October 8 runtime preparation is recorded in `PARITY_RUNTIME.md`: the
pinned Ponytail instruction builder ran with exact source verification in a
network-isolated container; Headroom's real native/ML runtime and the isolated
Linux Codex cell were blocked by official Python wheel-host TLS failures.
No placeholder Headroom arm or native-pass claim was substituted.

1. The bounded repository diagnostic is complete; retain its negative aggregate
   and the separate interrupted attempt rather than treating the navigation
   win as a whole-task result.
2. Freeze a fresh workload and independent grading before a representative
   comparison. Exposed development examples cannot become a new holdout simply
   by receiving new IDs.
3. For measured competitor parity, execute the pinned comparator implementations
   under equivalent task/model/tool boundaries. A capability matrix is not that
   experiment.
4. Verify the remaining named Codex/Windows/Desktop cells in an environment
   that cannot read or modify the normal user profile. Do not relax isolation
   to fill a table.
5. Keep Jev learning overhead, recovery, retries and failed attempts in their
   declared inventories. Retain the incumbent when the strict gate is
   inconclusive; do not force a promotion.

Replicating all upstream dashboards, proxies, multimodal transforms and
deployment products remains outside the adopted bounded parity backlog.
No host-global enablement or model-weight change follows from this analysis.

## Primary sources and receipt boundaries

All upstream claims above are source inspection, not executions of upstream
tests. Public source receipts preserve retrieval time, HTTP status and body
hashes under `evidence/parity-refresh-20261007/`. The refresh checked 26 pinned
Git blob identities and 35 citation ranges. `web.run` returned no usable
content in that session; direct unauthenticated official GETs supplied the
documents. No third-party summary or model benchmark was substituted.

- **[P0]** [Ponytail frozen comparison](https://github.com/DietrichGebert/ponytail/compare/c982cd411abb53323c4baa1baa3c2f020b8d0b08...552acd5efd0aeae2583a12efe39373d2f076f25e) and [observed v4.13.0 release](https://github.com/DietrichGebert/ponytail/releases/tag/v4.13.0).
- **[P1]** [Ponytail scope/reuse rules, pinned AGENTS.md lines 5–30](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/AGENTS.md#L5-L30).
- **[P2]** [Requested-depth exception, skill lines 66–73](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L66-L73) and [review limits, lines 54–61](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-review/SKILL.md#L54-L61).
- **[P3]** [Pinned mode state, runtime lines 42–75](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-runtime.js#L42-L75) and [later path hashing, lines 46–57](https://github.com/DietrichGebert/ponytail/blob/552acd5efd0aeae2583a12efe39373d2f076f25e/hooks/ponytail-runtime.js#L46-L57).
- **[P4]** [Host envelopes, lines 99–159](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-runtime.js#L99-L159) and [MCP instruction server, lines 1–52](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/ponytail-mcp/index.js#L1-L52).
- **[H0]** [Headroom frozen comparison](https://github.com/headroomlabs-ai/headroom/compare/1cf496612e781ef8d67ff87ee4f78037492f0bc7...5a516b54afd50156521638645a9063992e395a7b) and [observed v0.40.0 release](https://github.com/headroomlabs-ai/headroom/releases/tag/v0.40.0).
- **[H1]** [Conditional error protection, router lines 6098–6116](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/content_router.py#L6098-L6116) and [size/status decision, lines 7192–7213](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/content_router.py#L7192-L7213).
- **[H2]** [Inflation rollback, compress.py lines 300–313](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/compress.py#L300-L313) and [pipeline exception behavior, lines 347–372](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/transforms/pipeline.py#L347-L372).
- **[H3]** [Store retrieval/expiry, lines 458–482](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/cache/compression_store.py#L458-L482), [recovery defaults, lines 66–80](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/ccr/response_handler.py#L66-L80), and [explicit misses, lines 185–255](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/ccr/response_handler.py#L185-L255).
- **[H4]** [Responses tool/read exclusions, lines 2401–2430](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/openai.py#L2401-L2430), [WebSocket deadline handling, lines 8411–8454](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/openai.py#L8411-L8454), and [first-frame compaction failure, lines 8716–8730](https://github.com/headroomlabs-ai/headroom/blob/1cf496612e781ef8d67ff87ee4f78037492f0bc7/headroom/proxy/handlers/openai.py#L8716-L8730).
- **[J1]** Official [models](https://docs.typesafe.ai/models), [HTTP API](https://docs.typesafe.ai/api), [confidence semantics](https://docs.typesafe.ai/confidence), [Score](https://docs.typesafe.ai/primitives/score), and [jev-1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

`RESEARCH_PROVENANCE.md` indexes the longer historical dossiers. Their older
monetary framing is superseded by this report and `TOKEN_EFFICIENCY.md`.
