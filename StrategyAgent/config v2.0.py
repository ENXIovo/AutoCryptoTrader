SYSTEM_MESSAGE = "You are a professional automated trading analysis assistant. Your responsibility is to provide clear and detailed trading analysis and recommendations based on market data, account information, and technical indicators."

FIRST_USER_MESSAGE = """
Please strictly follow the steps below to conduct market trend analysis and provide detailed insights and recommendations:

1. Market Trend Analysis:
   - Multi-timeframe Technical Analysis:
     - Analyze short-term (1-minute, 5-minute, 15-minute) and mid-term (60-minute, 240-minute) trends.
     - If long-term (1440-minute) data is unavailable, infer the long-term trend based on mid-term data.
     - Technical Indicators Analysis (based on quantified thresholds):
       - RSI (Relative Strength Index):
         - Overbought zone (RSI > 70): Be cautious of potential pullbacks.
         - Oversold zone (RSI < 30): Look for rebound signals.
         - Neutral zone (RSI ≈ 50): Confirm direction using other indicators.
       - MACD (Moving Average Convergence Divergence):
         - DIF line crossing above the DEA line with a positive histogram: Bullish signal.
         - DIF line crossing below the DEA line with a negative histogram: Bearish signal.
         - Trend strength: Evaluate momentum changes based on histogram growth or decline.
       - Bollinger Bands:
         - Breaking above the upper band: Possible continuation of an uptrend.
         - Breaking below the lower band: Possible continuation of a downtrend.
         - Expanding band width: Indicates increased market volatility.
       - ATR (Average True Range):
         - High ATR value (greater than 2x the average): Indicates strong market volatility.
         - Low ATR value: Suggests the market may be consolidating.
   - Trend Direction and Consistency:
     - Determine the direction of multi-timeframe trends (upward, downward, or sideways).
     - Assess the consistency between short-term and mid-term trends and analyze potential divergences.
     - Evaluate the reliability of indicator signals and explain potential outcomes.

2. Key Support and Resistance Levels:
   - Identify key support and resistance levels using a combination of order book data and technical indicators:
     - Sources for Support/Resistance Levels:
       - Order book: Areas with high buy/sell order concentrations.
       - Bollinger Bands: Upper and lower bands as potential reversal zones.
       - Historical high/low prices: Mark their significance as high, medium, or low.
     - Provide price ranges for each level and explain their formation (e.g., order book data, Bollinger Band position, etc.).

3. Volatility and Risk Assessment:
   - Use ATR and Bollinger Band width to evaluate market volatility:
     - ATR for Dynamic Stop-Loss/Take-Profit Adjustment:
       - Short-term trades: Set stop-loss at current price ± (1-2x ATR); set take-profit at current price ± (2-3x ATR).
       - Mid-to-long-term trades: Set stop-loss at current price ± (2-5x ATR); set take-profit at current price ± (3-5x ATR).
       - In high-volatility markets (high ATR), widen stop-loss/take-profit ranges; in low-volatility markets, narrow the ranges.
   - High-Volatility Market Recommendations:
     - Confirm trading signals and avoid overly aggressive actions.
     - Adjust order ranges to ATR 50%-100% and reduce position sizes.
   - Indicator Divergence Assessment:
     - When RSI diverges from price trends, assess the likelihood of reversals and provide recommendations.

4. Outputs and Recommendations:
   - Summarize Multi-Timeframe Trend Directions:
     - Short-term trends: Determine current momentum and reversal signals using RSI and MACD.
     - Mid-term trends: Analyze trend consistency and key indicator signals.
   - Provide Actionable Strategies:
     - When the Trend is Clear:
       - Trend-following: Suggest breakout orders 0.5%-1% above/below key levels based on indicator signals.
       - Counter-trend: Consider reversal signals near support/resistance levels and set stop-loss at ATR 50%-100%.
     - In High-Volatility Markets:
       - Dynamic stop-loss/take-profit: Adjust order ranges based on ATR.
       - If the direction is unclear: Reduce position sizes or scale in gradually.
   - Risk Alerts and Countermeasures:
     - High-volatility risks: Monitor significant changes in ATR and Bollinger Band width.
     - Divergence risks: Highlight potential reversals and suggest dynamic position adjustments.
     - Order Recommendations: Prioritize breakout signals at key support/resistance levels and avoid aggressive strategies.
"""

SECOND_USER_MESSAGE = """
1. Account Status Analysis:
   - List the account's available funds (available_usd), funds reserved for open orders (open_order_value), and total funds (total_usd).
   - Calculate the account's liquidity ratio (available funds / total funds) and evaluate whether the liquidity is sufficient (recommended threshold: flag as risky if below 20%).
   - Analyze the profit and loss (P&L) of existing positions:
     - Calculate the unrealized P&L percentage (difference between the current market price and the weighted average cost).
     - If the unrealized P&L reaches a significant level (e.g., >10% profit or <-10% loss), provide recommendations for closing or adjusting the position.
   - Assess the account's overall risk status and provide optimization suggestions based on P&L and liquidity.

2. Order Analysis:
   - Analyze each order individually:
     - Calculate the percentage deviation of the order price from the current market price.
     - Determine whether the order price is near critical support/resistance levels (e.g., Bollinger Band boundaries, ATR range).
   - Provide the following recommendations for order adjustments:
     - Decide whether to hold, modify, or cancel the order.
     - Explain the reasoning for each recommendation (e.g., supported by market trend signals or excessive deviation from current price).

3. Actionable Recommendations:
   - Order Adjustments:
     - For each existing order, specify whether to hold, modify, or cancel it.
     - Use dynamic adjustment logic: set order ranges based on ATR and market volatility (e.g., price ± (ATR × 50%-100%)).
   - New Order Suggestions:
     - MAKE SURE WE HAVE AVAILABLE USDs!!!
     - Provide specific buy or sell strategies, including:
       - Order price ranges (based on critical support/resistance levels, ATR range, or market trend signals).
       - Order volumes (calculated based on available USDs and risk preferences).
     - Introduce dynamic order adjustment logic: use breakout orders when trends are clear, and range-bound orders during uncertain trends.
   - Position Management Suggestions:
     - Based on the account's liquidity ratio, recommend scaling in or out of positions to avoid overexposure to risk.

4. Output Requirements:
   - Natural Language Section:
     - Provide a detailed analysis of account liquidity, position P&L, order status, and market trends, with explanations for each point (at least 200 words).
"""

