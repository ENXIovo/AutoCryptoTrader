import time
import uuid
import requests
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("M1_Tester")

BASE_URL = "http://localhost:8100"  # Adjust if your port is different
# Hyperliquid-Lite uses "coin" not pair, but internal matching uses pair
# We will use "BTC" as coin
COIN = "BTC"

def test_connectivity():
    """Check if API is reachable via /info."""
    try:
        payload = {"type": "metaAndAssetCtxs"}
        resp = requests.post(f"{BASE_URL}/info", json=payload)
        if resp.status_code == 200:
            logger.info("✅ Connectivity Check Passed")
            return True
        else:
            logger.error(f"❌ Connectivity Check Failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Connectivity Check Failed: {e}")
        return False

def test_case_1_limit_buy_open():
    """Case 1: Place a far Limit Buy (should OPEN)."""
    logger.info("--- Starting Case 1: Limit Buy (Open) ---")
    
    price = 10000.0 
    sz = 0.1
    
    payload = {
        "coin": COIN,
        "is_buy": True,
        "sz": sz,
        "limit_px": price,
        "order_type": {"limit": {"tif": "Gtc"}},
        "reduce_only": False
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/exchange/order", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                oid = data["response"]["data"]["oid"]
                logger.info(f"✅ Order Placed. OID: {oid}")
                return oid
            else:
                logger.error(f"❌ API Error: {data}")
                return None
        else:
            logger.error(f"❌ HTTP Error: {resp.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Exception: {e}")
        return None

def test_case_2_cancel_order(oid):
    """Case 2: Cancel the order from Case 1."""
    logger.info("--- Starting Case 2: Cancel Order ---")
    if not oid:
        logger.warning("⚠️ Skipping Case 2 due to Case 1 failure.")
        return False

    payload = {
        "coin": COIN,
        "oid": oid
    }

    try:
        resp = requests.post(f"{BASE_URL}/exchange/cancel", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                logger.info(f"✅ Cancel Request Sent for OID {oid}")
                return True
            else:
                logger.error(f"❌ API Error: {data}")
                return False
        else:
            logger.error(f"❌ HTTP Error: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Exception: {e}")
        return False

def test_case_3_market_buy():
    """Case 3: Market Buy (Immediate Fill)."""
    logger.info("--- Starting Case 3: Market Buy ---")
    
    sz = 0.001
    # Market order in HL logic usually implies IOC or Frontend logic, 
    # here we mapped it to internal market order
    payload = {
        "coin": COIN,
        "is_buy": True,
        "sz": sz,
        "limit_px": 0, # Market
        "order_type": {"market": {}}, 
        "reduce_only": False
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/exchange/order", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                oid = data["response"]["data"]["oid"]
                logger.info(f"✅ Market Order Placed. OID: {oid}")
                
                # Wait for fill (polling driver cycle)
                logger.info("⏳ Waiting 60s for fill (polling cycle)...")
                # In real test we might not want to wait 60s, but M1 is 1m candle based.
                # We can just check if order status is closed in snapshot?
                # Our API doesn't expose order status query directly (HL doesn't have simple GET order status)
                # But we can check Balance change via /info
                
                time.sleep(5) 
                
                # Check Balance
                info_payload = {"type": "clearinghouseState"}
                info_resp = requests.post(f"{BASE_URL}/info", json=info_payload)
                if info_resp.status_code == 200:
                    state = info_resp.json()
                    equity = float(state.get("marginSummary", {}).get("accountValue", 0))
                    logger.info(f"✅ Account Value: {equity} (Should be ~10000 if flat, or changed if held)")
                    return True
            else:
                logger.error(f"❌ API Error: {data}")
                return False
        else:
            logger.error(f"❌ HTTP Error: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Exception: {e}")
        return False

def run_tests():
    logger.info("🚀 Starting M1 (Hyperliquid-Lite) Verification Suite")
    
    if not test_connectivity():
        logger.error("⛔ Aborting tests: Service unreachable.")
        return

    oid = test_case_1_limit_buy_open()
    if oid:
        test_case_2_cancel_order(oid)
    
    test_case_3_market_buy()
    
    logger.info("🏁 Test Suite Completed.")

if __name__ == "__main__":
    run_tests()
