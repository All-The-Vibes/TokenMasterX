# Pinned parity runtime qualification

Status on **October 8, 2026 UTC**: the Ponytail instruction component executed
successfully. Headroom's exact-commit image, source-pinned Kompress model and
public request pipeline now run offline, and a bounded 24-run primary-model
comparison has completed. **General/representative parity, other unexercised
routes and the isolated Linux Codex runtime cell remain unqualified.**
`COMPARATOR_RESULTS.md` records the actual scores, failures and limitations.

## What ran

### Ponytail: actual pinned instruction builder

- Source: `DietrichGebert/ponytail`
  `c982cd411abb53323c4baa1baa3c2f020b8d0b08`, package metadata 4.10.3.
- Recomputed the recursive Git tree objects and checked the root against the
  commit's `602912d96e9cf113408a9725ed03f42a07e7d25b` tree. The exact package,
  builder, configuration, skill and license blobs matched.
- Executed the unmodified `getPonytailInstructions("full")` export with
  Node v22.23.2, using the existing public image
  `sha256:c72861c6705868ed7f08e1cf22ef4f7ba07a82c19a54ba65d931c442d3575889`.
- Actual container inspection verified non-root execution, network none,
  read-only root and input mounts, all capabilities dropped, no-new-privileges,
  64 PIDs, 256 MiB memory and one CPU. Runtime environment was explicitly empty
  except for the task's allowlisted variables. No real home or credential
  configuration was mounted.
- The builder used the skill body, **not its error fallback**. It emitted
  5,229 characters / **1,274 `cl100k_base` reference tokens**, with SHA-256
  `da4fb09cff2f6726691ce6591cebc38c95597d79da132e49c6fa2665c4e8a3ff`.
  This measures the raw instruction string only: full model requests must be
  counted separately, and these tokens are not a savings metric.
- The exact task container was removed after checking its label/ID and terminal
  status; the public image was preserved.

This proves the pinned instruction component can be executed under the stated
boundary. It does **not** prove model obedience, native Ponytail hook acceptance,
task quality, or a head-to-head token advantage.

### Headroom: official exact-commit image, actual native import

The official `code-1cf4966` OCI candidate resolved to this immutable
`linux/amd64` manifest:

```text
ghcr.io/headroomlabs-ai/headroom@sha256:ec34aee0a3d0186dd5c0c0c663a6db5cdf351f37666a3bdf22217a7bc3964014
```

- The raw platform manifest hash was recomputed. The downloaded image ID
  matched its config digest
  `sha256:eb04988b9360cb5b4d0348a519a5a66232e04593de8f3bbee6571a6a397343c6`.
- The full revision label and retrieved SLSA build definition/materials name
  `1cf496612e781ef8d67ff87ee4f78037492f0bc7`, with the pinned Dockerfile and
  `proxy,code,bedrock` extras. **The publisher signature was not independently
  verified**, and the native build was not independently reproduced. The
  additional Bedrock adapter was installed by upstream, not exercised here.
- All **557 installed Python source files** matched the previously attested
  exact-commit archive; none were missing or different.
- Actual imports of `headroom._core.DiffCompressor` and `SmartCrusher`
  succeeded. The native extension SHA-256 is
  `74dc7526970e20aa3c5acff67c91137ce0cf57fba7c242bb6d20fd60909a6a97`.
  No replacement compressor, changed release-tag wheel or disabled ML path was
  substituted.
- Observed runtime: Headroom 0.39.1, Python 3.13.16, tiktoken 0.14.0,
  ONNX Runtime 1.30.0, Transformers 5.18.0, tokenizers 0.23.2, tree-sitter
  0.26.0, language pack 0.13.0 and MCP 1.30.0. The full installed distribution
  inventory is saved; do not equate it with TokenMaster's different runtime lock.
- Execution used UID/GID 65532, network none, read-only root, zero capabilities,
  no-new-privileges, two CPUs, 2 GiB memory/swap total and 256 PIDs. Only public
  read-only inputs and the exact output directory were mounted.

