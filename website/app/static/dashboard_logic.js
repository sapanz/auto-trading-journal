/* Pure calculation layer for the home dashboard (no DOM, no Chart.js).
 *
 * Everything the page shows - ranges, summaries, streaks, milestones, what-if
 * exclusions, loss clusters, the calendar - is computed here from the list of
 * closed positions the server embeds, so switching a range or toggling a chip
 * never needs a round trip. Kept free of browser globals so it can be unit
 * tested in Node (website/tests/dashboard_logic.test.mjs).
 *
 * A trade record (see dashboard_data.py):
 *   { id, sym, prod, dir, qty, entry, exit, entryTs, exitTs, date, hold,
 *     gross, charges, net, roi, tags: [name], rating, note }
 * `date` is the exit date (YYYY-MM-DD); timestamps are naive ISO strings, so
 * hours are read from the string rather than through a Date (no time-zone
 * surprises between the server and the browser).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.DashLogic = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // Tags the matching engine applies that mean "look at this trade" - the
  // basis of the discipline score. "Big Win" is a good thing, so it isn't one.
  var ATTENTION_TAGS = ['Big Loss', 'Quick Scalp', 'Possible Revenge Trade'];
  var SYSTEM_TAGS = ATTENTION_TAGS.concat(['Big Win']);
  var MIN_WEEK_TRADES = 3; // a week needs this many trades to count towards the weekly trend

  /* ---------- dates (ISO strings, UTC arithmetic so DST never matters) ---------- */

  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function parseIso(iso) {
    var p = iso.split('-');
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
  }
  function fmtIso(d) { return d.getUTCFullYear() + '-' + pad2(d.getUTCMonth() + 1) + '-' + pad2(d.getUTCDate()); }
  function addDays(iso, n) { var d = parseIso(iso); d.setUTCDate(d.getUTCDate() + n); return fmtIso(d); }
  function daysBetween(a, b) { return Math.round((parseIso(b) - parseIso(a)) / 86400000); }
  function localIso(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
  /** 0 = Monday ... 6 = Sunday */
  function weekdayIndex(iso) { return (parseIso(iso).getUTCDay() + 6) % 7; }
  function weekStart(iso) { return addDays(iso, -weekdayIndex(iso)); }
  /** Indian financial year starts 1 April. */
  function fyStart(iso) {
    var p = iso.split('-');
    var y = +p[0], m = +p[1];
    return (m >= 4 ? y : y - 1) + '-04-01';
  }
  function fyLabel(iso) {
    var y = +fyStart(iso).slice(0, 4);
    return y + '-' + String((y + 1) % 100).padStart(2, '0');
  }
  /** "2026-11-20T09:21:10" -> 9 * 60 + 21 */
  function minutesOfDay(ts) { return +ts.slice(11, 13) * 60 + +ts.slice(14, 16); }

  function byExit(a, b) {
    if (a.exitTs < b.exitTs) return -1;
    if (a.exitTs > b.exitTs) return 1;
    return a.id - b.id;
  }
  function sortedAsc(trades) { return trades.slice().sort(byExit); }

  /* ---------- ranges ---------- */

  var RANGES = [
    { key: 'day', short: 'Latest day' },
    { key: '7d', short: '7 days' },
    { key: '30d', short: '30 days' },
    { key: 'fy', short: 'This FY' },
    { key: 'all', short: 'All time' },
  ];

  /**
   * The window for a range key plus the window just before it, used for the
   * "vs previous" comparisons. `today` is an ISO date (the browser's local
   * day). "Latest day" is the most recent trading day on or before today, so
   * it still says something on a weekend.
   */
  function rangeFor(key, trades, today) {
    var dates = Array.from(new Set(trades.map(function (t) { return t.date; }))).sort();
    var start, end, prev = null, label;
    if (key === 'day') {
      var upto = dates.filter(function (d) { return d <= today; });
      end = upto.length ? upto[upto.length - 1] : today;
      start = end;
      var before = dates.filter(function (d) { return d < start; });
      if (before.length) { var pd = before[before.length - 1]; prev = { start: pd, end: pd }; }
      label = end === today ? 'Today' : 'Latest trading day (' + end + ')';
    } else if (key === '7d' || key === '30d') {
      var len = key === '7d' ? 7 : 30;
      end = today; start = addDays(today, -(len - 1));
      prev = { start: addDays(start, -len), end: addDays(start, -1) };
      label = 'Last ' + len + ' days';
    } else if (key === 'fy') {
      end = today; start = fyStart(today);
      var span = daysBetween(start, end) + 1;
      prev = { start: addDays(start, -span), end: addDays(start, -1) };
      label = 'FY ' + fyLabel(today) + ' so far';
    } else {
      end = today; start = dates.length ? dates[0] : today;
      label = 'All time';
    }
    return { key: key, label: label, start: start, end: end, prev: prev };
  }

  function inWindow(trades, win) {
    if (!win) return [];
    return trades.filter(function (t) { return t.date >= win.start && t.date <= win.end; });
  }

  /* ---------- per-trade helpers ---------- */

  function isFlagged(t) {
    for (var i = 0; i < t.tags.length; i++) if (ATTENTION_TAGS.indexOf(t.tags[i]) !== -1) return true;
    return false;
  }
  function hasTag(t, name) { return t.tags.indexOf(name) !== -1; }
  function isReviewed(t) { return !!((t.note && t.note.trim()) || t.rating); }
  function strategyTags(t) { return t.tags.filter(function (n) { return SYSTEM_TAGS.indexOf(n) === -1; }); }

  /* ---------- summaries ---------- */

  function summarize(trades) {
    var s = {
      count: trades.length, wins: 0, losses: 0, net: 0, gross: 0, charges: 0,
      sumWin: 0, sumLoss: 0, flagged: 0, journaled: 0, best: null, worst: null,
    };
    trades.forEach(function (t) {
      s.net += t.net; s.gross += t.gross; s.charges += t.charges;
      if (t.net > 0) { s.wins++; s.sumWin += t.net; }
      else if (t.net < 0) { s.losses++; s.sumLoss += t.net; }
      if (isFlagged(t)) s.flagged++;
      if (isReviewed(t)) s.journaled++;
      if (!s.best || t.net > s.best.net) s.best = t;
      if (!s.worst || t.net < s.worst.net) s.worst = t;
    });
    var n = s.count;
    s.clean = n - s.flagged;
    s.winRate = n ? s.wins / n * 100 : null;
    s.avgWin = s.wins ? s.sumWin / s.wins : 0;
    s.avgLoss = s.losses ? s.sumLoss / s.losses : 0; // negative
    s.payoff = (s.wins && s.losses) ? s.avgWin / Math.abs(s.avgLoss) : null;
    s.profitFactor = s.sumLoss < 0 ? s.sumWin / Math.abs(s.sumLoss) : null;
    s.expectancy = n ? s.net / n : 0;
    s.discipline = n ? s.clean / n * 100 : null;
    s.journalPct = n ? s.journaled / n * 100 : null;
    return s;
  }

  function dailyRows(trades) {
    var map = {};
    trades.forEach(function (t) {
      var r = map[t.date] || (map[t.date] = { date: t.date, net: 0, gross: 0, charges: 0, count: 0, wins: 0 });
      r.net += t.net; r.gross += t.gross; r.charges += t.charges; r.count++;
      if (t.net > 0) r.wins++;
    });
    return Object.keys(map).sort().map(function (d) { return map[d]; });
  }

  /**
   * Cumulative net P&L by trading day within the supplied rows, starting from
   * zero. `fromLow` is how far above the lowest point so far you are now;
   * `belowPeak` how far under the highest. lowDate is null when the start
   * itself was the low (i.e. it only ever went up).
   */
  function equity(daily) {
    var run = 0, peak = 0, low = 0, lowDate = null, peakDate = null, maxDd = 0;
    var cum = [], dd = [];
    daily.forEach(function (r) {
      run += r.net;
      if (run > peak) { peak = run; peakDate = r.date; }
      if (run < low) { low = run; lowDate = r.date; }
      cum.push(run);
      dd.push(run - peak);
      if (run - peak < maxDd) maxDd = run - peak;
    });
    return {
      dates: daily.map(function (r) { return r.date; }), cum: cum, dd: dd,
      last: run, peak: peak, peakDate: peakDate, low: low, lowDate: lowDate,
      fromLow: run - low, belowPeak: run - peak, maxDrawdown: maxDd,
    };
  }

  /* ---------- streaks ---------- */

  /** Consecutive trades with no attention tag: the current run and the best ever. */
  function cleanStreaks(trades) {
    var cur = 0, best = 0, bestEnd = null;
    sortedAsc(trades).forEach(function (t) {
      if (isFlagged(t)) { cur = 0; return; }
      cur++;
      if (cur > best) { best = cur; bestEnd = t.date; }
    });
    return { current: cur, best: best, bestEnd: bestEnd };
  }

  /** Consecutive profitable trading days (net of that day's charges). */
  function greenDayStreaks(daily) {
    var cur = 0, best = 0;
    daily.forEach(function (r) {
      if (r.net > 0) { cur++; if (cur > best) best = cur; } else cur = 0;
    });
    return { current: cur, best: best };
  }

  /** Trades since the last "Big Loss" (all of them if there never was one). */
  function sinceLastBigLoss(trades) {
    var asc = sortedAsc(trades), run = 0, never = true;
    asc.forEach(function (t) {
      if (hasTag(t, 'Big Loss')) { run = 0; never = false; } else run++;
    });
    return { run: run, never: never };
  }

  /** Discipline % per calendar week (Mon-start), skipping thin weeks. */
  function weeklyDiscipline(trades) {
    var map = {};
    trades.forEach(function (t) {
      var w = weekStart(t.date);
      var r = map[w] || (map[w] = { weekStart: w, n: 0, clean: 0, net: 0 });
      r.n++; r.net += t.net;
      if (!isFlagged(t)) r.clean++;
    });
    return Object.keys(map).sort().map(function (w) {
      var r = map[w];
      return { weekStart: w, n: r.n, net: r.net, discipline: r.clean / r.n * 100 };
    }).filter(function (r) { return r.n >= MIN_WEEK_TRADES; });
  }

  /** Weeks in a row (counting back from the latest) whose discipline held or improved vs the week before. */
  function weeklyTrend(weeks) {
    var steps = [];
    for (var i = 1; i < weeks.length; i++) steps.push(weeks[i].discipline >= weeks[i - 1].discipline - 1e-9);
    var cur = 0, best = 0, run = 0;
    steps.forEach(function (ok) { if (ok) { run++; if (run > best) best = run; } else run = 0; });
    for (var j = steps.length - 1; j >= 0 && steps[j]; j--) cur++;
    return { current: cur, best: best };
  }

  /* ---------- milestones ---------- */

  function tiered(def, value, current) {
    var reached = def.tiers.filter(function (t) { return value >= t; }).length;
    var next = reached < def.tiers.length ? def.tiers[reached] : null;
    var floor = reached ? def.tiers[reached - 1] : 0;
    return {
      id: def.id, title: def.title, blurb: def.blurb, unit: def.unit, tiers: def.tiers,
      value: value, current: current, reached: reached, next: next,
      progress: next === null ? 1 : Math.max(0, Math.min(1, (value - floor) / (next - floor))),
      complete: next === null,
    };
  }

  /**
   * Habits you control, not outcomes you don't. Each has tiers; `value` is the
   * best ever (so a badge once earned stays earned) except "no big loss",
   * which is by nature a current run.
   */
  function milestones(trades) {
    var clean = cleanStreaks(trades);
    var green = greenDayStreaks(dailyRows(trades));
    var big = sinceLastBigLoss(trades);
    var trend = weeklyTrend(weeklyDiscipline(trades));
    var reviewed = trades.filter(isReviewed).length;
    return [
      tiered({ id: 'clean', title: 'Clean trades in a row', unit: 'trades', tiers: [5, 10, 20, 50],
        blurb: 'Consecutive trades with no Big Loss, Quick Scalp or revenge flag.' }, clean.best, clean.current),
      tiered({ id: 'journal', title: 'Trades reviewed', unit: 'trades', tiers: [10, 25, 50, 100],
        blurb: 'Trades where you wrote a note or gave a self-rating.' }, reviewed, reviewed),
      tiered({ id: 'green', title: 'Green days in a row', unit: 'days', tiers: [2, 3, 5, 8],
        blurb: 'Trading days that ended in profit after charges.' }, green.best, green.current),
      tiered({ id: 'nobig', title: 'Trades since your last Big Loss', unit: 'trades', tiers: [10, 20, 40, 80],
        blurb: 'Your current run of trades without a Big Loss flag.' }, big.run, big.run),
      tiered({ id: 'trend', title: 'Weeks holding or lifting discipline', unit: 'weeks', tiers: [2, 3, 4, 6],
        blurb: 'Weeks in a row whose clean-trade rate matched or beat the week before.' }, trend.best, trend.current),
    ];
  }

  /* ---------- what-if exclusions ---------- */

  function entryMinutes(t) { return minutesOfDay(t.entryTs); }

  /** A predicate for a pattern id such as "flag:Quick Scalp" or "sym:TCS". */
  function patternMatcher(id) {
    var i = id.indexOf(':');
    var kind = id.slice(0, i), arg = id.slice(i + 1);
    switch (kind) {
      case 'flag': return function (t) { return hasTag(t, arg); };
      case 'prod': return function (t) { return t.prod === arg; };
      case 'dir': return function (t) { return t.dir === arg; };
      case 'sym': return function (t) { return t.sym === arg; };
      case 'tag': return function (t) { return hasTag(t, arg); };
      case 'time':
        if (arg === 'open') return function (t) { var m = entryMinutes(t); return m >= 555 && m < 570; };   // 09:15-09:30
        if (arg === 'late') return function (t) { return entryMinutes(t) >= 870; };                        // 14:30 onwards
        return function () { return false; };
      default: return function () { return false; };
    }
  }

  /**
   * Candidate "what if I hadn't taken these?" chips for the trades in view:
   * behaviours first, then worst symbols and strategy tags. Sorted worst net
   * first so the most costly pattern leads; each carries what it cost (net)
   * across how many trades. Only patterns with at least two trades, so a
   * single unlucky trade isn't dressed up as a pattern.
   */
  function buildPatterns(trades, opts) {
    var max = (opts && opts.max) || 8;
    var defs = [];
    ATTENTION_TAGS.forEach(function (n) {
      defs.push({ id: 'flag:' + n, label: n === 'Quick Scalp' ? 'Quick scalps (<2 min)' : n === 'Possible Revenge Trade' ? 'Revenge-style re-entries' : 'Big losses' });
    });
    defs.push({ id: 'prod:MIS', label: 'Intraday (MIS) trades' });
    defs.push({ id: 'time:open', label: 'Entries in the first 15 min' });
    defs.push({ id: 'time:late', label: 'Entries after 2:30 pm' });
    defs.push({ id: 'dir:SHORT', label: 'Short trades' });

    var bySym = {}, byTag = {};
    trades.forEach(function (t) {
      bySym[t.sym] = (bySym[t.sym] || 0) + t.net;
      strategyTags(t).forEach(function (n) { byTag[n] = (byTag[n] || 0) + t.net; });
    });
    Object.keys(bySym).sort(function (a, b) { return bySym[a] - bySym[b]; }).slice(0, 3).forEach(function (s) {
      defs.push({ id: 'sym:' + s, label: s + ' trades' });
    });
    Object.keys(byTag).sort(function (a, b) { return byTag[a] - byTag[b]; }).slice(0, 2).forEach(function (n) {
      defs.push({ id: 'tag:' + n, label: '"' + n + '" setups' });
    });

    var out = [];
    defs.forEach(function (d) {
      var test = patternMatcher(d.id), c = 0, net = 0;
      trades.forEach(function (t) { if (test(t)) { c++; net += t.net; } });
      if (c >= 2) out.push({ id: d.id, label: d.label, count: c, net: net });
    });
    out.sort(function (a, b) { return a.net - b.net; });
    return out.slice(0, max);
  }

  /** Trades that remain once every selected pattern is set aside. */
  function without(trades, ids) {
    if (!ids || !ids.length) return trades;
    var tests = ids.map(patternMatcher);
    return trades.filter(function (t) { return !tests.some(function (f) { return f(t); }); });
  }

  /* ---------- where the losses cluster ---------- */

  function lossBuckets(trades, keyFn, labelFn) {
    var map = {};
    trades.forEach(function (t) {
      var k = keyFn(t);
      var b = map[k] || (map[k] = { key: k, label: labelFn(k), count: 0, lossCount: 0, lossSum: 0, net: 0 });
      b.count++; b.net += t.net;
      if (t.net < 0) { b.lossCount++; b.lossSum += t.net; }
    });
    return Object.keys(map).map(function (k) { return map[k]; });
  }

  var WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  function hourKey(t) { return t.entryTs.slice(11, 13); }
  function hourLabel(h) { return h + ':00'; }
  function weekdayKey(t) { return String(weekdayIndex(t.date)); }
  function weekdayLabel(k) { return WEEKDAYS[+k]; }

  function lossClusters(trades) {
    return {
      hour: lossBuckets(trades, hourKey, hourLabel).sort(function (a, b) { return a.key < b.key ? -1 : 1; }),
      weekday: lossBuckets(trades, weekdayKey, weekdayLabel).sort(function (a, b) { return +a.key - +b.key; }),
      product: lossBuckets(trades, function (t) { return t.prod; }, function (k) { return k; })
        .sort(function (a, b) { return a.lossSum - b.lossSum; }),
    };
  }

  /** The n biggest losses, each with a plain-English hint about its context. */
  function biggestLosses(trades, n) {
    return trades.filter(function (t) { return t.net < 0; })
      .sort(function (a, b) { return a.net - b.net; }).slice(0, n || 5)
      .map(function (t) {
        var bits = [t.prod === 'MIS' ? 'Intraday' : t.prod === 'CNC' ? 'Delivery' : t.prod];
        bits.push(t.dir === 'SHORT' ? 'short' : 'long');
        bits.push(t.hold < 1 ? 'held under a minute' : t.hold < 90 ? 'held ' + Math.round(t.hold) + ' min' : t.hold < 60 * 24 ? 'held ' + (t.hold / 60).toFixed(1) + ' h' : 'held ' + Math.round(t.hold / 1440) + ' d');
        bits.push('entered ' + t.entryTs.slice(11, 16));
        return { trade: t, hint: bits.join(' · ') };
      });
  }

  /* ---------- calendar ---------- */

  function level(net, maxAbs) {
    if (net === null) return 'none';
    if (net === 0) return 'zero';
    var b = Math.min(Math.floor(Math.min(Math.abs(net) / maxAbs, 1) * 4) + 1, 4);
    return (net > 0 ? 'win-' : 'loss-') + b;
  }

  /**
   * Mon-Fri grid for the last `weeks` calendar weeks ending at `endIso`.
   * Each column is a week; cells carry the day's net (null = no trades).
   */
  function calendarWeeks(daily, endIso, weeks) {
    var byDate = {};
    daily.forEach(function (r) { byDate[r.date] = r; });
    var maxAbs = 0;
    var firstMonday = addDays(weekStart(endIso), -7 * (weeks - 1));
    var cols = [];
    for (var w = 0; w < weeks; w++) {
      var ws = addDays(firstMonday, 7 * w), days = [];
      for (var d = 0; d < 5; d++) {
        var iso = addDays(ws, d), r = byDate[iso];
        if (r && Math.abs(r.net) > maxAbs) maxAbs = Math.abs(r.net);
        days.push({ date: iso, net: r ? r.net : null, count: r ? r.count : 0, future: iso > endIso });
      }
      cols.push({ weekStart: ws, days: days });
    }
    cols.forEach(function (c) {
      c.days.forEach(function (day) { day.level = day.future ? 'future' : level(day.net, maxAbs || 1); });
    });
    return cols;
  }

  /* ---------- since your last visit ---------- */

  /** What happened after the newest trade you'd already seen (a timestamp string). */
  function sinceVisit(trades, lastSeenTs) {
    if (!lastSeenTs) return null;
    var fresh = trades.filter(function (t) { return t.exitTs > lastSeenTs; });
    if (!fresh.length) return { count: 0 };
    var s = summarize(fresh);
    return { count: s.count, net: s.net, clean: s.clean, flagged: s.flagged, wins: s.wins };
  }

  /* ---------- headline ---------- */

  /**
   * One honest sentence for the top of the page. Progress first when there is
   * some (that is the part you control), otherwise the single costliest
   * pattern to work on - and never a profitable pattern dressed up as a
   * problem. `P` is the previous period's summary (or null), `clean` the
   * clean-streak object, `topPattern` the first of buildPatterns().
   */
  function headline(S, P, clean, topPattern) {
    if (!S.count) return { tone: 'neutral', text: 'No trades in this window \u2014 rest days count too.' };
    var hasPrev = P && P.count;
    if (hasPrev && S.discipline !== null && P.discipline !== null && S.discipline - P.discipline >= 3) {
      return { tone: 'good', text: 'Discipline is up ' + Math.round(S.discipline - P.discipline) + ' points on the previous period \u2014 that part is yours to control.' };
    }
    if (clean && clean.current >= 3) {
      return { tone: 'good', text: clean.current + ' clean trades in a row. Keep the streak going.' };
    }
    if (hasPrev && S.net > P.net) {
      return { tone: 'good', text: 'Better than the previous period by ' + inr(S.net - P.net) + '.' };
    }
    if (S.flagged === 0) return { tone: 'good', text: 'Every trade in this window followed your rules.' };
    if (topPattern && topPattern.net < 0) {
      return { tone: 'focus', text: 'Biggest lever right now: ' + topPattern.label + ' \u2014 ' +
        topPattern.count + ' trades, ' + inr(topPattern.net) + '.' };
    }
    return { tone: 'neutral', text: S.count + ' trades in this window, ' + pct(S.discipline) + ' of them clean.' };
  }

  /* ---------- formatting ---------- */

  var MINUS = '−';
  function inr(n, opts) {
    opts = opts || {};
    var d = opts.decimals == null ? 0 : opts.decimals;
    var abs = Math.abs(n);
    var body;
    try {
      body = new Intl.NumberFormat('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }).format(abs);
    } catch (e) { body = abs.toFixed(d); }
    var sign = n < 0 ? MINUS : (opts.plus && n > 0 ? '+' : '');
    return sign + '₹' + body;
  }
  function pct(n, decimals) {
    return n === null || n === undefined ? '—' : n.toFixed(decimals == null ? 0 : decimals) + '%';
  }

  return {
    ATTENTION_TAGS: ATTENTION_TAGS, SYSTEM_TAGS: SYSTEM_TAGS, RANGES: RANGES,
    addDays: addDays, daysBetween: daysBetween, localIso: localIso, weekdayIndex: weekdayIndex,
    weekStart: weekStart, fyStart: fyStart, fyLabel: fyLabel, minutesOfDay: minutesOfDay,
    sortedAsc: sortedAsc, rangeFor: rangeFor, inWindow: inWindow,
    isFlagged: isFlagged, isReviewed: isReviewed, strategyTags: strategyTags,
    summarize: summarize, dailyRows: dailyRows, equity: equity,
    cleanStreaks: cleanStreaks, greenDayStreaks: greenDayStreaks, sinceLastBigLoss: sinceLastBigLoss,
    weeklyDiscipline: weeklyDiscipline, weeklyTrend: weeklyTrend, milestones: milestones,
    patternMatcher: patternMatcher, buildPatterns: buildPatterns, without: without,
    lossClusters: lossClusters, biggestLosses: biggestLosses,
    calendarWeeks: calendarWeeks, sinceVisit: sinceVisit, headline: headline, inr: inr, pct: pct,
  };
}));
