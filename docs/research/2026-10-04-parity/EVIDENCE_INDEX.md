# Evidence index

**October 4, 2026 — research-local outputs only**

Base directory:

`C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\`

## Read in this order

1. `PARITY_REPORT.md` — decision, canonical versions, capability matrix, new upstream behavior, concrete local findings, compatibility/security and qualification limits.
2. `GAP_BACKLOG.md` — 12 prioritized implementation slices; exact existing local paths/lines, proposed new paths and acceptance tests.
3. `BENCHMARK_PROTOCOL.md` — product comparisons, ablations, task strata, host/provider trace fields, cache-aware cost, latency, quality/statistical gates and release sequence.
4. `ponytail/REPORT.md` and `headroom/REPORT.md` — deeper source/test evidence and caveats.

## Provenance and integrity

| Artifact | Purpose |
|---|---|
| `repository-identities.json` | Raw selected GitHub API metadata: requested/resolved identities, canonical names, default branches, dates, source-license declarations and the old Headroom redirect |
| `tokenmaster/source-manifest.json` | Full TokenMaster SHA, configured remote, status, per-file SHA-256/length/line count and working-tree newline-normalized comparison |
| `tokenmaster/source/` | 31 byte-exact tracked-file snapshots from `426fc853389ddba4bc6e1dd35a28179a895c064f` |
| `ponytail/upstream-commit.json`, `upstream-tree.json`, `upstream-hashes.json` | Commit/tree evidence and 169/169 Git-blob verification for current upstream |
| `ponytail/installed-manifest.json`, `HASHES.md`, `skill-parity.json`, `skill-parity.diff` | 29 installed-file hashes, older 4.9.0 provenance, six-body/whole-file comparisons against both pins |
| `ponytail/installed-evidence/` | Only the relevant named bundle content; lock information is a labeled relevant extract, not unrelated plugin/user data |
| `ponytail/source/` | Current 4.10.3 and locked 4.9.0 source archives extracted under their full SHA names |
| `headroom/manifest.json`, `commit.json`, `source.zip`, `source/` | Source archive hash, pinned commit, source inventory and citation/check counts |
| `headroom/history-50.json`, per-file `*.history.json`, `history-evidence.md` | Bounded recent history from the inspected pin and older material transform changes |
| `headroom/citation-validation.json`, `cited-excerpts.txt` | The deep dossier's pinned line-range checks and source excerpts |
| `headroom/kompress-model-card.md`, `kompress-model-metadata.json` | Separately pinned publisher model metadata; code pin does not imply weight pin |
| `official/manifest.json`, `official/*.md` | Current official Claude/Codex/cache documentation, resolved redirects, retrieval times and SHA-256 hashes |
| `evidence-validation.json` | Final cross-report reference/line-bound checks and tracked-source preservation audit |

Sources are retained as evidence, not installed packages. Third-party license files remain in their source snapshots.

## Fresh execution evidence

### TokenMaster

- `probe_boundaries.py` — reproducible stdlib-only checks against the source snapshot.
- `boundary-probe-results.json` — **11 confirmed, narrowly scoped assertions**, including positive controls.
- `pytest-run.json` — exact command/environment/module availability.
- `pytest-output.txt`, `pytest-results.xml` — **120 collected; 110 passed; 10 failed; zero skipped/errors**. Missing tree-sitter dependencies explain the AST no-op failures. Some passing tests also succeed on no-op, so this is not dependency-enabled AST validation.
- `INDEPENDENT_REVIEW.md` — separate verifier's source/evidence audit, correcting potential overclaims about host acceptance, billed tokens and parser coverage.
- `probe-ccr.sqlite`, `hook-probe-ccr.sqlite` — research fixture stores only.
- `publisher-verification-snapshot.py`, `publisher-verification-provenance.json` — snapshot/hash of the pre-existing untracked dual-host harness, inspected but not executed in this research. Its hook portion is subprocess verification, not a live Claude schema-acceptance test.

All paths above are under `tokenmaster/`. MCP wrapper tests use a decorator-only shim, not a transport. Hook probes are subprocesses, not a running host. Token-count examples explicitly use the fallback estimator. No model behavior or bill was measured.

### Ponytail

- `verify_evidence.py`, `verification-summary.json`, `verification/`.
- **21 selected Node tests; 6 LOC regressions; 4 correctness regressions; 20 good/bad scorer-reference cases** passed.
- Rule/version consistency, an offline completeness-gate test and an isolated six-transition mode-state probe passed.
- 169 upstream Git blobs were verified; 29 installed-file hashes remained unchanged.
- Not run: live model/agentic/judge comparisons, full npm suite, MCP handshake, plugin installation or host lifecycle delivery.

### Headroom

- `pure_checks.py`, `pure-checks.json`.
- **23/23 isolated pure checks passed**: bounded folding, relevance segmentation, privacy-switch/header-policy and accounting examples.
- Not run: native Rust build/runtime, Kompress model, full pytest suite, proxy/server, live client/provider/cache or invoice comparison.
- Most cited upstream tests were inspected, not executed. Their existence does not prove a green CI run.

## Boundary of the work

No production implementation, dependency installation, service launch, model/API benchmark, persistent runtime-configuration change, commit or push was performed. Temporary process environments and fixture stores were confined to research-local verification. Reports/evidence were written only under the base directory above.

The repository's existing whitelist `.gitignore` ignores this directory. These are durable local files, not committed or externally published artifacts.

## Reproduction without changing production

The TokenMaster probe script is dependency-free:

```powershell
python -B "C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-parity\tokenmaster\probe_boundaries.py"
```

It writes only its research-local JSON/fixture stores. The saved pytest command is in `tokenmaster/pytest-run.json`; rerunning without optional grammars should not be represented as full AST coverage.

For upstream selected tests, use the saved verification scripts/commands only after reading their boundaries. Do not convert a research artifact into permission to install software, execute generated code without review, call paid APIs, or mutate real host configuration.
