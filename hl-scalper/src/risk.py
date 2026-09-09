"""
Risk limits. Every order passes through `RiskManager.check()` before it is
sent; every fill passes through `on_fill()`. The manager is the only thing
allowed to say "stop", and once it says stop it stays stopped until a human
clears the state file.
"""
import json, os, time, logging

log = logging.getLogger("risk")


class Halt(Exception):
    """Raised when trading must stop. Never caught by the strategy loop."""


class RiskManager:
    def __init__(self, cfg, state_path="state.json"):
        self.cfg = cfg
        self.r = cfg["risk"]
        self.equity0 = cfg["account"]["equity_usd"]
        self.state_path = state_path
        self.positions = {}          # coin -> signed notional in USD
        self.realized = 0.0
        self.day = time.strftime("%Y-%m-%d")
        self.day_pnl = 0.0
        self.peak = 0.0
        self.halted = None
        self._load()

    # ---------------------------------------------------------------- state
    def _load(self):
        if os.path.exists(self.state_path):
            s = json.load(open(self.state_path))
            self.__dict__.update({k: s[k] for k in
                ("realized", "day", "day_pnl", "peak", "halted") if k in s})
            self.positions = s.get("positions", {})

    def save(self):
        json.dump({"realized": self.realized, "day": self.day,
                   "day_pnl": self.day_pnl, "peak": self.peak,
                   "halted": self.halted, "positions": self.positions,
                   "ts": time.time()}, open(self.state_path, "w"), indent=2)

    # ---------------------------------------------------------------- gates
    def _rollover(self):
        today = time.strftime("%Y-%m-%d")
        if today != self.day:
            log.info("day rollover %s -> %s (pnl %.2f)", self.day, today, self.day_pnl)
            self.day, self.day_pnl = today, 0.0
            if self.halted == "daily_loss":
                self.halted = None       # a new day clears only the daily stop

    def check_halt(self):
        """Raise if trading must not continue. Called before every quote cycle."""
        self._rollover()
        if os.path.exists(self.cfg["risk"]["kill_switch_file"]):
            self.halted = "kill_switch"
        if self.halted:
            raise Halt(self.halted)

    def can_open(self, coin, add_notional):
        """True if adding `add_notional` (signed) keeps us inside every limit."""
        self._rollover()
        if self.halted:
            return False, self.halted
        new = self.positions.get(coin, 0.0) + add_notional
        if abs(new) > self.r["max_position_usd"]:
            return False, "max_position"
        gross = sum(abs(v) for k, v in self.positions.items() if k != coin) + abs(new)
        if gross > self.r["max_gross_usd"]:
            return False, "max_gross"
        equity = self.equity0 + self.realized
        if gross > equity * self.cfg["quoting"]["max_leverage"]:
            return False, "max_leverage"
        return True, "ok"

    # ----------------------------------------------------------------- fills
    def on_fill(self, coin, notional_delta, realized_pnl=0.0):
        self._rollover()
        self.positions[coin] = self.positions.get(coin, 0.0) + notional_delta
        if abs(self.positions[coin]) < 0.01:
            self.positions.pop(coin, None)
        self.realized += realized_pnl
        self.day_pnl += realized_pnl
        self.peak = max(self.peak, self.realized)

        if self.day_pnl <= -self.r["daily_loss_limit_usd"]:
            self.halted = "daily_loss"
            log.error("DAILY LOSS LIMIT hit: %.2f", self.day_pnl)
        if (self.peak - self.realized) >= self.r["max_drawdown_usd"]:
            self.halted = "max_drawdown"
            log.error("MAX DRAWDOWN hit: peak %.2f now %.2f", self.peak, self.realized)
        self.save()

    def summary(self):
        return (f"realized=${self.realized:+.3f} day=${self.day_pnl:+.3f} "
                f"gross=${sum(abs(v) for v in self.positions.values()):.2f} "
                f"pos={self.positions or '{}'} halt={self.halted or '-'}")
