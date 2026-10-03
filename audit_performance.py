import json
import os
import sys
from datetime import datetime
import numpy as np
import pandas as pd
from tabulate import tabulate

LEDGER_FILE = "canslim_paper_ledger.json"
# Fallback to general ledger if CAN SLIM ledger is not present
if not os.path.exists(LEDGER_FILE) and os.path.exists("paper_ledger.json"):
  LEDGER_FILE = "paper_ledger.json"


def load_ledger(filepath):
  if not os.path.exists(filepath):
    print(f"[ERROR] Ledger file '{filepath}' not found.")
    sys.exit(1)
  with open(filepath, "r") as f:
    return json.load(f)


def calculate_max_drawdown(equity_series):
  """Calculates the maximum peak-to-trough decline in portfolio equity."""
  if len(equity_series) == 0:
    return 0.0, 0.0
  equity = np.array(equity_series)
  peak = np.maximum.accumulate(equity)
  drawdown = (equity - peak) / peak
  max_dd_pct = np.min(drawdown) * 100
  max_dd_amount = np.min(equity - peak)
  return abs(max_dd_pct), abs(max_dd_amount)


def audit_portfolio():
  data = load_ledger(LEDGER_FILE)
  starting_capital = data.get("initial_capital", 30000.0)
  current_cash = data.get("cash", starting_capital)
  trade_history = data.get("trade_history", [])

  print(f"\n{'='*70}")
  print(f"{'PORTFOLIO PERFORMANCE & RISK AUDIT':^70}")
  print(f"{'='*70}")
  print(f"Ledger File Analyzed: {LEDGER_FILE}")
  print(f"Starting Capital:     ₹{starting_capital:,.2f}")
  print(f"Total Closed Trades:  {len(trade_history)}")

  if not trade_history:
    print(
        "\n[INFO] No closed trades recorded yet. Current cash:"
        f" ₹{current_cash:,.2f}"
    )
    return

  df = pd.DataFrame(trade_history)

  # Normalize columns
  if "exit_date" in df.columns:
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["month_year"] = df["exit_date"].dt.strftime("%Y-%m")
  else:
    df["month_year"] = "All-Time"

  # 1. Overall Win Rate & Profit Factor
  wins = df[df["net_pnl"] > 0]
  losses = df[df["net_pnl"] <= 0]

  total_trades = len(df)
  total_wins = len(wins)
  total_losses = len(losses)
  win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0.0

  gross_profit = wins["net_pnl"].sum()
  gross_loss = abs(losses["net_pnl"].sum())
  profit_factor = (
      (gross_profit / gross_loss)
      if gross_loss > 0
      else (np.inf if gross_profit > 0 else 0.0)
  )

  # 2. Cumulative Equity Curve for Max Drawdown
  df = df.sort_values(by="exit_date").reset_index(drop=True)
  df["running_pnl"] = df["net_pnl"].cumsum()
  df["equity"] = starting_capital + df["running_pnl"]

  equity_curve = [starting_capital] + df["equity"].tolist()
  max_dd_pct, max_dd_amount = calculate_max_drawdown(equity_curve)

  # 3. Monthly Breakdown Table
  monthly_groups = df.groupby("month_year")
  monthly_table = []

  for month, group in monthly_groups:
    m_trades = len(group)
    m_wins = len(group[group["net_pnl"] > 0])
    m_win_rate = (m_wins / m_trades) * 100 if m_trades > 0 else 0.0

    m_gross_profit = group[group["net_pnl"] > 0]["net_pnl"].sum()
    m_gross_loss = abs(group[group["net_pnl"] <= 0]["net_pnl"].sum())
    m_pf = (
        (m_gross_profit / m_gross_loss)
        if m_gross_loss > 0
        else (np.inf if m_gross_profit > 0 else 0.0)
    )

    m_net_pnl = group["net_pnl"].sum()
    pf_str = f"{m_pf:.2f}" if m_pf != np.inf else "Inf"

    monthly_table.append([
        month,
        m_trades,
        f"{m_win_rate:.1f}%",
        f"₹{m_gross_profit:,.2f}",
        f"₹{m_gross_loss:,.2f}",
        pf_str,
        f"₹{m_net_pnl:+,.2f}",
    ])

  headers = [
      "Month",
      "Trades",
      "Win Rate",
      "Gross Win",
      "Gross Loss",
      "Profit Factor",
      "Net P&L",
  ]
  print("\n" + tabulate(monthly_table, headers=headers, tablefmt="github"))

  # 4. Global Summary Metrics
  net_pnl_total = df["net_pnl"].sum()
  current_equity = starting_capital + net_pnl_total
  roi_pct = (net_pnl_total / starting_capital) * 100

  summary_cards = [
      ["Initial Capital", f"₹{starting_capital:,.2f}"],
      ["Ending Equity", f"₹{current_equity:,.2f}"],
      ["Total Net P&L", f"₹{net_pnl_total:+,.2f} ({roi_pct:+.2f}%)"],
      ["Global Win Rate", f"{win_rate:.1f}% ({total_wins}W / {total_losses}L)"],
      [
          "Global Profit Factor",
          f"{profit_factor:.2f}" if profit_factor != np.inf else "Inf",
      ],
      [
          "Average Win",
          f"₹{wins['net_pnl'].mean():,.2f}" if len(wins) > 0 else "₹0.00",
      ],
      [
          "Average Loss",
          f"₹{losses['net_pnl'].mean():,.2f}" if len(losses) > 0 else "₹0.00",
      ],
      [
          "Reward-to-Risk (Avg Win / Avg Loss)",
          f"{abs(wins['net_pnl'].mean() / losses['net_pnl'].mean()):.2f}"
          if len(losses) > 0 and len(wins) > 0
          else "N/A",
      ],
      ["Max Peak-to-Trough Drawdown", f"{max_dd_pct:.2f}% (₹{max_dd_amount:,.2f})"],
  ]

  print("\n" + tabulate(summary_cards, headers=["Metric", "Value"], tablefmt="fancy_grid"))
  print()


if __name__ == "__main__":
  audit_portfolio()