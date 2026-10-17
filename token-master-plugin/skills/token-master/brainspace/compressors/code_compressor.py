"""Recovery-required Python/Rust navigation views; exact passthrough by default.

Only explicit ``intent="navigation"`` can omit executable bodies. Tree-sitter
must parse without errors and every omitted byte span must be stashed before a
view is returned. Missing grammars, malformed source and failed storage are
whole-input passthrough. The skeleton is a view, not executable source.
"""

from __future__ import annotations

import importlib

from . import report_failure, require_stash


_LANG_SPECS = {
    "python": {
        "module": "tree_sitter_python",
        "elide": "function_definition",
    },
    "rust": {
        "module": "tree_sitter_rust",
        "elide": "function_item",
    },
}


def compress_code(
    content: str,
    *,
    stash=None,
    lang: str = "python",
    intent: str = "conservative",
    **opts,
) -> str:
    """Keep source exact except for recoverable body spans in navigation mode.

    Replacing each emitted reference with its stored fragment reconstructs the
    original source byte-for-byte, including decorators, gaps, CRLF and tabs.
    Unknown kwargs remain accepted; no budget can force a body omission.
    """
    if not isinstance(content, str) or intent != "navigation" or stash is None:
        return content
    try:
        spec = _LANG_SPECS.get(lang.lower())
        if spec is None or not content.strip():
            return content
        from tree_sitter import Language, Parser

        grammar = importlib.import_module(spec["module"])
        parser = Parser(Language(grammar.language()))
        source = content.encode("utf-8")
        root = parser.parse(source).root_node
        if root.has_error:
            return content

        spans: list[tuple[int, int, str]] = []
        _body_spans(root, source, spec, spans)
        parts: list[str] = []
        cursor = 0
        for start, end, name in spans:
            original = source[start:end].decode("utf-8")
            reference = require_stash(original, stash=stash, ctype="code",
                                      source=f"{name} body")
            parts.extend((source[cursor:start].decode("utf-8"), reference))
            cursor = end
        parts.append(source[cursor:].decode("utf-8"))
        view = "".join(parts)
        return view if len(view) < len(content) else content
    except Exception as exc:
        report_failure(opts, exc)
        return content


def _body_spans(node, source: bytes, spec: dict,
                spans: list[tuple[int, int, str]]) -> None:
    """Collect nonoverlapping replacement spans in source order."""
    if node.type != spec["elide"]:
        for child in node.children:
            _body_spans(child, source, spec, spans)
        return

    body = node.child_by_field_name("body")
    if body is None:
        return
    start, end = body.start_byte, body.end_byte
    if spec["elide"] == "function_item":
        # Keep Rust braces in the view; only their interior is executable body.
        start += 1
        end -= 1
    else:
        # Preserve the leading Python docstring and any preceding comments.
        for child in body.named_children:
            if child.type == "comment":
                continue
            if (child.type == "expression_statement" and
                    len(child.named_children) == 1 and
                    child.named_children[0].type in ("string", "concatenated_string")):
                start = child.end_byte
            break

    # Keep boundary whitespace verbatim, outside the recoverable fragment.
    while start < end and source[start:start + 1] in b" \t\r\n":
        start += 1
    while end > start and source[end - 1:end] in b" \t\r\n":
        end -= 1
    if start >= end:
        return
    name = node.child_by_field_name("name")
    label = source[name.start_byte:name.end_byte].decode("utf-8") if name else "<anon>"
    spans.append((start, end, label))
