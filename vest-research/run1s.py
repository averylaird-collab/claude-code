import sys; sys.path.insert(0, sys.argv[2])
import vest_bt as V
for sym in ("BTCUSDT","ETHUSDT"):
    bars = V.load(sym, sys.argv[1], "1s")
    print(f"\n===== {sym}: {len(bars):,} 1-second bars (Oct 1-21) =====")
    for tk in (1.0, 0.0):
        print(f"-- taker {tk}bp, maker 0 --")
        for n in (2500, 5000, 10000):
            for rule in ("random","fade","momo"):
                print(V.fmt(f"scalp TP$2.5 {rule:6s} ${n:,}", V.scalper(bars, rule=rule, notional=n, taker_bp=tk, k=60)))
        for n in (5000, 10000, 25000):
            st = V.straddle(bars, n, tk)
            print(V.fmt(f"STRADDLE ${n:,}", st), f" overshoot/cycle ${st['overshoot']/st['trades']:.3f}")
