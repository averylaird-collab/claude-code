"""'Claim ratchet' on recorded Vest quotes.
Open one position (long or short) in a $10 / $500 account at the touch (ask for long, bid for short),
pay the taker fee, and never close it. Every snapshot, value the account at a reference price
(book mid, mark, or index); whenever equity > $500, Claim Profit (x0.95) so equity goes back to $500.
When equity <= $490 the account is dead: buy a new one and reopen.
If the reference price were a pure random walk this would collect ~$9.50 per $10 account.
Anything above that is collected from short-lived noise in the price that the account is valued at."""
import json, sys

rows = [json.loads(l) for l in open(sys.argv[1])]
START, FLOOR, SPLIT, COST = 500.0, 490.0, 0.95, 10.0


def ref(r, s, how):
    q = r[s]
    return {"mid": (q["bid"] + q["ask"]) / 2, "mark": q["mark"], "index": q["index"]}[how]


def run(s, d, notional, how, fee_bp=1.0, every=1):
    claimed = 0.0; accounts = 0; payouts = 0; pos = None
    for k in range(0, len(rows), every):
        r = rows[k]
        if pos is None:
            px = r[s]["ask"] if d > 0 else r[s]["bid"]
            pos = (px, notional / px); accounts += 1
            base = START - notional * fee_bp / 1e4           # entry fee comes out of equity
            continue
        px, qty = pos
        eq = base + d * (ref(r, s, how) - px) * qty
        if eq <= FLOOR:
            pos = None
        elif eq > START:
            claimed += (eq - START) * SPLIT; payouts += 1
            base -= (eq - START)                             # equity reset to $500
    mins = (rows[-1]["t"] - rows[0]["t"]) / 60
    return claimed, accounts, payouts, mins


print(f"{len(rows)} snapshots, {(rows[-1]['t']-rows[0]['t'])/60:.1f} min\n")
for s in ("BTC", "ETH"):
    for how in ("mid", "mark", "index"):
        for notional in (5000, 10000, 25000):
            for fee in (1.0, 0.0):
                tot = acc = pay = 0
                for d in (1, -1):
                    c, a, p, mins = run(s, d, notional, how, fee)
                    tot += c; acc += a; pay += p
                net = tot - acc * COST
                print(f"{s} valued@{how:5s} ${notional:>6,} fee {fee}bp | claimed ${tot:7.2f} from {acc:3d} accts "
                      f"({tot/acc:5.2f}/acct, {pay:4d} payouts) net ${net:+8.2f} = ${net/mins*60:+8.1f}/hr")
        print()
