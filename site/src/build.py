"""Build site/index.html from the parts in site/src and the repository's own files.

    python site/src/build.py            write site/index.html
    python site/src/build.py --check    rebuild in memory and fail if site/index.html differs

Hand-written parts: body.html, style.css, app.js. Everything else is made at build time:

- the wordmark, the header mark and the favicon, drawn by assets/generate_logo.py
- the results data, read from evidence/*/analysis.json
- the two proof slides, which list the claims, what each holds when, and what writing the proofs found

The build stops if a theorem or test name that a proof slide prints no longer exists, or if proofs/README.md lists
a different number of claims or findings than the slides, so the page cannot drift from the proofs.
Only index.html is published; see site/src/README.md. Standard library only.
"""
import argparse
import ast
import html as htmllib
import json
import re
import sys
import urllib.parse
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parents[1]
OUT = ROOT / 'site' / 'index.html'
PROOFS = ROOT / 'proofs'
TESTS = ROOT / 'token-master-plugin' / 'skills' / 'token-master' / 'tests' / 'test_proof_conformance.py'
REPO = 'https://github.com/All-The-Vibes/TokenMasterX'


def fail(message):
    raise SystemExit(f'build.py: {message}')


def part(name):
    return (SRC / name).read_text(encoding='utf-8')


# ---------- the logo, drawn by assets/generate_logo.py ----------
def logo_parts():
    sys.path.insert(0, str(ROOT / 'assets'))
    import generate_logo as g
    body, glow, w, h, top = g.lockup(12, True)
    wordmark = (f'<svg class="wordmark" viewBox="0 {top:g} {w:g} {h:g}" role="img" aria-label="TokenMasterX">'
                + g.defs() + f'<g filter="url(#glow)" opacity=".6">{"".join(glow)}</g>' + ''.join(body) + '</svg>')
    mark = '<svg class="mark" viewBox="0 0 22 22" aria-hidden="true">' + ''.join(g.x_chips(0, 0, 3.2, True)) + '</svg>'
    favicon = 'data:image/svg+xml,' + urllib.parse.quote(g.mark_svg(), safe="/:=,;() '!*-._~").replace("'", '%27')
    return wordmark, mark, favicon


# ---------- the results, read from the committed analysis files ----------
def results_json():
    def load(path):
        return json.loads((ROOT / path).read_text(encoding='utf-8'))

    def metric(e):  # a change and its 95% CI as positive reductions, in percent
        return {'v': round(-e['change'] * 100, 2), 'lo': round(-e['ci95'][1] * 100, 2), 'hi': round(-e['ci95'][0] * 100, 2)}

    def arm(name, raw, cold, billed):
        return {'name': name, 'raw': metric(raw), 'cold': metric(cold), 'billed': metric(billed), 'note': ''}

    lean = load('evidence/lean-20261101/analysis.json')['django_15_tasks']
    nof = load('evidence/default-nolean-20261101/analysis.json')['django_15_tasks']
    d27 = load('evidence/default-routing-20261027/analysis.json')['django_15_tasks']
    p6 = load('evidence/prs6-copilot-1.0.98-20261026/analysis.json')

    def p6arm(block, model, label):
        m = p6[block][model]
        return arm(label, m['raw_tokens'], m['usd_if_every_first_call_cold'], m['usd_as_run'])

    runs = [
        {'id': 'nov1', 'label': 'Nov 1', 'title': 'Default routing, Copilot CLI 1.0.105',
         'sub': 'GPT-6 Astra, 15 Django caller lookups. Each arm against its own stock run.',
         'arms': [arm('--lean', lean['raw_tokens'], lean['usd_cold'], lean['usd_as_run']),
                  arm('No flags', nof['raw_tokens'], nof['usd_cold'], nof['usd_as_run'])]},
        {'id': 'oct27', 'label': 'Oct 27', 'title': 'Default routing, Copilot CLI 1.0.104',
         'sub': 'GPT-6 Astra, 15 Django caller lookups. The lean tool set was the launcher default then.',
         'arms': [arm('Lean tool set', d27['raw_tokens'], d27['usd_cold'], d27['usd_as_run'])]},
        {'id': 'prs6repo', 'label': 'PRS-6 repo', 'title': 'Pre-registered, relay mode, Copilot CLI 1.0.98',
         'sub': 'This repository, 29 tasks per model. Lean tool set, graph navigation and the request bridge.',
         'arms': [p6arm('repository_29_tasks', 'gpt-6-astra', 'GPT-6 Astra'),
                  p6arm('repository_29_tasks', 'claude-opus-5.5', 'Claude Opus 5.5')]},
        {'id': 'prs6dj', 'label': 'PRS-6 Django', 'title': 'Pre-registered, relay mode, Copilot CLI 1.0.98',
         'sub': 'Django 5.2, 15 caller lookups per model. Lean tool set, graph navigation and the request bridge.',
         'arms': [p6arm('django_15_tasks', 'gpt-6-astra', 'GPT-6 Astra'),
                  p6arm('django_15_tasks', 'claude-opus-5.5', 'Claude Opus 5.5')]},
    ]
    first_call = {'stock': lean['first_call_median']['stock']['input'], 'nolean': nof['first_call_median']['tm']['input'],
                  'lean': lean['first_call_median']['tm']['input']}
    return json.dumps({'runs': runs, 'firstCallInput': first_call}, separators=(',', ':'))


