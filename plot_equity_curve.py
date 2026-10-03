import os
import sys
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

LEDGER_FILE = "canslim_paper_ledger.json"
if not os.path.exists(LEDGER_FILE) and os.path.exists("paper_ledger.json"):
    LEDGER_FILE = "paper_ledger.json"

def plot_performance():
    if not os.path.exists(LEDGER_FILE):
        print(f"[ERROR] Ledger file '{LEDGER_FILE}' not found.")
        sys.exit(1)

    with open(LEDGER_FILE, "r") as f:
        data = json.load(f)

    starting_capital = data.get("initial_capital", 30000.0)
    trade_history = data.get("trade_history", [])

    if not trade_history:
        print("[INFO] No closed trades found in ledger to plot.")
        return

    # 1. Prepare trade DataFrame
    df = pd.DataFrame(trade_history)
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df = df.sort_values(by="exit_date").reset_index(drop=True)

    # 2. Build cumulative equity curve
    df["cumulative_pnl"] = df["net_pnl"].cumsum()
    df["equity"] = starting_capital + df["cumulative_pnl"]

    # Prepend starting capital baseline before the first trade
    first_date = df["exit_date"].iloc[0] - pd.Timedelta(days=1)
    baseline_row = pd.DataFrame([{
        "exit_date": first_date,
        "net_pnl": 0.0,
        "cumulative_pnl": 0.0,
        "equity": starting_capital
    }])
    plot_df = pd.concat([baseline_row, df], ignore_index=True)

    # 3. Calculate running peak and drawdown
    plot_df["peak_equity"] = plot_df["equity"].cummax()
    plot_df["drawdown_amount"] = plot_df["equity"] - plot_df["peak_equity"]
    plot_df["drawdown_pct"] = (plot_df["drawdown_amount"] / plot_df["peak_equity"]) * 100

    max_dd_pct = plot_df["drawdown_pct"].min()
    current_equity = plot_df["equity"].iloc[-1]
    total_net_pnl = current_equity - starting_capital
    total_return_pct = (total_net_pnl / starting_capital) * 100

    # 4. Construct Dual-Panel Plot
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})

    # --- Top Panel: Equity Curve ---
    ax1.plot(plot_df["exit_date"], plot_df["equity"], color="#1f77b4", linewidth=2.2, label="Portfolio Equity", zorder=3)
    ax1.plot(plot_df["exit_date"], plot_df["peak_equity"], color="#2ca02c", linestyle="--", linewidth=1.2, alpha=0.7, label="High-Water Mark")
    ax1.axhline(starting_capital, color="#7f7f7f", linestyle=":", linewidth=1.2, label=f"Initial Capital (₹{starting_capital:,.0f})")

    ax1.set_title(f"Trading Bot Performance — Equity Curve & Underwater Drawdown\n"
                  f"Net Return: ₹{total_net_pnl:+,.2f} ({total_return_pct:+.2f}%) | Max DD: {max_dd_pct:.2f}%",
                  fontsize=13, fontweight="bold", pad=12)
    ax1.set_ylabel("Portfolio Value (₹)", fontsize=11, fontweight="bold")
    ax1.yaxis.set_major_formatter("₹{:,.0f}".format)
    ax1.legend(loc="upper left", frameon=True)
    ax1.grid(True, linestyle="--", alpha=0.5)

    # Highlight winning vs losing exit points
    if len(df) > 0:
        wins = df[df["net_pnl"] > 0]
        losses = df[df["net_pnl"] <= 0]
        ax1.scatter(wins["exit_date"], wins["equity"], color="#2ca02c", marker="^", s=65, label="Win", zorder=4)
        ax1.scatter(losses["exit_date"], losses["equity"], color="#d62728", marker="v", s=65, label="Loss", zorder=4)

    # --- Bottom Panel: Underwater Drawdown ---
    ax2.fill_between(plot_df["exit_date"], plot_df["drawdown_pct"], 0, color="#d62728", alpha=0.35, label="Drawdown %")
    ax2.plot(plot_df["exit_date"], plot_df["drawdown_pct"], color="#d62728", linewidth=1.2)
    ax2.axhline(0, color="#333333", linestyle="-", linewidth=0.8)

    ax2.set_ylabel("Drawdown (%)", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Exit Date", fontsize=11, fontweight="bold")
    ax2.yaxis.set_major_formatter("{:.1f}%".format)
    ax2.set_ylim(min(max_dd_pct * 1.25, -2.0), 1.0)
    ax2.grid(True, linestyle="--", alpha=0.5)

    # Date formatting on X-axis
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y" if (plot_df["exit_date"].iloc[-1] - plot_df["exit_date"].iloc[0]).days > 90 else "%d %b"))
    fig.autofmt_xdate()

    plt.tight_layout()

    # 5. Output Handling
    output_png = "equity_and_drawdown.png"
    plt.savefig(output_png, dpi=300)
    print(f"[SUCCESS] Performance plot generated and saved to: {output_png}")

    # Display window if running in an interactive GUI session
    if os.environ.get("DISPLAY"):
        plt.show()

if __name__ == "__main__":
    plot_performance()