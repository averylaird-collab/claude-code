"""Record Vest's public WebSocket stream (no login) at full speed: book depth, ticker (mark/index) and trades.
Every message is written as one JSON line {"rt": receive time (unix s, float), "m": raw message}.
Reconnects automatically. Usage: python3 ws_record.py <out.jsonl> <seconds> [SYM:tick,SYM:tick,...]
Default markets: NDX-USD-PERP:0.25, SPX-USD-PERP:0.25, RTY-USD-PERP:0.1"""
import asyncio, json, ssl, sys, time
import websockets

URL = "wss://ws.hz.vestmarkets.com/ws?version=1.0&xwebsocketserver=restserver0"
OUT, DUR = sys.argv[1], float(sys.argv[2])
MKTS = [x.split(":") for x in (sys.argv[3] if len(sys.argv) > 3 else "NDX-USD-PERP:0.25,SPX-USD-PERP:0.25,RTY-USD-PERP:0.1").split(",")]
CTX = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
END = time.time() + DUR
stats = {"msgs": 0, "reconnects": 0}


async def session(f):
    async with websockets.connect(URL, ssl=CTX, proxy=True, open_timeout=15, ping_interval=20, max_size=2**22) as ws:
        rid = int(time.time() * 1000)
        for sym, tick in MKTS:
            for ch in (f"{sym}@depth_{tick}", f"{sym}@ticker", f"{sym}@trades_batch"):
                rid += 1
                await ws.send(json.dumps({"method": "SUBSCRIBE", "params": [ch], "id": rid}))
        while time.time() < END:
            try:
                m = await asyncio.wait_for(ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                await ws.send(json.dumps({"method": "PING", "params": [], "id": int(time.time() * 1000)}))
                continue
            f.write(json.dumps({"rt": time.time(), "m": m if isinstance(m, str) else m.decode()}) + "\n")
            stats["msgs"] += 1


async def main():
    with open(OUT, "a", buffering=1 << 16) as f:
        while time.time() < END:
            try:
                await session(f)
            except Exception as e:
                stats["reconnects"] += 1
                f.write(json.dumps({"rt": time.time(), "err": f"{type(e).__name__}: {str(e)[:200]}"}) + "\n")
                await asyncio.sleep(2)
    print(f"messages {stats['msgs']} reconnects {stats['reconnects']}")


asyncio.run(main())
