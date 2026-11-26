// Run: node --test website/tests/dashboard_logic.test.mjs   (Node 18+)
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const L = createRequire(import.meta.url)('../app/static/dashboard_logic.js');

let nextId = 1;
/** A closed trade; exit defaults to entry + 30 min, gross to net + charges. */
function mk(date, net, o = {}) {
  const entry = o.entry || '10:00:00';
  const [h, m] = entry.split(':').map(Number);
  const hold = o.hold == null ? 30 : o.hold;
  const exitMin = h * 60 + m + hold;
  const exitHM = String(Math.floor(exitMin / 60)).padStart(2, '0') + ':' + String(Math.floor(exitMin % 60)).padStart(2, '0');
  const charges = o.charges == null ? 20 : o.charges;
  return {
    id: o.id || nextId++, sym: o.sym || 'TCS', prod: o.prod || 'MIS', dir: o.dir || 'LONG', qty: 10,
    entry: 100, exit: 101, entryTs: `${date}T${entry}`, exitTs: `${date}T${exitHM}:00`, date,
    hold, gross: net + charges, charges, net, roi: net / 10, tags: o.tags || [], rating: o.rating || null, note: o.note || '',
  };
}
const approx = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);

/* ---------- dates ---------- */

test('date helpers: week start, FY boundaries and arithmetic across month ends', () => {
  assert.equal(L.weekStart('2026-11-26'), '2026-11-23');          // a Thursday -> its Monday
  assert.equal(L.weekStart('2026-11-23'), '2026-11-23');
  assert.equal(L.weekdayIndex('2026-11-22'), 6);                  // Sunday
  assert.equal(L.addDays('2026-11-30', 1), '2026-12-01');
  assert.equal(L.addDays('2026-03-01', -1), '2026-02-28');
  assert.equal(L.daysBetween('2026-11-01', '2026-11-26'), 25);
  assert.equal(L.fyStart('2026-11-26'), '2026-04-01');
  assert.equal(L.fyStart('2027-02-10'), '2026-04-01');            // Jan-Mar belongs to the FY that began the April before
  assert.equal(L.fyStart('2026-04-01'), '2026-04-01');
  assert.equal(L.fyLabel('2026-11-26'), '2026-27');
  assert.equal(L.fyLabel('2027-02-10'), '2026-27');
  assert.equal(L.minutesOfDay('2026-11-20T09:21:10'), 561);
});

/* ---------- ranges ---------- */

test('rangeFor: latest day falls back to the last trading day on a weekend, with the previous trading day to compare', () => {
  const trades = [mk('2026-11-18', 1), mk('2026-11-19', 1), mk('2026-11-20', 1)];   // Wed-Fri
  const r = L.rangeFor('day', trades, '2026-11-22');                                // Sunday
  assert.deepEqual([r.start, r.end], ['2026-11-20', '2026-11-20']);
  assert.deepEqual(r.prev, { start: '2026-11-19', end: '2026-11-19' });
  assert.match(r.label, /Latest trading day/);
  assert.equal(L.rangeFor('day', trades, '2026-11-20').label, 'Today');
  assert.equal(L.rangeFor('day', trades.slice(0, 1), '2026-11-18').prev, null);     // nothing before the first day
});

test('rangeFor: 7d, 30d and FY windows are inclusive and the previous window is the same length right before', () => {
  const t = [mk('2026-01-05', 1)];
  const w7 = L.rangeFor('7d', t, '2026-11-26');
  assert.deepEqual([w7.start, w7.end], ['2026-11-20', '2026-11-26']);
  assert.deepEqual(w7.prev, { start: '2026-11-13', end: '2026-11-19' });
  const w30 = L.rangeFor('30d', t, '2026-11-26');
  assert.equal(L.daysBetween(w30.start, w30.end) + 1, 30);
  assert.equal(L.daysBetween(w30.prev.start, w30.prev.end) + 1, 30);
  assert.equal(L.addDays(w30.prev.end, 1), w30.start);
  const fy = L.rangeFor('fy', t, '2026-11-26');
  assert.equal(fy.start, '2026-04-01');
  assert.equal(L.addDays(fy.prev.end, 1), fy.start);
  assert.equal(L.daysBetween(fy.prev.start, fy.prev.end), L.daysBetween(fy.start, fy.end));
  const all = L.rangeFor('all', t, '2026-11-26');
  assert.deepEqual([all.start, all.end, all.prev], ['2026-01-05', '2026-11-26', null]);
});

