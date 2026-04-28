#!/bin/bash

# Python venv Setup (Debug)
# This script bootstraps the virtual environment for development.
# puts it in the src/pipeline/ directory instead of build/pipeline directory for release

# Ensure we are operating relative to the script's location
cd "$(dirname "$0")"

echo "[*] Initializing Python environment in $(pwd)"

# 1. Detect Operating System and Set Vendored Path
OS_TYPE="$(uname -s)"
VENDORED_ROOT="../../vendor/python"

if [[ "$OS_TYPE" == "Darwin" ]]; then
    echo "[*] Detected macOS (ARM)"
    PYTHON_BIN="$VENDORED_ROOT/mac_arm/bin/python3"

    # Strip quarantine attributes so macOS allows the vendored binary to run
    if [ -d "$VENDORED_ROOT/mac_arm" ]; then
        echo "[*] Stripping macOS security attributes from vendor..."
        xattr -rc "$VENDORED_ROOT/mac_arm"
    fi

elif [[ "$OS_TYPE" == *"MINGW"* || "$OS_TYPE" == *"MSYS"* || "$OS_TYPE" == *"CYGWIN"* ]]; then
    echo "[*] Detected Windows (x64)"
    PYTHON_BIN="$VENDORED_ROOT/win_x64/python.exe"

else
    echo "[!] Error: Unsupported Operating System ($OS_TYPE)."
    echo "[!] AnitoScan currently only supports macOS (ARM) and Windows (x64) via vendored binaries."
    exit 1
fi

# 2. Verify Vendored Binary Exists
if [ ! -f "$PYTHON_BIN" ]; then
    echo "[!] Error: Vendored Python not found at: $PYTHON_BIN"
    echo "[!] Please ensure the standalone Python distribution is placed in the vendor directory."
    exit 1
fi

echo "[*] Using Vendored Python: $($PYTHON_BIN --version)"

# 3. Create Virtual Environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[*] Creating .venv using vendored interpreter..."
    "$PYTHON_BIN" -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[!] Error: Failed to create virtual environment."
        exit 1
    fi
else
    echo "[*] .venv already exists. Skipping creation."
fi

# 4. Install/Update Dependencies
# We use the python binary inside the .venv to ensure we stay in the sandbox
VENV_PYTHON="./.venv/bin/python3"
if [[ "$OS_TYPE" == *"MINGW"* ]]; then
    VENV_PYTHON="./.venv/Scripts/python.exe"
fi

if [ -f "requirements.txt" ]; then
    echo "[*] Installing dependencies from requirements.txt..."
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r requirements.txt

    if [ $? -ne 0 ]; then
        echo "[!] Error: Failed to install requirements."
        exit 1
    fi
else
    echo "[!] Warning: requirements.txt not found. No libraries installed."
fi

echo "[*] Setup Complete. Your AnitoScan Python environment is ready."
