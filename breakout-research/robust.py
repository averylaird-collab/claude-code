"""Stress tests for the one breakout that passed: crypto, range = first 30/40/45 min after the 9:30 ET US open.
 - per-day average across coins (coins trade on the same days, so pooled trades overstate t)
 - year by year
 - entry one bar late (next bar's open instead of the breakout bar's close)
 - higher costs
 - risk per trade, R multiples, drawdown"""
import math, sys, datetime as D
from collections import defaultdict
sys.argv = [sys.argv[0], sys.argv[1]]
exec(open(__file__.replace("robust.py", "breakout.py")).read().split('if __name__ == "__main__":')[0])


def trade_detail(sess, W, stop_mode, cost, late=False):
    out = []
    for day, bars in sess:
        rng = [b for b in bars if b[0] < W]; rest = [b[2:] for b in bars if b[0] >= W]
        if not rng or len(rest) < 3 or rng[0][0] != 0:
            continue
        hi = max(b[3] for b in rng); lo = min(b[4] for b in rng); mid = (hi + lo) / 2
        for k in range(len(rest) - 2):
            c = rest[k][3]
            if c > hi or c < lo:
                d = 1 if c > hi else -1
                entry = rest[k + 1][0] if late else c
                start = k + 1
                stop = mid if stop_mode == "mid" else (lo if d > 0 else hi)
                risk = abs(entry - stop) / entry * 1e4
                ex = rest[-1][3]
                for o, h, l, cc in rest[start:]:
                    if d > 0 and l <= stop:
                        ex = min(o, stop); break
                    if d < 0 and h >= stop:
                        ex = max(o, stop); break
                r = d * (ex / entry - 1) * 1e4 - cost
                out.append((day, r, d, risk))
                break
    return out


cry = {s: binance(s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
us = {s: sessions_clock(b, NY, (9, 30), (16, 0)) for s, b in cry.items()}

for W in (30, 40, 45):
    for sm in ("opp", "mid"):
        print(f"\n===== {W} min range, stop {sm} =====")
        per = {s: trade_detail(us[s], W, sm, 2.0) for s in cry}
        # per-day equal-weight portfolio across coins
        byday = defaultdict(list)
        for s, tr in per.items():
            for day, r, d, risk in tr:
                byday[day].append(r)
        daily = [(d, sum(v) / len(v)) for d, v in sorted(byday.items())]
        n, m, t, w = st([r for _, r in daily])
        print(f"  per-day basket (avg of coins that traded): {n} days, avg {m:+.2f}bp/day, t {t:+.2f}, win {w:.0%}")
        # year by year (basket)
        yr = defaultdict(list)
        for d, r in daily:
            yr[d.year].append(r)
        print("  by year: " + "  ".join(f"{y}: {sum(v)/len(v):+5.1f}bp (t {st(v)[2]:+.1f})" for y, v in sorted(yr.items())))
        # per coin, risk and R
        for s, tr in per.items():
            rs = [r for _, r, _, _ in tr]; risks = [k for *_, k in tr]
            R = [r / k for _, r, _, k in tr if k > 0]
            mr = sorted(risks)[len(risks) // 2]
            n, m, t, w = st(rs)
            print(f"  {s[:3]}: n {n}, avg {m:+.2f}bp t {t:+.2f} | median stop distance {mr:.0f}bp | avg R {sum(R)/len(R):+.3f}")
        # late entry and higher costs, basket
        for label, kw in (("entry 1 bar late (next open)", dict(late=True, cost=2.0)), ("cost 5bp", dict(cost=5.0)), ("cost 10bp", dict(cost=10.0))):
            bd = defaultdict(list)
            for s in cry:
                for day, r, d, risk in trade_detail(us[s], W, sm, kw["cost"], kw.get("late", False)):
                    bd[day].append(r)
            dl = [sum(v) / len(v) for _, v in sorted(bd.items())]
            n, m, t, w = st(dl)
            print(f"  {label:30s}: avg {m:+.2f}bp/day t {t:+.2f}")
        # drawdown of the basket in bp (1x notional, no compounding)
        eq = pk = dd = 0.0
        for _, r in daily:
            eq += r; pk = max(pk, eq); dd = max(dd, pk - eq)
        yrs = (daily[-1][0] - daily[0][0]).days / 365.25
        sd = math.sqrt(sum((r - eq / len(daily)) ** 2 for _, r in daily) / len(daily))
        print(f"  basket total {eq/100:+.1f}% over {yrs:.1f} yrs at 1x ({eq/100/yrs:+.1f}%/yr), max drawdown {dd/100:.1f}%, "
              f"Sharpe {(eq/len(daily))/sd*math.sqrt(252):.2f}")
