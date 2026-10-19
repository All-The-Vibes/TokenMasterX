"""Eval-only relay for interactive Copilot CLI checks (functional, not a savings study).

Serves verify_bridge.Relay on 127.0.0.1:<port> for a fixed time, so that an interactive Copilot CLI session in a
terminal can reach the GitHub Copilot API through the TokenMaster bridge. Usage numbers go to relay-usage-<run>.jsonl;
request bodies stay in captures/<run>/ (local only).

  python serve_relay.py [run] [port] [minutes]
"""
import sys
import time

RUN_NAME = sys.argv[1] if len(sys.argv) > 1 else "tui"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 47815
MINUTES = float(sys.argv[3]) if len(sys.argv) > 3 else 20
sys.argv = [sys.argv[0], RUN_NAME]  # verify_bridge takes its run name from argv when it is imported
import verify_bridge as vb  # noqa: E402


def main():
    vb.tokens.count_tokens("warm-up")  # before any server thread
    vb.CAPTURES.mkdir(parents=True, exist_ok=True)
    vb.RELAY_LOG.unlink(missing_ok=True)
    with vb.Relay(vb.p1.load_copilot_token(), log=vb.RELAY_LOG, port=PORT) as relay:
        relay.label = RUN_NAME
        print(relay.url, flush=True)
        time.sleep(MINUTES * 60)


if __name__ == "__main__":
    main()
