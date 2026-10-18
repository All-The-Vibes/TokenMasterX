# PRS-2 results: cache-native TokenMaster v6 lowers cost

**Run:** October 18, 2026, 8 workers.
**Protocol:** [PRS2_PROTOCOL.md](PRS2_PROTOCOL.md), frozen by SHA-256 before the run.
**Evidence:** `evidence/prs2-20261018/study/` (`summary.json`, `REPORT.md`,
`results.jsonl`). The raw captures stay local because they contain the captured
Copilot CLI system prompt.

## Bottom line

1. **v6 lowers real cost.** On 12 fresh tasks, written by an agent that was not told
   the arms, it cut cost by **11.6%** (95% CI −20.8% to −3.8%, Holm p = 0.014) and
   raw tokens by **17.2%**. Quality was unchanged at 36/36. This meets the
   pre-registered success criterion.
2. **The result holds under every pricing assumption tested** (−11.6% to −13.1%),
   and on the 12 older tasks (−16.8%, 95% CI −24.7% to −8.4%).
3. **The graph tools as shipped raise cost:** +12.9% against stock and +27.7% against
   v6 alone. Every call carries their tool definitions plus a 1,383-token agent text,
   and `codegraph_explore` returns large source dumps. `graphify-nav-find` itself is cheap.
4. **The goal of at least 30% savings is not met yet.**

## What ran

- 3 arms × 24 tasks × 3 repeats = 216 sessions, plus 1 pre-declared infrastructure
  re-run (`T11-tm6_graph-r3`, upstream HTTP 502).
- Every token count was recounted from the raw captures. No call needed an
  estimated count.
- Every arm used parallel tool calls and the same logical working directory.
  Cost per session = uncached input + 0.1 × cached input + 8 × output.

## Primary set (12 fresh tasks, confirmatory)

| Arm | Passed | Cost | Raw tokens | Uncached input | Cached input | Calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| stock | 36/36 | 473,611 | 1,044,322 | 319,191 | 714,763 | 172 |
| **tm6** | **36/36** | **418,706** | **864,793** | **283,189** | **571,812** | **160** |
| tm6_graph | 36/36 | 534,683 | 1,284,012 | 368,202 | 906,329 | 166 |

| Comparison | Cost (95% CI) | Holm p | Raw tokens | Passed (paired) | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| tm6 vs stock | **−11.6%** (−20.8%, −3.8%) | 0.014 | −17.2% | 36 vs 36 | **lower cost** |
| tm6_graph vs stock | +12.9% (+2.0%, +25.3%) | 0.027 | +22.9% | 36 vs 36 | higher cost |
| tm6_graph vs tm6 | +27.7% (+17.7%, +38.6%) | 0.003 | +48.5% | 36 vs 36 | higher cost |

**Sensitivity (tm6 vs stock, primary set).** The secondary endpoints were not
Holm-adjusted.

| Endpoint | Change (95% CI) |
| --- | ---: |
| Cost, cached input at 25% | −13.1% (−23.9%, −3.8%) |
| Cost, output at 4× | −12.2% (−21.7%, −4.1%) |
| Cost with a 1.25× cache-write premium | −11.6% (−20.6%, −3.9%) |
| Uncached input | −11.3% (−19.8%, −3.5%) |
| Model calls | −7.0% (−15.4%, +0.6%) |

## Secondary set (12 PRS-1 tasks, exposed)

| Comparison | Cost (95% CI) | Holm p | Raw tokens | Passed (paired) | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| tm6 vs stock | −16.8% (−24.7%, −8.4%) | 0.003 | −22.7% | 36 vs 36 | lower cost |
| tm6_graph vs stock | +3.8% (−12.3%, +23.1%) | 0.424 | +20.2% | 35 vs 36 | no significant difference |
| tm6_graph vs tm6 | +24.7% (+5.5%, +45.2%) | 0.042 | +55.5% | 35 vs 36 | higher cost |

## Why v6 works

- **It shapes each tool result once, in a deterministic way, so earlier messages
  never change** and the provider keeps reusing its cache.
- **It shrinks what enters the conversation.** Uncached input fell 11.3%, and the
  smaller history made every later call cheaper: cached input fell from 714,763 to
  571,812 tokens (−20%).
- **The model compensated a little, not much.** It made 7% fewer calls (not
  significant), and every answer stayed correct.

## Why the graph arm lost

- **Fixed overhead on every call.** Six graph tool definitions plus the 1,383-token
  routing text are re-sent each time. Cached, they are cheap per call, but they add up.
- **`codegraph_explore` returns verbatim source,** large even after v6 caps it.
- **The routing text tells the model to verify graph answers by reading the file.**
  In the primary set it still made 85 file reads (stock: 102).

The fix is a graph-first redesign on graphify's graph: compact `locate`, `read` and
`impact` tools, terse tool text, and no source dumps.

## Limits

One model, one repository and 24 tasks. A Copilot-CLI-shaped harness, not
`copilot.exe`. The cost weights are assumptions; GitHub Copilot subscriptions bill
premium requests, not tokens. The author of v6 built the harness; the mitigations
are listed in the protocol.
