# Dependency Evaluation: OSS mechanisms for LLM token economics

**Study date: October 4, 2026. Scope: independent external-source research only.**

## Recommendation

**Use these projects as layer-specific experimental references, not as a single ranked “token saver” shortlist.** For an API-facing context optimizer, prioritize a controlled **LLMLingua-2 compression experiment** and a **RouteLLM-style routing experiment**; investigate **mem0** only for workloads that genuinely require durable memory, and **Outlines** only where invalid structured outputs or verbose output formats cause measurable waste. For owned inference infrastructure, compare **vLLM and SGLang first**, then evaluate **LMCache as an additional KV-storage/reuse layer**. Selective Context is a useful historical baseline, not the preferred new production dependency. These are conditional research recommendations, not permission to install or integrate anything. The implementation and test evidence below supports the distinction. [L-filter] [R-route] [N-add] [O-mask] [V-cache] [G-cache] [K-retrieve] [S-filter]

### Strongest actionable findings

1. **Do not import upstream “savings” fields into financial accounting.** LLMLingua selects a `gpt-3.5-turbo` tokenizer and computes its displayed GPT-4 saving from a hard-coded **$0.06 per 1,000 removed tokens**. It does not reconcile current provider/model prices, cache discounts, output tokens, compressor compute, or retries. Treat its token counts as tokenizer-specific estimates, not invoice evidence. [L-load] [L-cost]
2. **Separate “fewer tokens sent” from “less prefill work.”** vLLM, SGLang, and LMCache reuse inference state without necessarily shortening the request. LMCache even documents a case where **256 retrieved tokens represent only 224 newly needed tokens**, because retrieval overlaps locally computed pages. Adding cache-hit counters from different layers will overstate avoided work. [V-cache] [G-cache] [K-count]
3. **Routing can save money without reducing token count.** RouteLLM changes the chosen model; its matrix-factorization router itself makes an embedding API call. Its controller scores only the last message, and explicitly notes its routers were trained on first-turn data. Count routing overhead and test multi-turn/tool-use quality before trusting a threshold. [R-route] [R-mf]
4. **Memory is a stateful selection system, not free compression.** Current mem0 source performs retrieval, one extraction LLM call, embedding, storage, and later hybrid retrieval. Its `top_k` is a count of memory records, not a token ceiling. Its current headline benchmarks explicitly concern the **managed platform with proprietary optimizations**, not identical OSS performance. [N-add] [N-extract] [N-search] [N-rank] [N-claims]
5. **Production security depends on boundaries, not stars.** LLMLingua defaults `trust_remote_code=True` and evaluates a budget expression; cache engines need tenant isolation and model/configuration identity; mem0 enables telemetry by default; grammar constraints are not semantic correctness or a safe way to accept arbitrarily complex untrusted grammars. [L-load] [L-eval] [V-salt] [G-namespace] [N-telemetry] [O-grammar] [GHSA-rwxx-mrjm-wc2m]

**Confidence:** high in the inspected mechanisms, repository identity, pinned source references, and metadata at retrieval; moderate in operational fitness; no confidence claim about workload-specific net savings until measured. **Stop condition:** source-backed layer classification and bounded adoption gates are complete. No integration, compatibility execution, or provider-price validation was authorized here.

## Method and evidence boundaries

- Eight candidates were selected because their implementation changes context selection, model choice, constrained generation, or inference-state reuse. Popularity was contextual, not a fitness ranking. No unrelated training framework was added to fill the list.
- Public, unauthenticated GitHub REST responses include stars, forks, license detection, archived status, default branch, latest commit samples, release records, public repository advisories, and bounded issue/comment samples. Every response includes retrieval time and HTTP headers in `metadata/`.
- Full-SHA codeload archives were downloaded and hashed. Selected source/test/manifests were copied byte-for-byte into `sources/`; the archives remain in `snapshots/`. `source-files.json` records source URL, full SHA, SHA-256, local path, and line count. Sources were read, **not imported or executed**.
- Official PyPI metadata was fetched separately. A current default-branch SHA is **not proof that the latest wheel contains that code**. Every source observation below refers to its pinned SHA; release/package versions are separate selection anchors.
- `web.run` was invoked for searches and repository pages but returned no usable result payloads. Verification therefore used live HTTPS requests to official GitHub, PyPI, and Hugging Face endpoints, with raw evidence preserved. No third-party comparison article was used.
- No upstream tests or benchmarks were run. “Test evidence” means inspected assertions/harnesses, not a passing result. No dependencies were installed, credentials accessed, paid calls made, runtime configuration changed, commits created, or pushes performed. Local TokenMaster code, Ponytail, and Headroom were not inspected.
- Public issue comments are **upstream reports**, not validated reproductions or proof of a fix. No representative maintainer-response SLA, download count, or production-adoption statistic is claimed.

## Candidates

The following metadata was retrieved live on **October 4, 2026 UTC**; exact per-request timestamps are in `evidence.json`. “Latest commit” means the default-branch head returned by the commits endpoint, not repository-wide `pushed_at`. All eight repositories were non-archived at retrieval. [repo-llmlingua] [repo-selective] [repo-routellm] [repo-lmcache] [repo-vllm] [repo-sglang] [repo-mem0] [repo-outlines]

| Package / layer | Latest PyPI version; Python declaration | Maintenance: latest default-branch commit | Adoption context: stars / forks | License | Security / quality evidence |
|---|---|---|---|---|---|
| [microsoft/LLMLingua][repo-llmlingua] / direct-context-compression | **0.2.2**; `>=3.8.0` [pypi-llmlingua] | 2026-09-10; Research package; recent workflow maintenance, old release [commits-llmlingua] | 6,729 / 434 [repo-llmlingua] | MIT [license-llmlingua] | Model-loaded exact-output regression tests; configuration hazards inspected; see detailed inspection below |
| [liyucheng09/Selective_Context][repo-selective] / direct-context-compression-historical-baseline | **0.1.4**; `>=3.7` [pypi-selective] | 2024-02-12; No default-branch changes since 2024 [commits-selective] | 426 / 25 [repo-selective] | MIT classifier only; no license text found [S-deps] | No discovered test suite; license ambiguity; see detailed inspection below |
| [lm-sys/RouteLLM][repo-routellm] / direct-model-routing | **0.2.0**; `not declared` [pypi-routellm] | 2024-08-10; No default-branch changes since 2024 [commits-routellm] | 5,568 / 441 [repo-routellm] | Apache-2.0 [license-routellm] | Two live smoke clients; embedding overhead and calibration mismatch; see detailed inspection below |
| [LMCache/LMCache][repo-lmcache] / adjacent-inference-kv-storage | **0.5.5**; `<3.14,>=3.10` [pypi-lmcache] | 2026-10-04; Active dev branch and releases [commits-lmcache] | 11,958 / 1,984 [repo-lmcache] | Apache-2.0 [license-lmcache] | KV retrieval/equality/failure tests; native runtime coupling; see detailed inspection below |
| [vllm-project/vllm][repo-vllm] / adjacent-inference-server | **0.30.0**; `<3.15,>=3.10` [pypi-vllm] | 2026-10-04; Active head and frequent releases [commits-vllm] | 93,175 / 22,982 [repo-vllm] | Apache-2.0 [license-vllm] | Cache-salt assertions; 86 published historical advisories, not 86 current flaws; see detailed inspection below |
| [sgl-project/sglang][repo-sglang] / adjacent-inference-server | **0.5.21**; `>=3.10` [pypi-sglang] | 2026-10-04; Active head and frequent releases [commits-sglang] | 36,778 / 9,315 [repo-sglang] | Apache-2.0 [license-sglang] | Prefix/salt unit tests and multi-client server harness; see detailed inspection below |
| [mem0ai/mem0][repo-mem0] / direct-stateful-context-selection | **2.2.1**; `<4.0,>=3.10` [pypi-mem0] | 2026-10-01; Active head; Python and TypeScript releases differ [commits-mem0] | 66,568 / 7,847 [repo-mem0] | Apache-2.0 [license-mem0] | Mock call-count/scope regressions; managed/OSS benchmark distinction; see detailed inspection below |
| [dottxt-ai/outlines][repo-outlines] / conditional-output-constraint-layer | **1.3.3**; `<3.14,>=3.10` [pypi-outlines] | 2026-08-24; Recent release; head Aug 24, 2026 [commits-outlines] | 15,899 / 896 [repo-outlines] | Apache-2.0 [license-outlines] | Schema/regex/whitespace tests; provider-specific constraints; see detailed inspection below |

