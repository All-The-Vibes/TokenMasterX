"""Runs axe-core on every slide at a desktop (1280x720) and a phone (375x812) size.

Uses the WCAG 2.0, 2.1 and 2.2 A and AA rules plus axe's best-practice rules. Any violation
fails the run (exit 1). Items axe lists as "incomplete" (it could not decide, so a person has
to look) are printed but do not fail it.

Run from the repo root:
    python site/src/checks/axe_run.py        # serves site/ on a free local port
    python site/src/checks/axe_run.py URL    # tests a live site, for example
                                             # https://all-the-vibes.github.io/TokenMasterX/

axe-core is read from $AXE_JS, else from site/src/checks/node_modules/axe-core/axe.min.js.
To install it, run "npm install axe-core --no-save --no-package-lock" inside site/src/checks
(the flags keep npm from writing a package.json and a lockfile there). Needs Playwright:
pip install playwright, then playwright install chromium. Exits 2 if either is missing.
"""
import contextlib
import functools
import http.server
import os
import pathlib
import sys
import threading

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('Playwright is not installed: run "pip install playwright", then "playwright install chromium".')
    sys.exit(2)

sys.stdout.reconfigure(errors='replace')  # page text can hold characters the console codepage lacks
ROOT = pathlib.Path(__file__).resolve().parents[3]
URL = sys.argv[1] if len(sys.argv) > 1 else None
DEFAULT_AXE = ROOT / 'site' / 'src' / 'checks' / 'node_modules' / 'axe-core' / 'axe.min.js'
AXE = next((p for p in (os.environ.get('AXE_JS'), DEFAULT_AXE) if p and pathlib.Path(p).is_file()), None)
if not AXE:
    print('axe-core not found: run "npm install axe-core --no-save --no-package-lock" inside site/src/checks, or set AXE_JS to the path of axe.min.js.')
    sys.exit(2)
seen = {}
runs = 0


@contextlib.contextmanager
def serve(url):
    """Yield url as given, or serve site/ on a free local port until the block ends."""
    if url:
        yield url
        return

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT / 'site')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown()
        server.server_close()


with serve(URL) as BASE, sync_playwright() as pw:
    b = pw.chromium.launch()
    for (w, h, label) in [(1280, 720, 'desktop'), (375, 812, 'mobile')]:
        ctx = b.new_context(viewport={'width': w, 'height': h})
        pg = ctx.new_page()
        pg.goto(BASE + '?axe#overview')
        pg.wait_for_function("document.querySelectorAll('.slide[data-state=current]').length === 1", timeout=15000)
        pg.add_script_tag(path=str(AXE))
        version = pg.evaluate('axe.version')
        ids = pg.evaluate("[...document.querySelectorAll('.slide')].map(s => s.id)")
        for sid in ids:
            pg.evaluate(f"location.hash = '#{sid}'")
            pg.wait_for_timeout(900)
            res = pg.evaluate("""async () => {
              const r = await axe.run(document, {resultTypes: ['violations', 'incomplete'], runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']}});
              const pick = (list) => list.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes.slice(0, 2).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\\n').slice(0, 2).join(' | ').slice(0, 220))}));
              return {violations: pick(r.violations), incomplete: pick(r.incomplete)};
            }""")
            runs += 1
            for kind in ('violations', 'incomplete'):
                for v in res[kind]:
                    key = (label, kind, v['id'])
                    seen.setdefault(key, []).append((sid, v))
        ctx.close()
    b.close()

for (label, kind, vid), items in sorted(seen.items()):
    slides = sorted({s for s, _ in items})
    imp = items[0][1]['impact']
    print(f'[{label}] {kind}: {vid} ({imp}) on {len(slides)} slide(s): {", ".join(slides)}')
    for s, v in items[:1]:
        for smp in v['sample']:
            print('     ', smp)

violated = [k for k in seen if k[1] == 'violations']
print(f'\naxe-core {version}, {runs} slide views: {len(violated)} violated rule(s), {len(seen) - len(violated)} incomplete rule(s)')
sys.exit(1 if violated else 0)
