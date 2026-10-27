# Setup observations (October 27, 2026)

Outputs observed while preparing the default-routing A/B, before and during the probe and the pilot. None of the
commands in sections 1 and 3 made a model call. Times are UTC. `<lane>` is a lane's home folder; `<name>` is the
operator's Windows user.

## 1. Pinning a Copilot CLI package

`copilot --version` through the WinGet launcher
(`%LOCALAPPDATA%\Microsoft\WinGet\Packages\GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe\copilot.exe`), with
the package copied into a lane's profile:

| Environment | Printed |
| --- | --- |
| `COPILOT_CLI_DIST_DIR=<lane>\...\pkg\win32-x64\1.0.98-2` | `GitHub Copilot CLI 1.0.98-2.` |
| the same, plus `COPILOT_AUTO_UPDATE=false` | `GitHub Copilot CLI 1.0.49.` |
| `COPILOT_CLI_DIST_DIR=<lane>\...\pkg\win32-x64\1.0.104` | `GitHub Copilot CLI 1.0.104.` |
| the same, plus `COPILOT_AUTO_UPDATE=false` | `GitHub Copilot CLI 1.0.49.` |

The package cache held 1.0.95-3, 1.0.96-2, 1.0.98-2, 1.0.103 and 1.0.104. PRS-6's `1.0.98` folder was gone.

## 2. Auto-update under default routing (pilot)

Copilot CLI's own logs in the pilot lanes' `COPILOT_HOME\logs`:

- 13:32:38, D01 session on `1.0.98-2`: `Successfully downloaded package, restart to update to version 1.0.104` and
  `Downloading updated win32-x64 binary...`.
- 13:34:47, the next session in the same lane (D13): `Starting Copilot CLI: 1.0.104` and `No update needed, current
  version is 1.0.104, fetched latest release is v1.0.104`.

The lanes' package caches then held `1.0.104` next to `1.0.98-2`. The shared WinGet launcher (`copilot.exe`) was
rewritten as well: once during the probe (12:58), and again during the pilot (13:32), which kept the 12:58 binary as
`copilot.exe.old-98468-1793107967058`. The probe's and the pilot's `setup.json` record different launcher hashes
(`8ff1371e...` and `07768311...`). The study pinned `1.0.104`, and its sessions logged no further update.

## 3. Instructions and skills inherited from ancestor folders

The operator's profile folder holds `.claude` (a `CLAUDE.md` and 101 entries in `skills`), `.copilot` (109 entries in
`skills`), `.agents` (93 entries in `skills`) and `.codex`. `C:\` and `C:\Users` hold none of these.

| Lane (a git repository) | `copilot skill list` | `copilot instruction list` |
| --- | --- | --- |
| `C:\Users\<name>\AppData\Local\Temp\opencode\dr-probe\l1\tokenmaster` | `Inherited skills:` and the operator's skills, 178 lines | `Repository instructions:` `CLAUDE.md` |
| `C:\tm-lanes\leaktest\l1\tokenmaster` | `Builtin skills:` `customize-cloud-agent`, `github-pr-media` | `No instruction sources found.` |

The probe ran from `%TEMP%` lanes. Its stock session's system message held a `custom_instruction` section of 15,630
characters with the operator's `CLAUDE.md` headings, and an `available_skills` list. First calls:

| Session | Lane | Copilot CLI | First call input tokens |
| --- | --- | --- | ---: |
| Probe, SMOKE, stock | `%TEMP%` | `1.0.98-2` | 23,463 |
| Probe, SMOKE, TokenMaster | `%TEMP%` | `1.0.98-2` | 11,582 |
| Pilot, D01, stock | `C:\tm-lanes` | `1.0.98-2` | 13,519 |
| Pilot, D01, TokenMaster | `C:\tm-lanes` | `1.0.98-2` | 7,723 |

The SMOKE and D01 prompts differ by about 60 tokens. The study's `setup.json` files record `copilot skill list` and
`copilot instruction list` for both lanes (`lane_sources`).

## 4. Model under default routing

The account's server policy carries the keys `model` and `permissions`. The operator's own Copilot CLI `1.0.104` log
(03:47) says that `permissions.model` has an unsupported or malformed value and was ignored. With
`--model gpt-6-astra` and default routing, every probe call in Copilot CLI's store recorded `gpt-6-astra`
(`probe-astra/runs/*/calls.jsonl`).

## 5. Graphify's skill refresh

Running `graphify --version` from a graphify `0.9.91` environment, with the operator's own environment, rewrote
`~/.claude/skills/graphify` (`SKILL.md`, a new `references` folder and `.graphify_version`) and kept the old
`SKILL.md` as `SKILL.md.bak`. The files were restored by hand. The harness sets `GRAPHIFY_NO_AUTO_REFRESH=1`, and its
installs run with a lane's own home folder.
