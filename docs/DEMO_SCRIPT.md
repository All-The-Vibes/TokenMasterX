# TokenMaster tokenomics: demo script

- **Length:** about 15 minutes.
- **Goal:** show what GitHub Copilot CLI spends on every model call, what TokenMaster removes, and how
  `/tokenomics` reports it.
- **Numbers:** all numbers here are real.
  - "Rehearsal" numbers come from Copilot CLI 1.0.98 on this machine, on October 23, 2026, with
    `gpt-6.1-sol` and default GitHub routing. Each is a single run, not a statistic.
  - The statistics come from the A/B runs in Part 1.

## Before the demo (10 minutes before)

1. Open two PowerShell 7 windows side by side:
   - **Window A:** stock Copilot CLI.
   - **Window B:** TokenMaster.

   Make each window at least 120 characters wide, and make the font large.
2. Paste this block into both windows. It defines two helpers for that window only:

   ```powershell
   cd C:\Users\shyamsridhar\code\Tokenmaster
   $django = "$env:TEMP\opencode\django-g091"
   $nav = "@$env:USERPROFILE\.copilot\token-master\demo-nav-mcp.json"
   function tokenomics { & "C:\Users\shyamsridhar\code\Tokenmaster\.token-master-dev\Scripts\python.exe" "$env:USERPROFILE\.copilot\token-master\tokenomics.py" @args }
   ```

3. In window B, check the setup:

   ```powershell
   copilot skill list
   tokenomics session --since 20261023
   ```

   - `tokenomics` is listed under "Personal skills".
   - The table shows 4 rehearsal sessions from this morning. Tell the audience that they are rehearsal runs.
4. Optional: run Step 4 once, so that the folder and permission questions do not surprise you live.
5. Optional: open `docs/tokenmaster-v5-slide.html` in a browser for the results slide.

## Part 1: The math (3 minutes)

### The fixed part of every call

Say:

1. "A token is a small piece of text. GitHub charges for each token that a model reads or writes."
2. "A model has no memory. On every call, Copilot CLI sends the whole prompt again."
3. "The prompt has a fixed part: the system prompt and the definitions of the built-in tools. Copilot sends
   this fixed part on every call."
4. "TokenMaster removes 11 built-in tools that no session used in our October 18 runs. The fixed part gets
   much smaller."

Show the rehearsal numbers: the same one-word prompt and the same model.

| One call, answer "OK" | Stock Copilot CLI | TokenMaster (`tmc`) |
| --- | ---: | ---: |
| Tokens sent and received | 15,185 | 9,016 (−40.6%) |
| GitHub's charge | $0.0380 | $0.0226 (−40.5%) |

Say: "This call answers one word. A real task makes several calls; a Django question in our A/B took 3 to 4
calls on average. Each call pays the fixed part again."

### How GitHub prices a call

GitHub prices four kinds of tokens. These are its prices for `gpt-6.1-sol`, from Copilot CLI's own records:

| Token type | Price per 1M tokens | Meaning |
| --- | ---: | --- |
| New input | $2.00 | Input that is not in GitHub's prompt cache |
| Cache write | $2.50 | Input that GitHub stores in its cache for later calls |
| Cache read | $0.10 | Input that GitHub reads back from its cache |
| Output | $10.00 | Text that the model writes |

**Cost of one call** = (new input × $2.00 + cache write × $2.50 + cache read × $0.10 + output × $10.00)
÷ 1,000,000.

Copilot CLI records the tokens and GitHub's charge for every call in `~/.copilot/session-store.db`. The
dashboard adds them up. **These numbers are measured.**

### How the dashboard estimates the saving

Nobody can run the stock twin of your session. So for each TokenMaster session, the dashboard estimates two
effects:

1. **Every call:** fixed tokens removed × cache-read price. Stock reads its fixed part from the cache after
   its first call.
2. **First call only:** (what stock would write to the cache − what TokenMaster wrote) × (cache-write price −
   cache-read price).

Worked example: the one-word TokenMaster session above.

- Fixed tokens removed: 5,558. A probe on Copilot CLI 1.0.98 measured this number.
- Every call: 5,558 × $0.10 ÷ 1M = **$0.0006**.
- First call:
  - Your stock sessions read 0 tokens from the cache on their first call.
  - So stock would write 9,008 + 5,558 = 14,566 tokens. TokenMaster wrote 9,008.
  - 5,558 × ($2.50 − $0.10) ÷ 1M = **$0.0133**.
- **Estimated saving: $0.0139.** Measured difference: $0.0380 − $0.0226 = $0.0154. The estimate is 90% of the
  measured difference.

