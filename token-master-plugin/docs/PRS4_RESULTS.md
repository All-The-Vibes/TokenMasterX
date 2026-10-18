# PRS-4 results: v7 with a cache-stable system prompt

Pre-registered live study, run on October 18, 2026. Protocol:
[PRS4_PROTOCOL.md](PRS4_PROTOCOL.md). Evidence: `evidence/prs4-20261018/study/`
(`summary.json`, `REPORT.md`, `results.jsonl`, gateway logs). The protocol was frozen at
sha256 `caa7b272…` before the first study call. `analyze` re-checked every frozen hash,
recounted every session from its raw captures, and checked every session against the
provider's own bill. The largest difference was 0.0.

## Result

**Under continuous use, `tm8` (v7 plus the cache-stable system prompt) cost 49.8% less than
stock Copilot CLI per finished task (95% CI −57.1% to −42.9%).** All 360 graded sessions
passed: 120 of 120 in each arm. The pre-registered goal rule is met, and the whole 95% CI lies
beyond −30%.

| Arm | Passed | Billed per session | Calls per session | First calls served from cache |
| --- | ---: | ---: | ---: | ---: |
| stock | 120/120 | 13,400 | 4.97 | 0 of 120 |
| tm7 (v6 + v7 tools) | 120/120 | 10,963 | 4.51 | 0 of 120 |
| **tm8** (tm7 + cache-stable prompt) | **120/120** | **6,727** | 4.62 | **119 of 120** |

Billed cost is in units of one uncached input token, priced with the provider's own table:
cache read 0.1, cache write 1.25, output 5.

| Family | Comparison | Change per finished task (95% CI) | Holm p | Tasks lower |
| --- | --- | ---: | ---: | ---: |
| primary | tm8 vs stock | **−49.8%** (−57.1%, −42.9%) | < 0.00001 | 24 of 24 |
| primary | tm7 vs stock | −18.2% (−26.6%, −9.5%) | 0.00049 | 18 of 24 |
| attribution | tm8 vs tm7 | −38.6% (−42.4%, −34.7%) | < 0.00001 | 24 of 24 |
| sensitivity | tm8, every first call re-priced as a cache miss, vs stock | −18.9% (−28.0%, −10.4%) | no claim | 17 of 24 |

## What the result means

- **The cache fix is the larger lever.** Raw tokens fell about 14% in both TokenMaster arms.
  tm8's extra saving comes from billing: its first calls read the system prompt from the
  cache (0.1 per token) instead of writing it again (1.25 per token).
- **v7 replicated on new tasks.** tm7 saved 18.2% against stock (PRS-3: 22.0% with the
  PRS-3 metric, 23.2% at the provider's prices).
- **The result depends on the usage regime.** In this study, the sessions of one repository
  ran back to back with 8 workers, and 119 of 120 tm8 sessions started warm.
  - A separate probe found that the cached prompt survives at least 6.5 minutes and less
    than 31 minutes ([evidence](../../evidence/cache-probe-20261018/ttl.jsonl)).
  - Isolated sessions, more than about half an hour apart, get the sensitivity result:
    about −19%, the same as tm7.
- **The relative saving falls as sessions get longer.** The fix saves a fixed amount per
  session: 6,673 units here, at about 4.6 calls per session.

## Limits

- **Product scope.** Only the native Copilot route applies the cache-stable prompt, because
  only that route sees the request. That route is experimental and read-only. The default
  install (the `tokenmaster-nav` MCP server and the v6 `view` hook) cannot apply it, so its
  users should expect at most the tm7 result.
- One model (`gpt-6-astra`), one provider price table, and one repository snapshot.
- The category mix (locate 6, logic 6, impact 4, docs 4, edit 4) equals PRS-3's.
- One session (P13-tm8-r3) failed for infrastructure reasons. It was re-run once under the
  pre-declared rule, and it passed.
- The study writes the session folder as `C:/Users/dev/.copilot/session-state/<32 hex>`.
  The rewrite has not run inside a live interactive Copilot CLI session.
