(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const nf = new Intl.NumberFormat('en-US');
  const fmt = (n) => nf.format(Math.round(n));
  const DATA = JSON.parse($('#data').textContent);

  /* ---------- helpers ---------- */
  // Build elements without parsing HTML strings.
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (v === true) n.setAttribute(k, '');
      else if (v !== false && v != null) n.setAttribute(k, v);
    }
    n.append(...kids);
    return n;
  };
  // Count a number up or down. Decorative, so it is skipped under reduced motion.
  function tween(el, to, format = fmt, dur = 380) {
    cancelAnimationFrame(el._raf);
    const from = el.dataset.v === undefined ? to : Number(el.dataset.v);
    el.dataset.v = to;
    if (reduce.matches || from === to) { el.textContent = format(to); return; }
    const t0 = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      el.textContent = format(from + (to - from) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) el._raf = requestAnimationFrame(step);
    };
    el._raf = requestAnimationFrame(step);
  }
  // Swap content with a short blur crossfade, so two versions never sit on top of each other.
  // The key names what should be showing: asking again for what is already there cancels a pending change.
  function swap(el, key, apply) {
    clearTimeout(el._t);
    if (el._shown === key) { delete el.dataset.swap; return; }
    el.classList.add('swap');
    const commit = () => { apply(); el._shown = key; delete el.dataset.swap; };
    if (reduce.matches) { commit(); return; }
    el.dataset.swap = '';
    el._t = setTimeout(commit, 110);
  }
  function swapText(el, text) {
    if (el._shown === undefined) el._shown = el.textContent;
    swap(el, text, () => { el.textContent = text; });
  }
  // Hover or focus previews an item, a click pins it, and leaving puts back the pinned item or the default.
  function inspector(root, itemSel, show, rest) {
    let pinned = null;
    const settle = () => (pinned ? show(pinned) : rest());
    root.addEventListener('pointerover', (e) => { const p = e.target.closest(itemSel); if (p && e.pointerType === 'mouse') show(p); });
    root.addEventListener('pointerout', (e) => { const p = e.target.closest(itemSel); if (p && e.pointerType === 'mouse' && !p.contains(e.relatedTarget)) settle(); });
    root.addEventListener('focusin', (e) => { const p = e.target.closest(itemSel); if (p) show(p); });
    root.addEventListener('focusout', (e) => { if (!root.contains(e.relatedTarget)) settle(); });
    root.addEventListener('click', (e) => {
      const p = e.target.closest(itemSel);
      if (!p) return;
      if (pinned) pinned.setAttribute('aria-pressed', 'false');
      pinned = pinned === p ? null : p;
      if (pinned) pinned.setAttribute('aria-pressed', 'true');
      settle();
    });
  }
  // A radio group drawn twice: the base row, and a lime copy clipped to the active segment.
  function segmented(root, onChange) {
    const base = $('.seg-base', root), on = $('.seg-on', root);
    const btns = () => $$('button', base);
    on.replaceChildren(...btns().map((b) => el('span', { text: b.textContent })));
    let current = btns().find((b) => b.getAttribute('aria-checked') === 'true') || btns()[0];
    const place = () => {
      const b = current.getBoundingClientRect(), c = base.getBoundingClientRect();
      on.style.setProperty('--l', (b.left - c.left) + 'px');
      on.style.setProperty('--r', (c.right - b.right) + 'px');
    };
    function set(value, silent) {
      const next = btns().find((b) => b.dataset.value === value);
      if (!next) return;
      current = next;
      btns().forEach((b) => { b.setAttribute('aria-checked', String(b === next)); b.tabIndex = b === next ? 0 : -1; });
      place();
      if (!silent) onChange(value);
    }
    root.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b && base.contains(b)) set(b.dataset.value); });
    root.addEventListener('keydown', (e) => {
      const list = btns(), i = list.indexOf(current);
      let n = i;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') n = (i + 1) % list.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') n = (i - 1 + list.length) % list.length;
      else if (e.key === 'Home') n = 0;
      else if (e.key === 'End') n = list.length - 1;
      else return;
      e.preventDefault();
      list[n].focus();
      set(list[n].dataset.value);
    });
    new ResizeObserver(place).observe(base);
    set(current.dataset.value, true);
    return { set };
  }

  /* ---------- deck ---------- */
  const deck = $('#deck');
  const slides = $$('.slide', deck);
  const ids = slides.map((s) => s.id);
  const live = $('#live');
  let index = -1, lastNav = 0, fastTimer = 0;

  slides.forEach((s, k) => {
    s.setAttribute('role', 'group');
    s.setAttribute('aria-roledescription', 'slide');
    s.setAttribute('aria-label', `${k + 1} of ${slides.length}: ${s.dataset.title}`);
    $$('[data-reveal]', s).forEach((el, i) => el.style.setProperty('--i', i));
  });

  // A slide that scrolls and has nothing focusable inside has to take focus itself, so a keyboard can scroll it.
  function syncScroll(s) {
    const scrolls = s.scrollHeight > s.clientHeight + 1;
    if (scrolls && !s.querySelector('a[href], button, input, select, textarea, [tabindex]')) s.setAttribute('tabindex', '0');
    else s.removeAttribute('tabindex');
  }

  function go(i, source) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    if (i === index) return;
    const now = performance.now();
    // Holding or tapping an arrow key is repeated work: skip the motion, as a command palette would.
    if (source === 'key' && now - lastNav < 320) {
      deck.dataset.fast = '';
      clearTimeout(fastTimer);
      fastTimer = setTimeout(() => delete deck.dataset.fast, 450);
    }
    lastNav = now;
    const first = index === -1;
    index = i;
    slides.forEach((s, k) => {
      s.dataset.state = k === i ? 'current' : k < i ? 'prev' : 'next';
      s.inert = k !== i;
    });
    slides[i].scrollTop = 0;
    syncScroll(slides[i]);
    updateRail();
    history.replaceState(null, '', '#' + ids[i]);
    if (!first) live.textContent = `Slide ${i + 1} of ${slides.length}: ${slides[i].dataset.title}`;
  }
  new ResizeObserver(() => { if (index >= 0) syncScroll(slides[index]); }).observe(deck);
  const fromHash = () => Math.max(0, ids.indexOf(location.hash.slice(1)));
  addEventListener('hashchange', () => { const k = ids.indexOf(location.hash.slice(1)); if (k >= 0) go(k, 'hash'); });
  $('.skip').addEventListener('click', (e) => { e.preventDefault(); deck.focus(); });

  document.addEventListener('click', (e) => {
    const n = e.target.closest('[data-next]');
    if (n) { e.preventDefault(); go(index + 1, 'ui'); return; }
    const g = e.target.closest('[data-go]');
    if (g) { e.preventDefault(); go(ids.indexOf(g.dataset.go), 'ui'); }
  });
  $('#prev').addEventListener('click', () => go(index - 1, 'ui'));
  $('#next').addEventListener('click', () => go(index + 1, 'ui'));
  $('.brand').addEventListener('click', (e) => { e.preventDefault(); go(0, 'ui'); });

  addEventListener('keydown', (e) => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const target = e.target instanceof Element ? e.target : document.body;
    if (target.closest('input, textarea, select, [role="radiogroup"], [contenteditable]')) return;
    const interactive = target.closest('a, button');
    let to = null;
    switch (e.key) {
      case 'ArrowRight': case 'PageDown': to = index + 1; break;
      case 'ArrowLeft': case 'PageUp': to = index - 1; break;
      case ' ': if (!interactive) to = index + (e.shiftKey ? -1 : 1); break;
      case 'Home': to = 0; break;
      case 'End': to = slides.length - 1; break;
      // The digit is the number in the slide's eyebrow, and 0 is the cover.
      default: if (/^[0-9]$/.test(e.key) && Number(e.key) < slides.length) to = Number(e.key);
    }
    if (to === null) return;
    e.preventDefault();
    go(to, 'key');
  });

  // Swipe on touch: the slide follows the finger, damped at either end, and a quick flick is enough.
  let drag = null;
  const current = () => slides[index];
  deck.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' || drag) return; // one finger at a time
    if (e.target.closest('input, button, a, pre, .seg, [data-no-swipe]')) return;
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, t: performance.now(), dx: 0, on: false };
  });
  deck.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.on) {
      if (Math.abs(dy) > 12 && Math.abs(dy) > Math.abs(dx)) { drag = null; return; }
      if (Math.abs(dx) < 10 || Math.abs(dx) < Math.abs(dy) * 1.3) return;
      drag.on = true;
      deck.setPointerCapture(e.pointerId);
      current().dataset.dragging = '';
    }
    drag.dx = dx;
    const edge = (dx > 0 && index === 0) || (dx < 0 && index === slides.length - 1);
    current().style.transform = `translate3d(${dx * (edge ? .22 : .55)}px,0,0)`;
    current().style.opacity = String(1 - Math.min(Math.abs(dx) / 520, .5));
  });
  const endDrag = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const d = drag; drag = null;
    if (!d.on) return;
    const el = current();
    const edge = (d.dx > 0 && index === 0) || (d.dx < 0 && index === slides.length - 1);
    delete el.dataset.dragging;
    el.style.transform = ''; el.style.opacity = '';
    const velocity = Math.abs(d.dx) / Math.max(1, performance.now() - d.t);
    if (Math.abs(d.dx) > 70 || velocity > .4) {
      // Leave from the release point, so the slide fades out where it is instead of sliding back first.
      el.style.setProperty('--dx', `${d.dx * (edge ? .22 : .55)}px`);
      setTimeout(() => el.style.removeProperty('--dx'), 400);
      go(index + (d.dx < 0 ? 1 : -1), 'swipe');
    }
  };
  deck.addEventListener('pointerup', endDrag);
  deck.addEventListener('pointercancel', endDrag);

  /* ---------- rail and its tooltip ---------- */
  const chips = $('#chips'), tip = $('#tip');
  let tipOpen = false, tipTimer = 0, tipHide = 0;
  function showTip(el, text) {
    clearTimeout(tipHide);
    const r = el.getBoundingClientRect();
    tip.textContent = text;
    tip.style.left = (r.left + r.width / 2) + 'px';
    tip.style.top = (r.top - 40) + 'px';
    // Once one tooltip is open, the next ones skip the delay and the motion.
    if (tipOpen) tip.dataset.instant = ''; else delete tip.dataset.instant;
    tip.dataset.open = '';
    tipOpen = true;
  }
  function hideTip() {
    clearTimeout(tipTimer);
    tipHide = setTimeout(() => { delete tip.dataset.open; tipOpen = false; }, 120);
  }
  slides.forEach((s, k) => {
    const b = el('button', { class: 'rail-chip', type: 'button', 'aria-label': `Slide ${k + 1}: ${s.dataset.title}` }, el('i'));
    b.addEventListener('click', () => go(k, 'ui'));
    b.addEventListener('pointerenter', (e) => {
      if (e.pointerType !== 'mouse') return;
      clearTimeout(tipHide); clearTimeout(tipTimer);
      if (tipOpen) showTip(b, s.dataset.title); else tipTimer = setTimeout(() => showTip(b, s.dataset.title), 260);
    });
    b.addEventListener('pointerleave', hideTip);
    b.addEventListener('focus', () => { if (b.matches(':focus-visible')) showTip(b, s.dataset.title); });
    b.addEventListener('blur', hideTip);
    chips.append(b);
  });
  function updateRail() {
    $$('.rail-chip').forEach((c, k) => c.setAttribute('aria-current', String(k === index)));
    $('#prev').setAttribute('aria-disabled', String(index === 0));
    $('#next').setAttribute('aria-disabled', String(index === slides.length - 1));
    $('#count').textContent = `${index + 1} / ${slides.length}`;
  }

  /* ---------- slide: the fixed prompt ---------- */
  const FIRST = DATA.firstCallInput, CHIP = 125, NCHIPS = 112;
  const SETUPS = {
    stock: { first: FIRST.stock, tools: 7819, removed: false, nav: false, sub: "Copilot CLI's own estimate. Every built-in tool is sent." },
    nolean: { first: FIRST.nolean, tools: 8200, removed: false, nav: true, sub: "Copilot CLI's own estimate. Every built-in tool stays, and three navigation tools are added." },
    lean: { first: FIRST.lean, tools: 1945, removed: true, nav: true, sub: "Copilot CLI's own estimate. 13 built-in tools are removed and three navigation tools are added." },
  };
  const FAMS = [
    { label: 'Session history', tools: ['session_store_sql'], when: 'the launch prompt mentions session history or earlier sessions, or you resume a session the launcher has no record for' },
    { label: 'Agents', tools: ['task', 'read_agent', 'write_agent', 'list_agents'], when: 'the launch prompt asks for subagents or starts a skill, or you pass --agent' },
    { label: 'Skills', tools: ['skill'], when: 'the launch prompt names an installed skill, for example as a slash command' },
    { label: 'SQL', tools: ['sql'], when: 'the launch prompt asks for the SQL scratchpad' },
    { label: 'Background shell', tools: ['read_powershell', 'stop_powershell', 'list_powershell'], when: 'the launch prompt mentions a background process, job or server' },
    { label: 'Copilot docs', tools: ['fetch_copilot_cli_documentation'], when: 'the launch prompt asks about Copilot CLI flags, settings or docs' },
    { label: 'Workflows', tools: ['run_dynamic_workflow', 'dynamic_workflows_manage'], when: 'the launch prompt mentions a workflow, or starts a skill' },
  ];
  // What Copilot CLI 1.0.105 still sent to GPT-6 Astra with the 13 removed (evidence/session-tools-20261030/resume_probe.json).
  const STAY = 'apply_patch, glob, powershell, rg, semantic_code_search, view, web_fetch and web_search';
  const NAV = 'locate, read_symbol and impact';
  const DEFAULT_INFO = 'Hover or tap a tool to see what keeps it.';

  const bar = $('#bar'), toolsEl = $('#tools'), info = $('#info');
  const chipEls = Array.from({ length: NCHIPS }, () => { const i = document.createElement('i'); i.className = 'chip'; bar.append(i); return i; });
  let shownChips = NCHIPS;

  function pill(name, kind, text) {
    return el('button', { type: 'button', class: 'tool' + (kind === 'nav' ? ' nav' : ''), 'data-kind': kind, 'data-info': text, 'data-sent': 'true', 'aria-pressed': 'false', text: name }, el('span', { class: 'sr' }));
  }
  toolsEl.append(el('p', { class: 'tlabel', text: 'Removed with --lean' }));
  toolsEl.append(el('div', { class: 'tgroup' }, ...FAMS.map((f) =>
    el('div', { class: 'cluster' }, ...f.tools.map((t) => pill(t, 'fam', `${t}: ${f.label.toLowerCase()}. With --lean it is removed unless ${f.when}. TOKENMASTER_KEEP_TOOLS keeps it too.`))))));
  toolsEl.append(el('div', { class: 'tgroup' }, el('div', { class: 'cluster' },
    pill('8 built-in tools stay', 'core', `${STAY}: the built-in tools Copilot CLI 1.0.105 still sent to GPT-6 Astra in a probe with the 13 removed, which also kept five GitHub MCP tools. --lean removes nothing outside the 13.`),
    pill('3 navigation tools added', 'nav', `${NAV}: added by TokenMasterX, with or without --lean.`))));

  function setInfo(text) { swapText(info, text); }
  inspector(toolsEl, '.tool', (p) => setInfo(p.dataset.info), () => setInfo(DEFAULT_INFO));

  function applySetup(key, initial) {
    const s = SETUPS[key];
    const on = Math.round(s.first / CHIP);
    // Removed chips go from the far end inward; chips coming back fill in from where they begin.
    chipEls.forEach((c, i) => {
      const delay = initial ? 0 : on < shownChips ? Math.max(0, shownChips - 1 - i) * 5 : Math.max(0, i - shownChips) * 5;
      c.style.setProperty('--k', delay);
      c.classList.toggle('off', i >= on);
    });
    shownChips = on;
    bar.setAttribute('aria-label', `${fmt(s.first)} first-call input tokens`);
    const diff = s.first - FIRST.stock;
    swapText($('#delta'), diff === 0 ? 'Same as stock.' : diff > 0 ? `${fmt(diff)} more tokens per call: the navigation tools are added.` : `${fmt(-diff)} fewer tokens per call.`);
    tween($('#first-val'), s.first);
    tween($('#tools-val'), s.tools);
    swapText($('#tools-sub'), s.sub);
    $$('.tool', toolsEl).forEach((p) => {
      const k = p.dataset.kind;
      const sent = k === 'core' ? true : k === 'nav' ? s.nav : !s.removed;
      p.dataset.sent = String(sent);
      $('.sr', p).textContent = sent ? '' : k === 'nav' ? ' (not added)' : ' (removed)';
    });
  }
  segmented($('#seg-setup'), (v) => applySetup(v));
  applySetup('stock', true);

  const calls = $('#calls');
  const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
  function estimate() {
    const n = Number(calls.value), tokens = n * (FIRST.stock - FIRST.lean);
    calls.style.setProperty('--p', ((n - 10) / 990 * 100) + '%');
    $('#calls-val').textContent = fmt(n);
    tween($('#est-tok'), tokens, fmt, 220);
    tween($('#est-usd'), tokens / 1e6, (v) => usd.format(v), 220);
  }
  calls.addEventListener('input', estimate);
  estimate();

  /* ---------- slide: the cache ---------- */
  const GROUPS = [['System + tools', 6], ['Turn 1', 2], ['Turn 2', 3], ['Turn 3', 2], ['Turn 4', 2], ['Turn 5', 1]];
  const R = 'read', W = 'write', G = 'gone', N = 'new';
  const CACHE = {
    once: [[R, R, R, R, R, R], [R, R], [R, R, R], [R, R], [R, R], [N]],
    rewrite: [[R, R, R, R, R, R], [R, R], [W, G, G], [W, W], [W, W], [N]],
  };
  const CACHE_NOTE = {
    once: 'TokenMasterX shapes each tool result when it arrives and never edits an earlier message. Only the new turn is written.',
    rewrite: "At turn 5 the harness compacts turn 2's tool output. The prompt gets shorter, but turn 2 and everything after it miss the cache and are written again.",
  };
  const stream = $('#stream');
  const cacheChips = GROUPS.map(([cap, n]) => {
    const g = document.createElement('div');
    g.className = 'grp';
    const c = document.createElement('div');
    c.className = 'chips';
    const els = Array.from({ length: n }, () => { const i = document.createElement('i'); i.className = 'chip'; c.append(i); return i; });
    const l = document.createElement('span');
    l.className = 'cap'; l.textContent = cap;
    g.append(c, l); stream.append(g);
    return els;
  });
  const kfmt = (v) => (Math.round(v * 100) / 100) + 'k';
  function applyCache(key) {
    const states = CACHE[key];
    let sent = 0, read = 0, write = 0;
    cacheChips.forEach((els, g) => els.forEach((el, i) => {
      const st = states[g][i];
      el.dataset.st = st;
      if (st !== G) sent++;
      if (st === R) read++;
      if (st === W || st === N) write++;
    }));
    tween($('#t-sent'), sent, kfmt, 260);
    tween($('#t-read'), read, kfmt, 260);
    tween($('#t-write'), write, kfmt, 260);
    tween($('#t-cost'), read * .1 + write * 1.25, kfmt, 260);
    swapText($('#cache-info'), CACHE_NOTE[key]);
  }
  segmented($('#seg-cache'), applyCache);
  applyCache('once');

  /* ---------- slide: results ---------- */
  const AXIS = 80;
  const METRICS = [['raw', 'Raw tokens'], ['cold', 'Cold-start cost'], ['billed', 'As billed']];
  const NOTES = {
    nov1: 'Both arms ran the same day, each against its own stock run. Two identical stock runs that day differed by 8.6% in raw tokens, so read the intervals as narrower than the real run-to-run noise.',
    oct27: 'The lean tool set was the launcher default on this build. A relay control the same day, on the same build, gave 48.6% fewer tokens. By the rule fixed before the sessions, routing explained none of the 11.1-point gap to PRS-6, and its interval allows up to 4.9 of those points.',
    prs6repo: 'Pre-registered before any study call, through an evaluation relay with the request bridge on. The bridge needs bring-your-own-model mode.',
    prs6dj: 'The same relay setup on the Django lookups that graph navigation answers directly. The 58.5% is the best cell we have measured. It did not hold under default routing.',
  };
  $('#axis').replaceChildren(...Array.from({ length: 9 }, (_, i) => el('span', { text: `${i * 10}%` })));
  const armsEl = $('#arms');
  for (let a = 0; a < 2; a++) {
    armsEl.append(el('section', { class: 'arm' }, el('h4'), ...METRICS.map(([k, label]) =>
      el('div', { class: 'mrow', 'data-m': k },
        el('span', { class: 'k', text: label }),
        el('div', { class: 'track', 'aria-hidden': 'true' }, el('i', { class: 'fill' }), el('i', { class: 'wl' }), el('i', { class: 'wt lo' }), el('i', { class: 'wt hi' })),
        el('span', { class: 'v' }, el('b', { class: 'num', 'aria-hidden': 'true' }), el('span', { class: 'num', 'aria-hidden': 'true' }), el('span', { class: 'sr' }))))));
  }
  $('#seg-run .seg-base').replaceChildren(...DATA.runs.map((r, k) =>
    el('button', { type: 'button', role: 'radio', 'aria-checked': String(k === 0), 'data-value': r.id, text: r.label })));
  const pct = (v) => v.toFixed(1) + '%';
  function showRun(id) {
    const r = DATA.runs.find((x) => x.id === id);
    swapText($('#run-title'), r.title);
    swapText($('#run-sub'), r.sub);
    swapText($('#run-note'), NOTES[id]);
    $$('.arm', armsEl).forEach((el, a) => {
      const arm = r.arms[a];
      el.toggleAttribute('data-absent', !arm);
      if (!arm) return;
      $('h4', el).textContent = arm.name;
      METRICS.forEach(([k, label]) => {
        const m = arm[k], rowEl = $(`[data-m="${k}"]`, el), t = $('.track', rowEl);
        t.style.setProperty('--v', m.v / AXIS);
        t.style.setProperty('--lo', m.lo / AXIS);
        t.style.setProperty('--hi', m.hi / AXIS);
        tween($('b', rowEl), m.v, pct, 420);
        $('.v span', rowEl).textContent = `${m.lo.toFixed(1)} to ${m.hi.toFixed(1)}`;
        $('.v .sr', rowEl).textContent = `${arm.name}, ${label}: ${pct(m.v)} lower, 95% interval ${m.lo.toFixed(1)} to ${m.hi.toFixed(1)}`;
      });
    });
  }
  segmented($('#seg-run'), showRun);
  showRun(DATA.runs[0].id);

  /* ---------- slide: the proofs ---------- */
  const claimInfo = $('#claim-info');
  const claimRest = claimInfo.firstElementChild.cloneNode(true);
  claimInfo._shown = 'rest';
  const showClaim = (btn) => swap(claimInfo, btn, () => claimInfo.replaceChildren($('.cd', btn.parentElement).cloneNode(true)));
  inspector($('#claims'), '.claim', showClaim, () => swap(claimInfo, 'rest', () => claimInfo.replaceChildren(claimRest.cloneNode(true))));

  const findLists = $$('#finds > ul');
  const showFinds = (v) => findLists.forEach((u) => u.toggleAttribute('data-off', u.dataset.set !== v));
  segmented($('#seg-finds'), showFinds);
  showFinds('fixed');

  /* ---------- copy buttons ---------- */
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* fall back to a selection */ }
    const t = document.createElement('textarea');
    t.value = text; t.style.cssText = 'position:fixed;opacity:0'; document.body.append(t); t.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { /* ok stays false */ }
    t.remove();
    return ok;
  }
  $$('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    const done = $('.done', b);
    clearTimeout(b._t);
    if (!(await copyText($('#' + b.dataset.copy).textContent))) {
      live.textContent = 'Copy failed. Select the text and copy it.';
      done.textContent = 'Failed'; b.dataset.failed = ''; b.dataset.copied = '';
      b._t = setTimeout(() => { delete b.dataset.copied; delete b.dataset.failed; done.textContent = 'Copied'; }, 1800);
      return;
    }
    b.dataset.copied = '';
    live.textContent = 'Copied to the clipboard';
    clearTimeout(b._t);
    b._t = setTimeout(() => delete b.dataset.copied, 1800);
  }));

  /* ---------- start ---------- */
  requestAnimationFrame(() => requestAnimationFrame(() => go(fromHash(), 'init')));
})();
