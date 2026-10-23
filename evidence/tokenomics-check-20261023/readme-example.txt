Copilot CLI versions in the captured system prompts: ['1.0.98', '1.0.98', '1.0.98']
Prompt: Which function in hello.py returns a greeting? Reply with the function name only.
Session 1: stock Copilot CLI. Sessions 2 and 3: through the TokenMaster launcher (lean tool set, bridge).
Reports regenerated after the October 23 attribution fix, on the same session store, with TokenMaster reinstalled.

$ tokenomics.py session --compact
╭────────────────────────────────────────────────────╮
│                                                    │
│   TokenMaster Tokenomics · Copilot CLI · Session   │
│                                                    │
╰────────────────────────────────────────────────────╯

┌──────────┬───────────────┬──────────────┬────────────┬──────────────┬────────────────┬───────────────┐
│ Session  │ Models        │ Total Tokens │ Cost (USD) │ TokenMaster  │ Saved Tokens ≈ │ Saved (USD) ≈ │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 579e5c15 │ • gpt-6-astra │       22,278 │      $0.15 │ -            │              - │             - │
│ repo     │               │              │            │              │                │               │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 9b2700f4 │ • gpt-6-astra │       16,847 │      $0.09 │ lean+bridge  │         16,674 │         $0.01 │
│ repo     │               │              │            │              │                │               │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 5690993e │ • gpt-6-astra │       16,844 │      $0.02 │ lean+bridge  │         16,674 │         $0.07 │
│ repo     │               │              │            │              │                │               │
├──────────┼───────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ Total    │               │       55,969 │      $0.26 │ 2/3 sessions │         33,348 │         $0.08 │
└──────────┴───────────────┴──────────────┴────────────┴──────────────┴────────────────┴───────────────┘

TokenMaster savings (estimated)
  TokenMaster sessions          2 of 3  6 model calls
  Tokens, actual                33,691  GitHub's token counts
  Tokens without TokenMaster ≈  67,039  saved 33,348 (49.7%)
  Cost, actual                   $0.11  GitHub's own charge per call
  Cost without TokenMaster ≈     $0.18  saved $0.08 (41.0%)
    of which lean tool set       $0.03  33,348 fewer fixed tokens, priced as cache reads
    of which first calls         $0.04  prompt-cache writes on each session's first call
  The estimate assumes stock Copilot CLI would have made the same model calls. Not counted: calls saved by graph navigation, v6 shaping, other behavior changes.
  Calibration: Copilot CLI 1.0.98, probe of October 23, 2026; other Copilot CLI versions send other fixed prompts. On the measured A/B runs (1.0.78-3), this method gave 72% to 125% of the measured token saving. Method: docs/TOKENOMICS.md.
  Measured on Copilot CLI 1.0.78-3 (45 Django tasks, October 22, 2026): full TokenMaster used 53.4% (gpt-6-astra) and 51.6% (claude-opus-5.5) fewer raw tokens than stock.

Data: <work>\home\copilot\session-store.db · 2 TokenMaster launches on record · times are local
Tip: in Copilot CLI, `! [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); & "C:\Users\shyamsridhar\code\Tokenmaster\.token-master-dev\Scripts\python.exe" "<work>\home\copilot\token-master\tokenomics.py"` shows this report without spending model tokens; /tokenomics asks the model to run it.

$ tokenomics.py daily --full
╭──────────────────────────────────────────────────╮
│                                                  │
│   TokenMaster Tokenomics · Copilot CLI · Daily   │
│                                                  │
╰──────────────────────────────────────────────────╯

┌────────────┬───────────────┬───────┬───────┬────────┬─────────────┬────────────┬──────────────┬────────────┬──────────────┬────────────────┬───────────────┐
│ Date       │ Models        │ Calls │ Input │ Output │ Cache Write │ Cache Read │ Total Tokens │ Cost (USD) │ TokenMaster  │ Saved Tokens ≈ │ Saved (USD) ≈ │
├────────────┼───────────────┼───────┼───────┼────────┼─────────────┼────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ 2026-10-23 │ • gpt-6-astra │     8 │    24 │    180 │      17,000 │     38,765 │       55,969 │      $0.26 │ 2/3 sessions │ 33,348 (49.7%) │ $0.08 (41.0%) │
├────────────┼───────────────┼───────┼───────┼────────┼─────────────┼────────────┼──────────────┼────────────┼──────────────┼────────────────┼───────────────┤
│ Total      │               │     8 │    24 │    180 │      17,000 │     38,765 │       55,969 │      $0.26 │ 2/3 sessions │ 33,348 (49.7%) │ $0.08 (41.0%) │
└────────────┴───────────────┴───────┴───────┴────────┴─────────────┴────────────┴──────────────┴────────────┴──────────────┴────────────────┴───────────────┘

TokenMaster savings (estimated)
  TokenMaster sessions          2 of 3  6 model calls
  Tokens, actual                33,691  GitHub's token counts
  Tokens without TokenMaster ≈  67,039  saved 33,348 (49.7%)
  Cost, actual                   $0.11  GitHub's own charge per call
  Cost without TokenMaster ≈     $0.18  saved $0.08 (41.0%)
    of which lean tool set       $0.03  33,348 fewer fixed tokens, priced as cache reads
    of which first calls         $0.04  prompt-cache writes on each session's first call
  The estimate assumes stock Copilot CLI would have made the same model calls. Not counted: calls saved by graph navigation, v6 shaping, other behavior changes.
  Calibration: Copilot CLI 1.0.98, probe of October 23, 2026; other Copilot CLI versions send other fixed prompts. On the measured A/B runs (1.0.78-3), this method gave 72% to 125% of the measured token saving. Method: docs/TOKENOMICS.md.
  Measured on Copilot CLI 1.0.78-3 (45 Django tasks, October 22, 2026): full TokenMaster used 53.4% (gpt-6-astra) and 51.6% (claude-opus-5.5) fewer raw tokens than stock.

Data: <work>\home\copilot\session-store.db · 2 TokenMaster launches on record · times are local
Tip: in Copilot CLI, `! [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); & "C:\Users\shyamsridhar\code\Tokenmaster\.token-master-dev\Scripts\python.exe" "<work>\home\copilot\token-master\tokenomics.py"` shows this report without spending model tokens; /tokenomics asks the model to run it.
