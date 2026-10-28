# Setup observations (October 27, 2026)

Outputs observed while preparing and piloting the relay control. Sections 1 to 5 made no model call apart from one
15-token sign-in check. `<name>` is the operator's Windows user and `<SHORT~1>` its 8.3 short name.

## 1. The relay's sign-in

`run_prs1_study.load_copilot_token()` reads PRS-6's relay sign-in from `~/.local/share/opencode/opencode.db`, table
`credential`. That table is gone. The file holds one OpenCode session from April 3-4, 2026 and drizzle migrations up
to `20260323234822_events`, and its `log` folder has four logs, all from April 3-4. PRS-6 read a sign-in from this
path on October 26. The installed OpenCode `1.18.15` creates the table when it next runs.

The user chose Copilot CLI's own stored sign-in for the account that the default-routing study (D104) ran under
(`~/.copilot/config.json`, `lastLoggedInUser`, a GitHub Enterprise Cloud account with data residency). Windows
Credential Manager holds it as a generic credential named `<host>:<login>:github.copilot-cli`, an OAuth token of type
`gho_`. `GET https://api.<tenant>.ghe.com/copilot_internal/user` names `https://copilot-api.<tenant>.ghe.com` as the
account's Copilot API. One call through the relay with PRS-6's headers (`Copilot-Integration-Id: vscode-chat`,
`Editor-Version: vscode/1.100.0`), 10 input and 5 output tokens, returned 200 from `gpt-6-astra` with
`copilot_usage.total_nano_aiu` = 35,000,000 and GitHub's prices per million tokens: input $10, cache read $1, cache
write $12.50, output $50. Those are the prices in both earlier runs.

## 2. The version pin in the relay environment

`copilot --version` through the WinGet launcher, with PRS-6's relay environment (`COPILOT_OFFLINE=true`, a provider
URL) and `COPILOT_CLI_DIST_DIR` on the lane's copy of the package:

| Package | Printed |
| --- | --- |
| `1.0.104` | `GitHub Copilot CLI 1.0.104.` |
| `1.0.98-2` | `GitHub Copilot CLI 1.0.98-2.` |

## 3. Transport and tools by routing

Every call in D104's records has `api_endpoint` = `ws:/responses` (91 of 91): under default routing, Copilot CLI
`1.0.104` sent its requests over a WebSocket. In relay mode, Copilot CLI posts `/responses` to the relay on
`http://127.0.0.1`, and the relay sends the same body to the Copilot API over HTTPS.

The tools that D01's sessions offered the model, from Copilot CLI's own event log (`session.usage_checkpoint`) for
D104's runs and from the relay's captures for this run. D104's event logs were not committed (they stay in its local
run folder), so this table is the record of their tool names.

| Routing, Copilot CLI | Stock | TokenMaster | Tools beyond the relay's `1.0.104` set |
| --- | ---: | ---: | --- |
| Default routing, `1.0.98-2` (D104 pilot) | 19 | 11 | `web_fetch` |
| Default routing, `1.0.104` (D104 study) | 20 | 12 | `web_fetch`, `semantic_code_search` |
| Relay, `1.0.104` (this run) | 18 | 10 | none |
| Relay, `1.0.98-2` (section 5 probe, stock only) | 16 | | none; lacks `run_dynamic_workflow` and `dynamic_workflows_manage` |
| Relay, `1.0.98` (PRS-6, `tools_sent` in its summaries) | 16 | 8 | |

Under default routing, both builds offered `run_dynamic_workflow` and `dynamic_workflows_manage`. In the relay
environment, `1.0.104` offers them and `1.0.98-2` does not.

## 4. Inherited instructions and skills depend on how the folder is written

`copilot instruction list` and `copilot skill list` on `1.0.104` in the relay environment, for the same folders
written two ways:

