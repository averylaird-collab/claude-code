"""Record Vest ticker (mark/index/imbalance) + top of book for a list of symbols, ~1x/second."""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
B = "https://server-prod.hz.vestmarkets.com/v2"
H = {"xrestservermm": "restserver0", "User-Agent": "backtest-client"}
SYMS = sys.argv[3].split(",")
out = open(sys.argv[1], "a"); end = time.time() + float(sys.argv[2])
def get(p):
    with urllib.request.urlopen(urllib.request.Request(B + p, headers=H), timeout=5) as r:
        return json.loads(r.read())
ex = ThreadPoolExecutor(len(SYMS) + 1); n = err = 0
while time.time() < end:
    t0 = time.time()
    try:
        ft = ex.submit(get, "/ticker/latest?symbols=" + ",".join(SYMS))
        fb = {s: ex.submit(get, f"/depth?symbol={s}&limit=1") for s in SYMS}
        row = {"t": t0}
        for x in ft.result()["tickers"]:
            row[x["symbol"]] = dict(mark=float(x["markPrice"]), index=float(x["indexPrice"]), imb=float(x["imbalance"]))
        for s, f in fb.items():
            d = f.result()
            if d["bids"] and d["asks"]:
                row[s].update(bid=float(d["bids"][0][0]), ask=float(d["asks"][0][0]), bq=float(d["bids"][0][1]), aq=float(d["asks"][0][1]))
        out.write(json.dumps(row) + "\n"); out.flush(); n += 1
    except Exception:
        err += 1
    time.sleep(max(0, 0.8 - (time.time() - t0)))
print(f"rows {n} errors {err}")
