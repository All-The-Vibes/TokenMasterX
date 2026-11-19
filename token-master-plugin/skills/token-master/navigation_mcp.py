"""TokenMaster code navigation over MCP: locate, read_symbol and impact (v7).

Serves brainspace/symbol_index.py for the repository the host starts it in: exact
symbol ranges from a local SQLite index (.token-master/symbols.sqlite) plus graphify's
call graph (.token-master/graph.json, built by setup.py). Every result stays under
2,400 tokens. Measured in PRS-3: token-master-plugin/docs/PRS3_RESULTS.md.
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brainspace import repo_brief, symbol_index  # noqa: E402

SERVER_NAME = "tokenmaster-nav"
DESCRIPTIONS = {spec["name"]: spec["description"] for spec in symbol_index.TOOL_SPECS}


def make_server(root: Path, *, class_skeleton: bool | str | None = None):
    from mcp.server.fastmcp import FastMCP

    mode = symbol_index._resolve_class_read_mode(class_skeleton)
    server = FastMCP(SERVER_NAME)
    lock = threading.Lock()
    state: dict[str, symbol_index.SymbolIndex] = {}

    def run(name: str, arguments: dict) -> str:
        with lock:  # one SQLite connection, built on first use so host startup never waits
            if "index" not in state:
                state["index"] = symbol_index.SymbolIndex(root, class_skeleton=mode)
            result = symbol_index.dispatch(state["index"], name, arguments)
            repo_brief.record_recall(state["index"], name, arguments, result)
            return result

    @server.tool(description=DESCRIPTIONS["locate"], structured_output=False)
    def locate(query: str) -> str:
        return run("locate", {"query": query})

    @server.tool(description=DESCRIPTIONS["read_symbol"], structured_output=False)
    def read_symbol(target: str) -> str:
        return run("read_symbol", {"target": target})

    @server.tool(description=DESCRIPTIONS["impact"], structured_output=False)
    def impact(symbol: str, depth: int = 1) -> str:
        return run("impact", {"symbol": symbol, "depth": depth})

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-skeleton", choices=symbol_index.CLASS_READ_MODES, default=None)
    ns = parser.parse_args()
    make_server(Path.cwd(), class_skeleton=ns.class_skeleton).run()