# ---------- what the proof slides are checked against ----------
def strip_lean_comments(s):
    s = re.sub(r'/-.*?-/', '', s, flags=re.S)
    return re.sub(r'--[^\n]*', '', s)


DECL = r'(?m)^[ \t]*(?:@\[[^\]]*\][ \t]*)?(?:(?:private|protected|nonrec)[ \t]+)*(?:theorem|lemma)[ \t]+([^\s:({\[]+)'


def lean_declarations():
    """Theorem and lemma names per module."""
    names = {}
    files = sorted((PROOFS / 'TokenMasterProofs').glob('*.lean'))
    if not files:
        fail(f'no Lean files under {PROOFS}')
    for p in files:
        text = strip_lean_comments(p.read_text(encoding='utf-8'))
        if re.search(r'\bsorry\b', text):
            fail(f'{p.name} contains sorry')
        names[p.stem] = set(re.findall(DECL, text))
    return names


def test_functions():
    tree = ast.parse(TESTS.read_text(encoding='utf-8'))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}


def written_up():
    """How many summary claims and findings proofs/README.md lists."""
    readme = (PROOFS / 'README.md').read_text(encoding='utf-8')

    def section(title):
        m = re.search(r'(?ms)^## ' + re.escape(title) + r'\n(.*?)(?=^## |\Z)', readme)
        return m.group(1) if m else fail('proofs/README.md has no section ' + title)

    return dict(claims=len([r for r in section('Summary').splitlines() if r.startswith('|')]) - 2,
                open=len(re.findall(r'(?m)^\d+\. ', section('Findings'))),
                fixed=len(re.findall(r'(?m)^- ', section('Fixed'))))


