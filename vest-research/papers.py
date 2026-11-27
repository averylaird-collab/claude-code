"""Backtests of published crypto findings on Binance USDT-M perps, 2020-01 .. 2026-10.
Every rule is fixed from the paper BEFORE looking at results. In-sample = 2020-2023, out-of-sample = 2024-2026.
Costs: 'cost' = round-trip cost in bp (taker both sides). Reported at 0, 2 (Vest-like) and 10 (Binance taker)."""
import csv, glob, math, sys, datetime as D
from collections import defaultdict

H = sys.argv[1]
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]
SPLIT = D.datetime(2024, 1, 1, tzinfo=D.UTC).timestamp()


def ts(x):
    x = int(x)
    return x // 1000000 if x > 10**14 else x // 1000


def bars(sym, kind="perp"):
    out = {}
    for f in sorted(glob.glob(f"{H}/{kind}/{sym}-30m-*.csv")):
        for r in csv.reader(open(f)):
            if r[0] == "open_time":
                continue
            out[ts(r[0])] = (float(r[1]), float(r[4]), float(r[5]))   # open, close, volume
    return out


def funding(sym):
    out = {}
    for f in sorted(glob.glob(f"{H}/funding/{sym}-fundingRate-*.csv")):
        for r in csv.reader(open(f)):
            if r[0] == "calc_time":
                continue
            out[ts(r[0]) // 60 * 60] = float(r[2])
    return out


def summarize(name, trades, cost_list=(0, 2, 10), per_year=None):
    """trades: list of (time, gross_return_bp)."""
    for part, sel in (("IN 2020-23", lambda t: t < SPLIT), ("OUT 2024-26", lambda t: t >= SPLIT)):
        xs = [r for t, r in trades if sel(t)]
        if len(xs) < 10:
            continue
        line = f"  {name:44s} {part}: {len(xs):5d} trades"
        for c in cost_list:
            ys = [x - c for x in xs]
            m = sum(ys) / len(ys); sd = math.sqrt(sum((y - m) ** 2 for y in ys) / (len(ys) - 1)) or 1e-9
            line += f" | cost {c:>2}bp: avg {m:+6.1f}bp t {m / (sd / math.sqrt(len(ys))):+5.1f} win {sum(y > 0 for y in ys) / len(ys):.0%}"
        print(line)


def daily_keys(b):
    days = sorted({t - t % 86400 for t in b})
    return days


# ---------- 1. Intraday momentum: first half-hour predicts last half-hour ----------
def intraday_momentum(sym, b):
    out_utc = []; out_us = []; out_rest = []
    for d in daily_keys(b):
        f0, l0 = b.get(d), b.get(d + 86400 - 1800)
        if f0 and l0:
            r1 = f0[1] / f0[0] - 1
            if r1 != 0:
                out_utc.append((d, (1 if r1 > 0 else -1) * (l0[1] / l0[0] - 1) * 1e4))
            # Gao et al. variant: rest of day (first 47 half-hours) predicts the last one
            rest = l0[0] / f0[0] - 1
            if rest != 0:
                out_rest.append((d, (1 if rest > 0 else -1) * (l0[1] / l0[0] - 1) * 1e4))
        # US-equity session version: 14:30-15:00 UTC predicts 20:30-21:00 UTC (weekdays)
        a, z = b.get(d + 14 * 3600 + 1800), b.get(d + 20 * 3600 + 1800)
        if a and z and D.datetime.fromtimestamp(d, D.UTC).weekday() < 5:
            r1 = a[1] / a[0] - 1
            if r1 != 0:
                out_us.append((d, (1 if r1 > 0 else -1) * (z[1] / z[0] - 1) * 1e4))
    return out_utc, out_rest, out_us


# ---------- 2/3. Funding: carry and contrarian ----------
def carry(sym, b, s, fr):
    """Long spot + short perp while trailing 3-day average funding > 0; collect funding, pay basis moves.
    One 'trade' = one 8h funding period held. Entry/exit costs charged when the position switches."""
    times = sorted(fr); out = []; on = False
    for k in range(9, len(times) - 1):
        t, t2 = times[k], times[k + 1]
        avg = sum(fr[times[j]] for j in range(k - 9, k)) / 9
        want = avg > 0
        pb0, pb1, sb0, sb1 = b.get(t), b.get(t2), s.get(t), s.get(t2)
        if not (pb0 and pb1 and sb0 and sb1):
            continue
        r = 0.0
        if want:
            spot_ret = sb1[0] / sb0[0] - 1; perp_ret = pb1[0] / pb0[0] - 1
            r = (spot_ret - perp_ret + fr[t2]) * 1e4     # short perp receives funding when rate > 0
        switch_cost = 2 * 10 if want != on else 0       # 2 legs x 10bp round-trip-half each way (taker)
        on = want
        out.append((t, r, switch_cost, want))
    return out


def funding_contrarian(sym, b, fr):
    """Extreme funding (top/bottom 5% of trailing 90 periods) -> fade it for the next 24h."""
    times = sorted(fr); out = []
    for k in range(90, len(times)):
        t = times[k]; win = sorted(fr[times[j]] for j in range(k - 90, k))
        hi, lo = win[int(0.95 * 89)], win[int(0.05 * 89)]
        f = fr[t]; d = -1 if f > hi else (1 if f < lo else 0)
        p0, p1 = b.get(t), b.get(t + 86400)
        if d and p0 and p1:
            out.append((t, d * (p1[0] / p0[0] - 1) * 1e4))
    return out


# ---------- 4. Time-series momentum (daily, 1-week lookback) ----------
def tsmom(sym, b, look=7, hold=1):
    days = [d for d in daily_keys(b) if d in b]
    px = {d: b[d][0] for d in days}; out = []; bh = []
    for d in days:
        p0, pl, p1 = px.get(d), px.get(d - look * 86400), px.get(d + hold * 86400)
        if p0 and pl and p1:
            sig = 1 if p0 > pl else -1
            out.append((d, sig * (p1 / p0 - 1) * 1e4)); bh.append((d, (p1 / p0 - 1) * 1e4))
    return out, bh


# ---------- 5. Seasonality learned in-sample, traded out-of-sample ----------
def seasonality(sym, b):
    hr = defaultdict(list)
    for t, (o, c, v) in b.items():
        if t < SPLIT:
            hr[(t % 86400) // 3600].append((c / o - 1) * 1e4)
    means = {h: sum(v) / len(v) for h, v in hr.items()}
    ranked = sorted(means, key=means.get)
    longs, shorts = set(ranked[-3:]), set(ranked[:3])
    out = []
    for t, (o, c, v) in b.items():
        h = (t % 86400) // 3600
        if h in longs or h in shorts:
            out.append((t, (1 if h in longs else -1) * (c / o - 1) * 1e4))
    dow = defaultdict(list)
    days = daily_keys(b)
    for d in days:
        if d < SPLIT and d in b and d + 86400 - 1800 in b:
            dow[D.datetime.fromtimestamp(d, D.UTC).weekday()].append((b[d + 86400 - 1800][1] / b[d][0] - 1) * 1e4)
    dmeans = {k: sum(v) / len(v) for k, v in dow.items()}
    best, worst = max(dmeans, key=dmeans.get), min(dmeans, key=dmeans.get)
    dout = []
    for d in days:
        wd = D.datetime.fromtimestamp(d, D.UTC).weekday()
        if wd in (best, worst) and d in b and d + 86400 - 1800 in b:
            dout.append((d, (1 if wd == best else -1) * (b[d + 86400 - 1800][1] / b[d][0] - 1) * 1e4))
    return out, sorted(longs), sorted(shorts), dout, best, worst


if __name__ == "__main__":
    pool = defaultdict(list)
    for sym in COINS:
        b = bars(sym); fr = funding(sym)
        if not b:
            continue
        print(f"\n######## {sym}: {len(b):,} half-hour bars, {len(fr):,} funding prints ########")
        u, rest, us = intraday_momentum(sym, b)
        summarize("1a intraday mom: 00:00-00:30 -> 23:30-24:00 UTC", u)
        summarize("1b intraday mom: rest-of-day -> last half-hour", rest)
        summarize("1c US-session mom: 14:30-15:00 -> 20:30-21:00 UTC", us)
        pool["1a"] += u; pool["1b"] += rest; pool["1c"] += us
        if glob.glob(f"{H}/spot/{sym}-30m-*.csv"):
            s = bars(sym, "spot"); c = carry(sym, b, s, fr)
            for part, sel in (("IN 2020-23", lambda t: t < SPLIT), ("OUT 2024-26", lambda t: t >= SPLIT)):
                xs = [x for x in c if sel(x[0])]
                if xs:
                    yrs = (xs[-1][0] - xs[0][0]) / (365 * 86400)
                    gross = sum(x[1] for x in xs); costs = sum(x[2] for x in xs)
                    on = sum(x[3] for x in xs) / len(xs)
                    print(f"  2 carry (long spot/short perp, on when 3d avg funding>0) {part}: in market {on:.0%}, "
                          f"gross {gross / yrs / 100:+.1f}%/yr, after 10bp taker legs {(gross - costs) / yrs / 100:+.1f}%/yr "
                          f"(1x notional, no leverage)")
        fc = funding_contrarian(sym, b, fr)
        summarize("3 funding extreme (5%/95% of 30d) -> fade 24h", fc)
        pool["3"] += fc
        tm, bh = tsmom(sym, b)
        summarize("4 TSMOM: sign of 7d return -> next 1d", tm)
        summarize("   (buy & hold, same days)", bh)
        pool["4"] += tm
        se, L, Sh, dw, best, worst = seasonality(sym, b)
        summarize(f"5a hours long {L} short {Sh} (picked on 2020-23)", se)
        summarize(f"5b weekday long {best} short {worst} (picked on 2020-23)", dw)
        pool["5a"] += se; pool["5b"] += dw
    print("\n######## ALL 6 COINS POOLED ########")
    names = {"1a": "1a intraday mom UTC", "1b": "1b rest-of-day -> last half-hour", "1c": "1c US-session mom",
             "3": "3 funding extreme fade", "4": "4 TSMOM 7d -> 1d", "5a": "5a hour-of-day (picked IS)", "5b": "5b weekday (picked IS)"}
    for k, v in pool.items():
        summarize(names[k], v)
