# Research: Ponytail implemented behavior, evidence, and installed-bundle parity

## Request Type

Bounded comprehensive source-reference research. Retrieved and verified **October 4, 2026**.

Scope: the requested upstream revision and the named installed bundle only. No TokenMaster architecture inspection, production edits, dependency installations, host-configuration changes, model/API benchmark runs, service launches, commits, pushes, subagents, or cross-chat messages.

Evidence labels:
- **Fact**: inspected file content or fresh bounded execution.
- **Publisher claim**: an upstream statement or historical result, not independently reproduced here.
- **Inference**: an interpretation of the inspected implementation, explicitly qualified.

## Direct Answer

1. **Upstream Ponytail is principally behavioral guidance plus real instruction-delivery/state adapters—not a deterministic code simplifier or task/scope/output policy engine.** Its executable Claude/Codex hooks select an intensity, persist a small mode flag, and inject instructions. They do not inspect diffs, prohibit unnecessary dependencies, enforce output length, verify generated tests, or block completion on quality failures. “Enforced” in the skill is prose, not a compiler, AST transformation, or permission gate. [U01], [U07], [U08], [U09], [U10], [U11]
2. **Review/audit/debt/gain are substantial workflow specifications, but not implemented analysis engines.** Review and audit direct the model to report complexity findings; debt supplies a grep recipe and ledger format; gain prints historical constants, expressly not per-repository savings. [U02], [U03], [U04], [U05]
3. **The installed `engineering-suite-ponytail` 2.0.0 package is not upstream 4.10.3.** It is a 29-file, skills-only repackaging with an entry router, six Ponytail skills, an auxiliary code-simplification skill, references/assets/licenses, and no hooks or MCP runtime. Its lock points to upstream **4.9.0**, commit `356918eba965ee1eac64bd3a7f0dd02108350de5`. All six skill bodies match that older pin after removing frontmatter; all six whole files differ because packaging changes frontmatter. Four bodies differ from the requested current pin. [L01], [L02], [L03], [L04]; `installed-manifest.json`, `skill-parity.json`, `skill-parity.diff`
4. **There is a genuine benchmark/evaluation harness with executable graders and adversarial references. There is not sufficient checked-in evidence to independently validate all published savings or quality claims at the requested revision.** Raw single-shot results and agent workspaces are absent from its complete Git tree and explicitly ignored. The gain card still says 47–77% lower cost, while a later upstream cost report revises that to 42–75% for its Claude runs and reports higher costs for two OpenAI reasoning-model runs. [U05], [U20], [U25], [U29], [U30]
5. **Fresh offline evidence:** 21 selected Node tests passed; 6 LOC and 4 correctness regressions passed; 20 good/bad references across 10 agentic scorers passed; rule/version consistency and the offline completeness-gate test passed. A direct isolated hook probe confirmed **compact/resume resets the mode to the configured default**, rather than reliably preserving a manually selected level/off state. These are implementation/instrument checks, not a fresh model-quality A/B. `verification-summary.json`, `verification/`

## Version Note and Provenance

| Object | Verified identity | Meaning |
|---|---|---|
| Requested upstream | `DietrichGebert/ponytail@c982cd411abb53323c4baa1baa3c2f020b8d0b08`; author and committer timestamp `2026-10-03T05:12:55Z`; package/manifests 4.10.3 | Research is pinned to this commit. “Main tip fetched October 4” is the caller's selection context; no moving-branch substitution was made. [U12], [U13], [U14], [P01] |
| Installed bundle | `.codex-plugin/plugin.json`: `engineering-suite-ponytail`, 2.0.0, author Saul Martí, skills path only | Bundle release numbering is independent of upstream release numbering. Cache presence does not prove active loading or successful host execution. [L01] |
| Bundle's Ponytail provenance | `UPSTREAM_LOCK.json:46-58`: `356918eba965ee1eac64bd3a7f0dd02108350de5`; GitHub commit timestamp `2026-09-07T16:27:00Z`; root package 4.9.0 | Six vendored skill bodies were compared against the actual archive at this older commit, not merely against its lock claim. [L03], [P02], [P03] |

**Integrity checks:** all **169/169** upstream archive files matched their expected Git blob SHA-1s from the pinned Git tree; the API tree is not truncated. SHA-256s are recorded independently in `upstream-hashes.json`. GitHub reports the selected commit signature as verified; this is GitHub's attestation metadata, not an independently verified PGP signature or a software-security assurance. See `upstream-commit.json` and `upstream-tree.json`.

Full byte hashes for all six skills at all three surfaces, and relevant package metadata, are in **`HASHES.md`**. `installed-manifest.json` records all 29 installed-file hashes. Only relevant bundle source content was copied to `installed-evidence/`; no other installed plugins or user content were collected.

