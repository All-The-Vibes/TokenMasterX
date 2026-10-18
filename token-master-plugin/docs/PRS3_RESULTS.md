# PRS-3 results: graph-first TokenMaster v7 cuts cost by 22%

**Run:** October 18, 2026, 8 workers.
**Protocol:** [PRS3_PROTOCOL.md](PRS3_PROTOCOL.md). It was frozen by SHA-256 before
the run (`protocol.json` `f2e67c76…`), and v7 was frozen before any task was read.
**Evidence:** `evidence/prs3-20261018/study/` (`summary.json`, `REPORT.md`,
`results.jsonl`). The raw captures stay local because they contain the captured
Copilot CLI system prompt.

## Bottom line

1. **v7 lowers real cost by 22.0% against stock.**
   - 95% CI: −35.4% to −8.9%. Holm p = 0.006.
   - Quality was unchanged at 120/120 passes.
   - This meets the pre-registered "v7 works" criterion, and tm7 was the cheapest arm.
2. **v6 replicated on fresh tasks: −13.0%** against stock.
   - 95% CI: −19.3% to −6.7%. Holm p = 0.0001.
   - PRS-2 had measured −11.6%.
3. **v7's extra saving over v6 is not statistically established.**
   - Against v6: −10.4% (CI −21.4% to +0.1%, p = 0.16).
   - Against v6 plus the one-sentence advice alone: −5.8% (p = 0.77).
   - The advice sentence alone saved 4.8% against v6 (CI −8.9% to −0.2%). This is not
     significant after Holm correction (p = 0.12).
4. **v7's benefit is concentrated on "who calls X" questions** (exploratory):
   - impact tasks cost 52% less than with v6;
   - locate, logic and docs tasks cost about the same;
   - edit tasks cost 9% more.
5. **The goal of at least 30% savings is not met.** The best estimate is 22%. 30% lies
   inside the confidence interval, so it is not ruled out either.

## What ran

- 4 arms × 24 fresh tasks × 5 repeats = 480 sessions.
  - There were no infrastructure failures and no re-runs.
  - No call needed an estimated token count.
  - Every token was recounted from the raw captures.
- The tasks:
  - Two agent sessions wrote them without being told the arms.
  - Their answers were checked against the source after v7 was frozen.
  - Two tasks were corrected before `prepare`; see the protocol.
- Every arm used parallel tool calls and the same logical working directory.
- Cost per session = uncached input + 0.1 × cached input + 8 × output.

## Results (all 24 tasks are confirmatory)

| Arm | Passed | Cost | Raw tokens | Uncached input | Cached input | Output | Calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stock | 120/120 | 2,027,995 | 4,527,778 | 1,367,100 | 3,117,029 | 43,649 | 615 |
| tm6 | 120/120 | 1,764,479 | 3,903,955 | 1,132,690 | 2,726,371 | 44,894 | 623 |
| tm6_hint | 120/120 | 1,679,456 | 3,806,310 | 1,039,774 | 2,720,583 | 45,953 | 642 |
| **tm7** | **120/120** | **1,581,512** | **3,901,007** | **996,089** | **2,867,585** | **37,333** | **647** |

| Family | Comparison | Cost (95% CI) | Holm p | Raw tokens | Tasks lower/higher | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| primary | tm6 vs stock | −13.0% (−19.3%, −6.7%) | 0.0001 | −13.8% | 20/4 | **lower cost** |
| primary | **tm7 vs stock** | **−22.0% (−35.4%, −8.9%)** | **0.006** | −13.8% | 18/6 | **lower cost** |
| primary | tm7 vs tm6 | −10.4% (−21.4%, +0.1%) | 0.160 | −0.1% | 15/9 | no significant difference |
| attribution | tm6_hint vs tm6 | −4.8% (−8.9%, −0.2%) | 0.121 | −2.5% | 14/10 | no significant difference |
| attribution | tm7 vs tm6_hint | −5.8% (−17.2%, +4.3%) | 0.768 | +2.5% | 13/11 | no significant difference |

Every comparison had 120 vs 120 paired passes.

**Sensitivity (tm7 vs stock).** These secondary endpoints were not Holm-adjusted.

