#!/bin/bash
# ============================================================
# DecentraStore Storage Node Launcher
# ============================================================
# Just run this script! A setup prompt will appear.
# ============================================================

# Change to script directory
cd "$(dirname "$0")"

echo ""
echo "============================================================"
echo "     DecentraStore Storage Node"
echo "============================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed!"
    echo "Install with: sudo apt install python3 python3-pip"
    exit 1
fi

# Run the launcher
python3 launcher.py --cli
