# Pinned author-associated code: differences from arXiv v1

**Read-only source audit; no downloaded code was executed or imported.**

Repository: [AhsanBilal7/self_refine][repo]. Pin: **`cf260f39da0640ea5faf6db6139121485ee78fc7`**, October 4, 2026, 19:52:02 UTC. The README names the exact paper and maps its method to the code name CIMR. GitHub metadata identifies repository creation on October 4, 2026. This later release is not by itself evidence that the same implementation produced the August 6 arXiv v1 results. No arXiv outbound repository link was found.

The corresponding author's name and repository account naming support the association, and the README self-identifies the work; no stronger identity claim is made. Narrow title/ID repository searches missed it; a title search including README content found it. All search results are retained, including the initially empty ones.

## 1. Method and budget discrepancies

| Finding | Pinned source reference | Consequence |
|---|---|---|
| Initialization is folded into depth 1: the first generator output is both \(r^{(0)}\) and \(g^{(1)}\). | `AhsanBilal7/self_refine@cf260f39da0640ea5faf6db6139121485ee78fc7:src/cimr_step.py:L14-L23,L258-L290`; [source][step] | Code executes \(3ND\) generation sequences, **96** at \(N=8,D=4\), not literal Algorithm 1's \(N+3ND=104\). Without critique it is \(2ND=64\), not 72. Freeze the intended schedule explicitly. |
| Only first-depth generation is sampled; later generation, critique and correction are greedy. | Same file `L267-L340`; [source][step] | Do not assume temperature .7 is applied to every role/depth. Black-box interfaces may not expose equivalent controls. |
| Concrete role prompts depend on problem and current branch content, not gold. | `src/cimr_prompts.py:L37-L61,L69-L80,L83-L132,L139-L177,L184-L230`; [source][prompts] | These are useful prompt references, not proof of effectiveness. The file claims a paper “Role Prompts” appendix, which is absent from the supplied v1. |
| Output budgets: generator 2048, critic 384, corrector 1024; prior/trace caps 4000 characters, critique cap 1500. | `src/cimr_step.py:L200-L224`; [source][step] | Different stage budgets and repeated context must be counted. Character caps are not token caps. |
| The generation wrapper uses each model's Hugging Face tokenizer/chat template, then truncates prompts to **2048 tokens** and decodes output with special tokens removed. | `src/cimr_step.py:L108-L126`; `src/model_wrapper.py:L196-L205,L259-L316`; [wrapper][wrapper] | Retokenizing saved strings later is not identical to measuring actual token IDs processed/generated. The released compute script does not replay this exact process. |

The no-PRM code generator-output upper bound under these defaults is \(ND(2048+384+1024)\) native new tokens, **110,592** for \(N=8,D=4\), before any input tokens. This is a configured upper bound, not an observed length or a closed-provider bound. No values were measured by inference here.

## 2. Default selection is not strictly verifier-free

The entry point loads **Qwen2.5-Math-PRM-7B unless `--no_prm` is set**:

`AhsanBilal7/self_refine@cf260f39da0640ea5faf6db6139121485ee78fc7:run_paired_ablation.py:L69-L73,L191-L200`. [Source][entry]

It scores both the reasoning and corrected trace at each branch/depth, up to \(2ND=64\) logical scoring evaluations for the default successful nonempty run (`src/cimr_step.py:L166-L193,L293,L359`). These sequences can be batched into fewer model forwards; they still contribute all their processed input tokens.

The final vote ranks answer groups by **vote count, summed PRM score, then first branch index**:

`AhsanBilal7/self_refine@cf260f39da0640ea5faf6db6139121485ee78fc7:src/cimr_aggregator.py:L89-L117`. [Source][aggregate]

**Analysis:** Despite comments describing scores as diagnostic, PRM-dependent ties affect the method's selected output. The default code is not strictly verifier-free. With `--no_prm`, scores are zero and ties reduce to branch order. A verifier-free adaptation should freeze that kind of non-verifier selector; it cannot inherit the default label while quietly using reward scores.

The code does **not** show gold-answer leakage into its generator/critic/corrector prompts. Although `gold_answer` is passed to the scoring interface, the implementation explicitly ignores it:

`AhsanBilal7/self_refine@cf260f39da0640ea5faf6db6139121485ee78fc7:src/verifier.py:L315-L328`. [Source][verifier]

Gold-based correctness is applied after the vote in `src/cimr_aggregator.py:L129-L140`. Do not confuse this offline evaluation with the runtime PRM or infer leakage merely from the argument name.

## 3. The released compute script is a proxy estimator, not an objective token ledger

`AhsanBilal7/self_refine@cf260f39da0640ea5faf6db6139121485ee78fc7:extract_compute_flop.py:L89-L123,L138-L167,L203-L311`. [Source][compute]

Observed source behavior:

- Assigns `cl100k_base` as the token-count proxy for every listed model.
- Adds a fixed **120-token** system/template overhead; exact formatted prompts are not stored.
- Approximates input by separately counting question and trace strings.
- Counts the *first* capped characters of a trace, whereas the actual prompt builder retains head and tail plus an omission marker.
- Does not apply the actual wrapper's final model-tokenizer 2048-token prompt truncation.
- Skips critique/correction input accounting when the saved output is empty.
- Calculates verifier forwards separately; they are added to `total_tflop_per_question`, while the README identifies `generator_tflop_per_question` as the verifier-free method's compute.

