"""Latency check for lag_live_variants.py: decide at snapshot k, but fill at snapshot k+L (each ~1 s later),
for entries AND exits. L=0 is the original (instant fill). Liquidation at mark.
Usage: python3 lag_live_latency.py <scratchpad>"""
import bisect, sys
sys.argv = sys.argv[:2]
_V = __file__.replace("lag_live_latency.py", "lag_live_variants.py")
_src = open(_V).read().split("for title, kw in")[0].replace("__file__", repr(_V))
exec(_src)


def run3(vs, N, THR, H, notional, sig_src, L):
    x = series2(vs); rs = PAIRS[vs]; T = [v[0] for v in x]
    reg = []; claimed = 0.0; accts = 1; pays = 0; eq = START; pos = None; pend = None
    for k, (t, b, a, mk, ix) in enumerate(x):
        mid = (a + b) / 2
        if pend and k >= pend[0]:                                    # delayed order reaches the book
            kind = pend[1]
            if kind == "enter":
                d = pend[2]; px = a if d > 0 else b; pos = (d, px, notional / px, t, session(t)); pend = None
            else:
                d, px, qty, t0, sess = pos; out = b if d > 0 else a; pnl = d * (out - px) * qty
                if sess == "regular":
                    reg.append(d * (out / px - 1) * 1e4)
                pos = None; pend = None; eq += pnl
                if eq > START:
                    claimed += (eq - START) * SPLIT; pays += 1; eq = START
            continue
        if pos:
            d, px, qty, t0, sess = pos
            if eq + d * (mk - px) * qty <= FLOOR:                     # liquidation is instant (Vest does it)
                out = b if d > 0 else a
                if sess == "regular":
                    reg.append(d * (out / px - 1) * 1e4)
                accts += 1; eq = START; pos = None; pend = None; continue
            out = b if d > 0 else a; pnl = d * (out - px) * qty
            if pend is None and (pnl >= TP or t - t0 >= H * 60):
                pend = (k + L, "exit")
                if L == 0:
                    pend = None; reg.append(d * (out / px - 1) * 1e4) if sess == "regular" else None
                    pos = None; eq += pnl
                    if eq > START:
                        claimed += (eq - START) * SPLIT; pays += 1; eq = START
            continue
        if pend:
            continue
        j = bisect.bisect_right(T, t - N * 60) - 1
        if j < 0 or t - N * 60 - T[j] > 10:
            continue
        r1, r0 = (ix, x[j][4]) if sig_src == "index" else (real_at(rs, t), real_at(rs, T[j]))
        if not r1 or not r0:
            continue
        sig = ((r1 / r0) - (mid / ((x[j][1] + x[j][2]) / 2))) * 1e4
        if abs(sig) > THR:
            d = 1 if sig > 0 else -1
            if L == 0:
                px = a if d > 0 else b; pos = (d, px, notional / px, t, session(t))
            else:
                pend = (k + L, "enter", d)
    return reg, claimed, accts, pays


for src in ("index", "futures"):
    print(f"\n===== signal from {src}, liquidation at mark =====")
    for L in (0, 1, 2):
        for vs in PAIRS:
            line = f"  delay {L} snapshot(s) ~{L}s  {vs[:3]}:"
            for lev in (20, 50):
                reg, c, a, p = run3(vs, 1, 3, 2, 500 * lev, src, L); n, m, t, w = st(reg)
                line += f" | {lev}x {n:3d} tr win {w:4.0%} avg {m:+5.2f}bp t {t:+5.2f} payouts {p:3d} accts {a:3d} claimed ${c:7.2f} net ${c - a * COST:+7.2f}"
            print(line)
