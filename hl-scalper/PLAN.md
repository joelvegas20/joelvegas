# Hyperliquid Scalping — Operating Plan ($50 account)

## 1. The finding that shapes everything

Before designing a strategy I measured the venue. Three numbers decide the
whole problem:

| Quantity | Measured value |
|---|---|
| Taker fee, round trip | **9.0 bps** (4.5 in + 4.5 out) |
| Maker fee, round trip | **3.0 bps** (1.5 in + 1.5 out) |
| Predictive edge of a 1m signal on BTC/ETH/SOL/HYPE/DOGE | **1.0 – 2.6 bps** |

The edge is smaller than the cost of trading on it, by 2–9x. That is not a
tuning problem; it is arithmetic.

**Backtest, 540 configurations** (5 assets x 108 parameter sets, 1m bars,
maker entries, pessimistic fills):

| Asset | Configs w/ >=20 trades | Profitable | Best $/trade | Median net |
|---|---|---|---|---|
| BTC  | 108 | **0** | -$0.095 | -$17.08 |
| ETH  | 108 | **0** | -$0.163 | -$45.45 |
| SOL  | 108 | **0** | -$0.175 | -$75.39 |
| HYPE | 108 | **0** | -$0.133 | -$78.50 |
| DOGE | 108 | **0** | -$0.203 | -$100.13 |

Zero of 540. The median DOGE configuration loses **$100 in 3.6 days** — a $50
account, twice over.

A signal test with fees switched off explains why: fading a stretched move has
a *negative* expectancy (price continues rather than reverts, t-stat -2 to
-4.5), and the continuation is only 0.5–2.6 bps. Real, statistically
significant, and far too small to pay a 9 bps toll.

**Conclusion: taker/directional scalping on this venue is structurally
negative-EV for a retail account. No parameter set fixes it.**

## 2. The one structure whose arithmetic can close

If the edge cannot exceed the fee, stop paying the taker fee and start being
paid the spread. A passive quote earns the spread and costs 3 bps round trip,
so any market quoting **wider than 3 bps** is arithmetically capable of paying.

A scan of the live book (top 60 perps by volume) found 20 such markets:

| Market | Spread | 24h volume | Top-of-book |
|---|---|---|---|
| MEGA | 13.8 bps | $2.3M | $400 |
| RENDER | 9.1 bps | $2.1M | $400 |
| AERO | 8.6 bps | $6.3M | $958 |
| PENDLE | 6.2 bps | $3.8M | $401 |
| ETC | 6.2 bps | $3.8M | $400 |
| ATOM | 6.2 bps | $3.4M | $400 |
| DASH | 5.6 bps | $4.5M | $3,108 |
| WLD | 4.6 bps | $25.1M | $400 |

By contrast BTC quotes 0.13 bps and HYPE 0.12 bps — the majors are picked
clean by professional market makers who receive **rebates** (-0.1 to -0.3 bps)
that a retail account cannot get. Do not compete there.

Thin top-of-book is a *feature* at this size: a $12 order sits inside $400 of
depth without moving anything.

## 3. Honest economics at $50

Per completed round trip on a 6 bps market with a $12 order:

```
gross spread capture   6.0 bps x $12   = $0.0072
maker fees             3.0 bps x $12   = $0.0036
net per round trip                     = $0.0036
```

**Under half a cent per round trip.** 100 round trips a day is $0.36 — before
adverse selection, which in passive market making typically consumes 50–80% of
gross spread capture. One bad inventory event (a 40 bps adverse move on a $25
position) loses $0.10, wiping out ~28 clean round trips.

State plainly what this means: **$50 is below the practical minimum for this
strategy.** The floor is set by the exchange's $10 minimum order, which forces
you to trade in chunks that are 20–24% of equity. There is no position sizing
that is both above the minimum and prudent at this account size.

I am building it anyway, because you asked for it and the infrastructure is
the real asset — but the honest expectation is **break-even at best, with a
real chance of losing the $50**. Treat this budget as tuition for learning the
machinery, not as capital expected to compound.