# ---------- the proof slides: what is claimed, and what each claim holds when ----------
CLAIMS = [
    dict(text="The bridge never changes bytes the provider already cached",
         lean=['Cache.bridge_prefix_stable', 'Cache.cache_prefix_kept'],
         holds="Assumes call ids are never reused, the client sends the same instructions and tools on every call, and the provider caches them ahead of the items. A lone surrogate in a tool output breaks the token counter.",
         tests=['test_bridge_rewrite_keeps_history_prefix'], flag='open finding'),
    dict(text="Policy v6 without guidance never changes an earlier message",
         lean=['Cache.shaping_prefix_stable'],
         holds="Proved for the shaping map. The runtime keeps it unless shaping would pass a `max_input_tokens` cap. Assumes call ids are never reused.",
         tests=['test_v6_plans_keep_earlier_messages', 'test_runtime_keeps_v6_shaping']),
    dict(text="Shaping never makes a tool result bigger",
         lean=['Shaping.guard_never_expands', 'Shaping.request_bytes_never_grow'],
         holds="True in counted tokens and in bytes. That GitHub's billed count falls when the cl100k count falls is an assumption.",
         tests=['test_shaped_results_never_expand']),
    dict(text="Policies v1 to v4 never grow a request",
         lean=['Policy.greedy_never_expands', 'Policy.protected_unchanged'],
         holds="They also never edit a protected message. A test checks this for policy v1.",
         tests=['test_plan_request_never_expands_and_keeps_protected_messages']),
    dict(text="The rg and glob folds are lossless",
         lean=['Folds.unfoldPaths_foldPaths', 'Folds.unfold_foldSearchChecked', 'Folds.foldSearch_not_injective'],
         holds="`fold_paths` gives back its exact input. `fold_search` refuses any input it could not give back, and a proof shows the refusal is needed: without it, two different inputs fold to the same text.",
         tests=['test_fold_paths_round_trip', 'test_fold_search_round_trip', 'test_fold_search_refuses_entry_like_copied_lines']),
    dict(text="Routing keeps every family whose trigger fires",
         lean=['Routing.fired_family_kept', 'Routing.excluded_subset_lean', 'Routing.default_excludes_nothing'],
         holds="Proved for the model, which drops only the 13 auxiliary tools. That the launcher routes only with `--lean` is a definition in the model, checked on `main` by a test. The triggers are keyword rules and miss some phrasings: \"have an agent review this diff\" drops `task`.",
         tests=['test_routing_default_sends_every_tool', 'test_routing_lists_match_the_lean_model', 'test_routing_fired_families_are_kept'], flag='open finding'),
    dict(text="A recorded --lean resume keeps its session's tool list",
         lean=['Routing.resume_same_list', 'Routing.resume_chain_keeps_first_list'],
         holds="Proved for the model, when the resume's `TOKENMASTER_KEEP_TOOLS` adds no tool. Which session record applies is the launcher's lookup, which the conformance tests check. A resume the launcher cannot tie to a record is routed again, and a resume without `--lean` sends every tool.",
         tests=['test_routing_resume_keeps_the_first_list']),
    dict(text="In BYOK mode, sessions that differ only in folder share a system prompt",
         lean=['SessionPrefix.system_same_across_sessions', 'SessionPrefix.folder_recoverable'],
         holds="There is exactly one folder line, and only the BYOK bridge does the rewrite. The folder path is assumed to have no newline, and whitespace around it is not recovered after the move.",
         tests=['test_session_prefix_same_system_and_recoverable_folder'], flag='open finding'),
    dict(text="Navigation results stay within 2,400 tokens, by the server's count",
         lean=['NavCap.assemble_le', 'NavCap.fit_prefix', 'NavCap.uncut_overflow_attained'],
         holds="Counted in the navigation server's own counter, with every result measured whole. Its fallback estimate can undercount non-ASCII text. The proofs found a case that reached 2,401 tokens, and it is fixed.",
         tests=['test_navigation_results_within_budget', 'test_uncut_read_within_budget', 'test_fit_matches_the_lean_model', 'test_assemble_matches_the_lean_model']),
    dict(text="The measurement definitions have the properties the protocol needs",
         lean=['Measurement.cold_term_is_coldened_charge', 'Measurement.ratio_of_sums_ge', 'Measurement.resample_within_task_range', 'Measurement.hero_monotone'],
         holds="Cold repricing is exactly the extra charge of a cold cache, and the bootstrap interval stays within the per-task range. The recorded data match. Not proved: the interval's 95% coverage, and the Wilcoxon and Holm-Bonferroni steps.",
         tests=['test_cold_repricing_matches_the_definition', 'test_bootstrap_interval_within_task_range', 'test_hero_verdicts_follow_the_rule', 'test_cache_writes_never_cost_less_than_reads']),
]
FIXED = [
    "Navigation results could pass the 2,400-token cap: footers sat outside the budget, and one branch skipped a newline (2,401 tokens observed). Every result is now measured whole.",
    "`fold_search` was not lossless when a copied line looked like a folded entry. It now refuses to fold that input.",
    "`fold_paths` dropped trailing newlines. It keeps them now.",
    "v6 shaping reverted a whole request when it measured no smaller on the JSON wire, which is not what a provider bills, so that call missed the cache. It no longer does.",
    "A resumed session ran the routing again, so its tool list could change. A resume tied to the session's record now sends the recorded list.",
]
OPEN = [
    "A lone surrogate in a tool output makes the token counter raise, which fails that bridge call and every later call that resends the output.",
    "The routing triggers miss some phrasings: \"have an agent review this diff\" drops `task`.",
    "Whitespace around the session folder path is not recovered after the move.",
]

