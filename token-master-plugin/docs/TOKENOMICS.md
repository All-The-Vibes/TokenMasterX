# /tokenomics: the TokenMaster usage and savings dashboard

`/tokenomics` shows how many tokens and dollars your Copilot CLI sessions used, and how much TokenMaster saved. It
works like [ccusage](https://github.com/ryoppippi/ccusage) does for Claude Code: it reads local usage records and
prints daily, weekly, monthly or per-session tables.

- **Actual tokens and cost are measured.** They come from Copilot CLI's own record of each model call, including
  GitHub's charge for that call.
- **Savings are estimated.** Nothing can measure the stock session that did not run. The estimate and its
  check against measured A/B results are below.

## Use it

1. Install TokenMaster for Copilot (see [COPILOT_BRIDGE.md](COPILOT_BRIDGE.md)). `brainspace_setup.py --host copilot`
   installs `tokenomics.py` and a personal Copilot skill, `<COPILOT_HOME>/skills/tokenomics/SKILL.md`.
2. Start Copilot CLI through the TokenMaster launcher. The launcher records each launch, so the dashboard can tell
   TokenMaster sessions from stock sessions.
3. In an interactive Copilot CLI session, type `/tokenomics`. Add a report and options after it, for example
   `/tokenomics session --since 20261020`.
4. Approve the two questions that Copilot CLI asks:
   - access to `<COPILOT_HOME>/token-master/tokenomics.py`, which is outside the session's folder;
   - permission to run the command, unless you started Copilot CLI with `--allow-all-tools`.

| Report | One row per |
| --- | --- |
| `daily` (default) | Day, in local time |
| `weekly` | Week, starting on Monday |
| `monthly` | Month |
| `session` | Copilot CLI session, with its folder, start time and TokenMaster mode |

| Option | Effect |
| --- | --- |
| `--since YYYYMMDD`, `--until YYYYMMDD` | Limit the days (local time) |
| `--project TEXT` | Only sessions whose folder or repository contains TEXT |
| `--only tokenmaster` or `--only stock` | Only TokenMaster calls, or only stock calls |
| `--breakdown` | One sub-row per model |
| `--full`, `--compact` | All columns, or the narrow table that `/tokenomics` uses by default |
| `--json` | Machine-readable output |
| `--order desc`, `--ascii`, `--no-color`, `--copilot-home PATH` | Order, plain characters, no colors, another Copilot home |

**Cost of the command itself.** `/tokenomics` asks the model to run the script and repeat its output. In the live
check on Copilot CLI 1.0.98, that took 2 model calls, 16,445 tokens and $0.16 with `gpt-6-astra`. To spend no model
tokens, run the script as a shell command in Copilot CLI with `!`. The dashboard prints the exact command. On Windows
it is `! [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); & "<python>" "<COPILOT_HOME>/token-master/tokenomics.py"`.

## What the columns mean

| Column | Meaning |
| --- | --- |
| Calls | Model calls |
| Input | New input tokens: neither read from nor written to GitHub's prompt cache |
| Output | Output tokens, reasoning included |
| Cache Write, Cache Read | Input tokens written to or read from GitHub's prompt cache |
| Total Tokens | Raw tokens: all input plus output |
| Cost (USD) | GitHub's own charge for the calls (`total_nano_aiu`; 10<sup>9</sup> nano = 1 AI credit = $0.01) |
| TokenMaster | Sessions that ran through the launcher, or the session's mode: `lean`, `nav`, `bridge` |
| Saved Tokens ≈, Saved (USD) ≈ | Estimated savings of the TokenMaster calls in the row |

## Data sources

| Source | Written by | What the dashboard uses |
| --- | --- | --- |
| `<COPILOT_HOME>/session-store.db`, table `assistant_usage_events` | Copilot CLI, for every model call | Model, API, token counts, cache reads and writes, GitHub's charge and price per token type |
| `<COPILOT_HOME>/session-store.db`, table `sessions` | Copilot CLI | Session folder and repository |
| `<COPILOT_HOME>/token-master/launches.jsonl` | TokenMaster launcher | Start and end time, folder, whether the lean tool set, the bridge and the navigation tools were on, and which tools the lean tool set excluded |

- The dashboard opens the database read-only. If Copilot CLI holds it, the dashboard reads a private copy.
- The launch records hold no prompt text. A session counts as a TokenMaster session if its folder matches a launch
  and its first call came during that launch. Its calls during the launch count as TokenMaster calls.
- Sessions that did not start through the launcher count as stock, with no savings. So do sessions resumed through
  the launcher, because their first call came before the launch.
- A stock session started in the same folder while a TokenMaster launch was running counts as TokenMaster.

## How the savings are estimated

The estimate covers the two effects that each call's own record can show. It assumes that stock Copilot CLI would
have made the same model calls.

1. **Lean tool set, per call.** Stock Copilot CLI sends more fixed tokens on every call: the definitions of the 11
   removed tools and the system-prompt text about them. The navigation tools add some back.
   - The `lean` calibrations were measured with those 11 tools, on builds and routing that did not send the two
     workflow tools. Where Copilot CLI sends them (default routing, and every mode from 1.0.104), the launcher now
     also removes them, about 2,000 more tokens per call, which the estimate does not count yet.
   - A prompt or a flag can keep some of the 11 tools: a prompt that starts a skill keeps `skill`, the workflow tools
     and the four subagent tools. The launch record lists the tools that the launcher excluded (names only), and the
     estimate credits their share of `lean`. Each of the 11 tools has a weight, `LEAN_WEIGHTS` in `tokenomics.py`:
     what keeping it adds to a call on Copilot CLI 1.0.104 (`gpt-6-astra`, Responses API, three skills installed),
     its family's cost split over the family's tools by definition size (`evidence/skill-trigger-20261029/`). A
     launch that kept the four subagent tools gets 56% of `lean`; one whose prompt started a skill (`skill` and the
     subagent tools), 48%; one started with `--fleet` (the subagent tools and `sql`), 44%. Launch records written
     before this change do not list the tools, and get the full `lean`.
   - The weights come from 1.0.104, `lean` from 1.0.98, and one set of weights serves both APIs. `skill` weighs 438
     with three skills installed; with the 128 skills of the test machine, keeping it adds about 3,990 tokens.
   - Fixed tokens saved per main-agent call = `lean` × the excluded tools' share (when the lean tool set was on) −
     `nav` (when the navigation tools were installed).
   - Cost saved per call = those tokens × the call's own cache-read price. Stock reads its fixed prefix from the cache
     after its first call.
2. **First call, per session.** The first call of a session writes most of its prompt to GitHub's cache.
   - Stock's first call would send the same prompt plus the fixed tokens. It would read its usual cached prefix
     and write the rest.
   - The usual cached prefix is measured from your own stock sessions: the median tokens that their first calls read
     from the cache, per model. Only for a model with no stock session in the store does the dashboard use the
     calibration value `stock_first_cached`.
   - Cost saved = (stock's write − the actual write) × (cache-write price − cache-read price).
   - The result can be negative. Example: a TokenMaster session starts cold, while stock's prefix is warm.
   - This term changes only cost, not raw tokens.
   - Why the dashboard measures it: on October 23, 2026, every stock first call in a Copilot CLI 1.0.98 home
     with default GitHub routing read 0 tokens from the cache (6 sessions, `gpt-6.1-sol` and `claude-sonnet-5.5`),
     even 2 minutes after another stock session. The probe's 6,450 came from bring-your-own-model mode with the
     built-in MCP servers off. With the calibration value, the dashboard showed a small negative cost saving for two
     TokenMaster sessions whose measured cost was 33% and 41% lower than stock's.

The fixed prompt depends on the Copilot CLI version. The dashboard uses the 1.0.98 values: the launcher runs the
installed Copilot CLI, which was 1.0.98 on October 23, 2026.

| Copilot CLI | API | Model | `lean` | `nav` | `stock_first_cached` | Source |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 1.0.98 | OpenAI Responses | `gpt-6-astra` | 5,558 | 252 | 6,450 | Probe, October 23 |
| 1.0.98 | Anthropic Messages | `claude-opus-5.5` | 9,727 | 531 | 11,226 | Probe, October 23 |
| 1.0.78-3 | OpenAI Responses | `gpt-6-astra` | 6,760 | 252 | 0 | 45-task Django A/B, October 22 |
| 1.0.78-3 | Anthropic Messages | `claude-opus-5.5` | 11,540 | 531 | 13,393 | 45-task Django A/B, October 22 |

- **1.0.98:** `evidence/copilot-version-probe-20261023/`. `lean` is the difference between the first calls of a stock
  session and a lean-tool-set session with the same prompt. `stock_first_cached` is what three back-to-back stock
  sessions read from the cache, in two different folders.
- **`nav`** was measured on 1.0.78-3 only. It is the size of TokenMaster's own navigation-tool definitions.
- **1.0.78-3:** medians from the Django A/B ([COPILOT_CLI_RESULTS.md](COPILOT_CLI_RESULTS.md)). Stock
  `gpt-6-astra` sessions on 1.0.78-3 read nothing from the cache on their first call.
- **Not counted:** model calls that graph navigation saved, v6 shaping of tool results, and any other change in what
  the model did.
- **Not estimated:** subagent calls, and calls over an API without calibration (for example Chat Completions). The
  dashboard reports how many TokenMaster calls had no estimate.

## Check against measured results

`evidence/tokenomics-validation-20261023/validate.py` ran the estimate on the TokenMaster sessions of the real-CLI A/B
runs. It compared the estimated "without TokenMaster" totals with the stock sessions that ran on the same tasks at the
same time. Those runs used Copilot CLI 1.0.78-3, so the check uses the 1.0.78-3 values.

| Model | Copilot CLI | Run | Token saving, estimated | Token saving, measured | Cost saving, estimated | Cost saving, measured |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `gpt-6-astra` | 1.0.98 | PRS-6 This repository, 29 tasks, full TokenMaster | 38.0% | 49.5% | 39.1% | 50.2% |
| `gpt-6-astra` | 1.0.98 | PRS-6 Django, 15 tasks, full TokenMaster | 45.4% | 58.5% | 57.5% | 70.7% |
| `claude-opus-5.5` | 1.0.98 | PRS-6 This repository, 29 tasks, full TokenMaster | 43.2% | 38.0% | 40.9% | 40.1% |
| `claude-opus-5.5` | 1.0.98 | PRS-6 Django, 15 tasks, full TokenMaster | 48.0% | 53.7% | 52.9% | 61.2% |
| `gpt-6-astra` | 1.0.78-3 | Django, 45 tasks, full TokenMaster | 45.2% | 53.4% | 77.0% | 79.9% |
| `gpt-6-astra` | 1.0.78-3 | Django, 45 tasks, without graphify | 45.1% | 44.9% | 70.3% | 70.8% |
| `gpt-6-astra` | 1.0.78-3 | This repository, 27 tasks, full TokenMaster | 39.5% | 44.8% | 59.1% | 62.8% |
| `claude-opus-5.5` | 1.0.78-3 | Django, 45 tasks, full TokenMaster | 49.7% | 51.6% | 58.5% | 60.8% |
| `claude-opus-5.5` | 1.0.78-3 | Django, 45 tasks, without graphify | 52.0% | 46.3% | 56.2% | 55.2% |
| `claude-opus-5.5` | 1.0.78-3 | This repository, 27 tasks, full TokenMaster | 47.4% | 53.5% | 45.4% | 51.2% |

- **Out-of-sample check on Copilot CLI 1.0.98 (PRS-6):** the 1.0.98 calibration values were set from the October 23
  probe before PRS-6 ran. On the four PRS-6 runs, the estimator gave 59.0% to 123.9% of the measured token saving
  and 56.0% to 103.6% of the measured cost saving. On the three runs where TokenMaster reduced model calls, the
  estimate is conservative because it does not count saved calls or v6 shaping; on the one run where TokenMaster made
  more calls (`claude-opus-5.5` on this repository: 137 vs 127 calls), it over-estimates raw token savings (43.2% vs
  38.0%) while matching cost savings within 0.8 percentage points (40.9% vs 40.1%).
- **Copilot CLI 1.0.78-3:** in 5 of 6 runs, the estimate gave 72% to 101% of the measured token saving.
- In one 1.0.78-3 run (`claude-opus-5.5` without graphify), it gave 125%. There, TokenMaster made 174 model calls and
  stock made 157. The estimate assumes that stock would have made the same calls, so it counts TokenMaster's 17 extra
  calls, and the tokens they sent, as calls that stock would also have made.
- The 1.0.78-3 check reuses the run that set the 1.0.78-3 values, so it is not independent. All 10 runs had sessions
  back to back; see [How to read the cost numbers](COPILOT_CLI_RESULTS.md#how-to-read-the-cost-numbers).

## Live checks in Copilot CLI (October 23, 2026)

`evidence/tokenomics-check-20261023/` holds the scripts and records.

| Check | Copilot CLI | Result |
| --- | --- | --- |
| `copilot -p "/tokenomics"`, lean tool set | 1.0.78-3 and 1.0.98 | The model got the text and did not run the skill |
| `copilot -p "/tokenomics"`, all tools | 1.0.78-3 | The same |
| Typed in an interactive session, lean tool set, `--allow-all-tools` | 1.0.78-3 | The skill ran after one path question; the dashboard printed |
| Typed in an interactive session, lean tool set, no pre-approval | 1.0.98 | The skill ran after a path question and a command question; the dashboard printed |
| `!` shell command in the same 1.0.98 session | 1.0.98 | The dashboard printed without a model call |
| One stock and two TokenMaster sessions in one folder, then the reports ([record](../../evidence/tokenomics-check-20261023/readme-example.txt)) | 1.0.98 | The stock session counted as stock, after the attribution fix below |

- The lean tool set removes Copilot CLI's `skill` tool. Typed `/tokenomics` still loaded the skill.
- The launcher wrote one start record and one end record for each interactive session.
- The last check found an attribution error. The stock session's last call came 66 ms after the launcher's start
  second, and a 5-second tolerance counted that session as TokenMaster. Now a session must have its first call during
  the launch, and the launcher records milliseconds. Older launch records hold whole seconds, so the dashboard extends
  their end by one second; otherwise it dropped calls from the launch's last second.
- The 1.0.78-3 checks ran that version by mistake. The scripts passed `--no-auto-update`, which makes the WinGet
  launcher run its bundled build. See [COPILOT_CLI_RESULTS.md](COPILOT_CLI_RESULTS.md#copilot-cli-version).

## Limits

- The savings are an estimate. The 1.0.98 values come from a probe with one short prompt, two models and no A/B
  run. A different Copilot CLI version, more MCP servers or custom instructions change the fixed prompt, and the
  values do not follow.
- Without a stock session of your own for a model, `stock_first_cached` assumes that another session of the same
  version ran shortly before, so stock's prefix is warm. After a long pause, stock's first call is colder, and the real
  first-call saving is larger.
- Copilot CLI's `session-store.db` is an internal file. A future Copilot CLI version can change its tables. The
  dashboard reads only the columns it finds.
- Cost is GitHub's charge for each call. It does not count premium requests or plan allowances.
- Only Copilot CLI is covered. Claude Code keeps its usage in other files, and ccusage already reads them.