If the goal is profit rather than education, the two changes that matter far
more than any strategy tweak are: (a) fund $500–1,000 so position sizing has
room, and (b) stake HYPE for the fee discount (up to 40% off).

## 4. Phased plan — each phase has a gate

Nothing advances to the next phase until its gate passes. The gates are the
plan; the code is just what runs between them.

### Phase 0 — Account setup *(you, ~1 hour)*
1. Fund a wallet with USDC on **Arbitrum One** (bridge minimum 5 USDC).
2. Deposit at https://app.hyperliquid.xyz — credited in about a minute.
3. Generate an **API wallet** at https://app.hyperliquid.xyz/API.
   An API wallet can trade but **cannot withdraw** — this is the key safety
   property. Put its key in `.env` on your own machine.
4. **Never share a private key or seed phrase with me, or paste one into a
   chat.** I have deliberately built this so I never need it.

> Gate: `python3 src/check_account.py` prints your equity.

### Phase 1 — Build history *(2 weeks, no trading)*
Hyperliquid's candle API retains only ~5000 bars (~3.6 days at 1m), which is
why the backtest above rests on a thin sample. `src/collector.py` archives
live BBO and trades so you own history the venue will not give you.

```sh
python3 src/collector.py          # leave running
```

> Gate: 14 days archived for the candidate markets.

### Phase 2 — Paper trade *(2 weeks, no money)*
```sh
python3 src/paper_mm.py           # live prices, simulated fills
```
Fills are modelled pessimistically: a resting quote fills only when a real
trade prints *through* it.

> **Gate — the honest one:** net positive over 14 continuous days, >=200
> simulated fills, max drawdown under $12.50. **If it does not pass, stop.**
> Do not proceed to real money on a strategy that could not make paper money.

### Phase 3 — Testnet *(1 week)*
Same code, `network: testnet`. This validates order mechanics — signing, tick
and lot rounding, cancels, reconnects — not profitability.

> Gate: 1000 orders placed and cancelled with zero rejects.

### Phase 4 — Live micro *(only if 1–3 all passed)*
`network: mainnet`, $12 orders, every limit in `config.yaml` active.

> Gate to continue: after 2 weeks, net > 0 after all fees.
> Otherwise stop and go back to Phase 1.

## 5. Risk controls (enforced in code, not by discipline)

Every one of these is in `src/risk.py` and runs before each order:

| Control | Value | Behaviour |
|---|---|---|
| Order size | $12 | just above the $10 exchange minimum |
| Max position / symbol | $25 | 50% of equity |
| Max gross exposure | $40 | across all symbols |
| Max leverage | 2x | hard ceiling, far below the 3–40x offered |
| Daily loss limit | $5 (10%) | flatten, stop until tomorrow |
| Max drawdown | $12.50 (25%) | stop permanently, human review required |
| Per-position stop | 40 bps | taker exit |
| Kill switch | `touch .halt` | flatten and stop, any time |

Leverage deserves emphasis: Hyperliquid offers up to 40x, and maintenance
margin runs 1.25%–16.7%. At 40x a **2.5% adverse move liquidates you**, and on
backstop liquidation the maintenance margin is *not returned*. The 2x ceiling
is not conservatism, it is the difference between a losing day and a zero.

## 6. What runs where

This planning session runs in an ephemeral container that is reclaimed when the
session ends — **it cannot host a trading bot**. Phases 1–4 must run on a
machine you control: your own computer, or a small VPS (~$5/month) if you want
it up 24/7. Nothing here needs more than 1 vCPU and 512MB.

## 7. Layout

```
hl-scalper/
├── PLAN.md              this document
├── config.yaml          every risk parameter, reviewable without reading code
├── .env.example         API wallet template (.env is gitignored)
└── src/
    ├── fetch_data.py    pull candle history
    ├── backtest.py      pessimistic 1m backtester
    ├── sweep.py         parameter sweep (the 540-config run)
    ├── diagnose.py      raw signal-edge test, fees off
    ├── spread_scan.py   find markets quoting wider than fees
    ├── collector.py     live BBO/trade archiver
    ├── risk.py          limits, kill switch, persistent state
    └── paper_mm.py      paper market maker on live data
```
