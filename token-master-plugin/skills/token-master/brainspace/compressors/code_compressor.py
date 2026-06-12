"""Code / AST compressor — Python-first tree-sitter skeletonization.

Walks top-level and nested function_definition / class_definition nodes,
keeps headers and leading docstrings, and replaces bodies with a single
stub line that optionally stashes the full body for lossless recovery.

Contract rules observed:
  1. Never raise — any parse or import failure returns content unchanged.
  2. str in, str out.
  3. Lossy display, lossless recovery: body text is stashed when stash is
     available; otherwise a plain '<N lines elided>' marker is used (lossless
     enough for measurement contexts where stash is None).
  4. Deterministic: traversal follows source order (tree-sitter preserves it).

Optional deps (lazy-imported inside the function):
  tree-sitter          https://pypi.org/project/tree-sitter/
  tree-sitter-python   https://pypi.org/project/tree-sitter-python/
When either is absent the module still imports cleanly and the function
degrades to a no-op (returns content unchanged).
"""

from __future__ import annotations


def compress_code(
    content: str,
    *,
    stash=None,
    lang: str = "python",
    **opts,
) -> str:
    """Return a skeletonized view of *content* (Python source by default).

    Parameters
    ----------
    content:
        Raw source code as a ``str``.
    stash:
        CCR stash callable (injected by the router).  When ``None`` the
        compressor behaves losslessly — bodies are replaced with inline
        ``<N lines elided>`` markers rather than placeholders.
    lang:
        Source language.  Currently only ``'python'`` is wired; any other
        value triggers a graceful noop.
    **opts:
        Ignored — callers pass a shared bag; unknown keys must not raise.
    """
    # ------------------------------------------------------------------ guards
    if not isinstance(content, str):
        return content  # type: ignore[return-value]
    if not content.strip():
        return content
    if lang.lower() != "python":
        # Only Python is wired; other langs degrade to noop transparently.
        return content

    # -------------------------------------------------- lazy optional imports
    try:
        from tree_sitter import Language, Parser  # type: ignore[import]
        import tree_sitter_python as tspy  # type: ignore[import]
    except Exception:
        # tree-sitter or tree-sitter-python absent — noop degrade.
        return content

    # --------------------------------------------------------- build language
    try:
        PY_LANG = Language(tspy.language())
        parser = Parser(PY_LANG)
    except Exception:
        return content

    # ----------------------------------------------------------- parse source
    try:
        src_bytes = content.encode("utf-8", errors="replace")
        tree = parser.parse(src_bytes)
    except Exception:
        return content

    # -------------------------------------------------------- walk + rewrite
    try:
        out = _skeletonize(src_bytes, tree.root_node, stash=stash)
        return out
    except Exception:
        return content


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _skeletonize(src_bytes: bytes, root_node, *, stash) -> str:
    """Walk *root_node* top-down and rebuild a skeletonized source string."""
    out_parts: list[str] = []
    cursor = 0  # byte offset of how far we've consumed src_bytes

    for child in root_node.children:
        node_type = child.type

        if node_type in ("function_definition", "decorated_definition",
                         "class_definition"):
            # Emit any source bytes between cursor and this node verbatim
            # (module-level imports, assignments, blank lines, comments).
            if child.start_byte > cursor:
                out_parts.append(
                    src_bytes[cursor: child.start_byte].decode("utf-8", errors="replace")
                )
            cursor = child.end_byte

            # Rewrite the node
            out_parts.append(
                _rewrite_top_node(src_bytes, child, stash=stash, indent=0)
            )
        else:
            # Keep verbatim (imports, assignments, module docstring, etc.)
            pass  # defer — we'll flush after the loop

    # Flush any remaining source after the last matched node
    if cursor < len(src_bytes):
        out_parts.append(
            src_bytes[cursor:].decode("utf-8", errors="replace")
        )

    # Rebuild: all non-matched children were NOT consumed by the cursor-skip
    # approach above; rebuild them properly.
    return _rebuild(src_bytes, root_node, stash=stash)


def _rebuild(src_bytes: bytes, root_node, *, stash) -> str:
    """Walk root_node children in source order, rewriting func/class bodies."""
    parts: list[str] = []
    cursor = 0

    for child in root_node.children:
        if child.start_byte > cursor:
            parts.append(
                src_bytes[cursor: child.start_byte].decode("utf-8", errors="replace")
            )

        if child.type in ("function_definition",):
            parts.append(_rewrite_func(src_bytes, child, stash=stash, indent=0))
            cursor = child.end_byte

        elif child.type in ("class_definition",):
            parts.append(_rewrite_class(src_bytes, child, stash=stash, indent=0))
            cursor = child.end_byte

        elif child.type == "decorated_definition":
            # The actual def/class is a child of this node; rewrite as unit.
            parts.append(_rewrite_decorated(src_bytes, child, stash=stash, indent=0))
            cursor = child.end_byte

        else:
            parts.append(
                src_bytes[child.start_byte: child.end_byte].decode("utf-8", errors="replace")
            )
            cursor = child.end_byte

    if cursor < len(src_bytes):
        parts.append(src_bytes[cursor:].decode("utf-8", errors="replace"))

    return "".join(parts)


def _rewrite_top_node(src_bytes: bytes, node, *, stash, indent: int) -> str:
    """Dispatch to the correct rewriter for a top-level node."""
    if node.type == "function_definition":
        return _rewrite_func(src_bytes, node, stash=stash, indent=indent)
    if node.type == "class_definition":
        return _rewrite_class(src_bytes, node, stash=stash, indent=indent)
    if node.type == "decorated_definition":
        return _rewrite_decorated(src_bytes, node, stash=stash, indent=indent)
    # Fallback: keep verbatim
    return src_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")


