"""Pull 1m candles from Hyperliquid in chunks (API caps ~5000 bars/request)."""
import json, urllib.request, time, os, sys

URL = "https://api.hyperliquid.xyz/info"
DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def post(body, retries=4):
    for i in range(retries):
        try:
            req = urllib.request.Request(
                URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=40))
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def fetch(coin, days=30, interval="1m"):
    now = int(time.time() * 1000)
    step = 4000 * 60 * 1000          # 4000 one-minute bars per chunk
    start = now - days * 24 * 3600 * 1000
    out, t = {}, start
    while t < now:
        chunk = post({"type": "candleSnapshot",
                      "req": {"coin": coin, "interval": interval,
                              "startTime": t, "endTime": min(t + step, now)}})
        for c in chunk or []:
            out[c["t"]] = c
        t += step
        time.sleep(0.15)
    rows = [out[k] for k in sorted(out)]
    path = os.path.join(DATA, f"{coin}_{interval}.json")
    json.dump(rows, open(path, "w"))
    print(f"{coin:6s} {len(rows):6d} bars -> {path}")
    return rows


if __name__ == "__main__":
    coins = sys.argv[1:] or ["BTC", "ETH", "SOL", "HYPE", "DOGE"]
    for c in coins:
        fetch(c, days=30)
