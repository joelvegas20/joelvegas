"""
Phase 0 gate. Verifies the account is reachable and correctly configured
WITHOUT placing any order. Read-only: it never signs a transaction.

    python3 src/check_account.py
"""
import os, sys, json, yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_env(path=os.path.join(ROOT, ".env")):
    if not os.path.exists(path):
        return {}
    out = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
    env = load_env()
    addr = env.get("HL_ACCOUNT_ADDRESS", "")
    net = cfg["account"]["network"]

    if not addr.startswith("0x") or len(addr) != 42:
        print("FAIL  HL_ACCOUNT_ADDRESS missing or malformed in .env")
        print("      Copy .env.example to .env and fill it in.")
        print("      This must be your MAIN wallet address, not the API wallet's.")
        return 1

    from hyperliquid.info import Info
    from hyperliquid.utils import constants
    url = constants.TESTNET_API_URL if net == "testnet" else constants.MAINNET_API_URL
    info = Info(url, skip_ws=True)
    st = info.user_state(addr)

    equity = float(st["marginSummary"]["accountValue"])
    used = float(st["marginSummary"]["totalMarginUsed"])
    withdrawable = float(st.get("withdrawable", 0))
    print(f"network        {net}")
    print(f"address        {addr}")
    print(f"equity         ${equity:,.2f}")
    print(f"margin used    ${used:,.2f}")
    print(f"withdrawable   ${withdrawable:,.2f}")

    positions = [p["position"] for p in st.get("assetPositions", [])]
    if positions:
        print("open positions:")
        for p in positions:
            print(f"  {p['coin']:<8} szi={p['szi']:>12}  entry={p.get('entryPx')}"
                  f"  uPnL={p.get('unrealizedPnl')}  lev={p['leverage']['value']}x")
    else:
        print("open positions none")

    cfg_eq = cfg["account"]["equity_usd"]
    if abs(equity - cfg_eq) > cfg_eq * 0.2:
        print(f"\nWARN  config.yaml says equity_usd={cfg_eq} but the account "
              f"holds ${equity:,.2f}. Risk limits are derived from the config "
              f"value -- update it before trading.")
    if equity < 10:
        print("\nFAIL  equity below the $10 exchange minimum order size.")
        return 1
    print("\nPASS  Phase 0 gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
