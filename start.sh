#!/bin/bash
# 启动 xhs-topics 本地服务（http://localhost:8773）
cd "$(dirname "$0")"
exec python3 server.py
