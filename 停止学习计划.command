#!/bin/bash
# 双击停止服务
cd "$(dirname "$0")"

# 先尝试通过 launchd 停止（如果已注册为开机自启服务）
launchctl bootout "gui/$(id -u)/com.studyplanner.daily" 2>/dev/null

# 再兜底：按 pid 文件和进程名停止
if [ -f server.pid ]; then
  kill "$(cat server.pid)" 2>/dev/null
  rm -f server.pid
fi
pkill -f "app.py" 2>/dev/null

echo "服务已停止"
