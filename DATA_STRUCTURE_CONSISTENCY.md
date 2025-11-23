# 数据结构一致性检查报告

## ✅ 检查结果：数据结构已完全一致

### 1. getTopNews 数据结构

#### 生产模式
```python
# News Service 返回
List[NewsItem] = [
    {
        "source": str,
        "category": str,  # "regulation,macro" 或 ["regulation","macro"]
        "importance": str,  # "0.8"
        "durability": str,  # "days"
        "summary": str,
        "confidence": str,  # "0.9"
        "ts": str,  # Unix timestamp 或 ISO8601
        "key": str,
        "label_version": str,
        "weight": float,
        "age": Optional[str]  # "15 hours ago"
    }
]

# NewsClient.getTopNews() 白名单过滤后
List[dict] = [
    {
        "summary": str,
        "category": List[str],  # 统一转换为列表
        "durability": str,
        "weight": float,  # 四舍五入到3位小数
        "confidence": str,
        "source": str,
        "age": Optional[str],
        "ts": str
    }
]
```

#### 回测模式
```python
# 完全相同的数据结构
# 唯一区别：before_timestamp 过滤，只返回历史时间点之前的新闻
```

**✅ 一致性**: 完全一致

---

### 2. getKlineIndicators 数据结构

#### 生产模式（DataCollector）
```python
{
    "symbol": str,  # "BTCUSDT"
    "common_info": {
        "ticker": {
            "last_price": float,
            "best_ask_price": float,
            "best_bid_price": float,
            "volume_24h": float,
            "high_24h": float,
            "low_24h": float
        },
        "order_book": {
            "top_ask_price": float,
            "top_ask_volume": float,
            "top_bid_price": float,
            "top_bid_volume": float,
            "total_bid_volume": float,
            "total_ask_volume": float,
            "bid_ask_volume_ratio": float,
            "spread": float
        },
        "recent_trades": {
            "recent_buy_count": int,
            "recent_sell_count": int,
            "total_buy_volume_trades": float,
            "total_sell_volume_trades": float,
            "buy_sell_volume_ratio": float
        }
    },
    "intervals_data": {
        "15": {  # 字符串键，数字是interval（分钟数）
            "timeframe": 15,  # 数字，不是字符串
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float,
            "ema_9": float,
            "sma_14": float,
            "rsi_14": float,
            "macd_line": float,
            "macd_signal": float,
            "macd_hist": float,
            "bollinger_upper": float,
            "bollinger_middle": float,
            "bollinger_lower": float,
            "atr_14": float
        },
        "240": {  # 4h = 240分钟
            ...
        },
        "1440": {  # 1d = 1440分钟
            ...
        }
    }
}
```

#### 回测模式（VirtualExchange）
```python
# 完全相同的数据结构
# 唯一区别：
# 1. 使用历史K线数据计算指标
# 2. 使用与DataCollector相同的指标计算函数（indicators.py）
```

**✅ 一致性**: 完全一致（已修复）

---

### 3. getAccountInfo 数据结构

#### 生产模式
```python
{
    "marginSummary": {
        "accountValue": str,  # Decimal转字符串
        "totalMarginUsed": str
    },
    "crossMarginSummary": {
        "accountValue": str
    },
    "assetPositions": List[dict],
    "openOrders": [
        {
            "oid": int,
            "coin": str,  # "BTC"
            "side": str,  # "B" 或 "A"
            "limitPx": str,  # Decimal转字符串
            "sz": str,  # Decimal转字符串
            "timestamp": int  # Unix毫秒
        }
    ]
}
```

#### 回测模式
```python
# 完全相同的数据结构
# 唯一区别：使用回测时间点的账户状态
```

**✅ 一致性**: 完全一致

---

## 🔧 修复的问题

### 问题1: 指标计算不一致 ❌ → ✅

**之前**:
- 回测模式使用简化计算（RSI=50.0固定值，MACD=0.0固定值）
- 生产模式使用完整计算（calculate_rsi, calculate_macd等）

**修复**:
- 创建 `VirtualExchange/app/indicators.py`，使用与DataCollector完全相同的指标计算逻辑
- 回测模式现在使用相同的计算函数

### 问题2: timeframe字段类型不一致 ❌ → ✅

**之前**:
- 生产模式：`timeframe: 15` (数字)
- 回测模式：`timeframe: "15m"` (字符串)

**修复**:
- 回测模式现在使用数字：`timeframe: 15` (与生产模式一致)

---

## 📊 数据结构对比表

| 字段 | 生产模式 | 回测模式 | 一致性 |
|------|---------|---------|--------|
| **getTopNews** | | | |
| `category` | List[str] | List[str] | ✅ |
| `weight` | float (3位小数) | float (3位小数) | ✅ |
| `age` | Optional[str] | Optional[str] | ✅ |
| **getKlineIndicators** | | | |
| `intervals_data` 键 | "15", "240", "1440" | "15", "240", "1440" | ✅ |
| `timeframe` | int (15, 240, 1440) | int (15, 240, 1440) | ✅ |
| `rsi_14` | float (calculate_rsi) | float (calculate_rsi) | ✅ |
| `macd_line` | float (calculate_macd) | float (calculate_macd) | ✅ |
| `bollinger_upper` | float (calculate_bollinger) | float (calculate_bollinger) | ✅ |
| `atr_14` | float (calculate_atr) | float (calculate_atr) | ✅ |
| **getAccountInfo** | | | |
| `accountValue` | str (Decimal) | str (Decimal) | ✅ |
| `openOrders` | List[dict] | List[dict] | ✅ |

---

## ✅ 验证方法

### 测试1: 数据结构验证
```python
# 生产模式
prod_news = getTopNews()
prod_kline = getKlineIndicators("BTCUSDT")
prod_account = getAccountInfo()

# 回测模式（T时刻）
backtest_news = getTopNews(before_timestamp=T)
backtest_kline = getKlineIndicators("BTCUSDT", timestamp=T)
backtest_account = getAccountInfo()  # 使用T时刻的账户状态

# 验证：字段名称、类型、结构完全一致
assert type(prod_news[0]["category"]) == type(backtest_news[0]["category"])
assert type(prod_kline["intervals_data"]["15"]["timeframe"]) == type(backtest_kline["intervals_data"]["15"]["timeframe"])
```

### 测试2: 指标计算验证
```python
# 使用相同的历史数据
historical_candles = load_candles("BTCUSDT", start_time, end_time, "15m")

# 生产模式计算
prod_rsi = calculate_rsi([c.close for c in historical_candles])

# 回测模式计算（使用indicators.py）
from VirtualExchange.app.indicators import calculate_rsi
backtest_rsi = calculate_rsi([c.close for c in historical_candles])

# 验证：结果应该完全相同
assert abs(prod_rsi - backtest_rsi) < 0.01
```

---

## 📝 结论

✅ **数据结构完全一致**

- 字段名称一致
- 字段类型一致
- 数据格式一致
- 指标计算逻辑一致

**唯一区别**（设计决定）:
- 时间点不同（生产模式使用当前时间，回测模式使用历史时间点）
- 数据来源不同（生产模式使用实时数据，回测模式使用历史数据）

这些区别是**预期的**，不影响数据结构一致性。

