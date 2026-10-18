"""TokenMaster code navigation over MCP: locate, read_symbol and impact (v7).

Serves brainspace/symbol_index.py for the repository the host starts it in: exact
symbol ranges from a local SQLite index (.token-master/symbols.sqlite) plus graphify's
call graph (.token-master/graph.json, built by setup.py). Every result stays under
2,400 tokens. Measured in PRS-3: token-master-plugin/docs/PRS3_RESULTS.md.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brainspace import symbol_index  # noqa: E402

SERVER_NAME = "tokenmaster-nav"
DESCRIPTIONS = {spec["name"]: spec["description"] for spec in symbol_index.TOOL_SPECS}


def make_server(root: Path):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(SERVER_NAME)
    lock = threading.Lock()
    state: dict[str, symbol_index.SymbolIndex] = {}

    def run(name: str, arguments: dict) -> str:
        with lock:  # one SQLite connection, built on first use so host startup never waits
            if "index" not in state:
                state["index"] = symbol_index.SymbolIndex(root)
            return symbol_index.dispatch(state["index"], name, arguments)

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
    make_server(Path.cwd()).run()
