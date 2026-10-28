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
   . $PROFILE
   cd C:\Users\shyamsridhar\code\Tokenmaster
   $django = "$env:TEMP\opencode\django-g091"
   $nav = "@$env:USERPROFILE\.copilot\token-master\demo-nav-mcp.json"
   ```

   (`tmc` and `tokenomics` are also installed in `C:\Users\shyamsridhar\.local\bin\`, which is on your `PATH`, so they work even if you skip `. $PROFILE`. Using `copilot.exe` for the stock commands bypasses any shell wrapper.)

3. In window B, check the setup:

   ```powershell
   copilot.exe skill list
   tokenomics session --since 20261023
   ```

   - `tokenomics` is listed under "Personal skills".
   - The table shows the rehearsal sessions from this morning (`lean` for the 1-word prompt, `lean+nav` for the Django Graphify lookup). Tell the audience that they are rehearsal runs.
4. Optional: run Step 4 once, so that the folder and permission questions do not surprise you live.
5. Open `docs/tokenomics-demo-slide.html` in a browser (4 tabs: Math, Architecture, Live Runbook with Copy buttons, and Dashboard Output & Q&A). `docs/tokenmaster-v5-slide.html` has the single-slide A/B summary.

## Part 1: The math (3 minutes)

### The fixed part of every call

Say:

1. "A token is a small piece of text. GitHub charges for each token that a model reads or writes."
2. "A model has no memory. On every call, Copilot CLI sends the whole prompt again."
3. "The prompt has a fixed part: the system prompt and the definitions of the built-in tools. Copilot sends
   this fixed part on every call."
4. "TokenMaster removes 13 built-in tools: 11 that no session used in our October 18 runs, and two
   workflow tools that none of our October 27 sessions used. The fixed part gets much smaller."

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

**1. Pre-registered PRS-6 study on Copilot CLI `1.0.98` (176 sessions, `88/88` pass rate in both `stock` and `tm` arms, October 26, 2026, commit `19443fc`, `evidence/prs6-copilot-1.0.98-20261026/analysis.json`):**

| PRS-6 (`1.0.98`, pre-registered) | Stock | Full TokenMaster (`tm`) | Change |
| --- | ---: | ---: | ---: |
| **29-task repository benchmark (`>2.4M` stock tokens/model)** | | | |
| `gpt-6-astra` raw tokens (`29/29` passes both arms) | 2,449,067 | 1,237,510 | **−49.5%** (27/29 lower) |
| `gpt-6-astra` cold cost / as-run cost | $8.91 / $6.83 | $5.21 / $3.40 | **−41.5%** cold / **−50.2%** as-run |
| `claude-opus-5.5` raw tokens (`29/29` passes both arms) | 2,672,316 | 1,655,797 | **−38.0%** (27/29 lower) |
| `claude-opus-5.5` cold cost / as-run cost | $4.23 / $2.72 | $2.79 / $1.63 | **−34.0%** cold / **−40.1%** as-run |
| **15-task Django 5.2 replication (`D01`–`D15`, `SCHEMA_VERSION = 4` import-alias resolution)** | | | |
| `gpt-6-astra` raw tokens (`15/15` passes both arms) | 707,799 | 293,779 | **−58.5%** (15/15 lower) |
| `gpt-6-astra` cold cost / as-run cost | $3.40 / $2.36 | $1.58 / $0.69 | **−53.5%** cold / **−70.7%** as-run |
| `claude-opus-5.5` raw tokens (`15/15` passes both arms) | 989,925 | 457,875 | **−53.7%** (15/15 lower) |
| `claude-opus-5.5` cold cost / as-run cost | $1.81 / $1.11 | $0.98 / $0.43 | **−46.0%** cold / **−61.2%** as-run |

**2. Exploratory 45-task Django 5.2 scale run on Copilot CLI `1.0.78-3` (270 sessions, October 22, 2026):**

| | Stock | Full TokenMaster |
| --- | ---: | ---: |
| `gpt-6-astra` raw tokens | 2,417,452 | 1,127,277 (−53.4%) |
| `claude-opus-5.5` raw tokens | 3,457,179 | 1,673,646 (−51.6%) |
| `gpt-6-astra` cost, every first call cold | $11.55 | $5.83 (−49.5%) |
| `claude-opus-5.5` cost, every first call cold | $6.14 | $3.31 (−46.0%) |
| Correct answers, both models | 90 of 90 | 88 of 90 (2 model errors) |

Say: "We have both the 45-task Django scale study on 1.0.78-3 and the pre-registered PRS-6 study on 1.0.98 across 176 sessions. In PRS-6, TokenMaster passed all 88 tasks per arm and cut raw tokens by 49.5% and 38.0% on our 29-task repository benchmark, and by 58.5% and 53.7% on the 15-task Django replication."

## Part 2: Architecture (3 minutes)

```text
 you ── tmc ──► TokenMaster launcher ──────────────► Copilot CLI 1.0.98 ──► GitHub Copilot API
                  │ adds --excluded-tools (13 tools)      │
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
| Launcher | Removes 13 unused built-in tools from every call. Records each launch: time, folder and settings, with no prompt text. | `~/.copilot/token-master/brainspace_copilot_bridge.py` |
| Bridge | Only in bring-your-own-model mode: makes the system prompt the same for sessions in one folder, so GitHub's cache can reuse it. Your default setup does not use it. | Inside the launcher |
| Graph tools (`tokenmaster-nav`) | `locate`, `read_symbol` and `impact` answer "where is X?" and "who calls X?" from a prebuilt call graph, in one compact result. | MCP server. The demo adds it for one session only. |
| View hook (v6) | Turns a large whole-file view into a short digest before the model reads it. | `~/.copilot/settings.json` |
| `/tokenomics` | ccusage-style tables: measured tokens and charges, and estimated savings. | `~/.copilot/skills/tokenomics/` |

