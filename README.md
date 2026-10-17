# TokenMaster

> **Working snapshot — October 16, 2026 (America/Chicago).**
> Branch: `codex/working-handoff-2026-10-16`. Start with the
> [handoff and next steps](token-master-plugin/docs/HANDOFF-2026-10-16.md).
> The latest real-model comparison completed **2/2 tasks with optimization off
> versus 1/2 with the candidate**; it did not establish useful token savings.
> The newer structural-preprotection experiment is opt-in and has not completed
> native or real-model qualification. This branch is not a release.

<p align="center">
  <img src="assets/tokenmaster-hero.svg?v=2" alt="A bounded graph query instead of repeated source-search paths" width="100%">
</p>

**Complete the same independently verified task with fewer observable reference tokens.**

TokenMaster combines graph navigation, conservative recoverable views, explicit
request planning, and a validator-gated policy search. The core is harness-neutral:
it consumes declared requests and traces rather than a provider's billing API.
There are **no monetary calculations and no foundation-model weight updates**.

**Historical component result — October 8, 2026:** the opt-in conservative V3 policy
matches baseline on all six reading questions: **6/6 correct, 23 requests,
116,883 gateway-reported tokens in each arm**. Four deliberately repeated-read
checks pass in both arms with **9.9% fewer task tokens** under V3 and no extra
requests. That is conditional mechanism evidence, **not a general savings
rate or production qualification**. See the
[repair and measured results](token-master-plugin/docs/CONSERVATIVE_POLICY_FIX.md)
and the preserved [earlier scorecard](token-master-plugin/docs/CONTROLLED_SCORECARD.md).

## What is implemented

- **Exact visible reuse (V3):** keep unique source content; shorten only identical
  older reads whose full original is still visible. Verify exact reconstruction
  and final token/byte guards. The opt-in conservative configuration adds no
  task-mode prompt and performs no external recovery or extra model call.
- **Safer views:** exact code/prose by default; explicit `navigation` for Python/Rust
  skeletons and `overview` for suitable JSON or successful logs. Exact/edit/debug,
  exhaustive, aggregate and security intents bypass. Failed recovery storage never
  justifies dropping content.
- **Complete recovery:** workspace-scoped originals, full-content and page digests,
  bounded exact search, Unicode paging, explicit errors, session leases and observable
  retention. A recovery reference is not a task-quality guarantee.
- **Honest measurement:** a pinned reference vocabulary, final-envelope token/byte
  guards, and separate input/output/peak/call totals. No savings footers in tool results.
  Estimates and native counters cannot enter an exact reference-token certificate.
- **Whole-task evaluation:** retries, auxiliaries, failures, recovery and verification
  all count at the declared boundary. Learning and deployment remain separate;
  all-in metrics require complete, sealed inventories.
- **Bounded improvement:** durable policy candidates, fresh paired confirmation,
  cumulative statistical error spending, atomic champion promotion and rollback.
  Jev screens proposals only; an independent outcome oracle controls promotion.
- **Scoped discipline:** preserve required depth, avoid unrelated work, and stop after
  sufficient verification. Task-local and session modes are distinct and reversible.
- **Graph integrity:** index/source provenance, stale-source detection and paging.
  Inferred graph edges remain candidates to verify against source.

The mathematical definitions, derivation and limitations are in
[Token efficiency](token-master-plugin/docs/TOKEN_EFFICIENCY.md). The tracked
[implementation/verification matrix](token-master-plugin/docs/IMPLEMENTATION_PLAN.md)
separates implemented features from release qualification. Current receipts and
limitations are summarized in [Verification](token-master-plugin/docs/VERIFICATION.md).

## Measure the entire trajectory

For all model calls in one task, under a pinned tokenizer and serialization:

```text
reference tokens = sum(full input tokens + full output tokens)
quality-normalized metric = all runtime tokens / verified successful tasks
```

Replayed history counts again. Raw tool output is not added a second time outside
those calls. Cache reuse does not subtract supplied tokens. Hidden reasoning,
non-text processing, unobserved auxiliary calls and opaque provider state are not
zero: partial traces cannot masquerade as complete measurements.

