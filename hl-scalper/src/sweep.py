import itertools, sys
from backtest import load, run

coins = ["BTC", "ETH", "SOL", "HYPE", "DOGE"]
grid = list(itertools.product([15, 30], [1.5, 2.0, 2.5], [10, 15, 20], [15, 25, 35], [5, 10]))

for coin in coins:
    bars = load(coin)
    rows = []
    for lb, z, tp, sl, mh in grid:
        r = run(bars, lookback=lb, entry_z=z, tp_bps=tp, sl_bps=sl, max_hold=mh)
        if r and r["n"] >= 20:
            rows.append(((lb, z, tp, sl, mh), r))
    rows.sort(key=lambda x: -x[1]["total"])
    print(f"\n===== {coin} ({len(bars)} bars) — top 5 of {len(rows)} configs w/ >=20 trades =====")
    print(f"{'lb':>3} {'z':>4} {'tp':>3} {'sl':>3} {'hold':>4} | {'n':>4} {'net$':>8} {'$/trade':>8} {'win%':>6} {'maxDD$':>8} {'$/day':>7} {'sharpe':>7}")
    for p, r in rows[:5]:
        print(f"{p[0]:>3} {p[1]:>4} {p[2]:>3} {p[3]:>3} {p[4]:>4} | {r['n']:>4} {r['total']:>8.2f} {r['per_trade']:>8.3f} {r['win_rate']:>6.1f} {r['max_dd']:>8.2f} {r['per_day']:>7.2f} {r['sharpe']:>7.2f}")
    if rows:
        pos = sum(1 for _, r in rows if r["total"] > 0)
        print(f"  --> {pos}/{len(rows)} configs profitable ({pos/len(rows)*100:.0f}%)   median net = ${sorted(r['total'] for _,r in rows)[len(rows)//2]:.2f}")
