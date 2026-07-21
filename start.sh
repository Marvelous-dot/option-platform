#!/bin/bash
# 期权平台后端启动脚本
# 先杀掉旧进程，再启动新进程
pkill -f "python3.11 run.py" 2>/dev/null
sleep 1
cd /root/option-platform/backend
nohup python3.11 run.py > /tmp/option-platform.log 2>&1 &
echo "PID: $!"
