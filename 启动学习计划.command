#!/bin/bash
# 双击启动：后台运行服务并打开浏览器（无需 Claude Code）
cd "$(dirname "$0")"
URL="http://127.0.0.1:5001/"

# 已经在运行则直接打开浏览器
if curl -s -o /dev/null "$URL"; then
  echo "服务已在运行，直接打开浏览器"
  open "$URL"
  exit 0
fi

# 后台启动（nohup 保证关闭终端后仍存活）
nohup ./venv/bin/python app.py >> server.log 2>&1 &
echo $! > server.pid
sleep 1.5
open "$URL"
echo "已启动服务并打开浏览器：$URL"
