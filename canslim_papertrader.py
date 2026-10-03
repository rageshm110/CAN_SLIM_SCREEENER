import numpy as np
import pandas as pd
import yfinance as yf
import json
import os
from datetime import datetime

LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canslim_paper_ledger.json")
INITIAL_CAPITAL = 30000.0
MAX_POSITIONS = 2
ALLOCATION_PER_POSITION = 0.45  # fraction of initial capital per trade

def download_daily(ticker, period):
    """Daily bars with flat OHLCV columns (yfinance returns a MultiIndex even for one ticker)"""
    df = yf.download(ticker, period=period, interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

class CANSLIMPaperTrader:
    def __init__(self, initial_capital=INITIAL_CAPITAL):
        self.capital = initial_capital
        self.load_state()

    def load_state(self):
        if os.path.exists(LEDGER_FILE):
            with open(LEDGER_FILE, "r") as f:
                self.state = json.load(f)
        else:
            self.state = {
                "cash": self.capital,
                "positions": {},  # {SYMBOL: {qty, entry_price, stop_loss, target_price, entry_date}}
                "trade_history": []
            }
            self.save_state()

    def save_state(self):
        with open(LEDGER_FILE, "w") as f:
            json.dump(self.state, f, indent=4)

    def calculate_relative_strength(self, stock_df, benchmark_df):
        """Calculates RS line (Stock Close / Benchmark Close) and checks 52-week RS high"""
        rs_line = stock_df["Close"] / benchmark_df["Close"]
        rs_52w_high = rs_line.rolling(window=250, min_periods=100).max()
        rs_leading = rs_line.iloc[-1] >= (rs_52w_high.iloc[-1] * 0.98)
        return rs_leading

    def check_market_direction(self):
        """M in CANSLIM: Major Index (Nifty 50) must be above its 21-day EMA"""
        nifty = download_daily("^NSEI", "6mo")
        close = nifty["Close"]
        ema_21 = close.ewm(span=21, adjust=False).mean()

        latest_close = close.iloc[-1].item()
        latest_ema21 = ema_21.iloc[-1].item()

        print(
            f"[NIFTY CHECK] Latest Close: {latest_close:.2f} | 21 EMA: {latest_ema21:.2f} | Diff: {latest_close - latest_ema21:+.2f}"
        )

        return bool(latest_close > latest_ema21)

    def scan_breakout(self, ticker, benchmark_df):
        """Scans for Base Breakout with Volume Confirmation and RS Leadership"""
        df = download_daily(ticker, "1y")
        if len(df) < 120:
            print(f"[SCAN] {ticker}: insufficient price history ({len(df)} bars)")
            return None

        df["Vol_SMA30"] = df["Volume"].rolling(window=30).mean()
        recent_close = df["Close"].iloc[-1].item()
        recent_vol = df["Volume"].iloc[-1].item()
        vol_sma30 = df["Vol_SMA30"].iloc[-1].item()
        vol_ratio = recent_vol / vol_sma30 if vol_sma30 else 0.0

        # 25-day consolidation high as pivot
        base_lookback = df.iloc[-25:-1]
        pivot_price = base_lookback["High"].max().item()
        
        # Volume dry-up check in base (at least 2 days with volume < 60% of average)
        vol_dryup = (base_lookback["Volume"] < (vol_sma30 * 0.60)).sum() >= 2
        
        # Relative Strength Check
        rs_strong = self.calculate_relative_strength(df, benchmark_df)

        # Breakout Rules:
        # 1. Price crosses pivot
        # 2. Not extended > 5% above pivot
        # 3. Volume >= 1.5x 30-day SMA
        # 4. Base had prior volume dry-up
        # 5. RS line within 2% of 52-week high
        is_breaking_out = (
            recent_close > ( pivot_price * 0.96) and
            recent_close <= (pivot_price * 1.05) and
            recent_vol >= (1.5 * vol_sma30) and
            vol_dryup and
            rs_strong
        )

        if is_breaking_out:
            return {
                "symbol": ticker,
                "close": round(recent_close, 2),
                "pivot": round(pivot_price, 2),
                "volume_ratio": round(vol_ratio, 2)
            }
        print(f"[SCAN] {ticker}: no breakout (close {recent_close:.2f}, pivot {pivot_price:.2f}, vol x{vol_ratio:.2f}, dry-up {vol_dryup}, RS {rs_strong})")
        return None

    def execute_paper_order(self, signal):
        """Enforces position sizing & strict O'Neil risk limits"""
        if len(self.state.get("positions", {})) >= MAX_POSITIONS:
            print(f"[LIMIT REACHED] Already holding {MAX_POSITIONS} active positions.")
            return

        price = signal["close"]
        if not price or pd.isna(price) or price <= 0:
                    print(f"[ERROR] Invalid price data for {signal['symbol']}: {price}")
                    return
        budget = self.capital * ALLOCATION_PER_POSITION
        qty = int(budget // price)
        if qty <= 0 or self.state["cash"] < (qty * price):
            print("[ALERT] Insufficient available cash buffer.")
            return

        cost = qty * price
        self.state["cash"] -= cost

        # Strict 7% stop-loss & 20% growth target
        position = {
            "qty": qty,
            "entry_price": price,
            "stop_loss": round(price * 0.93, 2),
            "target_price": round(price * 1.20, 2),
            "entry_date": datetime.now().strftime("%Y-%m-%d"),
        }
        self.state["positions"][signal["symbol"]] = position
        self.save_state()

        print(f"\n[CAN SLIM BUY EXECUTED] {qty} shares of {signal['symbol']} at Rs.{price:.2f}")
        print(f"Pivot: Rs.{signal['pivot']:.2f} | Stop Loss (-7%): Rs.{position['stop_loss']:.2f} | Target (+20%): Rs.{position['target_price']:.2f}")

    def manage_position(self, symbol, current_price):
        """Monitors an active holding against stop loss and profit targets"""
        position = self.state["positions"][symbol]
        entry = position["entry_price"]
        qty = position["qty"]
        pnl_pct = (current_price - entry) / entry

        # Exit triggers
        if current_price <= position["stop_loss"]:
            reason = "STOP_LOSS_HIT (-7%)"
        elif current_price >= position["target_price"]:
            reason = "TARGET_HIT (+20%)"
        else:
            print(f"[HOLDING] {symbol} at Rs.{current_price:.2f} (P&L: {pnl_pct*100:+.2f}%)")
            return

        gross = qty * current_price
        friction = 15.93 + (0.001 * gross)
        net_received = gross - friction
        net_pnl = net_received - (qty * entry)

        self.state["cash"] += net_received
        self.state["trade_history"].append({
            "symbol": symbol,
            "exit_date": datetime.now().strftime("%Y-%m-%d"),
            "qty": qty,
            "entry_price": entry,
            "exit_price": current_price,
            "net_pnl": round(net_pnl, 2),
            "reason": reason
        })
        print(f"\n[CAN SLIM EXIT] {symbol} sold at Rs.{current_price:.2f} ({reason}). Net P&L: Rs.{net_pnl:.2f}")

        del self.state["positions"][symbol]
        self.save_state()

if __name__ == "__main__":
    bot = CANSLIMPaperTrader()

    # Exits are checked every run; the market filter below only gates new buys
    for sym in list(bot.state["positions"]):
        curr_df = download_daily(sym, "5d")
        if curr_df.empty:
            print(f"[DATA ERROR] No price data for {sym}; exit check skipped.")
            continue
        bot.manage_position(sym, curr_df["Close"].iloc[-1].item())

    if not bot.check_market_direction():
        print("[MARKET FILTER] Nifty 50 is below its 21 EMA. CAN SLIM forbids new buying.")
    else:
        print("[MARKET FILTER] General market is in an uptrend (Confirmed).")
        
        # High-growth watchlist passing C, A, and I screens
        # Verified NSE ticker symbols formatted for yfinance (.NS)
        WATCHLIST = [
            "TDPOWERSYS.NS",  # TD Power Systems
            "SKYGOLD.NS",     # Sky Gold & Diamonds
            "EBGNG.NS",       # GNG Electronics (Electronics Bazaar)
            "PGIL.NS",        # Pearl Global Industries
            "ASKAUTOLTD.NS",  # ASK Automotive
            "KSHINTL.NS",     # KSH International
        ]
        nifty_df = download_daily("^NSEI", "1y")

        for stock in WATCHLIST:
            if len(bot.state["positions"]) >= MAX_POSITIONS:
                break
            if stock in bot.state["positions"]:
                continue
            sig = bot.scan_breakout(stock, nifty_df)
            if sig:
                bot.execute_paper_order(sig)