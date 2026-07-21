#!/usr/bin/env python3
"""清理期权平台 IV 历史数据（90天前）"""
from iv_store import cleanup_old_data
import sqlite3
import os
from datetime import datetime

db_path = '/root/option-platform/backend/iv_history.db'

try:
    # 清理90天前的数据
    deleted = cleanup_old_data(days=90)
    
    # 检查清理后的数据库大小
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM iv_history')
    total = c.fetchone()[0]
    conn.close()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    wan = total / 10000
    
    print(f"SUCCESS|{size_mb:.1f}|{total}|{wan:.1f}|{now}")
except Exception as e:
    print(f"ERROR|{e}")
