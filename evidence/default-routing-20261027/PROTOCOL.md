# Default-routing A/B protocol (written October 27, 2026, before the study sessions)

Exploratory, not pre-registered in the PRS sense. This file is committed before the 30 study sessions start, and
`analyze.py` applies the decision rule below as written. A model probe (2 sessions) and a pilot (4 sessions) ran
before this file was committed. They checked the setup and the cost, and the analysis excludes them.

What the probe and the pilot changed:

- **The model.** The parent plan expected an administrator policy to pin `gpt-6.1-sol` under default routing. With an
  explicit `--model gpt-6-astra`, Copilot CLI's own record shows `gpt-6-astra` for every probe call, so the study
  runs PRS-6's model. The user chose `gpt-6-astra` on Django D01-D15 only, to stay under the credit cap.
- **The lane location.** The probe's lanes were under `%TEMP%`, inside the operator's profile, and Copilot CLI
  inherits instructions and skills from every ancestor folder of its working directory. `C:\Users\<name>` holds the
  operator's `.claude` (a `CLAUDE.md` and 101 skills), `.copilot` (109 skills) and `.agents` (93 skills). Both probe
  sessions loaded that `CLAUDE.md`, and the stock session's `skill` tool listed the inherited skills: its first call
  was 23,463 tokens, against 13,519 from a clean lane. The pilot and the study run from lanes under `C:\tm-lanes`.
- **The Copilot CLI version.** Under default routing, auto-update is on (relay mode turns it off). In the pilot, a
  session pinned to `1.0.98-2` downloaded the latest release, and the next session in the same lane ran `1.0.104`.
  The study pins `1.0.104`, the latest release, so auto-update has nothing newer to install.
- **Graphify.** The only Graphify on this machine was `0.9.17`. With it, `impact` found 51 of the 56 answer-key
  callers of D01-D15 (D03: 1 of 6; `impact_recall.py`). PRS-6 used `0.9.91`, which found 56 of 56. The study
  installs `graphifyy==0.9.91` in its own virtual environment for the TokenMaster arm.

## Question

Every published TokenMaster result ran Copilot CLI in bring-your-own-model mode through a local relay, with the
bridge's cache-stable system prompt and v6 shaping on. With Copilot CLI's default GitHub routing, do the README hero
numbers hold on the suite they come from: up to 58% fewer tokens, up to 54% lower cold-start cost, and no drop in pass
rate (PRS-6, Django D01-D15, `gpt-6-astra`: −58.5% raw tokens, −53.5% cold-repriced cost, 15/15 vs 15/15)?

## Arms

| Arm | Definition |
| --- | --- |
| `stock` | Copilot CLI `1.0.104`, default agent, no TokenMaster component. |
| `tm` | The same CLI after `setup.py --host copilot` (Graphify `0.9.91`) and `brainspace_setup.py --host copilot`, started through `brainspace_copilot_bridge.py`. Without a provider URL the launcher adds only the lean tool set (`--excluded-tools`; for these 15 prompts the same 11 tools that PRS-6 removed). `tokenmaster-nav` and the v6 `view` hook load. The bridge does not run, so there is no cache-stable system prompt and no request shaping. |

Both arms:

- Default GitHub routing: no `COPILOT_PROVIDER_BASE_URL`, no `COPILOT_OFFLINE`, no relay. Copilot CLI signs in with
  its own stored login, a GitHub Enterprise Cloud account with data residency. Each lane's `config.json` holds the
  account names; the token stays in Windows Credential Manager.
- `--model gpt-6-astra --reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps --output-format json`,
  the PRS-6 flags.
- One isolated `HOME`, `LOCALAPPDATA` and `COPILOT_HOME` per arm, in a lane under `C:\tm-lanes`. Before the first
  session, `copilot skill list` and `copilot instruction list` run in each lane. The run stops unless stock loads only
  Copilot CLI's built-in skills, `tm` loads only those plus the skills its own install added (`tokenomics`), and
  neither loads an instruction file. Before each session the lane is reset from the arm's read-only template and
  Copilot CLI's session history is cleared and checked. No Python on the agents' `PATH`.