test('inWindow is inclusive at both ends and tolerates a missing window', () => {
  const t = [mk('2026-11-19', 1), mk('2026-11-20', 1), mk('2026-11-21', 1)];
  assert.equal(L.inWindow(t, { start: '2026-11-20', end: '2026-11-21' }).length, 2);
  assert.deepEqual(L.inWindow(t, null), []);
});

/* ---------- summaries ---------- */

test('summarize: money, win/loss maths and the discipline / journal percentages', () => {
  const t = [
    mk('2026-11-20', 300),
    mk('2026-11-20', -100, { tags: ['Quick Scalp'] }),
    mk('2026-11-20', -200, { tags: ['Big Loss', 'Possible Revenge Trade'], note: 'chased it' }),
    mk('2026-11-20', 0),
    mk('2026-11-20', 100, { tags: ['Big Win'], rating: 4 }),
  ];
  const s = L.summarize(t);
  assert.equal(s.count, 5);
  assert.deepEqual([s.wins, s.losses], [2, 2]);
  approx(s.net, 100);
  approx(s.charges, 100);
  approx(s.gross, 200);
  assert.equal(s.flagged, 2);                      // Big Win is not a flag
  assert.equal(s.clean, 3);
  approx(s.discipline, 60);
  assert.equal(s.journaled, 2);
  approx(s.journalPct, 40);
  approx(s.winRate, 40);
  approx(s.avgWin, 200);
  approx(s.avgLoss, -150);
  approx(s.payoff, 200 / 150);
  approx(s.profitFactor, 400 / 300);
  approx(s.expectancy, 20);
  assert.equal(s.best.net, 300);
  assert.equal(s.worst.net, -200);
});

test('summarize: empty and one-sided inputs give nulls, not NaN or Infinity', () => {
  const e = L.summarize([]);
  assert.deepEqual([e.count, e.net, e.winRate, e.discipline, e.journalPct, e.payoff, e.profitFactor], [0, 0, null, null, null, null, null]);
  const wins = L.summarize([mk('2026-11-20', 50), mk('2026-11-20', 70)]);
  assert.equal(wins.payoff, null);
  assert.equal(wins.profitFactor, null);
  assert.equal(wins.avgLoss, 0);
});

test('a rating of 0 or a whitespace-only note does not count as reviewed', () => {
  assert.equal(L.isReviewed(mk('2026-11-20', 1, { note: '   ' })), false);
  assert.equal(L.isReviewed(mk('2026-11-20', 1, { note: 'plan: VWAP bounce' })), true);
  assert.equal(L.isReviewed(mk('2026-11-20', 1, { rating: 3 })), true);
});

/* ---------- daily rows and equity ---------- */

test('dailyRows groups by exit date in order and nets charges per day', () => {
  const rows = L.dailyRows([mk('2026-11-21', -50), mk('2026-11-20', 200), mk('2026-11-20', -30)]);
  assert.deepEqual(rows.map(r => [r.date, r.net, r.count, r.wins]), [['2026-11-20', 170, 2, 1], ['2026-11-21', -50, 1, 0]]);
  approx(rows[0].charges, 40);
});

test('equity: peak, low, recovery from the low and drawdown', () => {
  // cumulative: +100, -200, -500, -300, -100  (a slide, then a climb back)
  const daily = [100, -300, -300, 200, 200].map((net, i) => ({ date: `2026-11-0${i + 1}`, net }));
  const e = L.equity(daily);
  assert.deepEqual(e.cum, [100, -200, -500, -300, -100]);
  assert.equal(e.last, -100);
  assert.equal(e.peak, 100);
  assert.equal(e.low, -500);
  assert.equal(e.lowDate, '2026-11-03');
  assert.equal(e.fromLow, 400);                     // up 400 from the low
  assert.equal(e.belowPeak, -200);
  assert.deepEqual(e.dd, [0, -300, -600, -400, -200]);
  assert.equal(e.maxDrawdown, -600);
});

