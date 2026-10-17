"""Build a revision-pinned evidence manifest from retrieved arXiv metadata."""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = json.loads((ROOT / "arxiv-metadata.raw.json").read_text(encoding="utf-8"))
BY_ID = {row["arxiv_id"]: row for row in RAW}

# key, identifier, selected version, class, inspected location, interface, narrow claim, caveat
RECORDS = [
    ("P01", "2310.06201", 1, "core", "Methods and experiments; efficiency and quality analyses", "text_api_plus_auxiliary_scorer",
     "50% context reduction; 36% inference-memory and 32% inference-time reduction; BERTScore -0.023 and faithfulness -0.038.",
     "Application/model-specific aggregate; not a task-correctness guarantee."),
    ("P02", "2310.05736", 2, "core", "Sections 4-5; Table 2", "text_api_plus_auxiliary_compressor",
     "GSM8K GPT-3.5-Turbo-0301: 2366 to 117 tokens, EM 78.85 to 77.33.",
     "Few-shot prompt compression; auxiliary alignment is not target retraining."),
    ("P03", "2310.06839", 2, "core", "Sections 4-5; Tables 1-2", "text_api_query_conditioned",
     "NQ 20 documents: 2946 to 748 tokens; position-10 54.1 to 71.2; reordered pipeline 75.5.",
     "The 21.4-point headline combines compression with reordering; ablate both."),
    ("P04", "2403.12968", 2, "core", "Sections 3-5; Tables 3, 5, 11; appendices", "text_api_trained_auxiliary_encoder",
     "LongBench 2000-token constraint: aggregate 39.1 at 1954 tokens versus LLMLingua 34.6 at 1950.",
     "Task-agnostic; benchmark aggregates and local V100 latency do not establish API latency."),
    ("P05", "2310.04408", 1, "core", "Sections 3-5; LM/QA settings and transfer results", "text_api_trained_auxiliary_compressor",
     "Trained LM compressors retain about 25%; QA retains 5-10%, with under 10% reported relative degradation.",
     "Do not conflate trained and oracle results, particularly the 6% headline."),
    ("P06", "2407.15504", 2, "core", "Sections 2-4; experiments; Appendices C-D", "framework_and_text_api_methods",
     "Exact rate-distortion curves in tractable settings; exhaustive curves infeasible for NarrativeQA-sized prompts.",
     "Optimality depends on source/query distribution, model, compressor, and distortion; toy experiments fine-tune models."),
    ("P07", "2408.10497", 3, "core", "Sections 3-4; Tables 1-2; Appendix F", "text_api_auxiliary_cross_attention",
     "Quoref, Llama-3-8B-Instruct, retained ratio .25: 86.8 EM versus full 93.1.",
     "Attention-based relevance is a surrogate; no universal retention certificate."),
    ("P08", "2307.03172", 3, "core", "Sections 2-3; Appendix G, Table 6", "black_box_evaluation",
     "GPT-3.5-Turbo 20-document QA: first 75.8, index-9 53.8, last 63.2.",
     "Historical model snapshots; position effect is not a present-model score prediction."),
    ("P09", "2404.06654", 3, "core", "Sections 3-6; Table 3", "black_box_evaluation",
     "13 tasks; GPT-4 96.6 at 4K, 87.0 at 64K, 81.2 at 128K.",
     "Effective length uses an 85.6 threshold and is benchmark-defined, not hardware capacity."),
    ("P10", "2502.05167", 3, "core", "Sections 3-5; Table 3; Appendices E-F", "black_box_evaluation",
     "GPT-4o base 99.3, 32K 69.7, effective length 8K at 85% of base.",
     "Synthetic non-literal associations and historical model snapshots; not complete application coverage."),
    ("P11", "2410.10813", 2, "core", "Sections 3-5; Figure 3; memory design analyses", "black_box_evaluation_stateful_memory",
     "500 questions; S about 115K tokens; Llama-3.1-8B oracle .710 versus full-history .420.",
     "Oracle retrieval is diagnostic; compression to user facts changes subgroup performance."),
    ("P12", "2602.07885", 3, "core", "Sections 2-3; Tables 1-2; implementation details and appendices", "text_api_stateful_memory_orchestration",
     "LoCoMo GPT-4o-mini average F1: MemCoRe 43.76, A-MEM 41.97, LoCoMo baseline 39.74.",
     "Title changed from MemFly; latest revision does not establish lower lifetime cost."),
    ("P13", "2304.08467", 3, "core", "PDF Sections 2-6; Table 3; limitations", "target_training_and_activation_interface",
     "Mean instruction cache 26 to 1 tokens; LLaMA full-cache comparison: .11% FLOPs and 1% wall-time savings.",
     "Single-forward-pass profiling; special-token text is not a learned activation; nuance may be lost."),
    ("P14", "2412.18547", 5, "core", "Sections 3-6; Tables 3-4", "EP_text_api_PT_training",
     "GSM8K 318.10 to 77.26 output tokens, 81.35 to 84.46 accuracy; college 78 to 70 accuracy.",
     "Table 3 caption conflicts with average row; task cells used, aggregate left unresolved."),
    ("P15", "2501.19393", 3, "core", "Sections 2-5; Tables 3-4; Appendices A-B, E", "target_training_and_decoding_control",
     "s1 AIME24 50.0 to 56.7 with four Wait extensions; budget forcing control 100% versus token prompting 40%.",
     "Not s1.1; small math benchmark and nondeterministic evaluation; output brevity is not equivalent."),
    ("P16", "2604.02985", 1, "core", "Sections 4.1-4.5; Figures 2-5", "text_api_and_server_evaluation",
     "Transformers gains in favorable settings; short vLLM inputs incur overhead; no reliable tested API speedup.",
     "Specific servers/endpoints; quality sometimes benefits because full baseline was truncated; not a universal claim."),
    ("B01", "2307.06945", 4, "boundary", "Sections 2-3, especially 3.3; memory-slot/training method", "trained_encoder_and_soft_embedding_interface",
     "512 context tokens to 128 memory slots; learned encoder, target LLM unchanged; span concatenation needs training exposure.",
     "Unchanged decoder weights do not imply a standard text-only API can receive the soft representation."),
    ("B02", "2402.02750", 2, "boundary", "Primary abstract and mechanism description", "serving_cache_precision_control",
     "KV quantization reduces numerical precision/storage, not submitted text.",
     "Mechanism-only review, no performance comparison or provider billing inference."),
    ("B03", "2306.14048", 3, "boundary", "Primary abstract and mechanism description", "serving_attention_and_cache_control",
     "KV eviction keeps recent and high-attention heavy-hitter states.",
     "Mechanism-only review; not prompt deletion or a semantic retention guarantee."),
    ("B04", "2211.17192", 2, "boundary", "Primary abstract and exact-sampling mechanism", "draft_target_decoding_coordination",
     "Exact speculative sampling preserves target distribution under algorithm assumptions; original T5-XXL reports 2-3x speedup.",
     "Not fewer semantic prompt/output tokens; no current endpoint compatibility claim."),
    ("H01", "2304.12102", 1, "precursor_metadata_only", "Version metadata only; not used for independent numeric corroboration", "not_assessed",
     "Earlier Selective Context-related preprint.",
     "Not the load-bearing EMNLP-era paper 2310.06201v1."),
]