THIRD_USER_MESSAGE = """
Based on the current market data and account information, generate a structured JSON output that meets the following requirements:

1. Structure and Order Requirements:
   - The JSON output must include the following key sections:
     1. Market Analysis (market_analysis): Summarize short-term, mid-term, and long-term market trends, including key price levels, volatility, and analysis summaries.
     2. Order Recommendations (recommendations):
        - Existing Order Adjustments (orders): Provide adjustment suggestions for each order, including action type, stop-loss/take-profit settings, and logical reasoning.
        - New Order Suggestions (new_orders): Propose new order strategies, including price ranges, trigger conditions, and risk assessments.

2. Market Analysis (market_analysis):
   - Generate market analysis for short-term, mid-term, and long-term trends using the following format:
     ```json
     "market_analysis": {
         "short_term": {
             "trend": "Short-term market trend direction (e.g., upward, sideways, downward)",
             "key_levels": {
                 "support": "Support price level (calculated using ATR or order book data)",
                 "resistance": "Resistance price level (calculated using historical highs or Bollinger Bands)"
             },
             "volatility": {
                 "atr": "Short-term ATR value",
                 "bollinger_band_width": "Bollinger Band width, used to measure short-term volatility"
             },
             "summary": "Short-term market summary, including trend direction, volatility, and key actionable zones"
         },
         "mid_term": { ... },
         "long_term": { ... }
     }
     ```
   - Notes:
     - The calculation of support/resistance levels can integrate order book concentration zones, Bollinger Band boundaries, and historical price levels.
     - Use the ATR value in the volatility field to dynamically adjust order ranges, and Bollinger Band width to assess market activity.

3. Order Recommendations (recommendations):
   - Existing Order Adjustments (orders):
     - Provide the following details for each order:
       ```json
       {
           "order_id": "Unique order identifier",
           "pair": "Trading pair name",
           "type": "buy or sell",
           "price": "Current order price",
           "volume": "Order volume",
           "action": "hold / cancel / modify",
           "reasoning": "Logical basis for the suggested adjustment",
           "stop_loss": "Stop-loss price (dynamic setting: short-term = 1-2x ATR; mid-to-long-term = 2-5x ATR)",
           "take_profit": "Take-profit price (dynamic setting: short-term = 2-3x ATR; mid-to-long-term = 3-5x ATR)"
       }
       ```
     - Explain the reasoning behind each adjustment, such as alignment with trends, proximity to key price levels, or changes in volatility.

   - New Order Suggestions (new_orders):
     - Provide specific suggestions for new orders using the following format:
       ```json
       {
           "pair": "Trading pair name",
           "type": "buy or sell",
           "price": "Order price (may be dynamically adjusted based on trends and volatility)",
           "volume": "Order volume (calculated based on available funds and risk preferences)",
           "action": "create",
           "reasoning": "Logical basis for the new order (e.g., breakout signal or support rebound)",
           "condition": "Trigger conditions (e.g., RSI overbought/oversold, or price breaking support/resistance levels)",
           "stop_loss": "Stop-loss price (dynamic setting below support or based on ATR range)",
           "take_profit": "Take-profit price (dynamic setting above resistance or based on ATR range)",
           "risk_assessment": {
               "risk_level": "low / medium / high",
               "atr_range": "ATR range, used for dynamic order adjustment",
               "estimated_drawdown": "Estimated drawdown percentage"
           },
           "expiry_time": "Order validity period (e.g., 24 hours or other durations)",
           "dynamic_price_range": "Dynamic price range (e.g., ±10% of ATR)"
       }
       ```

4. Logic and Dynamic Adjustments:
   - Dynamic Order Adjustments:
     - Ensure that order ranges are linked to market volatility, e.g., set order prices at support/resistance ± (ATR × 50%-100%).
     - Dynamic stop-loss and take-profit settings:
       - Short-term trades: Stop-loss = current price - (1-2x ATR); Take-profit = current price + (2-3x ATR).
       - Mid-to-long-term trades: Stop-loss = current price - (2-5x ATR); Take-profit = current price + (3-5x ATR).
   - Risk Control:
     - Evaluate the risk level of each order based on account liquidity, unrealized P&L, and market volatility, and limit the risk exposure for individual orders.

5. Output Notes:
   - Clear Structure: Start with market analysis, followed by order adjustments, and finally new order suggestions.
   - Concise Explanations: Logical reasoning should be clear but not overly verbose; JSON field content should be concise.
   - Error Handling: If data is insufficient (e.g., long-term trend data is missing), indicate "N/A" or "insufficient data" in the fields.
"""
