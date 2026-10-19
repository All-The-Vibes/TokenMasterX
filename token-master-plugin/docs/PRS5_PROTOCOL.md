# PRS-5 protocol (pre-registered)

Written on October 18, 2026, before any PRS-5 study call. The harness is
`token-master-plugin/evals/run_prs5_study.py`. Its `prepare` step records the SHA-256 of this
document, and `run` refuses to start if this document changes.

## Question

On the real GitHub Copilot CLI, with heavy multi-step tasks, how many raw tokens and how much
billed cost does the documented TokenMaster install save? The comparison is the same CLI
without TokenMaster.

## Background measured before this study

- PRS-4 measured 14.0% fewer raw tokens and 49.8% lower billed cost per finished task. PRS-4
  used a Copilot-CLI-shaped agent and short tasks, about 4.6 model calls per session.
- Live checks showed that the real Copilot CLI sends a fixed prompt of about 13,500 tokens on
  every call. Through the bridge, a later session's first call read that prompt from the cache.
- No study has measured TokenMaster on the real Copilot CLI.
- Inference, not a measurement: in longer sessions the first call is a smaller share of the
  total, so the cache-stable system prompt saves less in relative terms.

## Arms

| Arm | Definition |
| --- | --- |
| `stock` | Copilot CLI 1.0.98, default agent, no TokenMaster. |
| `tm` | Copilot CLI 1.0.98 after the documented install for Copilot. `setup.py --host copilot` installs the `tokenmaster-nav` MCP server, the graph, the symbol index and the `token-master` agent file. `brainspace_setup.py --host copilot` installs the `brainspace` MCP server, the v6 `view` hook and the bridge. Every session starts through the installed bridge. |

Both arms use:

- Model `gpt-6-astra`, reasoning effort low, maximum prompt 200,000 tokens, maximum output
  16,000 tokens.
- Non-interactive mode (`-p`) with `--allow-all-tools`, `--no-ask-user`, `--no-auto-update`,
  `--disable-builtin-mcps` and `--output-format json`.
- The default agent. The `tm` arm installs the `token-master` agent file but does not select
  it, because that agent has no edit tool.
- Copilot CLI's bring-your-own-key mode in offline mode, against an evaluation relay. The relay
  adds the GitHub Copilot credential and records every model call, including calls that get no
  response. It changes no request content.
- An isolated home folder per arm, with the installed Copilot CLI 1.0.98 package copied in.
- An allowlisted environment. It holds no operator environment variables and has no Python on
  PATH, so agents cannot run Python. Checks run after the session, outside it.
- Before each session, the harness deletes Copilot CLI's stored session history in the arm's
  home, so no session can read an earlier session's work.

## Tasks

- 8 heavy tasks, H01 to H08, written by two agent sessions that were not told the arms or the
  purpose of the study.
- Category quota: investigate 3, edit 3, feature 2.
- "Heavy" means that a competent engineer must open at least 5 files or change at least 3 files.
  The harness does not enforce this.
- Investigate tasks have exact JSON answers. They fail if any repository file changes. Changes
  inside dot-folders, cache folders and `graphify-out/` do not count.
- Edit and feature tasks have an executable check. `prepare` confirms, for both arms' templates,
  that each check fails on the untouched workspace and passes after the author's reference
  patch. It also confirms that the reference patch stays inside the task's allowed paths. A
  session that changes a file outside the allowed paths fails.
- Checks run in an isolated home folder, never the operator's.
- The topics of the 84 earlier tasks (T, N, M and P series) are excluded.
- The assistant re-checks every task after the harness and this document are committed, and
  records each correction in the task file's provenance.

## Design

- 8 tasks x 2 arms x 2 repeats = 32 sessions.
- Each arm runs its 16 sessions back to back in one fixed repository folder. The harness resets
  the folder from the arm's template before each session. This models continuous use of one
  repository.
- Both arms run at the same time, in the same task order (seed 20261022).
- The repository is `git archive 703aa20`, as in PRS-1 to PRS-4.
- A session that runs longer than 25 minutes fails.
- An infrastructure failure is a session that did not finish and saw HTTP 429, a 5xx error or no
  response from the provider. A harness error is also an infrastructure failure. Each one is
  re-run once. If the re-run also fails this way, the pair leaves the comparison, and the report
  lists it. Every other failure counts, with all its tokens.

## Smoke gate

- `smoke` runs 2 short sessions per arm in other folders. Their prompts therefore differ from
  the study's prompts from the working-directory line onward.
- `run` starts only if all 4 smoke sessions pass, the bridge applied the cache-stable system
  prompt, the second `tm` smoke session started warm, and the `tm` requests include the
  `tokenmaster-nav` tools.

## Endpoints

- **Co-primary:** raw tokens (input tokens plus output tokens, over all model calls) and billed
  cost. Billed cost = (input − cached − cache_write) + 0.1 x cached + 1.25 x cache_write + 5 x
  output. These are the provider's prices relative to new input. They match GitHub's published
  prices for GPT-6 Astra.
- Secondary: uncached input tokens (input − cached), model calls, the PRS-3 cost metric, pass
  rate and warm starts.
- The report also gives each endpoint per finished task: the sum over all graded sessions,
  failures included, divided by the passed sessions.
- The analysis recounts every session from its raw captures. Where a response states its own
  bill (`copilot_usage`), the analysis compares it with the billed cost. It stops if any session
  differs by more than 0.5 units, or if a response shows other prices.

## Statistics

- Sessions are paired by task and repeat.
- For each endpoint: ratio of sums over the paired sessions, a two-stage cluster bootstrap 95%
  CI and an exact Wilcoxon test on per-task mean differences, as in PRS-4.
- Holm correction across the 2 co-primary endpoints. With 8 tasks, the smallest possible
  Wilcoxon p-value is 0.0078, when all 8 tasks move in the same direction. After Holm, the
  smaller of the two raw p-values must be at most 0.025, and the larger at most 0.05.
- Verdict per primary endpoint, from the paired ratio-of-sums CI and the Holm p-value: "lower"
  if the CI upper bound is below 0 and the Holm p-value is below 0.05; "higher" if the CI lower
  bound is above 0 and the Holm p-value is below 0.05; otherwise "no significant difference".
- The change per finished task gets its own two-stage cluster bootstrap 95% CI (2,000
  resamples). It is reported but decides nothing.

## Workload floor

Each arm must use at least 2,000,000 raw tokens over its graded sessions. If an arm uses less,
the report says so. The harness adds no sessions after the run starts.

## Predictions (written before any study call; they decide nothing)

- Raw tokens: between −20% and +10%. The `tm` arm adds MCP tool definitions to every call.
  v6 and v7 make tool results smaller.
- Billed cost: between −10% and −40%.

## Disclosures

- The relay adds the GitHub Copilot credential and the same client headers as the PRS-1 to
  PRS-4 gateways. It listens on 127.0.0.1 without its own authentication, so a local process
  could use it. Any call it relays during a session counts toward that session.
- There is no file-system sandbox. The analysis searches every tool call and tool result for
  the study's own paths (output folder, task file, the other lane) and reports the hits.
- The `tm` install leaves graphify's output folder in the repository and adds a root
  `.gitignore`. `prepare` records whether git ignores the graphify output.
- One model, one repository snapshot, one operating system (Windows).
- The bridge and the hook changed after PRS-4. This study tests the current code, frozen by
  hash.
- The assistant wrote this harness after seeing the live-check results. An independent review
  of the harness found 2 blocking bugs and 18 risks before the freeze; all were fixed or
  disclosed here.
