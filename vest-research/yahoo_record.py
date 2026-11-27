"""Record Yahoo's latest futures quote (price + its own trade timestamp) every few seconds, as a backup
for when Yahoo's 1-minute bars are missing. Quotes are delayed ~10 min but carry the real trade time."""
import json, sys, time, urllib.request
SYMS = ["NQ%3DF", "ES%3DF", "RTY%3DF"]
out = open(sys.argv[1], "a"); end = time.time() + float(sys.argv[2]); last = {}
while time.time() < end:
    for s in SYMS:
        try:
            req = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1m&range=1d",
                                         headers={"User-Agent": "Mozilla/5.0"})
            m = json.loads(urllib.request.urlopen(req, timeout=10).read())["chart"]["result"][0]["meta"]
            key = (m.get("regularMarketTime"), m.get("regularMarketPrice"))
            if last.get(s) != key:
                last[s] = key
                out.write(json.dumps({"fetched": time.time(), "sym": s.replace("%3D", "="), "t": key[0], "p": key[1]}) + "\n"); out.flush()
        except Exception:
            pass
    time.sleep(4)
