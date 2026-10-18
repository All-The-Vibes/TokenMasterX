# PRS-4 protocol (pre-registered)

Written on October 18, 2026, before any PRS-4 study call. The harness is
`token-master-plugin/evals/run_prs4_study.py`. Its `prepare` step records the SHA-256
of this document, and `run` refuses to start if this document changes.

## Question

Under continuous use, does TokenMaster v7 with a cache-stable system prompt (`tm8`) cost at
least 30% less than stock Copilot CLI per finished task, at equal quality? "Continuous use"
means that the sessions of one repository run back to back (see "Usage regime").

## Background measured before this study

- PRS-3: v7 (`tm7`) cost 22.0% less than stock with the PRS-3 metric. Re-priced after the
  study with the provider's own price table, the saving was 23.2% (not pre-registered).
- None of the 480 PRS-3 first calls read the provider cache. Copilot CLI writes each
  session's own folder into its system prompt (`Session folder: <path>`), so no two
  sessions share a cached prefix.
- Cache probes ([evidence](../../evidence/cache-probe-20261018/results.json)): with that
  line moved to the first user message, a new session's first call read 3,401 of 3,564
  input tokens from the cache.

## Arms

| Arm | Definition |
| --- | --- |
| `stock` | Copilot-CLI-shaped agent with parallel tool calls; no TokenMaster (as in PRS-3). |
| `tm7` | stock + request-policy-v6 + the v7 navigation tools and 66-token hint (as in PRS-3). |
| `tm8` | tm7 + `stable_session_prefix` on every request. |

`stable_session_prefix` is product code in `brainspace/native_transport.py`. The native
Copilot route applies it in `NativeResponsesTransport.bind` to every request. It moves the
`Session folder:` line (the path must contain `session-state`) from the system prompt to the
start of the first user message, and puts a fixed line in its place. It matches the line on
each message's joined text, so a different split into text blocks gives the same result. The
`tm8` arm applies the same function to every study request.

**Product scope.** The arms are request-level configurations of a Copilot-CLI-shaped agent,
as in PRS-3. In the product, the stable prefix and v6 on every tool result run only where
TokenMaster sees the request: the native Copilot route, which is experimental and read-only.
The default install (the `tokenmaster-nav` MCP server and the v6 `view` hook) cannot apply the
stable prefix. A result for `tm8` is therefore not a result for the default install.

## Tasks

- 24 fresh tasks, P01–P24, written by two agent sessions that were not told the arms or
  the purpose of the study.
- Category quota, as in PRS-3: locate 6, logic 6, impact 4, docs 4, edit 4.
- The topics of T01–T12, N01–N12 and M01–M24 are excluded.
- The assistant re-checks every expected answer against the snapshot only after the
  treatment code is committed, and records every correction in the task file's provenance.

## Design

- 24 tasks × 3 arms × 5 repeats = 360 sessions.
- The schedule is shuffled within each repeat (seed 20261021). It runs with 8 workers; the
  protocol freezes this number, and `run` refuses any other.
- Model `gpt-6-astra`, reasoning effort low, at most 30 calls per session, output cap 4,096.
- Each session sends its own `prompt_cache_key`, as Copilot CLI does.
- The workspace is `git archive 703aa20`, shown to the model as `C:\work\tokenmaster`.
- The smoke check runs one session per arm and then a second `tm8` session, with one worker.
  Smoke sessions add a fixed line to the system prompt, so they cannot warm the study's
  cached prefix. The second `tm8` smoke session must start warm; if it does not, the study
  stops before `run` and the cause is reported.

## Usage regime

- Continuous use: the sessions of one repository run back to back.
- A `tm8` session shares its prefix only with other `tm8` sessions. It starts warm when
  another `tm8` session wrote that prefix within the provider's cache lifetime.
- The report counts warm starts: first calls that read at least 50% of their input from
  the cache.
- The primary result does not apply to isolated sessions. For them, the sensitivity arm
  `tm8_cold` re-prices each `tm8` first call's cached tokens as cache writes.
- The first call is a fixed cost per session, so the relative saving falls as sessions get
  longer. The report gives calls per session (PRS-3 stock: 5.12) and the absolute saving per
  session next to the headline.

## Endpoints

- **Primary: billed cost per finished task.** For each arm, sum the billed cost of all
  graded sessions, failures included, and divide by the passed sessions.
- Billed cost = (input − cached − cache_write) + 0.1 × cached + 1.25 × cache_write
  + 5 × output, from provider-reported usage. These are the provider's own prices relative
  to uncached input (`copilot_usage` in every response).
- On all 480 PRS-3 sessions this formula equals the sum of the provider's per-call bills
  (largest difference 0.0). The analysis repeats this check on every PRS-4 session. It stops
  if any call shows a different price, or if any session differs by more than 0.5 units.
- Secondary: the PRS-3 metric (`cost`), raw tokens, uncached input, calls, the other PRS-3
  sensitivity weights, and pass rate.

## Statistics

- Ratio of sums over paired sessions, a two-stage cluster bootstrap 95% CI, and an exact
  Wilcoxon test on per-task mean differences, all as in PRS-3.
- The change in billed cost per finished task gets its own two-stage cluster bootstrap 95% CI
  (2,000 resamples of tasks, then of sessions within each task).
- Holm correction within each family: primary {tm8 vs stock, tm7 vs stock}; attribution
  {tm8 vs tm7}. The sensitivity comparison {tm8_cold vs stock} is reported without a claim.
- Each comparison gets the PRS-3 verdict rule, applied to billed cost.
- `analyze` re-checks every frozen hash before it computes anything.

## Goal rule

- **Met** if, for tm8 vs stock: billed cost per finished task is at least 30% lower (point
  estimate), the Holm p-value of the billed comparison is below 0.05, and tm8 passes at least
  as many sessions as stock minus 3.
- **Confident** if the goal is met and the upper bound of the per-finished-task 95% CI is at
  or below −30%.
- Any other result is reported as not met.

## Failures

An HTTP 429, 5xx or network failure, or a harness failure before the first model call,
is an infrastructure failure and is re-run once. Every other failure counts, with all its
tokens.

## Disclosures

- The `tm8` rewrite was designed with PRS-3 captures and the cache probes. The tasks are new.
- The category mix equals PRS-3's. In PRS-3, v7 saved most on impact tasks.
- The study writes the session folder as `C:/Users/dev/.copilot/session-state/<32 hex>`.
  The `Session folder: <path>` line format comes from the captured Copilot CLI prompt.
- A cache-lifetime probe ran before this study and is reported separately; it does not
  change this analysis.
- The task authors' one-line summaries reached the assistant before the treatment code was
  committed. After that point the code changed only to fix a red-team review: line matching
  on joined text, the `session-state` requirement, the version string, frozen workers, smoke
  isolation, the billing stop rule, the per-finished-task CI and the goal-rule wording. None of
  these depends on task content.
- The analysis code was run end to end on PRS-3 data before `prepare`, with `tm6_hint`
  standing in for `tm8`, to catch errors. That dry run says nothing about `tm8`.
