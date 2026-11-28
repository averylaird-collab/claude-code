"""Backtest of "many small payouts" strategies under Vest Capital $10 Instant rules.

Rules modelled (from public reviews; Vest's own terms may differ):
  - $10 buys a $500 simulated account; static floor at $490 (drawdown = fee), checked on equity.
  - No daily loss limit, no profit target, Claim Profit any time, no minimum, 95% split.
  - When an account breaches the floor it is dead; you lose only the $10 (firm eats any overshoot).
Execution on 1-minute bars (Binance USDT-M perps):
  - Entry at next bar open (taker fee). TP is a resting limit (maker fee).
  - Floor breach = position closed at the floor price, or at the bar open if price gapped past it.
  - If TP and floor are both inside one bar, the floor is assumed hit first (conservative).
  - After every TP: equity above $500 is claimed (x0.95), equity reset to $500 = one "payout".
"""
import csv, glob, math, random, sys
from collections import defaultdict

ACCT_COST, START, FLOOR, SPLIT = 10.0, 500.0, 490.0, 0.95


def load(sym, data_dir, iv="1m"):
    rows = []
    for f in sorted(glob.glob(f"{data_dir}/{sym}-{iv}-*.csv")):
        with open(f) as fh:
            r = csv.reader(fh); next(r)
            for x in r:
                ts = int(x[0]); ts = ts // 1000000 if ts > 10**14 else ts // 1000
                rows.append((ts, float(x[1]), float(x[2]), float(x[3]), float(x[4])))
    return rows


def side_rule(name, bars, i, rng, k):
    """Direction for a new trade decided at the close of bar i (-1 short, +1 long)."""
    if name == "random":
        return 1 if rng.random() < 0.5 else -1
    if name == "long":
        return 1
    if name == "short":
        return -1
    o, h, l, c = bars[i][1:]
    ret = c / bars[i - k][4] - 1 if i >= k else 0.0
    if name == "momo":   # follow the last k minutes
        return 1 if ret >= 0 else -1
    if name == "fade":   # fade the last k minutes
        return -1 if ret >= 0 else 1
    raise ValueError(name)


def scalper(bars, rule="random", tp_usd=2.5, notional=5000.0, taker_bp=1.0, maker_bp=0.0,
            k=5, seed=1, lo=0, hi=None):
    """One trading slot: always in a trade; buys a fresh $10 account whenever one dies."""
    rng = random.Random(seed)
    hi = hi or len(bars)
    taker, maker = taker_bp / 1e4, maker_bp / 1e4
    st = dict(payouts=0, claimed=0.0, accounts=1, trades=0, fees=0.0)
    eq, pos = START, None
    i = max(lo, k + 1)
    while i < hi - 1:
        if pos is None:
            d = side_rule(rule, bars, i, rng, k)
            px = bars[i + 1][1]                    # next bar open
            qty = notional / px
            fee_in = notional * taker
            eq -= fee_in; st["fees"] += fee_in
            # price where equity hits floor (incl. the taker fee to get out)
            room = eq - FLOOR - notional * taker
            if room <= 0:
                raise SystemExit("notional too big: fees alone breach the floor")
            fl = px - d * room / qty
            tp = px + d * tp_usd / qty
            pos = (d, px, qty, fl, tp)
            i += 1
            continue
        d, px, qty, fl, tp = pos
        t, o, h, l, c = bars[i]
        adverse = (l <= fl) if d > 0 else (h >= fl)
        gap = (o <= fl) if d > 0 else (o >= fl)
        hit_tp = (h >= tp) if d > 0 else (l <= tp)
        if gap or adverse:                          # account dead
            st["trades"] += 1; st["accounts"] += 1
            eq, pos = START, None
        elif hit_tp:
            pnl = d * (tp - px) * qty - notional * maker
            st["fees"] += notional * maker
            eq += pnl; st["trades"] += 1
            if eq > START:
                st["claimed"] += (eq - START) * SPLIT; st["payouts"] += 1
                eq = START
            pos = None
        i += 1
    days = (bars[hi - 1][0] - bars[lo][0]) / 86400
    st["days"] = days
    st["net"] = st["claimed"] - st["accounts"] * ACCT_COST
    return st


def straddle(bars, notional=5000.0, taker_bp=1.0, lo=0, hi=None):
    """Hedge pair: account A long, account B short, same size. When one hits its floor it dies;
    the winner is closed at that moment and its profit claimed; then reopen both (buy a new account)."""
    hi = hi or len(bars)
    taker = taker_bp / 1e4
    st = dict(payouts=0, claimed=0.0, accounts=2, trades=0, overshoot=0.0)
    i = lo
    while i < hi - 1:
        px = bars[i + 1][1]; qty = notional / px
        room = START - notional * taker - FLOOR - notional * taker
        up_fl, dn_fl = px + room / qty, px - room / qty   # short dies at up_fl, long dies at dn_fl
        i += 1
        while i < hi:
            t, o, h, l, c = bars[i]
            if o >= up_fl or h >= up_fl:
                exit_px = max(o, up_fl); win = (exit_px - px) * qty - 2 * notional * taker
                break
            if o <= dn_fl or l <= dn_fl:
                exit_px = min(o, dn_fl); win = (px - exit_px) * qty - 2 * notional * taker
                break
            i += 1
        else:
            break
        st["overshoot"] += abs(exit_px - (up_fl if exit_px >= px else dn_fl)) * qty
        st["trades"] += 1; st["accounts"] += 1
        st["claimed"] += max(win, 0) * SPLIT; st["payouts"] += 1
        i += 0                                      # reopen on the next bar's open
    st["days"] = (bars[hi - 1][0] - bars[lo][0]) / 86400
    st["net"] = st["claimed"] - st["accounts"] * ACCT_COST
    return st


def fmt(name, st):
    d = st["days"]
    avgp = st["claimed"] / st["payouts"] if st["payouts"] else 0
    return (f"{name:42s} payouts/day {st['payouts']/d:6.1f}  avg ${avgp:5.2f}  "
            f"accts burned/day {st['accounts']/d:5.1f}  net/day ${st['net']/d:+8.2f}  "
            f"per $10 acct ${st['net']/st['accounts']:+6.2f}")


if __name__ == "__main__":
    data_dir = sys.argv[1]
    for sym in ("BTCUSDT", "ETHUSDT"):
        bars = load(sym, data_dir)
        print(f"\n===== {sym}: {len(bars):,} 1-min bars =====")
        for fees in ((1.0, 0.0), (0.0, 0.0)):
            print(f"-- taker {fees[0]}bp / maker {fees[1]}bp --")
            for notional in (2500, 5000, 10000):
                for rule in ("random", "long", "short", "momo", "fade"):
                    st = scalper(bars, rule=rule, notional=notional, taker_bp=fees[0], maker_bp=fees[1])
                    print(fmt(f"scalp TP$2.5 {rule:6s} ${notional:,}", st))
                print(fmt(f"STRADDLE pair ${notional:,}", straddle(bars, notional, fees[0])))
