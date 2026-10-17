"""Graph contract regressions; fixtures are synthetic and workspace-local."""
import importlib.util
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))


@pytest.fixture
def graph(tmp_path, monkeypatch):
    source = tmp_path / "src.py"
    source.write_text("def target(): pass\n")
    path = tmp_path / ".token-master" / "graph.json"
    path.parent.mkdir()
    monkeypatch.setenv("GRAPH_PATH", str(path))
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("graph_under_test", SKILL / "graphify_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    nodes = [{"id": "target", "label": "target", "file_type": "code",
              "source_file": "src.py", "source_location": 1}]

    def write(nodes=nodes, links=None):
        payload = {"nodes": nodes, "links": links or []}
        module.stamp_graph(payload, tmp_path, {"name": "fixture", "version": "1"})
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload
    write()
    return module, write, source, path, nodes


def meta(text):
    return json.loads(text.split("\nmetadata: ", 1)[1])


def test_source_edit_after_first_query_and_index_replacement(graph):
    module, write, source, path, nodes = graph
    first = meta(module.callers("target"))
    assert first["source_status"] == "fresh"
    source.write_text("def target(): return 123\n")
    assert meta(module.callers("target"))["source_status"] == "stale"
    write(nodes + [{"id": "new", "label": "new", "file_type": "code",
                    "source_file": "src.py", "source_location": 2}])
    assert "new" in module.find("new")
    second = meta(module.callers("target"))
    assert second["source_status"] == "fresh"
    assert second["index_sha256"] != first["index_sha256"]
    assert second["supplier"]["name"] == "fixture"


@pytest.mark.parametrize("tool,relation,reverse", [("callers", "calls", True),
                                                 ("callees", "calls", False),
                                                 ("impact", "calls", True),
                                                 ("inheritors", "inherits", True)])
def test_high_fanout_pages(graph, tool, relation, reverse):
    module, write, source, path, nodes = graph
    others = [{"id": f"n{i:03}", "label": f"n{i:03}", "file_type": "code",
               "source_file": "src.py", "source_location": i + 2} for i in range(137)]
    links = [{"source": n["id"] if reverse else "target",
              "target": "target" if reverse else n["id"], "relation": relation} for n in others]
    write(nodes + others, links)
    found, offset = [], 0
    while True:
        result = getattr(module, tool)("target", offset=offset, limit=17)
        m = meta(result)
        found.extend(m["row_ids"])
        assert not m["semantic_complete"]
        assert m["total"] == 137
        if m["next_offset"] is None:
            assert m["enumeration_complete"]
            break
        offset = m["next_offset"]
    assert len(found) == len(set(found)) == 137


def test_ambiguous_even_two_definitions_requires_id(graph):
    module, write, source, path, nodes = graph
    write(nodes + [dict(nodes[0], id="other")])
    assert "ambiguous" in module.callers("target()")
    assert "ambiguous" not in module.callers("target")


def test_distinct_candidate_ids_with_same_name_are_not_collapsed(graph):
    module, write, source, path, nodes = graph
    write(nodes + [dict(nodes[0], id=n, label="same-name") for n in ("a", "b")],
          [{"source": n, "target": "target", "relation": "calls"} for n in ("a", "b")])
    assert meta(module.callers("target"))["row_ids"] == ["a", "b"]
    assert meta(module.callers("target"))["semantic_complete"] is False


@pytest.mark.parametrize("bad", [{"nodes": [], "links": []},
                               {"nodes": [{"id": "x"}, {"id": "x"}], "links": []},
                               {"nodes": [{"id": "x"}], "links": [{"source": "x", "target": "missing", "relation": "calls"}]},
                               {"nodes": "bad", "links": []}, []])
def test_invalid_replacement_never_serves_cached_graph(graph, bad):
    module, write, source, path, nodes = graph
    assert "target" in module.find("target")
    path.write_text(json.dumps(bad))
    assert "invalid" in module.callers("target").lower()


def test_legacy_unknown_freshness_and_invalid_page(graph):
    module, write, source, path, nodes = graph
    path.write_text(json.dumps({"nodes": nodes, "links": []}))
    assert meta(module.callers("target"))["source_status"] == "unknown"
    assert "invalid" in module.callers("target", offset=-1).lower()
    assert "invalid" in module.callers("target", limit=0).lower()


def test_missing_mcp_dependency_retains_local_queries(graph):
    module, write, source, path, nodes = graph
    # -S intentionally omits site-packages: no fake dependency or network.
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import graphify_mcp as g;"
            "assert g.mcp is None; print(g.callers('target'))")
    result = subprocess.run([sys.executable, "-X", "utf8", "-S", "-c", code, str(SKILL)],
                            capture_output=True, encoding="utf-8", check=True,
                            env={**os.environ, "GRAPH_PATH": str(path)})
    assert meta(result.stdout.strip())["semantic_complete"] is False


def test_same_size_same_mtime_source_edit_detected(graph):
    module, write, source, path, nodes = graph
    before = source.stat()
    assert meta(module.callers("target"))["source_status"] == "fresh"
    source.write_bytes(source.read_bytes().replace(b"pass", b"None"))
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert meta(module.callers("target"))["source_status"] == "stale"


def test_source_outside_workspace_not_read_or_declared_fresh(graph, monkeypatch):
    module, write, source, path, nodes = graph
    original = Path.read_bytes
    def read_bytes(p):
        assert "outside.py" not in str(p)
        return original(p)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    write([dict(nodes[0], source_file="../outside.py")])
    assert meta(module.callers("target"))["source_status"] == "unknown"


def test_depth_boundary_disclosed_and_cycles_terminate(graph):
    module, write, source, path, nodes = graph
    nodes = nodes + [dict(nodes[0], id=name, label=name) for name in ("a", "b", "c")]
    write(nodes, [{"source": s, "target": t, "relation": "calls"}
                  for s, t in [("a", "target"), ("b", "a"), ("c", "b"), ("target", "c")]])
    shallow = meta(module.impact("target", depth=1))
    assert shallow["total"] == 1 and shallow["depth_boundary_has_more"]
    deep = meta(module.impact("target", depth=5))
    assert deep["total"] == 3 and not deep["depth_boundary_has_more"]


def test_real_mcp_stdio_tools_and_pagination_in_unicode_path(graph, tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    module, write, source, path, nodes = graph
    others = [dict(nodes[0], id=f"n{i:03}", label=f"n{i:03}") for i in range(75)]
    write(nodes + others, [{"source": n["id"], "target": "target", "relation": "calls"}
                          for n in others])
    install = tmp_path / "MCP space 工具"
    install.mkdir()
    script = install / "graphify_mcp.py"
    script.write_bytes((SKILL / "graphify_mcp.py").read_bytes())

    async def exercise():
        server = StdioServerParameters(command=sys.executable,
                                       args=["-X", "utf8", str(script)],
                                       env={"GRAPH_PATH": str(path), "PYTHONUTF8": "1"})
        async with stdio_client(server) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {t.name for t in tools.tools} == {"find", "callers", "callees", "impact", "inheritors", "explain"}
                schema = next(t.inputSchema for t in tools.tools if t.name == "callers")
                assert {"symbol", "offset", "limit"} <= schema["properties"].keys()
                result = await session.call_tool("callers", {"symbol": "target", "offset": 3, "limit": 7})
                assert not result.isError
                payload = meta(result.content[0].text)
                assert payload["returned"] == 7 and payload["total"] == 75
                assert payload["next_offset"] == 10 and not payload["semantic_complete"]
    asyncio.run(asyncio.wait_for(exercise(), timeout=30))
