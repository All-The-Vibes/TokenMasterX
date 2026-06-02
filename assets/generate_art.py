#!/usr/bin/env python3
"""
TokenMaster — generative hero art.

Deterministic, dependency-free SVG generator. The composition *is* the thesis:
a layered code graph (columns of functions, left to right) where the dim,
out-of-focus web is grep sprawl and one bright, blooming path is a single
bounded graph-routed query — threading cleanly from question to answer.

Design language (bolder pass): near-black navy field lit by two off-axis
blooms (indigo + cyan), a genuine Gaussian-blur glow on the routed path,
depth-of-field that pushes the grep tangle back, a CLI prompt cue, and a
tight, heavy type scale. Everything is seed-driven, so the SVG is
reproducible and remixable:

    python assets/generate_art.py                # default hero
    python assets/generate_art.py --seed 7       # a different weave
    python assets/generate_art.py --out x.svg

No third-party packages. Python 3.9+.
"""
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass

# ── palette ──────────────────────────────────────────────────────────────
BG_TOP = "#04060e"         # near-black navy
BG_BOT = "#0a1430"
BLOOM_I = "#4f46e5"        # indigo bloom (graphify)
BLOOM_C = "#0891b2"        # cyan bloom (answer)
DIM_EDGE = "#1b2547"       # grep sprawl, pushed back
DIM_NODE = "#33406e"
ROUTE_A = "#818cf8"        # indigo
ROUTE_B = "#a78bfa"        # violet (midpoint warmth)
ROUTE_C = "#22d3ee"        # cyan
NODE_HOT = "#e0e7ff"
TEXT = "#f4f7ff"
TEXT_DIM = "#94a3c8"
ACCENT = "#a5b4fc"
PROMPT = "#34e7c8"         # terminal caret / prompt glyph


@dataclass
class Node:
    x: float
    y: float
    col: int
    row: int


def _columns(rng: random.Random, geom) -> list[list[Node]]:
    """Lay nodes out in evenly-spaced columns. Even vertical distribution with
    a touch of jitter — structured enough to read as design, organic enough to
    feel alive."""
    gx, gy, gw, gh, n_cols, counts = geom
    cols: list[list[Node]] = []
    for c in range(n_cols):
        x = gx + gw * (c / (n_cols - 1))
        k = counts[c]
        nodes = []
        # center the column vertically with breathing room top/bottom
        span = gh * (0.5 + 0.5 * (k / max(counts)))
        top = gy + (gh - span) / 2
        for r in range(k):
            y = top + (span * (r / (k - 1)) if k > 1 else span / 2)
            y += rng.uniform(-10, 10)
            x_j = x + rng.uniform(-9, 9)
            nodes.append(Node(x_j, y, c, r))
        cols.append(nodes)
    return cols


def _edges(rng: random.Random, cols: list[list[Node]]):
    """Each node links forward to its 1–3 nearest in the next column. Forward-
    only keeps the weave legible — no backward crossings — but a denser fan-out
    dramatizes grep sprawl."""
    es = []
    for c in range(len(cols) - 1):
        nxt = cols[c + 1]
        for nd in cols[c]:
            cand = sorted(nxt, key=lambda m: abs(m.y - nd.y))
            for m in cand[: rng.choice([1, 2, 2, 3])]:
                es.append((nd, m))
    return es