### Classification: what changes, and what does not

| Candidate | Integration boundary | Primary economic variable | Not equivalent to |
|---|---|---|---|
| LLMLingua / LLMLingua-2 | Transform selected text before an API request | Input token quantity; preprocessing overhead | Lossless compression, exact invoice saving, provider cache |
| Selective Context | Pre-request sentence/phrase/token deletion | Input quantity; local scorer overhead | A current production-ready replacement |
| RouteLLM | Choose a strong/weak model before completion | Price/capability mix and router overhead | Token reduction, a hard dollar budget |
| mem0 | Extract/store facts; retrieve a subset for a later prompt | Repeated-history avoidance versus memory lifecycle cost | A token-budget packer, or managed-platform parity |
| Outlines | Provider structured-output adapter or local decoding mask | Invalid-output retries and output format | General prompt compression or guaranteed lower output length |
| vLLM | Own the model-serving process | GPU memory utilization and avoided prefill | A client-side hosted-API discount |
| SGLang | Own serving and KV-memory scheduling | Prefix reuse, serving throughput/latency | A transparent API text compressor |
| LMCache | Connect to a serving engine's KV tensors and storage | Reuse beyond GPU-resident cache lifetime; transfer/storage cost | A response cache or an alternative hosted API |

Sources for this classification: [L-filter] [S-filter] [R-route] [N-add] [N-rank] [O-provider] [O-mask] [V-cache] [G-cache] [K-retrieve].

### Release and identity traps

- **RouteLLM canonical public upstream is `lm-sys/RouteLLM`.** Its package homepage points there. The public `Berkeley/RouteLLM` API request returned 404. The canonical repo has no GitHub release records in the retrieved list; PyPI's current version is **0.2.0**. Do not manufacture a Berkeley-owned release. [repo-routellm] [R-deps] [berkeley-route] [release-routellm] [pypi-routellm]
- **`microsoft/TokenCut` was not found publicly:** direct repository API 404 and an owner-scoped Microsoft search returned zero complete results. This is a bounded negative finding, not a statement about private or future projects. The inspected metadata for `YangtaoWANG95/TokenCut` describes normalized-cut **computer-vision object discovery**, so it is excluded from LLM token economics. [tokencut] [tokencut-search] [tokencut-cv]
- **LMCache:** designated latest is **v0.5.5**, published September 12, 2026. More recent nightly and v0.5.6rc2 artifacts exist; some platform-suffixed RC variants have `prerelease=false`. Do not pick “first release whose flag is false.” The extended response is saved in `metadata/LMCache__LMCache/releases_extended.json`. [release-lmcache] [pypi-lmcache]
- **Selective Context:** PyPI says **0.1.4**, while the designated GitHub latest is **v0.1.0rc1**, published December 26, 2023, with `prerelease=false`. These are distinct publication surfaces, not an inferred version ordering. [pypi-selective] [release-selective]
- **mem0:** GitHub's designated latest is the TypeScript **ts-v3.3.1** release, while Python's current distribution is **mem0ai 2.2.1**. Python v2.2.1 also appears in the saved release list. Internal source comments describe a “V3” memory pipeline; that is not the same thing as the Python package's major version. [release-mem0] [pypi-mem0] [N-add]

## Detailed source evaluation

### 1. Microsoft LLMLingua — preferred learned compression experiment, with guardrails

**Observed algorithm.** The original path uses a causal language model's per-token cross-entropy as a compression signal. LLMLingua-2 instead runs a learned token classifier, takes class-1 probabilities, merges subword decisions into words, and applies percentile/retention rules. Context-level filtering and forced context IDs provide another selection stage. This is lossy content deletion with a model-derived importance estimate, not a tokenizer trick. [L-ppl] [L-filter] [L-budget]

**Learned models and runtime.** The constructor defaults to a Llama-2-family 7B model and CUDA, but selects token-classification versus causal-LM classes from model configuration. The LLMLingua-2 test uses `microsoft/llmlingua-2-xlm-roberta-large-meetingbank` on **CPU**, so GPU is not a categorical requirement for that path. Package metadata requires Python >=3.8, Transformers >=4.26, Torch, Accelerate, NumPy, NLTK, and tiktoken, with loose upper bounds. The selected classifier model's registry card declares MIT and supplies a separately pinned model SHA in evidence; the code license alone must not be generalized to every alternative checkpoint. [L-load] [L-test] [L-deps] [model-microsoft__llmlingua-2-xlm-roberta-large-meetingbank] [license-llmlingua]

**Tests inspected.** `tests/test_llmlingua2.py:41–80` constructs the CPU classifier and asserts exact compressed strings, counts, ratios, and retained percentages for one- and multiple-context cases. This is useful deterministic regression evidence, but it does not establish downstream answer correctness, current billed savings, or robustness across dependency upgrades. Model downloads and execution were not attempted. [L-test]

**Economics and failure modes.** The requested token target is converted into a retention rate, and final text is re-tokenized. Forced words, tokenization differences, chunking, and percentile ties mean it should not be treated as a strict downstream-provider token guarantee. **Inference:** dropping a negation, variable name, code delimiter, citation relationship, or constraint may create a much larger retry/error cost than the saved prompt tokens. Treat instructions, tool schemas, exact identifiers, and security boundaries as protected material; evaluate compressible prose separately. [L-budget] [L-filter] [L-cost]

