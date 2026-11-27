"""Time-based breakout backtest across range lengths from 10 minutes to 1 week.

Rule (fixed before looking at any results, same everywhere):
  1. Range = high/low of the first W of the session (or the first k days of the week, or the prior week).
  2. Entry: the first bar that CLOSES outside the range, at that bar's close, in the breakout direction.
     One trade per session. No entries on the session's last bar.
  3. Stop: 'opp' = other side of the range, or 'mid' = range midpoint. If a bar opens past the stop,
     the exit is at that open (gap), otherwise at the stop price.
  4. Exit at the session's last close (end of day for intraday ranges, Friday close for weekly ones).
  5. Cost: round trip in bp, charged on every trade (futures 1bp, crypto 2bp = Vest taker both sides).

Data:
  crypto  Binance USDT-M perps, 5m bars, 2020-01 .. 2026-10 (BTC, ETH, SOL)
  futures Yahoo NQ/ES/RTY/YM: 5m bars (last 60 days), 60m bars (since 2024-07), daily bars (since 2000)
"""
import csv, glob, json, math, sys, datetime as D, zoneinfo
from collections import defaultdict

ROOT = sys.argv[1]
NY = zoneinfo.ZoneInfo("America/New_York")
UTC = D.UTC


# ---------------- loading ----------------
def binance(sym):
    out = []
    for f in sorted(glob.glob(f"{ROOT}/bin/{sym}-5m-*.csv")):
        for r in csv.reader(open(f)):
            if r[0] == "open_time":
                continue
            t = int(r[0]); t = t // 1000000 if t > 10**14 else t // 1000
            out.append((t, float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    out.sort()
    return out


def yahoo(sym, iv):
    r = json.load(open(f"{ROOT}/yh/{sym}_{iv}.json"))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    return [(t, o, h, l, c) for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])
            if None not in (o, h, l, c)]


# ---------------- sessions ----------------
def sessions_clock(bars, tz, start_hm, end_hm, weekdays_only=True):
    """Group bars whose start time (in tz) is in [start, end) into one session per calendar day."""
    out = defaultdict(list)
    s0 = start_hm[0] * 60 + start_hm[1]; e0 = end_hm[0] * 60 + end_hm[1]
    for b in bars:
        d = D.datetime.fromtimestamp(b[0], tz)
        if weekdays_only and d.weekday() >= 5:
            continue
        m = d.hour * 60 + d.minute
        if s0 <= m < e0:
            out[d.date()].append((m - s0,) + b)          # minutes since session start, t, o, h, l, c
    return [(day, v) for day, v in sorted(out.items())]


def daily_from(bars, tz):
    """Aggregate intraday bars into calendar-day OHLC in tz."""
    out = {}
    for t, o, h, l, c in bars:
        d = D.datetime.fromtimestamp(t, tz).date()
        if d not in out:
            out[d] = [o, h, l, c]
        else:
            x = out[d]; x[1] = max(x[1], h); x[2] = min(x[2], l); x[3] = c
    return [(d, *v) for d, v in sorted(out.items())]


# ---------------- core trade logic ----------------
def run_trade(hi, lo, path, stop_mode, cost):
    """path: list of (o, h, l, c) bars after the range. Returns (bp, direction) or None."""
    mid = (hi + lo) / 2
    for k in range(len(path) - 1):
        c = path[k][3]
        if c > hi or c < lo:
            d = 1 if c > hi else -1
            entry = c
            stop = mid if stop_mode == "mid" else (lo if d > 0 else hi)
            ex = path[-1][3]
            for o, h, l, cc in path[k + 1:]:
                if d > 0 and l <= stop:
                    ex = min(o, stop); break
                if d < 0 and h >= stop:
                    ex = max(o, stop); break
            return d * (ex / entry - 1) * 1e4 - cost, d
    return None


def intraday(sess, W, stop_mode, cost):
    out = []
    for day, bars in sess:
        rng = [b for b in bars if b[0] < W]
        rest = [b[2:] for b in bars if b[0] >= W]
        if not rng or len(rest) < 2 or rng[0][0] != 0:
            continue
        hi = max(b[3] for b in rng); lo = min(b[4] for b in rng)
        r = run_trade(hi, lo, rest, stop_mode, cost)
        if r:
            out.append((day, *r))
    return out


