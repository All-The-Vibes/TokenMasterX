#!/usr/bin/env python3
"""
TokenMaster — generative meme creator.

Deterministic, dependency-free SVG generator.
Renders the ultimate "Developer Bell Curve" (Midwit) meme for TokenMaster.
Extremely clean, modern near-black navy theme matching the official repository.
"""
from __future__ import annotations

import argparse
import math

# Colors matching the main hero art
BG_TOP = "#04060e"         # near-black navy
BG_BOT = "#0a1430"
BLOOM_I = "#4f46e5"        # indigo bloom
BLOOM_C = "#0891b2"        # cyan bloom
TEXT = "#f4f7ff"
TEXT_DIM = "#94a3c8"
ACCENT = "#a5b4fc"
PROMPT = "#34e7c8"         # terminal caret / prompt glyph
ROSE = "#f43f5e"           # stressed rose/pink
CYAN = "#22d3ee"

def generate(w: int = 1200, h: int = 600) -> str:
    # We will generate a mathematically perfect bell curve
    # y = base - height * exp(-((x - mu) / std)**2)
    y_base = 480
    height = 320
    mu = 600
    std = 180

    points = []
    for x in range(100, 1101, 4):
        # Calculate gaussian curve
        y = y_base - height * math.exp(-((x - mu) / std)**2)
        points.append(f"{x:.1f},{y:.1f}")
    curve_path = "M " + " L ".join(points)

    P: list[str] = []
    P.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" role="img" '
        f'aria-label="TokenMaster Bell Curve Meme">'
    )
    
    # SVG Definitions
    P.append(f"""<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOT}"/>
  </linearGradient>
  <radialGradient id="bloomLeft" cx="0.25" cy="0.70" r="0.5">
    <stop offset="0" stop-color="{BLOOM_I}" stop-opacity="0.35"/>
    <stop offset="1" stop-color="{BLOOM_I}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="bloomRight" cx="0.80" cy="0.70" r="0.5">
    <stop offset="0" stop-color="{BLOOM_C}" stop-opacity="0.35"/>
    <stop offset="1" stop-color="{BLOOM_C}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="bloomCenter" cx="0.5" cy="0.3" r="0.4">
    <stop offset="0" stop-color="{ROSE}" stop-opacity="0.25"/>
    <stop offset="1" stop-color="{ROSE}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="curveGrad" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{ACCENT}"/>
    <stop offset="0.5" stop-color="{ROSE}"/>
    <stop offset="1" stop-color="{CYAN}"/>
  </linearGradient>
  <linearGradient id="wizardHatGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#818cf8"/>
    <stop offset="1" stop-color="{BLOOM_I}"/>
  </linearGradient>
  <filter id="glow" x="-30%" y="-30%" width="160%" height="180%">
    <feGaussianBlur stdDeviation="10"/>
  </filter>
  <filter id="softGlow" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="4"/>
  </filter>
</defs>""")

    # Backgrounds
    P.append(f'<rect width="{w}" height="{h}" fill="url(#bg)"/>')
    P.append(f'<rect width="{w}" height="{h}" fill="url(#bloomLeft)"/>')
    P.append(f'<rect width="{w}" height="{h}" fill="url(#bloomRight)"/>')
    P.append(f'<rect width="{w}" height="{h}" fill="url(#bloomCenter)"/>')

    # Faint dot-grid texture
    P.append('<g fill="#ffffff" opacity="0.015">')
    for gx in range(30, w, 40):
        for gy in range(30, h, 40):
            P.append(f'<circle cx="{gx}" cy="{gy}" r="1"/>')
    P.append("</g>")

    # Title & Subtitle
    P.append(
        f'<text x="600" y="55" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" '
        f'font-size="28" font-weight="800" fill="{TEXT}" letter-spacing="-0.5">THE AGENTIC CODE-UNDERSTANDING BELL CURVE</text>'
    )
    P.append(
        f'<text x="600" y="80" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" '
        f'font-size="13.5" fill="{TEXT_DIM}">How different mindsets approach codebase traversal in agent harnesses</text>'
    )

    # Draw the main Bell Curve with glowing effect
    # Glow underlay
    P.append(f'<path d="{curve_path}" fill="none" stroke="url(#curveGrad)" stroke-width="12" filter="url(#glow)" opacity="0.45" stroke-linecap="round"/>')
    # Soft glow underlay
    P.append(f'<path d="{curve_path}" fill="none" stroke="url(#curveGrad)" stroke-width="5" filter="url(#softGlow)" opacity="0.8" stroke-linecap="round"/>')
    # Crisp line on top
    P.append(f'<path d="{curve_path}" fill="none" stroke="url(#curveGrad)" stroke-width="2.5" stroke-linecap="round"/>')

    # Baseline of the bell curve
    P.append(f'<line x1="100" y1="{y_base}" x2="1100" y2="{y_base}" stroke="{TEXT_DIM}" stroke-width="1" opacity="0.15" stroke-dasharray="4 4"/>')

    # --- LEFT SIDE: THE BEGINNER / LOW IQ (x=240, y=y_base) ---
    lx = 240
    ly = y_base - 30
    # Left Face (Simple Happy Noob)
    P.append(f'<g transform="translate({lx}, {ly-30})">')
    P.append(f'  <circle cx="0" cy="0" r="22" fill="{BG_TOP}" stroke="{ACCENT}" stroke-width="2.5"/>')
    P.append(f'  <circle cx="-8" cy="-5" r="3" fill="{ACCENT}"/>')
    P.append(f'  <circle cx="8" cy="-5" r="3" fill="{ACCENT}"/>')
    P.append(f'  <path d="M -10,6 Q 0,16 10,6" fill="none" stroke="{ACCENT}" stroke-width="2.5" stroke-linecap="round"/>')
    P.append(f'</g>')
    # Left Labels
    P.append(f'<text x="{lx}" y="{ly+30}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="18" font-weight="800" fill="{ACCENT}">"just grep it"</text>')
    P.append(f'<text x="{lx}" y="{ly+55}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="13" fill="{TEXT_DIM}">Turn 1: grep. Done.</text>')
    P.append(f'<text x="{lx}" y="{ly+75}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="13" font-weight="700" fill="{PROMPT}">~2,000 context tokens</text>')
    P.append(f'<text x="{lx}" y="{ly+95}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="11.5" fill="{TEXT_DIM}" opacity="0.8">IQ: 80</text>')

    # --- MIDDLE: THE MIDWIT (x=600, y=y_base - height) ---
    cx = 600
    cy = y_base - height
    # Midwit Face (Crying / Stressed)
    P.append(f'<g transform="translate({cx}, {cy-65})">')
    P.append(f'  <circle cx="0" cy="0" r="22" fill="{BG_TOP}" stroke="{ROSE}" stroke-width="2.5"/>')
    # Crying/angry eyes
    P.append(f'  <path d="M -10,-8 L -4,-2 M -10,-2 L -4,-8" fill="none" stroke="{ROSE}" stroke-width="2.5" stroke-linecap="round"/>')
    P.append(f'  <path d="M 4,-8 L 10,-2 M 4,-2 L 10,-8" fill="none" stroke="{ROSE}" stroke-width="2.5" stroke-linecap="round"/>')
    # Tears (glowing blue)
    P.append(f'  <path d="M -7,2 Q -7,10 -9,10 Q -11,10 -11,7 Z" fill="{CYAN}" opacity="0.95" filter="url(#softGlow)"/>')
    P.append(f'  <path d="M 7,2 Q 7,10 5,10 Q 3,10 3,7 Z" fill="{CYAN}" opacity="0.95" filter="url(#softGlow)"/>')
    # Squiggly stressed mouth
    P.append(f'  <path d="M -10,8 Q -5,3 0,8 Q 5,13 10,8" fill="none" stroke="{ROSE}" stroke-width="2.5" stroke-linecap="round"/>')
    P.append(f'</g>')
    # Midwit wordy crying bubble/text block
    P.append(f'<g transform="translate({cx}, 200)">')
    P.append(f'  <text x="0" y="10" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="14.5" font-weight="800" fill="{ROSE}">"NOOO! You can\'t just route to a graph!</text>')
    P.append(f'  <text x="0" y="30" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="12.5" fill="{TEXT_DIM}">The LLM must recursively search the directory,</text>')
    P.append(f'  <text x="0" y="48" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="12.5" fill="{TEXT_DIM}">read 15 huge files, load embeddings, run cosine</text>')
    P.append(f'  <text x="0" y="66" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="12.5" fill="{TEXT_DIM}">similarity on every turn, and re-read the entire</text>')
    P.append(f'  <text x="0" y="84" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="12.5" fill="{TEXT_DIM}">accumulated transcript turn after turn to build</text>')
    P.append(f'  <text x="0" y="102" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="12.5" fill="{TEXT_DIM}">an organic, emergent mental model of the code!"</text>')
    P.append(f'  <text x="0" y="128" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="13" font-weight="800" fill="{ROSE}">105,000+ cumulative tokens processed 💸</text>')
    P.append(f'  <text x="0" y="148" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="11.5" fill="{TEXT_DIM}" opacity="0.8">IQ: 105</text>')
    P.append(f'</g>')

    # --- RIGHT SIDE: THE GURU / HIGH IQ (x=960, y=y_base) ---
    rx = 960
    ry = y_base - 30
    # Right Face (Wise Wizard)
    P.append(f'<g transform="translate({rx}, {ry-30})">')
    P.append(f'  <circle cx="0" cy="0" r="22" fill="{BG_TOP}" stroke="{CYAN}" stroke-width="2.5"/>')
    # Serene closed eyes
    P.append(f'  <path d="M -9,-4 Q -5,-1 -1,-4" fill="none" stroke="{CYAN}" stroke-width="2.5" stroke-linecap="round"/>')
    P.append(f'  <path d="M 1,-4 Q 5,-1 9,-4" fill="none" stroke="{CYAN}" stroke-width="2.5" stroke-linecap="round"/>')
    # Wise smile
    P.append(f'  <path d="M -8,6 Q 0,12 8,6" fill="none" stroke="{CYAN}" stroke-width="2.5" stroke-linecap="round"/>')
    # Glowing Halo above wizard
    P.append(f'  <ellipse cx="0" cy="-30" rx="18" ry="5" fill="none" stroke="{PROMPT}" stroke-width="2" opacity="0.8" filter="url(#softGlow)"/>')
    # Wizard Hat
    # brim
    P.append(f'  <path d="M -22,-15 C -10,-19 10,-19 22,-15" fill="none" stroke="{CYAN}" stroke-width="2.5" stroke-linecap="round"/>')
    # cone
    P.append(f'  <path d="M -14,-17 Q 0,-50 5,-55 Q 2,-30 14,-17 Z" fill="url(#wizardHatGrad)" stroke="{CYAN}" stroke-width="2" stroke-linejoin="round"/>')
    P.append(f'</g>')
    # Right Labels
    P.append(f'<text x="{rx}" y="{ry+30}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="18" font-weight="800" fill="{CYAN}">"just route to prebuilt graph"</text>')
    P.append(f'<text x="{rx}" y="{ry+55}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="13" fill="{TEXT_DIM}">TokenMaster: 1 query. Done.</text>')
    P.append(f'<text x="{rx}" y="{ry+75}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="13" font-weight="700" fill="{PROMPT}">5,500 tokens (73% cheaper) ⚡</text>')
    P.append(f'<text x="{rx}" y="{ry+95}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="11.5" fill="{TEXT_DIM}" opacity="0.8">IQ: 140</text>')

    # Footer badge / CLI representation
    P.append(
        f'<rect x="420" y="530" width="360" height="36" rx="6" fill="#0c1938" stroke="{CYAN}" stroke-width="1" opacity="0.8"/>'
    )
    P.append(
        f'<text x="600" y="553" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="13.5" fill="{TEXT}">'
        f'<tspan fill="{PROMPT}" font-weight="bold">❯ </tspan>/token-master  <tspan fill="{TEXT_DIM}">—  cost model: solved.</tspan></text>'
    )

    P.append("</svg>")
    return "\n".join(P)

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate TokenMaster bell curve meme (SVG).")
    ap.add_argument("--out", default="assets/tokenmaster-meme.svg")
    args = ap.parse_args()

    svg = generate()
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {args.out} ({len(svg):,} bytes)")

if __name__ == "__main__":
    main()