test('equity: a series that only ever rises has no "low date" and no drawdown', () => {
  const e = L.equity([{ date: '2026-11-01', net: 50 }, { date: '2026-11-02', net: 25 }]);
  assert.equal(e.lowDate, null);
  assert.equal(e.low, 0);
  assert.equal(e.maxDrawdown, 0);
  assert.equal(e.fromLow, 75);
  assert.deepEqual(L.equity([]).cum, []);
});

/* ---------- streaks ---------- */

test('cleanStreaks: current run resets on a flagged trade; best remembers its end date', () => {
  const t = [
    mk('2026-11-02', 1), mk('2026-11-02', 1), mk('2026-11-03', 1),                       // 3 clean
    mk('2026-11-04', -1, { tags: ['Quick Scalp'] }),                                      // flag
    mk('2026-11-05', 1), mk('2026-11-05', 1), mk('2026-11-06', 1), mk('2026-11-06', 1),   // 4 clean
    mk('2026-11-09', 1, { tags: ['Big Win'] }),                                           // Big Win is clean -> 5
    mk('2026-11-10', -1, { tags: ['Big Loss'] }),
    mk('2026-11-11', 1),                                                                  // current = 1
  ];
  const s = L.cleanStreaks(t.slice().reverse());                                         // order of input must not matter
  assert.deepEqual([s.current, s.best, s.bestEnd], [1, 5, '2026-11-09']);
});

test('greenDayStreaks: break-even and losing days end a run', () => {
  const d = [10, 20, -5, 30, 40, 50, 0].map((net, i) => ({ date: `2026-11-${10 + i}`, net }));
  assert.deepEqual(L.greenDayStreaks(d), { current: 0, best: 3 });
  assert.deepEqual(L.greenDayStreaks(d.slice(0, 2)), { current: 2, best: 2 });
});

test('sinceLastBigLoss counts the trades after the latest Big Loss, or all of them if there never was one', () => {
  const t = [mk('2026-11-02', -9, { tags: ['Big Loss'] }), mk('2026-11-03', 1), mk('2026-11-04', -9, { tags: ['Big Loss'] }),
    mk('2026-11-05', 1), mk('2026-11-06', 1), mk('2026-11-09', 1)];
  assert.deepEqual(L.sinceLastBigLoss(t), { run: 3, never: false });
  assert.deepEqual(L.sinceLastBigLoss(t.filter(x => !x.tags.length)), { run: 4, never: true });
});

test('weeklyDiscipline skips thin weeks; weeklyTrend counts weeks that held or improved', () => {
  const week = (monday, flaggedOf, n) => Array.from({ length: n }, (_, i) =>
    mk(L.addDays(monday, i % 5), 1, { tags: i < flaggedOf ? ['Quick Scalp'] : [] }));
  const trades = [
    ...week('2026-10-05', 4, 5),     // 20% clean
    ...week('2026-10-12', 3, 5),     // 40%
    ...week('2026-10-19', 1, 2),     // only 2 trades -> ignored
    ...week('2026-10-26', 1, 5),     // 80%
    ...week('2026-11-02', 1, 5),     // 80%  (held)
    ...week('2026-11-09', 2, 5),     // 60%  (dropped)
    ...week('2026-11-16', 1, 5),     // 80%
    ...week('2026-11-23', 0, 5),     // 100%
  ];
  const weeks = L.weeklyDiscipline(trades);
  assert.deepEqual(weeks.map(w => w.weekStart), ['2026-10-05', '2026-10-12', '2026-10-26', '2026-11-02', '2026-11-09', '2026-11-16', '2026-11-23']);
  assert.deepEqual(weeks.map(w => Math.round(w.discipline)), [20, 40, 80, 80, 60, 80, 100]);
  // steps: up, up, hold, DOWN, up, up  -> best run 3 (before the drop), current 2
  assert.deepEqual(L.weeklyTrend(weeks), { current: 2, best: 3 });
  assert.deepEqual(L.weeklyTrend(weeks.slice(0, 1)), { current: 0, best: 0 });
});