**Maintenance/security.** PyPI/GitHub release 0.2.2 remains from April 9, 2024, while default-branch activity reaches September 10, 2026; the latest sampled commit pins workflow actions. This demonstrates recent maintenance but not continuous algorithm releases. Default remote-code trust and `eval("target_token" + context_budget)` are directly observable risks if configuration is untrusted. **Mitigation:** audit/pin model artifacts, disable remote code when the chosen checkpoint permits it, never expose the expression field as arbitrary user input, and isolate compression behind a reversible adapter. The bug-report sample about Transformers `past_key_values` has no owner/member/collaborator response in the retrieved comments; it is an unresolved compatibility signal, not our verified bug. [commits-llmlingua] [pypi-llmlingua] [L-load] [L-eval] [comments-llmlingua]

**Decision:** evaluate the LLMLingua-2 approach first among these compressors, anchored to **0.2.2 plus an explicitly selected audited source/model revision**. Do not silently assume default-branch changes ship in 0.2.2. Stop adoption if workload quality or net cost fails its gate.

### 2. Selective Context — simple historical baseline; licensing and maintenance gates

**Observed algorithm.** GPT-2 supplies next-token probabilities; the code computes negative log probability, aggregates informativeness into sentences/phrases/tokens, and removes units below a percentile. English noun phrases use spaCy noun-chunk merging. Selection is based on model surprisal, not a query-conditioned guarantee that removed content is irrelevant. The output is concatenated retained text plus removed units. [S-load] [S-units] [S-filter]

**Runtime.** Python >=3.7 is declared, with Torch/Transformers/NLTK/NumPy and old exact pins `spacy==3.2.0`, `click==8.0.4`. Model loading supports English GPT-2 and a Chinese GPT-2 model, and contains a legacy Curie branch. Local scoring requires model artifacts and spaCy language resources; it is not a dependency-free preprocessor. The GPT-2 registry card is MIT, but that does not repair ambiguity in this project's source-license grant. [S-deps] [S-load] [model-openai-community__gpt2]

**Tests/evaluation gap.** The complete 33-entry archive inventory contains no test-named Python suite or tests directory. This absence is recorded rather than inventing test coverage. I inspected `main.py:30–109`: it iterates no-compression, self-information, and random baselines across ratios/tasks, obtains answers, and only invokes metrics under `do_eval`, which is set false in that file. This is an experiment harness, **not a passing regression suite**. [S-evaluation] The machine-readable inventory is `metadata/liyucheng09__Selective_Context/snapshot.json`.

**Maintenance/license.** Latest default-branch commit is February 12, 2024. GitHub detects no license and the snapshot contains no LICENSE/COPYING file; `pyproject.toml` advertises an MIT classifier, which is weaker evidence than an actual license text. **Mitigation:** do not copy/adopt source until rights are clarified. The inspected context-limit issue has community-only comments; do not assume it is maintained or fully compatible with a current Python/Torch/spaCy stack. [commits-selective] [repo-selective] [S-deps] [comments-selective]

**Failure modes and decision.** Context-length overflow, sentence segmentation, lexical alignment, code/URL damage, and semantic inversion are relevant test targets inferred from the algorithm. It also lacks a downstream tokenizer-budget guarantee. Use it to understand and benchmark a cheap surprisal baseline, not as the preferred production dependency. No endpoint/model compatibility for its legacy remote path was verified. [S-load] [S-units] [S-filter]

### 3. RouteLLM — direct cost-layer match, but a research-era implementation

**Observed algorithm.** A router estimates a strong-model win score and chooses the strong model when it reaches a configurable threshold; otherwise it chooses the weak model. The matrix-factorization implementation combines a learned model embedding with a projected prompt embedding, scores the pair, and applies a sigmoid to the score difference. The prompt embedding is fetched through an embedding provider call. Other included routers do not all have the same overhead profile. [R-threshold] [R-mf] [R-models]

**Integration boundary.** The controller preserves an OpenAI-shaped completion interface and forwards the selected model to LiteLLM, but the routing input is just `messages[-1]["content"]`. A “cost threshold” is a quality-score cutoff, not a dollar-denominated cap, and calibration to the percentage of strong-model calls does not constrain their token lengths. Existing trained scoring pairs use 2024-era models; applying them to a new serving pair requires evidence, not simply changing names. [R-route] [R-threshold] [R-calibrate] [R-models]

**Runtime/license.** PyPI is 0.2.0, with no `requires_python` declaration. The manifest includes Torch, Transformers, datasets, pandas, scikit-learn, OpenAI, LiteLLM, and NumPy <2; serving and evaluation add more dependencies. The matrix-factorization implementation chooses CUDA if available and otherwise CPU. Code is Apache-2.0. The retrieved `routellm/mf_gpt4_augmented` registry metadata did not provide a license value; treat checkpoint-use rights as unresolved rather than inheriting the repository license automatically. [pypi-routellm] [R-deps] [R-models] [license-routellm] [model-routellm__mf_gpt4_augmented]

**Tests/quality.** The two inspected `tests/` files are command-line smoke clients that make real completion requests and print output; they do **not** assert router calibration or a quality/cost bound. A static inconsistency also appears: the calibration script's generation branch passes `routed_pair=None`, while `Controller.__init__` requires `strong_model` and `weak_model` and does not accept that keyword. This likely fails if executed, but was not run. [R-test] [R-server-test] [R-calibrate] [R-constructor]

**Maintenance/failure modes.** Default-branch head is August 10, 2024; the latest PyPI release is July 8, 2024. The sampled later issue closed with only an unassociated community reply; no maintainer SLA follows. Main risks are distribution drift, last-turn-only routing, tool/multimodal incompatibility, score-pair mismatch, synchronous router work inside the async completion path, and embedding privacy/cost/latency. **Mitigation:** use as a reference, fit/calibrate on the actual model pair and conversation distribution, explicitly account for router calls, retain direct-model fallback, and verify provider parameter parity. [commits-routellm] [pypi-routellm] [comments-routellm] [R-route] [R-mf] [R-models]

**Decision:** good algorithmic reference, weak case for unqualified new dependency adoption. Compare calibrated routing against a simple fixed-model baseline and a simpler deterministic policy before taking on this frozen dependency tree.

### 4. mem0 — useful memory lifecycle, not a ready-made token budget optimizer

**Observed current implementation.** `infer=False` embeds raw non-system messages and stores them directly. With inference enabled, the inspected code obtains recent messages, embeds the new conversation for retrieval, retrieves ten existing memories, makes **one extraction LLM call**, batch-embeds extracted texts, and deduplicates by content hash before insertion. Do not repeat older descriptions that assume this path always makes separate extraction and update/delete LLM calls. [N-add] [N-extract]

**Retrieval.** Search defaults to `top_k=20` and threshold 0.1, requires a user/agent/run scope in filters, over-fetches semantic results with `max(limit*4,60)`, consults keyword search, computes entity boosts, and passes the candidates to ranking. Optional reranking adds another configured operation. This limits records, not tokenizer cost, and the candidate set in this inspected path is built from semantic results. A caller still needs token-aware packing and protected recent context. [N-search] [N-scope] [N-rank]