CHECK = '<svg viewBox="0 0 14 14" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 7.4 2.7 2.7L11 4.4"/></svg>'
ARROW = '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 8.5 8.5 3.5M4.5 3.5h4v4"/></svg>'


def inline_code(s):
    """Escape, then turn `code` spans into <code>."""
    parts = htmllib.escape(s, quote=False).split('`')
    return ''.join(f'<code>{p}</code>' if i % 2 else p for i, p in enumerate(parts))


def check_sources(decls, test_names, counts):
    """Every name the slides print has to exist, and the lists have to match the write-up."""
    if len(FIXED) != counts['fixed'] or len(OPEN) != counts['open']:
        fail(f"the findings changed: proofs/README.md lists {counts['fixed']} fixed and {counts['open']} open, "
             f'build.py has {len(FIXED)} and {len(OPEN)}')
    if len(CLAIMS) != counts['claims']:
        fail(f"proofs/README.md has {counts['claims']} summary rows but build.py has {len(CLAIMS)} claims")
    for c in CLAIMS:
        for name in c['lean']:
            module, _, ident = name.partition('.')
            if ident not in decls.get(module, ()):
                fail(f'Lean theorem not found: {name}')
        for t in c['tests']:
            if t not in test_names:
                fail(f'test not found: {t}')


def claim_item(i, c):
    flag = f'<span class="cv">{htmllib.escape(c["flag"])}</span>' if c.get('flag') else ''
    lean = ' '.join(f'<code>{htmllib.escape(n)}</code>' for n in c['lean'])
    shown = c['tests'][:2] + ([f'and {len(c["tests"]) - 2} more'] if len(c['tests']) > 2 else [])
    tests = ' '.join(f'<code>{htmllib.escape(t)}</code>' if not t.startswith('and ') else f'<span class="more">{t}</span>' for t in shown)
    return (f'<li style="--i:{i}"><button type="button" class="claim" aria-pressed="false" aria-describedby="cd-{i}">'
            f'<span class="ck" aria-hidden="true">{CHECK}</span><span class="ct">{htmllib.escape(c["text"])}</span>{flag}</button>'
            f'<dl class="cd" id="cd-{i}"><div><dt>Lean</dt><dd class="names">{lean}</dd></div><div><dt>Holds when</dt><dd>{inline_code(c["holds"])}</dd></div>'
            f'<div><dt>Checked by</dt><dd class="names">{tests}</dd></div></dl></li>')


def pull_link(n):
    return f'<a href="{REPO}/pull/{n}" target="_blank" rel="noopener">#{n}</a>'


