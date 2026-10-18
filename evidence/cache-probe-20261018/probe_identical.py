"""Follow-up cache probe: can a byte-identical first request read the provider cache?

Re-sends the first request of PRS-3 session M01-stock-r1 three times through the study gateway:
F1 as captured, F2 byte-identical to F1, G identical except for a new prompt_cache_key.
Only usage numbers and body hashes are written; the request body stays local.
"""
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "token-master-plugin" / "evals"))
import run_prs1_study as p1  # noqa: E402

OUT = Path(__file__).resolve().parent
CAPTURE = ROOT / "evidence/prs3-20261018/study/runs/M01-stock-r1/session/captures.jsonl"


def send(port: int, body: bytes) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=90) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    row = {"status": status, "input": None, "cached": None, "cache_write": None}
    text = raw.decode("utf-8", "replace")
    at = text.rfind('"usage":')
    if status == 200 and at >= 0:
        usage, _ = json.JSONDecoder().raw_decode(text[at + len('"usage":'):])
        details = usage.get("input_tokens_details") or {}
        row.update(input=usage.get("input_tokens"), cached=details.get("cached_tokens"),
                   cache_write=details.get("cache_write_tokens"))
    return row


def main() -> None:
    first = json.loads(CAPTURE.read_text(encoding="utf-8").splitlines()[0])
    body = first["input"].encode("utf-8")
    other = json.loads(body)
    other["prompt_cache_key"] = hashlib.sha256(b"probe-k7").hexdigest()[:32]
    body_g = json.dumps(other, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    server = p1.start_gateway(p1.load_copilot_token(), OUT / "gateway.jsonl")
    port = server.server_address[1]
    rows = []
    for call, payload, note in [("F1", body, "captured M01-stock-r1 first request, original key"),
                                ("F2", body, "byte-identical to F1"),
                                ("G", body_g, "F1 with a new prompt_cache_key")]:
        row = {"call": call, "note": note, "body_sha256": hashlib.sha256(payload).hexdigest()[:16],
               **send(port, payload)}
        rows.append(row)
        print(json.dumps(row))
        time.sleep(3)
    server.shutdown()
    results = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    results["followup"] = {"date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "question": "Does a byte-identical first request read the cache, and does the key matter?",
                           "rows": rows}
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