Say: "The dashboard reads two local files and changes nothing. The launch records hold no prompt text."

## Part 3: Live demo (8 minutes)

### Step 1: What is installed (no model calls, 30 seconds)

Window B:

```powershell
copilot.exe skill list
tokenomics session --since 20261023
```

Say: "`tokenomics` is a personal Copilot skill, and `tmc` starts Copilot through the TokenMaster launcher."

### Step 2: The fixed part, measured (2 minutes)

Window A:

```powershell
copilot.exe -p "Reply with the single word OK."
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
  - TokenMaster: 9,016 tokens (and 8,905 on a second run), $0.02, mode `lean`, Saved Tokens ≈ 5,558, Saved (USD) ≈ $0.01.

Say: "Total Tokens and Cost are GitHub's own numbers. The columns marked ≈ are estimates."

### Step 3: Graph over grep, on Django (3 minutes)

Django 5.2 has 2,818 Python files. The question is task D31 from our A/B. Its answer key was checked by hand.

Window A:

```powershell
cd $django
copilot.exe -p "List the non-test functions that call format() in django/utils/dateformat.py. Answer with the list only." --allow-all-tools
```

Window B:

```powershell
cd $django
tmc --additional-mcp-config $nav -p "Use the impact tool to list the non-test functions that call format() in django/utils/dateformat.py. Answer with the list only." --allow-all-tools
```

- **Correct answer:** `django.template.defaultfilters.date` and `django.utils.formats.date_format`.
- **Rehearsal, stock (`024cbb23`):** 4 calls, 62,484 tokens, $0.0472. It searched with `glob`, `rg` and `view`. It
  answered `format` and `time_format`, which is wrong.
- **Rehearsal, TokenMaster (`0c4d1fe3` and `0b7f206a`):** 2 calls, 21,495 and 21,541 tokens, $0.0315, mode `lean+nav`
  (saved ≈ 10,612 tokens, $0.01). It called `impact` once and answered both callers correctly.

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

Point at the start-up line "Disabled tools: …". These are the tools that the launcher removed.

In Copilot, type:

1. `/tokenomics`
   - Copilot asks two questions: access to the script, then running it. Answer Yes to both.
   - The daily table appears.
2. `/tokenomics session --since 20261023`
   - One row per session, including the sessions from Steps 2 and 3.
3. Optional: `/tokenomics monthly --breakdown`
   - One sub-row per model.
4. The free form. Because `tokenomics.cmd` is on your `PATH` (`~/.local/bin/tokenomics.cmd`), type:

   ```text
   ! tokenomics session --since 20261023 --full
   ```

   Say: "`/tokenomics` asks the model to run the report. That costs about 16,000 tokens. The `!` form runs the
   report directly: no model call, no cost."
5. `/exit`

### Step 5: Close (1 minute)

Say:

1. "Across the pre-registered PRS-6 study on Copilot CLI 1.0.98 (176 sessions, `88/88` passes in both arms) and the 45-task Django scale run on 1.0.78-3, TokenMaster cut raw tokens by 38% to 58.5% and cold-repriced cost by 34% to 53.5%."
2. "Today's runs are single examples. The pre-registered PRS-6 study and the 45-task Django A/B are the evidence."
3. "Limits: 1 run per task per model in PRS-6, dynamic dispatch / `getattr` is not statically indexed by `impact`, and the dashboard's `/tokenomics` estimate covers only the fixed prompt part."

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
  - The 13 tools are `task` (subagents), `skill`, `sql`, `session_store_sql`, three background-PowerShell
    tools, three agent tools, `fetch_copilot_cli_documentation`, and the two workflow tools,
    `run_dynamic_workflow` and `dynamic_workflows_manage`, which Copilot CLI sends under default routing and,
    from 1.0.104, in every mode.
  - No session used the first 11 in our October 18 runs; one later stock session used `task`. None of the 60
    sessions of October 27 used the workflow tools.
  - In the pre-registered PRS-6 study on `1.0.98`, both `stock` and `tm` scored `88/88` (`29/29` on repository tasks and `15/15` on Django `D01`–`D15` for each model).
  - For work that needs the removed tools, run plain `copilot` or `tmc --all-tools`.
- **"What about Copilot CLI 1.0.98 vs 1.0.78-3? / Which Copilot CLI version did you test?"**
  - The October 18–22 exploratory runs used Copilot CLI `1.0.78-3` because `--no-auto-update` selected the WinGet launcher's bundled build. We caught that in the session captures, corrected the documents, and pinned the version gate.
  - We then ran the pre-registered **PRS-6 study on Copilot CLI `1.0.98`** (`token-master-plugin/docs/PRS6_PROTOCOL.md`, commit `19443fc`, `evidence/prs6-copilot-1.0.98-20261026/analysis.json`, 176 sessions, `88/88` pass rate in both arms):
    - **29-task repository benchmark (`1.0.98`, >2.4M stock tokens/model):** `gpt-6-astra` raw tokens **−49.5%** (`2,449,067` → `1,237,510`), cold cost **−41.5%** (`$8.91` → `$5.21`), as-run cost **−50.2%** (`$6.83` → `$3.40`), `29/29` passes; `claude-opus-5.5` raw tokens **−38.0%** (`2,672,316` → `1,655,797`), cold cost **−34.0%** (`$4.23` → `$2.79`), as-run cost **−40.1%** (`$2.72` → `$1.63`), `29/29` passes.
    - **15-task Django 5.2 replication (`D01`–`D15` on `1.0.98` with `SCHEMA_VERSION = 4` import-alias resolution):** `gpt-6-astra` raw tokens **−58.5%** (`707,799` → `293,779`), cold cost **−53.5%** (`$3.40` → `$1.58`), as-run cost **−70.7%** (`$2.36` → `$0.69`), `15/15` passes; `claude-opus-5.5` raw tokens **−53.7%** (`989,925` → `457,875`), cold cost **−46.0%** (`$1.81` → `$0.98`), as-run cost **−61.2%** (`$1.11` → `$0.43`), `15/15` passes (lower on all 15 tasks for both models, including `D13` where `login` is imported as `auth_login`).
- **"When does `impact` miss a caller?"**
  - `SCHEMA_VERSION = 4` in `brainspace/symbol_index.py` (commit `19443fc`) now resolves `import ... as ...` and `from ... import ... as ...` aliases in scope (`56/56` answer-key callers on `D01`–`D15`, including `from django.contrib.auth import login as auth_login` in `D13`).
  - Only dynamic dispatch, `getattr`, and string-based lookup remain unindexed by static AST analysis.
- **"Does my prompt text go anywhere new?"** No. The dashboard reads local files and opens Copilot's
  database read-only. The launch records hold no prompt text.
- **"What does the bridge do?"** It works only in bring-your-own-model mode. It makes the system prompt the
  same for sessions in one folder, so GitHub's cache can reuse it. Your default setup does not use it.

## Sources

- Pre-registered PRS-6 protocol and results (`1.0.98`, 176 sessions): `token-master-plugin/docs/PRS6_PROTOCOL.md` (commit `19443fc`) and `evidence/prs6-copilot-1.0.98-20261026/analysis.json`.
- Exploratory A/B results and test parameters (`1.0.78-3`): `token-master-plugin/docs/COPILOT_CLI_RESULTS.md`.
- Dashboard method and its check against the A/B: `token-master-plugin/docs/TOKENOMICS.md`.
- Version probe (1.0.78-3 against 1.0.98): `evidence/copilot-version-probe-20261023/`.
- Rehearsal numbers: `tokenomics session --since 20261023 --json` on this machine.
