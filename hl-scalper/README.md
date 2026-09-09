# hl-scalper

Research and execution tooling for scalping Hyperliquid perpetuals on a small
account. **Read [PLAN.md](PLAN.md) before running anything** — it contains the
measurement that determines whether this is worth doing at all.

## The short version

Directional scalping on Hyperliquid is negative-EV for a retail account.
Measured 1-minute signal edge is **1–2.6 bps**; a taker round trip costs
**9 bps**. A 540-configuration backtest across BTC, ETH, SOL, HYPE and DOGE
returned **zero profitable configurations**.

The only structure whose arithmetic can close is passive market making on
markets quoting wider than the 3 bps maker round trip. That is what
`paper_mm.py` and `live_mm.py` implement.

At $50, expected profit is **cents per day at best**. See PLAN.md §3.

## Install

```sh
pip install hyperliquid-python-sdk websockets pyyaml
cp .env.example .env      # then fill it in
```

`.env` holds an **API wallet** key (generate at https://app.hyperliquid.xyz/API).
An API wallet can trade but **cannot withdraw**. Never put a main-wallet seed
phrase or private key anywhere in this repo.

## Phases

Each phase has a gate in PLAN.md §4. Do not skip them — `live_mm.py` refuses
to run on mainnet until every gate is recorded in `gates.json`.

```sh
python3 src/check_account.py               # Phase 0 — account reachable
python3 src/collector.py                   # Phase 1 — archive 14 days of data
python3 src/paper_mm.py                    # Phase 2 — paper trade 14 days
python3 src/live_mm.py --minutes 60        # Phase 3 — testnet
                                           # Phase 4 — mainnet, gates required
```

## Research scripts

```sh
python3 src/fetch_data.py BTC ETH SOL      # pull candles (API keeps ~3.6 days at 1m)
python3 src/spread_scan.py                 # find markets quoting wider than fees
python3 src/diagnose.py                    # raw signal edge, fees excluded
python3 src/sweep.py                       # the 540-config backtest
```

## Stopping

```sh
touch .halt     # flattens and stops, checked before every quote cycle
```

`config.yaml` holds every risk limit. Daily loss limit, max drawdown, position
caps and the 2x leverage ceiling are enforced in `src/risk.py` before each
order — not left to discipline.
