# AutoCryptoTrader (ACT)
**GPT-Powered Cryptocurrency Market Analyzer & Virtual Trading System** *Real-time market trend analysis using K-line data and GPT-based sentiment modeling* [![GitHub license](https://img.shields.io/badge/Stage-Active--Dev-blueviolet)]()  
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)  
[![Powered By](https://img.shields.io/badge/LLM-GPT4o-FF6C37)](https://platform.openai.com/docs)  

---

## 🔍 Project Overview

AutoCryptoTrader is a multi-service, GPT-powered quantitative assistant designed to automate the full lifecycle of trading analysis:
- **Data Ingestion:** Collects real-time ticker/K-line data and crypto news via Telegram.
- **Decision Making:** Runs a structured, multi-agent "Strategy Meeting" (Market Analyst, Risk Manager, CTO).
- **Execution:** Executes trades via a proprietary **Virtual Trading Engine (V1)**.

**Why Virtual V1?** To eliminate execution risks associated with live exchanges (e.g., API instability, slippage) during the strategy validation phase. This pivot allows us to validate workflows, latency, and agent reliability in a controlled, risk-free environment before bridging to live venues (e.g., Hyperliquid) in V2.

---

## 🧩 System Architecture

- **DataCollector:** Centralized service providing K-line indicators and `last_price` endpoints.
- **News Intelligence:**
    - *Collector:* Ingests raw feeds from Telegram channels.
    - *Labeler:* Uses LLM & heuristics to tag, categorize, and score news for importance.
- **Strategy Agent:** Orchestrates multi-agent debates (Market/TA/PM/Risk/CTO) using LangGraph/LLM tool routing.
- **Virtual Trading Engine (V1):** A standalone Order Management System (OMS) supporting market/limit orders and PnL tracking via Redis Streams.
- **Redis:** Acts as the nervous system for coordination, event streaming, and caching.

*> Note: Execution is fully decoupled from Kraken. Legacy Kraken client and WebSocket listeners have been removed for Core V1 stability.*

---

## 🗺️ Development Roadmap (Core V1)

*Each milestone is defined by a Data Pipeline, a Quantifiable Goal, and strict Acceptance Criteria.*

### ✅ M0: News Alert V1 (Current Priority)
**Pipeline:** `Telegram` → `Collector` → `Redis (Raw)` → `Labeler (LLM)` → `Redis (Structured)` → `Alert Service` → `Mobile Notification`

**Goal:** Receive a concise alert for high-importance news on mobile within **5 minutes** of publication.

**Acceptance Criteria:**
- **Stability:** Reliably monitors 3–5 designated Telegram channels; raw streams verified via timestamp/channel_id.
- **Labeling:** Every structured message contains `category`, `importance_score`, `source`, `symbol`, and `summary`.
- **Delivery:** A standalone `news_alert_service` filters the stream (e.g., `importance >= 0.7`) and pushes to Mobile (Telegram Bot/Discord).
- **Latency:** Verified < 5 min latency for 3 test cases. Alert includes: "One-sentence summary + Symbol + Rating (⭐⭐⭐)".
- **Observability:** A script/dashboard exists to query the last N pushed alerts from Redis.

### 🧱 M1: Virtual Trading Engine V1
**Pipeline:** `Strategy Meeting` / `Manual Input` → `TradePlan JSON` → `Virtual Order Engine` → `Virtual Ledger`

**Goal:** Full Order Management System (OMS) capabilities (Open/Modify/Cancel/Position Tracking) without external API dependencies.

**Acceptance Criteria:**
- **Entities:** Strongly typed `VirtualOrder`, `VirtualPosition`, `VirtualTrade` (supporting Market/Limit orders).
- **Matching:** Consumes real-time `last_price`. Market orders fill immediately; Limit orders fill upon price crossing.
- **Operations:** Support via HTTP/CLI for: Place Order, Modify Price/Qty, Cancel Order.
- **Decoupling:** Engine operates independently of any exchange API keys.
- **Validation:** A standard test sequence (Up/Chop/Down market simulation) results in Virtual PnL matching expected calculation.

### 📦 M2: DataStore V0 (Cold Storage)
**Pipeline:** `Real-time Stream` → `Data Writer` → `Local Files (Parquet/CSV)`

**Goal:** Enable offline backtesting and replay by persisting K-lines and News to local storage, removing reliance on Redis ephemeral cache.

**Acceptance Criteria:**
- **Candles:** Daily partitioning (e.g., `data/candles/BTCUSDT_5m/2025-11-16.parquet`) containing OHLCV.
- **News:** Daily partitioning of structured news objects.
- **Access API:** Python utility `load_candles(symbol, timeframe, start, end)` and `load_news(...)`.
- **Reliability:** Writer service runs >24h without failure.

### 📊 M3: Backtest V0 (Single-Asset/Single-Strategy)
**Pipeline:** `Historical Data (M2)` → `Backtest Engine` → `Virtual Matching (M1)` → `Performance Report`

**Goal:** Quantitatively validate a specific strategy using historical data to obtain Win Rate, R/R, and Drawdown metrics.

**Acceptance Criteria:**
- **Inputs:** Symbol, Timeframe, Range, Strategy Config (Entry/SL/TP logic).
- **Logic:** Reuses M1 matching logic for simulation accuracy.
- **Execution:** Checks logic per K-line (Entry condition? SL hit? TP hit?).
- **Output:** Report generating Total PnL, # Trades, Win Rate, Max Drawdown, and an Equity Curve plot.
- **Reproducibility:** Same data + same parameters = identical result.

### 🧪 M4: Meeting Lab V0 (Adversarial Agent Experiment)
**Pipeline:** `Historical Snapshot` → `Meeting Lab (Debate)` → `Trade Ideas` → `Backtest V0`

**Goal:** Experiment with "Adversarial Agent" workflows (e.g., "Debate Intensity") using historical data to optimize decision quality without production risk.

**Acceptance Criteria:**
- **Input:** Fixed context window (Price + News) from a specific historical point.
- **Config:** Adjustable roles (Bull/Bear/Risk) and debate rounds.
- **Output:** JSON Schema: `Action` (Buy/Sell/Hold), `Entry`, `SL`, `TP`, `Confidence Score`.
- **Validation:** Run simulation over a historical week -> Feed decisions to Backtest V0 -> Generate PnL report.
- **Isolation:** Runs offline; no interaction with production Redis or Orders.

---

## 🛠 Tech Stack

- **Core:** Python 3.10+, Pydantic, FastAPI, Celery
- **Data & Eventing:** Redis Streams (Message Bus), Parquet (Storage)
- **Networking:** httpx (Async HTTP)
- **AI:** GPT-4o via Proxy Service, LangGraph (planned)

---

## ⚠️ Disclaimer

*This project is in active development. Trading signals and virtual performance metrics are for research purposes only and do not constitute financial advice.*

---

## 👨‍💻 Author

**Haoyang Yin** MSCS @ Boston University  
Email: yinhaoya@bu.edu