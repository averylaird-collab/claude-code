"""Variants of lag_live_test.py on the same recording, same fixed rule (N=1, THR=3, H=2, TP $2.50) + grid.
 A) liquidation valued at Vest MARK price instead of book mid (Vest liquidates at mark)
 B) signal from Vest's own INDEX price instead of real futures (free, real time)
Usage: python3 lag_live_variants.py <scratchpad>"""
import bisect, math, sys, datetime as D
sys.argv = sys.argv[:2]
exec(open(__file__.replace("lag_live_variants.py", "lag_live_test.py")).read().split('if __name__ == "__main__":')[0])


def series2(vs):
    return [(r["t"], r[vs]["bid"], r[vs]["ask"], r[vs]["mark"], r[vs]["index"]) for r in rows
            if vs in r and "bid" in r[vs] and r["t"] <= REAL_END]


def run2(vs, N, THR, H, notional, liq="mid", sig_src="futures"):
    x = series2(vs); rs = PAIRS[vs]; T = [v[0] for v in x]
    tr = []; claimed = 0.0; accts = 1; pays = 0; eq = START; pos = None
    for k, (t, b, a, mk, ix) in enumerate(x):
        mid = (a + b) / 2
        if pos:
            d, px, qty, t0, sess = pos
            val = mk if liq == "mark" else mid
            out = b if d > 0 else a; pnl = d * (out - px) * qty
            if eq + d * (val - px) * qty <= FLOOR:
                tr.append((sess, d * (out / px - 1) * 1e4)); accts += 1; eq = START; pos = None; continue
            if pnl >= TP or t - t0 >= H * 60:
                tr.append((sess, d * (out / px - 1) * 1e4)); pos = None; eq += pnl
                if eq > START:
                    claimed += (eq - START) * SPLIT; pays += 1; eq = START
            continue
        j = bisect.bisect_right(T, t - N * 60) - 1
        if j < 0 or t - N * 60 - T[j] > 10:
            continue
        if sig_src == "index":
            r1, r0 = ix, x[j][4]
        else:
            r1, r0 = real_at(rs, t), real_at(rs, T[j])
        if not r1 or not r0:
            continue
        m0 = (x[j][1] + x[j][2]) / 2
        sig = ((r1 / r0) - (mid / m0)) * 1e4
        if abs(sig) > THR:
            d = 1 if sig > 0 else -1; px = a if d > 0 else b
            pos = (d, px, notional / px, t, session(t))
    reg = [r for s, r in tr if s == "regular"]
    return reg, claimed, accts, pays


for title, kw in (("A) futures signal, liquidation at MARK", dict(liq="mark")),
                  ("B) Vest INDEX signal, liquidation at mid", dict(sig_src="index")),
                  ("B+A) Vest INDEX signal, liquidation at MARK", dict(sig_src="index", liq="mark"))):
    print(f"\n===== {title} =====")
    for vs in PAIRS:
        line = f"  {vs[:3]} fixed rule:"
        for lev in (20, 50):
            reg, c, a, p = run2(vs, 1, 3, 2, 500 * lev, **kw); n, m, t, w = st(reg)
            line += f" | {lev}x {n:3d} tr win {w:4.0%} avg {m:+5.2f}bp t {t:+5.2f} payouts {p:3d} accts {a:3d} net ${c - a * COST:+7.2f}"
        print(line)
    for vs in ("NDX-USD-PERP",):
        nets = []
        for N in (1, 3):
            for THR in (2, 5):
                for H in (1, 5):
                    for lev in (20, 50):
                        reg, c, a, p = run2(vs, N, THR, H, 500 * lev, **kw); nets.append(c - a * COST)
        print(f"  NDX grid (8 settings x 20x/50x): {sum(n > 0 for n in nets)}/16 positive, net $ range {min(nets):+.0f}..{max(nets):+.0f}")