**Analysis:** Exact tokenization of an approximate string is still an approximate reconstruction. Empty output does not prove no input/compute was consumed. If PRM scores break a tie, excluding that PRM work understates the selected policy's full work. The script also calculates scoring-phase estimates without checking whether that run actually disabled PRM; do not equate a computed total with an observed call ledger.

These behaviors do not establish the paper's claim that all reported counts are actual processed contexts after the same truncation. They also do not prove which script/version produced the published tables. No raw run stores were present in the inspected current tree, so this audit does not recompute paper results.

For TokenMaster, retain the common reference tokenizer/protocol **as an explicitly named reference metric**, and preserve native usage separately. Do not import the author's proxy estimator as proof of native or total-token savings.

## 4. Evaluation, defaults and reproducibility

| Area | Evidence | Caveat |
|---|---|---|
| Answer extraction | `src/cimr_step.py:L68-L101` ([source][step]) reads the last boxed answer, falling back to the last number; empty correction carries generator output forward (`L344-L355`). | This needs an explicit validity/failure policy. It is not a proof checker. |
| Voting equivalence | `src/cimr_aggregator.py:L29-L45,L89-L117` ([source][aggregate]) preserves case and uses light string keys. | Paper Appendix A.5 says lowercase normalization. Symbolically equivalent representations can split votes. |
| Baseline/diagnostic consistency | `src/inference_methods.py:L344-L414` ([source][inference]) groups baseline votes with the evaluator's equivalence checker; `extract_cimr_metrics.py:L75-L121` ([source][metrics]) uses lowercase string correctness and first-seen count ties. | These are not the refinement selector's exact grouping/tie contract. Do not assume diagnostic curves or baseline voting isolate only the refinement policy. |
| Offline correctness | `src/cimr_aggregator.py:L129-L140` and `src/inference_methods.py:L136-L156` ([source][inference]) route to benchmark equivalence checks. | More than the paper's simple string description; the checker/version must be pinned separately. |
| Models | `configs/qwen_1b.conf:L1-L9` and `configs/ministral_8b.conf:L1-L9` ([Qwen][qwen-config], [Ministral][ministral-config]) use Qwen2.5-1.5B-**Instruct** and Ministral-8B-Instruct-**2410**. | These resolve ambiguities in paper labels, not identical-weight evidence for an arbitrary API model ID. No model revision SHA is pinned by the load calls. |
| Verifier baseline | Entry point defaults to PRM-7B; README [Baselines][readme-baselines] also describes PRM-7B and says beam/lookahead are not implemented. | Paper Table 1's RM@8 uses Math-RM-32B and includes beam/lookahead. Do not claim complete reproduction of those baselines from this tree. |
| Failure records | `src/cimr_step.py:L129-L159`; `src/cimr_rollout.py:L147-L203` ([source][rollout]) catch batch exceptions, carry placeholders/prior state, and can return completed rollout records. | A frozen objective audit must distinguish finished control flow, valid output, success and complete token accounting. |
| Resumption | `run_paired_ablation.py:L155-L160`; `src/cimr_inference.py:L57-L88,L191-L217` ([source][orchestrator]) reuse result paths/stores; the no-PRM flag is not part of the tag. | Reusing output directories can mix settings. A fresh frozen capture needs stronger identity than dataset/N/depth path names. |
| Release provenance | Repository metadata and pinned tree; final commit changes extraction behavior and the 1.5B label. | October source is later than August v1; current behavior is not historical run provenance. No raw results were found in this tree. |
| License | Public metadata reports no repository license; no root LICENSE appears in the pinned tree. README calls the vendored math toolkit MIT. | Do not infer a whole-repository license from a vendored component or the paper's CC BY license. No code adoption occurred. |

All abbreviated file references in this section are to `AhsanBilal7/self_refine@cf260f39da0640ea5faf6db6139121485ee78fc7`, never a moving branch.

## 5. Practical applicability conclusion

**Adaptable control flow, unproven benefit, non-identical paper/code contracts.**

An exposed-text, weight-free adaptation can be defined for OpenAI/Anthropic via an authorized Copilot surface. But first freeze whether it follows the paper's separate-initialization schedule or the released code's folded schedule, specify a non-verifier selector, and account for every actual call. Neither source supports independence of provider errors or correctness certification by self-critique/voting.

Do not weaken the current single-model/stateless/no-retry TokenMaster adapter to accept either policy. Use a separately frozen iterative/multi-model adapter and fresh paired oracle-scored capture, as specified in [APPLICABILITY.md](APPLICABILITY.md). This source audit did not run author experiments, reproduce a benchmark, inspect user credentials, or change application code.

[repo]: https://github.com/AhsanBilal7/self_refine/tree/cf260f39da0640ea5faf6db6139121485ee78fc7
[step]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/cimr_step.py
[prompts]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/cimr_prompts.py
[wrapper]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/model_wrapper.py
[entry]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/run_paired_ablation.py
[aggregate]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/cimr_aggregator.py
[verifier]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/verifier.py
[compute]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/extract_compute_flop.py
[inference]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/inference_methods.py
[qwen-config]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/configs/qwen_1b.conf
[ministral-config]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/configs/ministral_8b.conf
[readme-baselines]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/README.md#baselines
[rollout]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/cimr_rollout.py
[orchestrator]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/src/cimr_inference.py
[metrics]: https://github.com/AhsanBilal7/self_refine/blob/cf260f39da0640ea5faf6db6139121485ee78fc7/extract_cimr_metrics.py