sources = []
for key, aid, version, category, sections, control, claim, caveat in RECORDS:
    raw = BY_ID[aid]
    history = []
    for n, date in re.findall(r"\[v(\d+)\]\s+([^()]+?)\s+\(", raw["html_history_text"]):
        parsed = dt.datetime.strptime(date.strip(), "%a, %d %b %Y %H:%M:%S UTC").replace(tzinfo=dt.timezone.utc)
        history.append({"version": int(n), "submitted_at_utc": parsed.isoformat()})
    selected = next(h for h in history if h["version"] == version)
    assert selected["submitted_at_utc"][:10] <= "2026-10-04", key
    source = {
        "key": key,
        "category": category,
        "source_type": "primary_research_arxiv",
        "title_at_retrieval": raw["title"],
        "arxiv_id": aid,
        "selected_version": version,
        "selected_version_date": selected["submitted_at_utc"][:10],
        "selected_version_submitted_at_utc": selected["submitted_at_utc"],
        "first_submission_date": history[0]["submitted_at_utc"][:10],
        "abs_url": f"https://arxiv.org/abs/{aid}v{version}",
        "pdf_url": f"https://arxiv.org/pdf/{aid}v{version}",
        "html_url": f"https://arxiv.org/html/{aid}v{version}" if key != "P13" else None,
        "version_history_at_retrieval": history,
        "retrieved_at_utc": raw["retrieved_at_utc"],
        "metadata_html_sha256": raw["abs_html_sha256"],
        "inspected_sections": sections,
        "interface_classification_inference": control,
        "narrow_claim": claim,
        "limitations": caveat,
        "claim_status": "reported_not_reproduced" if category != "precursor_metadata_only" else "metadata_only",
        "venue_certification": "ArXiv revision verified; peer-review status is not used as a quality guarantee.",
    }
    if key == "P13":
        cache = ROOT / "gist-v3.research-cache.pdf"
        source["review_format"] = "PDF extracted with pre-existing pdftotext; HTML request returned HTTP 406."
        if cache.exists():
            source["reviewed_pdf_sha256"] = hashlib.sha256(cache.read_bytes()).hexdigest()
        elif (ROOT / "sources.json").exists():
            previous = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
            previous_gist = next(s for s in previous["sources"] if s["key"] == "P13")
            source["reviewed_pdf_sha256"] = previous_gist.get("reviewed_pdf_sha256")
    elif category == "boundary" and key != "B01":
        source["review_format"] = "versioned arXiv abstract; narrowly used for mechanism distinction"
    else:
        source["review_format"] = "versioned arXiv HTML and abstract metadata"
    sources.append(source)

