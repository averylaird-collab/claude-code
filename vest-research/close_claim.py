"""Close-then-claim on recorded Vest quotes (90 min): open at the touch, value at book mid for the floor,
close at the touch (bid for a long, ask for a short) once realizable profit >= target, claim, reopen."""
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
SPLIT = 0.95
def run(s, d, notional, start, floor, cost, target, fee_bp=1.0):
    fee = notional * fee_bp / 1e4
    claimed = 0.0; accts = 0; pays = 0; pos = None
    for r in rows:
        q = r[s]; mid = (q["bid"] + q["ask"]) / 2
        if pos is None:
            px = q["ask"] if d > 0 else q["bid"]; pos = (px, notional / px); accts += 1 if pos and 'live' not in locals() or not live else 0
            live = True; eq0 = start - fee; continue
        px, qty = pos
        if eq0 + d * (mid - px) * qty <= floor:            # floor breached (valued at mid)
            pos = None; live = False; continue
        out = q["bid"] if d > 0 else q["ask"]
        realized = eq0 + d * (out - px) * qty - fee        # what you'd actually have after closing
        if realized - start >= target:
            claimed += (realized - start) * SPLIT; pays += 1
            pos = None                                     # reopen next snapshot on the same live account
    mins = (rows[-1]["t"] - rows[0]["t"]) / 60
    return claimed, accts, pays, mins
for label, start, floor, cost in (("$500 acct ($10)", 500, 490, 10), ("$10k acct ($400)", 10000, 9600, 400)):
    for s, lev in (("BTC", 25), ("ETH", 15)):
        for fee in (1.0, 0.0):
            for target in (0.5, 2.5):
                n = start * lev
                tc = ta = tp = 0
                for d in (1, -1):
                    c, a, p, mins = run(s, d, n, start, floor, cost, target * start / 500, fee)
                    tc += c; ta += a; tp += p
                net = tc - ta * cost
                print(f"{label:17s} {s} {lev}x (${n:,.0f}) fee {fee}bp take ${target*start/500:>5.1f}: "
                      f"{tp:4d} payouts, {ta:3d} accts, claimed ${tc:8.2f}, net ${net:+9.2f} = ${net/mins*60:+8.1f}/hr")