A smaller tool result does not prove lower whole-task usage. It may trigger extra
retrieval, retries or a wrong answer. Token counts also do not prove lower latency
or compute. Zero verified successes yield an undefined ratio, not free execution.

## Safe defaults and host support

| Surface | Implemented boundary | Not implied |
| --- | --- | --- |
| Claude Code | Native MCP configuration and an explicit PostToolUse schema adapter | Every tool/version accepts replacement; see transport evidence |
| Codex CLI / desktop configuration | Documented local MCP configuration | Transparent output interception or desktop runtime qualification |
| GitHub Copilot CLI | Model-invoked MCP by default; explicit conservative JSON `view` hook via `--copilot-output-hook` | General hook/schema coverage or native full-profile Ponytail/Headroom/Jev execution |
| Direct Python API / CLI | Explicit request planning, measurement and evaluation | Automatic interception of an opaque harness |

An explicit [`native-copilot` route](token-master-plugin/docs/NATIVE_FULL_RUNTIME.md)
now connects the selected full runtime to the actual native CLI, scoped recovery
and the same ledger. Installed protocol checks pass; real-model efficiency,
native learning and broader write/debug qualification remain open.

Installers preserve unrelated configuration, reject malformed JSON/TOML, use
owned-setting receipts, backups and atomic writes, and support scoped uninstall.
They do not prove that a native host accepted a result. Unsupported schemas,
mixed media, error results and unavailable exact tokenization pass through.

A separate native acceptance matrix now verifies the named Read/Grep/Bash,
PowerShell-via-Bash, MCP text-array and bypass cases in Claude Code 2.1.289.
It also exercises actual temporary user-settings install/uninstall, without
an ambient tokenizer masking configuration mistakes. This is local
**mock-provider transport evidence**, not a model-quality result or a claim
about every host version. See [Native envelopes](token-master-plugin/docs/NATIVE_ENVELOPES.md).

An additional **Copilot CLI 1.0.95-0** before/install/uninstall run now verifies
the explicitly enabled conservative JSON `view` hook against a synthetic
provider. It is not the native full-profile runtime or a savings benchmark.
See [Native Copilot hook](token-master-plugin/docs/NATIVE_COPILOT_HOOK.md).

The reference runtime is validated on **Windows, CPython 3.12**. Other operating
systems, Python versions and host versions require separate qualification.

## Run locally

Provision the existing runtime dependencies once; server launches never invoke
an unpinned package resolver:

```powershell
python -m venv .token-master-runtime
.\.token-master-runtime\Scripts\python.exe -m pip install -r token-master-plugin/requirements-runtime.txt
```

Use that environment's Python for the following scripts. A reference tokenizer
must already be cached or supplied as a verified local file. Vocabulary acquisition
is a separate opt-in operation; runtime compression does not download it.

### Compression and recovery

The skill directory is `token-master-plugin/skills/token-master`.

```powershell
# Inspect the local tools and explicit task/session modes:
python token-master-plugin/skills/token-master/brainspace_tools.py --help

# Benchmark exact recovery on files; an overview is an explicit request:
python token-master-plugin/skills/token-master/brainspace_benchmark.py data.json --intent overview --json
```

The benchmark distinguishes `unchanged`, `root_exact`, `fragments_exact`,
`unverified` and `failed`. It actually retrieves minted references and compares
content. Changed output with no recovery evidence is not certified; a legitimate
JSON-whitespace compaction can therefore be `unverified` for *exact-text recovery*.
Failed or unverified required recovery returns a nonzero exit. The benchmark
**does not** certify task quality or whole-task savings.

MCP recovery is paged:

```text
brainspace_retrieve(ref, offset=0, limit=32768)
# Continue at next_offset until complete=true. Check full and page SHA-256.
brainspace_search(ref, query, offset=0, limit=20)
```

Private references are workspace-scoped. An explicit session ID adds session
isolation; otherwise the workspace has a persistent default lease. Sharing is
explicit. A server's scope is fixed at launch: use distinct processes or explicit
launch scopes for different workspaces/sessions. Stash/read pins originals; release only when references are no longer
needed. Retention quotas count compressed payload bytes, not total SQLite size.

### Demonstrate the improvement gate