def weekly(days, k, stop_mode, cost):
    """days: [(date, o, h, l, c)]. k = 1..4: range = first k trading days of the week, trade the rest of the week.
    k = 'prev': range = the whole previous week, trade this week."""
    weeks = defaultdict(list)
    for d, o, h, l, c in days:
        y, w, _ = d.isocalendar()
        weeks[(y, w)].append((d, o, h, l, c))
    keys = sorted(weeks); out = []
    for i, wk in enumerate(keys):
        bars = weeks[wk]
        if k == "prev":
            if i == 0 or len(weeks[keys[i - 1]]) < 3:
                continue
            prev = weeks[keys[i - 1]]
            hi = max(b[2] for b in prev); lo = min(b[3] for b in prev); path = bars
        else:
            if len(bars) < k + 2:
                continue
            hi = max(b[2] for b in bars[:k]); lo = min(b[3] for b in bars[:k]); path = bars[k:]
        r = run_trade(hi, lo, [b[1:] for b in path], stop_mode, cost)
        if r:
            out.append((bars[0][0], *r))
    return out


# ---------------- stats ----------------
def st(xs):
    n = len(xs)
    if n < 5:
        return n, float("nan"), float("nan"), float("nan")
    m = sum(xs) / n; sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) or 1e-9
    return n, m, m / (sd / math.sqrt(n)), sum(x > 0 for x in xs) / n


RESULTS = []


def report(market, label, trades, split):
    if len(trades) < 10:
        return
    all_ = [r for _, r, _ in trades]
    n, m, t, w = st(all_)
    _, mi, ti, _ = st([r for d, r, _ in trades if d < split])
    _, mo, to, _ = st([r for d, r, _ in trades if d >= split])
    _, ml, tl, _ = st([r for _, r, d in trades if d > 0])
    _, ms, ts, _ = st([r for _, r, d in trades if d < 0])
    RESULTS.append(dict(market=market, label=label, n=n, avg=m, t=t, win=w, t_in=ti, t_out=to, avg_in=mi, avg_out=mo,
                        avg_long=ml, avg_short=ms, t_long=tl, t_short=ts))
    print(f"  {market:16s} {label:22s} n {n:5d} | avg {m:+7.2f}bp t {t:+5.2f} win {w:4.0%} | "
          f"first half t {ti:+5.2f}  second half t {to:+5.2f} | long {ml:+7.2f}bp  short {ms:+7.2f}bp", flush=True)


INTRA_W = [10, 15, 30, 40, 45, 60, 120, 180, 240, 300]
WEEK_K = [1, 2, 3, 4, "prev"]
WEEK_NAME = {1: "1 day (Mon range)", 2: "2 days (Mon-Tue)", 3: "3 days (Mon-Wed)", 4: "4 days (Mon-Thu)", "prev": "1 week (prior week)"}


def wname(W):
    return f"{W} min" if W < 60 else f"{W // 60} hour" + ("s" if W > 60 else "")


