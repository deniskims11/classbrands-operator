/* Class Brands Operator — renders data/latest.json (decrypting it first when published). */
(function () {
  'use strict';
  const KEY_STORE = 'cbo_key_v1';
  const COLORS = ['--s1', '--s2', '--s3', '--s4'];
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const $ = (s, el = document) => el.querySelector(s);
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return el;
  };

  /* ---------- formatting ---------- */
  const ok = (v) => v != null && isFinite(v);
  const F = {
    money: (v) => ok(v) ? d3.format('$,.0f')(v) : '—',
    money2: (v) => ok(v) ? d3.format('$,.2f')(v) : '—',
    short: (v) => !ok(v) ? '—' : Math.abs(v) >= 1e6 ? '$' + d3.format('.2f')(v / 1e6) + 'M' : Math.abs(v) >= 1e4 ? '$' + d3.format(',.0f')(v / 1e3) + 'K' : Math.abs(v) >= 1e3 ? '$' + d3.format('.1f')(v / 1e3) + 'K' : d3.format('$,.0f')(v),
    x: (v) => ok(v) ? d3.format('.2f')(v) + '×' : '—',
    pct: (v) => ok(v) ? d3.format('.1%')(v) : '—',
    pct0: (v) => ok(v) ? d3.format('.0%')(v) : '—',
    int: (v) => ok(v) ? d3.format(',.0f')(v) : '—',
    day: (s) => s ? d3.utcFormat('%b %-d')(new Date(s + 'T00:00:00Z')) : '—',
  };
  // Signed change, coloured by whether it's good (lowerIsBetter flips it).
  function delta(v, lowerIsBetter, label) {
    if (!ok(v)) return h('span', {class: 'num'}, '—');
    const good = lowerIsBetter ? v < 0 : v > 0;
    const cls = Math.abs(v) < 0.02 ? '' : good ? 'up' : 'down';
    return h('span', {class: 'num ' + cls}, (v > 0 ? '+' : '') + d3.format('.0%')(v) + (label ? ' ' + label : ''));
  }

  /* ---------- data loading + password gate ---------- */
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const savedKey = () => { try { return localStorage.getItem(KEY_STORE) || sessionStorage.getItem(KEY_STORE); } catch (e) { return null; } };
  const forget = () => { try { localStorage.removeItem(KEY_STORE); sessionStorage.removeItem(KEY_STORE); } catch (e) {} };
  async function decrypt(p, password, key64) {
    let raw;
    if (key64) raw = b64(key64);
    else {
      const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits']);
      raw = new Uint8Array(await crypto.subtle.deriveBits({name: 'PBKDF2', hash: 'SHA-256', salt: b64(p.salt), iterations: p.iterations}, base, 256));
    }
    const key = await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['decrypt']);
    const gz = await crypto.subtle.decrypt({name: 'AES-GCM', iv: b64(p.iv)}, key, b64(p.data));
    const txt = await new Response(new Blob([gz]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
    return {data: JSON.parse(txt), key64: btoa(String.fromCharCode(...raw))};
  }
  async function boot() {
    let payload;
    try { payload = await (await fetch('data/latest.json?t=' + Date.now(), {cache: 'no-store'})).json(); }
    catch (e) { document.body.append(h('p', {class: 'empty', style: 'padding:24px'}, 'Could not load the dashboard data.')); return; }
    if (!payload.encrypted) return start(payload);
    const k = savedKey();
    if (k) { try { const r = await decrypt(payload, null, k); return start(r.data); } catch (e) { forget(); } }
    const gate = $('#gate'); gate.hidden = false; $('#gate-pw').focus();
    $('#gate-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = $('#gate-btn'); btn.disabled = true; btn.textContent = 'Opening…'; $('#gate-err').hidden = true;
      try {
        const r = await decrypt(payload, $('#gate-pw').value);
        try { ($('#gate-remember').checked ? localStorage : sessionStorage).setItem(KEY_STORE, r.key64); } catch (e) {}
        gate.hidden = true; start(r.data);
      } catch (e) { $('#gate-err').hidden = false; btn.disabled = false; btn.textContent = 'Open dashboard'; }
    });
  }

  /* ---------- app ---------- */
  let DATA = null;
  const slug = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const color = (i) => css(COLORS[i % COLORS.length]);

  function start(data) {
    DATA = data;
    $('#app').hidden = false;
    const tabs = $('#tabs');
    tabs.append(h('button', {class: 'tab', 'data-r': 'overview', onclick: () => go('overview')}, 'All clients'));
    data.clients.forEach((c, i) => tabs.append(h('button', {class: 'tab', 'data-r': slug(c.name), onclick: () => go(slug(c.name))},
      h('span', {class: 'dot', style: 'background:' + color(i)}), c.name)));
    const gen = new Date(data.generated_at);
    const mins = Math.round((Date.now() - gen) / 60000);
    $('#fresh').textContent = 'Data through ' + F.day(data.totals.as_of) + ' · refreshed ' + (mins < 90 ? mins + ' min' : Math.round(mins / 60) + ' h') + ' ago';
    window.addEventListener('hashchange', render);
    let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 150); });
    render();
  }
  function go(r) { location.hash = r === 'overview' ? '' : r; if (r === 'overview') render(); }
  function render() {
    const r = (location.hash || '').slice(1) || 'overview';
    document.querySelectorAll('.tab').forEach((t) => t.setAttribute('aria-current', t.dataset.r === r ? 'page' : 'false'));
    const main = $('#main'); main.replaceChildren();
    const i = DATA.clients.findIndex((c) => slug(c.name) === r);
    if (i >= 0) clientView(main, DATA.clients[i], i); else overview(main);
    window.scrollTo({top: 0});
  }

  /* ---------- pieces ---------- */
  function tile(label, value, sub, opts = {}) {
    return h('div', {class: 'tile' + (opts.ours ? ' ours' : '')},
      h('div', {class: 'l'}, h('span', {}, label), opts.right || null),
      h('div', {class: 'v', title: typeof value === 'string' ? value : ''}, value),
      sub ? h('div', {class: 's'}, sub) : null,
      opts.bar != null ? h('div', {class: 'bar'}, h('i', {style: `width:${Math.min(100, Math.max(0, opts.bar * 100))}%;background:${opts.barColor || css('--ink')}`})) : null);
  }
  const paceColor = (lvl) => css(lvl === 'ok' ? '--good' : lvl === 'warn' ? '--warn' : lvl === 'idle' ? '--dim' : '--bad');
  const pill = (lvl, text) => h('span', {class: 'pill ' + lvl}, text);

  function alertList(items) {
    if (!items.length) return h('p', {class: 'empty'}, 'Nothing flagged on the latest day.');
    const order = {bad: 0, warn: 1, ok: 2};
    return h('ul', {class: 'alerts'}, items.sort((a, b) => order[a[1]] - order[b[1]]).map(([who, lvl, text]) =>
      h('li', {class: lvl}, h('span', {class: 'ic'}, lvl === 'ok' ? '▲' : lvl === 'warn' ? '!' : '▼'), who ? h('span', {class: 'who'}, who) : null, h('span', {}, text))));
  }

  /* line chart: series [{name, color, values:[{d, v}], dash}] */
  function lineChart(el, series, o) {
    const W = Math.max(280, el.clientWidth || 600), H = o.height || 210;
    const all = series.flatMap((s) => s.values).filter((p) => ok(p.v));
    if (!all.length) { el.append(h('p', {class: 'empty'}, 'No data in this window.')); return; }
    const parse = (s) => new Date(s + 'T00:00:00Z');
    const x = d3.scaleUtc().domain(d3.extent(all, (p) => parse(p.d)));
    const y = d3.scaleLinear().domain([0, (d3.max(all, (p) => p.v) || 1) * 1.08]).nice();
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H).attr('role', 'img').attr('aria-label', o.label);
    const ticks = y.ticks(4);
    const probe = svg.append('text').text(ticks.map(o.yfmt).sort((a, b) => b.length - a.length)[0]);
    const ml = (probe.node().getComputedTextLength() || 34) + 10; probe.remove();
    const labelled = o.endLabels && W >= 460;
    const m = {l: ml, r: labelled ? 96 : 10, t: 8, b: 22};
    x.range([m.l, W - m.r]); y.range([H - m.b, m.t]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y).attr('y2', y).attr('stroke', css('--grid'));
    svg.append('g').selectAll('text').data(ticks).join('text').attr('x', m.l - 8).attr('y', (t) => y(t) + 4).attr('text-anchor', 'end').text(o.yfmt);
    svg.append('g').selectAll('text').data(x.ticks(Math.max(2, Math.floor(W / 110)))).join('text').attr('x', x).attr('y', H - 5).attr('text-anchor', 'middle').text(d3.utcFormat('%b %-d'));
    const line = d3.line().defined((p) => ok(p.v)).x((p) => x(parse(p.d))).y((p) => y(p.v));
    series.forEach((s) => {
      if (s.area) svg.append('path').datum(s.values.filter((p) => ok(p.v))).attr('fill', s.color).attr('opacity', 0.1)
        .attr('d', d3.area().x((p) => x(parse(p.d))).y0(H - m.b).y1((p) => y(p.v)));
      svg.append('path').datum(s.values).attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.width || 2)
        .attr('stroke-dasharray', s.dash || null).attr('stroke-linejoin', 'round').attr('d', line);
      const last = [...s.values].reverse().find((p) => ok(p.v));
      if (last) svg.append('circle').attr('cx', x(parse(last.d))).attr('cy', y(last.v)).attr('r', 3.5).attr('fill', s.color).attr('stroke', css('--panel')).attr('stroke-width', 2);
    });
    if (labelled) {  // direct labels at the line ends, nudged apart so they never collide
      const ends = series.map((s) => ({s, p: [...s.values].reverse().find((q) => ok(q.v))})).filter((e) => e.p).map((e) => ({name: e.s.name, y: y(e.p.v), x: x(parse(e.p.d))})).sort((a, b) => a.y - b.y);
      ends.forEach((e, i) => { if (i && e.y - ends[i - 1].y < 13) e.y = ends[i - 1].y + 13; });
      const over = ends.length ? ends[ends.length - 1].y - (H - m.b) : 0;
      if (over > 0) { ends.forEach((e) => { e.y -= over; }); for (let i = ends.length - 2; i >= 0; i--) if (ends[i + 1].y - ends[i].y < 13) ends[i].y = ends[i + 1].y - 13; }
      svg.append('g').attr('class', 'end-labels').selectAll('text').data(ends).join('text').attr('x', (e) => e.x + 9).attr('y', (e) => e.y + 4).text((e) => e.name);
    }
    const dates = [...new Set(all.map((p) => p.d))].sort();
    const cross = svg.append('line').attr('y1', m.t).attr('y2', H - m.b).attr('stroke', css('--dim')).attr('stroke-dasharray', '3 3').style('opacity', 0);
    const tip = $('#tip');
    svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', W - m.l - m.r).attr('height', H - m.t - m.b).attr('fill', 'transparent')
      .on('pointermove', (ev) => {
        const [px] = d3.pointer(ev);
        const day = dates[d3.bisector((d) => parse(d)).center(dates, x.invert(px))];
        if (!day) return;
        cross.attr('x1', x(parse(day))).attr('x2', x(parse(day))).style('opacity', 1);
        tip.replaceChildren(h('b', {}, F.day(day)));
        series.forEach((s) => { const p = s.values.find((q) => q.d === day); if (p && ok(p.v)) tip.append(h('div', {}, h('i', {style: 'background:' + s.color}), s.name + ': ' + o.tfmt(p.v))); });
        tip.hidden = false;
        const tw = tip.offsetWidth, th = tip.offsetHeight;
        let lx = ev.clientX + 14; if (lx + tw > window.innerWidth - 8) lx = ev.clientX - tw - 14;
        tip.style.left = Math.max(8, lx) + 'px'; tip.style.top = Math.max(8, ev.clientY - th - 10) + 'px';
      })
      .on('pointerleave', () => { tip.hidden = true; cross.style('opacity', 0); });
  }
  function legend(series) {
    return h('div', {class: 'legend'}, series.map((s) => h('span', {}, h('i', {style: `background:${s.color}` + (s.dash ? ';opacity:.6' : '')}), s.name)));
  }
  function chartCard(title, sub, series, o) {
    const box = h('div', {class: 'chart'});
    const card = h('div', {class: 'card'}, h('h2', {}, title), sub ? h('p', {class: 'sub'}, sub) : null, series.length > 1 ? legend(series) : null, box);
    requestAnimationFrame(() => lineChart(box, series, o));
    return card;
  }
  function spark(values, col) {
    const w = 96, hh = 26, vals = values.filter(ok);
    const svg = d3.create('svg').attr('width', w).attr('height', hh).attr('class', 'spark').attr('role', 'img').attr('aria-label', 'Daily Meta spend, last 30 days');
    if (vals.length < 2) return svg.node();
    const sx = d3.scaleLinear().domain([0, values.length - 1]).range([1, w - 3]), sy = d3.scaleLinear().domain([0, d3.max(vals) || 1]).range([hh - 2, 2]);
    svg.append('path').attr('d', d3.area().x((v, i) => sx(i)).y0(hh).y1((v) => sy(v || 0))(values)).attr('fill', col).attr('opacity', 0.15);
    svg.append('path').attr('d', d3.line().x((v, i) => sx(i)).y((v) => sy(v || 0))(values)).attr('fill', 'none').attr('stroke', col).attr('stroke-width', 1.5);
    svg.append('circle').attr('cx', sx(values.length - 1)).attr('cy', sy(values[values.length - 1] || 0)).attr('r', 2.5).attr('fill', col);
    return svg.node();
  }
  function adsManager(a) {
    const b = a.biz ? `&business_id=${a.biz}&global_scope_id=${a.biz}` : '';
    return `https://adsmanager.facebook.com/adsmanager/manage/ads/edit/standalone?act=${a.act}${b}&selected_ad_ids=${a.id}`;
  }
  function adCell(a, showChip) {
    const thumb = a.img ? h('img', {class: 'thumb', src: a.img, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer', onerror: (e) => { e.target.replaceWith(h('span', {class: 'thumb none'})); }}) : h('span', {class: 'thumb none'});
    return h('td', {}, h('div', {class: 'adcell'}, thumb, h('div', {class: 'adtext'},
      h('a', {class: 'adname', href: adsManager(a), target: '_blank', rel: 'noopener', title: a.name}, showChip && a.ours ? h('span', {class: 'ours-chip'}, 'OURS') : null, a.name || a.id),
      h('span', {class: 'adset', title: a.adset}, a.adset))));
  }
  // A number with a quiet second line, for dense table cells.
  const two = (main, sub) => h('td', {}, h('div', {class: 'two'}, h('span', {}, main), h('small', {}, sub)));
  // Spend with a thin bar scaled to the largest row.
  const spendBar = (key, rows) => {
    const max = Math.max(1, ...rows.map((r) => r[key] || 0));
    return (r) => h('td', {class: r[key] ? '' : 'zero'}, h('div', {class: 'barcell'}, h('span', {}, F.money(r[key])), h('i', {}, h('b', {style: `width:${Math.max(0, (r[key] || 0) / max * 100)}%`}))));
  };
  /* sortable table; `limit` shows the first rows with a button for the rest */
  function table(cols, rows, sortKey, limit) {
    let key = sortKey, dir = -1, open = !limit;
    const thead = h('thead'), tbody = h('tbody'), more = h('button', {class: 'more', type: 'button', onclick: () => { open = !open; draw(); }});
    const draw = () => {
      thead.replaceChildren(h('tr', {}, cols.map((c) => h('th', {class: (c.sort ? 'sortable' : '') + (key === c.sort && c.sort ? ' on' : ''), 'aria-sort': key === c.sort && c.sort ? (dir < 0 ? 'descending' : 'ascending') : null, onclick: c.sort ? () => { dir = key === c.sort ? -dir : -1; key = c.sort; draw(); } : null},
        c.label + (key === c.sort && c.sort ? (dir < 0 ? ' ↓' : ' ↑') : '')))));
      const sorted = key ? [...rows].sort((a, b) => dir * ((ok(a[key]) ? a[key] : -Infinity) - (ok(b[key]) ? b[key] : -Infinity))) : rows;
      const shown = open ? sorted : sorted.slice(0, limit);
      tbody.replaceChildren(...shown.map((r) => h('tr', {}, cols.map((c) => c.cell ? c.cell(r) : h('td', {class: r[c.sort] === 0 ? 'zero' : ''}, c.fmt(r[c.sort]))))));
      more.hidden = !limit || rows.length <= limit;
      more.textContent = open ? 'Show fewer' : `Show all ${rows.length}`;
    };
    draw();
    return h('div', {}, h('div', {class: 'tw'}, h('table', {}, thead, tbody)), more);
  }

  /* the headline panel: spend on our creatives against the monthly target */
  function hero(o) {
    const pct = Math.min(100, Math.max(0, (o.progress || 0) * 100)), tick = Math.min(100, (o.elapsed || 0) * 100);
    return h('section', {class: 'hero'},
      h('div', {class: 'hero-l'}, 'Spend on our creatives, month to date'),
      h('div', {class: 'hero-v'}, F.money(o.value)),
      h('div', {class: 'hero-s'}, o.sub),
      h('div', {class: 'track', role: 'img', 'aria-label': `${F.pct0(o.progress)} of the monthly target, ${F.pct0(o.elapsed)} of the month gone`},
        h('i', {style: `width:${pct}%;background:${paceColor(o.level)}`}), h('b', {style: `left:${tick}%`})),
      h('div', {class: 'track-cap'}, h('span', {}, h('strong', {}, F.pct0(o.progress)), ' of ', F.money(o.target), ' target'), h('span', {}, F.pct0(o.elapsed), ' of the month gone')),
      h('dl', {class: 'stats'}, o.stats.map(([k, v, note]) => h('div', {}, h('dt', {}, k), h('dd', {}, v), note ? h('small', {}, note) : null))));
  }
  const levelOf = (p) => p >= 1 ? 'ok' : p >= 0.5 ? 'warn' : 'bad';
  // Issues and wins side by side; a side with nothing in it is left out.
  function attention(items) {
    const issues = items.filter((x) => x[1] !== 'ok'), wins = items.filter((x) => x[1] === 'ok');
    const cards = [issues.length ? h('div', {class: 'card'}, h('h2', {}, 'Needs attention'), alertList(issues)) : null, wins.length ? h('div', {class: 'card'}, h('h2', {}, 'Going well'), alertList(wins)) : null].filter(Boolean);
    return cards.length ? h('div', {class: 'grid2'}, cards) : null;
  }

  /* ---------- overview ---------- */
  function overview(main) {
    const T = DATA.totals, C = DATA.clients;
    main.append(h('div', {class: 'page-h'}, h('h1', {}, 'All clients'), h('span', {class: 'page-sub'}, 'Meta only · month to date through ' + F.day(T.as_of) + ' · ' + T.days_left + ' days left')));
    main.append(h('div', {class: 'top-grid'},
      hero({value: T.mtd.ours, progress: T.progress, elapsed: T.elapsed, target: T.target, level: levelOf(T.pace),
        sub: [h('b', {}, F.pct(T.mtd.ours_share)), ' of Meta spend · ', delta(T.mtd_vs_pm.ours), ' vs same days last month'],
        stats: [['Run rate', F.short(T.runrate), F.pct0(T.pace) + ' of target'], ['Needed per day', F.short(T.needed_per_day), T.days_left + ' days left'], ['Fees so far', F.money(T.fee_so_far)], ['Fees projected', F.money(T.fee_proj), 'at target ' + F.short(T.fee_target)]]}),
      h('div', {class: 'tiles c2'},
        tile('Meta spend, month', F.money(T.mtd.meta), [delta(T.mtd_vs_pm.meta), ' vs same days last month']),
        tile('Meta revenue, month', F.money(T.mtd.rev), [delta(T.mtd_vs_pm.rev), ' vs same days last month']),
        tile('Meta ROAS, month', F.x(T.mtd.roas), ['CPA ', h('b', {}, F.money2(T.mtd.cpa))]),
        tile('Meta spend, latest day', F.money(T.y.meta), [delta(T.y_vs7.meta), ' vs 7-day avg · today ', h('b', {}, F.short(T.today_meta))]))));

    const rows = C.map((c, i) => ({c, i, ...flat(c)}));
    const cols = [
      {label: 'Client', cell: (r) => h('td', {}, h('button', {class: 'cl', onclick: () => go(slug(r.c.name))}, h('span', {class: 'dot', style: 'background:' + color(r.i)}), r.c.name))},
      {label: 'Status', cell: (r) => h('td', {}, pill(r.c.summary.status_level, r.c.summary.status))},
      {label: 'Meta spend, 30d', cell: (r) => h('td', {}, spark(r.c.daily.slice(-30).map((d) => d.meta), color(r.i)))},
      {label: 'Latest day', sort: 'y_meta', cell: (r) => two(F.money(r.y_meta), delta(r.y_vs7, false, 'vs 7d'))},
      {label: 'Meta, month', sort: 'm_meta', fmt: F.money},
      {label: 'ROAS', sort: 'm_roas', cell: (r) => two(F.x(r.m_roas), F.x(r.y_roas) + ' latest')},
      {label: 'CPA', sort: 'm_cpa', fmt: F.money2},
      {label: 'Our creatives', sort: 'm_ours', cell: (r) => r.m_ours ? two(F.money(r.m_ours), F.pct(r.m_share) + ' of Meta') : h('td', {class: 'zero'}, '$0')},
      {label: 'Our NVP', sort: 'm_ours_nvp', fmt: F.pct0},
      {label: 'Pace to $150K', sort: 'pace', cell: (r) => h('td', {}, r.m_ours ? h('span', {class: 'pace'}, h('span', {class: 'bar'}, h('i', {style: `width:${Math.min(100, (r.pace || 0) * 100)}%;background:${paceColor(r.c.summary.status_level)}`})), F.pct0(r.pace)) : h('span', {class: 'zero'}, '—'))},
      {label: 'Fee, projected', sort: 'fee_proj', fmt: F.money},
      {label: '', cell: (r) => h('td', {}, fullLink(r.c, 'Open ↗'))},
    ];
    main.append(h('div', {class: 'card'}, h('div', {class: 'card-h'}, h('h2', {}, 'Clients'), h('p', {class: 'sub'}, 'Click a name for its summary, or Open for the full creative dashboard. ROAS and CPA are Meta-reported.')), table(cols, rows, 'm_ours')));
    const box = attention(C.flatMap((c) => c.summary.alerts.map(([lvl, text]) => [c.name, lvl, text])));
    if (box) main.append(box);
    const series = C.map((c, i) => ({name: c.name, color: color(i), values: c.daily.map((d) => ({d: d.d, v: d.meta}))}));
    const oursSeries = C.map((c, i) => ({name: c.name, color: color(i), values: c.daily.map((d) => ({d: d.d, v: d.ours}))}));
    main.append(h('div', {class: 'grid2'},
      chartCard('Daily Meta spend', 'Last 60 days', series, {label: 'Daily Meta spend by client', yfmt: F.short, tfmt: F.money, endLabels: true}),
      chartCard('Daily spend on our creatives', 'Meta ads carrying our tag, last 60 days', oursSeries, {label: 'Daily spend on our creatives by client', yfmt: F.short, tfmt: F.money, endLabels: true})));
  }
  // Natural Rems keeps its own site; the other brands' dashboards live under b/<key>/.
  function fullLink(c, text, primary) {
    const ext = /^https?:/.test(c.dashboard);
    return h('a', {class: 'full-link' + (primary ? ' primary' : ''), href: c.dashboard, target: ext ? '_blank' : null, rel: ext ? 'noopener' : null}, text);
  }
  function flat(c) {
    const s = c.summary;
    return {y_meta: s.y.meta, y_vs7: s.y_vs7.meta, y_roas: s.y.roas, m_meta: s.mtd.meta, m_roas: s.mtd.roas, m_cpa: s.mtd.cpa,
      m_ours: s.mtd.ours, m_share: s.mtd.ours_share, m_ours_nvp: s.mtd.ours_nvp, pace: s.pace, fee_proj: s.fee_proj};
  }

  /* ---------- client ---------- */
  function clientView(main, c, i) {
    const s = c.summary, col = color(i), live = s.mtd.ours > 0 || s.status_level !== 'idle';
    main.append(h('div', {class: 'client-h'},
      h('div', {}, h('div', {class: 'page-h'}, h('h1', {}, c.name), pill(s.status_level, s.status)),
        h('p', {class: 'page-sub'}, `Fee ${F.pct0(s.rate)} of spend on our creatives${s.base ? ' + ' + F.money(s.base) + ' base' : ''} · ours = ${c.tag_label} · latest day ${F.day(s.as_of)}`)),
      fullLink(c, 'Open full dashboard ↗', true)));

    const ourTiles = h('div', {class: 'tiles c2'},
      tile('Our Meta ROAS, month', F.x(s.mtd.ours_roas), ['account ', h('b', {}, F.x(s.mtd.roas)), ' · CPA ', h('b', {}, F.money2(s.mtd.ours_cpa))]),
      tile('Our new-visitor share', F.pct0(s.mtd.ours_nvp), ['account ', h('b', {}, F.pct0(s.mtd.nvp))]),
      tile('Launches, month', F.int(s.launch_m.launched), [h('b', {}, F.int(s.launch_m.hit_1k)), ' hit $1K+ · last month ', h('b', {}, s.launch_pm.hit_1k + '/' + s.launch_pm.launched)]),
      tile('Fee, projected month', F.money(s.fee_proj), ['so far ', h('b', {}, F.money(s.fee_so_far)), ' · last month ', h('b', {}, F.money(s.fee_pm))]));
    main.append(live ? h('div', {class: 'top-grid'},
      hero({value: s.mtd.ours, progress: s.progress, elapsed: s.elapsed, target: s.target, level: s.status_level,
        sub: [h('b', {}, F.pct(s.mtd.ours_share)), ' of Meta spend · latest day ', h('b', {}, F.money(s.y.ours)), ' ', delta(s.y_vs7.ours)],
        stats: [['Run rate', F.short(s.runrate), F.pct0(s.pace) + ' of target'], ['Needed per day', F.short(s.needed_per_day), s.days_left + ' days left'], ['Fee so far', F.money(s.fee_so_far)], ['Fee at target', F.money(s.fee_target)]]}), ourTiles)
      : h('div', {class: 'card idle'}, h('h2', {}, 'No creatives launched yet'), h('p', {class: 'sub'}, 'They will appear here automatically once they start spending.')));

    main.append(h('h3', {class: 'sec-h'}, 'Meta · month to date'), h('div', {class: 'tiles c5'},
      tile('Meta spend', F.money(s.mtd.meta), [delta(s.mtd_vs_pm.meta), ' vs same days last month']),
      tile('Meta revenue', F.money(s.mtd.rev), [delta(s.mtd_vs_pm.rev), ' vs same days last month']),
      tile('Meta ROAS', F.x(s.mtd.roas), [delta(s.mtd_vs_pm.roas), ' vs same days last month']),
      tile('CPA', F.money2(s.mtd.cpa), [delta(s.mtd_vs_pm.cpa, true), ' · ', h('b', {}, F.int(s.mtd.orders)), ' purchases']),
      tile('CPM', F.money2(s.mtd.cpm), [delta(s.mtd_vs_pm.cpm, true), ' · CTR ', h('b', {}, F.pct(s.mtd.ctr))])));
    main.append(h('h3', {class: 'sec-h'}, 'Meta · latest day'), h('div', {class: 'tiles c5'},
      tile('Meta spend', F.money(s.y.meta), [delta(s.y_vs7.meta), ' vs 7-day avg · today ', h('b', {}, F.short(s.today_meta))]),
      tile('Meta revenue', F.money(s.y.rev), [delta(s.y_vs7.rev), ' vs 7-day avg · today ', h('b', {}, F.short(s.today_rev))]),
      tile('Meta ROAS', F.x(s.y.roas), [delta(s.y_vs7.roas), ' vs ', h('b', {}, F.x(s.avg7.roas)), ' 7-day']),
      tile('CPA', F.money2(s.y.cpa), [delta(s.y_vs7.cpa, true), ' vs 7-day avg · ', h('b', {}, F.int(s.y.orders)), ' purchases']),
      tile('New-visitor share', F.pct0(s.y.nvp), ['7-day ', h('b', {}, F.pct0(s.avg7.nvp))])));

    const box = attention(s.alerts.map(([lvl, t]) => [null, lvl, t]));
    if (box) main.append(box);

    const d = c.daily, spendSeries = [{name: 'Meta', color: col, area: true, values: d.map((x) => ({d: x.d, v: x.meta}))}];
    if (live) spendSeries.push({name: 'Our creatives', color: css('--ours'), values: d.map((x) => ({d: x.d, v: x.ours}))});
    const nvpSeries = [{name: 'Account', color: col, values: d.map((x) => ({d: x.d, v: x.vis ? x.nv / x.vis : null}))}];
    if (live) nvpSeries.push({name: 'Our creatives', color: css('--ours'), values: d.map((x) => ({d: x.d, v: x.ours_vis ? x.ours_nv / x.ours_vis : null}))});
    main.append(h('div', {class: 'grid3'},
      chartCard('Daily Meta spend', 'Last 60 days', spendSeries, {label: c.name + ' daily Meta spend', yfmt: F.short, tfmt: F.money}),
      chartCard('Meta ROAS', 'Meta-reported revenue ÷ Meta spend, daily', [
        {name: 'Meta ROAS', color: col, values: d.map((x) => ({d: x.d, v: x.meta ? x.rev / x.meta : null}))}], {label: c.name + ' daily Meta ROAS', yfmt: (v) => d3.format('.1f')(v) + '×', tfmt: F.x}),
      chartCard('New-visitor share', 'Share of Meta visitors new to the site, daily', nvpSeries, {label: c.name + ' new-visitor share', yfmt: d3.format('.0%'), tfmt: F.pct})));

    if (live) main.append(h('div', {class: 'card'}, h('div', {class: 'card-h'}, h('h2', {}, 'Our creatives this month'), h('p', {class: 'sub'}, 'Highest spend first. Ad names open in Ads Manager.')),
      c.ours.length ? table([
        {label: 'Ad', cell: (a) => adCell(a, false)},
        {label: 'Spend, month', sort: 'spend_m', cell: spendBar('spend_m', c.ours)},
        {label: 'Last 7 days', sort: 'spend_7', fmt: F.money},
        {label: 'Latest day', sort: 'spend_y', fmt: F.money},
        {label: 'Meta ROAS', sort: 'roas_m', fmt: F.x},
        {label: 'CPA', sort: 'cpa_m', fmt: F.money2},
        {label: 'NVP', sort: 'nvp_m', fmt: F.pct0},
      ], c.ours, 'spend_m', 10) : h('p', {class: 'empty'}, 'No spend on our tagged ads this month.')));

    main.append(h('div', {class: 'card'}, h('div', {class: 'card-h'}, h('h2', {}, 'Top ads in the account, last 7 days'), h('p', {class: 'sub'}, 'Whoever made them. OURS marks our tagged ads.' + (s.top_ad_share_7 ? ` The #1 ad carries ${F.pct0(s.top_ad_share_7)} of Meta spend.` : ''))),
      table([
        {label: 'Ad', cell: (a) => adCell(a, true)},
        {label: 'Spend, 7d', sort: 'spend_7', cell: spendBar('spend_7', c.top)},
        {label: 'Latest day', sort: 'spend_y', fmt: F.money},
        {label: 'Meta ROAS', sort: 'roas_7', fmt: F.x},
        {label: 'CPA', sort: 'cpa_7', fmt: F.money2},
        {label: 'NVP', sort: 'nvp_7', fmt: F.pct0},
        {label: 'CTR', sort: 'ctr_7', fmt: F.pct},
      ], c.top, 'spend_7', 10)));
  }

  boot();
})();