Say: "The estimate counts only the fixed part. It does not count calls that the graph tools save. On 6
measured A/B comparisons, it gave 72% to 125% of the measured token saving."

### The measured A/B results

Real Copilot CLI 1.0.78-3, 45 "who calls X?" questions on Django 5.2 per model, October 22, 2026:

| | Stock | Full TokenMaster |
| --- | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,417,452 | 1,127,277 (−53.4%) |
| `claude-opus-5.5` raw tokens | 3,457,179 | 1,673,646 (−51.6%) |
| `gpt-6-astra` cost, every first call cold | $11.55 | $5.83 (−49.5%) |
| `claude-opus-5.5` cost, every first call cold | $6.14 | $3.31 (−46.0%) |
| Correct answers, both models | 90 of 90 | 88 of 90 (2 model errors) |

Say: "These runs used Copilot CLI 1.0.78-3. On 1.0.98, the fixed part is smaller, but TokenMaster still
removes about half of it. We have not repeated the full A/B on 1.0.98."

## Part 2: Architecture (3 minutes)

```text
 you ── tmc ──► TokenMaster launcher ──────────────► Copilot CLI 1.0.98 ──► GitHub Copilot API
                  │ adds --excluded-tools (11 tools)      │
                  │ writes a launch record                ├─ view hook: large file view → short digest (v6)
                  ▼                                       ├─ tokenmaster-nav: locate, read_symbol, impact
   ~/.copilot/token-master/launches.jsonl                 ├─ /tokenomics skill → runs tokenomics.py
                  │                                       └─ records every call → ~/.copilot/session-store.db
                  │                                                                   │
                  └─────────────────────► tokenomics.py ◄─────────────────────────────┘
                                 measured tables + estimated savings
```

| Part | What it does | Where it is |
| --- | --- | --- |
| `tmc` | Starts Copilot CLI through the TokenMaster launcher. | PowerShell 7 profile |
| Launcher | Removes 11 unused built-in tools from every call. Records each launch: time, folder and settings, with no prompt text. | `~/.copilot/token-master/brainspace_copilot_bridge.py` |
| Bridge | Only in bring-your-own-model mode: makes the system prompt the same for sessions in one folder, so GitHub's cache can reuse it. Your default setup does not use it. | Inside the launcher |
| Graph tools (`tokenmaster-nav`) | `locate`, `read_symbol` and `impact` answer "where is X?" and "who calls X?" from a prebuilt call graph, in one compact result. | MCP server. The demo adds it for one session only. |
| View hook (v6) | Turns a large whole-file view into a short digest before the model reads it. | `~/.copilot/settings.json` |
| `/tokenomics` | ccusage-style tables: measured tokens and charges, and estimated savings. | `~/.copilot/skills/tokenomics/` |

Say: "The dashboard reads two local files and changes nothing. The launch records hold no prompt text."

## Part 3: Live demo (8 minutes)

### Step 1: What is installed (no model calls, 30 seconds)

Window B:

```powershell
copilot skill list
(Get-Command tmc).Definition
```

Say: "`tokenomics` is a personal Copilot skill. `tmc` is one line: it starts Copilot through the TokenMaster
launcher."

### Step 2: The fixed part, measured (2 minutes)

Window A:

```powershell
copilot -p "Reply with the single word OK."
```

Window B:

```powershell
tmc -p "Reply with the single word OK."
tokenomics session --since 20261023
```

- Point at the first line in window B: `[tokenmaster] ... lean tool set on`.
- Point at the two newest rows of the table.
- Rehearsal values:
  - Stock: 15,185 tokens, $0.04.
  - TokenMaster: 9,016 tokens, $0.02, mode `lean`, Saved Tokens ≈ 5,558, Saved (USD) ≈ $0.01.

Say: "Total Tokens and Cost are GitHub's own numbers. The columns marked ≈ are estimates."

### Step 3: Graph over grep, on Django (3 minutes)

Django 5.2 has 2,818 Python files. The question is task D31 from our A/B. Its answer key was checked by hand.

Window A:

```powershell
cd $django
copilot -p "List the non-test functions that call format() in django/utils/dateformat.py. Answer with the list only." --allow-all-tools
```

Window B:

```powershell
cd $django
tmc --additional-mcp-config $nav -p "Use the impact tool to list the non-test functions that call format() in django/utils/dateformat.py. Answer with the list only." --allow-all-tools
```

- **Correct answer:** `django.template.defaultfilters.date` and `django.utils.formats.date_format`.
- **Rehearsal, stock:** 4 calls, 62,484 tokens, $0.0472. It searched with `glob`, `rg` and `view`. It
  answered `format` and `time_format`, which is wrong.