```powershell
python token-master-plugin/skills/token-master/token_efficiency.py --db .token-master/demo.sqlite demo --synthetic --samples 256
python token-master-plugin/skills/token-master/token_efficiency.py --db .token-master/demo.sqlite status
```

This executes the real planner, counter, independent toy oracle, durable registry
and promotion logic. **It is a constructed offline fixture, not a real language
model performance result.** The Python `Optimizer` API accepts an independently
implemented evaluator for a real, declared workload.

Only a registry-saved certificate for the current incumbent may promote a
candidate. Strict equal-quality evidence may remain inconclusive; the controller
never quietly relaxes the correctness gate. No global optimum or indefinite
improvement is promised.

### Optional Jev screening

`brainspace.jev.JevClient` pins `jev-1.13.0`, reads `TYPESAFE_API_KEY` from the
calling process, and requires both explicit network enablement and a
synthetic/sanitized data classification. It denies redirects, bounds requests
and responses, makes no automatic retries, and avoids credential-bearing logs.

The user controls which state leaves the machine. A sanitized label is an
attestation, not an automatic sanitizer or a retention guarantee. Missing keys,
network errors and invalid responses retain the deterministic fallback; Jev
confidence never becomes correctness evidence or authorization. Credentials are
not persisted by this package. See [Jev contract](token-master-plugin/docs/JEV_CONTRACT.md).

### Check whole-task savings offline

```powershell
python token-master-plugin/evals/verify_savings.py --study <complete-study-directory> --use-recorded-reviews
```

No API key or network call is needed. The checker recounts raw calls, checks
source/model/task/control identities and saved outcome evidence, and rejects
incomplete or inconsistent traces. Exit 0 means audit consistency, **not a
savings certificate**. Unknown outcomes and reduced quality block efficiency
wins. Reference counts, explicit-context counts and bridge-reported usage stay
in separate units; cached/reasoning tokens are not subtracted/added twice.

The eight-pair exploratory pilot observed **10.77% fewer bridge-reported tokens**
and **3.49% fewer full-body reference tokens**, with 8/8 outcomes passing in each
arm. One constructed navigation case dominated the reduction; six other cases
used more reported tokens. Calls and wall time increased. There is **no statistical
certificate, representative-workload claim, or policy promotion**.
See [Objective savings](token-master-plugin/docs/OBJECTIVE_SAVINGS.md) for the
raw-count boundaries, reproducible local command, per-task interpretation and
learning overhead.

### Install only into the host you choose

Installation is an explicit configuration change. For isolated validation, set
`CODEX_HOME`, `CLAUDE_CONFIG_DIR` or `COPILOT_HOME` to a temporary directory first.

```powershell
python token-master-plugin/skills/token-master/brainspace_setup.py --host codex --python <runtime-python> --tokenizer-file <verified-local-vocabulary>
python token-master-plugin/skills/token-master/brainspace_setup.py --host codex --uninstall
```

Use `--host claude` or `--host copilot` for those adapters. Uninstall removes
owned configuration and retains package files and recovery data. For graph
routing, `setup.py <repo-root> --host <host> --python <runtime-python>` requires an
already installed graph supplier. Optional supplier installation is separate and
explicit. Graph freshness covers indexed files, not newly added unindexed files.

## Verification and claim boundaries

```powershell
python -m pytest token-master-plugin/skills/token-master -q
```

Install the pinned development requirements first when running tests. The suite
covers corruption, failed storage, full public recovery, envelope schemas, exact
counts, protected requests, configuration ownership, graph freshness, statistical
constants, replay/restart protection, candidate validation and stale promotion.

Transport fixtures exercise actual native executables against a **synthetic mock
provider**, with isolated homes and no copied authentication. That checks transport,
not model reasoning quality. A separate real-model study exercises synthetic
workspaces and actual generated-code tests in a bounded WSL sandbox. Its eight
task pairs are exploratory, not independent population confirmation. The live
Jev smoke uses synthetic state only. None is a production workload benchmark or
a broad Ponytail/Headroom parity certificate.

Earlier headline percentages and blanket "lossless/verified host" statements in
Git history predate the repaired oracle and current conservative defaults. They
are **not current release evidence**. New efficiency claims require a complete
whole-task trace and independent outcome validation for the named workload.

## License

[MIT](LICENSE)
