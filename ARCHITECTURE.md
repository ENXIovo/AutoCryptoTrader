# 双系统架构说明

## 概述

系统采用**双系统架构**，完全解耦回测和实盘：

- **VirtualExchange** (端口 8100): 回测系统，非实时撮合，基于历史K线数据
- **HyperliquidExchange** (端口 8200): 实盘系统，完全代理 Hyperliquid API

Strategy Agent 通过 `TRADING_URL` 配置切换，代码无需修改。

---

## 目录结构

```
AutoCryptoTrader/
├── VirtualExchange/          # 回测系统
│   ├── app/
│   │   ├── config.py         # 配置（无外部API依赖）
│   │   ├── models.py         # 数据模型
│   │   ├── matching_engine.py  # 非实时撮合引擎
│   │   ├── wallet.py         # 简单钱包管理
│   │   ├── data_loader.py    # M2数据加载器
│   │   ├── backtest_runner.py # 回测运行器
│   │   └── main.py           # FastAPI（交易接口 + 数据Mock）
│   ├── docker-compose.yml
│   └── requirements.txt
│
└── HyperliquidExchange/      # 实盘系统
    ├── app/
    │   ├── config.py         # Hyperliquid配置
    │   ├── models.py         # 数据模型
    │   ├── hyperliquid_client.py  # SDK封装
    │   ├── exchange.py      # 代理层
    │   └── main.py          # FastAPI（纯代理）
    ├── docker-compose.yml
    └── requirements.txt
```

---

## VirtualExchange（回测系统）

### 核心组件

1. **MatchingEngine** (`matching_engine.py`)
   - 非实时撮合引擎
   - 基于1分钟K线数据
   - 支持市价单、限价单、TPSL订单
   - OCO逻辑：TPSL触发时自动取消对侧订单

2. **Wallet** (`wallet.py`)
   - 简单钱包管理
   - 单账本余额跟踪
   - 订单扣款/退款（立即执行）
   - 持仓管理

3. **DataLoader** (`data_loader.py`)
   - 从M2 DataStore加载历史K线数据
   - 支持Parquet/CSV格式
   - 按日期分区读取

4. **BacktestRunner** (`backtest_runner.py`)
   - 回测运行器
   - 加载历史数据
   - 按时间轴加速执行
   - 生成回测报告

### API接口

#### 交易接口（与HyperliquidExchange保持一致）

- `POST /exchange/order` - 下单
- `POST /exchange/cancel` - 取消订单
- `POST /exchange/modify` - 修改订单
- `POST /info` - 账户信息

#### 数据Mock接口（Mock DataCollector）

- `GET /gpt-latest/{symbol}` - 返回当前回测时间点的历史数据

**关键设计**：VirtualExchange 不仅模拟交易接口，还模拟数据查询接口。Strategy Agent 的 `DATA_SERVICE_URL` 在回测时也指向 VirtualExchange，实现"时间旅行"。

#### 回测接口（可选）

- `POST /backtest/run` - 手动触发回测

---

## HyperliquidExchange（实盘系统）

### 核心组件

1. **HyperliquidClient** (`hyperliquid_client.py`)
   - Hyperliquid SDK 封装
   - 提供 Info 和 Exchange 客户端

2. **OrderManager** (`exchange.py`)
   - 纯代理层
   - 无本地缓存
   - 直接转发到 Hyperliquid API

### API接口

- `POST /exchange/order` - 下单（代理Hyperliquid）
- `POST /exchange/cancel` - 取消订单（代理Hyperliquid）
- `POST /exchange/modify` - 修改订单（代理Hyperliquid）
- `POST /info` - 账户信息（代理Hyperliquid）
- `POST /exchange/leverage` - 设置杠杆
- `POST /exchange/isolated-margin` - 调整隔离保证金

---

## 配置切换

### Strategy Agent 配置

在 `.env` 文件中设置 `TRADING_URL`：

```bash
# 回测模式
TRADING_URL=http://virtual-exchange:8100
DATA_SERVICE_URL=http://virtual-exchange:8100

# 实盘模式
TRADING_URL=http://hyperliquid-exchange:8200
DATA_SERVICE_URL=http://data-collector:8000
```

---

## 回测流程

1. **Strategy Meeting 结束**
   - 提取挂单列表（JSON格式）

2. **加载历史数据**
   - BacktestRunner 从 M2 DataStore 加载历史K线

3. **按时间轴加速执行**
   - 几分钟跑完几天的数据
   - 每根K线检查订单匹配
   - 市价单：在Close价格成交
   - 限价单：如果价格在Low-High范围内成交
   - TPSL：检查触发条件

4. **生成回测报告**
   - PnL、胜率、回撤、权益曲线

---

## 关键设计决策

### 1. 统一接口（Interface-based Strategy Pattern）

两个系统提供相同的API接口，Strategy Agent 无需修改代码，只需切换配置。

### 2. 时间旅行问题解决

VirtualExchange 不仅模拟交易接口，还模拟数据查询接口。Strategy Agent 在回测时从 VirtualExchange 获取历史数据，而不是从 DataCollector 获取实时数据。

### 3. 非实时撮合

VirtualExchange 使用非实时撮合，基于历史K线数据，完全可控，避免实时撮合的可靠性问题。

### 4. 无Redis依赖（回测系统）

回测是一次性进程，所有状态保存在内存中，无需Redis持久化。

---

## 部署

### VirtualExchange

```bash
cd VirtualExchange
docker-compose up -d
```

### HyperliquidExchange

```bash
cd HyperliquidExchange
docker-compose up -d
```

---

## 下一步

1. **M2 DataStore 实现**：需要实现历史K线数据的Parquet/CSV存储
2. **回测报告可视化**：创建独立的Jupyter Notebook或脚本，用matplotlib画出资金曲线
3. **回测自动化**：实现会议结束后自动触发回测的功能

