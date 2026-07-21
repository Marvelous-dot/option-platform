#!/usr/bin/env python3
"""IV历史数据清理脚本"""
import sys
sys.path.insert(0, '/root/option-platform/backend')

from iv_store import cleanup_old_data
import sqlite3
import os
from datetime import datetime

# 清理90天前的数据
print("开始清理90天前的IV历史数据...")
cleanup_old_data(days=7)

# 检查清理后的数据库大小
db_path = '/root/option-platform/backend/iv_history.db'
size_mb = os.path.getsize(db_path) / (1024*1024)
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM iv_history')
total = c.fetchone()[0]
conn.close()

now = datetime.now().strftime("%Y-%m-%d %H:%M")
print(f"清理完成: 数据库 {size_mb:.1f}MB, 剩余 {total:,} 条记录")
print(f"清理时间: {now}")
