# PRS-1 results: TokenMaster on real repository tasks

**Run:** October 18, 2026, 00:45–00:59 (America/Chicago), 8 workers.
**Protocol:** [PRS1_PROTOCOL.md](PRS1_PROTOCOL.md), frozen by SHA-256 before the run.
**Evidence:** `evidence/prs1-20261018/` (`study/summary.json`, `study/REPORT.md`,
`study/results.jsonl`; raw captures stay local because they contain the captured
Copilot CLI system prompt).

## Bottom line

1. **No TokenMaster configuration reduced total tokens.** Measured against the
   unoptimized baseline, v5 compaction was +7.8%, graph routing was −1.1%, and
   graph + v5 was +4.8%. None is significant. Every 95% interval spans roughly −35%
   to +53%.
2. **v5 made cost worse under prompt caching.** Cache-weighted tokens (cached input
   at 10%) rose **+61.6%** (95% CI +19.6% to +111.0%). Graph + v5 rose +57.0%
   (+10.1% to +118.0%). Uncached input almost doubled (+94.8%).
3. **Quality held.** Every TokenMaster arm passed 36/36, the same as baseline.
4. **The largest effect came from a setting TokenMaster turns off.** Letting the model
   make parallel tool calls cut total tokens by 32.8% (95% CI −50.4% to −8.8%). The
   Holm-adjusted p is 0.11, so under the pre-declared rule this is not significant.
   TokenMaster's transport forces `parallel_tool_calls: false`.

The October 17 claims (−83%, −73%, −65.68%, −44%) are retracted. See the protocol
for the six design flaws behind them.

## What ran

- 7 arms × 12 tasks × 3 repeats = **252 sessions**, plus 1 pre-declared infrastructure
  re-run. 1,609 model calls and **14.29M provider-reported tokens** counted.
- `gpt-6-astra`, reasoning `low`. GitHub Copilot CLI's own system prompt is used
  (2,944 tokens). Workspace: this repository at commit `703aa20` (201 files).
- Tasks were written by a separate agent that was not told the arms, then
  independently verified: 3 locate, 3 logic, 2 impact, 2 docs, 2 edit.
- Every token count was recounted from raw captures with no mismatch. No call
  needed an estimated count. All gateway attempts returned HTTP 200 except one
  network error.

## Primary endpoint: provider-reported tokens (input + output)

| Arm | Passed | Total tokens | Uncached input | Cached input | Output | Calls | Tokens per success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 36/36 | 2,082,599 | 398,178 | 1,668,616 | 15,805 | 247 | 57,850 |
| baseline_parallel | 35/36 | 1,399,967 | 427,107 | 955,813 | 17,047 | 173 | 39,999 |
| ponytail | 34/36 | 2,498,333 | 477,812 | 2,004,303 | 16,218 | 251 | 73,480 |
| headroom | 35/36 | 1,820,351 | 363,965 | 1,440,490 | 15,896 | 245 | 52,010 |
| graph | 36/36 | 2,060,438 | 501,165 | 1,547,232 | 12,041 | 201 | 57,234 |
| v5 | 36/36 | 2,245,809 | 775,770 | 1,452,174 | 17,865 | 280 | 62,384 |
| graph_v5 | 36/36 | 2,182,011 | 758,044 | 1,411,122 | 12,845 | 212 | 60,611 |

## Pre-declared comparisons

Change is arm vs. reference (negative = fewer tokens). CIs come from a two-stage
cluster bootstrap. p is the exact Wilcoxon test on 12 per-task means. Holm adjusts
across all 7 comparisons.

| Comparison | Total tokens (95% CI) | p / Holm p | Cache-weighted, w=0.1 (95% CI) | Uncached input (95% CI) | Calls | Passed (paired) | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline_parallel vs baseline | **−32.8%** (−50.4%, −8.8%) | 0.016 / 0.113 | −7.1% (−20.0%, +8.2%) | +7.3% (−3.3%, +19.6%) | −30.0% | 35 vs 36 | no significant difference |
| ponytail vs baseline | +20.0% (−2.0%, +47.3%) | 0.034 / 0.205 | +19.6% (+6.1%, +38.1%) | +20.0% (+9.4%, +35.8%) | +1.6% | 34 vs 36 | no significant difference |
| headroom vs baseline | −12.6% (−29.3%, +7.9%) | 0.064 / 0.320 | −9.8% (−22.2%, +3.5%) | −8.6% (−18.9%, +1.7%) | −0.8% | 35 vs 36 | no significant difference |
| graph vs baseline | −1.1% (−35.1%, +42.1%) | 0.092 / 0.369 | +15.0% (−10.7%, +43.9%) | +25.9% (+5.3%, +50.1%) | −18.6% | 36 vs 36 | no significant difference |
| v5 vs baseline | +7.8% (−24.7%, +49.8%) | 0.233 / 0.467 | **+61.6% (+19.6%, +111.0%)** | **+94.8% (+47.0%, +151.2%)** | +13.4% | 36 vs 36 | no significant difference |
| graph_v5 vs baseline | +4.8% (−32.2%, +52.8%) | 0.129 / 0.388 | **+57.0% (+10.1%, +118.0%)** | **+90.4% (+35.2%, +165.2%)** | −14.2% | 36 vs 36 | no significant difference |
| graph_v5 vs graph | +5.9% (−6.6%, +17.6%) | 0.301 / 0.467 | **+36.5% (+8.0%, +69.4%)** | **+51.3% (+12.2%, +99.8%)** | +5.5% | 36 vs 36 | no significant difference |

