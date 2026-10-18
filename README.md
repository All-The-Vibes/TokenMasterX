# TokenMaster

<p align="center">
  <img src="assets/tokenmaster-hero.svg?v=2" alt="TokenMaster" width="100%">
</p>

TokenMaster is an experimental toolkit that tries to cut the real cost of AI coding
agents. It has two parts:

1. **Tool-result shaping (`request-policy-v6`):** a runtime that shapes each tool
   result once, when it enters the conversation. It packs search output
   losslessly and turns oversized results into short digests. It never rewrites
   history, so the provider's prompt cache keeps working.
   - It is the default policy of the native Copilot route, which keeps the
     client's parallel tool calls.
   - It also runs in the Copilot output hook, which is installed by default and
     shapes whole-file `view` results.
2. **Graph-first navigation (v7, `brainspace/symbol_index.py`):** three compact tools
   over graphify's call graph and an exact-range symbol index.
   - `locate` finds a symbol or a file's outline.
   - `read_symbol` returns exactly one symbol or range.
   - `impact` lists callers.
   - Every result stays under 2,400 tokens.

   Host setup (`setup.py`) installs v7 as one MCP server, `tokenmaster-nav`, with a
   short agent prompt. It replaces the older graph routing (graphify-nav and
   codegraph servers plus a 1,383-token routing prompt), which PRS-2 measured as more
   expensive.

## Current evidence: PRS-4 (October 18, 2026) — v7 + cache-stable prompt cuts cost by 50%

Pre-registered live study:
- 360 sessions on 24 fresh tasks, written by agents that were not told the arms.
- Model: `gpt-6-astra`. Primary endpoint: billed cost per finished task, at the provider's own
  prices (cache read 0.1, cache write 1.25, output 5, relative to uncached input).
- Every token was recounted from raw captures and checked against the provider's bill.

| Configuration | Passed | Change per finished task vs. stock (95% CI) | Holm p |
| --- | ---: | ---: | ---: |
| v7 (v6 + navigation tools) | 120/120 | −18.2% (−26.6%, −9.5%) | 0.00049 |
| **v7 + cache-stable system prompt** | **120/120** | **−49.8% (−57.1%, −42.9%)** | **< 0.00001** |

- **The 30% goal is met** under continuous use: sessions of one repository back to back,
  so 119 of 120 first calls read the system prompt from the cache.
- Isolated sessions (more than about 30 minutes apart) save about 19%, as v7 alone does.
- Only the native Copilot route applies the cache-stable prompt today. It is experimental
  and read-only; the default install gets the v7 result at most.

Details: [PRS4_RESULTS.md](token-master-plugin/docs/PRS4_RESULTS.md).

## Earlier evidence: PRS-3 (October 18, 2026) — v7 cuts cost by 22%

Pre-registered live study:
- 480 sessions on 24 fresh tasks, written by agents that were not told the arms.
- Model: `gpt-6-astra`. Cost = uncached input + 0.1 × cached input + 8 × output.
- Every token was recounted from raw captures.

| Configuration | Passed | Cost change vs. stock (95% CI) | Holm p |
| --- | ---: | ---: | ---: |
| v6 | 120/120 | −13.0% (−19.3%, −6.7%) | 0.0001 |
| **v7** (v6 + navigation tools) | **120/120** | **−22.0% (−35.4%, −8.9%)** | **0.006** |

- **v6 replicated** its PRS-2 result (−11.6%) on new tasks.
- **v7's extra saving over v6 alone is not established:** −10.4%, p = 0.16. It is
  concentrated on "who calls X" tasks: −52% against v6, an exploratory result. One
  sentence of advice without the tools saved 4.8% (not significant).
- **The goal of at least 30% savings was not met by PRS-3.** PRS-4 met it (above).

Details: [PRS3_RESULTS.md](token-master-plugin/docs/PRS3_RESULTS.md).

## Earlier evidence: PRS-2 (October 18, 2026) — v6 lowers cost

On 12 fresh tasks, v6 cut cost by **11.6%** (95% CI −20.8% to −3.8%, Holm p = 0.014),
with quality at 36/36. The graph tools as shipped raised cost by 12.9%.
Details: [PRS2_RESULTS.md](token-master-plugin/docs/PRS2_RESULTS.md).

