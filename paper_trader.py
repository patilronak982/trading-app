import pandas as pd
import yfinance as yf


class PaperTrader:

  def __init__(self, starting_cash=10000.0):
    self.starting_cash = float(starting_cash)
    self.cash = float(starting_cash)
    # Structure: {'AAPL': {'shares': 10, 'total_cost': 1500.0}}
    self.portfolio = {}
    self.trade_history = []

  def get_live_price(self, symbol: str) -> float | None:
    """Fetch the latest market price for a given stock symbol."""
    try:
      ticker = yf.Ticker(symbol.upper())
      # Attempt fast_info for real-time market price
      price = ticker.fast_info.get('lastPrice') or ticker.fast_info.get(
          'regularMarketPrice'
      )

      # Fallback to historical daily data if fast_info is unavailable
      if price is None or pd.isna(price):
        df = ticker.history(period='1d')
        if not df.empty:
          price = df['Close'].iloc[-1]
        else:
          return None
      return float(price)
    except Exception:
      return None

  def buy(self, symbol: str, quantity: int):
    """Buy shares at the current market price."""
    symbol = symbol.upper()
    if quantity <= 0:
      print("Error: Quantity must be greater than zero.")
      return

    price = self.get_live_price(symbol)
    if price is None:
      print(f"Error: Could not retrieve market data for '{symbol}'.")
      return

    total_cost = price * quantity
    if total_cost > self.cash:
      print(
          f"Insufficient Cash! Cost: ${total_cost:,.2f} | Available:"
          f" ${self.cash:,.2f}"
      )
      return

    self.cash -= total_cost
    if symbol not in self.portfolio:
      self.portfolio[symbol] = {'shares': 0, 'total_cost': 0.0}

    self.portfolio[symbol]['shares'] += quantity
    self.portfolio[symbol]['total_cost'] += total_cost

    self.trade_history.append({
        'action': 'BUY',
        'symbol': symbol,
        'shares': quantity,
        'price': price,
        'total': total_cost,
    })
    print(
        f"SUCCESS: Bought {quantity} shares of {symbol} at ${price:,.2f}/share"
        f" (Total: ${total_cost:,.2f})"
    )

  def sell(self, symbol: str, quantity: int):
    """Sell shares at the current market price."""
    symbol = symbol.upper()
    if quantity <= 0:
      print("Error: Quantity must be greater than zero.")
      return

    held_shares = self.portfolio.get(symbol, {}).get('shares', 0)
    if held_shares < quantity:
      print(
          f"Insufficient Position! You hold {held_shares} shares of {symbol}."
      )
      return

    price = self.get_live_price(symbol)
    if price is None:
      print(f"Error: Could not retrieve market data for '{symbol}'.")
      return

    total_revenue = price * quantity
    avg_cost_per_share = (
        self.portfolio[symbol]['total_cost'] / self.portfolio[symbol]['shares']
    )
    cost_basis_sold = avg_cost_per_share * quantity

    self.cash += total_revenue
    self.portfolio[symbol]['shares'] -= quantity
    self.portfolio[symbol]['total_cost'] -= cost_basis_sold

    if self.portfolio[symbol]['shares'] == 0:
      del self.portfolio[symbol]

    self.trade_history.append({
        'action': 'SELL',
        'symbol': symbol,
        'shares': quantity,
        'price': price,
        'total': total_revenue,
    })
    print(
        f"SUCCESS: Sold {quantity} shares of {symbol} at ${price:,.2f}/share"
        f" (Total: ${total_revenue:,.2f})"
    )

  def display_portfolio(self):
    """Display overall portfolio performance and holdings."""
    print('\n' + '=' * 75)
    print(f"{'PORTFOLIO DASHBOARD':^75}")
    print('=' * 75)
    print(f"Available Cash: ${self.cash:,.2f}\n")

    total_stock_value = 0.0

    if not self.portfolio:
      print('Holdings: None')
    else:
      print(
          f"{'Ticker':<8} {'Shares':<8} {'Avg Cost':<12} {'Current':<12}"
          f" {'Value':<12} {'Unrealized P/L':<15}"
      )
      print('-' * 75)

      for symbol, data in self.portfolio.items():
        shares = data['shares']
        avg_cost = data['total_cost'] / shares
        current_price = self.get_live_price(symbol) or avg_cost
        mkt_val = shares * current_price
        pl_dollars = mkt_val - data['total_cost']
        pl_percent = (pl_dollars / data['total_cost']) * 100

        total_stock_value += mkt_val
        pl_str = f"${pl_dollars:+,.2f} ({pl_percent:+.2f}%)"
        print(
            f'{symbol:<8} {shares:<8} ${avg_cost:<11.2f} ${current_price:<11.2f}'
            f' ${mkt_val:<11.2f} {pl_str:<15}'
        )

    total_account_value = self.cash + total_stock_value
    net_pl = total_account_value - self.starting_cash
    net_pl_pct = (net_pl / self.starting_cash) * 100

    print('-' * 75)
    print(f'Total Account Value : ${total_account_value:,.2f}')
    print(f'Net Return          : ${net_pl:+,.2f} ({net_pl_pct:+.2f}%)')
    print('=' * 75 + '\n')


# --- Interactive CLI Loop ---
if __name__ == '__main__':
  trader = PaperTrader(starting_cash=10000.0)

  while True:
    print('Commands: [1] Price Check  [2] Buy  [3] Sell  [4] Portfolio  [5] Exit')
    choice = input('Select an option (1-5): ').strip()

    if choice == '1':
      symbol = input('Enter ticker symbol (e.g., AAPL, NVDA, TSLA): ').strip()
      price = trader.get_live_price(symbol)
      if price:
        print(f"Current price for {symbol.upper()}: ${price:,.2f}")
      else:
        print('Invalid ticker or price unavailable.')

    elif choice == '2':
      symbol = input('Ticker to BUY: ').strip()
      qty = input('Quantity of shares: ').strip()
      if qty.isdigit():
        trader.buy(symbol, int(qty))

    elif choice == '3':
      symbol = input('Ticker to SELL: ').strip()
      qty = input('Quantity of shares: ').strip()
      if qty.isdigit():
        trader.sell(symbol, int(qty))

    elif choice == '4':
      trader.display_portfolio()

    elif choice == '5':
      print('Exiting Paper Trading App.')
      break

    else:
      print('Invalid selection. Choose between 1 and 5.')
  
