# AutoCryptoTrader (ACT)
**GPT-Powered Cryptocurrency Market Analyzer**  
*Real-time market trend analysis using K-line data and GPT-based sentiment modeling*  

[![GitHub license](https://img.shields.io/badge/Stage-Active--Dev-blueviolet)]()  
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)  
[![Powered By](https://img.shields.io/badge/LLM-GPT4o-FF6C37)](https://platform.openai.com/docs)  

---

## 🔍 Project Overview

AutoCryptoTrader is an intelligent trading assistant designed to analyze real-time cryptocurrency market data and provide GPT-based trading insights. The system fetches K-line (candlestick) data from major exchanges, applies trend analysis, and (in progress) integrates financial news to assist with risk-aware decision-making.

---

## 🧩 System Components

### 1. Real-Time Market Data Pipeline 📉  
- Fetches K-line data from multiple exchanges (e.g., Binance, Kraken) using CCXT or REST/WebSocket APIs  
- Stores structured time series in a PostgreSQL-compatible TSDB (TimescaleDB)  
- Cleans and aligns multivariate time frames for multi-window analysis  

### 2. Price Trend Analyzer 📈  
- Calculates technical indicators (e.g., RSI, MACD, Bollinger Bands)  
- Identifies trend reversals and volatility regions  
- Output used as one decision input for GPT  

### 3. GPT-Based Sentiment Reasoner 🧠 *(In Progress)*  
- (Planned) Collects and summarizes financial news from major outlets  
- GPT-4 performs sentiment scoring and keyword-based reasoning  
- Results will be combined with market indicators for holistic analysis  

### 4. Decision Output (In Planning)  
- Merges quantitative trends + qualitative sentiment  
- Risk thresholding for "hold / buy / sell" signal  
- Future plan: integrate trade execution backend via API sandbox

---

## 🛠 Tech Stack

- **Python 3.10+**, Pandas, TA-Lib  
- **CCXT / WebSocket APIs** for market data  
- **PostgreSQL + TimescaleDB** for time series storage  
- **OpenAI GPT-4 API** for reasoning + summarization (WIP)  
- **LangChain** used for structured prompting and sentiment synthesis  

---

## 🗺️ Roadmap

| Feature                         | Status       |
|---------------------------------|--------------|
| Market Data Ingestion           | ✅ Complete  |
| Technical Analysis Module       | ✅ Complete  |
| News Crawling + GPT Summary     | 🔄 In Dev    |
| Combined Trade Decision Logic   | ⏳ In Planning |
| Automated Execution API         | 💡 Proposed  |

---

## ⚠️ Disclaimer

*This project is in active development. Trading signals are for research purposes only and not financial advice.*

---

## 👨‍💻 Author

Haoyang Yin  
MSCS @ Boston University  
Email: yinhaoya@bu.edu  