**Runtime/permissions.** Python package 2.2.1 requires >=3.10,<4; core dependencies include Qdrant client, Pydantic, OpenAI, HTTPX, PostHog, SQLAlchemy, and protobuf. Other providers/stores and local embedding models are optional. No local GPU is inherent to using remote LLM/embedding providers, but those calls and persistent vector/history storage are additional operational and data-permission boundaries. Telemetry is enabled by default and records operation/configuration data; review or disable it before processing sensitive material. Code is Apache-2.0; hosted-platform service terms are a separate matter. [N-deps] [N-add] [N-telemetry] [N-telemetry-data] [license-mem0]

**Tests inspected.** Regression assertions ensure `infer=False` embeds only once and inferred insertion uses one query embedding plus one batch embedding, guarding against duplicated spend. Another test rejects top-level `user_id` in search, requiring the filter interface. These are mocks, not an empirical memory-quality or billing evaluation. [N-tests] [N-test-scope]

**Important benchmark limitation.** The April 2026 README table reports LoCoMo **92.5, 7.0K tokens, 0.88s p50**, but explicitly says the figures reflect the managed platform and proprietary optimizations absent from OSS. It also describes a `top_200` evaluation retrieval budget, unlike the inspected method's default 20. Do not transpose those numbers onto this SDK or compare them to another repo's unrelated benchmark. [N-claims] [N-search]

**Risks/decision.** Inference: accumulating facts can retain stale/conflicting claims; an extracted fact can be wrong or attacker-influenced; scope IDs must come from authorization, not arbitrary client input. Content-hash deduplication is not semantic reconciliation. Memory writes, embeddings, reranking, and database operations may cost more than avoided history, especially for short or one-off conversations. Use only if repeated useful retrieval amortizes those costs. Keep provenance, original events, expiry/deletion, and rollback behavior; do not let remembered text become higher-trust instructions. The current source/release distinction and the inspected API change require a migration test, not a transparent drop-in assumption. [N-extract] [N-scope] [N-rank] [N-test-scope]

### 5. Outlines — retain only as a conditional output/retry-economics candidate

**Why included.** If many calls waste tokens repairing invalid JSON or emit avoidable formatting, constrained generation is economically relevant. If the workload already uses reliable provider-native schemas and does not retry, this is not a material prompt-cost optimization. That conditional relevance, not its stars, earns its place here. [O-provider] [O-test]

**Two distinct paths.** For local steerable models, the Outlines Core backend turns a JSON schema into a regex/index and applies token bitmasks as generation advances. For its OpenAI adapter, it sends native `response_format` options; it does not locally control the remote model's logits. The inspected adapter rejects regex and CFG output types and distinguishes JSON mode from strict JSON schema. These are statements about this adapter's pinned implementation, **not a universal claim about every provider's current capabilities**. [O-grammar] [O-mask] [O-provider]

**Runtime/quality.** Outlines 1.3.3 declares Python >=3.10,<3.14, Pydantic 2+, JSON Schema tooling, diskcache/cloudpickle, and `outlines_core==0.2.14`. Provider and local-runtime integrations are optional extras. API use need not require a local GPU; local decoding needs a supported model runtime. Apache-2.0 covers the library; model weights retain their own terms. Type-adapter tests assert unsupported-type errors and strict-schema construction; backend tests assert generated sequences match regexes. A regression test checks that the whitespace option actually reaches schema compilation. [O-deps] [O-test] [O-test-backend] [O-test-whitespace] [license-outlines]

**Failure modes/decision.** A syntactically valid answer can still be wrong. Schemas add request material; a permissive schema may not reduce output length; constraints may add compilation/masking cost. The provider wrapper returns text and raises on refusal, so the caller needs to preserve usage telemetry at the provider-client layer rather than assuming returned text carries billing details. The vLLM advisory concerning unbounded regex compilation in Outlines/XGrammar backends is a concrete integration warning, not proof that current standalone Outlines 1.3.3 is affected by that exact advisory. Bound grammar complexity, compilation time, output length, and retry count. Adopt only if measured cost per accepted result improves over the already-selected provider's native interface. [O-call] [O-provider] [O-grammar] [GHSA-rwxx-mrjm-wc2m]

### 6. vLLM — inference-server baseline, not an API-client token reducer

**Observed mechanism.** Prefix-cache keys chain a preceding-block hash, current token IDs, and extra keys. Extra keys include multimodal identity, LoRA identity, cache salt, and prompt embeddings where applicable. The cache manager finds the longest reusable full-block prefix. Even an apparent full prompt hit needs last-token computation to obtain logits and can therefore trigger block-level recomputation. This is a much stronger model of reuse than “same number of prompt tokens means same work.” [V-hash] [V-salt] [V-cache]

**Tests inspected.** `test_cache_key_salting` constructs requests with identical token prefixes and asserts a **48-token hit with the same salt** and **zero hit with a different salt**, while checking the chained hashes. This directly supports tenant-namespace test design. It does not measure API invoice savings. The source also exposes a prefix-cache reset for changed weights or benchmarking. [V-test] [V-reset]

**Runtime/maintenance.** Current distribution is 0.30.0, with Python >=3.10,<3.15. The inspected default-branch build pins Torch 2.13.0; this is not a blanket compatibility promise for the release wheel. This layer owns model loading, serving, accelerator/CPU backend selection, process resources, and network exposure; the package is not a no-GPU client-side add-on. Frequent releases and an October 4 head demonstrate active maintenance, not universal stability for every model/backend/quantization combination. Apache-2.0 applies to code. [pypi-vllm] [V-deps] [commits-vllm] [release-vllm] [license-vllm]

**Economics and risks.** Upstream explicitly distinguishes prefill benefit from decode time: prefix caching principally helps reused prefixes, not long generations with little shared input. Inference: owned-server savings depend on utilization, cache residency, concurrency, transfer overhead, accelerator pricing, and quality; no provider billing discount can be inferred from this engine. Multi-tenant cache correctness/security must be validated alongside throughput. [V-limit] [V-cache] [V-test]

**Security gate.** The repository advisory endpoint returned **86 published advisories** at retrieval, including historical auth, RCE, resource-exhaustion, hash/caching, and multi-tenant issues; this is neither a count of currently vulnerable releases nor a cross-project safety ranking. Two particularly relevant advisories concern LMCache-MP salt validation and salt loss on Harmony tool continuations. The former has an internally inconsistent patched-version string (`>= 30.0.0` against affected `< 0.30.0`); preserve that conflict and verify the fix/release artifact rather than silently normalizing it. [advisories-vllm] [GHSA-2823-qmq8-rwvj] [GHSA-935w-9g4m-p28p]

**Decision:** use 0.30.0 as a **candidate baseline version**, subject to exact model/backend security and correctness validation, not an unconditional safe-version endorsement.

### 7. SGLang — alternative server/reuse implementation, not another prompt compressor

**Observed mechanism.** The inspected radix cache matches token-ID prefixes with explicit namespace metadata and cache salts, rounds to page boundaries, splits tree nodes when a match ends inside one, and returns KV indices. Eviction selects eligible leaves by a configured priority and frees their KV segments. The newer unified cache has corresponding match/insert/evict entrypoints; an LMCache integration propagates namespace data through a connector. This shows that LMCache can be a layer beneath a server, not just a competing “same-feature” product. The classic radix implementation is a inspected reference path, not a claim that every configuration selects it by default. [G-namespace] [G-cache] [G-match] [G-evict] [G-unified] [G-lmcache]

