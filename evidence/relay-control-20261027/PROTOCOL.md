# Relay control protocol (written October 27, 2026, before the study sessions)

Exploratory, not pre-registered. This file is committed before the 30 study sessions start, and `analyze.py`
computes what it names. A pilot (D01 from `C:\tm-lanes`, 2 sessions) and a lane test (D01 from `%TEMP%`, 2 sessions)
ran before the commit. They checked the sign-in, the version pin and the cost, and the statistics exclude them.

What the pilot and the lane test changed:

- **The harness.** A code review after the pilot led to four changes before the study. A budget refusal now stops
  both arms. A session with no answered call, or one that ended without a final answer after an HTTP 429/5xx or no
  response, counts as an infrastructure failure, as in D104. An HTTP 401 or 403 from the Copilot API, or a session on
  another Copilot CLI version, stops the run. The version and the `tokenmaster-nav` calls are read from Copilot CLI's
  own event log, as in D104.
- **The lane test.** It ran from `C:\Users\<name>\AppData\Local\Temp\opencode\rct`, and from there Copilot CLI listed
  no inherited instruction or skill. The same folder written in its 8.3 form, `C:\Users\<SHORT~1>\...`, lists the
  operator's `CLAUDE.md` and about 170 skills. R98's lanes were recorded in the 8.3 form. So the lane test did not
  repeat R98's lane condition, and a second lane test from the 8.3 form runs after the study, so that its sessions
  cannot overlap the study's.

## Question

On Django D01-D15 with `gpt-6-astra`, TokenMaster used 41.5% of stock's raw tokens in PRS-6's relay run (R98, Copilot
CLI `1.0.98`, October 26) and 52.6% under default routing (D104, Copilot CLI `1.0.104`, October 27). The two runs
differ in routing, and also in client build, account, day, lane location and TokenMaster commit. How much of the
11.1-point gap comes from routing?

This run (R104) uses PRS-6's relay with D104's client build, account, day, lanes, graphify and TokenMaster runtime.

- R104 vs D104 differs in routing only, plus about two hours of clock time.
- R104 vs R98 differs in client build, TokenMaster commit, day, lane location and account.

