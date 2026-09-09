"""Scan the whole perp universe: where is the spread wide enough to beat the 3bps maker round-trip?"""
import json, urllib.request, time

URL="https://api.hyperliquid.xyz/info"
def post(b):
    r=urllib.request.Request(URL,data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=30))

meta_ctx = post({"type":"metaAndAssetCtxs"})
universe = meta_ctx[0]["universe"]; ctxs = meta_ctx[1]

rows=[]
for a, c in zip(universe, ctxs):
    if a.get("isDelisted"): continue
    try:
        mark=float(c["markPx"]); oi=float(c["openInterest"])*mark
        vol=float(c.get("dayNtlVlm",0))
        rows.append((a["name"], mark, oi, vol, a["maxLeverage"], a["szDecimals"]))
    except: pass

rows.sort(key=lambda r:-r[3])
print(f"Universe: {len(rows)} live perps. Sampling books of top-60 by 24h volume...\n")
print(f"{'coin':<12}{'24h vol $':>14}{'OI $':>13}{'spread bps':>11}{'top-bid $':>11}{'lev':>5}  {'MM-viable?'}")
print("-"*76)
viable=[]
for name, mark, oi, vol, lev, szd in rows[:60]:
    try:
        b=post({"type":"l2Book","coin":name})
        bid=float(b["levels"][0][0]["px"]); ask=float(b["levels"][1][0]["px"])
        mid=(bid+ask)/2; sp=(ask-bid)/mid*1e4
        depth=float(b["levels"][0][0]["sz"])*bid
        ok = "YES" if sp > 3.0 and vol > 2e6 else ""
        if ok: viable.append((name, sp, vol, depth, lev))
        print(f"{name:<12}{vol:>14,.0f}{oi:>13,.0f}{sp:>11.2f}{depth:>11,.0f}{lev:>5}  {ok}")
    except Exception as e:
        pass
    time.sleep(0.12)

print(f"\n>>> {len(viable)} markets with spread > 3bps (maker round-trip) AND >$2M daily volume")
for v in sorted(viable, key=lambda x:-x[1]):
    print(f"    {v[0]:<10} spread={v[1]:6.2f}bps  vol=${v[2]:,.0f}  topbid=${v[3]:,.0f}  maxlev={v[4]}x")