**Tests inspected.** Unit tests verify full/partial prefix matches and independent isolation of cache salt and extra key, including deliberately ambiguous concatenation-like pairs (`a`+`bc` versus `ab`+`c`). A server test runs eight clients for six rounds and is registered for CUDA, AMD, and CPU CI. Its shared harness captures cached tokens, TTFT, total latency, and output IDs separately. This is a strong measurement pattern; it was not run here. [G-test] [G-test-salt] [G-test-e2e] [G-metrics]

**Runtime/maintenance.** Current release is 0.5.21, GitHub-published October 2, 2026; PyPI uploaded it October 1. Python >=3.10 is declared. The inspected main-branch manifest pins Torch 2.14.1, Transformers 5.17.0, SGLang kernel 0.4.9 and several accelerator libraries, illustrating how tightly runtime compatibility can be coupled. Upstream lists multiple GPU, CPU and other hardware paths, but that is not evidence that every path supports the same cache features. Head and issue/CI activity are current; code is Apache-2.0. [release-sglang] [pypi-sglang] [G-deps] [G-platforms] [commits-sglang] [comments-sglang] [license-sglang]

**Risks/decision.** Inference: cache eviction, hybrid model state, speculative execution, page sizing, hardware kernels, and namespace propagation can change correctness and economics. Keep tenants isolated even when that sacrifices cross-tenant hits. Compare it to vLLM on the same model, quantization, workload, hardware, concurrency, and cold/warm protocol. Do not combine their advertised gains or select one by stars alone. **0.5.21 is an evaluation anchor**, not a tested drop-in for local code. [G-cache] [G-namespace] [G-test-salt] [V-test]

### 8. LMCache — evaluate after a server baseline proves reusable context

**Observed mechanism.** Fixed-size token chunks produce chained prefix hashes and keys containing model name, worker/world-size information, dtype, and request configuration. A separate segment mode splits at a special token separator and hashes segments independently; non-prefix reuse therefore must not be conflated with ordinary exact prefix reuse. The cache engine retrieves KV objects into the serving engine through a GPU connector, with health checks and reference/pin lifecycle management. Upstream's non-prefix CacheBlend description explicitly includes selective recomputation for quality recovery. [K-hash] [K-chunk] [K-segment] [K-independent] [K-retrieve] [K-claims]

**Tests inspected.** Prefix retrieval tests compare recovered KV values when equality checking is enabled. For the `remote_cachegen` branch, that equality check is explicitly disabled; do not claim all compression modes are bitwise lossless from this test. Other inspected tests truncate the retrieval mask after a failed chunk and assert correct handling of byte-valued hashes. These are useful correctness surfaces beyond README speed claims. [K-test] [K-test-equality] [K-test-failure] [K-test-hash]

**Runtime/compatibility.** PyPI and designated stable release are 0.5.5. The pinned manifest declares Linux/GPU orientation, Python >=3.10,<3.14, and a Torch 2.13.0 build requirement. Runtime requirements deliberately leave Torch unpinned and explain that this avoids overriding a serving engine's installation; this does **not** establish ABI compatibility. The installation prose still says Python 3.9–3.13, conflicting with package metadata. Use artifact metadata as the resolver gate and validate the exact engine/Torch/CUDA-or-other-runtime tuple. Code is Apache-2.0. [pypi-lmcache] [release-lmcache] [K-deps] [K-runtime] [K-install] [license-lmcache]

**Permissions/failure modes.** This layer handles inference-state data in host memory, local disk, or remote storage and needs connector/storage access. Inference: cache contents and transport require confidentiality, authorization, invalidation when model/configuration changes, and disciplined namespace handling. It is not safe to share merely because visible text matches. Slow transfers, storage misses, partial reads, pin leaks, and cache churn can erase prefill savings; avoid treating a storage hit as a successful useful onload. The inspected implementation explicitly separates required/retrieved tokens, bytes, and timing, including overlap. [K-hash] [K-retrieve] [K-count] [K-test-failure]

**Decision:** evaluate **0.5.5 with a verified server/runtime tuple**, not a blind “latest” install. Use only after warm-prefix experiments show offload/reload is cheaper than recomputation and tenant/model boundaries are correct. The current default branch is `dev`, so its source findings cannot automatically be attributed to stable 0.5.5. [repo-lmcache] [release-lmcache]

## Maintenance, issue responsiveness, and security interpretation

Commit/release dates and popularity counts are observations, not support guarantees. LLMLingua, Selective Context, and RouteLLM have release-age concerns; LMCache, vLLM, SGLang, and mem0 have visibly active but changing surfaces; Outlines has a recent release but its default-branch last commit is older than repository `pushed_at`. Keep those signals separate. [commits-llmlingua] [commits-selective] [commits-routellm] [commits-lmcache] [commits-vllm] [commits-sglang] [commits-mem0] [commits-outlines] [repo-outlines]

One issue/comment thread per project was inspected as a **non-representative convenience sample**:

| Candidate | Inspected issue | What the sample supports |
|---|---|---|
| LLMLingua | #232 | Compatibility report; retrieved comment is community-only. [comments-llmlingua] |
| Selective Context | #34 | Context-limit discussion; community replies, no owner/member/collaborator reply observed. [comments-selective] |
| RouteLLM | #83 | Closed issue, but its one retrieved comment is not maintainer-associated; closure is not a support guarantee. [comments-routellm] |
| LMCache | #5454 | Recent technical discussion and proposed PR; comment associations do not establish maintainer response. [comments-lmcache] |
| vLLM | #53912 | Active multi-week contributor/community discussion; several evolving explanations, not one verified defect/fix. [comments-vllm] |
| SGLang | #17050 | Collaborator-associated CI triage and fix tracking; not a general user-issue response-time estimate. [comments-sglang] |
| mem0 | #7516 | Competing community fix claims/proposals; do not treat “fixed on main” in a comment as proven. [comments-mem0] |
| Outlines | #2049 | Recent community reproduction discussion and PR references; no maintainer-associated reply in this sample. [comments-outlines] |

The public repository-advisory endpoint returned zero entries for the other seven projects. **Zero published repository advisories is not “no vulnerabilities,” a clean dependency scan, or evidence they are safer than vLLM.** Transitive dependency advisories, unpublished issues, model artifacts, and all service deployments remain outside this audit. Security-sensitive decisions must include exact artifact and runtime inventories. [advisories-llmlingua] [advisories-selective] [advisories-routellm] [advisories-lmcache] [advisories-sglang] [advisories-mem0] [advisories-outlines]

## Reported savings versus measured evidence

**No performance, quality, energy, or dollar saving was measured in this study.** Reading an assertion is not running it; downloading a benchmark harness is not reproducing a paper.

