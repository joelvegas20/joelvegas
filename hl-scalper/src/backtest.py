"""
Pessimistic 1m-bar backtester for a maker-entry mean-reversion scalper.

Modelling choices are deliberately unkind to the strategy:
  * A maker (ALO) entry only fills if the bar trades STRICTLY through the
    limit price -- a touch is not a fill.
  * When both take-profit and stop-loss sit inside the same bar's range, the
    stop is assumed to hit first.
  * Take-profit exits pay the maker fee, stops pay the taker fee.
  * A position still open after `max_hold` bars is closed at market (taker).
"""
import json, os, statistics as st

MAKER = 0.00015   # 1.5 bps
TAKER = 0.00045   # 4.5 bps
DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def load(coin):
    rows = json.load(open(os.path.join(DATA, f"{coin}_1m.json")))
    return [{"t": r["t"], "o": float(r["o"]), "h": float(r["h"]),
             "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])}
            for r in rows]


def run(bars, lookback=20, entry_z=2.0, tp_bps=12, sl_bps=18,
        max_hold=10, notional=250.0, vol_floor_bps=4.0):
    """Fade stretched moves: buy `entry_z` sigma below the mean, sell above."""
    trades, pos = [], None
    for i in range(lookback, len(bars) - 1):
        win = bars[i - lookback:i]
        closes = [b["c"] for b in win]
        mean = sum(closes) / len(closes)
        rets = [(closes[j] / closes[j - 1] - 1) for j in range(1, len(closes))]
        sigma = st.pstdev(rets) if len(rets) > 1 else 0
        bar = bars[i]

        if pos:
            held = i - pos["i"]
            hit_sl = bar["l"] <= pos["sl"] if pos["side"] == 1 else bar["h"] >= pos["sl"]
            hit_tp = bar["h"] >= pos["tp"] if pos["side"] == 1 else bar["l"] <= pos["tp"]
            exit_px = fee = None
            if hit_sl:                       # pessimistic: stop wins ties
                exit_px, fee = pos["sl"], TAKER
            elif hit_tp:
                exit_px, fee = pos["tp"], MAKER
            elif held >= max_hold:
                exit_px, fee = bar["c"], TAKER
            if exit_px is not None:
                gross = pos["side"] * (exit_px / pos["px"] - 1) * notional
                cost = notional * (MAKER + fee)
                trades.append({"pnl": gross - cost, "bars": held,
                               "won": gross - cost > 0})
                pos = None
            continue

        if sigma * 1e4 < vol_floor_bps:      # too quiet to pay for the fees
            continue
        dev = (bar["c"] - mean) / mean
        z = dev / sigma if sigma else 0
        side = 0
        if z <= -entry_z:
            side = 1
        elif z >= entry_z:
            side = -1
        if not side:
            continue

        # Post the maker order at the current close; require the NEXT bar to
        # trade strictly through it for a fill.
        limit, nxt = bar["c"], bars[i + 1]
        filled = nxt["l"] < limit if side == 1 else nxt["h"] > limit
        if not filled:
            continue
        pos = {"i": i + 1, "px": limit, "side": side,
               "tp": limit * (1 + side * tp_bps / 1e4),
               "sl": limit * (1 - side * sl_bps / 1e4)}

    if not trades:
        return None
    pnl = [t["pnl"] for t in trades]
    total = sum(pnl)
    wins = sum(t["won"] for t in trades)
    eq, peak, dd = 0, 0, 0
    for p in pnl:
        eq += p
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    days = (bars[-1]["t"] - bars[0]["t"]) / 86400000
    return {"n": len(trades), "total": total, "per_trade": total / len(trades),
            "win_rate": wins / len(trades) * 100, "max_dd": dd,
            "per_day": total / days, "trades_day": len(trades) / days,
            "sharpe": (st.mean(pnl) / st.pstdev(pnl) * (len(pnl) ** 0.5))
                      if len(pnl) > 1 and st.pstdev(pnl) else 0}
