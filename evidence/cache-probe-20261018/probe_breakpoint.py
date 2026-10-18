"""Cache-breakpoint probe: is there a cache entry at the end of the system message, and does
moving the per-session folder path out of the system message let a new session's first call
read the shared prefix?

H1  = M01-stock-r1's first request with only the user message changed.
H3a = session folder s8: the folder path in the system message becomes a fixed placeholder and
      the real path moves to the start of the user message.
H3b = the same rewrite for session folder s9 with a different user message.
Only usage numbers and body hashes are written; the request bodies stay local.
"""
import copy
import hashlib
import json
import re
import time

from probe_identical import CAPTURE, OUT, p1, send

FOLDER = re.compile(r"C:/Users/dev/\.copilot/session-state/[0-9a-f]{32}")
PLACEHOLDER = "<session-folder>"


def edit_text(content, fn):
    if isinstance(content, str):
        return fn(content)
    return [{**part, "text": fn(part["text"])} if isinstance(part, dict) and "text" in part else part
            for part in content]


def with_user_suffix(body: dict, suffix: str) -> dict:
    out = copy.deepcopy(body)
    out["input"][1]["content"] = edit_text(out["input"][1]["content"], lambda t: t + suffix)
    return out


def stable_prefix(body: dict, folder_id: str, suffix: str) -> dict:
    out = copy.deepcopy(body)
    path = "C:/Users/dev/.copilot/session-state/" + hashlib.sha256(folder_id.encode()).hexdigest()[:32]
    out["input"][0]["content"] = edit_text(out["input"][0]["content"], lambda t: FOLDER.sub(PLACEHOLDER, t))
    out["input"][1]["content"] = edit_text(
        out["input"][1]["content"], lambda t: f"{PLACEHOLDER} is {path}\n\n" + t + suffix)
    return out


def main() -> None:
    body = json.loads(json.loads(CAPTURE.read_text(encoding="utf-8").splitlines()[0])["input"])
    assert len(FOLDER.findall(json.dumps(body["input"][0]))) == 1
    server = p1.start_gateway(p1.load_copilot_token(), OUT / "gateway.jsonl")
    port = server.server_address[1]
    rows = []
    for call, payload, note in [
            ("H1", with_user_suffix(body, "\nAnswer briefly."), "F1 with only the user message changed"),
            ("H3a", stable_prefix(body, "s8", ""), "folder path moved to the user message; session s8"),
            ("H3b", stable_prefix(body, "s9", "\nAnswer briefly."), "same rewrite; session s9, other user text")]:
        wire = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        row = {"call": call, "note": note, "body_sha256": hashlib.sha256(wire).hexdigest()[:16], **send(port, wire)}
        rows.append(row)
        print(json.dumps(row))
        time.sleep(3)
    server.shutdown()
    results = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    results["breakpoint"] = {"date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             "question": "Is there a cache entry at the end of the system message, and does a "
                                         "folder-free system message give a new session a cache hit?",
                             "rows": rows}
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
