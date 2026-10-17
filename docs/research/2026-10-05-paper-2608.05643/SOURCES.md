# Source manifest and reading record

Retrieved October 5, 2026 UTC. Sources below are primary paper/author-associated source or official GitHub/OpenAI/Anthropic documentation. No third-party tutorial supplies a substantive claim.

## Outputs

- [APPLICABILITY.md](APPLICABILITY.md): paper interpretation, applicability, all-call objective and bounded frozen-study proposal.
- [AUTHOR_CODE_AUDIT.md](AUTHOR_CODE_AUDIT.md): pinned code/paper differences and exact file/line references.
- [source_manifest.json](source_manifest.json): machine-readable retrieval metadata and SHA-256 inventory of every source/derivative.

## Identity and paper version

- Exact input: https://arxiv.org/html/2608.05643v1
- Independent record: https://arxiv.org/abs/2608.05643v1
- Author source archive: https://arxiv.org/src/2608.05643v1
- Confirmed title: **Refining Over Resampling: Test-Time Self-Correction for LLM Reasoning**.
- Version: **v1**, submitted **August 6, 2026, 06:38:37 UTC**; record says submitted to EMNLP 2026, not accepted.
- Authors: Ahsan Bilal; Muhammad Ahmed Mohsin; Muhammad Umer; Lena Trigg; Ali Subhan; Muhammad Ali; Dean F. Hougen.
- License: **CC BY 4.0** for the paper/source archive. Retained sources and figures are attributed to those authors; rendered PNGs/text are local research derivatives, not revised results.
- HTML SHA-256: `33a805ecd594621879e1b4f10bbf52089df2cb9fb489102d3df0b414d821ad68`.

Read the complete paper, including Algorithm 1, all four numbered tables, all six figures (seven supplied figure assets), numbered equations 1–10, references, appendices and limitations. Source TeX was checked for the Appendix B errors, missing reproduction details and commented-out material. Each figure PDF was rendered and visually inspected. Equations and selected numerical results are analyzed, not independently reproduced by model inference.

## Author-associated repository

- Repository: https://github.com/AhsanBilal7/self_refine
- Read at `cf260f39da0640ea5faf6db6139121485ee78fc7`, committed **October 4, 2026, 19:52:02 UTC**.
- Pinned tree: https://github.com/AhsanBilal7/self_refine/tree/cf260f39da0640ea5faf6db6139121485ee78fc7
- Association: README gives the exact title and method; account naming matches the corresponding author. No arXiv outbound repository link was present. Do not overstate original-run provenance.
- Discovery: initial narrow ID/title searches returned zero; README-scoped title search returned the repository among paper lists. Paper lists were not used as evidence. Original search JSON responses remain in `sources/`.
- Inspected full core refinement/prompt/aggregation/orchestration paths and relevant generation, scoring, evaluator, defaults, resumption and compute-analysis paths. Source files were saved/read only, never imported, installed or run.
- The pinned current tree has no raw experiment result store and no root LICENSE. Do not extend a vendored MIT component's license or the paper's CC license to the whole repository.

## Official Copilot version pins

- Stable SDK **v1.0.16**, released September 30, 2026: `f8ae645902b74b62cd47aac1fd9b29adaec3aff2`.
- Tag resolved via the public GitHub tag-ref endpoint, not merely inferred from release metadata.
- Also inspected HEAD `6b4f3a3bde7eb9a8604617b91effe0f4a2e3921b` (October 4), which references CLI snapshot 1.0.92-4. Stable pins are used for the main source citations where possible.
- Neither version is a claim about this user's installation. Rolling official docs can differ from a shipped runtime; concurrency descriptions conflict within the retrieved CLI page and are flagged in the report.

## Main official documentation

