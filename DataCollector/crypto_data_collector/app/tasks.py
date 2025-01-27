# tasks.py

import json
import redis

from celery import Celery
from celery.schedules import crontab
from sqlalchemy.orm import Session
import pandas as pd
from decimal import Decimal
from typing import List

from app.db import SessionLocal
from app.models import MarketData
from app.config import settings
from app import crud
from app.kraken_client import (
    get_ticker,
    get_order_book,
    get_ohlc,
    get_recent_trades,
)

redis_client = redis.Redis(host='redis-server', port=6379, decode_responses=True)

celery_app = Celery(
    "tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.beat_schedule = {
    "fetch-all-symbols-every-minute": {
        "task": "app.tasks.fetch_all_symbols_data",
        "schedule": crontab(minute="*"),  # 每分钟运行一次
    },
}
celery_app.conf.timezone = "UTC"

@celery_app.task
def fetch_all_symbols_data():
    """
    定时任务：遍历 SYMBOLS 列表并获取数据
    """
    db: Session = SessionLocal()
    try:
        symbols = settings.SYMBOLS
        intervals = [1, 5, 15, 60, 240, 1440]  # 示例间隔，可以自定义

        for symbol in symbols:
            print(f"[Celery] Fetching data for {symbol}")
            fetch_and_store_data_for_intervals(symbol, intervals)
    except Exception as e:
        print(f"[Celery] Error in scheduled task: {e}")
    finally:
        db.close()


