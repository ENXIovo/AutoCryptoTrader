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

**Design Philosophy (V1 Simplified):**
- **K-Line Matching:** Matches orders based on **1-minute OHLC** data instead of tick-level data. If `Low <= Buy Price` in a minute, it fills. This unifies logic for both Live Trading and Backtesting.
- **Simple Wallet:** Single-ledger balance tracking. Orders deduct funds immediately; Cancels refund immediately. No complex freeze/unfreeze logic.
- **Snapshot Persistence:** State is saved as a single JSON snapshot to Redis on every change, ensuring simple disaster recovery.

**Acceptance Criteria:**
- **Entities:** Strongly typed `VirtualOrder`, `VirtualPosition`, `VirtualTrade` (supporting Market/Limit orders).
- **Matching:** Consumes 1m OHLC from DataCollector. Market orders fill at Close; Limit orders fill if Price is within Low-High range.
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

**Goal:** Quantitatively validate a specific strategy using historical data to obtain Win Rate, R/R, and Drawdown metrics. **Enable perfect historical reproduction of any strategy/signal/meeting conclusion for stable evaluation and review.**

**Why Priority:** This directly addresses the core pain point—"lots of discussion, unclear direction, afraid to refactor"—by providing a stable "trial-and-error channel" for strategy validation.

**Implementation Plan (Three Stages):**

#### Stage A: M3 Backtest V0 Foundation (Current Focus)
**Objective:** Any strategy/signal/meeting conclusion can be stably reproduced and evaluated on offline historical data.

**A1. Minimal Complete Backtest Report**
- **Trade-level metrics:**
  - Entry/exit time, quantity, fees, slippage, PnL, R-multiple per trade
- **Portfolio-level metrics:**
  - Equity curve (per bar)
  - Max drawdown / MDD duration
  - Win rate / avg win / avg loss / profit factor
  - Exposure (time occupancy), turnover
- **Reproducibility metadata:**
  - Data hash (version of candles/news)
  - Strategy config (parameter snapshot)
  - Engine version (git commit)

**A2. Visualization (Minimal but Usable)**
Three essential charts for 90% of decision-making:
- Equity curve + drawdown area
- Trades on price (entry/exit markers)
- PnL distribution (histogram or box plot)

**Output format:**
- `reports/{run_id}.json`
- `reports/{run_id}.png` (or multiple charts)

**A3. Backtest Accuracy Validation (Critical)**
Three validation tests:
- **Matching consistency test:** Given fixed K-line sequence + fixed order sequence, matching results must be deterministic.
- **PnL and fee reconciliation:** Manually construct 2-3 trades, calculated results must match exactly.
- **Backtest reproducibility:** Same `run_id` (same data hash + config) repeated runs produce bit-identical output (at least consistent metrics).

**Stage A Acceptance:** Can run any strategy config to produce "3 charts + JSON report + reproducible run_id".

#### Stage B: Validate/Align M1 (Unify "Offline/Live Semantics")
**Objective:** VirtualExchange and HyperliquidExchange have consistent behavioral semantics, enabling seamless strategy switching between "backtest → paper/live trading".

**B1. Define Exchange Contract (Text + Tests)**
Create `exchange_contract.md` documenting:
- Order state machine (NEW → PARTIAL → FILLED → CANCELED ...)
- Stop/TP/SL trigger basis (last? mark? index?)
- Fee model (maker/taker)
- Slippage model (how to simulate in virtual?)
- Time granularity principles (conservative/aggressive assumptions for 1m OHLC matching)

**B2. Align Both Engines with Synthetic Scenarios**
Create 10 scenarios, e.g.:
- Can limit orders fill in trending one-way markets?
- Will stops slip through gaps/jumps?
- Priority of multiple triggers in same bar
- FIFO & reduceOnly behavior

Run VirtualExchange and Hyperliquid (sandbox/mock) through same scenarios, compare event logs for consistency.

