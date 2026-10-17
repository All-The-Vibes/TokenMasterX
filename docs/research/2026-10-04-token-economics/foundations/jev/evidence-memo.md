# Research: Jev in a frozen-model TokenMaster optimizer

## Request Type
Bounded current-best-practice and API-contract research. Retrieved October 4, 2026. No inference calls, installations, account access, implementation, or weight updates.

## Direct Answer
**Jev can supply decisions to repeated search over prompts, context selection, transforms, and routing without customer weight updates. That does not establish continuous improvement.** TypeSafe explicitly says Jev is not customer-fine-tuned/LoRA-adapted; requests, rather than per-account weights, customize its behavior [S2]. No reviewed source establishes monotonic improvement, convergence, or improvement in TokenMaster's true objective from hill climbing on Jev scores. Treat these as possible search signals, not proof obligations discharged by the provider.

The parent should distinguish three properties: valid output shape, accurate judgment, and statistically justified acceptance. Only the first is the typed-output contract; the other two require separate evidence [S1, S4, S5]. Changing request content is compatible with frozen weights; changing a moving model alias is not a reproducible frozen-model experiment [S2].

## Official Docs Evidence

### Typed outputs and probability semantics
- **Choice:** returns the maximum-probability member of supplied options, their normalized distribution, and confidence; at most 255 options. This chooses among supplied labels, not arbitrary text, and does not establish that the chosen label is true [S1].
- **Noul:** returns a probability of “yes” in `[0,1]`, with no separate confidence field. The application owns the threshold; “yes” means the supplied proposition, not necessarily “candidate is correct” [S1, S3].
- **Score:** returns the expectation `sum(i * p_i)` over zero-based rubric levels, plus probabilities, legend, and confidence. Use 2–10 descriptive levels. Levels are evaluated separately without their indices or neighbors being shown to the model. The resulting expectation is not a measured quantity or a license to numerically interpolate a true answer [S1, S6, S7].
- Multiple questions share one state and are described as independently evaluated. **Inference:** operationally separate question evaluation is not a statistical independence assumption about their errors [S8].

### Confidence is not correctness certification
For `n > 1` Choice options, the documented statistic is

`C_choice = (p_max - 1/n) / (1 - 1/n)`.

For Score, with modal index `m`,

`C_score = max(0, 1 - sum(p_i * abs(i-m)) / D)`,
`D = (1/n) * sum(abs(i - (n-1)/2))`.

Noul has no returned confidence; the docs optionally suggest `abs(2p-1)`. These are distribution-derived statistics, not independent correctness measurements [S3]. In particular, neither `p_max` nor this rescaling automatically supplies calibrated accuracy on TokenMaster's task distribution.

TypeSafe describes RLCD as optimizing calibrated decisions. Its current explanatory docs explicitly limit calibration to groups of predictions, not guarantees for individual answers [S4, S5]. The Score documentation itself says higher confidence does not establish correctness [S6]. No inspected page provides a workload-universal calibration bound, confidence interval, or guarantee under adaptive prompt/transform search.

### Repeatability, input, and content limits
The public request contract exposes state, model, and questions—not a documented seed, temperature, or deterministic mode [S1, C1]. The closed-set/parallel output mechanism must not be described as guaranteeing repeatability. Backend stochasticity, precision, routing, tie-breaking, and reproducibility commitments remain unresolved; the independent observations below reinforce the need not to assume determinism. Content-moderation/refusal behavior beyond the documented HTTP errors was not established.

Inputs are text, including JSON objects/arrays; no native image/audio/video. English is the strongest documented language. Limits are 64k tokens for state plus all questions, and 32k for state plus the longest question [S2, S8]. JSON may contain numeric fields; that does not make Jev an arithmetic engine.

The provider documents unreliable counting, arithmetic/date comparison, multi-hop indirection, distractor-heavy context, contradictory criteria, adversarial state, and Choice ordering bias. State is not treated as hostile by default [S7]. Keep exact token counts, prices, validity checks, and arithmetic outside Jev. Use fully described rubric levels and explicit no-match options rather than assuming an offered label must fit.

### Cost and latency boundaries
Current published price is **$0.042 per million input tokens; output tokens free**. The tariff component is `0.042 * billed_input_tokens / 1,000,000`; use returned usage rather than assuming characters or local tokenizer counts equal billable tokens [S1, S2]. Shared-state batching avoids re-sending state for every question; questions still add tokens [S2, S6].

