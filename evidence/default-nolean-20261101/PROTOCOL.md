# Default TokenMaster under default routing: protocol (written November 1, 2026, before any study session)

Exploratory, not pre-registered in the PRS sense. This file is written and its SHA-256 recorded before the 30 study
sessions start, and `analyze.py` applies the decision rule below as written. No probe or pilot with model calls ran;
a `--prepare-only` check, which makes no model call, validated the lanes, the install and the Copilot CLI version.

## Question

Since PR #20 (`e28d1ad`), the TokenMaster launcher sends every built-in Copilot CLI tool unless it is started with
`--lean`. Every published saving was measured with the lean tool set on. What does TokenMaster save in its default
setup, with `tokenmaster-nav` and the v6 `view` hook installed and every built-in tool kept, against stock Copilot
CLI under GitHub's default routing?

## Arms

| Arm | Definition |
| --- | --- |
| `stock` | Copilot CLI `1.0.105`, default agent, no TokenMaster component. |
| `tm` | The same CLI after `setup.py --host copilot` (Graphify `0.9.91`) and `brainspace_setup.py --host copilot` from master `e28d1ad`, started through `brainspace_copilot_bridge.py` without `--lean`. The launcher passes Copilot CLI's command through unchanged. `tokenmaster-nav` and the v6 `view` hook load. The bridge does not run (no provider URL). |

The harness is `token-master-plugin/evals/default_routing_ab.py` at `e28d1ad`, run through `run.py` in this folder,
which changes three things and nothing else: it drops the `--lean` flag the harness passes to the launcher, it pins
Copilot CLI `1.0.105` (the latest release, so auto-update has nothing newer to install), and it records no lean
exclusions.

Both arms, as on October 27:

- Default GitHub routing: no `COPILOT_PROVIDER_BASE_URL`, no `COPILOT_OFFLINE`, no relay. Copilot CLI signs in with
  its own stored login, a GitHub Enterprise Cloud account with data residency; each lane's `config.json` holds the
  account names, and the token stays in Windows Credential Manager.
- `--model gpt-6-astra --reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps --output-format json`,
  the flags of PRS-6 and of the October 27 run. The built-in GitHub MCP server is off in both arms, so this measures
  TokenMaster's own components.
- One isolated `HOME`, `LOCALAPPDATA` and `COPILOT_HOME` per arm, in lanes under `C:\tm-lanes` (`dnr`, `dnc`). The
  harness's skill and instruction checks must pass before the first session. No Python on the agents' `PATH`.
- Sessions run back to back in one folder per arm, with both arms at the same time.

## Tasks

Django 5.2, commit `9e7cc2b6`, tasks D01-D15 from `evidence/django-scale-20261022/tasks.json`. Two shards run at the
same time, in PRS-6's orders: `django-rare` D09, D01, D07, D03, D05, D04, D08, D02, D06, D10 and `django-common` D12,
D11, D14, D13, D15. One run per task and arm: 30 sessions.

## Measurement and statistics

As on October 27. Copilot CLI's own record of every model call (`session-store.db`, `assistant_usage_events`):
GitHub's token counts, charge and per-token prices. Raw tokens are input plus output over all calls of a session.
As-run cost is the sum of `total_nano_aiu`. Cold-repriced cost adds, for the first main-agent call, its cache reads
times (cache-write price minus cache-read price). Paired ratio of sums (`tm / stock - 1`), 10,000-resample paired
bootstrap over tasks (seed `20261022`), exact two-sided Wilcoxon signed-rank test, Holm over raw tokens and
cold-repriced cost. One re-run per infrastructure failure.

## Decision rule

- For raw tokens and for cold-repriced cost separately: "lower" if the whole 95% CI of the change is below 0 and the
  Holm-adjusted p is below 0.05; "higher" if the whole CI is above 0 and p is below 0.05; otherwise "no significant
  difference".
- A headline may quote a saving for the default setup only if raw tokens are "lower", and then with the point
  estimate and its 95% CI.
- The verdict is withheld if the audit finds a session on another Copilot CLI version or model, more than one Copilot
  session in a run, a charge that differs from its token counts or from the CLI's own running total, or a results
  row that differs from its recount.

## Known differences from the October 27 run

Copilot CLI `1.0.105`, not `1.0.104`; TokenMaster `e28d1ad`, not `v0.2.0`; a different day. A comparison with the
October 27 lean result crosses runs and cannot separate the lean tool set from these differences. The result of this
study is the within-run comparison of `tm` and `stock`.

## Budget

The user approved about $5 (500 AI credits). Expected spend is about 460 credits. Each shard gets a cap
(`--budget-credits`): `django-rare` 430, `django-common` 280. Each running session holds a 60-credit allowance against
its shard's cap, so the caps sit about 120 credits above the expected spend. A shard starts no session once its spend
plus 60 credits would pass its cap. If a shard stops early, the missing sessions are reported and none is added
without a new approval.

## Amendment (November 1, 2026, before any study session)

The first attempt stopped during setup, before any session or model call: with both shards installing TokenMaster
at the same time, graphify's index of Django took longer than the harness's 900-second install timeout in both lanes.
`run.py` now raises that timeout to 2,700 seconds for the install step. Nothing else changed.