Two preflight attempts refused to start because the upstream image declares a
persistent `VOLUME` at `/home/nonroot/.headroom`. The successful attempt explicitly
covered it with bounded private tmpfs rather than accepting an unexpected
persistent mount. The successful container exited 0 and was removed by verified
ID. The directly identified second-preflight anonymous volume was removed after
checking that no container referenced it. The first preflight's mount identity
was not retained, so no guessed volume deletion or global pruning was attempted.
The immutable public image remains cached.

That initial inspection established **source correspondence and native import**,
not compression or proxy health. The following model/pipeline continuation is
separate evidence. The default proxy server entrypoint was not started.

### Headroom: pinned model and actual public request pipeline

Before downloading, the loader source was checked. It pins Kompress to
`b1563631b35bfdcee37587ad530147497d820d4c` in `headroom/onnx_runtime.py`,
not the initially inspected Hub `main` revision `e00cc5e6...`. The earlier
metadata was never used to load that newer revision. The ONNX bytes happen to
have the same published digest at both revisions, but source fidelity still
requires retaining the actual upstream pin.

- Repository: `chopratejas/kompress-v2-base`
- Actual upstream revision: `b1563631b35bfdcee37587ad530147497d820d4c`
- Default first ONNX candidate: `onnx/kompress-int8-wo.onnx`
- Downloaded and verified SHA-256:
  `c47ddd764dec5cf91fd1f10cf69e5538dd2a49d913828da7f6a993931cc7904f`
- Verified size: 274,049,435 bytes.
- Actual tokenizer source: **`answerdotai/ModernBERT-base`**, not the tokenizer
  files in the Kompress repository. The upstream loader names a floating
  default ref; this study freezes it to
  `8949b909ec900327062f0ebf497f51aef5e6f0c8` in the private cache.

Five model/tokenizer files were downloaded anonymously and checked against
published LFS SHA-256 or Git-blob identities. The verified `cl100k_base`
vocabulary was copied from the existing local public-asset cache. Inference
then ran with **network none and a read-only model cache**. No personal Hugging
Face credential, normal home, provider credential or Jev key was mounted.

The unchanged default Kompress settings were used: automatic device selection,
CCR enabled, 350-word chunks, 0.5 score threshold and 64-word minimum. No forced
retention ratio or disabled canary was used. The selected backend was ONNX;
the execution smoke, canary and two authored text fixtures completed with no
degraded reason or inference failures. Both fixtures changed and both complete
originals were retrieved exactly. Those four observed Python ONNX calls are
activation evidence, **not primary-language-model task outcomes**.

The subsequent test called **`headroom.compress(...)`**, exercising its real
default `TransformPipeline`, not substituting the standalone compressor.
Two older `fetch_notes` results changed; the short instructions, newest four
messages and tool-call metadata remained unchanged. Two pipeline-phase ONNX
forwards completed, and both returned references recovered their entire original
fixtures. Complete message-array JSON measured **1069 → 973 `cl100k_base`
reference tokens**. This is a single constructed activation fixture, **not an
end-to-end savings result, representative workload or comparison with TokenMaster**.

Important observed boundaries:

- A separate `read_file` control remained unchanged because the default router
  intentionally protects recent Read results. This was an ineligible positive
  fixture, not a missing-model failure; its original failed readiness assertion
  and later negative-control audit are retained.
- The actual diagnostic route is `router:text`, not `router:kompress`.
  An intermediate verifier asserted the wrong label. The successful verifier
  additionally observes actual completed ONNX forwards instead of inferring
  the engine solely from a diagnostic name. That failed receipt is retained.
- For `gpt-6-astra`, the pinned upstream registry selects
  **`EstimatingTokenCounter`**. Its reported counts are not serving tokens or
  the independent reference measurement. This must remain explicit in a future
  benchmark; no alias or tokenizer override was silently registered.