- Sessions run back to back in one folder per arm, with both arms at the same time.

## Tasks

Django 5.2, commit `9e7cc2b6` (2,818 Python files), tasks D01-D15 from
`evidence/django-scale-20261022/tasks.json` (identical to PRS-6's sources). As in PRS-6, two shards run at the same
time, in PRS-6's orders: `django-rare` D09, D01, D07, D03, D05, D04, D08, D02, D06, D10 and `django-common` D12, D11,
D14, D13, D15. One run per task and arm: 30 sessions.

## Measurement

Copilot CLI's own record of every model call, `session-store.db` table `assistant_usage_events`: GitHub's input,
cache-read, cache-write and output token counts, GitHub's charge (`total_nano_aiu`) and GitHub's per-token prices
(`token_details_json`). `tokenomics.py` reads the same table. Only calls made after the session started count.

- **Raw tokens:** input plus output over all calls of a session, subagent calls included.
- **As-run cost:** the sum of `total_nano_aiu` (1e9 nano = 1 AI credit = $0.01).
- **Cold-repriced cost:** as-run cost plus, for the session's first main-agent call, its cache-read tokens times
  (cache-write price − cache-read price) at that call's own prices. This is PRS-6's cold re-pricing.
- **Pass:** the JSON answer lists exactly the answer-key callers (paths normalized, order ignored), and no file
  changed.

## Statistics

Paired ratio of sums (`tm / stock − 1`), 10,000-resample paired bootstrap over tasks (seed `20261022`), exact
two-sided Wilcoxon signed-rank test, Holm-Bonferroni over raw tokens and cold-repriced cost. One re-run per
infrastructure failure: a session with no recorded model call, or one that ended without a final answer after a
rate-limit or 5xx error event. A task without a graded session in both arms is left out of the paired token and
cost analysis and reported.

## Decision rule (hero check)

- "Up to 58% fewer tokens" holds if the upper end of the 95% CI of the raw-token reduction is at least 58%.
- "Up to 54% lower cold-start cost" holds if the upper end of the 95% CI of the cold-repriced cost reduction is at
  least 54%.
- "No drop in pass rate" holds if `tm` passes at least as many tasks as `stock`, counted both over all 15 tasks (a
  task without a graded session after its re-run counts as not passed) and over the paired tasks.

The point estimates and CIs are reported either way. The verdict is withheld if the audit finds a session on another
Copilot CLI version or model, calls from more than one Copilot session, a charge that differs from its token counts
or from the CLI's own running total, or a results row that differs from its recount.

## Known differences from PRS-6

Routing is the variable under test. These also differ, and the comparison with PRS-6 cannot separate them from it:

- Copilot CLI `1.0.104`, not `1.0.98`. In the pilot, stock first calls were 13,519 tokens on `1.0.98-2` and 13,587
  on `1.0.104`; tm first calls 7,723 and 7,791.
- Account: Copilot CLI's own sign-in, not the relay's OpenCode sign-in.
- TokenMaster `v0.2.0` (commit `2aa2a28`, capability-aware tool routing), not PRS-6's commit `19443fc`.
- Sessions on a different day; GitHub's server-side prompt and model may have changed.
- Lane location. PRS-6's lanes were under `%TEMP%`, inside the operator's profile. Whether its sessions inherited the
  operator's skills and `CLAUDE.md` is untested: its captures were deleted. The October 23 relay probe, run from
  `%TEMP%` as well, sent first calls of 11,083 tokens (stock) and 5,525 (lean tool set).

## Budget

The user approved up to 1,450 AI credits for the probe, the pilot and the study. The probe and the pilot spent 132.
Each shard gets a budget (`--budget-credits`): `django-rare` 760, `django-common` 400. A shard starts no session once
its spend plus 60 credits would pass its budget. If either shard stops early, the missing sessions are reported and
the study does not continue without a new approval.
