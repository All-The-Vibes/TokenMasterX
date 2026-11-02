"""End-to-end checks for the deck, run in headless Chromium with real input events.

Covers keyboard and hash navigation, the cover links, the proofs, checks, prompt, estimate,
cache and results interactions, overflow at seven viewport sizes, reduced motion, the no-JS
page, and that the page requests nothing outside its own origin and links out only to the
repo and elan.

Run from the repo root:
    python site/src/checks/deck_test.py        # serves site/ on a free local port
    python site/src/checks/deck_test.py URL    # tests a live site, for example
                                               # https://all-the-vibes.github.io/TokenMasterX/

Prints one line per failed check and a summary, and exits 1 if any check failed.
Screenshots go to site/src/checks/out/. Needs Playwright: pip install playwright, then
playwright install chromium (exits 2 without it).
"""
import contextlib
import functools
import http.server
import pathlib
import sys
import threading
from urllib.parse import urlsplit

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
LINK_REPOS = ('/All-The-Vibes/TokenMasterX', '/leanprover/elan')  # the only github.com repos the deck may link to
fails, passes = [], 0


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
    global passes
    if cond:
        passes += 1
    else:
        fails.append(name)
        print('FAIL', name, detail)


def link_ok(href):
    u = urlsplit(href)
    return u.scheme == 'https' and u.netloc == 'github.com' and any(u.path == r or u.path.startswith(r + '/') for r in LINK_REPOS)


CUR = "[...document.querySelectorAll('.slide')].findIndex(s => s.dataset.state === 'current')"


def open_deck(browser, w=1280, h=720, hash_='overview', reqs=None, **ctx):
    context = browser.new_context(viewport={'width': w, 'height': h}, **ctx)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    if reqs is not None:
        page.on('request', lambda r: reqs.append(r.url))
    page.goto(f'{BASE}?pw={w}x{h}#{hash_}')
    page.wait_for_function(f"document.querySelectorAll('.slide[data-state=current]').length === 1", timeout=15000)
    page.wait_for_timeout(500)
    return context, page, errors


def settle(page, ms=450):
    page.wait_for_timeout(ms)


