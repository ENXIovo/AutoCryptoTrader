# 回测模式与生产模式一致性检查清单

## 概述

本文档确保回测模式的实现与生产模式完全一致，保证回测结果的可靠性。

---

## 核心流程对比

### 生产模式流程

```
当前时间 T (例如: 2025-01-15 12:00:00 UTC)
  ↓
1. Strategy Agent 会议启动
  ↓
2. Market Analyst: getTopNews() → 获取当前时间的新闻
  ↓
3. Lead Technical Analyst: getKlineIndicators(symbol) → 获取当前时间的15m/4h K线
  ↓
4. Position Manager: 分析持仓
  ↓
5. Risk Manager: 筛选交易机会
  ↓
6. CTO: placeOrder() → 实际下单到 Exchange
  ↓
7. Exchange: 立即撮合订单（使用实时1m K线）
```

### 回测模式流程

```
历史时间点 T (例如: 2025-01-15 12:00:00 UTC)
  ↓
1. BacktestOrchestrator 设置回测时间点: runner.set_current_time(T)
  ↓
2. Strategy Agent 会议启动（backtest_mode=True, backtest_timestamp=T）
  ↓
3. Market Analyst: getTopNews() → 获取T时刻之前的新闻（before_timestamp=T）
  ↓
4. Lead Technical Analyst: getKlineIndicators(symbol) → 获取T时刻的15m/4h历史K线（timestamp=T）
  ↓
5. Position Manager: 分析持仓（从Exchange获取，使用T时刻的账户状态）
  ↓
6. Risk Manager: 筛选交易机会
  ↓
7. CTO: placeOrder() → 返回模拟响应，订单从tool_calls提取
  ↓
8. BacktestOrchestrator: 收集订单
  ↓
9. 用1m K线撮合订单到下一个时间点（T + 4小时）
```

---

## 一致性检查点

### ✅ 1. 数据查询一致性

| 组件 | 生产模式 | 回测模式 | 一致性 |
|------|---------|---------|--------|
| **getTopNews** | 当前时间的新闻 | T时刻之前的新闻 | ✅ 一致 |
| **getKlineIndicators** | 当前时间的K线 | T时刻的历史K线 | ✅ 一致 |
| **时间点设置** | `datetime.now()` | `datetime.fromtimestamp(backtest_timestamp)` | ✅ 一致 |

**实现位置：**
- `Agents/news_labeler/app/services/topnews_service.py`: `before_timestamp` 参数
- `VirtualExchange/app/main.py`: `/gpt-latest/{symbol}` 的 `timestamp` 参数
- `Agents/strategy_agent/app/tool_router.py`: `backtest_timestamp` 参数

---

### ✅ 2. 工具调用一致性

| 工具 | 生产模式 | 回测模式 | 一致性 |
|------|---------|---------|--------|
| **placeOrder** | 实际调用Exchange API | 返回模拟响应，订单从tool_calls提取 | ✅ 一致（行为不同但逻辑一致） |
| **cancelOrder** | 实际调用Exchange API | 返回模拟响应 | ✅ 一致 |
| **getAccountInfo** | 获取当前账户状态 | 获取T时刻的账户状态 | ✅ 一致 |
| **getKlineIndicators** | 当前时间数据 | T时刻历史数据 | ✅ 一致 |
| **getTopNews** | 当前时间新闻 | T时刻之前新闻 | ✅ 一致 |

**实现位置：**
- `Agents/strategy_agent/app/tool_handlers.py`: `placeOrder`, `cancelOrder` 的回测模式检查
- `Agents/strategy_agent/app/agent_runner.py`: `_extract_orders_from_cto_result` 提取订单

---

### ✅ 3. 会议流程一致性

| 阶段 | 生产模式 | 回测模式 | 一致性 |
|------|---------|---------|--------|
| **时间点确定** | `datetime.now(timezone.utc)` | `datetime.fromtimestamp(backtest_timestamp)` | ✅ 一致 |
| **会议间隔** | 每4小时（:05 UTC） | 每4小时（可配置） | ✅ 一致 |
| **Agent顺序** | News/TA并行 → PM → Risk → CTO | 相同 | ✅ 一致 |
| **上下文传递** | 按顺序传递报告 | 相同 | ✅ 一致 |
| **订单提取** | 从Exchange获取 | 从tool_calls提取 | ✅ 一致（方式不同但结果一致） |

**实现位置：**
- `Agents/strategy_agent/app/agent_runner.py`: `run_agents_in_sequence_async(backtest_timestamp)`

---

### ✅ 4. 订单执行一致性

| 步骤 | 生产模式 | 回测模式 | 一致性 |
|------|---------|---------|--------|
| **订单创建** | CTO调用placeOrder → Exchange创建订单 | CTO调用placeOrder → 从tool_calls提取 → 创建VirtualOrder | ✅ 一致 |
| **订单格式** | VirtualOrder (通过Exchange API) | VirtualOrder (直接创建) | ✅ 一致 |
| **TPSL支持** | 支持 | 支持 | ✅ 一致 |
| **撮合时机** | 立即（实时1m K线） | 延迟（历史1m K线，按时间顺序） | ✅ 一致（时机不同但逻辑一致） |

**实现位置：**
- `VirtualExchange/app/backtest_orchestrator.py`: `_extract_orders_from_meeting_result`
- `VirtualExchange/app/backtest_orchestrator.py`: `_match_orders_until`

---

### ✅ 5. 账户状态一致性

