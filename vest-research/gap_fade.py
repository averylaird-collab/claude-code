"""Gap trading on Vest's zero-fee perps, using the recorded book (real fill prices).

gap = book mid vs Vest's own index (bp). Two entry ideas:
  FADE : gap is far from its recent average -> bet it snaps back (buy when Vest is cheap vs index).
  CHASE: the index just moved and the book hasn't yet -> trade in the index's direction.
Fills: buy at ask, sell at bid. Account: $10 / $500, floor $490 valued at book mid.
Exit: close at the touch once realized profit >= take, or when the signal is gone, or after max_hold.
After every profitable close: Claim Profit (x0.95) -> equity back to $500. Fees = 0 (these markets)."""
import json, math, sys
from collections import deque

rows = [json.loads(l) for l in open(sys.argv[1])]
START, FLOOR, SPLIT, COST = 500.0, 490.0, 0.95, 10.0
SYMS = [s for s in rows[0] if s != "t"]


def series(s):
    out = []
    for r in rows:
        q = r.get(s)
        if q and "bid" in q and q["index"] > 0:
            out.append((r["t"], q["bid"], q["ask"], q["index"], q["mark"]))
    return out


def stats(s, x):
    mid = [(b + a) / 2 for _, b, a, _, _ in x]
    idx = [i for *_, i, _ in x]
    gap = [(m / i - 1) * 1e4 for m, i in zip(mid, idx)]
    spr = [(a - b) / ((a + b) / 2) * 1e4 for _, b, a, _, _ in x]
    n = len(x)
    def corr(a, b):
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        sa = math.sqrt(sum((v - ma) ** 2 for v in a)); sb = math.sqrt(sum((v - mb) ** 2 for v in b))
        return sum((u - ma) * (v - mb) for u, v in zip(a, b)) / (sa * sb) if sa and sb else float("nan")
    W = 60
    dev = []; fut = []
    for j in range(W, n - 10):
        m = sum(gap[j - W:j]) / W
        dev.append(gap[j] - m); fut.append(gap[j + 10] - gap[j])
    ri = [idx[k + 1] / idx[k] - 1 for k in range(n - 1)]
    rm = [mid[k + 1] / mid[k] - 1 for k in range(n - 1)]
    lead = [corr(ri[: n - 1 - L], rm[L:]) for L in range(4)]
    print(f"{s:14s} n={n:5d} index distinct {len(set(idx)):5d} | spread {sum(spr)/n:5.2f}bp | gap mean {sum(gap)/n:+6.1f} "
          f"min {min(gap):+6.1f} max {max(gap):+6.1f} | revert corr {corr(dev, fut):+.2f} | "
          f"index->book lead corr lag0..3: " + " ".join(f"{v:+.2f}" for v in lead))


def sim(x, mode, z, notional, take, max_hold=120, W=60):
    gapq = deque(maxlen=W)
    claimed = 0.0; accts = 1; pays = 0; trades = 0; pos = None; eq = START; prev_idx = None
    for k, (t, b, a, i, mk) in enumerate(x):
        mid = (a + b) / 2; g = (mid / i - 1) * 1e4
        if pos is not None:
            d, px, qty, k0 = pos
            if eq + d * (mid - px) * qty <= FLOOR:                 # account dead
                accts += 1; trades += 1; pos = None; eq = START
            else:
                out = b if d > 0 else a
                pnl = d * (out - px) * qty
                gone = (mode == "fade" and len(gapq) == W and d * (g - sum(gapq) / W) >= 0)
                if pnl >= take or (gone and pnl > 0) or k - k0 >= max_hold:
                    trades += 1; pos = None; eq += pnl
                    if eq > START:
                        claimed += (eq - START) * SPLIT; pays += 1; eq = START
        if pos is None and len(gapq) == W:
            sig = 0
            if mode == "fade":
                dv = g - sum(gapq) / W
                sig = -1 if dv > z else (1 if dv < -z else 0)
            elif mode == "chase" and prev_idx:
                mv = (i / prev_idx - 1) * 1e4 - (mid / prev_mid - 1) * 1e4   # index moved more than the book
                sig = 1 if mv > z else (-1 if mv < -z else 0)
            if sig:
                px = a if sig > 0 else b
                pos = (sig, px, notional / px, k)
        gapq.append(g); prev_idx = i; prev_mid = mid
    hrs = (x[-1][0] - x[0][0]) / 3600
    return dict(net=claimed - accts * COST, accts=accts, pays=pays, trades=trades, hrs=hrs, claimed=claimed)


if __name__ == "__main__":
    print(f"{len(rows)} snapshots over {(rows[-1]['t']-rows[0]['t'])/60:.1f} min\n")
    data = {s: series(s) for s in SYMS}
    for s in SYMS:
        if len(data[s]) > 200:
            stats(s, data[s])
    print()
    for s in SYMS:
        x = data[s]
        if len(x) < 200:
            continue
        best = []
        for mode, zs in (("fade", (1, 2, 4, 8)), ("chase", (0.5, 1, 2, 4))):
            for z in zs:
                for lev in (20, 50):
                    for take in (1.0, 2.5):
                        r = sim(x, mode, z, 500 * lev, take)
                        if r["trades"] >= 5:
                            best.append((r["net"], mode, z, lev, take, r))
        best.sort(key=lambda v: -v[0])
        for net, mode, z, lev, take, r in best[:3]:
            print(f"{s:14s} {mode:5s} z={z:<4} {lev}x take ${take}: {r['trades']:4d} trades {r['pays']:4d} payouts "
                  f"{r['accts']:3d} accts net ${net:+8.2f} = ${net/r['hrs']:+7.1f}/hr")
        print()