| Working directory | `instruction list` | `skill list` |
| --- | --- | --- |
| `C:\Users\<SHORT~1>\AppData\Local\Temp\opencode\rct\l1\tokenmaster` | `Repository instructions:` (the operator's `CLAUDE.md`) | `Inherited skills:` and the operator's skills, 178 lines |
| `C:\Users\<name>\AppData\Local\Temp\opencode\rct\l1\tokenmaster` | `No instruction sources found.` | `Builtin skills:` only |

A second folder gave the same pair of results, and `1.0.98-2` also lists the operator's files from the 8.3 form. The
first lane test ran from the long form and so inherited nothing. PRS-6's lanes and the default-routing probe's were
recorded in the 8.3 form, which is what Python's `tempfile.gettempdir()` returns on this machine.

## 5. The first request by build, lane and launcher, without a model call

`dead_upstream_probe.py` starts a stock D01 session in the relay environment with the relay's upstream on a closed
local port, so the relay captures the first request and nothing leaves the machine. Sizes in cl100k tokens
(`dead_upstream_probe.json`):

| Copilot CLI | Lane | Request | Tools | Operator `CLAUDE.md` | Skills listed |
| --- | --- | ---: | ---: | :---: | ---: |
| `1.0.98-2` | `C:\tm-lanes` | 12,152 | 16 | no | 2 |
| `1.0.98-2` | `%TEMP%`, 8.3 form | 22,487 | 16 | yes | 25 |
| `1.0.104` | `C:\tm-lanes` | 14,195 | 18 | no | 2 |
| `1.0.104` | `%TEMP%`, 8.3 form | 24,530 | 18 | yes | 25 |

"Skills listed" counts the entries of the request's `available_skills` list: the 2 built-in skills from a clean lane,
and 23 more from the 8.3 form (`copilot skill list` there prints about 170 inherited skills, some of which fail to
load).

The probe also ran through the launcher that auto-update replaced on October 27 at 12:58 UTC (`8ff1371e...`, last
written May 19, so most likely the one PRS-6 ran on October 26; PRS-6's records hold no launcher hash). Every row is
within 10 tokens of these (`dead_upstream_probe-launcher-8ff1371e.json`).

- `1.0.104` sends two tool definitions that `1.0.98-2` does not: `run_dynamic_workflow` (1,247 tokens) and
  `dynamic_workflows_manage` (963). The other 16 are the same size in both builds. TokenMaster's lean tool set (11
  tools, chosen from the October 18 runs) removes neither, so on `1.0.104` they are in every call of both arms. For a
  stock D01 first request, GitHub counted 12,784 tokens (this run's pilot), and the probe's equivalent request counts
  14,195 cl100k tokens: 0.90 GitHub tokens per cl100k token. At that rate the two tools are about 1,990 GitHub tokens,
  a quarter of TokenMaster's first call (median 7,614) and a sixth of stock's (12,784).
- PRS-6's 15 stock first calls on these tasks were 11,194 to 11,205 GitHub tokens. At 0.90 GitHub tokens per cl100k
  token, the probe's `1.0.98-2` requests come to about 10,940 from `C:\tm-lanes` and 20,250 from the 8.3 form; PRS-6's
  are within 2.5% of the first. PRS-6's sessions did not carry the operator's files, although its lanes were recorded
  in the 8.3 form. Neither `1.0.98-2` nor the older launcher avoids the inheritance today, and why PRS-6 avoided it
  was not tested: its build, `1.0.98`, is no longer on this machine.

## 6. Pilot, lane test and the changes they led to

D01, both arms, GitHub's charges:

| Session | Lane | First call input | Raw tokens | Calls | Credits |
| --- | --- | ---: | ---: | ---: | ---: |
| Pilot, stock | `C:\tm-lanes` | 12,784 | 40,728 | 3 | 21.67 |
| Pilot, TokenMaster | `C:\tm-lanes` | 7,612 | 24,017 | 3 | 12.66 |
| Lane test, stock | `%TEMP%`, long form | 12,820 | 41,137 | 3 | 12.51 |
| Lane test, TokenMaster | `%TEMP%`, long form | 7,649 | 15,666 | 2 | 5.75 |

All four passed, ran `1.0.104` and had GitHub's charge on every call. The bridge applied its cache-stable system
prompt to 3 of 3 pilot calls. The lane test's stock session started warm (8,210 cached tokens) from the pilot's,
ten minutes earlier on the same account. The two TokenMaster sessions of the same task differ by a third of their
tokens (3 calls against 2), an example of the noise in one session per task.

A code review of the harness after the pilot found no blocker and led to the four changes listed in `PROTOCOL.md`,
committed with it before the study. `PROTOCOL.md` also planned a second lane test from the 8.3 form after the study.
It did not run: the probe in section 5 answered its question without model calls, and its 80-credit reserve was not
spent.