Routing here is the whole bundle that a provider URL switches on: Copilot CLI's bring-your-own-model mode
(`COPILOT_OFFLINE`, HTTPS `POST /responses` through the relay) instead of its own routing (a WebSocket to
`/responses`, per the `api_endpoint` field of D104's records), and, in the TokenMaster arm, the bridge's cache-stable
system prompt and v6 shaping, which run only with a provider URL.

## Arms

| Arm | Definition |
| --- | --- |
| `stock` | Copilot CLI `1.0.104`, default agent, no TokenMaster component. |
| `tm` | The same CLI after `setup.py --host copilot` (graphify `0.9.91`) and `brainspace_setup.py --host copilot`, started through the installed `brainspace_copilot_bridge.py`, which runs its own bridge in front of the relay (lean tool set, cache-stable system prompt, v6 shaping). |

The installed TokenMaster files are D104's: this branch differs from D104's product commit `2aa2a28` only in
`SKILL.md`, `setup.py`, `hosts/config.py` and `hosts/tokenizer.py`, and the installers copy none of them into Copilot
CLI's home.

## Setup

- Copilot CLI `1.0.104` through the WinGet launcher, the package copied into each lane and pinned with
  `COPILOT_CLI_DIST_DIR`. Relay environment as in PRS-6 (`run_prs5_study.cli_env`): `COPILOT_OFFLINE=true`, provider
  type `openai`, wire API `responses`, provider URL = the relay. In this environment `copilot --version` prints
  `1.0.104`.
- Relay: `run_prs5_study.Relay`, request bodies unchanged, PRS-6's headers. Upstream: the Copilot API that GitHub
  names for the account in `/copilot_internal/user` (`https://copilot-api.<tenant>.ghe.com`). Sign-in: Copilot CLI's
  stored token for the account D104 ran under (`~/.copilot/config.json`, `lastLoggedInUser`), read from Windows
  Credential Manager into memory. PRS-6's relay read an OpenCode sign-in, which no longer exists on this machine.
- Lanes `C:\tm-lanes\drr` and `C:\tm-lanes\drc`, D104's names, so the working directories in the prompts match D104's.
  Before the first session, `copilot skill list` and `copilot instruction list` must show only Copilot CLI's built-in
  skills (plus `tokenomics` in `tm`) and no instruction file.
- PRS-6's flags: `--model gpt-6-astra --reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps
  --output-format json`.
- Tasks: Django 5.2 commit `9e7cc2b6`, D01-D15 from `evidence/django-scale-20261022/tasks.json`, in D104's shards and
  orders (PRS-6's): `relay-rare` D09, D01, D07, D03, D05, D04, D08, D02, D06, D10 and `relay-common` D12, D11, D14,
  D13, D15. Both shards at the same time, both arms at the same time, one session per task and arm: 30 sessions.

## Measurement

The relay's record of every model call (PRS-6's `calls.jsonl` and `captures.jsonl`).

- **Raw tokens:** input plus output over the answered calls of a session.
- **As-run cost:** GitHub's charge, `copilot_usage.total_nano_aiu` of each answered call (1e9 nano = 1 AI credit =
  $0.01).
- **Cold-repriced cost:** as-run cost plus, for the session's first answered call, its cache-read tokens times
  (cache-write price minus cache-read price) at that call's own prices.
- **Pass:** PRS-6's grader: the JSON answer lists exactly the answer-key callers, and no file changed.

## Statistics

- Within R104, as in D104: paired ratio of sums (`tm / stock - 1`), 10,000-resample paired bootstrap over tasks (seed
  `20261022`), exact Wilcoxon signed-rank test, Holm over raw tokens and cold-repriced cost.
- Between runs, on the tasks graded in all three: 10,000 task resamples (seed `20261023` for R104 vs D104, `20261024`
  for R104 vs R98) of each arm's change in total and of the difference in `tm / stock` (percentage points of stock).
- One re-run per infrastructure failure: a session with no answered call, or one that ended without a final answer
  after an HTTP 429/5xx or no response (D104's rule), or one with an HTTP 429/5xx or no response and a non-zero exit
  (PRS-6's rule).

## Reading rule

With `d_routing` = R104's `tm / stock` raw-token ratio minus D104's, and `d_rest` = R104's minus R98's (each with its
95% CI):

- **Routing explains the gap** if the CI of `d_routing` is below 0 and the CI of `d_rest` contains 0.
- **Routing explains none of it** if the CI of `d_routing` contains 0 and the CI of `d_rest` is above 0.
- Otherwise **routing explains part of it**, or the run cannot tell. Either way, the share of the gap that routing
  closes, `-d_routing / (D104 - R98)` with each run's `tm / stock` ratio, is reported as a point estimate.

The same reading applies to cold-repriced cost. The verdict is withheld if the audit finds a session on another
Copilot CLI version or model, an answered call without GitHub's charge and prices, a charge that differs from its token
counts at its own prices, or a results row that differs from its recount.

## Limits

- One session per task and arm. The task bootstrap includes session-to-session noise only as far as tasks differ.
- R104 ran about two hours after D104, on the same day.
- R98's lanes were under `%TEMP%` in the 8.3 form, and from such a lane both `1.0.98-2` and `1.0.104` list the
  operator's `CLAUDE.md` and about 170 skills in the relay environment. The second lane test measures what such a lane
  adds to a relay session on `1.0.104` today; the operator's files have changed since October 26.

## Budget

The user approved up to 700 AI credits. The pilot and the lane test spent 52.6 (plus about 0.2 for warm-up calls the
relay does not record). Each running session holds a 40-credit allowance. Budgets: `relay-rare` 320, `relay-common`
240, the second lane test 80. If a shard stops early, the missing sessions are reported and the study does not
continue without a new approval.
