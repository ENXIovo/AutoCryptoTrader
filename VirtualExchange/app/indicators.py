"""
Technical Indicators Calculator - 单职责：技术指标计算
与DataCollector使用相同的计算逻辑，确保生产模式和回测模式一致
统一使用UTC时区
"""
import pandas as pd
from typing import List, Optional, Tuple


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """
    计算EMA（指数移动平均）
    与DataCollector的calculate_ema逻辑一致
    """
    if not prices or len(prices) < period:
        return None
    prices_series = pd.Series(prices)
    return float(prices_series.ewm(span=period, adjust=False).mean().iloc[-1])


def calculate_sma(prices: List[float], period: int) -> Optional[float]:
    """
    计算SMA（简单移动平均）
    与DataCollector的calculate_sma逻辑一致
    """
    if len(prices) < period:
        return None
    prices_series = pd.Series(prices)
    return float(prices_series.rolling(window=period).mean().iloc[-1])


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    计算RSI（相对强弱指标）
    与DataCollector的calculate_rsi逻辑一致
    """
    if len(prices) < period + 1:  # 需要至少period+1个数据点
        return None
    prices_series = pd.Series(prices)
    delta = prices_series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty and not pd.isna(rsi.iloc[-1]) else None


def calculate_macd(
    prices: List[float], 
    short_period: int = 12, 
    long_period: int = 26, 
    signal_period: int = 9
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    计算MACD（移动平均收敛散度）
    与DataCollector的calculate_macd逻辑一致
    
    Returns:
        (macd_line, macd_signal, macd_hist)
    """
    if len(prices) < long_period:
        return None, None, None
    close_series = pd.Series(prices)
    short_ema = close_series.ewm(span=short_period, adjust=False).mean()
    long_ema = close_series.ewm(span=long_period, adjust=False).mean()
    macd_line = short_ema - long_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    hist = macd_line - signal_line
    return (
        float(macd_line.iloc[-1]) if not macd_line.empty else None,
        float(signal_line.iloc[-1]) if not signal_line.empty else None,
        float(hist.iloc[-1]) if not hist.empty else None
    )


def calculate_bollinger_bands(
    prices: List[float], 
    period: int = 20, 
    num_std: float = 2.0
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    计算布林带
    与DataCollector的calculate_bollinger_bands逻辑一致
    
    Returns:
        (upper, middle, lower)
    """
    if len(prices) < period:
        return None, None, None
    close_series = pd.Series(prices)
    middle = close_series.rolling(window=period).mean()
    std = close_series.rolling(window=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return (
        float(upper.iloc[-1]) if not upper.empty else None,
        float(middle.iloc[-1]) if not middle.empty else None,
        float(lower.iloc[-1]) if not lower.empty else None
    )


def calculate_atr(
    highs: List[float], 
    lows: List[float], 
    closes: List[float], 
    period: int = 14
) -> Optional[float]:
    """
    计算ATR（平均真实波幅）
    与DataCollector的calculate_atr逻辑一致
    """
    if len(highs) < period + 1:
        return None
    tr_list = []
    for i in range(1, len(highs)):
        current_high = highs[i]
        current_low = lows[i]
        prev_close = closes[i-1]
        tr = max(
            current_high - current_low,
            abs(current_high - prev_close),
            abs(current_low - prev_close)
        )
        tr_list.append(tr)
    tr_series = pd.Series(tr_list)
    atr_series = tr_series.rolling(window=period).mean()
    return float(atr_series.iloc[-1]) if not atr_series.empty else None