## Earlier evidence: PRS-1 (October 18, 2026)

PRS-1 is a pre-registered live study: 252 sessions, 12 real tasks on this
repository, 7 arms, `gpt-6-astra`, and the real GitHub Copilot CLI system prompt.
The tasks were written by an agent that was not told the arms. Every token count
was recounted from raw captures.

| Arm | Passed | Total tokens | Change vs. baseline (95% CI) | Cache-weighted change (95% CI) |
| --- | ---: | ---: | ---: | ---: |
| baseline | 36/36 | 2,082,599 | — | — |
| baseline_parallel | 35/36 | 1,399,967 | −32.8% (−50.4%, −8.8%) | −7.1% (−20.0%, +8.2%) |
| ponytail | 34/36 | 2,498,333 | +20.0% (−2.0%, +47.3%) | +19.6% (+6.1%, +38.1%) |
| headroom | 35/36 | 1,820,351 | −12.6% (−29.3%, +7.9%) | −9.8% (−22.2%, +3.5%) |
| graph | 36/36 | 2,060,438 | −1.1% (−35.1%, +42.1%) | +15.0% (−10.7%, +43.9%) |
| v5 | 36/36 | 2,245,809 | +7.8% (−24.7%, +49.8%) | **+61.6% (+19.6%, +111.0%)** |
| graph_v5 | 36/36 | 2,182,011 | +4.8% (−32.2%, +52.8%) | **+57.0% (+10.1%, +118.0%)** |

- **No TokenMaster configuration significantly reduced total tokens.**
- **v5 raised cache-weighted cost by 61.6%.** Rewriting earlier messages breaks the
  provider's prompt cache, and v5 sessions made 13% more model calls.
  Cache-weighted means cached input counts at 10%.
- **Quality held:** every TokenMaster arm passed 36/36.
- **Parallel tool calls** gave the largest observed reduction (−32.8%), but the
  Holm-adjusted p is 0.11, so it is not significant under the pre-declared rule.
  TokenMaster's transport currently forces parallel tool calls off.

Full results: [PRS1_RESULTS.md](token-master-plugin/docs/PRS1_RESULTS.md).
Protocol: [PRS1_PROTOCOL.md](token-master-plugin/docs/PRS1_PROTOCOL.md).

> **Retraction (October 18, 2026).** The October 17 savings claims (−83.29%,
> −73.19%, −65.68%, −48.51%, −44.20%, −43.14%) are withdrawn. They came from
> synthetic modules padded with repetitive lines, scripted file reads, extra tools
> in the baseline, a misconfigured Headroom adapter, and ignored prompt caching.
> The scripts that produced them are kept only as synthetic mechanism checks.

## How it works and where it falls short

| Component | Mechanism | Measured limits |
| --- | --- | --- |
| Graph-first navigation (v7) | `locate`, `read_symbol` and `impact` over a SQLite symbol index with exact line ranges and graphify's call graph. Every result is capped at 2,400 tokens; the tool definitions are 269 tokens. | PRS-3: −22.0% cost against stock, 120/120 passed. Against v6 alone, −10.4% (not significant). Cheaper on "who calls X" tasks, about equal on locate, logic and docs tasks, and 9% dearer on edits (exploratory). Installed by `setup.py` as the `tokenmaster-nav` MCP server. |
| Graph routing (before v7) | `graphify-nav` (6 tools) and `codegraph` MCP servers on prebuilt indexes, plus a routing agent prompt. | Added about 2,100 tokens to every call; PRS-2: +12.9% cost. `setup.py` now removes these servers when TokenMaster owns them. |
| `request-policy-v6` | Shapes each tool result once, deterministically, when it enters the conversation. Folds search and list output losslessly; turns oversized results into digests that name what was omitted and how to fetch it. | PRS-2: −11.6% cost; PRS-3: −13.0% cost on new tasks. Quality unchanged. Never rewrites history, so the provider's cache stays valid. |
| `request-policy-v5` | Keeps the newest tool result verbatim. Compacts older `view` results (code skeletons, JSON overviews, Markdown and log summaries) behind one `[[BR:<sha256>\|r=1]]` reference with exact SQLite recovery. | Removed 15.7% of tokens on the requests it changed. Uncached input still rose 94.8%, because each rewrite invalidates the cached prefix. Superseded by v6. |
| Runtime transport | Captures every request and reply for whole-task accounting. | The native route now keeps the client's parallel tool calls (default on). Earlier versions forced them off, which PRS-1 suggested was costly. |