/* ---------- milestones ---------- */

test('milestones: tiers, progress to the next one, and badges that stay earned', () => {
  // 12 clean trades in a row, 2 reviewed, one green day, no Big Loss ever
  const t = Array.from({ length: 12 }, (_, i) => mk(L.addDays('2026-11-02', Math.floor(i / 2)), i === 0 ? 5 : 1,
    { note: i < 2 ? 'ok' : '' }));
  const m = Object.fromEntries(L.milestones(t).map(x => [x.id, x]));
  assert.deepEqual([m.clean.value, m.clean.reached, m.clean.next], [12, 2, 20]);
  approx(m.clean.progress, (12 - 10) / (20 - 10));
  assert.deepEqual([m.journal.value, m.journal.reached, m.journal.next], [2, 0, 10]);
  approx(m.journal.progress, 0.2);
  assert.equal(m.green.value, 6);                                      // 6 trading days, all green
  assert.equal(m.nobig.value, 12);
  // a flag at the end resets the current streak but not the earned badge
  const later = t.concat([mk('2026-11-20', -3, { tags: ['Quick Scalp'] })]);
  const m2 = Object.fromEntries(L.milestones(later).map(x => [x.id, x]));
  assert.deepEqual([m2.clean.value, m2.clean.current, m2.clean.reached], [12, 0, 2]);
});

test('milestones: a completed ladder reports progress 1 and no next tier', () => {
  const t = Array.from({ length: 60 }, (_, i) => mk(L.addDays('2026-06-01', Math.floor(i / 2)), 1));
  const clean = L.milestones(t).find(x => x.id === 'clean');
  assert.deepEqual([clean.reached, clean.next, clean.progress, clean.complete], [4, null, 1, true]);
});

/* ---------- what-if ---------- */

test('patternMatcher: tags, product, direction, symbol and entry-time windows', () => {
  const m = id => L.patternMatcher(id);
  assert.ok(m('flag:Quick Scalp')(mk('2026-11-02', 1, { tags: ['Quick Scalp'] })));
  assert.ok(!m('flag:Quick Scalp')(mk('2026-11-02', 1)));
  assert.ok(m('prod:MIS')(mk('2026-11-02', 1, { prod: 'MIS' })));
  assert.ok(m('dir:SHORT')(mk('2026-11-02', 1, { dir: 'SHORT' })));
  assert.ok(m('sym:INFY')(mk('2026-11-02', 1, { sym: 'INFY' })));
  assert.ok(m('time:open')(mk('2026-11-02', 1, { entry: '09:15:00' })));
  assert.ok(m('time:open')(mk('2026-11-02', 1, { entry: '09:29:59' })));
  assert.ok(!m('time:open')(mk('2026-11-02', 1, { entry: '09:30:00' })));
  assert.ok(!m('time:late')(mk('2026-11-02', 1, { entry: '14:29:00' })));
  assert.ok(m('time:late')(mk('2026-11-02', 1, { entry: '14:30:00' })));
  assert.ok(!m('nonsense:x')(mk('2026-11-02', 1)));
});