Secondary endpoints were not Holm-adjusted. Unadjusted Wilcoxon p for cache-weighted
tokens: v5 0.012 (10 of 12 tasks higher), graph_v5 0.016, ponytail 0.012, graph 0.034.

## Per-task mean tokens (thousands, 3 repeats)

| Task | Category | baseline | baseline_parallel | ponytail | headroom | graph | v5 | graph_v5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T01 | locate | 33 | 38 | 35 | 34 | 52 | 33 | 47 |
| T02 | locate | 53 | 23 | 69 | 52 | 57 | 52 | 74 |
| T03 | locate | 29 | 22 | 59 | 27 | 45 | 47 | 51 |
| T04 | logic | 88 | 62 | 117 | 85 | 88 | 159 | 86 |
| T05 | logic | 65 | 41 | 79 | 61 | 108 | 82 | 130 |
| T06 | logic | 27 | 21 | 32 | 24 | 42 | 51 | 38 |
| T07 | impact | 38 | 23 | 54 | 38 | 40 | 57 | 40 |
| T08 | impact | 173 | 57 | 133 | 93 | 39 | 75 | 42 |
| T09 | docs | 26 | 26 | 42 | 24 | 52 | 31 | 52 |
| T10 | docs | 78 | 88 | 91 | 95 | 81 | 80 | 78 |
| T11 | edit | 41 | 28 | 67 | 32 | 42 | 40 | 48 |
| T12 | edit | 43 | 38 | 55 | 40 | 40 | 40 | 40 |

All 4 failed sessions were docs tasks: 1 in baseline_parallel, 2 in ponytail and
1 in headroom. Each one was a wrong answer.

## Why v5 did not save tokens (exploratory)

- **The compaction itself works.** v5 compacted 122 of its 286 requests and removed
  15.7% of the reference tokens on those requests, about 2,000 tokens each.
- **It breaks the provider's prompt cache.** Each turn rewrites the previous
  newest tool result, which invalidates the cached prefix from that message on.
  The cached share of input fell from 80.7% (baseline) to 65.2% (v5). Uncached
  input rose 94.8%.
- **The model worked harder.** v5 made 13.4% more calls (280 vs 247), 24 more
  `grep` calls, and 8 `retrieve_original` calls.
- **Real sessions are not dominated by re-sent large files.** Every call carries a
  ~3,700-token fixed prefix, plus many small `grep`/`glob` results and ranged views.
  v5 compacts only `view` results.

## Graph routing (exploratory)

- Its tool definitions and agent text add **+2,107 tokens to every call**
  (first-call input is 5,809 vs 3,702).
- It cut calls by 18.6%. It wins big on the caller/impact task T08 (173k → 39k),
  but costs more on most locate and logic tasks.
- codegraph 1.6.2 exposes only `codegraph_explore`, which returns verbatim source.
  The shipped agent text still names 8 codegraph tools.

## Comparators

- **Headroom** (default proxy settings): −12.6%, not significant, 35/36.
  First-call input was identical to baseline. The offline probe confirms it passes
  `view` output through verbatim by design.
- **Ponytail:** +20.0%, not significant, 34/36. Its ruleset adds 1,268 tokens to
  every call. Cache-weighted it costs +19.6% (+6.1% to +38.1%).

## Incidents and deviations

- `T06-v5-r1` hit an upstream network error after 6 calls (29,894 tokens). It was
  re-run once per protocol, and the original is excluded.
- Changes before the run (smoke-test tokenizer race; independent-review fixes) are
  listed in the protocol. Nothing was changed after the run started.

## What this does not show

- One model, one repository, 12 tasks: not representative of all coding work.
- A Copilot-CLI-shaped harness, not `copilot.exe` itself.
- The 10% cache weight is an assumption that matches common cached-input
  pricing. GitHub Copilot subscriptions bill premium requests, not tokens.

## Engineering follow-ups (not results; each needs its own test)

1. Stop forcing `parallel_tool_calls: false` (`brainspace/transport.py:145`,
   `brainspace/native_transport.py:69`).
2. Do not enable v5 by default. Any successor must avoid rewriting
   already-cached messages.
3. Offer graph tools for structural (caller/impact) questions only. Trim the
   1,383-token agent text and fix its stale codegraph tool names.
4. Add `view` to `exact_reuse._TOOLS` so exact duplicate reads can be reused.