Current nominal limits are **100k tokens/second and 80 requests/second**, explicitly dynamic and subject to change [S2]. The launch advertises **70–500 ms end-to-end**, not a demonstrated TokenMaster percentile or an SLA [S0]. Exact tokenizer, fixed serialization/internal overhead, minimum billing increments, retry/deduplication charging, cache discounts, and workload-specific tail latency were not established. This is not an all-in optimizer price: candidate generation, retries, independent verification, and regressions remain separate costs.

### Privacy
The Privacy Policy (November 19, 2025) prohibits training/fine-tuning on customer inputs, but permits service-provider processing and necessity-based retention; it describes U.S. hosting/storage/processing [S9]. The DPA (April 24, 2026) also uses necessity-based retention [S10]. Enterprise ZDR is offered separately, not established for this account [S11]. No organization-specific contract, ZDR entitlement, or exact default deletion period was verified. Do not interpret “not trained on” as “not retained.”

## Version Note
- Official launch page: **September 15, 2026** [S0].
- Current model table: **`jev-1.13.0`**. Both `jev-latest` (stable alias) and `jev-preview` currently map to it; no separate preview is listed. Pin the explicit version and log the response model. No immutable-backend guarantee, model-weight digest, retirement policy, or exact 1.13.0 release date was established [S2].
- SDK examined: documentation-linked JavaScript **v0.6.0**, full commit **`66880ccded6cb642dc1809620c2b108c33730214`**, committed **September 15, 2026, 18:16:33 UTC**. This is the documented release examined, not a claim that no newer package exists [C0–C3].
- Docs are mutable. The saved snapshots, retrieval timestamps, and SHA-256 hashes establish what was inspected, not what existed at an earlier date.

## Source-Reference Evidence
Canonical vendor SDK source fills the gap between TypeScript declarations and runtime enforcement:

- `typesafe-ai/typesafe-sdk-js@66880ccded6cb642dc1809620c2b108c33730214:src/types.ts:L73-L142` — response types preserve criterion keys and carry model/usage metadata [C1].
- `typesafe-ai/typesafe-sdk-js@66880ccded6cb642dc1809620c2b108c33730214:src/types.ts:L155-L171` — public request fields; comment allows forwarding extra properties, which is **not** evidence that undocumented provider controls work [C1].
- `typesafe-ai/typesafe-sdk-js@66880ccded6cb642dc1809620c2b108c33730214:src/client.ts:L311-L346` — validates questions, sends request, parses response, then casts to `T` [C2].
- `typesafe-ai/typesafe-sdk-js@66880ccded6cb642dc1809620c2b108c33730214:src/client.ts:L472-L489` — permissive JSON parsing. This path does not validate response probability ranges/sums, rubric membership, calibration, or semantic truth [C2].

**Compatibility ambiguity:** SDK `state` admits `null`, while prose API documentation lists string/object/array. Treat server acceptance of `null` as unverified; SDK typing alone cannot resolve it [S1, C1].

## Independent Primary Research
**Citation correction:** the supplied `2609.26301` is *Design of Polar Codes with Puncturing and Extending*, submitted **September 22, 2026**, not the requested title [P0]. The relevant study located is *JEV vs. LLMs as Rubric Judges: Cheaper, Faster, and Wrong in the Same Places*, Rao/Callison-Burch: **2609.29769**, v1 **September 24**, v2 **September 28, 2026**. This memo uses v2; intended-paper identity remains unconfirmed [P1].

Methods: 5,003 pairs, nine panels/seven human-labeled benchmarks; fixed zero-shot criteria; binary thresholds/ordinal decoding; unit-bootstrap intervals (10,000 resamples), Holm correction. Runs: September 19; holistic/high-effort extensions September 27. Comparators: `gpt-5.6-luna`, `gemini-3.8-flash`, `deepseek/deepseek-v4.1-flash`, undated IDs. Main Jev used `jev-latest`, unlogged resolution; same-day stability requests reported `jev-1.13.0`, with repeated-input verdict changes.

Of 252 comparator verdicts on 84 selected confident Jev errors, 242 repeated its error (96.0%; conditional-independence baseline 50.3%). Oracle cascades gained at most 2.7 points over the best single judge.

