#!/usr/bin/env python3
"""TokenMasterX brand art: the mark, the logo lockup and the README hero.

Everything is drawn from square "token" chips, so the art renders the same on every
platform with no fonts to embed. The mark is an X whose second arm goes hollow chip
by chip: the tokens TokenMasterX prunes.

    python assets/generate_logo.py            # writes the three SVGs into assets/
    python assets/generate_logo.py --preview  # also writes assets/_brand_preview.html

No third-party packages. Python 3.9+.
"""
from __future__ import annotations

import argparse
import base64
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Palette: near-black field, acid lime accent, warm white type.
BG = "#07080a"
PLATE = "#0c0f0b"
EDGE = "#1b2117"
LIME = "#c6f432"
LIME_DEEP = "#7ccf1d"
INK = "#f2f5ee"
INK_SHADE = "#c9d0c3"
MUTED = "#8d968a"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, 'Helvetica Neue', Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'Cascadia Code', Menlo, Consolas, monospace"

TOKEN = 0.86    # chip size as a share of the grid pitch; tight seams read as solid letters
X_SCALE = 1.3   # the X is drawn larger than the letters

# 7-row token font: '#' is a chip. Lowercase sits on rows 2-6.
GLYPHS = {
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "o": [".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."],
    "k": ["#...", "#...", "#..#", "#.#.", "##..", "#.#.", "#..#"],
    "e": [".....", ".....", ".###.", "#...#", "#####", "#....", ".###."],
    "n": [".....", ".....", "####.", "#...#", "#...#", "#...#", "#...#"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "a": [".....", ".....", ".###.", "....#", ".####", "#...#", ".####"],
    "s": [".....", ".....", ".####", "#....", ".###.", "....#", "####."],
    "t": [".#..", ".#..", "####", ".#..", ".#..", ".#..", "..##"],
    "r": ["....", "....", "#.##", "##..", "#...", "#...", "#..."],
}
# The X: (row, col, kind). Kind 0 is a solid chip; 1-3 go from solid to hollow.
X_CELLS = [(i, i, 0) for i in range(7)] + [(0, 6, 0), (1, 5, 0), (2, 4, 0), (4, 2, 1), (5, 1, 2), (6, 0, 3)]
PRUNED_OPACITY = {1: 0.9, 2: 0.6, 3: 0.35}


def chip(x, y, size, fill):
    return f'<rect x="{x:g}" y="{y:g}" width="{size:g}" height="{size:g}" rx="{size * 0.2:g}" fill="{fill}"/>'


def x_chips(x0, y0, pitch, animate):
    """The mark's chips at (x0, y0). Pruned chips are hollow and, when animated, blink out in turn."""
    size, out = pitch * TOKEN, []
    for row, col, kind in X_CELLS:
        x, y = x0 + col * pitch, y0 + row * pitch
        if kind == 0:
            out.append(chip(x, y, size, "url(#lime)"))
            continue
        line = max(size * 0.16, 1.5)
        css = f' class="prune p{kind}"' if animate else ""
        out.append(f'<rect x="{x + line / 2:g}" y="{y + line / 2:g}" width="{size - line:g}" '
                   f'height="{size - line:g}" rx="{size * 0.18:g}" fill="none" stroke="{LIME}" '
                   f'stroke-width="{line:g}" opacity="{PRUNED_OPACITY[kind]}"{css}/>')
    return out


def lockup(pitch, animate):
    """'TokenMaster' in token chips, then the larger X, drawn from (0, 0).

    Returns (body, glow, width, height, top); top is negative because the X overhangs the letters.
    """
    size, body, cursor = pitch * TOKEN, [], 0.0
    for letter in "TokenMaster":
        rows = GLYPHS[letter]
        for r, line in enumerate(rows):
            for c, cell in enumerate(line):
                if cell == "#":
                    body.append(chip(cursor + c * pitch, r * pitch, size, "url(#ink)"))
        cursor += (len(rows[0]) + 1) * pitch
    xp = pitch * X_SCALE
    x_left, x_top = cursor + pitch * 0.6, (7 * pitch - 7 * xp) / 2
    body += x_chips(x_left, x_top, xp, animate)
    span = 6 * xp + xp * TOKEN
    return body, x_chips(x_left, x_top, xp, False), x_left + span, span, x_top


def defs():
    return ('<defs>'
            f'<linearGradient id="lime" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{LIME}"/>'
            f'<stop offset="1" stop-color="{LIME_DEEP}"/></linearGradient>'
            f'<linearGradient id="ink" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{INK}"/>'
            f'<stop offset="1" stop-color="{INK_SHADE}"/></linearGradient>'
            '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>'
            '</defs>')


STYLE = ("<style>.prune{animation:prune 6s ease-in-out infinite}.p2{animation-delay:.35s}.p3{animation-delay:.7s}"
         "@keyframes prune{0%,55%,100%{opacity:var(--o)}70%,85%{opacity:.05}}"
         + "".join(f".p{k}{{--o:{v}}}" for k, v in PRUNED_OPACITY.items())
         + "@media (prefers-reduced-motion:reduce){.prune{animation:none}}</style>")


def svg_open(width, height, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" width="{width:g}" '
            f'height="{height:g}" role="img" aria-label="{label}">{defs()}{STYLE}')


def plate(width, height, radius, fill):
    return (f'<rect width="{width:g}" height="{height:g}" rx="{radius}" fill="{fill}"/>'
            f'<rect x=".5" y=".5" width="{width - 1:g}" height="{height - 1:g}" rx="{radius - .5:g}" '
            f'fill="none" stroke="{EDGE}"/>')


def mark_svg():
    pitch = 15
    offset = (128 - (6 * pitch + pitch * TOKEN)) / 2
    return (svg_open(128, 128, "TokenMasterX") + plate(128, 128, 28, PLATE)
            + f'<g filter="url(#glow)" opacity=".55">{"".join(x_chips(offset, offset, pitch, False))}</g>'
            + "".join(x_chips(offset, offset, pitch, True)) + "</svg>")


def logo_svg():
    pad = 30
    body, glow, w, h, top = lockup(10, True)
    width, height = round(w + 2 * pad), round(h + 2 * pad)
    move = f'transform="translate({pad} {pad - top:g})"'
    return (svg_open(width, height, "TokenMasterX") + plate(width, height, 20, PLATE)
            + f'<g {move}><g filter="url(#glow)" opacity=".5">{"".join(glow)}</g>{"".join(body)}</g></svg>')


STATS = [("UP TO", "58%", "fewer tokens"), ("UP TO", "54%", "lower cold-start cost"), ("WITH", "0", "drop in pass rate")]


def hero_svg():
    width, height = 1200, 540
    body, glow, w, h, top = lockup(12, True)
    move = f'transform="translate({(width - w) / 2:g} {104 - top:g})"'
    tile_w, gap = 300, 36
    left = (width - (3 * tile_w + 2 * gap)) / 2
    tiles = []
    for i, (eyebrow, number, label) in enumerate(STATS):
        cx = left + i * (tile_w + gap) + tile_w / 2
        tiles.append(
            f'<text x="{cx:g}" y="394" text-anchor="middle" font-family="{MONO}" font-size="12" font-weight="600" '
            f'letter-spacing="2" fill="{MUTED}">{eyebrow}</text>'
            f'<text x="{cx:g}" y="452" text-anchor="middle" font-family="{SANS}" font-size="60" font-weight="800" '
            f'letter-spacing="-1.5" fill="url(#lime)">{number}</text>'
            f'<text x="{cx:g}" y="484" text-anchor="middle" font-family="{SANS}" font-size="17" font-weight="500" '
            f'fill="{INK}">{label}</text>')
    label = ("TokenMasterX. Half the tokens, same answers, for GitHub Copilot. Up to 58% fewer tokens and "
             "up to 54% lower cold-start cost, with no drop in pass rate.")
    return (svg_open(width, height, label)
            + '<defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
            f'<rect x="9" y="9" width="4" height="4" rx="1" fill="{INK}" opacity=".05"/></pattern>'
            '<radialGradient id="halo" cx=".5" cy=".3" r=".55">'
            f'<stop offset="0" stop-color="{LIME}" stop-opacity=".13"/>'
            f'<stop offset="1" stop-color="{LIME}" stop-opacity="0"/></radialGradient></defs>'
            + plate(width, height, 14, BG)
            + f'<rect width="{width}" height="{height}" rx="14" fill="url(#dots)"/>'
            + f'<rect width="{width}" height="{height}" rx="14" fill="url(#halo)"/>'
            + f'<text x="{width / 2:g}" y="72" text-anchor="middle" font-family="{MONO}" font-size="13" '
              f'font-weight="600" letter-spacing="3" fill="{MUTED}">FOR GITHUB COPILOT</text>'
            + f'<g {move}><g filter="url(#glow)" opacity=".6">{"".join(glow)}</g>{"".join(body)}</g>'
            + f'<text x="{width / 2:g}" y="282" text-anchor="middle" font-family="{SANS}" font-size="44" '
              f'font-weight="750" letter-spacing="-1" fill="{INK}">Half the tokens. Same answers.</text>'
            + f'<text x="{width / 2:g}" y="320" text-anchor="middle" font-family="{SANS}" font-size="18" '
              f'fill="{MUTED}">Tool pruning · graph code navigation · cache-safe output · /tokenomics</text>'
            + f'<line x1="{left:g}" y1="356" x2="{width - left:g}" y2="356" stroke="{EDGE}"/>'
            + "".join(tiles) + "</svg>")


PREVIEW = """<!doctype html><meta charset="utf-8"><title>TokenMasterX brand preview</title>
<style>body{{margin:0;font:14px system-ui}}section{{padding:32px}}.dark{{background:#0d1117;color:#e6edf3}}
.light{{background:#fff;color:#1f2328}}img{{display:block;margin:12px 0}}.row{{display:flex;gap:20px;align-items:end}}</style>
<section class="dark"><h3>Hero (GitHub dark)</h3><img src="{hero}" style="width:100%;max-width:1012px">
<h3>Logo and mark</h3><img src="{logo}" style="height:120px">
<div class="row">{marks}</div></section>
<section class="light"><h3>Hero (GitHub light)</h3><img src="{hero}" style="width:100%;max-width:1012px">
<div class="row"><img src="{logo}" style="height:90px">{marks}</div></section>"""


def data_uri(svg):
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", action="store_true", help="also write assets/_brand_preview.html")
    args = parser.parse_args()
    outputs = {"tokenmasterx-mark.svg": mark_svg(), "tokenmasterx-logo.svg": logo_svg(),
               "tokenmasterx-hero.svg": hero_svg()}
    for name, svg in outputs.items():
        (HERE / name).write_text(svg + "\n", encoding="utf-8")
        print(f"wrote assets/{name} ({len(svg):,} bytes)")
    if args.preview:
        mark = data_uri(outputs["tokenmasterx-mark.svg"])
        marks = "".join(f'<img src="{mark}" width="{s}" height="{s}">' for s in (16, 32, 64, 128, 200))
        page = PREVIEW.format(hero=data_uri(outputs["tokenmasterx-hero.svg"]),
                              logo=data_uri(outputs["tokenmasterx-logo.svg"]), marks=marks)
        (HERE / "_brand_preview.html").write_text(page, encoding="utf-8")
        print("wrote assets/_brand_preview.html")


if __name__ == "__main__":
    main()