def proof_slides():
    return f'''
  <!-- The claims, findings and names on the next two slides are checked by site/src/build.py against proofs/ and test_proof_conformance.py. Rebuild with: python site/src/build.py -->
  <section class="slide" id="proofs" data-title="Proofs">
    <div class="inner split proofs">
      <div class="stack">
        <p class="eyebrow" data-reveal><b>06</b>Proof-driven development</p>
        <h2 data-reveal>The savings are measured. The rules behind them are proved.</h2>
        <p class="lead" data-reveal>Each mechanism has rules the code must always keep, such as never changing text the provider has already cached. We state them as theorems about a model of the code and check the proofs with Lean 4, which accepts a proof only if every step is valid.</p>
        <ol class="pipe" data-reveal>
          <li><span class="n">1</span><div><h3>State a rule the code must keep.</h3></div></li>
          <li><span class="n">2</span><div><h3>Prove it, and let a computer check the proof.</h3></div></li>
          <li><span class="n">3</span><div><h3>Hold the code to the proof, and change them together.</h3></div></li>
        </ol>
      </div>
      <div class="stack">
        <div class="panel claimbox" data-reveal>
          <p class="eyebrow">What is proved</p>
          <ul class="claims" id="claims">
            {''.join(claim_item(i, c) for i, c in enumerate(CLAIMS))}
          </ul>
          <div class="inspect" id="claim-info"><p class="rest">Hover or tap a claim to see its theorems, what it assumes and the tests that check it.</p></div>
        </div>
      </div>
    </div>
  </section>

  <section class="slide" id="checks" data-title="Validation">
    <div class="inner split">
      <div class="stack">
        <p class="eyebrow" data-reveal><b>07</b>How it is checked</p>
        <h2 data-reveal>A proof covers a model. Four checks tie it to the real code.</h2>
        <ol class="pipe" data-reveal>
          <li><span class="n">1</span><div><h3>Lean checks every proof.</h3><p>Lean 4 accepts a proof only if every step is valid, and a clean build means no step was skipped.</p></div></li>
          <li><span class="n">2</span><div><h3>Tests run the real code.</h3><p>Conformance tests run the Python on generated inputs and on the recorded study data. Each names the Lean theorem or definition it checks.</p></div></li>
          <li><span class="n">3</span><div><h3>Every assumption is written down.</h3><p>The write-up lists what the models assume about the code and marks each as tested, read from the code, or assumed. One is known to be false: the token counter raises on a lone surrogate (open finding 1).</p></div></li>
          <li><span class="n">4</span><div><h3>Gaps become findings.</h3><p>Where a claim and the code disagree, the gap is recorded. Writing and reviewing the proofs found mistakes in our own claims. Most are fixed, and the rest are published.</p></div></li>
        </ol>
        <p class="small" data-reveal>Code and proofs change together: {pull_link(18)}, {pull_link(19)} and {pull_link(20)}, the last three routing pull requests, each updated the proofs write-up and the conformance tests; {pull_link(18)} and {pull_link(20)} also changed <code>Routing.lean</code>.</p>
      </div>
      <div class="stack">
        <div class="panel" data-reveal>
          <div class="phead">
            <h3>What writing the proofs found</h3>
            <div class="seg-scroll">
              <div class="seg" id="seg-finds" role="radiogroup" aria-label="Findings">
                <div class="seg-base">
                  <button type="button" role="radio" aria-checked="true" data-value="fixed">Fixed</button>
                  <button type="button" role="radio" aria-checked="false" data-value="open">Still open</button>
                </div>
                <div class="seg-on" aria-hidden="true"></div>
              </div>
            </div>
          </div>
          <div class="finds" id="finds">
            <ul class="list" data-set="fixed">{''.join(f'<li>{inline_code(t)}</li>' for t in FIXED)}</ul>
            <ul class="list old" data-set="open">{''.join(f'<li>{inline_code(t)}</li>' for t in OPEN)}<li class="note">Open findings stay published. Where a test can reproduce one, it does.</li></ul>
          </div>
        </div>
        <div class="panel" data-reveal>
          <p class="eyebrow">Check it yourself</p>
          <div class="cmd"><pre class="code" id="c5">lake -d proofs build</pre>@@COPY c5@@</div>
          <div class="cmd"><pre class="code" id="c6">python -m pytest token-master-plugin/skills/token-master/tests/test_proof_conformance.py</pre>@@COPY c6@@</div>
          <p class="small">Run both from the repository root. Install Lean 4 with <a href="https://github.com/leanprover/elan" target="_blank" rel="noopener">elan</a> first; <code>lake</code> reads the pinned version from <code>proofs/lean-toolchain</code>.</p>
        </div>
      </div>
    </div>
  </section>
'''


