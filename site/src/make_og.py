"""Render the link-preview card, site/og.png, from site/src/og.html.

    python site/src/make_og.py

Link previews (Reddit, Slack, Discord, X) show this 1200 by 630 image. It needs Playwright and Chromium, the same as
the checks: pip install playwright, then playwright install chromium. The PNG is committed, because Pages serves it
as is. The fonts come from the machine that renders it, so regenerate it on one machine and commit the result.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
import build  # noqa: E402  (draws the wordmark the same way the page does)

OUT = SRC.parent / 'og.png'


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit('make_og.py: Playwright is not installed. Run: pip install playwright, then: playwright install chromium')
    wordmark, _mark, _favicon = build.logo_parts()
    page_html = (SRC / 'og.html').read_text(encoding='utf-8').replace('{{WORDMARK}}', wordmark)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
        page.set_content(page_html)
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT), clip={'x': 0, 'y': 0, 'width': 1200, 'height': 630})
        browser.close()
    print(f'wrote {OUT.relative_to(build.ROOT)} ({OUT.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