| Evidence | Upstream statement or observed behavior | What may be concluded |
|---|---|---|
| LLMLingua README | Up to 20x compression; LLMLingua-2 described as 3–6x faster than LLMLingua. [L-claims] | Author-reported, workload-specific claims; neither an invoice result nor our reproduction. |
| LLMLingua tests | A test asserts 98 original and 30 compressed tokens. [L-test] | Expected test output under its model/tokenizer, not a successful run here. |
| Selective Context | README says 2x more content; repository metadata additionally claims memory/GPU savings. [S-claims] [repo-selective] | Historical author claims, not current end-to-end measurements. |
| RouteLLM README | Up to 85% cost reduction while retaining 95% GPT-4 performance on cited benchmarks. [R-claims] | Benchmark- and price-era-specific author claim; routing embedding cost, new models and task distribution must be remeasured. |
| mem0 README | Current managed-platform benchmark table; explicit proprietary-optimization caveat. [N-claims] | Not an OSS parity claim; do not reuse older generic token-saving percentages. |
| KV-cache code/tests | Reuse and isolation mechanisms, masked partial failures, and separate latency/cache metrics. [V-test] [G-metrics] [K-test-failure] | Mechanistic and test-design evidence, not achieved speedup or billed cost. |
| Outlines | Schema/regex constraints and assertions. [O-test] [O-test-backend] | Format enforcement evidence, not proof of fewer total tokens or retries in a target workload. |

## Proposed economic measurement contract

This is a **recommended study design**, not an implemented accounting system and not an analysis of TokenMaster.

### Keep the quantities distinct

1. **Transport bytes:** JSON encoding, whitespace, and network compression. A smaller packet alone does not establish fewer tokenizer tokens or lower charges.
2. **Tokenizer estimate:** original/transformed prompt, exact tokenizer identity/version, output estimate, and protected versus compressible segments.
3. **Provider-reported usage:** model/version, uncached input, cache-read input, cache creation/write where applicable, output, and any additional provider-defined categories. Reconcile categories to avoid counting cached input or reasoning tokens twice.
4. **Logical inference work:** local prefix hit, externally retrieved KV, overlapping pages, actual newly computed prefill, decode tokens, transfer bytes/time, cache eviction and retry.
5. **End-to-end outcome:** accepted-task cost and latency, not just one request's tokens, an internal compression ratio, or first-token latency.

These distinctions are motivated by the inspected tokenizer-specific estimator, routing call graph, memory lifecycle, cache overlap, and streaming metrics. [L-cost] [R-mf] [N-add] [K-count] [G-metrics]

Use a bookkeeping identity such as:

```text
total cost for a task =
    sum(actual billable provider usage categories × applicable unit rates)
  + router/compressor/extractor/embedder/reranker costs
  + allocated serving + storage + transfer costs
  + retries, fallbacks, repairs, and failed attempts
```

Allocate shared infrastructure once; do not double-count a cost already included in a provider bill or another overhead category. Report **cost per accepted task**, acceptance/quality rate, and latency distributions together. For a lossy transform, “quality unchanged” needs task-specific evidence rather than a single aggregate similarity score.

### Bounded experiments for the leader

- **Compression:** compare no transform, a deterministic selection baseline, Selective Context as a historical algorithm baseline if rights/runtime permit, and LLMLingua-2. Include negation, numbers, entity relations, code, tool schemas, long documents, and multilingual input. Measure preprocessing plus completion; retokenize the final payload using the target provider/model's applicable accounting.
- **Routing:** compare fixed strong model, fixed cheap model, simple policy, and calibrated learned routing. Include multi-turn follow-ups and tools; count embedding/router calls and fallbacks. Calibration target should concern accepted-task cost/quality, not just strong-call fraction.
- **Memory:** compare full transcript, bounded recent history, deterministic retrieval/packing, and extracted memory. Include updates, contradictions, deletions, tenant separation, and cold-start. Charge ingestion cost over a declared reuse horizon rather than hiding it outside the benchmark window.
- **Output constraints:** compare native provider schema support first, then an adapter/local constraint backend if needed. Track invalid-format rate, refusal/truncation, repairs, schema token overhead, actual completion length, and compile/mask latency.
- **Serving/KV:** use identical weights/revisions, tokenizer, quantization, hardware, model configuration and load. Measure cold and warm operation, independent versus repeated prefixes, eviction pressure, multi-tenant isolation, and long-output workloads. Establish vLLM/SGLang baselines before adding LMCache.
- **Composition:** run ablations. Compression can destroy exact-prefix reuse; routing can split cache locality across models; retrieval order can change prefixes; stricter tenant separation deliberately reduces shared hits. These interactions are inferences from the inspected keying and transformation code, not measured results. [L-filter] [R-route] [V-hash] [G-namespace] [K-chunk] [N-rank]

**Adoption gate:** choose quality and cost/latency thresholds before experimenting; require reproducible net benefit after all overhead and acceptable tail behavior. Stop or roll back a candidate when a protected-content, isolation, licensing, reproducibility, or correctness gate fails.

## Migration path and handoffs

No replacement or implementation was approved in this slice.

1. **Leader / explore:** map local request assembly, token estimates, usage ingestion, retries, provider caches, model routing, memory stores, and test coverage. This report deliberately does not assert any local integration point.
2. **Researcher:** confirm the exact chosen provider's current billing categories, cache rules, structured-output behavior, and runtime compatibility documentation once a candidate is selected.
3. **Dependency decision:** pin both package artifacts and model/tokenizer revisions; check licenses and transitive advisories. Do not substitute a moving branch for a release artifact without a deliberate compatibility decision.
4. **Executor only after approval:** put a reversible adapter/feature switch around a single mechanism; retain the original request and direct-model path for rollback. For memory, use a separate collection/schema version and retain raw events; for KV reuse, invalidate state after weight/configuration changes.
5. **Verifier:** run the predefined ablation/quality suite and usage reconciliation; no upstream marketing percentage becomes an acceptance criterion by itself.

Externally visible migration issues already identified: mem0 search scope uses `filters` rather than top-level IDs; RouteLLM's last-message extraction and model-pair scoring require explicit conversational checks; Outlines' provider adapter accepts fewer constraint forms than local backends; LMCache and inference engines require matched artifact/runtime combinations. [N-test-scope] [R-route] [R-models] [O-provider] [K-deps] [K-runtime] [G-deps] [V-deps]

## Pinned full source SHAs

| Upstream | Inspected default-branch full SHA | Commit timestamp (UTC) |
|---|---|---|
| microsoft/LLMLingua | `5a4c78ae18ab17a98cf997e8259354e546081d64` [commits-llmlingua] | 2026-09-10T23:36:23Z |
| liyucheng09/Selective_Context | `3074343653bbf3559a87a588667e843744bc6f2a` [commits-selective] | 2024-02-12T22:49:09Z |
| lm-sys/RouteLLM | `0b64fdafe049e596a3f5657c219329f24af24198` [commits-routellm] | 2024-08-10T19:10:15Z |
| LMCache/LMCache | `3efdd261c4ff37194031f64ea6deee42ff9379a0` [commits-lmcache] | 2026-10-04T08:42:19Z |
| vllm-project/vllm | `155488d853a0bc42df227dbfc74005b3fd488e94` [commits-vllm] | 2026-10-04T17:07:46Z |
| sgl-project/sglang | `bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b` [commits-sglang] | 2026-10-04T19:51:22Z |
| mem0ai/mem0 | `abb81c88e1f738a8117d8293530fbc31a5ef8fd9` [commits-mem0] | 2026-10-01T16:16:18Z |
| dottxt-ai/outlines | `c52af8472c6fe8a607a733ec11b709476af77a96` [commits-outlines] | 2026-08-24T14:20:14Z |

