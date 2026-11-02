"""Touch swipe checks for the deck, in headless Chromium with a touch screen.

Sends real touch events through a CDP session and checks that a left swipe goes forward, a
right swipe goes back, a right swipe on the first slide stays, a vertical scroll does not
change the slide, a quick flick counts, the leaving slide gets and then loses its --dx exit
offset, and that taps on buttons still work.

Run from the repo root:
    python site/src/checks/swipe_test.py        # serves site/ on a free local port
    python site/src/checks/swipe_test.py URL    # tests a live site, for example
                                                # https://all-the-vibes.github.io/TokenMasterX/

Prints one line per check, then the failed check names (or "none"), and exits 1 if any failed.
The screenshot goes to site/src/checks/out/. Needs Playwright: pip install playwright, then
playwright install chromium (exits 2 without it).
"""
import contextlib
import functools
import http.server
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
SHOTS = ROOT / 'site' / 'src' / 'checks' / 'out'
SHOTS.mkdir(parents=True, exist_ok=True)
CUR = "[...document.querySelectorAll('.slide')].findIndex(s => s.dataset.state === 'current')"
fails = []


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


def check(name, cond, detail=''):
    print('ok  ' if cond else 'FAIL', name, '' if cond else detail)
    if not cond:
        fails.append(name)


with serve(URL) as BASE, sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 375, 'height': 812}, has_touch=True, is_mobile=True, device_scale_factor=2)
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    pg.goto(BASE + '?swipe#overview')
    pg.wait_for_function("document.querySelectorAll('.slide[data-state=current]').length === 1", timeout=15000)
    pg.wait_for_timeout(600)
    cdp = ctx.new_cdp_session(pg)

    def swipe(x0, y0, x1, y1, steps=8, dt=12):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0}]})
        for i in range(1, steps + 1):
            x = x0 + (x1 - x0) * i / steps
            y = y0 + (y1 - y0) * i / steps
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y}]})
            pg.wait_for_timeout(dt)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        pg.wait_for_timeout(450)

    cur = lambda: pg.evaluate(CUR)
    check('starts on the cover', cur() == 0)
    swipe(300, 150, 60, 160)
    check('left swipe goes forward', cur() == 1, cur())
    swipe(60, 150, 300, 160)
    check('right swipe goes back', cur() == 0, cur())
    swipe(60, 150, 300, 160)
    check('right swipe at the first slide stays', cur() == 0, cur())
    swipe(200, 600, 190, 300, steps=10)
    check('a vertical scroll gesture does not change slide', cur() == 0, cur())
    swipe(250, 150, 215, 150, steps=2, dt=4)
    check('a short slow drag under the threshold stays', cur() == 0, cur())
    # a fast short flick counts
    swipe(260, 150, 195, 152, steps=2, dt=0)
    check('a quick flick goes forward', cur() == 1, cur())
    # the leaving slide fades from where the finger let go: --dx is set on release, then cleared
    pg.keyboard.press('Home'); pg.wait_for_timeout(400)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': 320, 'y': 150}]})
    for i in range(1, 9):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': 320 - i * 28, 'y': 152}]})
        pg.wait_for_timeout(10)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    dx = pg.evaluate("document.querySelector('#overview').style.getPropertyValue('--dx')")
    check('release sets the exit offset on the leaving slide', dx.endswith('px') and float(dx[:-2]) < -20, dx)
    pg.wait_for_timeout(700)
    check('and clears it afterwards', pg.evaluate("document.querySelector('#overview').style.getPropertyValue('--dx')") == '')
    # taps still work on buttons (not swallowed by the swipe layer)
    pg.evaluate("location.hash = '#proofs'"); pg.wait_for_timeout(700)
    pg.tap('#claims .claim >> nth=4'); pg.wait_for_timeout(400)
    check('tap pins a claim', pg.get_attribute('#claims .claim >> nth=4', 'aria-pressed') == 'true' and 'Folds.unfoldPaths_foldPaths' in pg.inner_text('#claim-info'))
    pg.evaluate("location.hash = '#results'"); pg.wait_for_timeout(1000)
    pg.screenshot(path=str(SHOTS / 'results_mobile_after.png'))
    check('no console errors', not errors, errors[:3])
    b.close()
print('\nFAILED:', fails if fails else 'none')
sys.exit(1 if fails else 0)
