"""
LIVE order execution. Same quoting logic as paper_mm, but orders are real.

Safety properties, deliberately built in:
  * Refuses to run unless every earlier phase gate has been recorded.
  * Defaults to testnet; mainnet requires BOTH config.yaml and an explicit
    --i-understand-this-is-real-money flag.
  * Posts ALO (add-liquidity-only) orders exclusively -- an order that would
    cross is rejected by the venue rather than paying the taker fee.
  * Cancels every resting order on exit, including on crash.
  * Honours the same RiskManager and the .halt kill switch as paper mode.

    python3 src/live_mm.py --minutes 60
"""
import asyncio, json, os, sys, time, logging, signal
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from risk import RiskManager, Halt
from check_account import load_env

ROOT = os.path.join(os.path.dirname(__file__), "..")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                              logging.FileHandler(os.path.join(ROOT, "logs", "live.log"))])
log = logging.getLogger("live")


def round_px(px, sz_decimals, is_perp=True):
    """Hyperliquid: max 5 significant figures, and at most
    MAX_DECIMALS - szDecimals decimal places (MAX_DECIMALS = 6 for perps)."""
    max_dec = (6 if is_perp else 8) - sz_decimals
    return float(f"%.{max(max_dec, 0)}f" % float(f"%.5g" % px))


def round_sz(sz, sz_decimals):
    """Sizes floor-truncate to szDecimals."""
    f = 10 ** sz_decimals
    return int(sz * f) / f


class LiveMM:
    def __init__(self, cfg, exchange, info, address):
        self.cfg, self.ex, self.info, self.addr = cfg, exchange, info, address
        self.q = cfg["quoting"]
        self.risk = RiskManager(cfg, state_path=os.path.join(ROOT, "state_live.json"))
        self.meta = {a["name"]: a for a in info.meta()["universe"]}
        self.open_orders = {}     # coin -> {side: oid}

    # ------------------------------------------------------------ ordering
    def cancel_all(self):
        """Best-effort cancel of every resting order. Safe to call repeatedly."""
        try:
            for o in self.info.open_orders(self.addr):
                try:
                    self.ex.cancel(o["coin"], o["oid"])
                    log.info("cancelled %s %s", o["coin"], o["oid"])
                except Exception as e:
                    log.error("cancel failed %s %s: %s", o["coin"], o["oid"], e)
        except Exception as e:
            log.error("could not list open orders: %s", e)
        self.open_orders.clear()

    def place(self, coin, is_buy, px, notional):
        m = self.meta.get(coin)
        if not m:
            return None
        szd = m["szDecimals"]
        px = round_px(px, szd)
        sz = round_sz(notional / px, szd)
        if sz * px < 10:                      # exchange minimum
            log.warning("%s size $%.2f below $10 minimum -- skipped", coin, sz * px)
            return None
        ok, why = self.risk.can_open(coin, notional if is_buy else -notional)
        if not ok:
            log.info("%s %s blocked by risk: %s", coin, "buy" if is_buy else "sell", why)
            return None
        try:
            # ALO = post-only. The venue rejects it rather than let it cross,
            # so we can never accidentally pay the taker fee.
            r = self.ex.order(coin, is_buy, sz, px, {"limit": {"tif": "Alo"}})
            st = r["response"]["data"]["statuses"][0]
            if "resting" in st:
                oid = st["resting"]["oid"]
                self.open_orders.setdefault(coin, {})["buy" if is_buy else "sell"] = oid
                log.info("POST %-8s %-4s %.6f @ %.6f  ($%.2f) oid=%s", coin,
                         "BUY" if is_buy else "SELL", sz, px, sz * px, oid)
                return oid
            log.warning("%s order not resting: %s", coin, st)
        except Exception as e:
            log.error("order failed %s: %s", coin, e)
        return None

    # ----------------------------------------------------------- main loop
    async def run(self, coins, minutes=None):
        deadline = time.time() + minutes * 60 if minutes else None
        log.info("LIVE on %s | equity $%.2f | order $%.2f",
                 ", ".join(coins), self.cfg["account"]["equity_usd"], self.q["order_notional"])
        try:
            while True:
                if deadline and time.time() > deadline:
                    log.info("duration reached")
                    break
                try:
                    self.risk.check_halt()
                except Halt as h:
                    log.error("HALTED (%s) -- cancelling orders and flattening", h)
                    break

                for coin in coins:
                    try:
                        b = self.info.l2_snapshot(coin)
                        bid = float(b["levels"][0][0]["px"])
                        ask = float(b["levels"][1][0]["px"])
                    except Exception as e:
                        log.warning("book fetch failed %s: %s", coin, e)
                        continue
                    mid = (bid + ask) / 2
                    spread_bps = (ask - bid) / mid * 1e4
                    need = self.cfg["fees"]["maker_bps"] * 2 + self.q["edge_bps"]
                    if spread_bps < need:
                        continue
                    self.place(coin, True, bid, self.q["order_notional"])
                    self.place(coin, False, ask, self.q["order_notional"])

                await asyncio.sleep(self.q["max_quote_age_s"])
                self.cancel_all()
                log.info("STATUS %s", self.risk.summary())
        finally:
            log.info("shutting down -- cancelling all orders")
            self.cancel_all()


def main():
    args = sys.argv[1:]
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
    net = cfg["account"]["network"]

    if net == "mainnet" and "--i-understand-this-is-real-money" not in args:
        print("REFUSED  config says mainnet but the confirmation flag is absent.")
        print("         Re-run with --i-understand-this-is-real-money if that is")
        print("         genuinely what you intend.")
        return 1

    gates = os.path.join(ROOT, "gates.json")
    passed = json.load(open(gates)) if os.path.exists(gates) else {}
    required = ["phase0_account", "phase1_data", "phase2_paper", "phase3_testnet"]
    missing = [g for g in required if not passed.get(g)]
    if net == "mainnet" and missing:
        print(f"REFUSED  these gates have not been recorded as passed: {missing}")
        print(f"         See PLAN.md section 4. Record them in {gates} only when")
        print(f"         each phase genuinely passed its stated criteria.")
        return 1

    env = load_env()
    key, addr = env.get("HL_API_PRIVATE_KEY"), env.get("HL_ACCOUNT_ADDRESS")
    if not key or not addr:
        print("FAIL  .env is missing HL_API_PRIVATE_KEY or HL_ACCOUNT_ADDRESS")
        return 1

    import eth_account
    from hyperliquid.info import Info
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants
    url = constants.TESTNET_API_URL if net == "testnet" else constants.MAINNET_API_URL
    wallet = eth_account.Account.from_key(key)
    ex = Exchange(wallet, url, account_address=addr)
    info = Info(url, skip_ws=True)

    minutes = None
    if "--minutes" in args:
        minutes = float(args[args.index("--minutes") + 1])
    coins = [a for a in args if not a.startswith("--") and a.isupper()] \
            or cfg["markets"]["candidates"][:cfg["markets"]["max_concurrent"]]

    mm = LiveMM(cfg, ex, info, addr)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: (mm.cancel_all(), sys.exit(0)))
    asyncio.run(mm.run(coins, minutes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
