"""Live test of 'Vest lags the real futures' on Friday Nov 27 2026's recording.

Rule FIXED before looking at results:
  signal(t) = real futures move over the last N min  -  Vest book-mid move over the same N min   (bp)
  if |signal| > THR and flat: trade Vest in the signal's direction (buy at ask / sell at bid)
  exit: first of  (a) $2.50 profit available at the touch,  (b) H minutes,  (c) account floor hit
  Fixed rule: N = 1 min, THR = 3 bp, H = 2 min.  Grid: N {1,3} x THR {2,5} x H {1,5}.
Account: Vest $10 Instant. $500 balance, $490 floor valued at book mid, zero fees on these markets.
  After a profitable close: claim 95% of the profit, equity back to $500.  Floor hit: account lost, buy a new one.
Real prices: Yahoo quotes with their true trade timestamp (vest/fri_yahoo.jsonl), last quote at or before t.
  NOTE: in real life Yahoo is ~10 min delayed; this test assumes a real-time CME feed.
Usage: python3 lag_live_test.py <scratchpad>"""
import bisect, json, math, sys, datetime as D, zoneinfo

S = sys.argv[1]
NY = zoneinfo.ZoneInfo("America/New_York")
PAIRS = {"NDX-USD-PERP": "NQ=F", "SPX-USD-PERP": "ES=F", "RTY-USD-PERP": "RTY=F"}
START, FLOOR, SPLIT, TP, COST = 500.0, 490.0, 0.95, 2.50, 10.0

rows = [json.loads(l) for l in open(f"{S}/vest/fri.jsonl")]
yq = [json.loads(l) for l in open(f"{S}/vest/fri_yahoo.jsonl")]
real = {}
for s in set(PAIRS.values()):
    q = sorted((x["t"], x["p"]) for x in yq if x["sym"] == s)
    real[s] = ([a for a, _ in q], [b for _, b in q])
REAL_END = min(v[0][-1] for v in real.values())


def real_at(sym, t):
    ts, ps = real[sym]
    i = bisect.bisect_right(ts, t) - 1
    return ps[i] if i >= 0 and t - ts[i] < 60 else None     # must be fresh (<60s old)


def session(t):
    m = D.datetime.fromtimestamp(t, NY); hm = m.hour * 60 + m.minute
    return "overnight" if hm < 9 * 60 + 30 else "regular"


def series(vs):
    out = []
    for r in rows:
        q = r.get(vs)
        if q and "bid" in q and r["t"] <= REAL_END:
            out.append((r["t"], q["bid"], q["ask"]))
    return out


def run(vs, N, THR, H, notional):
    x = series(vs); rs = PAIRS[vs]; T = [a for a, _, _ in x]
    trades = []; claimed = 0.0; accts = 1; pays = 0; eq = START; pos = None
    for k, (t, b, a) in enumerate(x):
        mid = (a + b) / 2
        if pos:
            d, px, qty, t0, sess = pos
            if eq + d * (mid - px) * qty <= FLOOR:                       # floor hit at mid: account gone
                out = b if d > 0 else a
                trades.append((sess, d * (out / px - 1) * 1e4, d * (out - px) * qty))
                accts += 1; eq = START; pos = None; continue
            out = b if d > 0 else a; pnl = d * (out - px) * qty
            if pnl >= TP or t - t0 >= H * 60:
                trades.append((sess, d * (out / px - 1) * 1e4, pnl)); pos = None; eq += pnl
                if eq > START:
                    claimed += (eq - START) * SPLIT; pays += 1; eq = START
            continue
        j = bisect.bisect_right(T, t - N * 60) - 1
        if j < 0 or t - N * 60 - T[j] > 10:                               # need a Vest snapshot near t-N
            continue
        r1, r0 = real_at(rs, t), real_at(rs, T[j])
        if not r1 or not r0:
            continue
        m0 = (x[j][1] + x[j][2]) / 2
        sig = ((r1 / r0) - (mid / m0)) * 1e4
        if abs(sig) > THR:
            d = 1 if sig > 0 else -1; px = a if d > 0 else b
            pos = (d, px, notional / px, t, session(t))
    return trades, claimed, accts, pays


def st(xs):
    n = len(xs)
    if n < 3:
        return n, float("nan"), float("nan"), float("nan")
    m = sum(xs) / n; sd = math.sqrt(sum((v - m) ** 2 for v in xs) / (n - 1)) or 1e-9
    return n, m, m / (sd / math.sqrt(n)), sum(v > 0 for v in xs) / n


def show(label, vs, N, THR, H):
    for lev in (20, 50):
        tr, claimed, accts, pays = run(vs, N, THR, H, 500 * lev)
        for sess in ("overnight", "regular"):
            bp = [r for s, r, _ in tr if s == sess]
            n, m, t, w = st(bp)
            if n == 0:
                continue
            print(f"  {label:26s} {vs[:3]} {lev}x {sess:9s}: {n:4d} trades win {w:4.0%} avg {m:+6.2f}bp t {t:+5.2f}")
        print(f"  {'':26s} {vs[:3]} {lev}x whole day: payouts {pays:4d}  accounts used {accts:3d}  claimed ${claimed:7.2f}  "
              f"net ${claimed - accts * COST:+8.2f}")


if __name__ == "__main__":
    f = lambda t: D.datetime.fromtimestamp(t, NY).strftime("%H:%M")
    print(f"Vest snapshots {len(rows)} ({f(rows[0]['t'])}-{f(rows[-1]['t'])} ET, gap 02:29-09:33), real quotes to {f(REAL_END)} ET\n")
    print("===== FIXED RULE: N=1 min, THR=3bp, H=2 min, TP $2.50 =====")
    for vs in PAIRS:
        show("fixed", vs, 1, 3, 2)
    print("\n===== ROBUSTNESS GRID (20x only, all markets pooled by trade) =====")
    for N in (1, 3):
        for THR in (2, 5):
            for H in (1, 5):
                allbp = {"overnight": [], "regular": []}; net = 0.0; pays = accts = 0
                for vs in PAIRS:
                    tr, c, a, p = run(vs, N, THR, H, 10000)
                    for s, r, _ in tr:
                        allbp[s].append(r)
                    net += c - a * COST; pays += p; accts += a
                line = f"  N={N} THR={THR} H={H}:"
                for s in ("overnight", "regular"):
                    n, m, t, w = st(allbp[s])
                    line += f" | {s} {n:4d} tr avg {m:+6.2f}bp t {t:+5.2f} win {w:4.0%}"
                print(line + f" | payouts {pays} accts {accts} net ${net:+.2f}")