with serve(URL) as BASE, sync_playwright() as pw:
    browser = pw.chromium.launch()

    # ---------- keyboard, hash, skip link ----------
    ctx, page, errors = open_deck(browser)
    ids = page.evaluate("[...document.querySelectorAll('.slide')].map(s => s.id)")
    check('11 slides', len(ids) == 11, ids)
    cur = lambda: page.evaluate(CUR)
    check('starts on the cover', cur() == 0)
    for key, want in [('ArrowRight', 1), ('ArrowLeft', 0), ('3', 3), ('End', 10), ('Home', 0), ('0', 0), ('9', 9), ('Space', 10), ('Shift+Space', 9), ('PageDown', 10), ('PageUp', 9), ('ArrowRight', 10), ('ArrowRight', 10)]:
        page.keyboard.press(key)
        settle(page, 380)
        check(f'key {key} -> {want}', cur() == want, cur())
    page.keyboard.press('Home'); settle(page, 380)
    check('digit matches eyebrow: 3 is navigation', ids[3] == 'navigation' and page.evaluate("document.querySelector('#navigation .eyebrow b').textContent") == '03')
    check('eyebrows follow slide order', page.evaluate("[...document.querySelectorAll('.slide')].slice(1).map(s => s.querySelector('.eyebrow b')?.textContent).join(',')") == '01,02,03,04,05,06,07,08,09,10')
    page.evaluate("location.hash = '#cache'"); settle(page)
    check('hash routes', cur() == 4)
    page.evaluate("location.hash = '#nonsense'"); settle(page)
    check('unknown hash is ignored', cur() == 4)
    check('only the current slide is interactive', page.evaluate("[...document.querySelectorAll('.slide')].filter(s => !s.inert).length") == 1)
    page.keyboard.press('Home'); settle(page, 380)
    page.focus('.skip'); page.keyboard.press('Enter'); settle(page, 100)
    check('skip link focuses the deck and keeps the slide', page.evaluate("document.activeElement.id") == 'deck' and cur() == 0, page.evaluate("location.hash"))
    # rail
    page.click('#next'); settle(page, 380)
    check('next button', cur() == 1)
    page.click('#prev'); settle(page, 380)
    check('prev button', cur() == 0)
    check('prev is aria-disabled on the cover, not disabled', page.evaluate("document.querySelector('#prev').getAttribute('aria-disabled')") == 'true' and not page.evaluate("document.querySelector('#prev').disabled"))
    page.keyboard.press('End'); settle(page, 380)
    page.focus('#next')
    check('next stays focusable on the last slide', page.evaluate("document.activeElement.id") == 'next')
    # cover links
    page.keyboard.press('Home'); settle(page, 380)
    page.click('.actions a[data-go=proofs]'); settle(page, 500)
    check('cover Proofs link', cur() == ids.index('proofs') and page.evaluate("location.hash") == '#proofs', page.evaluate("location.hash"))
    page.keyboard.press('Home'); settle(page, 380)
    page.click('.proofbar'); settle(page, 500)
    check('cover proof bar link', cur() == ids.index('proofs'))
    check('no console errors (keyboard)', not errors, errors[:3])
    ctx.close()

    # ---------- proofs slide ----------
    ctx, page, errors = open_deck(browser, hash_='proofs')
    page.wait_for_timeout(1400)
    check('the proofs slide explains the concept in three steps', page.locator('#proofs .pipe li').count() == 3)
    shown = page.evaluate("[document.querySelector('.proofbar .pt').textContent, ...[...document.querySelectorAll('#proofs .pipe h3')].map(h => h.textContent)].join(' ')")
    check('the cover strip and the concept steps carry no numbers', not any(ch.isdigit() for ch in shown), shown)
    check('10 claims', page.locator('#claims .claim').count() == 10)
    rest = page.inner_text('#claim-info')
    page.hover('#claims .claim >> nth=0'); settle(page, 350)
    check('hover shows the claim details', 'Cache.bridge_prefix_stable' in page.inner_text('#claim-info') and 'checked by' in page.inner_text('#claim-info').lower())
    page.mouse.move(5, 5); settle(page, 350)
    check('leaving restores the prompt', page.inner_text('#claim-info') == rest, page.inner_text('#claim-info')[:60])
    page.hover('#claims .claim >> nth=5'); page.click('#claims .claim >> nth=5'); settle(page, 350)
    check('click pins', page.get_attribute('#claims .claim >> nth=5', 'aria-pressed') == 'true')
    page.hover('#claims .claim >> nth=1'); settle(page, 300)
    page.mouse.move(5, 5); settle(page, 350)
    check('pinned claim comes back after a hover elsewhere', 'Routing.fired_family_kept' in page.inner_text('#claim-info'), page.inner_text('#claim-info')[:80])
    page.click('#claims .claim >> nth=5'); page.mouse.move(5, 5); settle(page, 350)
    check('second click unpins', page.get_attribute('#claims .claim >> nth=5', 'aria-pressed') == 'false' and page.inner_text('#claim-info') == rest)
    page.focus('#claims .claim >> nth=8'); settle(page, 350)
    check('focus shows details', 'NavCap.assemble_le' in page.inner_text('#claim-info'))
    # quick out-and-back must not land on the default text
    page.hover('#claims .claim >> nth=2'); settle(page, 300)
    box = page.locator('#claims .claim >> nth=2').bounding_box()
    page.mouse.move(box['x'] + 5, box['y'] + box['height'] + 3); page.mouse.move(box['x'] + 8, box['y'] + 4); settle(page, 400)
    check('out and back keeps the hovered claim', 'Shaping.guard_never_expands' in page.inner_text('#claim-info'), page.inner_text('#claim-info')[:60])
    page.screenshot(path=str(SHOTS / 'proofs_1280x720_hover.png'))
    check('no console errors (proofs)', not errors, errors[:3])
    ctx.close()

    # ---------- checks slide ----------
    ctx, page, errors = open_deck(browser, hash_='checks')
    ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=BASE.rstrip('/'))
    page.wait_for_timeout(900)
    state = lambda: page.evaluate("[...document.querySelectorAll('#finds > ul')].map(u => u.dataset.set + ':' + u.hasAttribute('data-off')).join(',')")
    check('fixed list shows first', state() == 'fixed:false,open:true', state())
    page.click('#seg-finds button[data-value=open]'); settle(page, 400)
    check('open list shows after the switch', state() == 'fixed:true,open:false', state())
    check('radio state follows', page.evaluate("[...document.querySelectorAll('#seg-finds button')].map(b => b.getAttribute('aria-checked')).join(',')") == 'false,true')
    vis = page.evaluate("[...document.querySelectorAll('#finds > ul')].map(u => getComputedStyle(u).visibility).join(',')")
    check('hidden list is not exposed', vis == 'hidden,visible', vis)
    page.focus('#seg-finds button[data-value=open]'); page.keyboard.press('ArrowLeft'); settle(page, 400)
    check('arrow keys move inside the radiogroup, not the slide', state() == 'fixed:false,open:true' and page.evaluate(CUR) == ids.index('checks'))
    page.click('[data-copy=c5]'); settle(page, 300)
    check('copy writes the command', page.evaluate("navigator.clipboard.readText()") == 'lake -d proofs build', page.evaluate("navigator.clipboard.readText()"))
    check('copy shows Copied', page.evaluate("document.querySelector('[data-copy=c5]').hasAttribute('data-copied')"))
    page.screenshot(path=str(SHOTS / 'checks_1280x720.png'))
    check('no console errors (checks)', not errors, errors[:3])
    ctx.close()

    # ---------- prompt, estimate, cache, results ----------
    ctx, page, errors = open_deck(browser, hash_='prompt')
    page.wait_for_timeout(700)
    page.click('#seg-setup button[data-value=lean]'); settle(page, 900)
    check('lean first-call number', page.inner_text('#first-val') == '6,034' and page.inner_text('#tools-val') == '1,945')
    check('stay pill names the probed tools', 'apply_patch' in page.evaluate("document.querySelector('#tools .tool[data-kind=core]').dataset.info") and '8 built-in' in page.inner_text('#tools'))
    check('removed pills say so to a screen reader', page.evaluate("document.querySelector('#tools .tool[data-kind=fam] .sr').textContent") == ' (removed)')
    page.click('#seg-setup button[data-value=stock]'); settle(page, 900)
    check('stock restores the numbers and the sr text', page.inner_text('#first-val') == '13,589' and page.evaluate("document.querySelector('#tools .tool[data-kind=fam] .sr').textContent") == '')
    page.hover('#tools .tool[data-kind=fam] >> nth=1'); settle(page, 350)
    check('tool hover info mentions the launch prompt', 'launch prompt' in page.inner_text('#info') and 'TOKENMASTER_KEEP_TOOLS' in page.inner_text('#info'), page.inner_text('#info'))
    page.screenshot(path=str(SHOTS / 'prompt_1280x720.png'))
    page.evaluate("location.hash = '#estimate'"); settle(page, 600)
    page.evaluate("const c = document.querySelector('#calls'); c.value = 1000; c.dispatchEvent(new Event('input', {bubbles: true}))"); settle(page, 500)
    check('estimate at 1,000 calls', page.inner_text('#est-tok') == '7,555,000' and page.inner_text('#est-usd') == '$7.56', page.inner_text('#est-usd'))
    check('estimate copy no longer says the first call is a write', 'first call of every session' not in page.inner_text('#estimate'))
    page.evaluate("location.hash = '#cache'"); settle(page, 600)
    page.click('#seg-cache button[data-value=rewrite]'); settle(page, 600)
    check('cache rewrite tally', page.inner_text('#t-sent') == '14k' and page.inner_text('#t-write') == '6k' and page.inner_text('#t-cost') == '8.3k')
    page.evaluate("location.hash = '#results'"); settle(page, 600)
    got = []
    for rid in ['nov1', 'oct27', 'prs6repo', 'prs6dj']:
        page.click(f'#seg-run button[data-value={rid}]'); settle(page, 700)
        got.append(page.evaluate("[...document.querySelectorAll('#arms .arm')].filter(a => !a.hasAttribute('data-absent')).length"))
    check('runs show 2,1,2,2 arms', got == [2, 1, 2, 2], got)
    check('the .v cells have sentence text for screen readers', 'lower, 95% interval' in page.evaluate("document.querySelector('#arms .v .sr').textContent"))
    check('tabular numerals survive', page.evaluate("getComputedStyle(document.querySelector('#first-val')).fontVariantNumeric") == 'tabular-nums')
    check('no console errors (interactions)', not errors, errors[:3])
    ctx.close()

    # ---------- overflow and layout across viewports ----------
    sizes = [(1280, 720), (1366, 650), (1366, 768), (1440, 900), (1920, 1080), (768, 1024), (375, 812)]
    table = {}
    for (w, h) in sizes:
        ctx, page, errors = open_deck(browser, w, h)
        row = {}
        for sid in ids:
            page.evaluate(f"location.hash = '#{sid}'")
            page.wait_for_timeout(520)
            row[sid] = page.evaluate("""(sid) => { const s = document.getElementById(sid); const wide = [...s.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > innerWidth + 1 && !e.closest('.seg-scroll') && !e.closest('.track') && !e.closest('svg') && getComputedStyle(e).visibility !== 'hidden'; }).length; return [s.scrollHeight - s.clientHeight, wide]; }""", sid)
            if (w, h) in [(1280, 720), (375, 812)]:
                page.screenshot(path=str(SHOTS / f'{sid}_{w}x{h}.png'))
        table[(w, h)] = row
        check(f'no console errors at {w}x{h}', not errors, errors[:3])
        ctx.close()
    for (w, h), row in table.items():
        over = {k: v[0] for k, v in row.items() if v[0] > 0}
        wide = {k: v[1] for k, v in row.items() if v[1] > 0}
        print(f'{w}x{h}: vertical overflow {over or "none"} | horizontal overflow {wide or "none"}')
        if w >= 1280:
            check(f'fits without scrolling at {w}x{h}', not over, over)
        check(f'no sideways overflow at {w}x{h}', not wide, wide)

    # ---------- reduced motion ----------
    ctx, page, errors = open_deck(browser, hash_='proofs', reduced_motion='reduce')
    page.wait_for_timeout(300)
    r = page.evaluate("""() => ({
      reveal: getComputedStyle(document.querySelector('#proofs [data-reveal]')).opacity,
      ck: getComputedStyle(document.querySelector('#claims .ck'), '::before').opacity,
      pipe: getComputedStyle(document.querySelector('#proofs .pipe')).opacity,
      segOnTransition: getComputedStyle(document.querySelector('#seg-finds .seg-on')).transitionDuration })""")
    check('reduced motion: content is visible at once', r['reveal'] == '1' and r['ck'] == '1' and r['pipe'] == '1' and r['segOnTransition'] in ('0s', '0.001s'), r)
    page.screenshot(path=str(SHOTS / 'proofs_reduced.png'))
    ctx.close()

    # ---------- no JavaScript ----------
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720}, java_script_enabled=False)
    page = ctx.new_page()
    page.goto(f'{BASE}?nojs')
    page.wait_for_timeout(400)
    r = page.evaluate("""() => ({
      visible: [...document.querySelectorAll('.slide')].filter(s => getComputedStyle(s).visibility === 'visible' && getComputedStyle(s).opacity === '1').length,
      segOn: [...document.querySelectorAll('.seg-on')].filter(e => getComputedStyle(e).display !== 'none').length,
      cd: getComputedStyle(document.querySelector('.cd')).display })""")
    check('no-JS: every slide is visible, no stray lime boxes, details shown', r['visible'] == 11 and r['segOn'] == 0 and r['cd'] != 'none', r)
    page.screenshot(path=str(SHOTS / 'nojs_top.png'), full_page=False)
    html = page.content()
    check('no-JS page serves the proof claims as text', 'Cache.bridge_prefix_stable' in html and 'Navigation results stay within 2,400 tokens' in html)
    ctx.close()

    # ---------- no outside requests, outbound links ----------
    reqs = []
    ctx, page, _ = open_deck(browser, reqs=reqs)
    for sid in ids:
        page.evaluate(f"location.hash = '#{sid}'")
        page.wait_for_timeout(250)
    own = '{0.scheme}://{0.netloc}/'.format(urlsplit(BASE))
    outside = [u for u in reqs if not u.startswith(own) and not u.startswith('data:')]
    check('every request goes to the page origin', not outside, outside)
    links = sorted({a for a in page.evaluate("[...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))") if not a.startswith('#')})
    print('outbound links:\n  ' + '\n  '.join(links))
    check('outbound links point only to the repo and elan', all(map(link_ok, links)), [a for a in links if not link_ok(a)])
    ctx.close()

    browser.close()

print(f'\n{passes} passed, {len(fails)} failed')
if fails:
    print('FAILED:', '; '.join(fails))
    sys.exit(1)
