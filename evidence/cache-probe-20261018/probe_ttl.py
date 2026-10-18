"""Cache-lifetime probe for the folder-free system message (see probe_breakpoint.py).

Each call is a new session (new folder, new user text) with the shared prefix. The waits are
measured from the previous call, which last used the prefix: about 6.5, 31 and 61 minutes.
Rows are appended to ttl.jsonl as they arrive.
"""
import json
import time

from probe_breakpoint import CAPTURE, OUT, p1, send, stable_prefix

WAITS = [390, 1860, 3660]


def main() -> None:
    body = json.loads(json.loads(CAPTURE.read_text(encoding="utf-8").splitlines()[0])["input"])
    server = p1.start_gateway(p1.load_copilot_token(), OUT / "gateway.jsonl")
    port = server.server_address[1]
    last = time.time()
    for n, wait in enumerate(WAITS):
        time.sleep(max(0.0, last + wait - time.time()))
        payload = stable_prefix(body, f"ttl-{n}", f"\nProbe {n}.")
        wire = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        started = time.time()
        row = {"call": f"T{n}", "seconds_since_last_use": round(started - last),
               "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)), **send(port, wire)}
        last = time.time()
        with (OUT / "ttl.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    server.shutdown()


if __name__ == "__main__":
    main()