| Endpoint | Change (95% CI) |
| --- | ---: |
| Cost, cached input at 25% | −19.4% (−33.2%, −5.2%) |
| Cost, output at 4× | −22.7% (−36.4%, −9.1%) |
| Cost with a 1.25× cache-write premium | −22.8% (−36.1%, −9.7%) |
| Uncached input | −27.1% (−40.4%, −13.5%) |
| Raw tokens | −13.8% (−30.6%, +4.0%) |
| Model calls | +5.2% (−4.7%, +16.2%) |

## Predictions against outcomes

| Comparison | Predicted | Observed |
| --- | ---: | ---: |
| tm6 vs stock | −8% to −18% | −13.0% |
| tm7 vs stock | −15% to −30% | −22.0% |
| tm7 vs tm6 | −5% to −15% | −10.4% (not significant) |
| tm6_hint vs tm6 | −5% to +5% | −4.8% (not significant) |
| tm7 vs tm6_hint | −5% to −15% | −5.8% (not significant) |

All five point estimates fell inside their predicted ranges. Three of the five
comparisons did not reach significance.

## Diagnostics

- **The model used the new tools.**
  - 89 of 120 tm7 sessions made at least one navigation call, and the average was 2.39
    per session: `locate` 176, `read_symbol` 91, `impact` 20.
  - Compared with tm6, tm7 made 35% fewer `view` calls and 52% fewer `grep` calls.
- **Prompt caching treated every arm alike.**
  - All 480 first calls wrote the cache and none read it; every later call read it.
  - The 2,684-token start of the system prompt is identical across sessions, yet it was
    never reused from one session to the next. The cause is not established; each
    session sends its own `prompt_cache_key`.

## Why v7 is cheaper

- **Less new input.** Exact symbols and call lists replace whole-file views and broad
  searches. Uncached input fell 27.1% against stock and 12.1% against v6.
- **Less output.** tm7 wrote 17% fewer output tokens than v6 (37,333 against 44,894).
  At 8× weight, that is about a third of its cost edge over v6.
- **Slightly more calls.** tm7 made 5% more calls than stock (not significant), so raw
  tokens fell less (−13.8%) than cost.

## Exploratory breakdown by category (not pre-registered)

| Category (tasks) | tm6 vs stock | tm7 vs stock | tm7 vs tm6 | tm6_hint vs tm6 |
| --- | ---: | ---: | ---: | ---: |
| locate (6) | −9.5% | −9.6% | −0.1% | −3.9% |
| logic (6) | −2.6% | −3.1% | −0.5% | −6.0% |
| impact (4) | −25.9% | **−64.1%** | **−51.5%** | −9.8% |
| docs (4) | −16.2% | −18.2% | −2.5% | +0.1% |
| edit (4) | −11.9% | −4.0% | +9.0% | −0.4% |

Small subgroups like these are hypotheses for the next study, not findings.

## What this means for the product

- **Make v6 the default request policy.** Two pre-registered studies replicated it, at
  −11.6% and −13.0%.
- **v7 is the best measured configuration.**
  - It is 22% cheaper than stock at equal quality.
  - Its CI against v6 reaches only +0.1%, so v7 is very unlikely to cost more than v6.
  - It is a sound default, as long as the claim stays at "22% against stock".
  - "Better than v6" is not proven.

## Next levers toward 30% (hypotheses to test, not results)

1. **First-call caching across sessions.**
   - Every session paid full price for about 3,600 first-call input tokens.
   - Reading them from the cache would be worth about 14% of stock's cost.
   - This needs a test of a stable cache key per repository.
2. **Edit tasks:** find out why tm7 cost 9% more than v6 on them.
3. **Output tokens:** v7 already cut them by 17%; terser final answers may cut more.

## Limits

1. One model, one repository and 24 tasks. A Copilot-CLI-shaped harness, not
   `copilot.exe`.
2. The cost weights are assumptions. GitHub Copilot subscriptions bill premium
   requests, not tokens.
3. With 24 task clusters, a difference of about 10% can stay non-significant, as
   tm7 vs tm6 did.
4. The author of v7 also built this harness. The mitigations are listed in the protocol.
