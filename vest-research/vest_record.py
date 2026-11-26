"""Record Vest's live quotes ~4x/second: ticker (mark, index, imbalance) + top of book, for BTC and ETH."""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

B = "https://server-prod.hz.vestmarkets.com/v2"
H = {"xrestservermm": "restserver0", "User-Agent": "backtest-client"}
out = open(sys.argv[1], "a")
secs = float(sys.argv[2])


def get(path):
    req = urllib.request.Request(B + path, headers=H)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def snap():
    t0 = time.time()
    with ThreadPoolExecutor(3) as ex:
        ft = ex.submit(get, "/ticker/latest?symbols=BTC-PERP,ETH-PERP")
        fb = ex.submit(get, "/depth?symbol=BTC-PERP&limit=1")
        fe = ex.submit(get, "/depth?symbol=ETH-PERP&limit=1")
        tk, db, de = ft.result(), fb.result(), fe.result()
    row = {"t": (t0 + time.time()) / 2}
    for x in tk["tickers"]:
        s = x["symbol"][:3]
        row[s] = dict(mark=float(x["markPrice"]), index=float(x["indexPrice"]), imb=float(x["imbalance"]))
    for s, d in (("BTC", db), ("ETH", de)):
        row[s].update(bid=float(d["bids"][0][0]), ask=float(d["asks"][0][0]), book_ts=d["ts_ms"] / 1000)
    return row


end = time.time() + secs
n = err = 0
while time.time() < end:
    try:
        out.write(json.dumps(snap()) + "\n"); n += 1
    except Exception as e:
        err += 1
    out.flush()
    time.sleep(0.15)
print(f"rows {n} errors {err}")