def proof_bar():
    return f'''<a class="proofbar" href="#proofs" data-go="proofs" data-reveal>
        <span class="ck on" aria-hidden="true">{CHECK}</span>
        <span class="pt"><b>Proof-driven.</b> The rules behind these savings are proved by a computer, and the code is held to those proofs.</span>
        <span class="pa" aria-hidden="true">{ARROW}</span>
      </a>'''


# ---------- the page ----------
COPY_LABELS = {'c5': 'Copy the build command', 'c6': 'Copy the test command'}


def build():
    check_sources(lean_declarations(), test_functions(), written_up())
    wordmark, mark, favicon = logo_parts()

    body = part('body.html').replace('{{PROOF_SLIDES}}', proof_slides()).replace('{{PROOF_BAR}}', proof_bar())
    body = re.sub(r'@@COPY (c\d)@@', lambda m: (
        f'<button class="copy" type="button" data-copy="{m.group(1)}" aria-label="{COPY_LABELS[m.group(1)]}">'
        '<span class="idle">Copy</span><span class="done" aria-hidden="true">Copied</span></button>'), body)
    body = re.sub(r'<(ul|ol) class=', r'<\1 role="list" class=', body)  # list-style: none drops list semantics in Safari
    body = body.replace('{{MARK}}', mark).replace('{{WORDMARK}}', wordmark)
    body = body.replace('{{N_SLIDES}}', str(body.count('<section class="slide"')))
    left = re.findall(r'\{\{[^}]*\}\}|@@[^@]*@@', body)
    if left:
        fail(f'placeholders left in body.html: {left[:5]}')

    data = results_json().replace('<', '\\u003c')  # keeps the JSON safe inside a script element
    return f'''<!doctype html>
<html lang="en" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>TokenMasterX: about half the tokens with --lean</title>
<meta name="description" content="Interactive deck for TokenMasterX: how it trims GitHub Copilot CLI's tokens, results with confidence intervals, the Lean 4 proofs behind the mechanisms, limits and install.">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#07080a">
<link rel="canonical" href="https://all-the-vibes.github.io/TokenMasterX/">
<meta property="og:type" content="website">
<meta property="og:title" content="TokenMasterX: about half the tokens with --lean">
<meta property="og:description" content="Up to 53% fewer tokens with --lean and 9 to 29% fewer with no flags on GitHub Copilot CLI, measured on 15 short Django lookups with GPT-6 Astra. Lean 4 proofs cover the rules the mechanisms must keep.">
<meta property="og:url" content="https://all-the-vibes.github.io/TokenMasterX/">
<meta name="twitter:card" content="summary">
<link rel="icon" type="image/svg+xml" href="{favicon.strip()}">
<script>document.documentElement.classList.remove('no-js')</script>
<style>
{part('style.css')}</style>
</head>
<body>
{body}
<script type="application/json" id="data">{data}</script>
<script>
{part('app.js')}</script>
</body>
</html>
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true', help='fail if site/index.html is not what the build produces')
    args = ap.parse_args()
    page = build()
    if args.check:
        current = OUT.read_bytes().replace(b'\r\n', b'\n').decode('utf-8') if OUT.exists() else ''
        if current != page:
            fail('site/index.html is stale. Run: python site/src/build.py')
        print('site/index.html is up to date')
        return
    OUT.write_text(page, encoding='utf-8', newline='\n')
    print(f'wrote {OUT.relative_to(ROOT)} ({len(page.encode("utf-8")):,} bytes)')


if __name__ == '__main__':
    main()
