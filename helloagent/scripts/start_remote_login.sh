#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"

if ! pgrep -f "Xvfb ${DISPLAY}" >/dev/null 2>&1; then
  Xvfb "${DISPLAY}" -screen 0 1440x1000x24 -ac +extension RANDR >/tmp/helloagent-xvfb.log 2>&1 &
  sleep 1
fi

if ! pgrep -f "fluxbox.*${DISPLAY}" >/dev/null 2>&1; then
  DISPLAY="${DISPLAY}" fluxbox >/tmp/helloagent-fluxbox.log 2>&1 &
  sleep 1
fi

if ! pgrep -f "x11vnc.*${VNC_PORT}" >/dev/null 2>&1; then
  x11vnc -display "${DISPLAY}" -localhost -rfbport "${VNC_PORT}" -forever -shared -nopw >/tmp/helloagent-x11vnc.log 2>&1 &
  sleep 1
fi

if ! pgrep -f "websockify.*${NOVNC_PORT}" >/dev/null 2>&1; then
  websockify --web=/usr/share/novnc "127.0.0.1:${NOVNC_PORT}" "127.0.0.1:${VNC_PORT}" >/tmp/helloagent-novnc.log 2>&1 &
  sleep 1
fi

echo "noVNC 已启动。请在本地建立 SSH 隧道："
echo "ssh -N -L ${NOVNC_PORT}:127.0.0.1:${NOVNC_PORT} <服务器用户>@<服务器IP>"
echo "然后打开：http://127.0.0.1:${NOVNC_PORT}/vnc.html?autoconnect=true&path=websockify"
echo

exec /home/ubuntu/helloagent/.venv/bin/python /home/ubuntu/helloagent/scripts/login_platforms.py
