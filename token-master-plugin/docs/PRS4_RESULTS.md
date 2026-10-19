# PRS-4 results: v7 with a cache-stable system prompt

PRS-4 is a pre-registered live study. It ran on October 18, 2026, from 21:56 to 22:08 UTC.
Protocol: [PRS4_PROTOCOL.md](PRS4_PROTOCOL.md). Evidence: `evidence/prs4-20261018/study/`
(`summary.json`, `REPORT.md`, `results.jsonl`, gateway logs).

- The protocol record (`protocol.json`, sha256 `caa7b272…`) was frozen before the first study call.
- `analyze` re-checked every frozen hash and recounted every session from its raw captures.
- `analyze` also checked every graded session against the provider's own bill. The largest
  difference was 0.0 units.

## Result

**Under continuous use, `tm8` (v7 plus the cache-stable system prompt) had 49.8% lower billed
cost per finished task than `stock` (95% CI −57.1% to −42.9%).**

- `stock` is a Copilot-CLI-shaped agent without TokenMaster, as in PRS-3.
- "Continuous use" means that the sessions of one repository run back to back.
- All 360 graded sessions passed: 120 of 120 in each arm.
- The pre-registered goal rule is met. It required at least 30% lower billed cost per finished
  task, Holm p below 0.05, and at most 3 fewer passes than stock.
- The whole 95% CI also lies beyond −30%.

| Arm | Passed | Billed per session | Calls per session | Warm starts |
| --- | ---: | ---: | ---: | ---: |
| stock | 120/120 | 13,400 | 4.97 | 0 of 120 |
| tm7 (v6 + v7 tools and hint) | 120/120 | 10,963 | 4.51 | 0 of 120 |
| **tm8** (tm7 + cache-stable system prompt) | **120/120** | **6,727** | 4.62 | **119 of 120** |

Billed cost is in units of one uncached input token. It uses the provider's own price table:
cache read 0.1, cache write 1.25, output 5. A warm start is a first call that read at least
half of its input from the cache.

| Family | Comparison | Change per finished task (95% CI) | Holm p | Tasks lower |
| --- | --- | ---: | ---: | ---: |
| primary | tm8 vs stock | **−49.8%** (−57.1%, −42.9%) | < 0.00001 | 24 of 24 |
| primary | tm7 vs stock | −18.2% (−26.6%, −9.5%) | 0.00049 | 18 of 24 |
| attribution | tm8 vs tm7 | −38.6% (−42.4%, −34.7%) | < 0.00001 | 24 of 24 |
| sensitivity | tm8_cold vs stock | −18.9% (−28.0%, −10.4%) | no claim | 17 of 24 |

`tm8_cold` is not a separate run. It re-prices the tm8 sessions as if every first call
missed the cache.

## What the result means

- **The cache-stable system prompt gave most of tm8's saving.**
  - Per session, tm8 cost 6,673 units less than stock.
  - Warm first calls gave 4,137 of those units. This is the gap between tm8_cold and tm8.
  - The other 2,536 units are the gap between stock and tm8_cold.
- **tm8's extra saving over tm7 came from price, not from fewer tokens.**
  - Against stock, raw tokens fell 14.0% in tm8 and 14.6% in tm7. tm8 used 0.6% more raw
    tokens than tm7.
  - tm8's first calls read 92.7% of their input from the cache, at 0.1 per token.
  - tm7's first calls read nothing from the cache. They wrote their input to it, at 1.25 per
    token.
- **v7 cut cost again on new tasks.** The point estimate is smaller than in PRS-3.
  - tm7 cost 18.2% less than stock. With the PRS-3 metric, it cost 18.1% less.
  - In PRS-3, v7 cost 22.0% less than stock with the PRS-3 metric.
  - Re-priced after that study at the provider's prices, the PRS-3 saving was 23.2%. That
    re-pricing was not pre-registered.
- **The result depends on the usage regime.**
  - In this study, the sessions of one repository ran back to back with 8 workers.
  - 119 of 120 tm8 sessions started warm. The one cold start, P17-tm8-r1, was among the
    first tm8 sessions of the run.
  - In one probe, a cached prompt was still in the cache 6.5 minutes after its last use. It
    was gone after 31 minutes ([evidence](../../evidence/cache-probe-20261018/ttl.jsonl)).
  - Inference: a tm8 session starts cold if no other session sent the same system prompt
    within the cache lifetime. The probe puts that lifetime between 6.5 and 31 minutes.
  - Inference: for cold sessions, the sensitivity result applies. That is −18.9%, close to
    tm7's −18.2%.
- **Inference: the relative saving falls as sessions get longer.**
  - The cache-stable system prompt changes only the price of the first call.
  - So its saving per session does not grow with the number of calls.
  - Sessions here averaged 4.5 to 5.0 calls. PRS-3 stock sessions averaged 5.12 calls.

## Limits

- **Product scope.**
  - Only the native Copilot route applies the cache-stable system prompt, because only that
    route sees the request. That route is experimental and read-only.
  - The default install (the `tokenmaster-nav` MCP server and the v6 `view` hook) cannot apply
    it. That hook applies v6 only to whole-file `view` results.
  - No PRS study measured the default install. Inference: its users should not expect more
    than the tm7 result.
- One model (`gpt-6-astra`), one provider price table, and one repository snapshot (`703aa20`).
- The category mix (locate 6, logic 6, impact 4, docs 4, edit 4) equals PRS-3's.
- One session (P13-tm8-r3) had an infrastructure failure: an HTTP 502 error on its third
  call. It was re-run once under the pre-declared rule, and the re-run passed. The analysis
  uses the re-run.
- The study writes the session folder as `C:/Users/dev/.copilot/session-state/<32 hex>`.
  `stable_session_prefix` has not run inside a live interactive Copilot CLI session.