## Artifacts and validation

All artifacts are under:

`C:\Users\shyamsridhar\code\TokenMaster\docs\research\2026-10-04-token-economics\oss\`

- `REPORT.md` — this report.
- `evidence.json` — normalized metadata, classification, cross-cutting claims, source URLs, issue-sample caveats, and evidence boundaries.
- `source-files.json` — byte hashes, full SHAs, file/line metadata, original URLs, and absolute paths of the selected source snapshots.
- `metadata/` — timestamped raw GitHub/PyPI/model-registry responses and archive inventories.
- `sources/` — selected upstream implementation, tests, manifests, and license files; never executed.
- `snapshots/` — eight pinned compressed upstream archives.
- `validation.json` — artifact integrity and citation-range checks only; explicitly **not** upstream test results.

Limitations remain explicit: Selective Context has no discovered test suite and ambiguous source-license evidence; RouteLLM tests are live smoke scripts; current wheel-to-head equivalence and target-runtime compatibility were not established; no workload economics or provider prices were measured; advisory collection is not a full supply-chain audit.

## Sources

Source references below resolve to official APIs or full-SHA upstream file/line permalinks. Raw responses preserve the October 4 retrieval state even when the live API later changes.

[L-filter]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/llmlingua/prompt_compressor.py#L2342-L2440
[R-route]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/controller.py#L105-L170
[N-add]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/mem0/memory/main.py#L881-L964
[O-mask]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/src/outlines/backends/outlines_core.py#L104-L173
[V-cache]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/vllm/v1/core/kv_cache_manager.py#L264-L321
[G-cache]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/sglang/srt/mem_cache/radix_cache.py#L355-L414
[K-retrieve]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/lmcache/v1/cache_engine.py#L801-L839
[S-filter]: https://github.com/liyucheng09/Selective_Context/blob/3074343653bbf3559a87a588667e843744bc6f2a/selective_context.py#L255-L310
[L-load]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/llmlingua/prompt_compressor.py#L71-L164
[L-cost]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/llmlingua/prompt_compressor.py#L924-L986
[K-count]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/lmcache/v1/cache_engine.py#L948-L997
[R-mf]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/routers/matrix_factorization/model.py#L74-L129
[N-extract]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/mem0/memory/main.py#L976-L1044
[N-search]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/mem0/memory/main.py#L1393-L1434
[N-rank]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/mem0/memory/main.py#L1642-L1701
[N-claims]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/README.md#L45-L63
[L-eval]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/llmlingua/prompt_compressor.py#L1173-L1201
[V-salt]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/vllm/v1/core/kv_cache_utils.py#L614-L652
[G-namespace]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/sglang/srt/mem_cache/radix_cache.py#L166-L247
[N-telemetry]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/mem0/memory/telemetry.py#L14-L23
[O-grammar]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/src/outlines/backends/outlines_core.py#L214-L251
[GHSA-rwxx-mrjm-wc2m]: https://github.com/vllm-project/vllm/security/advisories/GHSA-rwxx-mrjm-wc2m
[repo-llmlingua]: https://api.github.com/repos/microsoft/LLMLingua
[repo-selective]: https://api.github.com/repos/liyucheng09/Selective_Context
[repo-routellm]: https://api.github.com/repos/lm-sys/RouteLLM
[repo-lmcache]: https://api.github.com/repos/LMCache/LMCache
[repo-vllm]: https://api.github.com/repos/vllm-project/vllm
[repo-sglang]: https://api.github.com/repos/sgl-project/sglang
[repo-mem0]: https://api.github.com/repos/mem0ai/mem0
[repo-outlines]: https://api.github.com/repos/dottxt-ai/outlines
[pypi-llmlingua]: https://pypi.org/pypi/llmlingua/json
[commits-llmlingua]: https://api.github.com/repos/microsoft/LLMLingua/commits?per_page=5
[license-llmlingua]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/LICENSE
[pypi-selective]: https://pypi.org/pypi/selective-context/json
[commits-selective]: https://api.github.com/repos/liyucheng09/Selective_Context/commits?per_page=5
[S-deps]: https://github.com/liyucheng09/Selective_Context/blob/3074343653bbf3559a87a588667e843744bc6f2a/pyproject.toml#L4-L27
[pypi-routellm]: https://pypi.org/pypi/routellm/json
[commits-routellm]: https://api.github.com/repos/lm-sys/RouteLLM/commits?per_page=5
[license-routellm]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/LICENSE
[pypi-lmcache]: https://pypi.org/pypi/lmcache/json
[commits-lmcache]: https://api.github.com/repos/LMCache/LMCache/commits?per_page=5
[license-lmcache]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/LICENSE
[pypi-vllm]: https://pypi.org/pypi/vllm/json
[commits-vllm]: https://api.github.com/repos/vllm-project/vllm/commits?per_page=5
[license-vllm]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/LICENSE
[pypi-sglang]: https://pypi.org/pypi/sglang/json
[commits-sglang]: https://api.github.com/repos/sgl-project/sglang/commits?per_page=5
[license-sglang]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/LICENSE
[pypi-mem0]: https://pypi.org/pypi/mem0ai/json
[commits-mem0]: https://api.github.com/repos/mem0ai/mem0/commits?per_page=5
[license-mem0]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/LICENSE
[pypi-outlines]: https://pypi.org/pypi/outlines/json
[commits-outlines]: https://api.github.com/repos/dottxt-ai/outlines/commits?per_page=5
[license-outlines]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/LICENSE
[O-provider]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/src/outlines/models/openai.py#L141-L209
[R-deps]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/pyproject.toml#L5-L29
[berkeley-route]: https://api.github.com/repos/Berkeley/RouteLLM
[release-routellm]: https://api.github.com/repos/lm-sys/RouteLLM/releases/latest
[tokencut]: https://api.github.com/repos/microsoft/TokenCut
[tokencut-search]: https://api.github.com/search/repositories?q=TokenCut+user%3Amicrosoft
[tokencut-cv]: https://api.github.com/repos/YangtaoWANG95/TokenCut
[release-lmcache]: https://api.github.com/repos/LMCache/LMCache/releases/latest
[release-selective]: https://api.github.com/repos/liyucheng09/Selective_Context/releases/latest
[release-mem0]: https://api.github.com/repos/mem0ai/mem0/releases/latest
[L-ppl]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/llmlingua/prompt_compressor.py#L165-L210
[L-budget]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/llmlingua/prompt_compressor.py#L818-L867
[L-test]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/tests/test_llmlingua2.py#L41-L80
[L-deps]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/setup.py#L25-L68
[model-microsoft__llmlingua-2-xlm-roberta-large-meetingbank]: https://huggingface.co/api/models/microsoft/llmlingua-2-xlm-roberta-large-meetingbank
[comments-llmlingua]: https://api.github.com/repos/microsoft/LLMLingua/issues/232/comments?per_page=100
[S-load]: https://github.com/liyucheng09/Selective_Context/blob/3074343653bbf3559a87a588667e843744bc6f2a/selective_context.py#L37-L117
[S-units]: https://github.com/liyucheng09/Selective_Context/blob/3074343653bbf3559a87a588667e843744bc6f2a/selective_context.py#L165-L247
[model-openai-community__gpt2]: https://huggingface.co/api/models/openai-community/gpt2
[S-evaluation]: https://github.com/liyucheng09/Selective_Context/blob/3074343653bbf3559a87a588667e843744bc6f2a/main.py#L30-L109
[comments-selective]: https://api.github.com/repos/liyucheng09/Selective_Context/issues/34/comments?per_page=100
[R-threshold]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/routers/routers.py#L32-L45
[R-models]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/routers/routers.py#L210-L242
[R-calibrate]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/calibrate_threshold.py#L31-L58
[model-routellm__mf_gpt4_augmented]: https://huggingface.co/api/models/routellm/mf_gpt4_augmented
[R-test]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/tests/test_openai_client.py#L13-L53
[R-server-test]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/tests/test_openai_server.py#L11-L58
[R-constructor]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/controller.py#L42-L70
[comments-routellm]: https://api.github.com/repos/lm-sys/RouteLLM/issues/83/comments?per_page=100
[N-scope]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/mem0/memory/main.py#L1471-L1519
[N-deps]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/pyproject.toml#L5-L82
[N-telemetry-data]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/mem0/memory/telemetry.py#L192-L218
[N-tests]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/tests/test_memory.py#L682-L755
[N-test-scope]: https://github.com/mem0ai/mem0/blob/abb81c88e1f738a8117d8293530fbc31a5ef8fd9/tests/test_memory.py#L1115-L1126
[O-test]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/tests/models/test_openai_type_adapter.py#L134-L176
[O-deps]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/pyproject.toml#L5-L54
[O-test-backend]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/tests/backends/test_outlines_core.py#L83-L109
[O-test-whitespace]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/tests/backends/test_outlines_core.py#L284-L323
[O-call]: https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/src/outlines/models/openai.py#L263-L287
[V-hash]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/vllm/v1/core/kv_cache_utils.py#L684-L714
[V-test]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/tests/v1/core/test_prefix_caching.py#L3266-L3349
[V-reset]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/vllm/v1/core/kv_cache_manager.py#L674-L689
[V-deps]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/pyproject.toml#L1-L36
[release-vllm]: https://api.github.com/repos/vllm-project/vllm/releases/latest
[V-limit]: https://github.com/vllm-project/vllm/blob/155488d853a0bc42df227dbfc74005b3fd488e94/docs/features/automatic_prefix_caching.md#L38-L47
[advisories-vllm]: https://api.github.com/repos/vllm-project/vllm/security-advisories?per_page=100
[GHSA-2823-qmq8-rwvj]: https://github.com/vllm-project/vllm/security/advisories/GHSA-2823-qmq8-rwvj
[GHSA-935w-9g4m-p28p]: https://github.com/vllm-project/vllm/security/advisories/GHSA-935w-9g4m-p28p
[G-match]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/sglang/srt/mem_cache/radix_cache.py#L637-L676
[G-evict]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/sglang/srt/mem_cache/radix_cache.py#L551-L579
[G-unified]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/sglang/srt/mem_cache/unified_radix_cache.py#L557-L619
[G-lmcache]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/sglang/srt/mem_cache/storage/lmcache/lmcache_unified_radix_cache.py#L173-L207
[G-test]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/test/registered/unit/mem_cache/test_radix_cache_unit.py#L346-L380
[G-test-salt]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/test/registered/unit/mem_cache/test_radix_cache_unit.py#L661-L689
[G-test-e2e]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/test/registered/radix_cache/test_radix_cache_hit.py#L18-L49
[G-metrics]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/sglang/test/kits/cache_hit_kit.py#L50-L116
[release-sglang]: https://api.github.com/repos/sgl-project/sglang/releases/latest
[G-deps]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/python/pyproject.toml#L1-L100
[G-platforms]: https://github.com/sgl-project/sglang/blob/bab04cd7913ff50d1bf1a677a2d10e5015dc4c3b/README.md#L44-L58
[comments-sglang]: https://api.github.com/repos/sgl-project/sglang/issues/17050/comments?per_page=100
[K-hash]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/lmcache/v1/token_database.py#L234-L295
[K-chunk]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/lmcache/v1/token_database.py#L331-L445
[K-segment]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/lmcache/v1/token_database.py#L452-L468
[K-independent]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/lmcache/v1/token_database.py#L543-L562
[K-claims]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/README.md#L53-L79
[K-test]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/tests/v1/test_cache_engine.py#L155-L188
[K-test-equality]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/tests/v1/test_cache_engine.py#L234-L259
[K-test-failure]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/tests/v1/test_cache_engine.py#L1653-L1681
[K-test-hash]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/tests/v1/test_token_database.py#L135-L154
[K-deps]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/pyproject.toml#L1-L45
[K-runtime]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/requirements/common.txt#L1-L52
[K-install]: https://github.com/LMCache/LMCache/blob/3efdd261c4ff37194031f64ea6deee42ff9379a0/docs/source/getting_started/installation.rst#L3-L12
[comments-lmcache]: https://api.github.com/repos/LMCache/LMCache/issues/5454/comments?per_page=100
[comments-vllm]: https://api.github.com/repos/vllm-project/vllm/issues/53912/comments?per_page=100
[comments-mem0]: https://api.github.com/repos/mem0ai/mem0/issues/7516/comments?per_page=100
[comments-outlines]: https://api.github.com/repos/dottxt-ai/outlines/issues/2049/comments?per_page=100
[advisories-llmlingua]: https://api.github.com/repos/microsoft/LLMLingua/security-advisories?per_page=100
[advisories-selective]: https://api.github.com/repos/liyucheng09/Selective_Context/security-advisories?per_page=100
[advisories-routellm]: https://api.github.com/repos/lm-sys/RouteLLM/security-advisories?per_page=100
[advisories-lmcache]: https://api.github.com/repos/LMCache/LMCache/security-advisories?per_page=100
[advisories-sglang]: https://api.github.com/repos/sgl-project/sglang/security-advisories?per_page=100
[advisories-mem0]: https://api.github.com/repos/mem0ai/mem0/security-advisories?per_page=100
[advisories-outlines]: https://api.github.com/repos/dottxt-ai/outlines/security-advisories?per_page=100
[L-claims]: https://github.com/microsoft/LLMLingua/blob/5a4c78ae18ab17a98cf997e8259354e546081d64/README.md#L34-L48
[S-claims]: https://github.com/liyucheng09/Selective_Context/blob/3074343653bbf3559a87a588667e843744bc6f2a/readme.md#L1-L24
[R-claims]: https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/README.md#L10-L15

