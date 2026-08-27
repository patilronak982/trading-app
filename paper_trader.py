"""=============================================================================
ENTERPRISE PAPER TRADING & MARKET SIMULATION ENGINE
=============================================================================
Dependencies: yfinance, pandas, numpy
Author: Production Engineering Spec
Target: Python 3.10+
============================================================================="""

from dataclasses import dataclass, field
import datetime
from enum import Enum
import json
import logging
import math
import os
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import yfinance as yf

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler("paper_trader.log"), logging.StreamHandler()],
)
logger = logging.getLogger("PaperTraderEngine")


# =============================================================================
# DATA STRUCTURES & ENUMS
# =============================================================================
class OrderSide(Enum):
  BUY = "BUY"
  SELL = "SELL"


class OrderType(Enum):
  MARKET = "MARKET"
  LIMIT = "LIMIT"
  STOP_LOSS = "STOP_LOSS"
  TAKE_PROFIT = "TAKE_PROFIT"
  TRAILING_STOP = "TRAILING_STOP"


class OrderStatus(Enum):
  PENDING = "PENDING"
  FILLED = "FILLED"
  PARTIALLY_FILLED = "PARTIALLY_FILLED"
  CANCELLED = "CANCELLED"
  REJECTED = "REJECTED"
  EXPIRED = "EXPIRED"


class PositionSide(Enum):
  LONG = "LONG"
  SHORT = "SHORT"


@dataclass
class Order:
  order_id: str
  symbol: str
  side: OrderSide
  order_type: OrderType
  quantity: int
  limit_price: Optional[float] = None
  stop_price: Optional[float] = None
  trailing_percent: Optional[float] = None
  filled_quantity: int = 0
  avg_fill_price: float = 0.0
  status: OrderStatus = OrderStatus.PENDING
  created_at: str = field(
      default_factory=lambda: datetime.datetime.now().isoformat()
  )
  updated_at: str = field(
      default_factory=lambda: datetime.datetime.now().isoformat()
  )
  high_water_mark: Optional[float] = None


@dataclass
class Execution:
  execution_id: str
  order_id: str
  symbol: str
  side: OrderSide
  quantity: int
  price: float
  commission: float
  timestamp: str = field(
      default_factory=lambda: datetime.datetime.now().isoformat()
  )


@dataclass
class Position:
  symbol: str
  quantity: int
  avg_cost_basis: float
  total_cost: float
  current_price: float = 0.0
  market_value: float = 0.0
  unrealized_pnl: float = 0.0
  unrealized_pnl_pct: float = 0.0
  realized_pnl: float = 0.0


@dataclass
class PortfolioMetrics:
  timestamp: str
  total_equity: float
  cash_balance: float
  position_value: float
  unrealized_pnl: float
  realized_pnl: float
  daily_return: float
  total_return_pct: float
  drawdown_pct: float