## Official Docs Evidence

These are current host/protocol contracts, **not pinned Ponytail implementation evidence**:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks): documents `SessionStart`, `SubagentStart`, `UserPromptSubmit`, `PostToolUse`, plugin hook manifests, review/trust of exact hook definitions, `PLUGIN_DATA`, compatibility `CLAUDE_PLUGIN_ROOT`, and optional `commandWindows`. Thus **Codex does support hooks**; the installed bundle simply does not ship them. Snapshot: `official-docs/codex-hooks.readable.txt:996-1047,1143-1155,1294-1316`.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks): documents context injection, executable command hooks, shell/exec behavior, and that command hooks run with the user's permissions. Snapshot: `official-docs/claude-hooks.readable.txt:460-495,995-1035,3803-3808`.
- [Claude Code setup](https://code.claude.com/docs/en/setup): current Windows support includes native Windows and WSL; Git for Windows is optional in the current native setup, with PowerShell used when Git Bash is absent. This should not be replaced by older “Git Bash always required” advice. Snapshot: `official-docs/claude-setup.readable.txt:106-135`.
- [MCP prompts, protocol revision 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts): prompts expose retrievable message templates and are designed for user-controlled invocation; the protocol does not mandate a particular UI. Snapshot: `official-docs/mcp-prompts.readable.txt:65-82`.

Direct HTTPS snapshots and retrieval metadata are retained in `official-docs/`. The web-search/open tool returned empty responses during this run, so primary pages were fetched directly; Claude hook documentation was additionally retrieved through Context7. No third-party compatibility article substitutes for these sources. Host docs can evolve independently of this Ponytail commit. The caller's newer host-doc checkpoint was incorporated; tool-output rewriting and TokenMaster's adapter remain outside this report.

## Source-Reference Evidence

### 1. Task, scope, output, and intensity discipline

| Surface | Actual specified behavior | Enforcement/evidence boundary |
|---|---|---|
| Main skill | Understand the touched flow first; grep callers for root-cause fixes; then try YAGNI, existing repository helpers, stdlib, native platform, installed dependencies, one-line/minimum implementation. Prefer deletion and few files. [U01:32-64](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L32-L64) | Instructions to the model. No repository inspector, scope allowlist, task state machine, automatic deletion detector, or dependency gate is wired to these rules. Hook output is instruction context. [U07], [U11] |
| Output | Code first, at most three unsolicited explanatory lines; explicitly requested reports/walkthroughs remain full-length. [U01:66-75](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L66-L75) | Not an output validator. “What you build, not how you talk” coexists with terse-output rules; interpret the explicit requested-explanation exception rather than claiming no prose guidance. [U01:114-120](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L114-L120) |
| Levels | Lite fulfills the request and names a simpler alternative; full applies the ladder; ultra challenges scope more aggressively. [U01:77-95](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L77-L95) | Instruction builder strips frontmatter and filters **intensity rows and quoted examples**, not all other prescriptive prose. Therefore lite is not a separate permissive execution policy; shared rules still reach the model. [U11:11-41,77-91] |
| Safety/completeness floor | Preserve trust-boundary validation, loss-preventing errors, security, accessibility, explicit requirements, hardware calibration; nontrivial logic should leave one runnable check. [U01:90-112](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L90-L112) | No automatic confirmation that the check exists, executes, or covers the change. The benchmarks test some behaviors separately; their presence does not enforce them in ordinary sessions. [U21], [U22] |
| Always-on rule copies | `AGENTS.md` and host rule files carry a compact discipline; check-rule-copies verifies consistency and selected invariants. [U15], [U36] | Rule-file portability is not equivalent to lifecycle-hook persistence, command availability, or host isolation. |

### 2. Review, audit, debt, gain, and help

- **Review:** diff-focused, location/tag/replacement per finding, estimated net removable lines. It explicitly excludes correctness/security/performance review and does not apply fixes. Its smoke-test minimum must not be flagged as bloat. The new `reuse:` tag names an existing repository helper. **Inference:** it complements, rather than replaces, a general quality/security review. [U02:13-60](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-review/SKILL.md#L13-L60)
- **Audit:** whole-tree complexity report, largest cuts first, estimated lines/dependencies removable. Current source adds a whole-tree reference search—including tests, fixtures, strings/dynamic references—before a `delete:` finding. This is a model instruction, not a sound unused-symbol analysis. [U03:12-44](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-audit/SKILL.md#L12-L44)
- **Debt:** asks the agent to run textual grep for `#`, `//`, or `/*` Ponytail markers while excluding `.git`, `node_modules`, `dist`, `build`; extracts ceiling/upgrade trigger, flags missing triggers, optionally uses blame, and only persists a ledger on request. No standalone parser, debt database, owner integration, or background maintenance service is shipped. The regex is not AST/comment-aware, and its language coverage is explicitly extensible. [U04:15-44](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-debt/SKILL.md#L15-L44)[U35:41-93](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/tests/commands.test.js#L41-L93)
- **Gain:** a static benchmark scoreboard, no calculation against the active repository, no token meter, no mode change. Its warning against inventing counterfactual per-repository savings is valuable, but the printed historical cost range has drifted from the later cost report. [U05:13-49](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-gain/SKILL.md#L13-L49)[U30:7-22,48-85]
- **Help:** static reference card. Current upstream corrects Codex CLI/IDE skill invocation from `@` to `$`. It describes full-upstream runtime configuration; that is not proof those capabilities exist in a skills-only repackaging. [U06:35-67](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-help/SKILL.md#L35-L67)[L08]

These command surfaces ultimately supply prompts/skill bodies. The source tree contains runtime adapters and benchmark analyzers, but no production review/audit/debt calculation engine behind the corresponding skill names. Pi, for example, registers the report commands separately from its session-level command. [U16:116-175](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/pi-extension/index.js#L116-L175)

### 3. Session persistence and hooks: substantive implementation, important limits

**Fact—registered events:** the shared Claude/Codex hook map registers **three** events, `SessionStart` (startup/resume/clear/compact), `SubagentStart`, and `UserPromptSubmit`; each runs a Node script with a five-second host timeout. README references to “two lifecycle hooks” are stale relative to this map. No Claude/Codex `PreToolUse`, `PostToolUse`, or completion-gating hook is registered here. [U07] [U18:124-151](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/README.md#L124-L151)

**Fact—state and configuration:**
- Default resolution is `PONYTAIL_DEFAULT_MODE` → config `defaultMode` → full. Runtime defaults are off/lite/full/ultra; review is not a valid default in the shared JS resolver. XDG config override is honored; native Windows fallback is APPDATA/Ponytail. [U09:16-34,54-100]
- Runtime writes `.ponytail-active`; with `CLAUDE_PROJECT_DIR`, it also writes a per-project filename under `ponytail-modes/`. Codex detection uses `PLUGIN_DATA` and writes there, not blindly into the user's Claude directory. [U10:19-75](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-runtime.js#L19-L75)
- `/ponytail default <mode>` is the explicit persistent-config path and does not switch the current session. Regular level switches only write mode state. Standalone “stop ponytail”/“normal mode” clear state; those phrases embedded in ordinary requests do not. Bare `/ponytail` reports the current active level or enables the configured level (full when the default is off). Report skill commands do not latch review as a session level. [U08:41-122](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-mode-tracker.js#L41-L122)[U09:36-43,136-150]
- On ordinary Claude/Codex prompts, the tracker is generally silent; it does not re-inject the full ruleset every turn. Full text is injected at activation and subagent start; mode changes send a header, relying on host skill/context behavior for the rest. This differs from some other adapters. [U08:87-145](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-mode-tracker.js#L87-L145)[U11]

**Verified caveat—resume/compaction:** activation unconditionally calls `getDefaultMode()` and writes that mode; it does not inspect the incoming SessionStart source or restore the existing mode flag. Because the manifest includes `compact` and `resume`, a manual ultra selection becomes full on compact when full is configured; off can reactivate on resume. The isolated runtime probe observed both transitions. This qualifies the skill's “persists until changed or session end” prose. [U07] [U17:29-62](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-activate.js#L29-L62); `verification/runtime-state-probe.stdout.txt`

**Other limits/inferences:**
- Two sessions in the **same repository share** a mode; the shared status badge is last-writer-wins. The implementation comments acknowledge this. Project filenames use lossy character replacement, not a collision-resistant key; potential path collisions are an inference, not reproduced here. Writes are ordinary synchronous file writes, not a transactional/session-ID store. [U10:44-75](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-runtime.js#L44-L75)
- Subagent injection defaults to all subagents. Optional case-insensitive regex matching is bounded by a 100 ms VM evaluation timeout; invalid/missing/unparseable/timeout cases **fail open to injection**, not closed to exclusion. Thus the matcher is persona scoping, not a security boundary. [U19:8-94](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-subagent.js#L8-L94)
- The tracker has a one-second stdin fallback and best-effort/silent failure behavior. This prevents certain hangs, but a successful exit is not evidence that a command was parsed or context reached a host. [U08:147-170](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-mode-tracker.js#L147-L170)[U34]
- Pi uses session custom entries and per-turn instruction injection; OpenCode persists a shared mode file and injects system context per turn. These are actual adapters, but their persistence contracts must not be generalized to Claude/Codex or the installed bundle. They were inspected, not host-tested here. [U16:24-35,93-100,185-228] [U37:29-61,133-178]

**Telemetry:** no publisher telemetry endpoint, automatic token/cost collection, or savings ledger was found in the inspected lifecycle hooks, instruction/config modules, MCP runtime, or inspected Pi/OpenCode adapters. The state is mode/status data, not measured savings. Separately, the **benchmark harness** captures model/CLI usage, cost, latency, turns, and denial counts in local result files. This negative finding is scoped to inspected code; it is not a claim about host telemetry or all downstream dependencies. [U08], [U09], [U10], [U16] [U23:262-286](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/run.py#L262-L286)[U24], [U37]

### 4. Installed packaging: overlap and exact drift

`SNAP` means exactly:
`C:\Users\shyamsridhar\.codex\plugins\cache\openai-curated-remote\engineering-suite-ponytail\2.0.0`

The package manifest advertises only `./skills/`; README calls it skills-only. Inventory contains **no `hooks/`, `ponytail-mcp/`, benchmark/test directories, package.json, or upstream AGENTS.md**. The entry skill routes intent to bundled workflows and reserves code-simplification for an auxiliary clarity pass. These are packaging facts, not evidence that the host loaded or obeyed the router. [L01], [L02], [L04]; `installed-manifest.json`

| Skill | Body matches locked 4.9.0 | Body matches requested 4.10.3 | Material drift |
|---|---|---|---|
| ponytail | Yes | Yes | Core ladder, root-cause, output exceptions and safety/check guidance overlap. |
| ponytail-review | Yes | No | Installed copy lacks current `reuse:` tag and example. [L05:15-36] [L05] [U02:21-46](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-review/SKILL.md#L21-L46) |
| ponytail-audit | Yes | No | Lacks current reuse guidance and explicit whole-tree reference check before deletion findings. [L06:14-24] [L06] [U03:19-33](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-audit/SKILL.md#L19-L33) |
| ponytail-debt | Yes | No | Installed grep mentions skipping directories in prose but does not actually pass exclusion flags; it also omits `/*` recognition. [L07:13-19] [L07] [U04:17-23](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-debt/SKILL.md#L17-L23) |
| ponytail-gain | Yes | Yes | Same historical scoreboard and non-per-repo boundary—including stale cost range. |
| ponytail-help | Yes | No | Installed Codex `@` forms versus current CLI/IDE `$` forms. [L08:33-35] [L08] [U06:35-37](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-help/SKILL.md#L35-L37) |

“Body” equality means **remove YAML frontmatter, normalize line endings, compare the remaining text exactly**, not semantic similarity. **None** of the six whole files equals either upstream original byte-for-byte: the package serializes descriptions differently and adds `disable-model-invocation: true`. The entry router lacks that flag. This shows explicit packaging intent, but this report does not claim how every host interprets that metadata. The package's “unmodified skill files” notice is therefore accurate for these locked bodies, **not for complete files**. [L04], [L09]; `HASHES.md`, `skill-parity.diff`

The auxiliary **code-simplification** skill is additional bundled guidance, not a seventh upstream Ponytail skill. It favors exact behavior preservation, readability over shortest line count, recently modified scope, incremental tests, and build/lint checks. Its provenance is separately listed under Addy in the package lock. That makes this bundle a composite instruction surface; its broader verification checklist must not be attributed to upstream Ponytail's executable enforcement. [L10:9-13,33-43,62-104,158-170,320-332] [L03:59-61] [L03]

**Packaging mismatch:** the installed help still discusses auto-activation, mode flags/configuration, status persistence, and Claude-style updates, while the required hooks/config reader are not present. The installed gain card refers to benchmarks and README, but the package's README contains no benchmark results and the benchmarks are not bundled. These are dangling upstream-context instructions, not functionality implemented by 2.0.0. [L02] [L08:42-65] [L08] [L11:12-15] [L11]; inventory

### 5. Benchmark/eval harness and strength of evidence

#### Implemented instruments

- **Single-shot harness:** promptfoo configurations define baseline, Caveman, and Ponytail arms on five tasks. Baseline has only a user task; Ponytail supplies the full current SKILL.md as a system prompt. The committed configuration specifies three Claude model IDs, temperature 1, and 8192 max tokens. This is prompt conditioning, not a test of the installed 2.0.0 bundle or its entry router. Reproduction uses moving `promptfoo@latest`; no exact benchmark dependency lock is in the pinned tree. [U20], [U38], [U39]
- **LOC grader:** deterministic nonblank/noncomment line count across fenced blocks, falling back to the entire response if unfenced. It always passes and records a metric. It is not a correctness gate and can count non-code fallback prose; line-count parsing is not language-aware. Current code differs from the older writeups' broad characterization of counting conversational answers. [U40] [U25:64-71](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/README.md#L64-L71)
- **Correctness grader:** executes Python/Node snippets for email/debounce/CSV. React countdown and FastAPI rate-limit checks are regex/structure checks only. In particular, the rate-limit checker computes `hasTimeTracking` but never gates on it. Unknown tasks pass as skipped. Therefore “100% correctness” is instrument-relative, not production/UI/security correctness. [U41:9-13,233-291]
- **Behavior gates:** calibration is recognized through phrase regexes; requested explanation requires at least 45 prose words plus structural cues; “one runnable check” only detects assert/test-like text, not execution. Unknown probes pass. Unit tests validate selected grader examples, not whether models reliably obey the rules. [U21], [U22]
- **Agentic harness:** launches headless Claude Code in copied/seeded workspaces; real plugin arms resolve a plugin-cache path or environment override; baseline and one-line arms differ in injected instructions. It disables user-setting sources, MCP servers, Bash, repository instructions and auto-memory via flags/environment; appends a no-run directive. It retains cell artifacts and extracts CLI usage/cost/latency data. This is genuine orchestration and scoring code, but the workspaces are not an OS sandbox. [U23:34-71,262-347]
- **Metrics and quality:** source/test LOC are separated; Python self-check sections can be counted as tests. Fixture metrics count **added diff lines**, not net deletion savings. Fixture “correct” is merely nonzero produced LOC and “safe” is hardcoded 1; open/vibe tasks can be permissive or compile-only. The safety and comprehension tasks instead execute known adversarial/behavioral checks. These axes must not be pooled as uniformly strong quality evidence. [U23:73-181,275-286] [U42:414-430,810-893]
- **Two LLM judges:** published 0–3 rubrics separately score over-engineering and completeness using `claude-sonnet-4-6` at temperature 0. Live selftests must order minimal vs overbuilt or complete vs stub references correctly before matrix scoring. The offline completeness test checks ranking logic only. The judge's own score is neither deterministic correctness nor security verification; completeness is a separate pass, not a mandatory condition in `run.py`. [U26], [U27]

#### Publisher results, not independently reproduced savings

| Historical result | What the source actually supports |
|---|---|
| Single-shot June 2026 headline | Publisher reports 80–94% less code and 3–6× speedup on its five-task Claude comparisons, but now explicitly warns about chatty baselines and non-session costs. [U25:36-71,96-107] |
| June 17 cost recheck | Publisher reports 42–75% lower Claude cost, not gain's 47–77%; GPT-5.4-mini +26.2% and GPT-5.5 +38.7% cost in that historical setup. Some repetitions were excluded; Gemini remained pending. These are historical model/config results, not today's pricing or universal Codex economics. [U30:7-37,48-93] |
| June 18 agentic result | Haiku 4.5, Claude Code 2.1.177, n=4: publisher reports aggregate **54% less added LOC**, 20% lower cost and 27% less time on 12 feature tasks. 60–94% is the subset with over-build opportunities, not the overall average. Safety: 20/20 for Ponytail **and baseline/Caveman**, versus 19/20 for the one-liner arm. [U29:49-69,77-151,153-198] |
| June 22 comprehension/reuse | Publisher reports trace-transfer root-cause gains on Sonnet/Opus, but not reliable Haiku improvement; reuse probes already passed both arms, so the added reuse rung's benefit was **unproven** in those probes. [U31:38-95](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-22-issue-245-217-comprehension.md#L38-L95) |
| Correctness caveats | Upstream documents old unfenced-code/debounce gate bugs and genuine email edge-case failures; the robustness report includes model-dependent regressions. Broad “no quality cost” conclusions exceed those specific instruments and samples. [U32:23-46,74-88] [U33:51-88](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-16-robustness-audit.md#L51-L88) |

#### Reproducibility and evidence gaps

1. **Raw outputs absent:** complete tree inventory plus `.gitignore` show no `output-10x.json`, raw model-output matrices, agentic run workspaces, or judge/completeness result JSON. An older writeup calls responses “committed,” but they are **not committed at this pin**. Cannot independently recompute published aggregates from this snapshot. [U28:9-12,25-26] [U32:41-46,97-99]
2. **Code pin is not experiment pin:** agentic Ponytail/Caveman arms use an env override or lexicographically sorted last cache directory—not necessarily the checked-out revision; template path is external and the documented short fixture revision is not verified in the copy operation. Current run metadata records models/CLI, not exact plugin-source and fixture hashes. The current aggregation reports medians, while the historical feature writeup reports means. [U23:44-61,288-306,349-374,469-474] [U42:26-30](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/tasks.py#L26-L30)[U29:79,155]
3. **Historical contamination was real:** publisher explicitly withdraws the earlier agentic comparison because Ponytail activation leaked into the baseline. The replacement harness contains isolation measures, but those measures should be tested against the actual host version before claiming an uncontaminated new experiment. [U29:40-47](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-18-agentic.md#L40-L47)[U23:309-337](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/run.py#L309-L337)
4. **Quality coverage is uneven:** no retrieved raw completeness pass proves the historical LOC wins fulfilled every feature; no browser/server validation was part of that feature experiment. Small safety sets establish specific guards, not general security, maintainability, accessibility, or whole-project parity. [U27] [U29:67-69,186-198]

### 6. Installation, compatibility, permissions, licensing, security

| Target | Source-backed finding | Caveat |
|---|---|---|
| Claude Code upstream | Manifest registers shared lifecycle hooks; README documents marketplace + plugin installation. Hook implementation uses built-in Node APIs, so Node must be available to the noninteractive hook process. [U07], [U13] [U18:124-140](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/README.md#L124-L140) | Commands were inspected, not executed. No minimum compatible Claude Code release is declared in the package. Command hooks run with user permissions; persona instructions are not a sandbox. Official Claude docs above. |
| Codex upstream | Dedicated manifest supplies skills and hooks. Runtime emits `hookSpecificOutput.additionalContext` and uses `PLUGIN_DATA`; these align with current official Codex docs. [U10:106-121](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-runtime.js#L106-L121)[U14] | Installation does not automatically trust hooks. Need the host's review/trust flow; no host install/activation test was performed here. Three events are registered despite README's “two.” |
| Installed Codex/ChatGPT bundle | Readable bundled skills, router, auxiliary guidance; no executable hook or MCP package. [L01], [L02], [L04] | Do not infer upstream lifecycle persistence, statusline, environment/config behavior, benchmark runtime, or MCP availability from the display name. |
| Windows | Current shared command reads plugin root **inside Node** rather than interpolating it into shell text; normalizes backslashes. Config handles Windows paths/BOMs; tracker bounds stuck stdin; `.ps1` statusline supplied. Windows-oriented tests passed locally. [U07] [U09:54-96](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-config.js#L54-L96)[U08:152-170](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-mode-tracker.js#L152-L170)[U34], [U43] | Local tests ran on Windows with Node **25.9.0**, Python **3.12.12**, not within every real host. Upstream CI is Ubuntu/Node 22/Python 3.12, not a Windows matrix. Full hooks.test.js invokes `/bin/sh`; debt's documented grep recipe needs an appropriate tool/shell or adaptation. [U44] [U45:73-95](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/tests/hooks.test.js#L73-L95)[U04:20] |
| MCP | Separate private `ponytail-mcp` package exposes one prompt and one read-only instruction tool over stdio; both return the shared text for lite/full/ultra. Prompt response is a user message; tool returns text + structuredContent. [U24], [U46] | Not an always-on adapter, not code-review/scan tools. `off` is not served: resolution falls back to configured active level/full. SDK/Zod dependencies use semver ranges; no lockfile in this tree. Unit tests do not perform a protocol handshake. Not present in the installed bundle or root npm `files` allowlist. [U12], [U46], [U47], [U48] |

**Side effects and risk boundaries:**
- Activation writes mode/nudge files and reads Claude settings to decide whether to offer statusline setup; it does **not itself edit settings.json**. The Windows setup suggestion includes `powershell -ExecutionPolicy Bypass`; that is a proposed statusline command, not an automatic policy/config change. Unsafe shell-path characters trigger a manual-setup suggestion. [U17:54-112](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-activate.js#L54-L112)[U09:45-52](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-config.js#L45-L52)
- Hooks fail best-effort rather than stopping work. There is no guarantee that model output preserves required behavior merely because activation or tests succeed. Stale/shared state and fail-open subagent matching are reliability/scope concerns, not permission isolation. [U08], [U10], [U19]
- Benchmark code executes produced code in subprocesses or imports it in the scorer process. Live agentic runs use `bypassPermissions`, and inherited environment/configuration may matter. Judge scripts load API keys and send source to Anthropic. These are research-harness behaviors, **not automatic telemetry from installing the skills**. None of those live paths was launched here. [U23:315-337](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/run.py#L315-L337)[U26:41-77](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/judge.py#L41-L77)[U41:46-53](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/correctness.js#L46-L53)[U42:34-45](https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/tasks.py#L34-L45)
- The publish workflow gates publishing on a reusable test job, pins GitHub Actions by full SHA, and grants OIDC only to the publish job. That is positive source-level supply-chain hygiene; it does not prove a registry artifact was attested, all dependencies are pinned, or CI passed for this SHA. No live CI run or registry attestation was verified. [U44], [U49]
- **Licensing fact, not legal advice:** upstream LICENSE is MIT with DietrichGebert's copyright and notice-retention condition. Installed root LICENSE is MIT for Engineering Suite contributors; the bundled Ponytail license is byte-identical to upstream (`fb1bc6909ac3ef82d5c22106e32ef682b0cff66788fa915fb9b53b15c9d2f3ab`). Retain applicable notices when redistributing substantial content. This is not a comprehensive legal or vulnerability audit. [U50], [L12], [L13]

## Supporting Examples: Fresh Offline Verification

All execution used a research-local scratch directory and a minimized environment with home/config/temp paths redirected there. No installed package or actual user configuration was mutated.

| Check | Fresh result | What it proves—and does not |
|---|---|---|
| Selected Node suite | **21 passed, 0 failed/skipped** | Behavior grader examples, Windows command-shape/injection/open-stdin regressions, MCP instruction selection and version-wiring test; not actual model behavior or MCP handshake. |
| LOC regressions | **6/6** | Comment/fence/CRLF cases in this grader. |
| Correctness regressions | **4/4** | Fenced/unfenced email, broken-email rejection, unfenced arrow debounce. |
| Agentic selected scorers | **20/20 references**, 10 tasks | Known good passes / known bad is caught for seven safety/correctness tasks plus trace-transfer and two reuse probes; not statistical model success rates. |
| Completeness gate offline | Passed | Synthetic complete-vs-stub ranking logic. The printed `XX` is an intentional negative control, not a failed run. |
| Rules and versions | Passed; **8 version files at 4.10.3** | Consistency, not runtime host support. |
| State probe | Passed six transitions | Startup full → ultra → review leaves ultra → compact resets full → stop clears → resume restores full. Direct scripts only, not host lifecycle delivery. |
| Archive integrity | **169/169 Git blobs match**, rechecked after tests | Inspected upstream bytes remained unchanged. |

Reproducer: `verify_evidence.py`. Machine-readable commands, versions and exits: `verification-summary.json`. Full logs: `verification/`.

**Not run:** full npm suite, live promptfoo/agentic/LLM-judge benchmarks, dependency installs, template cloning, MCP server, or host plugin installation. Full `run.py --selftest` was intentionally not invoked because it also exercises an HTTP service and process-tree termination; only the reviewed pure Python scorers were used.

## OSS Reference Implementations

No additional implementations were introduced. The selected upstream repository itself supplies the implementation evidence. Historical benchmark mentions of other repositories/researchers are treated as publisher-reported context, not independently audited corroboration.

## Supplemental Evidence

None needed beyond primary host/protocol documentation, the two pinned Ponytail snapshots, installed packaging, and fresh offline execution.

## Caveats / Ambiguity Flags

- Strong confidence in **file/content parity, declared wiring, scoped offline test results**; no claim of active bundle loading, full host integration, or current model-performance parity.
- The six installed bodies preserve locked 4.9.0 prose, but runtime capabilities were not bundled and four bodies lag the requested 4.10.3 pin.
- Compact/resume reset, same-repository mode sharing, stale gain costs, incomplete raw benchmark provenance, and permissive quality metrics are substantive—not cosmetic—caveats.
- Instructions saying “never,” “enforced,” “always active,” or “does not apply fixes” remain model guidance unless an actual host mechanism enforces that property.
- No evidence from this work establishes current-project token savings, universal quality preservation, or equivalence to any TokenMaster behavior.

## Reusable Takeaway

**Treat Ponytail as a tested instruction-distribution system with a meaningful anti-overengineering discipline and imperfect historical evaluation evidence. Treat installed Engineering Suite Ponytail 2.0.0 as a composite, older, skills-only package—not the current upstream plugin runtime. Reuse the guidance and provenance facts separately from any claim of deterministic enforcement, persistence, or measured local savings.**

## Citation Registry

All `U` references below use the requested **full SHA**. Line ranges in prose narrow the linked range where helpful.

[U01]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md#L26-L120
[U02]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-review/SKILL.md#L13-L61
[U03]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-audit/SKILL.md#L12-L45
[U04]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-debt/SKILL.md#L15-L44
[U05]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-gain/SKILL.md#L13-L50
[U06]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail-help/SKILL.md#L35-L67
[U07]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/claude-codex-hooks.json#L1-L41
[U08]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-mode-tracker.js#L41-L170
[U09]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-config.js#L16-L150
[U10]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-runtime.js#L19-L159
[U11]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-instructions.js#L11-L91
[U12]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/package.json#L1-L48
[U13]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.claude-plugin/plugin.json#L1-L10
[U14]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.codex-plugin/plugin.json#L1-L31
[U15]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/AGENTS.md#L1-L32
[U16]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/pi-extension/index.js#L24-L228
[U17]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-activate.js#L29-L118
[U18]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/README.md#L124-L151
[U19]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-subagent.js#L8-L94
[U20]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/promptfooconfig.yaml#L1-L41
[U21]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/behavior.js#L17-L54
[U22]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/tests/behavior.test.js#L1-L80
[U23]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/run.py#L31-L479
[U24]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/ponytail-mcp/index.js#L1-L52
[U25]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/README.md#L3-L108
[U26]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/judge.py#L24-L185
[U27]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/complete.py#L25-L154
[U28]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.gitignore#L1-L26
[U29]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-18-agentic.md#L40-L219
[U30]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-17-cost-verification.md#L1-L93
[U31]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-22-issue-245-217-comprehension.md#L18-L98
[U32]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-16-correctness-gate-fix.md#L23-L107
[U33]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/results/2026-06-16-robustness-audit.md#L51-L115
[U34]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/tests/hooks-windows.test.js#L30-L193
[U35]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/tests/commands.test.js#L41-L93
[U36]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/scripts/check-rule-copies.js#L1-L76
[U37]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.opencode/plugins/ponytail.mjs#L29-L182
[U38]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/arms/baseline.js#L1-L2
[U39]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/arms/ponytail.js#L1-L8
[U40]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/loc.js#L1-L15
[U41]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/correctness.js#L9-L292
[U42]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/benchmarks/agentic/tasks.py#L23-L968
[U43]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/hooks/ponytail-statusline.ps1#L1-L24
[U44]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.github/workflows/test.yml#L1-L39
[U45]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/tests/hooks.test.js#L73-L95
[U46]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/ponytail-mcp/package.json#L1-L12
[U47]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/ponytail-mcp/instructions.js#L1-L26
[U48]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/ponytail-mcp/test/server.test.js#L1-L15
[U49]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.github/workflows/publish.yml#L1-L30
[U50]: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/LICENSE#L1-L21
[P01]: https://github.com/DietrichGebert/ponytail/commit/c982cd411abb53323c4baa1baa3c2f020b8d0b08
[P02]: https://github.com/DietrichGebert/ponytail/commit/356918eba965ee1eac64bd3a7f0dd02108350de5
[P03]: https://github.com/DietrichGebert/ponytail/blob/356918eba965ee1eac64bd3a7f0dd02108350de5/package.json#L1-L4

### Installed local citations

All local refs resolve below the exact `SNAP` root defined above. Relevant full files are also frozen under `installed-evidence/` with the same relative paths and line numbering.

- **L01** — `SNAP\.codex-plugin\plugin.json:1-34`
- **L02** — `SNAP\README.md:1-21`
- **L03** — `SNAP\UPSTREAM_LOCK.json:46-61` (only Ponytail and the relevant auxiliary-skill repository/commit metadata are copied as a clearly labeled extract)
- **L04** — `SNAP\skills\entry-ponytail\SKILL.md:1-24`
- **L05** — `SNAP\skills\ponytail-review\SKILL.md:1-51`
- **L06** — `SNAP\skills\ponytail-audit\SKILL.md:1-36`
- **L07** — `SNAP\skills\ponytail-debt\SKILL.md:1-40`
- **L08** — `SNAP\skills\ponytail-help\SKILL.md:1-69`
- **L09** — `SNAP\THIRD_PARTY_NOTICES.md:1-10`; frontmatter differences also in `skill-parity.diff`
- **L10** — `SNAP\skills\code-simplification\SKILL.md:1-332`
- **L11** — `SNAP\skills\ponytail-gain\SKILL.md:1-46`
- **L12** — `SNAP\LICENSE:1-21`
- **L13** — `SNAP\third_party_licenses\ponytail-LICENSE:1-21`
- **L14** — `SNAP\skills\ponytail\SKILL.md:1-109`

[L01]: installed-evidence/.codex-plugin/plugin.json
[L02]: installed-evidence/README.md
[L03]: installed-evidence/ponytail-provenance-extract.json
[L04]: installed-evidence/skills/entry-ponytail/SKILL.md
[L05]: installed-evidence/skills/ponytail-review/SKILL.md
[L06]: installed-evidence/skills/ponytail-audit/SKILL.md
[L07]: installed-evidence/skills/ponytail-debt/SKILL.md
[L08]: installed-evidence/skills/ponytail-help/SKILL.md
[L09]: installed-evidence/THIRD_PARTY_NOTICES.md
[L10]: installed-evidence/skills/code-simplification/SKILL.md
[L11]: installed-evidence/skills/ponytail-gain/SKILL.md
[L12]: installed-evidence/LICENSE
[L13]: installed-evidence/third_party_licenses/ponytail-LICENSE
[L14]: installed-evidence/skills/ponytail/SKILL.md
