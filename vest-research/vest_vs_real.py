"""Compare Vest's historical bars with the real market (Yahoo) on normal trading days.
gap = Vest close / real price at the same moment - 1 (bp). Frozen stretches (Vest flat) are dropped."""
import json, math, sys, datetime as D

S = sys.argv[1]
PAIRS = {"NDX-USD-PERP": ["^NDX", "NQ=F"], "SPX-USD-PERP": ["^GSPC", "ES=F"], "RTY-USD-PERP": ["RTY=F"],
         "EUR-USD-PERP": ["EURUSD=X"], "AUD-USD-PERP": ["AUDUSD=X"], "GBP-USD-PERP": ["GBPUSD=X"], "GC-PERP": ["GC=F"]}


def yahoo(t, iv="1m"):
    r = json.load(open(f"{S}/yahoo/{t}_{iv}.json"))["chart"]["result"][0]
    ts = r["timestamp"]; c = r["indicators"]["quote"][0]["close"]
    return {a: b for a, b in zip(ts, c) if b}


def vest(s, iv):
    d = json.load(open(f"{S}/vesthist/{s}_{iv}.json"))["data"]
    step = 300 if iv == "5m" else 3600
    return sorted((x[0] // 1000 + step, x[1], x[2], x[3], x[4]) for x in d)   # (close time, o, h, l, c)


def corr(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def matched(s, t, iv):
    real = yahoo(t, "1m")
    out = []
    for ct, o, h, l, c in vest(s, iv):
        p = real.get(ct - 60)                     # Yahoo 1m bar starting 1 min before Vest's close = price at close
        if p and not (o == h == l == c):          # skip frozen bars
            out.append((ct, c, p, h, l))
    return out


if __name__ == "__main__":
    for iv, step in (("5m", 300), ("1h", 3600)):
        print(f"\n===== Vest {iv} bars vs real (Yahoo 1m) =====")
        for s, ts in PAIRS.items():
            for t in ts:
                m = matched(s, t, iv)
                if len(m) < 30:
                    print(f"{s:13s} vs {t:9s}: only {len(m)} live matched bars"); continue
                gap = [(c / p - 1) * 1e4 for _, c, p, _, _ in m]
                # consecutive bars only, for reversion stats
                dg = [(gap[k], gap[k + 1] - gap[k]) for k in range(len(m) - 1) if m[k + 1][0] - m[k][0] == step]
                mu = sum(gap) / len(gap); sd = math.sqrt(sum((g - mu) ** 2 for g in gap) / len(gap))
                ch = [b for _, b in dg]
                rv = corr([a - mu for a, _ in dg], ch) if len(dg) > 20 else float("nan")
                days = sorted(set(D.datetime.fromtimestamp(x[0], D.UTC).strftime("%m-%d") for x in m))
                print(f"{s:13s} vs {t:9s}: {len(m):4d} bars ({days[0]}..{days[-1]}, {len(days)} days) gap mean {mu:+7.1f}bp "
                      f"sd {sd:5.1f} | bar-to-bar gap change sd {math.sqrt(sum(c*c for c in ch)/len(ch)):5.1f}bp | "
                      f"gap now vs next change corr {rv:+.2f}")