@celery_app.task
def fetch_and_store_data_for_intervals(symbol: str, intervals: List[int]):
    """
    一次性处理多个周期(例如 1, 60, 240, 1440 等).
    - Ticker / OrderBook / Trades: 只需要获取一次即可
    - OHLC: 每个 interval 都要获取一遍并计算指标
    - 每个 interval 会单独保存到数据库
    - 最后打印出一个“给 GPT 用”的整合结果到终端
    """
    db: Session = SessionLocal()
    try:
        print(f"[Celery] Starting multi-interval data fetch for symbol: {symbol} intervals={intervals}")

        # ====== 1) 通用数据 (Ticker / OrderBook / RecentTrades) ======
        # 这些与 interval 无关，只需获取/计算一次

        # Ticker
        print("[Celery] Fetching ticker data...")
        ticker_data = get_ticker(symbol)
        ticker_key = list(ticker_data.keys())[0]
        t_data = ticker_data[ticker_key]
        last_price = float(t_data["c"][0])
        best_ask_price = float(t_data["a"][0])
        best_bid_price = float(t_data["b"][0])
        volume_24h = float(t_data["v"][-1])
        high_24h = float(t_data["h"][-1])
        low_24h = float(t_data["l"][-1])
        print(f"[Celery] Ticker data: last_price={last_price}, "
              f"bid={best_bid_price}, ask={best_ask_price}, vol_24h={volume_24h}")

        # Order Book
        print("[Celery] Fetching order book data...")
        order_book = get_order_book(symbol, depth=20)
        ob_key = list(order_book.keys())[0]
        ob_data = order_book[ob_key]
        asks = ob_data.get("asks", [])
        bids = ob_data.get("bids", [])

        top_ask_price = float(asks[0][0]) if asks else None
        top_ask_volume = float(asks[0][1]) if asks else None
        top_bid_price = float(bids[0][0]) if bids else None
        top_bid_volume = float(bids[0][1]) if bids else None

        total_bid_volume = sum(float(b[1]) for b in bids)
        total_ask_volume = sum(float(a[1]) for a in asks)
        bid_ask_volume_ratio = (total_bid_volume / total_ask_volume) if total_ask_volume else None
        spread = (top_ask_price - top_bid_price) if (top_ask_price and top_bid_price) else None
        print("[Celery] Order book data: top_ask_price={top_ask_price}, "
              f"top_bid_price={top_bid_price}, spread={spread}")

        # Recent Trades
        print("[Celery] Fetching recent trades data...")
        trades_data = get_recent_trades(symbol)
        trades_key = list(trades_data.keys())[0]
        trades_list = trades_data[trades_key]

        recent_buy_count = sum(1 for t in trades_list if t[3] == "b")
        recent_sell_count = sum(1 for t in trades_list if t[3] == "s")
        total_buy_volume_trades = sum(float(t[1]) for t in trades_list if t[3] == "b")
        total_sell_volume_trades = sum(float(t[1]) for t in trades_list if t[3] == "s")
        buy_sell_volume_ratio = (
            total_buy_volume_trades / total_sell_volume_trades
            if total_sell_volume_trades > 0 else None
        )
        print("[Celery] Trades data: buys={recent_buy_count}, sells={recent_sell_count}, "
              f"buy_volume={total_buy_volume_trades}, sell_volume={total_sell_volume_trades}")

        # ====== 2) 供 GPT 使用的整合数据结构 ======
        # 每个 interval 算完后往这里塞数据
        gpt_data = {
            "symbol": symbol,
            "common_info": {
                "ticker": {
                    "last_price": last_price,
                    "best_ask_price": best_ask_price,
                    "best_bid_price": best_bid_price,
                    "volume_24h": volume_24h,
                    "high_24h": high_24h,
                    "low_24h": low_24h
                },
                "order_book": {
                    "top_ask_price": top_ask_price,
                    "top_ask_volume": top_ask_volume,
                    "top_bid_price": top_bid_price,
                    "top_bid_volume": top_bid_volume,
                    "total_bid_volume": total_bid_volume,
                    "total_ask_volume": total_ask_volume,
                    "bid_ask_volume_ratio": bid_ask_volume_ratio,
                    "spread": spread,
                },
                "recent_trades": {
                    "recent_buy_count": recent_buy_count,
                    "recent_sell_count": recent_sell_count,
                    "total_buy_volume_trades": total_buy_volume_trades,
                    "total_sell_volume_trades": total_sell_volume_trades,
                    "buy_sell_volume_ratio": buy_sell_volume_ratio
                }
            },
            "intervals_data": {}
        }

        # ====== 3) 针对每个 interval 做 OHLC 计算 ======
        for interval in intervals:
            print(f"[Celery] Processing interval={interval} ...")

            # (a) 拉取OHLC
            ohlc_data = get_ohlc(symbol, interval=interval)
            ohlc_key = list(ohlc_data.keys())[0]
            kline_list = ohlc_data[ohlc_key]
            if not kline_list:
                print(f"[Celery] No OHLC data for interval={interval}, skipping...")
                continue

            closes = [float(item[4]) for item in kline_list]
            highs = [float(item[2]) for item in kline_list]
            lows = [float(item[3]) for item in kline_list]

            # (b) 计算指标
            ema_9 = calculate_ema(closes, period=9)
            sma_14 = calculate_sma(closes, period=14)
            rsi_14 = calculate_rsi(closes, period=14)
            macd_line, macd_signal, macd_hist = calculate_macd(closes)
            boll_up, boll_mid, boll_low = calculate_bollinger_bands(closes)
            atr_14 = calculate_atr(highs, lows, closes, period=14)

            # (c) 拼出单个interval数据 (给 GPT)
            interval_data = {
                "timeframe": interval,
                "ema_9": ema_9,
                "sma_14": sma_14,
                "rsi_14": rsi_14,
                "macd_line": macd_line,
                "macd_signal": macd_signal,
                "macd_hist": macd_hist,
                "bollinger_upper": boll_up,
                "bollinger_middle": boll_mid,
                "bollinger_lower": boll_low,
                "atr_14": atr_14
            }
            # 放到 gpt_data 结构
            gpt_data["intervals_data"][str(interval)] = interval_data

            # (d) 要存数据库的话，先组装 combined_data
            combined_data = {
                "symbol": symbol,
                "timeframe": str(interval),  # 需要在models.py里添加 timeframe 字段
                "latest_price": Decimal(str(last_price)),
                "bid_price": Decimal(str(best_bid_price)),
                "ask_price": Decimal(str(best_ask_price)),
                "volume_24h": Decimal(str(volume_24h)),
                "high_24h": Decimal(str(high_24h)),
                "low_24h": Decimal(str(low_24h)),

                # Order book
                "top_ask_price": Decimal(str(top_ask_price)) if top_ask_price else None,
                "top_ask_volume": Decimal(str(top_ask_volume)) if top_ask_volume else None,
                "top_bid_price": Decimal(str(top_bid_price)) if top_bid_price else None,
                "top_bid_volume": Decimal(str(top_bid_volume)) if top_bid_volume else None,
                "total_bid_volume": Decimal(str(total_bid_volume)),
                "total_ask_volume": Decimal(str(total_ask_volume)),
                "bid_ask_volume_ratio": Decimal(str(bid_ask_volume_ratio)) if bid_ask_volume_ratio else None,
                "spread": Decimal(str(spread)) if spread else None,

                # Indicators
                "ema_9": Decimal(str(ema_9)) if ema_9 else None,
                "sma_14": Decimal(str(sma_14)) if sma_14 else None,
                "rsi": Decimal(str(rsi_14)) if rsi_14 else None,
                "macd_line": Decimal(str(macd_line)) if macd_line else None,
                "macd_signal": Decimal(str(macd_signal)) if macd_signal else None,
                "macd_hist": Decimal(str(macd_hist)) if macd_hist else None,
                "bollinger_upper": Decimal(str(boll_up)) if boll_up else None,
                "bollinger_middle": Decimal(str(boll_mid)) if boll_mid else None,
                "bollinger_lower": Decimal(str(boll_low)) if boll_low else None,
                "atr": Decimal(str(atr_14)) if atr_14 else None,

                # Trades
                "recent_buy_count": recent_buy_count,
                "recent_sell_count": recent_sell_count,
                "total_buy_volume": Decimal(str(total_buy_volume_trades)),
                "total_sell_volume": Decimal(str(total_sell_volume_trades)),
                "buy_sell_volume_ratio": Decimal(str(buy_sell_volume_ratio)) if buy_sell_volume_ratio else None,
            }

            # (e) 去重/保存数据库
            existing_data = db.query(MarketData).filter_by(symbol=symbol)\
                              .filter_by(timeframe=str(interval))\
                              .order_by(MarketData.created_at.desc()).first()
            if existing_data and float(existing_data.latest_price) == last_price:
                print(f"[Celery] Duplicate data for {symbol} interval={interval}, skipping DB save.")
                continue

            saved_record = crud.save_market_data(db, combined_data)
            print(f"[Celery] Data saved for interval={interval}, ID={saved_record.id}")

        # ====== 4) 最终打印“整合后给 GPT 看”的数据 ======
        print("[Celery] GPT DATA (Multi-Interval) =============================")
        print(json.dumps(gpt_data, indent=2))
        print("[Celery] ======================================================")

        # ====== 存储到 Redis (覆盖式) ======
        # 例如我们用 "gpt_data:<symbol>" 作为 key
        redis_key = f"gpt_data:{symbol}"
        redis_value = json.dumps(gpt_data)
        # 设置一个TTL，比如 300 秒，也可以不设置
        redis_client.set(redis_key, redis_value, ex=300)

        # 最后将 gpt_data 作为任务的返回值
        return gpt_data

    except Exception as e:
        print(f"[Celery] Error during multi-interval data collection for {symbol} intervals={intervals}: {e}")
        return {"error": str(e)}
    finally:
        db.close()
        print("[Celery] Database session closed.")