def _route(rng: random.Random, cols: list[list[Node]]) -> list[Node]:
    """One node per column, forward-nearest with slight drift — the bounded
    query path from question (left) to answer (right)."""
    path = [rng.choice(cols[0][len(cols[0]) // 3 : 2 * len(cols[0]) // 3] or cols[0])]
    for c in range(1, len(cols)):
        prev = path[-1]
        nxt = min(cols[c], key=lambda m: abs(m.y - prev.y) + rng.uniform(-6, 6))
        path.append(nxt)
    return path


def _cubic(a: Node, b: Node) -> str:
    """Horizontal-ish bezier between columns — smooth, flowing, no kinks."""
    mx = (a.x + b.x) / 2
    return f"M{a.x:.1f},{a.y:.1f} C{mx:.1f},{a.y:.1f} {mx:.1f},{b.y:.1f} {b.x:.1f},{b.y:.1f}"


def generate(seed: int = 42, w: int = 1200, h: int = 420) -> str:
    rng = random.Random(seed)

    # graph lives in the right portion; type breathes on the left
    gx, gy, gw, gh = 478, 64, 668, 300
    n_cols = 7
    counts = [4, 6, 8, 9, 8, 6, 4]
    cols = _columns(rng, (gx, gy, gw, gh, n_cols, counts))
    edges = _edges(rng, cols)
    path = _route(rng, cols)
    route_d = [_cubic(path[i], path[i + 1]) for i in range(len(path) - 1)]
    route_full = " ".join(route_d)

    P: list[str] = []
    P.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" role="img" '
        f'aria-label="TokenMaster — one bright graph-routed path blooming through a dim, out-of-focus code graph">'
    )
    P.append(
        f"""<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOT}"/>
  </linearGradient>
  <radialGradient id="bloomA" cx="0.70" cy="0.30" r="0.62">
    <stop offset="0" stop-color="{BLOOM_I}" stop-opacity="0.55"/>
    <stop offset="1" stop-color="{BLOOM_I}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="bloomB" cx="0.92" cy="0.78" r="0.5">
    <stop offset="0" stop-color="{BLOOM_C}" stop-opacity="0.42"/>
    <stop offset="1" stop-color="{BLOOM_C}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="route" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{ROUTE_A}"/>
    <stop offset="0.5" stop-color="{ROUTE_B}"/>
    <stop offset="1" stop-color="{ROUTE_C}"/>
  </linearGradient>
  <linearGradient id="ink" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{TEXT}"/><stop offset="1" stop-color="#c3cbe6"/>
  </linearGradient>
  <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
    <feGaussianBlur stdDeviation="6"/>
  </filter>
  <filter id="halo" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="3.4"/>
  </filter>
  <filter id="soften" x="-10%" y="-10%" width="120%" height="120%">
    <feGaussianBlur stdDeviation="1.15"/>
  </filter>
</defs>"""
    )
    P.append(f'<rect width="{w}" height="{h}" fill="url(#bg)"/>')
    P.append(f'<rect width="{w}" height="{h}" fill="url(#bloomA)"/>')
    P.append(f'<rect width="{w}" height="{h}" fill="url(#bloomB)"/>')

    # faint dot-grid texture (very low opacity) — subtle depth, not noise
    P.append('<g fill="#ffffff" opacity="0.022">')
    for gx2 in range(40, w, 34):
        for gy2 in range(40, h, 34):
            P.append(f'<circle cx="{gx2}" cy="{gy2}" r="1"/>')
    P.append("</g>")

    # ── grep sprawl: dim edges + nodes, softened and pushed back (depth of field) ──
    P.append('<g filter="url(#soften)" opacity="0.62">')
    P.append(f'<g stroke="{DIM_EDGE}" stroke-width="1" fill="none">')
    for a, b in edges:
        P.append(f'<path d="{_cubic(a, b)}"/>')
    P.append("</g>")
    P.append(f'<g fill="{DIM_NODE}">')
    for col in cols:
        for nd in col:
            P.append(f'<circle cx="{nd.x:.1f}" cy="{nd.y:.1f}" r="2.6"/>')
    P.append("</g>")
    P.append("</g>")

    # ── routed path: genuine bloom underlay (blurred thick copy) ──
    P.append('<g filter="url(#glow)" opacity="0.95">')
    P.append('<g stroke="url(#route)" stroke-width="7" fill="none" stroke-linecap="round">')
    for d in route_d:
        P.append(f'<path d="{d}"/>')
    P.append("</g>")
    P.append("</g>")

    # ── route node halos (soft) ──
    P.append('<g filter="url(#halo)">')
    for nd in path:
        P.append(f'<circle cx="{nd.x:.1f}" cy="{nd.y:.1f}" r="7" fill="{ROUTE_C}" opacity="0.5"/>')
    P.append("</g>")

    # ── crisp routed path on top ──
    P.append('<g stroke="url(#route)" stroke-width="2.6" fill="none" stroke-linecap="round">')
    for d in route_d:
        P.append(f'<path d="{d}"/>')
    P.append("</g>")

    # ── route nodes (crisp) ──
    for i, nd in enumerate(path):
        endpoint = i in (0, len(path) - 1)
        r = 6 if endpoint else 4
        P.append(
            f'<circle cx="{nd.x:.1f}" cy="{nd.y:.1f}" r="{r}" fill="{NODE_HOT}" '
            f'stroke="{ROUTE_C}" stroke-width="1.5"/>'
        )
    # traveller pulse — a glowing dot threading the route
    P.append(
        f'<circle r="3.4" fill="#ffffff">'
        f'<animateMotion dur="5.5s" repeatCount="indefinite" path="{route_full}"/></circle>'
    )
    # endpoint labels: query → answer
    qa = path[0]
    an = path[-1]
    P.append(
        f'<text x="{qa.x:.0f}" y="{qa.y - 15:.0f}" text-anchor="middle" '
        f'font-family="ui-monospace,Menlo,monospace" font-size="11.5" fill="{ACCENT}" '
        f'opacity="0.9">query</text>'
    )
    P.append(
        f'<text x="{an.x:.0f}" y="{an.y - 15:.0f}" text-anchor="middle" '
        f'font-family="ui-monospace,Menlo,monospace" font-size="11.5" fill="{ROUTE_C}" '
        f'opacity="0.95">answer</text>'
    )

    # ── left column: heavy type, CLI cue, metric ──
    tx = 70
    P.append(
        f'<text x="{tx}" y="150" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" '
        f'font-size="56" font-weight="800" fill="url(#ink)" letter-spacing="-1.5">TokenMaster</text>'
    )
    P.append(
        f'<text x="{tx+2}" y="184" font-family="ui-monospace,Menlo,monospace" '
        f'font-size="15" fill="{TEXT_DIM}">route the question to the graph,</text>'
    )
    P.append(
        f'<text x="{tx+2}" y="206" font-family="ui-monospace,Menlo,monospace" '
        f'font-size="15" fill="{TEXT_DIM}">not the grep.</text>'
    )
    # CLI prompt cue — reads instantly as a command-line tool
    py = 240
    P.append(
        f'<g transform="translate({tx},{py})">'
        f'<text x="0" y="0" font-family="ui-monospace,Menlo,monospace" font-size="15.5" '
        f'font-weight="700" fill="{PROMPT}">❯</text>'
        f'<text x="20" y="0" font-family="ui-monospace,Menlo,monospace" font-size="15.5" '
        f'fill="{TEXT}">/token-master</text>'
        f'<rect x="156" y="-12" width="9" height="16" rx="1.5" fill="{PROMPT}">'
        f'<animate attributeName="opacity" values="1;1;0;0" dur="1.1s" repeatCount="indefinite"/>'
        f'</rect>'
        f"</g>"
    )
    # thin accent rule
    P.append(f'<rect x="{tx}" y="266" width="46" height="3" rx="1.5" fill="url(#route)"/>')
    # metric badge
    by = 286
    P.append(
        f'<g transform="translate({tx},{by})">'
        f'<text x="0" y="40" font-family="ui-monospace,Menlo,monospace" font-size="48" '
        f'font-weight="800" fill="url(#route)" letter-spacing="-1">3.7×</text>'
        f'<text x="126" y="26" font-family="ui-monospace,Menlo,monospace" font-size="13.5" '
        f'fill="{TEXT}">fewer cumulative</text>'
        f'<text x="126" y="45" font-family="ui-monospace,Menlo,monospace" font-size="13.5" '
        f'fill="{TEXT_DIM}">context tokens</text>'
        f"</g>"
    )

    P.append("</svg>")
    return "\n".join(P)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate TokenMaster hero art (SVG).")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=420)
    ap.add_argument("--out", default="assets/tokenmaster-hero.svg")
    args = ap.parse_args()

    svg = generate(args.seed, args.width, args.height)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {args.out}  ({len(svg):,} bytes, seed={args.seed})")


if __name__ == "__main__":
    main()
