"""
Archive live book + trade data to disk.

Hyperliquid's public candle endpoint only retains ~5000 bars per interval
(~3.6 days at 1m), which is far too little to validate a scalping strategy.
This process builds the history the venue will not give you. Run it for two
weeks BEFORE trusting any backtest.

    python3 src/collector.py

Writes newline-delimited JSON to data/archive/<coin>_<date>.ndjson
"""
import asyncio, json, os, time, gzip, logging, sys
import websockets, yaml

WS = "wss://api.hyperliquid.xyz/ws"
ROOT = os.path.join(os.path.dirname(__file__), "..")
ARCHIVE = os.path.join(ROOT, "data", "archive")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")


class Archive:
    """One gzipped ndjson file per coin per UTC day, flushed every 5s."""
    def __init__(self):
        os.makedirs(ARCHIVE, exist_ok=True)
        self.files, self.buf, self.last_flush = {}, {}, time.time()

    def _fh(self, coin):
        key = (coin, time.strftime("%Y-%m-%d", time.gmtime()))
        if key not in self.files:
            for k in [k for k in self.files if k[0] == coin]:
                self.files.pop(k).close()          # new day -> roll the file
            path = os.path.join(ARCHIVE, f"{key[0]}_{key[1]}.ndjson.gz")
            self.files[key] = gzip.open(path, "at")
            log.info("archiving -> %s", path)
        return self.files[key]

    def write(self, coin, rec):
        self.buf.setdefault(coin, []).append(rec)
        if time.time() - self.last_flush > 5:
            for c, rows in self.buf.items():
                fh = self._fh(c)
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
                fh.flush()
            self.buf.clear()
            self.last_flush = time.time()


async def collect(coins):
    arch = Archive()
    counts = {c: 0 for c in coins}
    backoff = 1
    while True:
        try:
            async with websockets.connect(WS, ping_interval=20) as ws:
                for c in coins:
                    for ch in ("bbo", "trades"):
                        await ws.send(json.dumps({"method": "subscribe",
                            "subscription": {"type": ch, "coin": c}}))
                log.info("subscribed: %s", ", ".join(coins))
                backoff = 1
                last_log = time.time()
                async for raw in ws:
                    m = json.loads(raw)
                    ch, d = m.get("channel"), m.get("data")
                    if ch == "bbo" and d:
                        coin = d["coin"]
                        lv = d.get("bbo") or []
                        if len(lv) == 2 and lv[0] and lv[1]:
                            arch.write(coin, {"ts": d["time"], "k": "bbo",
                                              "b": lv[0]["px"], "bs": lv[0]["sz"],
                                              "a": lv[1]["px"], "as": lv[1]["sz"]})
                            counts[coin] = counts.get(coin, 0) + 1
                    elif ch == "trades" and d:
                        for t in d:
                            arch.write(t["coin"], {"ts": t["time"], "k": "trade",
                                                   "px": t["px"], "sz": t["sz"],
                                                   "side": t["side"]})
                    if time.time() - last_log > 60:
                        log.info("events/min: %s", dict(counts))
                        counts = {c: 0 for c in coins}
                        last_log = time.time()
        except Exception as e:
            log.warning("ws dropped (%s) -- reconnect in %ds", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
    coins = sys.argv[1:] or cfg["markets"]["candidates"]
    asyncio.run(collect(coins))