**Stage B Acceptance:** Guarantee "same strategy has consistent semantics in backtest vs paper/live trading", differences are explainable and configurable.

#### Stage C: M4 Meeting Lab V0 (Minimal Viable Lab)
**Objective:** Begin rolling discussion + interruptible + multi-model workflow, leveraging Stage A/B benefits for reviewable and calibratable conclusions.

**C1. Information Layer Memo Generator (Non-interruptible)**
- **Input:** Current market snapshot (price/volatility/positions/recent news top-k) + historical snapshot (last memo/decision)
- **Output:** `memo/{t}.json` (facts/signals/unknowns)
- Each agent outputs memo fragments, orchestrator merges and deduplicates.

**C2. Discussion Layer Adversarial System (Interruptible)**
- **Minimal implementation:** 3 roles (MA, LTA, RM), CTO responsible for convergence
- Interrupt budget + interrupt types (Clarify / Counterevidence / Reframe / Veto-to-Revise)

**C3. Review Loop (Immediately Connect to M3)**
Each discussion outputs:
- `decision/{t}.json`: Conclusion (main path/backup path), confidence, trigger conditions, corresponding strategy config id (if any)
- After future window (e.g., 3d/7d/30d), automatically run backtest comparison, write outcome back.

**Stage C Acceptance:** Clear chain visible: Event trigger → memo → debate → decision → backtest/live outcome → review weight update.

**Original Acceptance Criteria (Baseline):**
- **Inputs:** Symbol, Timeframe, Range, Strategy Config (Entry/SL/TP logic).
- **Logic:** Reuses M1 matching logic for simulation accuracy.
- **Execution:** Checks logic per K-line (Entry condition? SL hit? TP hit?).
- **Output:** Report generating Total PnL, # Trades, Win Rate, Max Drawdown, and an Equity Curve plot.
- **Reproducibility:** Same data + same parameters = identical result.

### 🧪 M4: Meeting Lab V0 (Adversarial Agent Experiment)
**Pipeline:** `Historical Snapshot` → `Meeting Lab (Debate)` → `Trade Ideas` → `Backtest V0` → `Review Loop`

**Goal:** Experiment with "Adversarial Agent" workflows (e.g., "Debate Intensity") using historical data to optimize decision quality without production risk. **Enable rolling discussion with interruptible multi-model debates, connected to M3 for automatic outcome review.**

**Implementation Plan (See M3 Stage C):**

**C1. Information Layer Memo Generator (Non-interruptible)**
- **Input:** Current market snapshot (price/volatility/positions/recent news top-k) + historical snapshot (last memo/decision)
- **Output:** `memo/{t}.json` (facts/signals/unknowns)
- Each agent outputs memo fragments; orchestrator merges and deduplicates.

**C2. Discussion Layer Adversarial System (Interruptible)**
- **Minimal implementation:** 3 roles (MA, LTA, RM), CTO responsible for convergence
- Interrupt budget + interrupt types (Clarify / Counterevidence / Reframe / Veto-to-Revise)

**C3. Review Loop (Immediately Connect to M3)**
- Each discussion outputs `decision/{t}.json`: Conclusion (main path/backup path), confidence, trigger conditions, corresponding strategy config id (if any)
- After future window (e.g., 3d/7d/30d), automatically run backtest comparison, write outcome back.

**Acceptance Criteria:**
- **Input:** Fixed context window (Price + News) from a specific historical point.
- **Config:** Adjustable roles (Bull/Bear/Risk) and debate rounds.
- **Output:** JSON Schema: `Action` (Buy/Sell/Hold), `Entry`, `SL`, `TP`, `Confidence Score`.
- **Validation:** Run simulation over a historical week -> Feed decisions to Backtest V0 -> Generate PnL report.
- **Isolation:** Runs offline; no interaction with production Redis or Orders.
- **Review Chain:** Clear chain visible: Event trigger → memo → debate → decision → backtest/live outcome → review weight update.

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