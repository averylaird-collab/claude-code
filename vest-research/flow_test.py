"""Can an order-flow signal make the $10-account claim-every-win scalper profitable?
Signal: taker-buy imbalance over the last N bars, (2*taker_buy - vol) / vol. Trade in its direction
only when |imbalance| > thr. Train on the first part of the data, report the held-out part separately."""
import csv, glob, sys
from collections import deque

START, FLOOR, SPLIT, COST = 500.0, 490.0, 0.95, 10.0


def load(sym, d, iv):
    out = []
    for f in sorted(glob.glob(f"{d}/{sym}-{iv}-*.csv")):
        for x in csv.reader(open(f)):
            if x[0] == "open_time":
                continue
            ts = int(x[0]); ts = ts // 1000000 if ts > 10**14 else ts // 1000
            out.append((ts, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), float(x[9])))
    return out


def run(b, N, thr, notional, tp_usd=2.5, taker_bp=1.0, lo=0, hi=None):
    hi = hi or len(b)
    taker = taker_bp / 1e4
    vol = deque(); buy = deque(); sv = sb = 0.0
    claimed = 0.0; payouts = 0; accounts = 1; trades = 0
    pos = None; i = lo
    while i < hi - 1:
        t, o, h, l, c, v, tb = b[i]
        if pos is not None:
            d, px, qty, fl, tp = pos
            if (o <= fl or l <= fl) if d > 0 else (o >= fl or h >= fl):
                accounts += 1; trades += 1; pos = None
            elif (h >= tp) if d > 0 else (l <= tp):
                gain = tp_usd - notional * taker           # entry taker fee, TP is a maker limit
                if gain > 0:
                    claimed += gain * SPLIT; payouts += 1
                trades += 1; pos = None
        vol.append(v); buy.append(tb); sv += v; sb += tb
        if len(vol) > N:
            sv -= vol.popleft(); sb -= buy.popleft()
        if pos is None and len(vol) == N and sv > 0:
            imb = (2 * sb - sv) / sv
            if abs(imb) > thr:
                d = 1 if imb > 0 else -1
                px = b[i + 1][1]; qty = notional / px
                room = START - notional * taker - FLOOR - notional * taker
                pos = (d, px, qty, px - d * room / qty, px + d * tp_usd / qty)
        i += 1
    days = (b[hi - 1][0] - b[lo][0]) / 86400
    net = claimed - accounts * COST
    return dict(pay_day=payouts / days, acct_day=accounts / days, net_day=net / days,
                per_acct=net / accounts, trades=trades)


if __name__ == "__main__":
    d, iv = sys.argv[1], sys.argv[2]
    for sym in ("BTCUSDT", "ETHUSDT"):
        b = load(sym, d, iv)
        cut = int(len(b) * 0.65)
        print(f"\n== {sym} {iv}: train {cut:,} bars / test {len(b)-cut:,} bars ==")
        res = []
        for N in ((5, 15, 30, 60) if iv == "1s" else (1, 3, 5, 15)):
            for thr in (0.2, 0.4, 0.6, 0.8):
                for notional in (2500, 5000):
                    for tk in (1.0, 0.0):
                        r = run(b, N, thr, notional, taker_bp=tk, hi=cut)
                        if r["trades"] >= 100:
                            res.append(((N, thr, notional, tk), r))
        res.sort(key=lambda x: -x[1]["per_acct"])
        print("best 6 on TRAIN, then the same settings on held-out TEST:")
        for (N, thr, n, tk), r in res[:6]:
            te = run(b, N, thr, n, taker_bp=tk, lo=cut)
            print(f"  N={N:<3} thr={thr} ${n:,} taker={tk}bp | train ${r['per_acct']:+5.2f}/acct "
                  f"{r['pay_day']:5.1f} pay/d | TEST ${te['per_acct']:+5.2f}/acct {te['pay_day']:5.1f} pay/d "
                  f"{te['acct_day']:5.1f} acct/d net ${te['net_day']:+7.2f}/d ({te['trades']} trades)")
