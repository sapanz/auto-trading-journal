/* Home dashboard: turns the embedded trades into an interactive page.
 * All numbers come from DashLogic (dashboard_logic.js, unit tested); this file
 * only decides what to show and wires up the interactions. DOM is built with
 * textContent / createElement - never string-concatenated HTML - so trade
 * notes, symbols and tags can't inject markup.
 */
(function () {
  'use strict';

  var L = window.DashLogic;
  var data = JSON.parse(document.getElementById('journal-data').textContent);
  var trades = data.trades;
  var meta = data.meta || {};

  var QUOTES = [
    ['The elements of good trading are cutting losses, cutting losses, and cutting losses.', 'Ed Seykota'],
    ['It’s not whether you’re right or wrong, but how much money you make when you’re right and how much you lose when you’re wrong.', 'George Soros'],
    ['The goal of a successful trader is to make the best trades. Money is secondary.', 'Alexander Elder'],
    ['Amateurs think about how much money they can make. Professionals think about how much they could lose.', 'Jack Schwager'],
    ['Plan your trade and trade your plan.', 'Trading proverb'],
    ['Every trade is a lesson; every loss is tuition.', ''],
    ['Discipline is the bridge between goals and accomplishment.', 'Jim Rohn'],
    ['Consistency is what transforms average into excellence.', ''],
  ];

  /* ---------- small helpers ---------- */

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    });
    (kids || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      n.appendChild(typeof c === 'object' ? c : document.createTextNode(String(c)));
    });
    return n;
  }
  var SVG_NS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs) {
    var n = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function $(id) { return document.getElementById(id); }
  function fill(node, kids) { node.replaceChildren.apply(node, kids.filter(Boolean)); }

  // localStorage can throw (private mode, blocked storage): every use is guarded.
  var store = {
    get: function (k) { try { return window.localStorage.getItem('journal.v1.' + k); } catch (e) { return null; } },
    set: function (k, v) { try { window.localStorage.setItem('journal.v1.' + k, v); } catch (e) { /* ignore */ } },
  };

  function tone(n) { return n > 0 ? 'pos' : n < 0 ? 'neg' : ''; }
  function money(n, o) { return L.inr(n, o); }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : (many || one + 's')); }
  function shortDate(iso) {
    var d = new Date(iso + 'T00:00:00Z');
    return d.getUTCDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()];
  }
  function scrollToId(id) {
    var n = $(id);
    if (n) n.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  }

  // A message that outlives the re-render that follows a save (the form it
  // was typed into is rebuilt, and a filtered row may drop out of the list).
  var toastTimer = null;
  function toast(msg, isError) {
    var t = $('toast');
    t.textContent = msg;
    t.className = 'toast show' + (isError ? ' error' : '');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = 'toast'; }, isError ? 6000 : 2600);
  }

  /* ---------- state ---------- */

  var validRange = L.RANGES.some(function (r) { return r.key === store.get('range'); });
  var state = {
    range: validRange ? store.get('range') : '30d',
    status: 'all',      // all | wins | losses | flagged | unreviewed
    day: null,          // an ISO date picked on the chart / calendar (searches ALL trades, not just the range)
    hour: null, weekday: null, prod: null, q: '',
    sortKey: 'exitTs', sortDir: -1, shown: 25, expanded: null, lesson: null,
    excluded: [], showGross: false, cluster: 'hour',
  };
  // What you had seen at your last visit, captured once at load so re-renders
  // (a range change, a click) don't wipe the "since last visit" / "New" cues.
  var lastSeenAtLoad = store.get('lastExit');
  var milestonesAtLoad = (function () {
    try { var raw = store.get('milestones'); return raw === null ? null : JSON.parse(raw); } catch (e) { return null; }
  }());
  var chart = null;
  var chartIds = [];   // trade ids behind each chart point when the chart is per-trade (single day)

  function view() {
    var today = L.localIso(new Date());
    var win = L.rangeFor(state.range, trades, today);
    var cur = L.sortedAsc(L.inWindow(trades, win));
    var prevT = win.prev ? L.inWindow(trades, win.prev) : [];
    return {
      today: today, win: win, cur: cur,
      S: L.summarize(cur), P: win.prev ? L.summarize(prevT) : null,
      daily: L.dailyRows(cur), all: L.sortedAsc(trades),
    };
  }

  /* ---------- header ---------- */

  function renderHead(v) {
    var h = new Date().getHours();
    $('home-greeting').textContent = (h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening') + '.';
    var patterns = L.buildPatterns(v.cur);
    var line = L.headline(v.S, v.P, L.cleanStreaks(v.all), patterns[0] || null);
    var hl = $('home-headline');
    hl.textContent = line.text;
    hl.className = 'home-headline tone-' + line.tone;

    fill($('range-pills'), L.RANGES.map(function (r) {
      return el('button', {
        type: 'button', class: 'pill' + (state.range === r.key ? ' active' : ''), 'aria-pressed': state.range === r.key ? 'true' : 'false',
        text: r.short,
        onclick: function () {
          state.range = r.key; state.excluded = []; state.hour = state.weekday = state.prod = null;
          store.set('range', r.key); renderAll();
        },
      });
    }));
  }

  /* ---------- since you were last here ---------- */

  var dismissedVisit = false;
  function renderVisit(v) {
    var box = $('visit-strip');
    var s = dismissedVisit ? null : L.sinceVisit(v.all, lastSeenAtLoad);
    if (!s || !s.count) { fill(box, []); return; }
    var text = 'Since you were last here: ' + plural(s.count, 'trade') + ' closed — ' + s.clean + ' clean' +
      (s.flagged ? ', ' + s.flagged + ' flagged' : '') + ', net ' + money(s.net, { plus: true }) + '.';
    fill(box, [el('div', { class: 'visit-strip' }, [
      el('span', { text: text }),
      el('button', { type: 'button', class: 'link-btn', text: 'Dismiss', onclick: function () { dismissedVisit = true; renderVisit(v); } }),
    ])]);
  }

  /* ---------- the four things you control ---------- */

  function delta(text, kind) { return el('span', { class: 'delta delta-' + kind, text: text }); }
  function pointsDelta(cur, prev, unit) {
    if (cur === null || prev === null) return null;
    var d = Math.round(cur - prev);
    if (d === 0) return delta('same as the previous period', 'flat');
    return delta((d > 0 ? '▲ ' : '▼ ') + Math.abs(d) + ' ' + unit + ' vs previous period', d > 0 ? 'up' : 'down');
  }

  function ring(pct) {
    var r = 34, c = 2 * Math.PI * r, p = pct === null ? 0 : Math.max(0, Math.min(100, pct));
    var s = svg('svg', { viewBox: '0 0 80 80', class: 'ring', role: 'img', 'aria-label': pct === null ? 'No trades' : Math.round(pct) + ' percent' });
    s.appendChild(svg('circle', { cx: 40, cy: 40, r: r, class: 'ring-track' }));
    s.appendChild(svg('circle', { cx: 40, cy: 40, r: r, class: 'ring-fill', 'stroke-dasharray': (c * p / 100) + ' ' + c, transform: 'rotate(-90 40 40)' }));
    return s;
  }

  function ctlCard(o) {
    return el('div', { class: 'ctl-card' }, [
      el('div', { class: 'ctl-top' }, [
        o.visual || null,
        el('div', { class: 'ctl-main' }, [
          el('span', { class: 'ctl-label', text: o.label }),
          el('span', { class: 'ctl-value' + (o.valueClass ? ' ' + o.valueClass : ''), text: o.value }),
        ]),
      ]),
      el('p', { class: 'ctl-sub', text: o.sub }),
      o.delta || null,
      o.action ? el('button', { type: 'button', class: 'link-btn', text: o.action.text, onclick: o.action.run }) : null,
    ]);
  }

  function showTrades(patch) {
    state.shown = 25; state.expanded = null;
    Object.keys(patch).forEach(function (k) { state[k] = patch[k]; });
    var v = view();
    renderTrades(v); renderCalendar(v); renderClusters(v);
    scrollToId('trades');
  }

  function renderControls(v) {
    var S = v.S, P = v.P, cs = L.cleanStreaks(v.all);
    var ms = L.milestones(v.all).filter(function (m) { return m.id === 'clean'; })[0];
    var unrev = S.count - S.journaled;
    var cards = [];

    cards.push(ctlCard({
      label: 'Discipline', value: L.pct(S.discipline), visual: ring(S.discipline),
      sub: S.count ? S.clean + ' of ' + plural(S.count, 'trade') + ' had no flags' : 'No trades in this window',
      delta: P ? pointsDelta(S.discipline, P.discipline, 'pts') : null,
      action: S.flagged ? { text: S.flagged === 1 ? 'Show the flagged trade' : 'Show the ' + S.flagged + ' flagged', run: function () { showTrades({ status: 'flagged', day: null }); } } : null,
    }));

    cards.push(ctlCard({
      label: 'Clean streak', value: String(cs.current), valueClass: cs.current >= 3 ? 'pos' : '',
      sub: 'trades in a row without a flag · best ever ' + cs.best,
      delta: ms && ms.next ? delta('Next badge: ' + ms.next + ' in a row', 'flat') : delta('Top badge reached', 'up'),
      action: { text: 'See milestones', run: function () { scrollToId('milestones'); } },
    }));

    cards.push(ctlCard({
      label: 'Journal habit', value: L.pct(S.journalPct), visual: ring(S.journalPct),
      sub: S.count ? S.journaled + ' of ' + plural(S.count, 'trade') + ' reviewed' : 'No trades in this window',
      delta: P ? pointsDelta(S.journalPct, P.journalPct, 'pts') : null,
      action: unrev > 0 ? { text: 'Review ' + unrev + ' now', run: function () { showTrades({ status: 'unreviewed', day: null }); } } : null,
    }));

    var lossDelta = null;
    if (P && P.losses && S.losses) {
      var chg = Math.round((Math.abs(S.avgLoss) - Math.abs(P.avgLoss)) / Math.abs(P.avgLoss) * 100);
      lossDelta = chg === 0 ? delta('same as the previous period', 'flat')
        : delta((chg < 0 ? '▼ ' : '▲ ') + Math.abs(chg) + '% ' + (chg < 0 ? 'smaller' : 'bigger') + ' than the previous period', chg < 0 ? 'up' : 'down');
    }
    cards.push(ctlCard({
      label: 'Average loss', value: S.losses ? money(S.avgLoss) : '—',
      sub: S.wins ? 'average win ' + money(S.avgWin) + (S.payoff ? ' · win/loss ' + S.payoff.toFixed(2) + '×' : '') : 'No winning trades in this window',
      delta: lossDelta,
      action: S.losses ? { text: S.losses === 1 ? 'Show the loss' : 'Show the ' + S.losses + ' losses', run: function () { showTrades({ status: 'losses', day: null }); } } : null,
    }));

    fill($('controls'), cards);
  }

  /* ---------- where you stand (+ chart + what-if) ---------- */

  function statBlock(label, valueNode) {
    return el('div', { class: 'mini-stat' }, [el('span', { class: 'mini-label', text: label }), valueNode]);
  }

  function renderStanding(v) {
    var S = v.S, P = v.P;
    var single = v.win.start === v.win.end;
    var eq = L.equity(single ? v.cur.map(function (t) { return { date: t.date, net: t.net }; }) : v.daily);
    var notes = [];

    if (P && P.count) {
      var d = S.net - P.net;
      notes.push(el('li', { class: d >= 0 ? 'note-up' : 'note-down' }, [
        (d >= 0 ? '▲ ' : '▼ ') + money(Math.abs(d)) + (d >= 0 ? ' better' : ' lower') + ' than the previous period (' + money(P.net, { plus: true }) + ')',
      ]));
    }
    if (!single && S.count && eq.lowDate && eq.fromLow > 0 && eq.last > eq.low) {
      notes.push(el('li', { class: 'note-up' }, ['▲ Up ' + money(eq.fromLow) + ' from your low on ' + shortDate(eq.lowDate)]));
    }
    if (!single && S.count && eq.belowPeak < 0 && eq.peakDate) {      // no "best point" if it never got above zero
      notes.push(el('li', {}, [money(Math.abs(eq.belowPeak)) + ' below your best point on ' + shortDate(eq.peakDate)]));
    }
    if (S.count && S.gross > 0 && S.net < 0) {
      notes.push(el('li', { class: 'note-focus' }, ['Before charges you were ' + money(S.gross, { plus: true }) + '; ' + money(S.charges) + ' of costs turned it negative — fewer, better trades cut that.']));
    } else if (S.count && S.charges > 0) {
      notes.push(el('li', {}, [money(S.charges) + ' went to charges (' + (S.gross > 0 ? Math.round(S.charges / S.gross * 100) + '% of gross profit' : 'est. brokerage, STT and taxes') + ')']));
    }
    if (meta.capital > 0 && S.count) {
      notes.push(el('li', {}, [(S.net / meta.capital * 100).toFixed(1).replace('-', '−') + '% of your ' + money(meta.capital) + ' capital']));
    }

    fill($('standing-top'), [
      el('div', { class: 'stand-main' }, [
        el('span', { class: 'ctl-label', text: 'Net P&L · ' + v.win.label }),
        el('span', { class: 'stand-value ' + tone(S.net), text: S.count ? money(S.net, { plus: true }) : '—' }),
        el('div', { class: 'breakdown' }, S.count ? [
          el('span', {}, ['Gross ', el('b', { class: tone(S.gross), text: money(S.gross, { plus: true }) })]),
          el('span', {}, ['Charges ', el('b', { text: money(-S.charges) })]),
          el('span', {}, ['Net ', el('b', { class: tone(S.net), text: money(S.net, { plus: true }) })]),
        ] : []),
      ]),
      el('div', { class: 'stand-stats' }, [
        statBlock('Trades', el('b', { text: String(S.count) })),
        statBlock('Win rate', el('b', { text: L.pct(S.winRate) })),
        statBlock('Profit factor', el('b', { text: S.profitFactor === null ? '—' : S.profitFactor.toFixed(2) })),
        statBlock('Per trade', el('b', { class: tone(S.expectancy), text: S.count ? money(S.expectancy, { plus: true }) : '—' })),
      ]),
      notes.length ? el('ul', { class: 'stand-notes' }, notes) : null,
    ]);

    renderWhatIf(v);
    drawChart(v, single);
  }

  function renderWhatIf(v) {
    var patterns = L.buildPatterns(v.cur);
    state.excluded = state.excluded.filter(function (id) { return patterns.some(function (p) { return p.id === id; }); });
    var box = $('whatif');
    if (!patterns.length) { fill(box, []); return; }

    var chips = patterns.map(function (p) {
      var on = state.excluded.indexOf(p.id) !== -1;
      return el('button', {
        type: 'button', class: 'chip' + (on ? ' on' : '') + (p.net < 0 ? ' costly' : ''), 'aria-pressed': on ? 'true' : 'false',
        title: plural(p.count, 'trade') + ', net ' + money(p.net, { plus: true }),
        onclick: function () {
          var i = state.excluded.indexOf(p.id);
          if (i === -1) state.excluded.push(p.id); else state.excluded.splice(i, 1);
          renderStanding(v);
        },
      }, [p.label, el('span', { class: 'chip-amt ' + tone(p.net), text: ' ' + money(p.net, { plus: true }) })]);
    });

    var result = null;
    if (state.excluded.length) {
      var kept = L.without(v.cur, state.excluded), K = L.summarize(kept);
      var diff = K.net - v.S.net, setAside = v.cur.length - kept.length;
      result = el('p', { class: 'whatif-result' }, [
        'Setting aside ' + plural(setAside, 'trade') + ' → net ', el('b', { class: tone(K.net), text: money(K.net, { plus: true }) }),
        diff >= 0 ? ' (' + money(diff) + ' better)' : ' (' + money(Math.abs(diff)) + ' worse — those trades were net profitable)',
        '. ', el('span', { class: 'muted', text: 'Hindsight only: it shows where the money went, not what would have happened.' }),
      ]);
    }
    fill(box, [
      el('h3', { text: 'What if I hadn’t taken…' }),
      el('p', { class: 'muted small', text: 'Tap a pattern to set those trades aside and see the curve without them.' }),
      el('div', { class: 'chips' }, chips),
      result,
    ]);
  }

  function drawChart(v, single) {
    var wrap = $('chart-wrap'), canvas = $('equity-canvas'), msg = $('chart-msg');
    var rows = single ? v.cur.map(function (t) { return { date: t.exitTs.slice(11, 16), net: t.net, gross: t.gross, id: t.id }; })
      : v.daily;
    chartIds = single ? rows.map(function (r) { return r.id; }) : [];
    $('chart-hint').textContent = '';
    if (!rows.length) {
      if (chart) { chart.destroy(); chart = null; }
      wrap.classList.add('empty'); msg.textContent = 'No trades in this window — nothing to plot.'; return;
    }
    if (rows.length < 2) {
      if (chart) { chart.destroy(); chart = null; }
      wrap.classList.add('empty'); msg.textContent = 'Just one closed trade so far \u2014 the curve appears once there are two.'; return;
    }
    wrap.classList.remove('empty');
    if (!window.Chart) { msg.textContent = 'The chart library could not be loaded (offline?). Your numbers above are unaffected.'; wrap.classList.add('empty'); return; }

    var eq = L.equity(rows);
    var labels = single ? rows.map(function (r) { return r.date; }) : eq.dates;
    var accent = cssVar('--accent') || '#2563eb', good = cssVar('--positive') || '#16a34a', muted = cssVar('--muted') || '#94a3b8';
    var grid = cssVar('--border') || '#e2e8f0';
    var datasets = [{
      label: 'Net P&L', data: eq.cum, borderColor: accent, backgroundColor: accent + '22', fill: true, tension: 0.2,
      borderWidth: 2, pointRadius: labels.length <= 40 ? 3 : 0, pointHoverRadius: 6,
    }];
    if (state.showGross) {
      var run = 0;
      datasets.push({ label: 'Gross (before charges)', data: rows.map(function (r) { run += r.gross; return run; }), borderColor: muted, borderWidth: 1.5, borderDash: [2, 3], pointRadius: 0, fill: false, tension: 0.2 });
    }
    if (state.excluded.length) {
      var kept = L.without(v.cur, state.excluded), keptIds = {}, byDate = {}, acc = 0;
      kept.forEach(function (t) { keptIds[t.id] = true; byDate[t.date] = (byDate[t.date] || 0) + t.net; });
      var without = single ? rows.map(function (r) { acc += keptIds[r.id] ? r.net : 0; return acc; })
        : rows.map(function (r) { acc += byDate[r.date] || 0; return acc; });
      datasets.push({ label: 'Without the selected trades', data: without, borderColor: good, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, fill: false, tension: 0.2 });
    }

    var options = {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      onClick: function (evt, _els, ch) {
        var hit = ch.getElementsAtEventForMode(evt, 'index', { intersect: false }, true);
        if (!hit.length) return;
        var i = hit[0].index;
        if (single) { showTrades({ expanded: chartIds[i], day: null, status: 'all' }); }
        else { showTrades({ day: eq.dates[i], status: 'all' }); }
      },
      plugins: {
        legend: { display: datasets.length > 1, labels: { color: muted, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            title: function (items) { return single ? 'Closed ' + items[0].label : shortDate(items[0].label); },
            label: function (item) {
              var r = rows[item.dataIndex], base = item.dataset.label + ': ' + money(item.parsed.y, { plus: true });
              return item.datasetIndex === 0 ? [base, (single ? 'This trade: ' : 'That day: ') + money(r.net, { plus: true })] : base;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: muted, maxTicksLimit: 8, callback: function (val) { var l = this.getLabelForValue(val); return single ? l : shortDate(l); } }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { color: muted, callback: function (val) { return money(val); } }, grid: { color: function (c) { return c.tick.value === 0 ? muted : grid; }, lineWidth: function (c) { return c.tick.value === 0 ? 1.5 : 1; } } },
      },
    };

    if (chart) { chart.data.labels = labels; chart.data.datasets = datasets; chart.options = options; chart.update(); }
    else chart = new window.Chart(canvas, { type: 'line', data: { labels: labels, datasets: datasets }, options: options });
    $('chart-hint').textContent = single ? 'Each point is a closed trade — click one to open it.' : 'Click a point to see that day’s trades.';
  }

  /* ---------- milestones ---------- */

  function renderMilestones(v) {
    var ms = L.milestones(v.all);
    var seen = milestonesAtLoad || {}, hasSeen = milestonesAtLoad !== null;

    var rows = ms.map(function (m) {
      var fresh = hasSeen && m.reached > (seen[m.id] || 0);
      var dots = m.tiers.map(function (t, i) { return el('span', { class: 'tier' + (i < m.reached ? ' earned' : ''), title: t + ' ' + m.unit }); });
      return el('div', { class: 'milestone' }, [
        el('div', { class: 'ms-head' }, [
          el('span', { class: 'ms-title', text: m.title }),
          fresh ? el('span', { class: 'new-pill', text: 'New' }) : null,
        ]),
        el('div', { class: 'ms-tiers' }, dots),
        el('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(m.progress * 100) }, [
          el('span', { class: 'bar-fill', style: 'width:' + Math.round(m.progress * 100) + '%' }),
        ]),
        el('div', { class: 'ms-foot' }, [
          el('span', { text: m.complete ? 'Top tier reached — ' + m.value + ' ' + m.unit : m.value + ' of ' + m.next + ' ' + m.unit }),
          m.current !== m.value ? el('span', { class: 'muted', text: 'now ' + m.current }) : null,
        ]),
        el('p', { class: 'muted small', text: m.blurb }),
      ]);
    });
    fill($('milestones-body'), rows);
    var snapshot = {};
    ms.forEach(function (m) { snapshot[m.id] = m.reached; });
    store.set('milestones', JSON.stringify(snapshot));
  }

  /* ---------- calendar ---------- */

  function renderCalendar(v) {
    var weeks = L.calendarWeeks(L.dailyRows(v.all), v.today, 20);
    var months = weeks.map(function (w, i) {
      var m = shortDate(w.weekStart).split(' ')[1];
      var prev = i ? shortDate(weeks[i - 1].weekStart).split(' ')[1] : null;
      return el('span', { class: 'cal-month', text: m !== prev ? m : '' });
    });
    var grid = el('div', { class: 'cal-grid' }, weeks.map(function (w) {
      return el('div', { class: 'cal-col' }, w.days.map(function (d) {
        var label = d.future ? '' : shortDate(d.date) + ': ' + (d.net === null ? 'no trades' : money(d.net, { plus: true }) + ' from ' + plural(d.count, 'trade'));
        return el('button', {
          type: 'button', class: 'cal-cell lv-' + d.level + (state.day === d.date ? ' picked' : ''), title: label, 'aria-label': label || null,
          disabled: d.future || d.net === null ? true : null,
          onclick: function () { showTrades({ day: d.date, status: 'all' }); },
        });
      }));
    }));
    var legend = el('div', { class: 'cal-legend' }, [
      el('span', { class: 'muted small', text: 'Down' }),
      el('i', { class: 'cal-cell lv-loss-4' }), el('i', { class: 'cal-cell lv-loss-2' }), el('i', { class: 'cal-cell lv-zero' }),
      el('i', { class: 'cal-cell lv-win-2' }), el('i', { class: 'cal-cell lv-win-4' }),
      el('span', { class: 'muted small', text: 'Up' }),
    ]);
    fill($('calendar-body'), [
      el('div', { class: 'cal-months' }, months),
      el('div', { class: 'cal-wrap' }, [
        el('div', { class: 'cal-days' }, ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].map(function (d, i) { return el('span', { text: i % 2 === 0 ? d : '' }); })),
        grid,
      ]),
      legend,
    ]);
    var active = L.dailyRows(v.all).filter(function (r) { return r.date >= weeks[0].weekStart; });
    var green = active.filter(function (r) { return r.net > 0; }).length;
    $('calendar-note').textContent = active.length ? green + ' of ' + plural(active.length, 'trading day') + ' ended in profit over the last 20 weeks. Click any day to see its trades.' : 'Trading days will show up here.';
  }

  /* ---------- where the losses cluster ---------- */

  function renderClusters(v) {
    var tabs = [['hour', 'Time of day'], ['weekday', 'Weekday'], ['product', 'Product']];
    var c = L.lossClusters(v.cur)[state.cluster];
    var losing = c.filter(function (b) { return b.lossSum < 0; });
    var totalLoss = losing.reduce(function (a, b) { return a + b.lossSum; }, 0);
    var maxLoss = losing.reduce(function (a, b) { return Math.min(a, b.lossSum); }, 0);
    var top = losing.slice().sort(function (a, b) { return a.lossSum - b.lossSum; })[0];

    var rows = c.map(function (b) {
      var w = b.lossSum < 0 && maxLoss < 0 ? Math.max(3, Math.round(b.lossSum / maxLoss * 100)) : 0;
      var picked = state[state.cluster] === b.key;
      return el('button', {
        type: 'button', class: 'bar-row' + (picked ? ' picked' : ''), 'aria-pressed': picked ? 'true' : 'false',
        title: plural(b.lossCount, 'losing trade') + ' of ' + b.count + ', net ' + money(b.net, { plus: true }),
        onclick: function () {
          var patch = { day: null, status: 'all', hour: null, weekday: null, prod: null };
          patch[state.cluster === 'product' ? 'prod' : state.cluster] = picked ? null : b.key;
          showTrades(patch);
        },
      }, [
        el('span', { class: 'bar-label', text: b.label }),
        el('span', { class: 'hbar' }, [el('span', { class: 'hbar-fill', style: 'width:' + w + '%' })]),
        el('span', { class: 'bar-amt', text: b.lossSum < 0 ? money(b.lossSum) : '—' }),
      ]);
    });

    fill($('clusters-body'), [
      el('div', { class: 'tabs', role: 'tablist' }, tabs.map(function (t) {
        return el('button', { type: 'button', role: 'tab', class: 'tab' + (state.cluster === t[0] ? ' active' : ''), 'aria-selected': state.cluster === t[0] ? 'true' : 'false', text: t[1],
          onclick: function () { state.cluster = t[0]; renderClusters(v); } });
      })),
      c.length ? el('div', { class: 'bars' }, rows) : el('p', { class: 'muted', text: 'No trades in this window.' }),
      top && totalLoss < 0 ? el('p', { class: 'cluster-note', text: Math.round(top.lossSum / totalLoss * 100) + '% of your losses (' + money(top.lossSum) + ') came from ' +
        (state.cluster === 'hour' ? 'entries in the ' + top.label + ' hour' : state.cluster === 'weekday' ? top.label + 's' : top.label + ' trades') + '. Tap a bar to see those trades.' }) : null,
    ]);
  }

  /* ---------- biggest setbacks ---------- */

  function renderSetbacks(v) {
    var list = L.biggestLosses(v.cur, 5);
    if (!list.length) {
      fill($('setbacks-body'), [el('p', { class: 'muted', text: v.S.count ? 'No losing trades in this window — nothing to learn from the downside here.' : 'No trades in this window.' })]);
      return;
    }
    fill($('setbacks-body'), list.map(function (item) {
      var t = item.trade, open = state.lesson === t.id;
      var area = el('textarea', { rows: 3, 'aria-label': 'What did this trade teach you?', placeholder: 'What did this trade teach you? What will you do differently?' });
      area.value = t.note || '';
      var status = el('span', { class: 'muted small', 'aria-live': 'polite' });
      return el('article', { class: 'setback' }, [
        el('div', { class: 'setback-head' }, [
          el('b', { text: t.sym }), el('span', { class: 'neg', text: money(t.net) }),
          el('span', { class: 'muted small', text: shortDate(t.date) }),
        ]),
        el('p', { class: 'muted small', text: item.hint }),
        el('div', { class: 'tag-row' }, t.tags.map(function (n) { return tagChip(n); })),
        t.note && !open ? el('p', { class: 'lesson', text: '“' + t.note + '”' }) : null,
        open ? el('div', { class: 'lesson-form' }, [area, el('div', { class: 'row' }, [
          el('button', { type: 'button', class: 'btn', text: 'Save lesson', onclick: function () { saveReview(t, area.value, t.rating, status); } }), status,
        ])]) : el('button', { type: 'button', class: 'link-btn', text: t.note ? 'Edit lesson' : 'Add a lesson', onclick: function () { state.lesson = t.id; renderSetbacks(v); } }),
      ]);
    }));
  }

  function tagChip(name) {
    var cls = { 'Big Loss': 'tag-loss', 'Big Win': 'tag-win', 'Quick Scalp': 'tag-scalp', 'Possible Revenge Trade': 'tag-revenge' }[name] || 'tag-custom';
    return el('span', { class: 'tag ' + cls, text: name });
  }

  /* ---------- saving a note / rating ---------- */

  function saveReview(t, notes, rating, statusEl) {
    statusEl.textContent = 'Saving…';
    fetch('/api/positions/' + t.id + '/review', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ notes: notes, rating: rating }),
    }).then(function (r) {
      if (r.redirected || !(r.headers.get('content-type') || '').includes('json')) throw new Error('Your session expired — reload the page and sign in again.');
      if (!r.ok) throw new Error('Could not save (' + r.status + ').');
      return r.json();
    }).then(function (j) {
      t.note = j.note; t.rating = j.rating;
      statusEl.textContent = 'Saved.';
      var v = view(); renderControls(v); renderMilestones(v); renderTrades(v);
      toast('Saved \u2014 ' + t.sym + (j.note ? ' reviewed.' : '.'));
      if (state.lesson === t.id) { state.lesson = null; renderSetbacks(v); }
    }).catch(function (e) { statusEl.textContent = e.message; toast(e.message, true); });
  }

  /* ---------- the trades table ---------- */

  var STATUS = [['all', 'All'], ['wins', 'Wins'], ['losses', 'Losses'], ['flagged', 'Flagged'], ['unreviewed', 'Needs review']];
  var COLUMNS = [['exitTs', 'Closed'], ['sym', 'Symbol'], ['prod', 'Type'], ['qty', 'Qty'], ['entry', 'Entry → exit'], ['hold', 'Held'], ['net', 'Net P&L'], ['roi', 'ROI'], ['tags', 'Flags']];

  function heldText(m) { return m < 1 ? '<1 min' : m < 90 ? Math.round(m) + ' min' : m < 1440 ? (m / 60).toFixed(1) + ' h' : Math.round(m / 1440) + ' d'; }

  function filteredTrades(v) {
    var base = state.day ? v.all.filter(function (t) { return t.date === state.day; }) : v.cur;
    var q = state.q.trim().toLowerCase();
    var out = base.filter(function (t) {
      if (state.status === 'wins' && !(t.net > 0)) return false;
      if (state.status === 'losses' && !(t.net < 0)) return false;
      if (state.status === 'flagged' && !L.isFlagged(t)) return false;
      if (state.status === 'unreviewed' && L.isReviewed(t)) return false;
      if (state.hour !== null && t.entryTs.slice(11, 13) !== state.hour) return false;
      if (state.weekday !== null && String(L.weekdayIndex(t.date)) !== state.weekday) return false;
      if (state.prod !== null && t.prod !== state.prod) return false;
      if (q && (t.sym + ' ' + t.tags.join(' ') + ' ' + t.note).toLowerCase().indexOf(q) === -1) return false;
      return true;
    });
    var k = state.sortKey, d = state.sortDir;
    out.sort(function (a, b) {
      var x = k === 'tags' ? a.tags.length : a[k], y = k === 'tags' ? b.tags.length : b[k];
      return (x < y ? -1 : x > y ? 1 : 0) * d;
    });
    return out;
  }

  function activeFilterChips(v) {
    var chips = [];
    function chip(text, clear) { chips.push(el('button', { type: 'button', class: 'chip on', title: 'Remove this filter', onclick: function () { clear(); state.shown = 25; renderTrades(view()); } }, [text + ' ✕'])); }
    if (state.day) chip('Day: ' + shortDate(state.day), function () { state.day = null; });
    if (state.hour !== null) chip('Entered in the ' + state.hour + ':00 hour', function () { state.hour = null; });
    if (state.weekday !== null) chip(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][+state.weekday] + 's', function () { state.weekday = null; });
    if (state.prod !== null) chip(state.prod + ' only', function () { state.prod = null; });
    return chips;
  }

  function reviewForm(t) {
    var sel = el('select', { 'aria-label': 'Self-rating' }, [el('option', { value: '', text: 'No rating' })].concat([1, 2, 3, 4, 5].map(function (i) {
      return el('option', { value: String(i), text: i + (i === 1 ? ' — poor' : i === 5 ? ' — followed the plan' : '') });
    })));
    sel.value = t.rating ? String(t.rating) : '';
    var area = el('textarea', { rows: 3, 'aria-label': 'Journal note', placeholder: 'What was the plan? Did you follow it? What would you do differently?' });
    area.value = t.note || '';
    var status = el('span', { class: 'muted small', 'aria-live': 'polite' });
    return el('div', { class: 'review' }, [
      el('label', { class: 'muted small', text: 'Self-rating' }), sel,
      el('label', { class: 'muted small', text: 'Note' }), area,
      el('div', { class: 'row' }, [
        el('button', { type: 'button', class: 'btn', text: 'Save', onclick: function () { saveReview(t, area.value, sel.value ? +sel.value : null, status); } }),
        el('a', { href: '/positions/' + t.id, class: 'link-btn', text: 'Open full page' }), status,
      ]),
    ]);
  }

  function tradeRows(t) {
    var open = state.expanded === t.id;
    var main = el('tr', { class: 'trow ' + (t.net > 0 ? 'won' : t.net < 0 ? 'lost' : '') + (open ? ' open' : ''), 'data-id': t.id }, [
      el('td', {}, [el('span', { text: shortDate(t.date) }), el('span', { class: 'muted small', text: ' ' + t.exitTs.slice(11, 16) })]),
      el('td', {}, [el('b', { text: t.sym })]),
      el('td', {}, [t.prod + ' · ' + (t.dir === 'SHORT' ? 'short' : 'long')]),
      el('td', { text: String(t.qty) }),
      el('td', { text: t.entry.toFixed(2) + ' → ' + t.exit.toFixed(2) }),
      el('td', { text: heldText(t.hold) }),
      el('td', { class: 'num ' + tone(t.net), text: money(t.net, { plus: true, decimals: 2 }) }),
      el('td', { class: tone(t.roi), text: t.roi.toFixed(2).replace('-', '−') + '%' }),
      el('td', {}, t.tags.map(tagChip).concat(L.isReviewed(t) ? [el('span', { class: 'reviewed', title: 'Reviewed', text: '✎' })] : [])),
      el('td', {}, [el('button', { type: 'button', class: 'link-btn', 'aria-expanded': open ? 'true' : 'false', text: open ? 'Close' : 'Details',
        onclick: function (e) { e.stopPropagation(); state.expanded = open ? null : t.id; renderTrades(view()); } })]),
    ]);
    if (!open) return [main];
    var det = el('tr', { class: 'detail-row' }, [el('td', { colspan: COLUMNS.length + 1 }, [
      el('div', { class: 'detail-grid-2' }, [
        el('div', { class: 'facts' }, [
          fact('Gross', money(t.gross, { plus: true, decimals: 2 }), tone(t.gross)), fact('Charges', money(-t.charges, { decimals: 2 })),
          fact('Net', money(t.net, { plus: true, decimals: 2 }), tone(t.net)), fact('Entered', t.entryTs.replace('T', ' ').slice(0, 16)), fact('Closed', t.exitTs.replace('T', ' ').slice(0, 16)),
        ]),
        reviewForm(t),
      ]),
    ])]);
    return [main, det];
  }
  function fact(label, value, cls) { return el('div', {}, [el('span', { class: 'muted small', text: label }), el('b', { class: cls || '', text: value })]); }

  function renderTrades(v) {
    var list = filteredTrades(v);
    var shown = list.slice(0, state.shown);
    var searchBox = el('input', { type: 'search', class: 'search', placeholder: 'Search symbol, flag or note', 'aria-label': 'Search trades', value: state.q });
    searchBox.addEventListener('input', function () {
      state.q = searchBox.value; state.shown = 25;
      var pos = searchBox.selectionStart; renderTrades(view());
      var again = $('trades-body').querySelector('.search'); if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (e) { /* ignore */ } }
    });

    var head = el('tr', {}, COLUMNS.map(function (c) {
      var on = state.sortKey === c[0];
      return el('th', { 'aria-sort': on ? (state.sortDir > 0 ? 'ascending' : 'descending') : 'none' }, [
        el('button', { type: 'button', class: 'th-btn' + (on ? ' on' : ''), text: c[1] + (on ? (state.sortDir > 0 ? ' ▲' : ' ▼') : ''),
          onclick: function () { if (on) state.sortDir *= -1; else { state.sortKey = c[0]; state.sortDir = c[0] === 'sym' || c[0] === 'prod' ? 1 : -1; } renderTrades(view()); } }),
      ]);
    }).concat([el('th')]));

    var body = [];
    shown.forEach(function (t) { tradeRows(t).forEach(function (r) { body.push(r); }); });

    fill($('trades-body'), [
      el('div', { class: 'toolbar' }, [
        el('div', { class: 'seg', role: 'group', 'aria-label': 'Filter trades' }, STATUS.map(function (s) {
          return el('button', { type: 'button', class: 'seg-btn' + (state.status === s[0] ? ' active' : ''), 'aria-pressed': state.status === s[0] ? 'true' : 'false', text: s[1],
            onclick: function () { state.status = s[0]; state.shown = 25; renderTrades(view()); } });
        })),
        searchBox,
      ]),
      activeFilterChips(v).length ? el('div', { class: 'chips' }, activeFilterChips(v)) : null,
      el('p', { class: 'muted small', text: (state.day ? 'Every trade closed on ' + shortDate(state.day) : v.win.label) + ' — ' + plural(list.length, 'trade') + (list.length !== shown.length ? ', showing ' + shown.length : '') + '.' }),
      list.length ? el('div', { class: 'table-scroll' }, [el('table', { class: 'trade-table' }, [el('thead', {}, [head]), el('tbody', {}, body)])])
        : el('p', { class: 'empty-note', text: v.all.length ? 'Nothing matches these filters.' : 'No closed trades yet — once the fetcher syncs your trades they will show up here.' }),
      list.length > shown.length ? el('button', { type: 'button', class: 'btn ghost', text: 'Show ' + Math.min(25, list.length - shown.length) + ' more', onclick: function () { state.shown += 25; renderTrades(view()); } }) : null,
    ]);
  }

  /* ---------- quote ---------- */

  var quoteIndex = 0;
  function renderQuote() {
    var q = QUOTES[quoteIndex % QUOTES.length];
    fill($('quote'), [el('span', { class: 'quote-text', text: '“' + q[0] + '”' }), q[1] ? el('span', { class: 'quote-by', text: ' — ' + q[1] }) : null]);
  }

  /* ---------- go ---------- */

  function renderAll() {
    var v = view();
    renderHead(v); renderVisit(v); renderControls(v); renderStanding(v); renderMilestones(v);
    renderCalendar(v); renderClusters(v); renderSetbacks(v); renderTrades(v);
  }

  quoteIndex = Math.floor(Math.random() * QUOTES.length);
  renderQuote();
  $('quote').addEventListener('click', function () { quoteIndex++; renderQuote(); });
  $('show-gross').addEventListener('change', function (e) { state.showGross = e.target.checked; renderStanding(view()); });
  renderAll();

  // Remember where you got to, so next time the page can say what's new since.
  if (trades.length) store.set('lastExit', L.sortedAsc(trades).slice(-1)[0].exitTs);
})();