if __name__ == "__main__":
    CRYPTO_SPLIT = D.date(2024, 1, 1)
    for stop_mode in ("opp", "mid"):
        print(f"\n################ STOP = {'other side of range' if stop_mode == 'opp' else 'range midpoint'} ################")

        print("\n=== CRYPTO perps, range from the 9:30 ET US open, exit 16:00 ET (weekdays), cost 2bp ===")
        cry = {s: binance(s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
        us_sess = {s: sessions_clock(b, NY, (9, 30), (16, 0)) for s, b in cry.items()}
        utc_sess = {s: sessions_clock(b, UTC, (0, 0), (24, 0), weekdays_only=False) for s, b in cry.items()}
        for W in INTRA_W:
            pool = []
            for s in cry:
                tr = intraday(us_sess[s], W, stop_mode, 2.0); pool += tr
                report(s[:3] + " US-open", wname(W) + f" [{stop_mode}]", tr, CRYPTO_SPLIT)
            report("CRYPTO US pooled", wname(W) + f" [{stop_mode}]", pool, CRYPTO_SPLIT)

        print("\n=== CRYPTO perps, range from 00:00 UTC, exit 24:00 UTC (all days), cost 2bp ===")
        for W in INTRA_W:
            pool = []
            for s in cry:
                tr = intraday(utc_sess[s], W, stop_mode, 2.0); pool += tr
                report(s[:3] + " UTC-day", wname(W) + f" [{stop_mode}]", tr, CRYPTO_SPLIT)
            report("CRYPTO UTC pooled", wname(W) + f" [{stop_mode}]", pool, CRYPTO_SPLIT)

        print("\n=== CRYPTO perps, multi-day ranges on UTC daily bars, exit end of week, cost 2bp ===")
        for k in WEEK_K:
            pool = []
            for s, b in cry.items():
                days = daily_from(b, UTC)
                days = [x for x in days if x[0].weekday() < 5]          # Mon-Fri weeks, like futures
                tr = weekly(days, k, stop_mode, 2.0); pool += tr
                report(s[:3] + " weekly", WEEK_NAME[k] + f" [{stop_mode}]", tr, CRYPTO_SPLIT)
            report("CRYPTO wk pooled", WEEK_NAME[k] + f" [{stop_mode}]", pool, CRYPTO_SPLIT)

        FUT = ("NQ", "ES", "RTY", "YM")
        print("\n=== FUTURES 5m bars (last 60 days only, ~45 sessions: thin), 9:30-16:00 ET, cost 1bp ===")
        f5 = {s: sessions_clock(yahoo(s, "5m"), NY, (9, 30), (16, 0)) for s in FUT}
        for W in INTRA_W:
            pool = []
            for s in FUT:
                tr = intraday(f5[s], W, stop_mode, 1.0); pool += tr
            split = sorted(d for d, _, _ in pool)[len(pool) // 2] if pool else None
            report("FUT 5m pooled", wname(W) + f" [{stop_mode}]", pool, split)

        print("\n=== FUTURES 60m bars (since 2024-07), session 9:00-16:00 ET (hourly bars start on the hour), cost 1bp ===")
        f60 = {s: sessions_clock(yahoo(s, "60m"), NY, (9, 0), (16, 0)) for s in FUT}
        HSPLIT = D.date(2025, 9, 15)
        for W in (60, 120, 180, 240, 300):
            pool = []
            for s in FUT:
                tr = intraday(f60[s], W, stop_mode, 1.0); pool += tr
                report(s + " 60m", wname(W) + f" [{stop_mode}]", tr, HSPLIT)
            report("FUT 60m pooled", wname(W) + f" [{stop_mode}]", pool, HSPLIT)

        print("\n=== FUTURES daily bars (since 2000), multi-day ranges, exit Friday close, cost 1bp ===")
        FSPLIT = D.date(2013, 1, 1)
        for k in WEEK_K:
            pool = []
            for s in FUT:
                days = [(D.datetime.fromtimestamp(t, NY).date(), o, h, l, c) for t, o, h, l, c in yahoo(s, "1d")]
                tr = weekly(days, k, stop_mode, 1.0); pool += tr
                report(s + " daily", WEEK_NAME[k] + f" [{stop_mode}]", tr, FSPLIT)
            report("FUT wk pooled", WEEK_NAME[k] + f" [{stop_mode}]", pool, FSPLIT)

    json.dump(RESULTS, open(f"{ROOT}/results.json", "w"), default=str)
    good = [r for r in RESULTS if r["t"] > 2 and r["t_in"] > 1.5 and r["t_out"] > 1.5]
    print(f"\n{len(RESULTS)} tests run. Passing (t>2 overall AND t>1.5 in both halves): {len(good)}")
    for r in sorted(good, key=lambda r: -r["t"]):
        print(f"  {r['market']:16s} {r['label']:24s} n {r['n']:5d} avg {r['avg']:+.2f}bp t {r['t']:+.2f} "
              f"(halves {r['t_in']:+.2f} / {r['t_out']:+.2f}) long {r['avg_long']:+.2f} short {r['avg_short']:+.2f}")