| Source | URL | Establishes |
|---|---|---|
| Supported Copilot models | https://docs.github.com/en/copilot/reference/ai-models/supported-models | Public model/client/policy distinctions; not account entitlement |
| Programmatic reference | https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference | Explicit model selection, precedence, JSONL |
| CLI command reference | https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference | Controls, usage output, subagents and documented inconsistencies |
| Multiple sessions | https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/work-with-multiple-sessions | Side-by-side running sessions |
| Usage limits | https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/usage-limits | Throttling; no universal experimental concurrency allowance |
| Session limits | https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/set-session-limit | Soft non-token cap; not a hard all-call token bound |
| SDK usage guide | https://github.com/github/copilot-sdk/blob/f8ae645902b74b62cd47aac1fd9b29adaec3aff2/docs/features/usage-and-billing.md | Ephemeral per-call events versus current context versus cumulative metrics |
| Responses usage | https://developers.openai.com/api/reference/resources/responses/methods/create | Native OpenAI usage fields |
| OpenAI token counting | https://developers.openai.com/api/docs/guides/token-counting | Processed input and hidden-output limitations of local counting |
| Anthropic prompt caching | https://platform.claude.com/docs/en/build-with-claude/prompt-caching#tracking-cache-performance | Direct Anthropic input-token component decomposition |

No pricing, account credits or monetary quantity enters the research objective or proposed gates. Raw official source snapshots may contain unrelated sections; those sections are not adopted as objectives or optimization advice.

## Retrieval and validation boundaries

The web tool returned no usable page bodies in this lane. Direct public HTTPS GET retrieval succeeded, and raw bodies, retrieval records and hashes are preserved. No authenticated account endpoint or inference/counting endpoint was called. One guessed CLI documentation path returned 404 and is retained as a failed retrieval; valid official pages were then found from documentation links. The old rate-limit URL redirected; the final official URL is recorded.

For initial HTML and SDK-tree retrievals, exact request time was not separately recorded, so their manifests explicitly use snapshot filesystem modification time as the timestamp basis. Other retrievals have recorded UTC request-completion times. Derived text may omit layout; raw HTML/TeX/PDF/source is authoritative.

All research writes were confined to this new folder. No TokenMaster implementation, configuration, credentials, experiments, commits or pushes were touched. Current adapter/pilot statements are attributed to the user's task updates, not inferred from local source.

## Snapshot inventory

Every row below is a successfully retrieved source. Full SHA-256 values, resolved URLs, retrieval timestamps, failures, archive members and derivative hashes are in `source_manifest.json`.