# =============================================================================
# PERSISTENCE LAYER (SQLITE DATABASE MANAGER)
# =============================================================================
class DatabaseManager:

  """Manages SQLite storage for trade persistence, accounts, and analytics."""

  def __init__(self, db_path: str = "paper_trading.db"):
    self.db_path = db_path
    self.lock = threading.Lock()
    self._init_db()

  def _get_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self):
    with self.lock, self._get_connection() as conn:
      cursor = conn.cursor()

      # Accounts Table
      cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    cash_balance REAL NOT NULL,
                    initial_balance REAL NOT NULL,
                    currency TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

      # Positions Table
      cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL,
                    avg_cost_basis REAL NOT NULL,
                    total_cost REAL NOT NULL,
                    realized_pnl REAL NOT NULL
                )
            """)

      # Orders Table
      cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    limit_price REAL,
                    stop_price REAL,
                    trailing_percent REAL,
                    filled_quantity INTEGER NOT NULL,
                    avg_fill_price REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    high_water_mark REAL
                )
            """)

      # Executions Table
      cursor.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    commission REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
            """)

      # Portfolio Snapshots Table
      cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_equity REAL NOT NULL,
                    cash_balance REAL NOT NULL,
                    position_value REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    daily_return REAL NOT NULL,
                    total_return_pct REAL NOT NULL,
                    drawdown_pct REAL NOT NULL
                )
            """)

      # Audit Logs
      cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                )
            """)
      conn.commit()

  def save_account(
      self,
      account_id: str,
      cash_balance: float,
      initial_balance: float,
      currency: str = "USD",
  ):
    with self.lock, self._get_connection() as conn:
      conn.execute(
          """
                INSERT OR REPLACE INTO accounts (account_id, cash_balance, initial_balance, currency, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
          (
              account_id,
              cash_balance,
              initial_balance,
              currency,
              datetime.datetime.now().isoformat(),
          ),
      )
      conn.commit()

  def save_order(self, order: Order):
    with self.lock, self._get_connection() as conn:
      conn.execute(
          """
                INSERT OR REPLACE INTO orders 
                (order_id, symbol, side, order_type, quantity, limit_price, stop_price, 
                 trailing_percent, filled_quantity, avg_fill_price, status, created_at, updated_at, high_water_mark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
          (
              order.order_id,
              order.symbol,
              order.side.value,
              order.order_type.value,
              order.quantity,
              order.limit_price,
              order.stop_price,
              order.trailing_percent,
              order.filled_quantity,
              order.avg_fill_price,
              order.status.value,
              order.created_at,
              order.updated_at,
              order.high_water_mark,
          ),
      )
      conn.commit()

  def save_execution(self, execution: Execution):
    with self.lock, self._get_connection() as conn:
      conn.execute(
          """
                INSERT OR REPLACE INTO executions (execution_id, order_id, symbol, side, quantity, price, commission, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
          (
              execution.execution_id,
              execution.order_id,
              execution.symbol,
              execution.side.value,
              execution.quantity,
              execution.price,
              execution.commission,
              execution.timestamp,
          ),
      )
      conn.commit()

  def save_position(self, position: Position):
    with self.lock, self._get_connection() as conn:
      if position.quantity == 0:
        conn.execute(
            "DELETE FROM positions WHERE symbol = ?", (position.symbol,)
        )
      else:
        conn.execute(
            """
                    INSERT OR REPLACE INTO positions (symbol, quantity, avg_cost_basis, total_cost, realized_pnl)
                    VALUES (?, ?, ?, ?, ?)
                """,
            (
                position.symbol,
                position.quantity,
                position.avg_cost_basis,
                position.total_cost,
                position.realized_pnl,
            ),
        )
      conn.commit()

  def save_snapshot(self, metrics: PortfolioMetrics):
    with self.lock, self._get_connection() as conn:
      conn.execute(
          """
                INSERT INTO portfolio_snapshots 
                (timestamp, total_equity, cash_balance, position_value, unrealized_pnl, realized_pnl, daily_return, total_return_pct, drawdown_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
          (
              metrics.timestamp,
              metrics.total_equity,
              metrics.cash_balance,
              metrics.position_value,
              metrics.unrealized_pnl,
              metrics.realized_pnl,
              metrics.daily_return,
              metrics.total_return_pct,
              metrics.drawdown_pct,
          ),
      )
      conn.commit()

  def load_positions(self) -> Dict[str, Position]:
    positions = {}
    with self.lock, self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute(
          "SELECT symbol, quantity, avg_cost_basis, total_cost, realized_pnl"
          " FROM positions"
      )
      rows = cursor.fetchall()
      for row in rows:
        positions[row["symbol"]] = Position(
            symbol=row["symbol"],
            quantity=row["quantity"],
            avg_cost_basis=row["avg_cost_basis"],
            total_cost=row["total_cost"],
            realized_pnl=row["realized_pnl"],
        )
    return positions

  def load_orders(self) -> List[Order]:
    orders = []
    with self.lock, self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT * FROM orders")
      rows = cursor.fetchall()
      for row in rows:
        orders.append(
            Order(
                order_id=row["order_id"],
                symbol=row["symbol"],
                side=OrderSide(row["side"]),
                order_type=OrderType(row["order_type"]),
                quantity=row["quantity"],
                limit_price=row["limit_price"],
                stop_price=row["stop_price"],
                trailing_percent=row["trailing_percent"],
                filled_quantity=row["filled_quantity"],
                avg_fill_price=row["avg_fill_price"],
                status=OrderStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                high_water_mark=row["high_water_mark"],
            )
        )
    return orders

  def load_snapshots(self) -> pd.DataFrame:
    with self.lock, self._get_connection() as conn:
      df = pd.read_sql_query(
          "SELECT * FROM portfolio_snapshots ORDER BY timestamp ASC", conn
      )
    return df


# =============================================================================
# TECHNICAL ANALYSIS ENGINE
# =============================================================================
class TechnicalAnalysis:

  """Mathematical functions for quantitative technical indicator calculations."""

  @staticmethod
  def SMA(series: pd.Series, period: int = 20) -> pd.Series:
    return series.rolling(window=period).mean()

  @staticmethod
  def EMA(series: pd.Series, period: int = 20) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

  @staticmethod
  def RSI(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

  @staticmethod
  def MACD(
      series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
  ) -> Tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = TechnicalAnalysis.EMA(series, fast)
    slow_ema = TechnicalAnalysis.EMA(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = TechnicalAnalysis.EMA(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

  @staticmethod
  def BollingerBands(
      series: pd.Series, period: int = 20, num_std: float = 2.0
  ) -> Tuple[pd.Series, pd.Series, pd.Series]:
    middle_band = TechnicalAnalysis.SMA(series, period)
    std_dev = series.rolling(window=period).std()
    upper_band = middle_band + (std_dev * num_std)
    lower_band = middle_band - (std_dev * num_std)
    return upper_band, middle_band, lower_band

  @staticmethod
  def ATR(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"].shift(1)
    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# =============================================================================
# MARKET DATA PROVIDER (YAHOO FINANCE WRAPPER)
# =============================================================================
class MarketDataProvider:

  """Handles real-time price retrieval, historical streaming, and caching."""

  def __init__(self, cache_ttl_seconds: int = 5):
    self.cache_ttl = cache_ttl_seconds
    self._price_cache: Dict[str, Tuple[float, float]] = (
        {}
    )  # symbol -> (price, timestamp)
    self._historical_cache: Dict[str, Tuple[pd.DataFrame, float]] = {}

  def get_current_price(self, symbol: str) -> Optional[float]:
    symbol = symbol.upper()
    now = time.time()

    # Check Cache
    if symbol in self._price_cache:
      cached_price, cached_time = self._price_cache[symbol]
      if now - cached_time < self.cache_ttl:
        return cached_price

    # Fetch from Yahoo Finance
    try:
      ticker = yf.Ticker(symbol)
      # Fast info fetch
      price = ticker.fast_info.get("lastPrice") or ticker.fast_info.get(
          "regularMarketPrice"
      )

      if price is None or math.isnan(price):
        df = ticker.history(period="1d", interval="1m")
        if not df.empty:
          price = float(df["Close"].iloc[-1])
        else:
          logger.warning(
              f"Could not retrieve real-time price for ticker {symbol}"
          )
          return None

      price = float(price)
      self._price_cache[symbol] = (price, now)
      return price

    except Exception as e:
      logger.error(f"Error fetching real-time price for {symbol}: {str(e)}")
      return None

  def get_historical_data(
      self, symbol: str, period: str = "1mo", interval: str = "1d"
  ) -> pd.DataFrame:
    symbol = symbol.upper()
    cache_key = f"{symbol}_{period}_{interval}"
    now = time.time()

    if cache_key in self._historical_cache:
      df, cached_time = self._historical_cache[cache_key]
      if now - cached_time < 300:  # 5 min cache for historical
        return df

    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(period=period, interval=interval)
      if not df.empty:
        self._historical_cache[cache_key] = (df, now)
      return df
    except Exception as e:
      logger.error(
          f"Failed to fetch historical data for {symbol}: {str(e)}"
      )
      return pd.DataFrame()

  def get_market_quote(self, symbol: str) -> Dict[str, Any]:
    symbol = symbol.upper()
    try:
      ticker = yf.Ticker(symbol)
      fast = ticker.fast_info
      price = fast.get("lastPrice", 0.0)
      prev_close = fast.get("previousClose", 0.0)
      change = price - prev_close if price and prev_close else 0.0
      pct_change = (change / prev_close * 100) if prev_close else 0.0

      return {
          "symbol": symbol,
          "price": float(price) if price else 0.0,
          "open": float(fast.get("open", 0.0) or 0.0),
          "high": float(fast.get("dayHigh", 0.0) or 0.0),
          "low": float(fast.get("dayLow", 0.0) or 0.0),
          "previous_close": float(prev_close or 0.0),
          "change": float(change),
          "change_pct": float(pct_change),
          "volume": int(fast.get("lastVolume", 0) or 0),
          "market_cap": float(fast.get("marketCap", 0.0) or 0.0),
      }
    except Exception as e:
      logger.error(f"Error constructing market quote for {symbol}: {str(e)}")
      return {"symbol": symbol, "error": str(e)}


# =============================================================================
# RISK MANAGEMENT ENGINE
# =============================================================================
class RiskManager:

  """Enforces trading guardrails, portfolio drawdown rules, and position sizing."""

  def __init__(
      self,
      max_portfolio_risk_pct: float = 0.02,
      max_position_size_pct: float = 0.25,
      max_drawdown_limit_pct: float = 0.15,
  ):
    self.max_portfolio_risk_pct = max_portfolio_risk_pct
    self.max_position_size_pct = max_position_size_pct
    self.max_drawdown_limit_pct = max_drawdown_limit_pct

  def validate_order(
      self,
      order: Order,
      current_price: float,
      cash_balance: float,
      total_equity: float,
      existing_position_qty: int,
  ) -> Tuple[bool, str]:
    order_val = order.quantity * current_price

    if order.side == OrderSide.BUY:
      # Cash Check
      if order_val > cash_balance:
        return (
            False,
            f"Insufficient Cash. Required: ${order_val:,.2f}, Available:"
            f" ${cash_balance:,.2f}",
        )

      # Single Position Cap
      new_total_val = (existing_position_qty * current_price) + order_val
      max_allowed_val = total_equity * self.max_position_size_pct
      if new_total_val > max_allowed_val:
        return (
            False,
            f"Position Limit Exceeded. Max position allowed:"
            f" ${max_allowed_val:,.2f} ({self.max_position_size_pct*100}% of"
            " Equity)",
        )

    elif order.side == OrderSide.SELL:
      if order.quantity > existing_position_qty:
        return (
            False,
            f"Insufficient Shares. Requested: {order.quantity}, Holding:"
            f" {existing_position_qty}",
        )

    return True, "Order Approved"

  def calculate_max_position_size(
      self, price: float, cash: float, total_equity: float
  ) -> int:
    max_by_cash = cash / price if price > 0 else 0
    max_by_equity = (
        (total_equity * self.max_positio
    
