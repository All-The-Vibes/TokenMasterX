"""Synthetic-only MCP result shapes for isolated native-host acceptance tests."""
import argparse
import base64
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    args = parser.parse_args()
    text = args.fixture.read_text(encoding="utf-8")
    image = base64.b64encode(args.image.read_bytes()).decode("ascii")
    server = FastMCP("TokenMaster synthetic native envelope fixture")

    @server.tool()
    def json_text() -> CallToolResult:
        """Return the synthetic fixture as an unstructured text-content array."""
        return CallToolResult(content=[TextContent(type="text", text=text)])

    @server.tool()
    def mixed_content() -> CallToolResult:
        """Return synthetic text and a one-pixel image; must remain unchanged."""
        return CallToolResult(content=[
            TextContent(type="text", text=text),
            ImageContent(type="image", data=image, mimeType="image/png"),
        ])

    @server.tool()
    def structured_content() -> CallToolResult:
        """Return duplicate structured and text forms; must not diverge."""
        return CallToolResult(content=[TextContent(type="text", text=text)],
                              structuredContent=json.loads(text))

    @server.tool()
    def error_content() -> CallToolResult:
        """Return a synthetic error carrying data; must remain an error."""
        error = json.loads(text)
        error["error_marker"] = "TOKENMASTER_SYNTHETIC_ERROR"
        return CallToolResult(isError=True, content=[
            # Valid pretty JSON would otherwise be eligible for compaction.
            # The error flag, not an unparseable prefix, must prevent rewriting.
            TextContent(type="text", text=json.dumps(error, indent=4)),
        ])

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