Limitations: exploratory/post-hoc analyses; selected errors; small samples; rounding/abstention conventions; asymmetric prompts/options; unpinned service drift; possible contamination; English short ordinal tasks; no larger/few-shot judges; optimistic oracle selection. These are tested configurations, not every workload [P1, §§3–6, Limitations, Appendix A].

## Supporting Examples: supported roles, not implementation decisions
| Role | Concrete bounded use | Boundary |
|---|---|---|
| Candidate triage | Score relevance/constraint adherence to prioritize a shortlist; explicitly preserve no-match/uncertain outcomes. | Ranking errors can hide good candidates; no completeness guarantee. |
| Task/transform routing | Choice among pre-approved transforms or handlers, with code controlling applicability and fallback. | Not authority to execute, change permissions, or certify a transform. |
| Cheap proxy evaluator | Several narrow Noul/Score questions about a candidate, retained individually before application-defined aggregation. | A proxy can disagree with the acceptance objective; combining numbers does not establish joint correctness. |
| Independent acceptance gate | **Jev alone does not supply this.** Parent defines evidence appropriate to the property: executable checks, reference answers, held-out labeled assessment, or other justified verification. | A second neural judge is not independent merely because it has a different provider or architecture. |

These are application-level inferences from the typed-decision workflow and documented limitations, not vendor guarantees or a proposed weight-training scheme [S1, S4, S7, S12]. No transform-specific performance has been measured here.

## Caveats / Ambiguity Flags
1. Separate calibration, discrimination/ranking, and correctness; validate the actual question/label set, not merely the model brand.
2. A syntactically valid answer can be confidently wrong. A finite schema also excludes any correct answer that its designer omitted.
3. Treat operational batching as distinct from independent evidence. Rephrasing the same question or taking multiple Jev votes does not establish independent error draws.
4. For the parent's proof work, expose model/version, rubric, candidate-generation process, evaluation distribution, measurements, and acceptance procedure as explicit assumptions. No proof is supplied by this memo.
5. Repeated optimization, holdout use, drift monitoring, and acceptance-error control require a separately specified protocol; no blanket mathematical claim follows from “Jev + hill climbing.”

## Reusable Takeaway
**Frozen-weight search is compatible with Jev's API. Guaranteed continuous improvement is not an established Jev capability.** Use it as a measured routing/triage/proxy signal; retain independently justified acceptance evidence. Resolve the supplied paper citation before attributing findings to “Judge the Judges.”

## Source Index
Primary sources only; source-reference evidence is vendor code, not a separate OSS comparison.

| ID | Source |
|---|---|
| S0 | https://typesafe.ai/blog/introducing-system-one-models-and-jev |
| S1 | https://docs.typesafe.ai/api.md |
| S2 | https://docs.typesafe.ai/models.md |
| S3 | https://docs.typesafe.ai/confidence.md |
| S4 | https://docs.typesafe.ai/concepts/system-one.md |
| S5 | https://docs.typesafe.ai/introduction/machine-learning-primer.md |
| S6 | https://docs.typesafe.ai/primitives/score.md |
| S7 | https://docs.typesafe.ai/model-jaggedness/jev-1.13.md |
| S8 | https://docs.typesafe.ai/concepts/state.md |
| S9 | https://typesafe.ai/legal/privacy-policy |
| S10 | https://typesafe.ai/legal/data-processing |
| S11 | https://docs.typesafe.ai/legal.md |
| S12 | https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md |
| C0 | https://docs.typesafe.ai/sdk/javascript.md |
| C1 | https://github.com/typesafe-ai/typesafe-sdk-js/blob/66880ccded6cb642dc1809620c2b108c33730214/src/types.ts |
| C2 | https://github.com/typesafe-ai/typesafe-sdk-js/blob/66880ccded6cb642dc1809620c2b108c33730214/src/client.ts |
| C3 | https://api.github.com/repos/typesafe-ai/typesafe-sdk-js/commits/v0.6.0 |
| P0 | https://arxiv.org/abs/2609.26301 |
| P1 | https://arxiv.org/html/2609.29769v2 |

### Verification and scope
Source reads and scoped artifact writes only. No model execution, account inspection, sensitive-content submission, dependency installation, service launch, commit, or production edit. Other repository work was not inspected or modified. `retrieval-log.json` records downloaded-source hashes; `source-metadata.json` maps memo citations to evidence and version caveats.