test('buildPatterns: worst first, needs two trades, and carries what each pattern cost', () => {
  const t = [
    mk('2026-11-02', -300, { tags: ['Quick Scalp'], sym: 'INFY', entry: '09:16:00' }),
    mk('2026-11-02', -200, { tags: ['Quick Scalp'], sym: 'INFY', entry: '09:20:00' }),
    mk('2026-11-03', -50, { tags: ['Big Loss'], sym: 'TCS' }),                    // a single trade: not a pattern
    mk('2026-11-03', 400, { sym: 'WIPRO', prod: 'CNC' }),
    mk('2026-11-04', 150, { sym: 'WIPRO', prod: 'CNC', tags: ['Gap fade'] }),
    mk('2026-11-04', -20, { sym: 'WIPRO', prod: 'CNC', tags: ['Gap fade'] }),
  ];
  const p = L.buildPatterns(t);
  const byId = Object.fromEntries(p.map(x => [x.id, x]));
  assert.ok(!byId['flag:Big Loss']);                                              // only one trade
  assert.deepEqual([byId['flag:Quick Scalp'].count, byId['flag:Quick Scalp'].net], [2, -500]);
  assert.deepEqual([byId['time:open'].count, byId['time:open'].net], [2, -500]);
  assert.ok(byId['sym:INFY'] && byId['tag:Gap fade']);
  assert.equal(byId['tag:Gap fade'].net, 130);
  for (let i = 1; i < p.length; i++) assert.ok(p[i - 1].net <= p[i].net, 'sorted by net, worst first');
  assert.ok(L.buildPatterns(t, { max: 2 }).length <= 2);
});

test('without: removes trades matching ANY selected pattern, and changes the totals accordingly', () => {
  const t = [
    mk('2026-11-02', -300, { tags: ['Quick Scalp'] }),
    mk('2026-11-02', -100, { tags: ['Possible Revenge Trade'] }),
    mk('2026-11-03', 250, { tags: ['Quick Scalp'] }),
    mk('2026-11-03', 120),
  ];
  approx(L.summarize(t).net, -30);
  const noScalp = L.without(t, ['flag:Quick Scalp']);
  assert.equal(noScalp.length, 2);
  approx(L.summarize(noScalp).net, 20);                                          // -100 + 120
  approx(L.summarize(L.without(t, ['flag:Quick Scalp', 'flag:Possible Revenge Trade'])).net, 120);
  assert.equal(L.without(t, []), t);                                              // nothing selected: untouched
  assert.equal(L.without(t, ['flag:Quick Scalp']).includes(t[2]), false);          // it removes profitable ones too - that's honest
});

/* ---------- loss clusters and biggest losses ---------- */

test('lossClusters: buckets by entry hour, weekday and product with loss totals', () => {
  const t = [
    mk('2026-11-23', -100, { entry: '09:20:00' }),                  // Monday 09h
    mk('2026-11-23', 40, { entry: '09:40:00' }),                    // Monday 09h win
    mk('2026-11-24', -60, { entry: '13:05:00', prod: 'CNC' }),      // Tuesday 13h
  ];
  const c = L.lossClusters(t);
  const h09 = c.hour.find(b => b.key === '09');
  assert.deepEqual([h09.label, h09.count, h09.lossCount, h09.lossSum, h09.net], ['09:00', 2, 1, -100, -60]);
  assert.deepEqual(c.weekday.map(b => b.label), ['Mon', 'Tue']);
  assert.equal(c.product[0].key, 'MIS');                           // the product that lost most first
  assert.equal(c.product[0].lossSum, -100);
});

test('biggestLosses: ranks by net, and describes the trade in plain words', () => {
  const t = [
    mk('2026-11-02', -50, { hold: 1.4, entry: '09:21:00' }),
    mk('2026-11-03', -400, { hold: 0.5, entry: '09:16:00', dir: 'SHORT', tags: ['Quick Scalp'] }),
    mk('2026-11-04', -120, { hold: 200, entry: '11:00:00', prod: 'CNC' }),
    mk('2026-11-05', 900),
  ];
  const b = L.biggestLosses(t, 2);
  assert.deepEqual(b.map(x => x.trade.net), [-400, -120]);
  assert.equal(b[0].hint, 'Intraday · short · held under a minute · entered 09:16');
  assert.equal(b[1].hint, 'Delivery · long · held 3.3 h · entered 11:00');
});

/* ---------- calendar ---------- */

