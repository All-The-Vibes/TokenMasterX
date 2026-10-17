# Research basis and scope

The research completed on October 4, 2026 before this implementation branch.
This is a compact index to the source-pinned workspace dossiers, not a new
claim that moving upstream branches still have the same contents.

The shipped, token-only current implementation comparison is
`PARITY_ANALYSIS.md`. It incorporates an October 7, 2026 UTC official-source
refresh while retaining the original benchmark SHAs. The capability analysis,
native transport receipts and real-model savings qualification remain distinct.

## Compared implementations

| Project | Research pin | Use here |
| --- | --- | --- |
| TokenMaster baseline | `426fc853389ddba4bc6e1dd35a28179a895c064f` | Original implementation and regression baseline |
| Ponytail, `DietrichGebert/ponytail` | `c982cd411abb53323c4baa1baa3c2f020b8d0b08` | Scoped task discipline and mode lifecycle, not deterministic model obedience |
| Headroom, `headroomlabs-ai/headroom` | `1cf496612e781ef8d67ff87ee4f78037492f0bc7` | Recovery, request/role protection, transport and evidence boundaries |
| GEPA, `gepa-ai/gepa` | `fb1ed589fd83372caef499cffc2c73173d3b096b` | Frozen-weight policy search; external promotion gate over every candidate path |
| Installed Ponytail bundle | Upstream `356918eba965ee1eac64bd3a7f0dd02108350de5` | Distinguished from the later upstream runtime; bundle presence is not active hook support |

The initial implementation was local-only: no competitor source package, proxy
or model weights were imported. Later runtime work added actual pinned Ponytail
instruction loading and an isolated Headroom worker; see `PRODUCT_RUNTIME.md`
and `INTEGRATION_PARITY_STATUS.md` rather than treating that initial boundary as
the current integration status. The local compressor, request planner and
controller remain separately identified. Jev is an optional external API.

The detailed source manifests and analyses remain under:

```text
docs/research/2026-10-04-parity/PARITY_REPORT.md
docs/research/2026-10-04-parity/GAP_BACKLOG.md
docs/research/2026-10-04-parity/ponytail/REPORT.md
docs/research/2026-10-04-parity/headroom/REPORT.md
docs/research/2026-10-04-token-efficiency/FRAMEWORK.md
docs/research/2026-10-04-token-economics/foundations/PROOFS-AND-CONTINUOUS-IMPROVEMENT.md
docs/research/2026-10-04-token-economics/foundations/references/foundational-reference-memo.md
```

Selected authored research dossiers, mathematical checks and provenance indexes
are preserved on `codex/working-handoff-2026-10-16` through explicit packaging
exceptions. Fetched upstream source trees, bulk source snapshots and raw runs
remain local-only; a checkout is not the complete historical evidence archive.
The only bundled upstream source-tree exception is the qualifier's two pinned
public document fixtures, with their original LICENSE and NOTICE.
The handoff and its JSON index distinguish included records from excluded
assets. Historical validators may require those excluded original inputs and
must not be mistaken for current-source verification.

The token-only theorem and implementation contract are reproduced in
`TOKEN_EFFICIENCY.md`; they do not require an ignored file to define the
software's behavior. The older research's monetary framing is historical,
superseded by the user's token-only scope. This snapshot does not refresh the
upstream research pins or paper conclusions.

## Primary research references

- Agrawal et al., **GEPA: Reflective Prompt Evolution Can Outperform Reinforcement
  Learning**, arXiv `2507.19457v2`. Supports an empirical frozen-weight search
  strategy, not a global-optimum or deployment-safety theorem.
- Howard, Ramdas, McAuliffe and Sekhon, **Time-uniform Chernoff bounds via
  nonnegative supermartingales**, arXiv `1808.03204v8`. Bounded-difference
  concentration and range-width assumptions.
- Howard et al., **Time-uniform, nonparametric, nonasymptotic confidence
  sequences**, arXiv `1810.08240v9`. Time-uniform inference; the implementation
  uses its own elementary union-spending construction, not a claim to implement
  the paper's sharper variance-adaptive methods.
- Dwork et al., **Generalization in Adaptive Data Analysis and Holdout Reuse**,
  arXiv `1506.02629v2`. Why repeated adaptive holdout use is not fresh evidence.
  The implementation prevents known replay; it does not implement Thresholdout.
- **JEV vs. LLMs as Rubric Judges**, arXiv `2609.29769v2`. Model/vendor evaluation
  context only, not an independent correctness oracle for this repository.
- Task-dependent rate–distortion research, arXiv `2407.15504v2`. Motivation for
  preserving task-relevant information, not a proof that a particular code/log
  omission is safe.
- Hoeffding's original bounded-sum inequality supplies the elementary
  concentration specialization proved and used in `TOKEN_EFFICIENCY.md`.

## Official implementation contracts

```text
https://docs.typesafe.ai/api
https://code.claude.com/docs/en/hooks
https://code.claude.com/docs/en/mcp
https://developers.openai.com/codex/mcp/
https://developers.openai.com/codex/config-reference/
https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers
```

Host behavior is version-sensitive. The native smoke evidence records the
installed CLI versions and tested schemas. A source/doc citation, a model's
confidence, a storage round-trip, and an accepted host replacement are four
different forms of evidence; none establishes whole-task quality by itself.
