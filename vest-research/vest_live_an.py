"""Analyse recorded Vest quotes: how the tradeable book relates to Vest's index (Binance/OKX/Bybit median)."""
import json, math, sys


def corr(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


rows = [json.loads(l) for l in open(sys.argv[1])]
dt = (rows[-1]["t"] - rows[0]["t"]) / (len(rows) - 1)
print(f"{len(rows)} snapshots over {(rows[-1]['t']-rows[0]['t'])/60:.1f} min, one every {dt:.2f}s")
for s in ("BTC", "ETH"):
    mid = [(r[s]["bid"] + r[s]["ask"]) / 2 for r in rows]
    idx = [r[s]["index"] for r in rows]
    mark = [r[s]["mark"] for r in rows]
    spr = [(r[s]["ask"] - r[s]["bid"]) / ((r[s]["ask"] + r[s]["bid"]) / 2) * 1e4 for r in rows]
    prem = [(m / i - 1) * 1e4 for m, i in zip(mid, idx)]
    mprem = [(m / i - 1) * 1e4 for m, i in zip(mark, idx)]
    stale = [r["t"] - r[s]["book_ts"] for r in rows]
    imb = sorted(set(r[s]["imb"] for r in rows))
    print(f"\n== {s} ==")
    print(f"  book spread {sum(spr)/len(spr):.2f}bp | book age at fetch {sorted(stale)[len(stale)//2]:.2f}s median")
    print(f"  book mid vs index: mean {sum(prem)/len(prem):+.2f}bp  min {min(prem):+.2f}  max {max(prem):+.2f}")
    print(f"  mark     vs index: mean {sum(mprem)/len(mprem):+.2f}bp  min {min(mprem):+.2f}  max {max(mprem):+.2f}")
    print(f"  distinct imbalance values seen: {len(imb)}")
    lg = [(r[s]["mark"] / r[s]["ask"] - 1) * 1e4 for r in rows]   # buy at ask, valued at mark
    sh = [(1 - r[s]["mark"] / r[s]["bid"]) * 1e4 for r in rows]   # sell at bid, valued at mark
    print(f"  instant mark P&L of a new LONG {sum(lg)/len(lg):+.2f}bp (min {min(lg):+.2f}, max {max(lg):+.2f}); "
          f"new SHORT {sum(sh)/len(sh):+.2f}bp")
    # lead/lag: does the index move first and the Vest book follow?
    ri = [idx[k + 1] / idx[k] - 1 for k in range(len(idx) - 1)]
    rm = [mid[k + 1] / mid[k] - 1 for k in range(len(mid) - 1)]
    for L in range(0, 6):
        a = ri[: len(ri) - L]; b = rm[L:]
        print(f"  index move at t vs book move at t+{L} samples (~{L*dt:.1f}s): corr {corr(a, b):+.3f}")
    # mean reversion of the premium
    for H in (5, 15, 30, 60):
        k = max(1, round(H / dt))
        dev = [prem[j] - sum(prem[max(0, j - 30):j + 1]) / len(prem[max(0, j - 30):j + 1]) for j in range(len(prem) - k)]
        fut = [prem[j + k] - prem[j] for j in range(len(prem) - k)]
        if len(fut) < 20:
            continue
        print(f"  premium deviation now vs premium change over next ~{H}s: corr {corr(dev, fut):+.3f}  "
              f"(std of change {math.sqrt(sum(x*x for x in fut)/len(fut)):.2f}bp)")
