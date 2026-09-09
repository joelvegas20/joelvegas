"""Is there ANY gross edge before fees? And does the momentum sign work better?"""
import json, os, statistics as st
from backtest import load

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

def edge_test(bars, lookback=15, z_thresh=2.0, horizon=5):
    """After a z-sigma stretch, what does price do over the next `horizon` bars?
    Pure signal test: no fees, no fills, no stops. Returns bps."""
    rev, mom, base = [], [], []
    for i in range(lookback, len(bars) - horizon):
        closes = [b["c"] for b in bars[i-lookback:i]]
        mean = sum(closes)/len(closes)
        rets = [closes[j]/closes[j-1]-1 for j in range(1, len(closes))]
        sigma = st.pstdev(rets)
        if not sigma: continue
        z = ((bars[i]["c"] - mean)/mean)/sigma
        fwd = (bars[i+horizon]["c"]/bars[i]["c"] - 1) * 1e4   # bps
        base.append(abs(fwd))
        if z <= -z_thresh:  rev.append(fwd)     # stretched DOWN -> reversion = long
        elif z >= z_thresh: rev.append(-fwd)    # stretched UP   -> reversion = short
    return rev, base

print(f"{'coin':6s} {'z':>4} {'h':>3} | {'n':>5} {'mean_bps':>9} {'t-stat':>7} {'  verdict'}")
print("-"*62)
for coin in ["BTC","ETH","SOL","HYPE","DOGE"]:
    bars = load(coin)
    for z in (1.5, 2.0, 2.5):
        for h in (3, 5, 10):
            rev, base = edge_test(bars, z_thresh=z, horizon=h)
            if len(rev) < 30: continue
            m = st.mean(rev); s = st.pstdev(rev)
            t = m/s*(len(rev)**0.5) if s else 0
            # reversion edge must beat 3bps (maker r/t) to be tradeable
            verdict = "REVERSION" if t > 2 else ("MOMENTUM" if t < -2 else "no signal")
            print(f"{coin:6s} {z:>4} {h:>3} | {len(rev):>5} {m:>9.2f} {t:>7.2f}   {verdict}")