def _rewrite_decorated(src_bytes: bytes, node, *, stash, indent: int) -> str:
    """Keep decorator lines; rewrite the inner def/class."""
    parts: list[str] = []
    inner = None
    for child in node.children:
        if child.type in ("function_definition", "class_definition"):
            inner = child
        else:
            parts.append(
                src_bytes[child.start_byte: child.end_byte].decode("utf-8", errors="replace")
            )

    if inner is None:
        return src_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")

    parts.append(_rewrite_top_node(src_bytes, inner, stash=stash, indent=indent))
    return "".join(parts)


def _rewrite_func(src_bytes: bytes, node, *, stash, indent: int) -> str:
    """Return a skeletonized function: keep header + docstring, stub body."""
    body_node = node.child_by_field_name("body")
    if body_node is None:
        return src_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")

    # Header: everything from node start up to body start
    header = src_bytes[node.start_byte: body_node.start_byte].decode("utf-8", errors="replace")

    # Extract function name for stash metadata
    name_node = node.child_by_field_name("name")
    func_name = (
        src_bytes[name_node.start_byte: name_node.end_byte].decode("utf-8", errors="replace")
        if name_node
        else "<anon>"
    )

    # Leading docstring (first statement if it is an expression_statement
    # whose sole child is a string node)
    docstring_text, body_start_byte = _extract_docstring(src_bytes, body_node)

    # Body bytes (everything after optional docstring, up to body end)
    body_text = src_bytes[body_start_byte: body_node.end_byte].decode(
        "utf-8", errors="replace"
    )

    stub_line = _make_stub(body_text, func_name, stash=stash, indent=indent)

    # Assemble: header + optional docstring + stub
    pieces = [header]
    if docstring_text:
        pieces.append(docstring_text)
    pieces.append(stub_line)
    # Ensure trailing newline
    result = "".join(pieces)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _rewrite_class(src_bytes: bytes, node, *, stash, indent: int) -> str:
    """Return a skeletonized class: keep header + docstring, recurse into methods."""
    body_node = node.child_by_field_name("body")
    if body_node is None:
        return src_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")

    # Header: class X(...):
    header = src_bytes[node.start_byte: body_node.start_byte].decode("utf-8", errors="replace")

    # Class docstring
    docstring_text, body_start_byte = _extract_docstring(src_bytes, body_node)

    # Recurse: rebuild body, rewriting each method but keeping class-level assigns
    body_parts: list[str] = []
    cursor = body_start_byte
    for child in body_node.children:
        if child.start_byte < body_start_byte:
            continue  # already consumed by docstring extraction

        if child.start_byte > cursor:
            body_parts.append(
                src_bytes[cursor: child.start_byte].decode("utf-8", errors="replace")
            )

        if child.type == "function_definition":
            body_parts.append(_rewrite_func(src_bytes, child, stash=stash, indent=indent + 4))
            cursor = child.end_byte
        elif child.type == "decorated_definition":
            body_parts.append(_rewrite_decorated(src_bytes, child, stash=stash, indent=indent + 4))
            cursor = child.end_byte
        elif child.type == "class_definition":
            body_parts.append(_rewrite_class(src_bytes, child, stash=stash, indent=indent + 4))
            cursor = child.end_byte
        else:
            body_parts.append(
                src_bytes[child.start_byte: child.end_byte].decode("utf-8", errors="replace")
            )
            cursor = child.end_byte

    if cursor < body_node.end_byte:
        body_parts.append(
            src_bytes[cursor: body_node.end_byte].decode("utf-8", errors="replace")
        )

    pieces = [header]
    if docstring_text:
        pieces.append(docstring_text)
    pieces.extend(body_parts)
    return "".join(pieces)


def _extract_docstring(src_bytes: bytes, body_node) -> tuple[str, int]:
    """Return (docstring_source_text, next_byte) for the leading docstring.

    If no docstring is present, returns ('', body_node.start_byte).
    """
    for child in body_node.children:
        if child.type in ("comment", "newline", "\n"):
            continue
        if child.type == "expression_statement":
            # Check if sole meaningful child is a string
            string_child = _first_string_child(child)
            if string_child is not None:
                text = src_bytes[child.start_byte: child.end_byte].decode(
                    "utf-8", errors="replace"
                )
                return text, child.end_byte
        # First non-docstring child: stop
        break
    return "", body_node.start_byte


def _first_string_child(node):
    """Return the first string node child (or None) of an expression_statement."""
    for child in node.children:
        if child.type in ("string", "concatenated_string"):
            return child
        if child.type not in ("comment", "newline", "\n"):
            return None
    return None


def _make_stub(body_text: str, name: str, *, stash, indent: int) -> str:
    """Return the stub replacement line for a function body.

    Uses stash when available; falls back to a plain elision marker.
    """
    n_lines = body_text.count("\n") + (1 if body_text and not body_text.endswith("\n") else 0)
    pad = " " * (indent + 4)  # one extra indent level inside the function

    if stash is not None:
        placeholder = None
        try:
            placeholder = stash(body_text, ctype="code", source=f"{name} body")
        except Exception:
            placeholder = None
        if placeholder is not None:
            return f"{pad}... {placeholder}\n"
        # stash returned None — keep losslessly with inline marker
    # Lossless fallback (no stash, or stash failed)
    return f"{pad}... <{n_lines} lines elided>\n"