- **Rehearsal, TokenMaster:** 2 calls, 21,495 tokens, $0.0315. It called `impact` once and answered
  correctly.

Say: "`impact` answers 'who calls X?' from a prebuilt call graph in one compact result. With grep, the model
reads raw search output and files."

Say also, to be fair: "The TokenMaster prompt names the tool, so that the demo is predictable. In the A/B,
both versions got the same prompt, and the models chose the graph tools by themselves: `gpt-6-astra` in 45 of
45 sessions, `claude-opus-5.5` in 26 of 45."

`--additional-mcp-config` adds the graph tools for this one session. Your global Copilot configuration does not
change.

Then, in both windows: `cd C:\Users\shyamsridhar\code\Tokenmaster`

### Step 4: `/tokenomics` inside Copilot (3 minutes)

Window B:

```powershell
tmc
```

Point at the start-up line "Disabled tools: …". These are the 11 tools that the launcher removed.

In Copilot, type:

1. `/tokenomics`
   - Copilot asks two questions: access to the script, then running it. Answer Yes to both.
   - The daily table appears.
2. `/tokenomics session --since 20261023`
   - One row per session, including the sessions from Steps 2 and 3.
3. Optional: `/tokenomics monthly --breakdown`
   - One sub-row per model.
4. The free form. The last line of the report shows a `!` command. Type it, with
   `session --since 20261023` at the end:

   ```text
   ! [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); & "C:/Users/shyamsridhar/code/Tokenmaster/.token-master-dev/Scripts/python.exe" "C:/Users/shyamsridhar/.copilot/token-master/tokenomics.py" session --since 20261023
   ```

   Say: "`/tokenomics` asks the model to run the report. That costs about 16,000 tokens. The `!` form runs the
   report directly: no model call, no cost."
5. `/exit`

### Step 5: Close (1 minute)

Say:

1. "On 45 Django questions per model, TokenMaster used about half the tokens of stock Copilot CLI. It got 2
   fewer correct answers out of 90; both were model errors."
2. "Today's runs are single examples. The A/B is the evidence."
3. "Limits: one task type, one run per task, and Copilot CLI 1.0.78-3 for the A/B. The dashboard's estimate
   covers only the fixed part."

## If something goes wrong

| Problem | What to do |
| --- | --- |
| Copilot asks you to trust the folder | Choose Yes. |
| Copilot asks you to sign in | Type `/login`. Or skip to the rehearsal rows: `tokenomics session --since 20261023`. |
| `/tokenomics` is not in the command list | Run `copilot skill list`, then restart Copilot. Or use the `!` form. |
| Step 3 does not call `impact` | Check the file: `Test-Path $nav.TrimStart('@')`. Show the rehearsal numbers instead. |
| The numbers differ from the rehearsal | This is normal: the model makes different calls on each run. Point to the A/B for statistics. |
| No network | Run `tokenomics session --since 20261023` on the rehearsal data, and show the slide. |

## Questions you may get

- **"Is the saving measured or estimated?"** Both. The A/B is measured. The dashboard measures your tokens and
  cost, and it estimates what stock would have cost.
- **"Does removing tools hurt?"**
  - The 11 tools are `task` (subagents), `skill`, `sql`, `session_store_sql`, three background-PowerShell
    tools, three agent tools and `fetch_copilot_cli_documentation`.
  - No session used them in our October 18 runs. One later stock session used `task`.
  - For work that needs them, run plain `copilot`.
- **"Which Copilot CLI version did you test?"**
  - The A/B ran Copilot CLI 1.0.78-3, because of a harness flag. We found the error and corrected the
    documents.
  - On 1.0.98, TokenMaster still removes about half of the fixed part.
  - A full A/B on 1.0.98 is still to do.
- **"Does my prompt text go anywhere new?"** No. The dashboard reads local files and opens Copilot's
  database read-only. The launch records hold no prompt text.
- **"What does the bridge do?"** It works only in bring-your-own-model mode. It makes the system prompt the
  same for sessions in one folder, so GitHub's cache can reuse it. Your default setup does not use it.

## Sources

- A/B results and test parameters: `token-master-plugin/docs/COPILOT_CLI_RESULTS.md`.
- Dashboard method and its check against the A/B: `token-master-plugin/docs/TOKENOMICS.md`.
- Version probe (1.0.78-3 against 1.0.98): `evidence/copilot-version-probe-20261023/`.
- Rehearsal numbers: `tokenomics session --since 20261023 --json` on this machine.