# ======== 指标计算函数 (与前相同) ========
def calculate_ema(prices: list, period: int) -> float:
    if not prices or len(prices) < period:
        return None
    prices_series = pd.Series(prices)
    return prices_series.ewm(span=period, adjust=False).mean().iloc[-1]

def calculate_sma(prices: list, period: int) -> float:
    if len(prices) < period:
        return None
    prices_series = pd.Series(prices)
    return prices_series.rolling(window=period).mean().iloc[-1]

def calculate_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period:
        return None
    prices_series = pd.Series(prices)
    delta = prices_series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs)).iloc[-1]

def calculate_macd(prices: list, short_period=12, long_period=26, signal_period=9):
    if len(prices) < long_period:
        return None, None, None
    close_series = pd.Series(prices)
    short_ema = close_series.ewm(span=short_period, adjust=False).mean()
    long_ema = close_series.ewm(span=long_period, adjust=False).mean()
    macd_line = short_ema - long_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], hist.iloc[-1]

def calculate_bollinger_bands(prices: list, period=20, num_std=2):
    if len(prices) < period:
        return None, None, None
    close_series = pd.Series(prices)
    middle = close_series.rolling(window=period).mean()
    std = close_series.rolling(window=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper.iloc[-1], middle.iloc[-1], lower.iloc[-1]

def calculate_atr(highs: list, lows: list, closes: list, period=14) -> float:
    if len(highs) < period + 1:
        return None
    tr_list = []
    for i in range(1, len(highs)):
        current_high = highs[i]
        current_low = lows[i]
        prev_close = closes[i-1]
        tr = max(current_high - current_low,
                 abs(current_high - prev_close),
                 abs(current_low - prev_close))
        tr_list.append(tr)
    tr_series = pd.Series(tr_list)
    atr_series = tr_series.rolling(window=period).mean()
    return atr_series.iloc[-1] if not atr_series.empty else None
