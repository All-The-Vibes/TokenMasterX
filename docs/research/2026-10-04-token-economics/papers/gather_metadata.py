"""Read-only primary-source retrieval; writes only metadata beside this script."""
import datetime
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAPERS = {
    "LLMLingua": "2310.05736",
    "LongLLMLingua": "2310.06839",
    "LLMLingua-2": "2403.12968",
    "Selective Context precursor": "2304.12102",
    "Selective Context": "2310.06201",
    "Lost in the Middle": "2307.03172",
    "RULER": "2404.06654",
    "RECOMP": "2310.04408",
    "Rate-distortion prompt compression": "2407.15504",
    "QUITO-X": "2408.10497",
    "Gist tokens": "2304.08467",
    "LongMemEval": "2410.10813",
    "TALE": "2412.18547",
    "NoLiMa": "2502.05167",
    "MemCoRe (formerly MemFly)": "2602.07885",
    "Prompt Compression in the Wild": "2604.02985",
    "ICAE": "2307.06945",
    "s1": "2501.19393",
    "KIVI": "2402.02750",
    "H2O": "2306.14048",
    "Speculative decoding": "2211.17192",
}

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TokenEconomicsLiteratureReview/1.0"})
    return urllib.request.urlopen(req, timeout=50).read().decode("utf-8")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    output = []
    for label, paper_id in PAPERS.items():
        url = f"https://arxiv.org/abs/{paper_id}"
        try:
            page = fetch(url)
            meta = dict(re.findall(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"', page))
            section = page.split("Submission history", 1)[-1].split("</div>", 1)[0]
            history = re.sub("<[^>]+>", " ", section)
            history = html.unescape(re.sub(r"\s+", " ", history)).strip()
            row = {
                "label": label,
                "arxiv_id": paper_id,
                "title": html.unescape(meta.get("citation_title", "")),
                "canonical_abs_url": url,
                "latest_pdf_url_at_retrieval": meta.get("citation_pdf_url"),
                "first_submission_date": meta.get("citation_date"),
                "html_history_text": history,
                "retrieved_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "abs_html_sha256": hashlib.sha256(page.encode()).hexdigest(),
                "source_type": "primary_research_arxiv",
                "selection_rule": "Claims must use an explicitly reviewed version no later than 2026-10-04.",
            }
            output.append(row)
            print(label, paper_id, row["title"], history, flush=True)
        except Exception as exc:
            output.append({"label": label, "arxiv_id": paper_id, "error": str(exc)})
            print("ERROR", label, str(exc), flush=True)
        time.sleep(1.5)
    (ROOT / "arxiv-metadata.raw.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