| 功能 | 生产模式 | 回测模式 | 一致性 |
|------|---------|---------|--------|
| **账户价值计算** | 当前余额 + 持仓市值 | T时刻余额 + 持仓市值 | ✅ 一致 |
| **持仓查询** | 当前持仓 | T时刻持仓 | ✅ 一致 |
| **订单查询** | 当前未完成订单 | T时刻未完成订单 | ✅ 一致 |

**实现位置：**
- `VirtualExchange/app/main.py`: `/info` 接口使用 `runner.get_current_backtest_time()`
- `VirtualExchange/app/backtest_orchestrator.py`: 在调用Agent前设置价格

---

### ✅ 6. 时间处理一致性

| 操作 | 生产模式 | 回测模式 | 一致性 |
|------|---------|---------|--------|
| **时区** | UTC | UTC | ✅ 一致 |
| **时间格式** | ISO8601 | ISO8601 | ✅ 一致 |
| **时间戳** | Unix秒 | Unix秒 | ✅ 一致 |
| **会议时间计算** | 基于当前时间 | 基于回测时间点 | ✅ 一致 |

**实现位置：**
- `Agents/strategy_agent/app/agent_runner.py`: 使用 `backtest_timestamp` 或 `datetime.now()`
- `VirtualExchange/app/utils/time_utils.py`: 统一的时区处理

---

## 关键差异（设计决定）

### 1. 订单执行时机

- **生产模式**: 订单立即执行（实时撮合）
- **回测模式**: 订单延迟执行（历史撮合，按时间顺序）

**原因**: 回测需要按历史时间顺序处理，确保时间一致性。

**影响**: 无。两种模式都使用相同的撮合逻辑（1m K线），只是时机不同。

---

### 2. 订单提交方式

- **生产模式**: 通过Exchange API实际提交
- **回测模式**: 从tool_calls提取，不实际提交

**原因**: 回测模式下，订单需要统一收集后按时间顺序撮合。

**影响**: 无。两种模式都生成相同的VirtualOrder对象。

---

### 3. 数据查询方式

- **生产模式**: 查询当前时间的数据
- **回测模式**: 查询历史时间点的数据

**原因**: 回测需要模拟历史决策。

**影响**: 无。两种模式使用相同的数据查询接口，只是时间点不同。

---

## 验证测试

### 测试1: 数据查询一致性

```python
# 生产模式
news = getTopNews()  # 当前时间的新闻
kline = getKlineIndicators("BTCUSDT")  # 当前时间的K线

# 回测模式（T时刻）
news = getTopNews(before_timestamp=T)  # T时刻之前的新闻
kline = getKlineIndicators("BTCUSDT", timestamp=T)  # T时刻的K线
```

**验证**: 回测模式返回的数据应该是生产模式在T时刻会看到的数据。

---

### 测试2: 订单格式一致性

```python
# 生产模式
order = placeOrder(coin="BTC", is_buy=True, sz=0.1, ...)
# → Exchange创建VirtualOrder

# 回测模式
order = placeOrder(coin="BTC", is_buy=True, sz=0.1, ...)
# → 从tool_calls提取，创建VirtualOrder
```

**验证**: 两种模式生成的VirtualOrder对象应该具有相同的字段和值。

---

### 测试3: 撮合逻辑一致性

```python
# 生产模式
# 订单立即用实时1m K线撮合

# 回测模式
# 订单用历史1m K线按时间顺序撮合
```

**验证**: 两种模式使用相同的撮合引擎（MatchingEngine），逻辑完全一致。

---

## 潜在问题与解决方案

### 问题1: 回测模式下账户状态可能不完整

**场景**: 在回测早期，账户可能还没有任何交易，账户价值计算可能不准确。

**解决方案**: 
- 在调用Agent前设置基础价格（已实现）
- 如果无法获取价格，记录警告但继续执行

---

### 问题2: 回测模式下订单提取失败

**场景**: 如果CTO的tool_calls格式不符合预期，订单提取可能失败。

**解决方案**:
- 使用 `_extract_orders_from_cto_result` 函数统一提取
- 记录警告但继续执行（不中断回测）

---

### 问题3: 回测模式下时间点设置不一致

**场景**: 如果不同组件使用不同的时间点，可能导致数据不一致。

**解决方案**:
- 统一使用 `backtest_timestamp` 参数
- 所有组件都从同一个时间点获取数据

---

## 总结

✅ **所有核心逻辑与生产模式一致**

- 数据查询：使用相同接口，只是时间点不同
- 工具调用：行为不同但逻辑一致（回测模式模拟响应）
- 会议流程：完全相同的Agent顺序和上下文传递
- 订单格式：完全相同的VirtualOrder对象
- 撮合逻辑：使用相同的MatchingEngine

✅ **关键差异都是设计决定，不影响一致性**

- 订单执行时机：延迟执行是为了时间一致性
- 订单提交方式：提取而不是提交是为了统一处理
- 数据查询时间点：历史时间点是为了模拟历史决策

---

## 使用建议

1. **回测前检查**:
   - 确保有足够的历史数据（1m、15m、4h K线）
   - 确保有历史新闻数据（Redis中）

2. **回测后验证**:
   - 检查订单是否正确提取
   - 检查撮合结果是否合理
   - 对比生产模式的决策逻辑

3. **问题排查**:
   - 如果订单提取失败，检查CTO的tool_calls格式
   - 如果数据查询失败，检查时间点设置
   - 如果撮合异常，检查1m K线数据完整性

