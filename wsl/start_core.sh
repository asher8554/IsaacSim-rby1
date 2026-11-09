#!/usr/bin/env bash
# WSL에서 rby1 core(app_main isaac)와 Isaac Sim 중계 릴레이를 함께 실행하는 스크립트
# Usage (WSL):  bash /mnt/e/Github/IsaacSim-rby1/wsl/start_core.sh        (HEADLESS=1 hides the core status window)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$ROOT/rby1-core"
[[ -x "$CORE/sdk/app/app_main" ]] || { echo "rby1-core missing: run tools/fetch_rby1_core.py first" >&2; exit 1; }

# Same environment as the official image (rby1-core/image_env.json)
export LD_LIBRARY_PATH="$CORE/sdk/app${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="$CORE/internal"
export ROBOT_MODEL_NAME=A ROBOT_MODEL_VERSION=1.2
export RBY1_SKIP_CONTROL_TIMEOUT=1 RBY1_SKIP_RT_LOOP_TIMEOUT=1
[[ "${HEADLESS:-0}" == "1" ]] && export RBY1_HEADLESS=1

# udp_protocol.so targets Isaac Sim 6.2's numpy 2.x; Ubuntu's system numpy is 1.26, so use the rby1-sdk venv
PY="${RBY1_PYTHON:-$HOME/rby1-venv/bin/python}"
[[ -x "$PY" ]] || PY=python3
"$PY" -u "$ROOT/wsl/rby1_relay.py" &
RELAY=$!
trap 'kill $RELAY 2>/dev/null || true' EXIT
sleep 0.5
cd "$CORE/sdk/app"
./app_main isaac
