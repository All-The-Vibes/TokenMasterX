"""v7 navigation server: the installed layout serves locate, read_symbol and impact over MCP stdio."""
from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]


def _nav_modules():
    spec = importlib.util.spec_from_file_location("token_master_setup", SKILL / "setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NAV_MODULES


def test_installed_navigation_server_answers_over_stdio(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from brainspace.symbol_index import TOOL_SPECS

    install = tmp_path / "MCP space 工具"
    for rel in ("navigation_mcp.py", *_nav_modules()):  # exactly what setup.py installs
        (install / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SKILL / rel, install / rel)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def helper():\n    return 1\n\n\ndef main():\n    return helper()\n", encoding="utf-8")
    (repo / "lib.rs").write_text("pub fn rust_helper() -> u8 {\n    1\n}\n\n"
                                 "pub fn rust_main() -> u8 {\n    rust_helper()\n}\n", encoding="utf-8")

    async def exercise():
        server = StdioServerParameters(command=sys.executable, args=["-X", "utf8", str(install / "navigation_mcp.py")],
                                       cwd=str(repo), env={"PYTHONUTF8": "1"})
        async with stdio_client(server) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert {t.name: t.description for t in tools} == {s["name"]: s["description"] for s in TOOL_SPECS}
                located = await session.call_tool("locate", {"query": "helper"})
                assert not located.isError and "app.py:1-2 function helper" in located.content[0].text
                callers = await session.call_tool("impact", {"symbol": "helper"})
                assert "  app.py:6 main | return helper()" in callers.content[0].text
                body = await session.call_tool("read_symbol", {"target": "app.py::main"})
                assert body.content[0].text.endswith("6.     return helper()")
                rust = await session.call_tool("impact", {"symbol": "rust_helper"})
                assert "  lib.rs:6 rust_main | rust_helper()" in rust.content[0].text

    asyncio.run(asyncio.wait_for(exercise(), timeout=60))
    assert (repo / ".token-master" / "symbols.sqlite").is_file()
