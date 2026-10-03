#!/bin/bash
PROJECT_DIR="/home/mirage-admin/workspace/CAN_SLIM_SCREEENER"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
SCRIPT="$PROJECT_DIR/canslim_papertrader.py"
LOG_FILE="$PROJECT_DIR/trader.log"

echo "=== Run started at $(date) ===" >> "$LOG_FILE"
"$VENV_PYTHON" "$SCRIPT" >> "$LOG_FILE" 2>&1
echo "=== Run finished at $(date) ===" >> "$LOG_FILE"