- AST CodeAware compression is **disabled by upstream default**, even in the
  code-dependency image. Optional `fastembed` is absent; semantic relevance on
  applicable search/log routes was not qualified. Native-detector inference is
  not covered by the Python ONNX counter. Do not imply all optional paths ran.
- Library mode does not automatically expose recovery tools to the primary
  model. A fair agent comparison still needs the actual CCR tool-loop wiring.

Independent review rehashed the assets and checked the raw messages and complete
recovery hashes. It found a future verifier weakness: a substring could pass the
old recovery predicate. The actual saved recoveries were already whole originals.
The verifier now requires whole-source equality and coverage of **every changed
source**, with eight passing offline regressions. The tightened offline audit
rechecks the saved runtime evidence; it does not claim a fresh retrieval or
inference rerun. Other Headroom routes may legitimately use block references,
so this whole-message gate is specific to these fixtures.

The OCI route avoids the failed PyPI transport without disabling certificate
verification or using an unofficial mirror. It makes **zero primary-provider
or Jev calls** and changes no normal host profile. Evidence is in
`evidence/runtime-route-check-20261008/`, especially
`runtime-output-003/runtime-inspection.json`, its actual container configuration,
the source/build provenance and cleanup receipts. Model/pipeline evidence is in
`evidence/headroom-model-readiness-20261008/`: `asset-plan.json`, `download-001`,
`offline-001`, `pipeline-001` through `pipeline-003`, the retained verifier
versions and `strict-recovery-offline-audit.json`. All five new task containers
were removed after verified terminal state; the public image and model cache
are deliberately retained.

## Still unqualified and retained failed routes

### Live shared-harness comparison, not native-host parity

`evals/competitors/headroom_worker.py` now calls the public pipeline and the
actual upstream `CCRResponseHandler` while the shared parent owns every
primary model request. The worker is snapshotted and hash-bound before launch.
Each task receives a fresh network-none, read-only process; no writable host
mount is exposed. Audit retrieval happens only after the primary task ends,
avoiding feedback contamination during measurement.

The six-case/four-arm study used common original histories, tool schemas and
model limits. All 24 attempts and 97 primary calls including readiness are
retained. Source, outcome, history, RPC and cleanup checks passed an independent
audit. TokenMaster and Ponytail both got 6/6; baseline and Headroom got 5/6 for
different reasons. TokenMaster used more tokens than Ponytail. See
`COMPARATOR_RESULTS.md`; these are not production-wide rankings.

### Headroom: earlier independent source build blocked by official wheel transport

The retained archive for
`headroomlabs-ai/headroom@1cf496612e781ef8d67ff87ee4f78037492f0bc7`
has SHA-256
`540cf3f5a5d167683daabf965d6da9125aeb2dfa10e3f6bb5a0c29b0142a31f6`.
All **2,542** extracted files matched those archive bytes.

The bounded build used the existing public Rust image
`sha256:1ebdfa4f7c7ccd1b4221f94a6b62f744f8e803fa354e7069fbfaf19b653c6f37`.
Only public source and task-owned scripts/output were mounted. The intended
build preserves the real release-mode Rust/PyO3 extension and `Cargo.lock`,
then installs the source-declared `proxy,code` dependencies. It does not swap
in a release-tag wheel with a different commit or disable local ML to obtain
an easier comparator.

In that earlier source-build attempt, the official `files.pythonhosted.org` download failed TLS negotiation while
installing the declared Maturin build dependency. The native extension build,
dependency installation, pinned ML-asset provisioning and compressor execution
**never started/completed as qualified stages**. The build container exited 1
and was removed by exact checked ID after preserving its logs.

Host Python, PowerShell's normal HTTPS client, and Windows curl/Schannel with
TLS 1.2 also failed official-file access. A hidden browser probe timed out and
could not recover an existing tab; it established no browser download result.
No certificate validation was disabled, insecure URL or unofficial mirror used,
or application dependency changed.

**Do not run a comparator labeled "Headroom" with missing Kompress/model assets,
substituted Python compression, or unreported disabled components.** Readiness
must be proven before the study can include that arm.