| Snapshot | Bytes | SHA-256 prefix |
|---|---:|---|
| `sources/anthropic-prompt-caching.md` | 159255 | `78d10f9ffe8ebd5d` |
| `sources/author-README.md` | 11952 | `df9aba34cb0a3bca` |
| `sources/author-code-id-readme-search.json` | 5891 | `2d2b74f875c5b42b` |
| `sources/author-code-search.json` | 55 | `4af480b8ee5b87b3` |
| `sources/author-code-title-readme-search.json` | 44341 | `3085f386a1c49023` |
| `sources/author-configs__llama3_8b.conf` | 536 | `a12493eeb363180d` |
| `sources/author-configs__ministral_8b.conf` | 546 | `1430901afa36f59d` |
| `sources/author-configs__qwen_1b.conf` | 526 | `b64905e14b380412` |
| `sources/author-configs__qwen_7b.conf` | 532 | `1c1348a516eb114f` |
| `sources/author-extract_baseline_flop.py` | 27726 | `5c476b0fc59b8662` |
| `sources/author-extract_cimr_metrics.py` | 23599 | `d7e7666f9a7cd84a` |
| `sources/author-extract_compute_flop.py` | 32698 | `859e86859b27d205` |
| `sources/author-head.json` | 14337 | `6c5d3e981d2715f8` |
| `sources/author-print_paired_accuracies.py` | 10692 | `b6ccf0d1c2af901d` |
| `sources/author-repository.json` | 5264 | `f0c8aae226e6335d` |
| `sources/author-requirements.txt` | 646 | `edf2c667a341a6bf` |
| `sources/author-run_paired_ablation.py` | 13495 | `f6d10eea91fff4c0` |
| `sources/author-run_paired_ablation.sh` | 5498 | `89371a655e9ca5ca` |
| `sources/author-src__cimr_aggregator.py` | 6155 | `46b6c85cef64a6c5` |
| `sources/author-src__cimr_inference.py` | 8523 | `f6c284c19f926ccc` |
| `sources/author-src__cimr_prompts.py` | 9241 | `c621520973ea66ba` |
| `sources/author-src__cimr_rollout.py` | 7071 | `351a656164caed00` |
| `sources/author-src__cimr_step.py` | 14103 | `d59739787151e8f1` |
| `sources/author-src__dataset_loader.py` | 9653 | `6eb587b12d09fb49` |
| `sources/author-src__evaluator_classes.py` | 10691 | `40e4c25262af434b` |
| `sources/author-src__inference_methods.py` | 20040 | `cc94dcf692d9d266` |
| `sources/author-src__math_toolkit__latex_answer_check.py` | 14304 | `11bbb71c7cf97746` |
| `sources/author-src__model_wrapper.py` | 20398 | `5c513917a45a44e6` |
| `sources/author-src__verifier.py` | 13815 | `2793bb41f849e797` |
| `sources/author-tree.json` | 10045 | `eba6cfec6534cd99` |
| `sources/copilot-cli-commands.html` | 1879901 | `54dfaf5283be25b6` |
| `sources/copilot-multiple-sessions.html` | 650725 | `9d567f77069cd38c` |
| `sources/copilot-programmatic.html` | 690324 | `3eec744a7305d308` |
| `sources/copilot-rate-limits.html` | 557983 | `d05683dd4effba06` |
| `sources/copilot-run-programmatically.html` | 665197 | `a4dfa8cfb8f5d560` |
| `sources/copilot-sdk-head.json` | 1174571 | `5f2d73fa62f69717` |
| `sources/copilot-sdk-latest-stable.json` | 3165 | `4c034321e217a40c` |
| `sources/copilot-sdk-releases.json` | 53594 | `70ba97bc987b7be1` |
| `sources/copilot-sdk-repository.json` | 6459 | `a7cd67d54a3b3765` |
| `sources/copilot-sdk-tree.json` | 1289031 | `c19b0e734bfa421e` |
| `sources/copilot-session-limit.html` | 578825 | `9882a4cc51740e2a` |
| `sources/copilot-supported-models.html` | 1354524 | `04fdb2b49d58e908` |
| `sources/openai-response-create.md` | 502744 | `e9c46fb7f7a206b5` |
| `sources/openai-token-counting.md` | 22672 | `a446c08afd6dca0e` |
| `sources/paper-2608.05643v1.html` | 476835 | `33a805ecd5946218` |
| `sources/paper-abstract.html` | 42523 | `bda6805296a48de1` |
| `sources/paper-source.tar.gz` | 300685 | `c1b4c622bfc92400` |
| `sources/paper-title-code-search.json` | 55 | `4af480b8ee5b87b3` |
| `sources/sdk-README.md` | 13442 | `39ab230a39a2592c` |
| `sources/sdk-docs__features__session-limits.md` | 4999 | `d01bd1d04216784f` |
| `sources/sdk-docs__features__usage-and-billing.md` | 40636 | `a76db00bd1c65f44` |
| `sources/sdk-docs__getting-started.md` | 62472 | `9754e30ec0e969de` |
| `sources/sdk-nodejs__src__client.ts` | 153248 | `f5b01a51598f540b` |
| `sources/sdk-nodejs__src__generated__session-events.ts` | 413852 | `806b6b67a4d8879b` |
| `sources/sdk-nodejs__src__session.ts` | 108024 | `ddb849f09a50a0c1` |
| `sources/sdk-nodejs__src__types.ts` | 133174 | `7e9934cbb4c1b4a7` |
| `sources/sdk-stable-tag-ref.json` | 341 | `19aec6f458e2d7e7` |
| `sources/stable-sdk-docs__features__session-limits.md` | 4999 | `d01bd1d04216784f` |
| `sources/stable-sdk-docs__features__usage-and-billing.md` | 40636 | `a76db00bd1c65f44` |
| `sources/stable-sdk-nodejs__src__client.ts` | 148752 | `321b1f51f1e01698` |
| `sources/stable-sdk-nodejs__src__generated__session-events.ts` | 404619 | `8bc4ec9dea0577c5` |
| `sources/stable-sdk-nodejs__src__types.ts` | 128813 | `4bd098fd654d63cc` |
| `sources/stable-sdk-nodejs__test__e2e__session_lifecycle.e2e.test.ts` | 6299 | `24e5eab708b9e2f5` |
