#!/bin/bash
# xhs-topics 桌面 App 启动器（独立原生窗口）
# 复用 daily-todo 的 venv（已装 pywebview+pyobjc），跑 desktop_app.py
set -e
DIR="$HOME/xhs-topics"
# 优先用 daily-todo 的 venv（装齐了 webview）；没有则退化到本目录 venv；再没有退浏览器
PY="$HOME/daily-todo/venv/bin/python"
[ -x "$PY" ] || PY="$DIR/venv/bin/python"

if [ -x "$PY" ] && "$PY" -c "import webview" 2>/dev/null; then
    # 原生窗口模式，detach 让 .app 立即返回
    nohup "$PY" "$DIR/desktop_app.py" > /tmp/xhs-topics-app.log 2>&1 &
    disown
else
    # 兜底：webview 不可用 → 浏览器开
    open "http://localhost:8773"
fi