### Codex CLI: isolated Linux sidecar blocked before native start

`evals/hosts/docker_codex_cli.py` reuses the existing native smoke runner,
TokenMaster installer/MCP fixtures and loopback mock provider. Its new tests
exercise exact-container checks and response correlation. It accepts immutable
local images, uses no real credential configuration, and designs the runtime
as non-root, read-only, network-none, capability-free and resource-bounded.

The official standalone **Codex 0.147.0** Linux archive matched its GitHub
release digest:
`0246e2e773834e07f0fb5249ed6ebad12e4591e608f8c7bb97dd6a9690544c36`.
The repository's locked Python runtime wheels could not be downloaded from
their official host. **The actual native MCP run and in-container isolation
checks were not reached.** Unit tests and the verified executable archive
cannot replace that missing runtime evidence.

The initial offline sidecar validation passed 18 tests and 19 subtests,
including existing smoke regressions; Ruff and configured mypy passed. The
sidecar verified 7/7 exact-resource cleanup checks and preserved the existing
public images. Failed setup attempts remain in the evidence directory.

The subsequent combined plugin/host run passed **1,500 tests and 19 subtests**
with no failures/errors/skips and one existing dependency warning. Its
106-file Python source/test inventory was identical before and after the run.
This validates the code changes, not the unexecuted native transport cell.

The Docker engine is Linux. Even a later successful Linux CLI test does not
close the original **native Windows user-skill isolation or Codex Desktop**
requirements. Do not weaken those boundaries or alter the user's normal
profile to manufacture acceptance.

The October 8 documentation-only AppContainer/LPAC review did not establish
an acceptable replacement. The existing host-loopback mock-provider route
conflicts with the no-admin/no-exemption-change boundary, and complete
CLI/Desktop compatibility is unverified. See `WINDOWS_ISOLATION_FEASIBILITY.md`.
No OS/profile/ACL changes or native launches were attempted for that review.

## Unblocking and stop conditions

1. Reuse the verified immutable image and pinned cache. Model and eligible-text
   request-pipeline activation already ran; do not repeat dependency downloads
   merely to reconfirm them.
2. Preserve the now-executed public-pipeline/CCR wiring and its common measured
   boundary. Replicate on fresh representative tasks, keeping upstream defaults,
   estimates and unqualified optional routes explicit rather than silently
   changing settings to produce a better score.
3. The isolated Codex sidecar's next unused native attempt is `--attempt 3`;
   its exact locked wheel closure still needs verified official access or an
   independently verified offline bundle. Do not launch solely to repeat the
   same failure or silently substitute Headroom's MCP 1.30.0 environment.
4. Freeze fresh workload/oracle/arm identities after runtime readiness and
   before inference. Neither runtime setup nor exposed four-task examples
   count as representative held-out competitor qualification.
5. Retain both the negative context-only results and the scoped-profile pilot;
   retain the incumbent unless the declared promotion gate actually passes.
   No comparative performance certificate, global enablement or weight change
   has occurred.

## Local evidence

- `evidence/parity-runtime-20261008/`: setup plan, source attestations, executed
  Ponytail export/commands, instruction-token measurement, failed Headroom
  build logs, verified-TLS probes and exact cleanup receipt.
- `evidence/runtime-route-check-20261008/`: immutable official OCI resolution,
  exact-source/native import, dependency inventory, model metadata and bounded
  isolation/cleanup evidence.
- `evidence/headroom-model-readiness-20261008/`: source-pinned assets, actual
  offline model/public-pipeline execution, preserved negative/intermediate
  checks, exact recovery and independent review/regressions. Not a live
  primary-language-model comparison.
- `evidence/codex-linux-isolation-20261008/`: sidecar report, source snapshots,
  verified official executable, failed builds and cleanup/test receipts.
- `evidence/repository-diagnostic-20261007/`: the completed negative aggregate,
  preserved interrupted attempt and offline recount. These are separate
  experiments, not entries to combine into a fabricated parity result.