manifest = {
    "research_title": "Task-level LLM token economics",
    "review_date": "2026-10-04",
    "timezone": "America/Chicago",
    "literature_cutoff": "2026-10-04",
    "scope": "Primary-paper research only; no repository analysis or benchmark reproduction.",
    "source_count": len(sources),
    "core_publication_count": sum(s["category"] == "core" for s in sources),
    "boundary_reference_count": sum(s["category"] == "boundary" for s in sources),
    "precursor_metadata_count": sum(s["category"] == "precursor_metadata_only" for s in sources),
    "latest_in_field_claim": False,
    "search_strategy": [
        "Search arXiv for requested seed papers, information bottleneck and rate-distortion compression.",
        "Follow primary citations on task-aware compression, learned latent interfaces, context evaluation, and memory.",
        "Search for 2026 compression evaluation and memory work; inspect selected full methods/evaluations.",
        "Verify revision histories directly from arXiv and pin claims to selected revisions.",
    ],
    "excluded_evidence": "No third-party summaries, repository-local claims, dependency rankings, or current pricing.",
    "known_ambiguities": [
        "TALE v5 Table 3 caption disagrees with its average row and task count.",
        "MemFly was renamed MemCoRe; old-version result headlines must not be mixed with v3 tables.",
        "Selective Context precursor and EMNLP-era paper use different arXiv identifiers.",
        "Compression speedup is sensitive to model/server/cache/output-length baselines.",
    ],
    "sources": sources,
}
(ROOT / "sources.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# Expand grouped citations into valid Markdown references.
memo = ROOT / "research-memo.md"
text = memo.read_text(encoding="utf-8")
def expand(match):
    group = match.group(1)
    items = []
    for part in group.split(", "):
        range_match = re.fullmatch(r"([PB])(\d{2})[–-]([PB])(\d{2})", part)
        if range_match:
            a, start, b, stop = range_match.groups()
            assert a == b
            items.extend(f"{a}{i:02d}" for i in range(int(start), int(stop)+1))
        else:
            items.append(part)
    return ", ".join(f"[{item}]" for item in items)
text = re.sub(r"\[((?:[PB]\d{2})(?:[–-][PB]\d{2})?(?:, [PB]\d{2}(?:[–-][PB]\d{2})?)*)\]",
              expand, text)
memo.write_text(text, encoding="utf-8")
print(f"Wrote {len(sources)} sources: {manifest['core_publication_count']} core, 4 boundary, 1 precursor.")
