import json
from concurrent.futures import ThreadPoolExecutor
from app.config import SHORT_TERM_SYSTEM_MESSAGE, MID_TERM_SYSTEM_MESSAGE, LONG_TERM_SYSTEM_MESSAGE, USER_MESSAGE
from app.gpt_client import GPTClient
from app.models import MessageRequest

def fetch_data(url: str):
    """Fetch data from a given URL."""
    import requests
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching data from {url}: {e}")
        return None


def process_open_orders_balance(data: dict, current_price: float) -> dict:
    """Process open orders and compute necessary statistics."""
    processed = {}

    # Normalize keys and extract relevant information
    for key, value in data.items():
        if key == "trade_history":
            key = "closed_order"  # Rename key
        processed[key] = value

    # Analyze balance and open orders
    balance = processed.get("balance", {})
    filtered_balance = {}
    for symbol, value in balance.items():
        if "USD" not in symbol:
            filtered_balance[symbol] = value
    processed["balance"] = filtered_balance
    
    open_orders = processed.get("open_orders")
    altname = processed.get("altname")
    symbol = processed.get("symbol_request")
    
    filtered_open_orders = []
    
    for pair, orders in open_orders.items():
        if altname in pair or symbol in pair:
            filtered_open_orders.append(orders)
    
    processed["open_orders"] = filtered_open_orders
    processed["usd_analysis"] = calculate_available_usd(altname, balance, open_orders)

    # Calculate weighted prices and other statistics
    if "closed_order" in processed:
        closed_orders = processed["closed_order"]
        weighted_prices = calculate_weighted_prices(closed_orders, current_price)
        processed["weighted_prices"] = weighted_prices
        processed["closed_order"] = closed_orders

    return processed


def calculate_available_usd(altname: str, balance: dict, open_orders: list) -> dict:
    """Calculate available USD based on balance and open orders."""
    total_usd = sum(float(value) for key, value in balance.items() if "USD" in key)
    total_crypto = float(next((value for key, value in balance.items() if altname in key), 0))
    total_open_order_value = sum(
        float(order.get("price", 0)) * float(order.get("vol", 0))
        for orders in open_orders.values()
        for order in orders 
        if order.get("type") == "buy"
        and order.get("status") == "open"
    )
    
    total_open_order_crypto = sum(
        float(order.get("vol", 0))
        for orders in open_orders.values()
        for order in orders 
        if order.get("type") == "sell"
        and order.get("status") == "open"
    )
    available_usd = total_usd - total_open_order_value
    available_crypto = total_crypto - total_open_order_crypto
    return {
        # "total_usd": total_usd,
        # "open_order_value": total_open_order_value,
        "available_usd": available_usd,
        "available_crypto": available_crypto
    }


def calculate_weighted_prices(closed_orders: dict, current_price: float) -> dict:
    """Calculate weighted average prices and unrealized PnL."""
    weighted_prices = {
        "weighted_average_buy_price": 0,
        "weighted_average_sell_price": 0,
        "total_buy_volume": 0,
        "total_sell_volume": 0,
        "unrealized_pnl_percent": 0.0,
    }
    for trades in closed_orders.values():
        for trade in trades:
            trade_type = trade.get("type")
            price = float(trade.get("price", 0))
            volume = float(trade.get("vol", 0))
            if trade_type == "buy":
                weighted_prices["weighted_average_buy_price"] += price * volume
                weighted_prices["total_buy_volume"] += volume
            elif trade_type == "sell":
                weighted_prices["weighted_average_sell_price"] += price * volume
                weighted_prices["total_sell_volume"] += volume
    if weighted_prices["total_buy_volume"] > 0:
        weighted_prices["weighted_average_buy_price"] /= weighted_prices["total_buy_volume"]
        weighted_prices["unrealized_pnl_percent"] = (
            (current_price - weighted_prices["weighted_average_buy_price"])
            / weighted_prices["weighted_average_buy_price"]
        ) * 100
    if weighted_prices["total_sell_volume"] > 0:
        weighted_prices["weighted_average_sell_price"] /= weighted_prices["total_sell_volume"]
    return weighted_prices

def fetch_account_data(symbol: str):
    # 并发获取市场数据和订单信息
    with ThreadPoolExecutor() as executor:
        future_market = executor.submit(fetch_data, f"http://host.docker.internal:8000/gpt-latest/{symbol}USD")
        future_orders = executor.submit(fetch_data, f"http://host.docker.internal:9000/kraken-filter?symbol={symbol}")

        market_data = future_market.result()
        account_data = future_orders.result()

    # 检查数据是否完整
    if not market_data or not account_data:
        print("Failed to fetch required data. Please check API connectivity.")
        return
    # Mock fetching account data
    return market_data, account_data

def execute_analysis(symbol: str, analysis_mode: str = "short") -> str:
    """
    Fully automated analysis process. Combines three steps of analysis and returns final output.
    """
    market_data, account_data = fetch_account_data(symbol)

    current_price = market_data.get("common_info").get("ticker").get("last_price")
    processed_data = process_open_orders_balance(account_data, current_price)

    balance = processed_data.get("balance")
    open_orders = processed_data.get("open_orders", [])
    # trade_balance = processed_data.get("trade_balance") 整个账户情况，暂时不需要，usd_analysis有流动资金的情况
    usd_analysis = processed_data.get("usd_analysis")
    weighted_prices = processed_data.get("weighted_prices")

    USER_MESSAGE_FILLED = USER_MESSAGE.format(
        symbol=symbol,
        market_data=json.dumps(market_data, indent=2),
        usd_analysis=json.dumps(usd_analysis, indent=2),
        balance=json.dumps(balance, indent=2),
        open_orders=json.dumps(open_orders, indent=2),
        weighted_prices=json.dumps(weighted_prices, indent=2),
    )
    print(USER_MESSAGE_FILLED)
    
    if analysis_mode == "short":
        system_prompt = SHORT_TERM_SYSTEM_MESSAGE.format(symbol=symbol)
    elif analysis_mode == "mid":
        system_prompt = MID_TERM_SYSTEM_MESSAGE.format(symbol=symbol)
    elif analysis_mode == "long":
        system_prompt = LONG_TERM_SYSTEM_MESSAGE.format(symbol=symbol)
    else:
        # 可以抛出异常或默认为短期
        system_prompt = SHORT_TERM_SYSTEM_MESSAGE
    

    print("User message (short/mid/long) sent, processing...", analysis_mode)
    gpt_request = MessageRequest(
        message=USER_MESSAGE_FILLED, 
        system_message=system_prompt
    )
    gpt_response = GPTClient.send_message(gpt_request)
    print(gpt_response["content"])

    return gpt_response["content"]

# if __name__ == "__main__":
#     execute_analysis("TRUMP")