test('calendarWeeks: Mon-Fri columns, future days marked, shade scaled to the biggest day', () => {
  const daily = [
    { date: '2026-11-23', net: 400, count: 2 },       // Monday this week
    { date: '2026-11-24', net: -100, count: 1 },
    { date: '2026-11-16', net: 0, count: 1 },         // last week, break-even
  ];
  const cols = L.calendarWeeks(daily, '2026-11-25', 2);             // ends Wednesday 25th
  assert.deepEqual(cols.map(c => c.weekStart), ['2026-11-16', '2026-11-23']);
  assert.equal(cols[0].days.length, 5);
  const cell = (c, i) => cols[c].days[i];
  assert.equal(cell(0, 0).level, 'zero');
  assert.equal(cell(0, 1).level, 'none');
  assert.equal(cell(1, 0).level, 'win-4');                           // the max-abs day gets the top shade
  assert.equal(cell(1, 1).level, 'loss-2');                          // 100/400 = 25% -> bucket 2
  assert.equal(cell(1, 2).level, 'none');                            // Wednesday: today, no trades yet
  assert.equal(cell(1, 3).level, 'future');
  assert.equal(cell(1, 4).future, true);
});

/* ---------- since your last visit ---------- */

test('sinceVisit: only trades that closed after the last one you saw', () => {
  const t = [mk('2026-11-23', 100), mk('2026-11-24', -40, { tags: ['Quick Scalp'] }), mk('2026-11-24', 60, { entry: '14:00:00' })];
  const seen = t[0].exitTs;
  assert.deepEqual(L.sinceVisit(t, seen), { count: 2, net: 20, clean: 1, flagged: 1, wins: 1 });
  assert.deepEqual(L.sinceVisit(t, t[2].exitTs), { count: 0 });
  assert.equal(L.sinceVisit(t, null), null);                         // first ever visit: nothing to compare
});

/* ---------- formatting ---------- */

test('inr uses Indian digit grouping, a real minus sign and optional plus', () => {
  assert.equal(L.inr(1234567), '₹12,34,567');
  assert.equal(L.inr(-1234.5), '−₹1,235');
  assert.equal(L.inr(-1234.5, { decimals: 2 }), '−₹1,234.50');
  assert.equal(L.inr(88, { plus: true }), '+₹88');
  assert.equal(L.inr(0, { plus: true }), '₹0');
  assert.equal(L.pct(61.234, 1), '61.2%');
  assert.equal(L.pct(null), '—');
});

/* ---------- headline ---------- */

test('headline: leads with progress when there is some, otherwise names the costliest pattern', () => {
  const S = (o) => ({ count: 10, discipline: 70, net: -500, flagged: 3, ...o });
  const none = { current: 0 };
  assert.equal(L.headline(S({ count: 0 }), null, none, null).tone, 'neutral');
  // discipline up 3+ points beats everything else
  let h = L.headline(S({ discipline: 80 }), S({ discipline: 70 }), { current: 5 }, null);
  assert.deepEqual([h.tone, h.text.includes('up 10 points')], ['good', true]);
  // a clean streak of 3+
  h = L.headline(S(), S({ discipline: 70 }), { current: 4 }, null);
  assert.match(h.text, /4 clean trades in a row/);
  // net better than the previous period
  h = L.headline(S({ net: -100 }), S({ net: -900 }), none, null);
  assert.match(h.text, /Better than the previous period by \u20B9800/);
  // nothing flagged
  h = L.headline(S({ flagged: 0, net: -100 }), S({ net: 300 }), none, null);
  assert.match(h.text, /followed your rules/);
  // otherwise: focus on the most costly pattern, with its cost
  h = L.headline(S(), S({ net: 200 }), none, { label: 'Quick scalps (<2 min)', net: -640, count: 4 });
  assert.deepEqual([h.tone, /Quick scalps/.test(h.text), /\u2212\u20B9640/.test(h.text)], ['focus', true, true]);
  // labels are used verbatim: a ticker symbol keeps its capitals
  h = L.headline(S(), S({ net: 200 }), none, { label: 'TCS trades', net: -300, count: 2 });
  assert.match(h.text, /: TCS trades \u2014 2 trades/);
  // a profitable "pattern" is never presented as the problem
  h = L.headline(S(), S({ net: 200 }), none, { label: 'Short trades', net: 90, count: 3 });
  assert.equal(h.tone, 'neutral');
});
