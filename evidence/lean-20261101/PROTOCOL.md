# TokenMaster with --lean under default routing on Copilot CLI 1.0.105: protocol (written November 1, 2026, before any study session)

Exploratory, not pre-registered in the PRS sense. This file is written and its SHA-256 recorded before the 30 study
sessions start, and `analyze.py` applies the decision rule below as written. It repeats
`evidence/default-nolean-20261101` (same day, same Copilot CLI build, same tasks, model, account and harness) with one
change: the TokenMaster arm starts the launcher with `--lean`. Each run is its own stock-versus-TokenMaster
comparison, so the two runs give the default setup's saving and the `--lean` saving on one build.

## Question

On Copilot CLI `1.0.105` under GitHub's default routing, what does TokenMaster save with `--lean` (the 13-tool lean
set, `tokenmaster-nav` and the v6 `view` hook) against stock Copilot CLI?

## Arms

| Arm | Definition |
| --- | --- |
| `stock` | Copilot CLI `1.0.105`, default agent, no TokenMaster component. |
| `tm` | The same CLI after `setup.py --host copilot` (Graphify `0.9.91`) and `brainspace_setup.py --host copilot` from master `e28d1ad`, started through `brainspace_copilot_bridge.py --lean`, as `default_routing_ab.py` does. The launcher adds `--excluded-tools` with the lean set for each prompt. `tokenmaster-nav` and the v6 `view` hook load. The bridge does not run (no provider URL). |

The harness is `token-master-plugin/evals/default_routing_ab.py` at `e28d1ad`, run through `run.py` in this folder,
which changes two things and nothing else: it pins Copilot CLI `1.0.105`, and it raises the install step's timeout
from 900 to 2,700 seconds (as amended for the default-setup run). The launcher keeps `--lean`.

Everything else as in `evidence/default-nolean-20261101/PROTOCOL.md`: default GitHub routing with Copilot CLI's own
sign-in; `--model gpt-6-astra --reasoning-effort low --allow-all-tools --no-ask-user --disable-builtin-mcps
--output-format json`; isolated lanes under `C:\tm-lanes` (`dlr`, `dlc`) with the harness's skill and instruction
checks; sessions back to back in one folder per arm, both arms at the same time.

## Tasks

Django 5.2, commit `9e7cc2b6`, D01-D15, two shards at the same time in PRS-6's orders: `django-rare` D09, D01, D07,
D03, D05, D04, D08, D02, D06, D10 and `django-common` D12, D11, D14, D13, D15. One run per task and arm: 30 sessions.

## Measurement, statistics and decision rule

As in the default-setup run: raw tokens, as-run cost and cold-repriced cost from `assistant_usage_events`; paired
ratio of sums, 10,000-resample paired bootstrap (seed `20261022`), exact Wilcoxon, Holm over raw tokens and
cold-repriced cost. For each of the two endpoints: "lower" if the whole 95% CI of the change is below 0 and the
Holm-adjusted p is below 0.05, "higher" if the whole CI is above 0 and p is below 0.05, otherwise "no significant
difference". A headline may quote the `--lean` saving only if raw tokens are "lower", with the point estimate and its
95% CI. The verdict is withheld if the audit finds a session on another version or model, more than one Copilot
session in a run, a charge that differs from its token counts or from the CLI's own total, or a results row that
differs from its recount.

A headline that sets this saving next to the default setup's quotes each against its own stock arm. The difference
between the two savings is reported with a bootstrap CI over tasks, labelled as a comparison across two runs on the
same day and build.

## Budget

The user approved this run on November 1 (about $3.60). Expected spend is about 370 AI credits. Shard caps
(`--budget-credits`): `django-rare` 370, `django-common` 250, so the caps sit about 120 credits above the expected
spend, for the 60-credit allowance each running session holds. A shard starts no session once its spend plus 60
credits would pass its cap. If a shard stops early, the missing sessions are reported and none is added without a new
approval.
