"""Does Vest's lag behind the real futures predict Vest's next move? (live, non-frozen bars only)
Signal at bar close: catch-up = real futures' move over the last L bars minus Vest's move over the same bars.
Trade Vest in the direction of the catch-up when |catch-up| > thr, hold H bars, exit at Vest's close.
Costs: half the live-measured spread on each side is charged as 'cost_bp' round trip."""
import json, math, sys
S = sys.argv[1]
exec(open(f"{S}/code/vest_vs_real.py").read().split("if __name__")[0].replace("S = sys.argv[1]", f"S = {S!r}"))

MINR = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
PAIRS = [("NDX-USD-PERP", "NQ=F"), ("SPX-USD-PERP", "ES=F"), ("RTY-USD-PERP", "RTY=F"), ("GC-PERP", "GC=F"),
         ("EUR-USD-PERP", "EURUSD=X"), ("AUD-USD-PERP", "AUDUSD=X"), ("GBP-USD-PERP", "GBPUSD=X")]


def real_at(real1m, real60, ts):
    return real1m.get(ts - 60) or real60.get(ts - 3600)    # 1m bar ending at ts, else the 60m bar ending at ts


def test(s, t, iv, step, L, thr, H, cost_bp):
    r1 = yahoo(t, "1m"); r60 = yahoo(t, "60m")
    rows = [(ct, c) for ct, o, h, l, c in vest(s, iv) if (h - l) / c * 1e4 >= MINR]
    byt = dict(rows); pnl = []
    for ct, c in rows:
        p0t = ct - L * step
        if p0t not in byt or (ct + H * step) not in byt:
            continue
        a, b = real_at(r1, r60, ct), real_at(r1, r60, p0t)
        if not a or not b:
            continue
        catch = ((a / b) - (c / byt[p0t])) * 1e4
        if abs(catch) > thr:
            d = 1 if catch > 0 else -1
            pnl.append(d * (byt[ct + H * step] / c - 1) * 1e4 - cost_bp)
    if len(pnl) < 8:
        return None
    m = sum(pnl) / len(pnl); sd = math.sqrt(sum((x - m) ** 2 for x in pnl) / (len(pnl) - 1))
    return len(pnl), m, m / (sd / math.sqrt(len(pnl))), sum(1 for x in pnl if x > 0) / len(pnl)


for iv, step, Ls, Hs in (("1h", 3600, (1, 2), (1, 2)), ("5m", 300, (1, 3, 6), (1, 3, 6))):
    print(f"\n===== Vest {iv} bars (live only) =====")
    for s, t in PAIRS:
        best = []
        for L in Ls:
            for H in Hs:
                for thr in (2, 5, 10, 20):
                    for cost in (0.0, 2.0):
                        r = test(s, t, iv, step, L, thr, H, cost)
                        if r:
                            best.append((r[2], L, H, thr, cost, r))
        if not best:
            print(f"  {s:13s}: not enough live matched bars"); continue
        best.sort(key=lambda v: -v[0])
        allz = [b[0] for b in best if b[4] == 0.0]
        print(f"  {s:13s} {len(best)} settings tried, median t (no cost) {sorted(allz)[len(allz)//2]:+.1f}")
        for tz, L, H, thr, cost, (n, m, tt, hit) in best[:3]:
            print(f"      lookback {L} hold {H} thr {thr:>2}bp cost {cost}bp: {n:4d} trades, avg {m:+6.2f}bp/trade, t {tt:+.1f}, win {hit:.0%}")

print("\n===== ONE FIXED RULE everywhere (no picking): lookback 1 bar, hold 1 bar, threshold 5bp, cost 1bp =====")
for iv, step in (("1h", 3600), ("5m", 300)):
    for s, t in PAIRS:
        r = test(s, t, iv, step, 1, 5, 1, 1.0)
        print(f"  {iv} {s:13s}: " + (f"{r[0]:4d} trades, avg {r[1]:+6.2f}bp/trade, t {r[2]:+.1f}, win {r[3]:.0%}" if r else "too few trades"))