## Version history

| Version | What it did | What testing showed |
| --- | --- | --- |
| `v1` / `v2` | Tree-sitter skeletons with a 190-byte reference per function | Multi-function files barely shrank, and extra recovery calls raised totals. |
| `v3` | Exact reuse of repeated identical reads | 9.9% on forced duplicate reads; 0% on ordinary workflows. |
| `v4` | Lossless JSON whitespace compaction | 1.43% across an 8-task suite. |
| `v5` | Multi-format compaction with one compact-root reference per file | PRS-1: +7.8% total tokens (not significant), +61.6% cache-weighted cost, 36/36 passed. |
| `v6` | Shapes each tool result once, deterministically: lossless folding, budgeted digests, history never rewritten | PRS-2: −11.6% cost on fresh tasks (95% CI −20.8% to −3.8%), 36/36 passed. PRS-3: −13.0% on 24 new tasks, 120/120. |
| `v7` | v6 plus graph-first navigation: `locate`, `read_symbol`, `impact` on graphify's call graph and exact line ranges | PRS-3: −22.0% cost against stock (95% CI −35.4% to −8.9%), 120/120 passed; −10.4% against v6 (not significant). |

The lesson: compaction that rewrites conversation history fights prompt caching.
Shape each result once, when it enters the conversation, and leave history alone.

## Reproduce PRS-1

```powershell
$env:BRAINSPACE_TOKENIZER_FILE = "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
$py = ".\.token-master-dev\Scripts\python.exe"
$h = "token-master-plugin\evals\run_prs1_study.py"
& $py -B $h self-test                                         # offline checks
& $py -B $h prepare --output evidence\prs1-new\study          # freeze snapshot, tasks, prompts, schedule
& $py -B $h probe-headroom --output evidence\prs1-new\probe   # offline Headroom mechanism check
& $py -B $h smoke --output evidence\prs1-new\study            # one dummy task per arm
& $py -B $h run --output evidence\prs1-new\study              # 252 live sessions
& $py -B $h analyze --output evidence\prs1-new\study          # recount from raw captures
```

Live runs need these:

- An active GitHub Copilot sign-in in OpenCode. The token is read in memory and
  never written.
- Local installs of `graphify`, `codegraph` and `headroom-ai`.

Their paths are listed at the top of `run_prs1_study.py`.

## Tests

```powershell
$env:BRAINSPACE_TOKENIZER_FILE = "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
.\.token-master-dev\Scripts\python.exe -B -m pytest -q token-master-plugin/skills/token-master/tests
```

Status on October 18, 2026 (Windows): 4,396 passed, 4 skipped, 82 failed. The same 82
tests also fail on a clean checkout of commit `703aa20`, so they predate the v5 changes:

- 76 need the trusted Linux sandbox runner, which is not available here.
- 5 fail because the committed `evals/repository-cases.json` (`b9d54dfb…`) no longer
  matches its pinned hash (`f4ebd67e…`).
- 1 needs a local evidence file that is not in the repository.

## Documentation

- [Documentation index](token-master-plugin/docs/README.md)
- [PRS-4 results](token-master-plugin/docs/PRS4_RESULTS.md) and [protocol](token-master-plugin/docs/PRS4_PROTOCOL.md)
- [PRS-3 results](token-master-plugin/docs/PRS3_RESULTS.md) and [protocol](token-master-plugin/docs/PRS3_PROTOCOL.md)
- [PRS-2 results](token-master-plugin/docs/PRS2_RESULTS.md) and [protocol](token-master-plugin/docs/PRS2_PROTOCOL.md)
- [PRS-1 results](token-master-plugin/docs/PRS1_RESULTS.md) and [protocol](token-master-plugin/docs/PRS1_PROTOCOL.md)
- [Single-slide summary](docs/tokenmaster-v5-slide.html)
- [Mission](MISSION.md) and [changelog](CHANGELOG.md)
- The documentation index lists the historical `v1`–`v4` studies.

## License

[MIT](LICENSE)
