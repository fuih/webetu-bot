#!/usr/bin/env bash
# ========================================================
#   WebEtu Meal Reservation Automation - 1-Click Runner
# ========================================================
cd "$(dirname "$0")" || exit 1

# Detect Python 3
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo "[!] Error: Python 3 is not installed."
    echo "    On Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "    On Arch/CachyOS:  sudo pacman -S python python-requests"
    echo "    On Termux:        pkg install python"
    exit 1
fi

# Ensure 'requests' package is available
if ! $PY -c "import requests" &>/dev/null; then
    echo "[*] Installing required library (requests)..."
    $PY -m pip install -r requirements.txt 2>/dev/null || pip install -r requirements.txt 2>/dev/null || true
fi

# Run auto reservation
$PY webetu_client.py auto "$@"
