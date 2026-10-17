"""Real stdio MCP transport, synthetic data, no host profile or model inference."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

SKILL = Path(__file__).resolve().parents[1] / "skills" / "token-master"
sys.path.insert(0, str(SKILL))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from brainspace.ccr import PLACEHOLDER_RE  # noqa: E402
from brainspace import tokens  # noqa: E402


def fixture():
    unit, suffix = "[INFO] " + "漢" * 70 + "\n", "[INFO] tests passed\n"
    count = (200001 - len(suffix) - 8) // len(unit)
    padding = 200001 - count * len(unit) - len(suffix) - 8
    text = unit * count + "[INFO] " + "a" * padding + "\n" + suffix
    assert len(text) == 200001
    return text


async def run():
    with tempfile.TemporaryDirectory(prefix="tokenmaster-mcp-") as directory:
        root = Path(directory) / "Unicode 空 白"
        root.mkdir()
        vocabulary = tokens._vocabulary_path()
        data = vocabulary.read_bytes() if vocabulary else b""
        if hashlib.sha256(data).hexdigest() != tokens.VOCABULARY_SHA256:
            raise ValueError("local pinned vocabulary required")
        local_vocabulary = root / "cl100k_base.tiktoken"
        local_vocabulary.write_bytes(data)
        env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR")
               if key in os.environ}
        env.update(PYTHONUTF8="1", BRAINSPACE_WORKSPACE_ROOT=str(root),
                   BRAINSPACE_TOKENIZER_FILE=str(local_vocabulary),
                   BRAINSPACE_SESSION_ID="synthetic-transport-session")
        parameters = StdioServerParameters(
            command=sys.executable, args=["-X", "utf8", str(SKILL / "brainspace_mcp.py")],
            env=env, cwd=str(root),
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = sorted(tool.name for tool in (await client.list_tools()).tools)
                original = fixture()
                compressed_result = await client.call_tool("brainspace_compress", {
                    "content": original, "hint": "fixture.log", "intent": "overview",
                })
                assert not compressed_result.isError
                assert compressed_result.structuredContent is None
                compressed = compressed_result.content[0].text
                references = [match.group(0) for match in PLACEHOLDER_RE.finditer(compressed)]
                assert references
                ref = references[-1]
                wire = compressed_result.model_dump(mode="json", exclude_none=True)
                baseline_wire = json.loads(json.dumps(wire))
                baseline_wire["content"][0]["text"] = original
                assert tokens.guard_replacement(baseline_wire, wire)
                offset, pages = 0, []
                digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
                while True:
                    result = await client.call_tool("brainspace_retrieve", {
                        "ref": ref, "offset": offset, "limit": 32768,
                    })
                    assert not result.isError
                    page = json.loads(result.content[0].text)
                    assert page["ok"] and page["sha256"] == digest
                    assert page["page_sha256"] == hashlib.sha256(page["content"].encode()).hexdigest()
                    pages.append(page["content"])
                    if page["complete"]:
                        break
                    assert page["next_offset"] > offset
                    offset = page["next_offset"]
                assert "".join(pages) == original
                search = await client.call_tool("brainspace_search", {
                    "ref": ref, "query": "tests passed",
                })
                found = json.loads(search.content[0].text)
                assert found["ok"] and len(found["results"]) == 1 and found["complete"]
                unknown = await client.call_tool("brainspace_retrieve", {"ref": "not-a-reference"})
                assert not json.loads(unknown.content[0].text)["ok"]
                return {
                    "ok": True, "synthetic_only": True, "transport": "MCP stdio",
                    "native_host_verified": False, "task_quality_verified": False,
                    "tools": tools, "original_chars": len(original),
                    "original_utf8_bytes": len(original.encode()), "full_sha256": digest,
                    "pages": len(pages), "public_reconstruction_exact": True,
                    "reference_envelope_tokens_before": tokens.count_tokens(tokens.serialize(baseline_wire)),
                    "reference_envelope_tokens_after": tokens.count_tokens(tokens.serialize(wire)),
                    "search_and_unknown_reference_verified": True,
                }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(run())
    encoded = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
