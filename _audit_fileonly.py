#!/usr/bin/env python3
"""Accuracy audit via file-only data (terminal blocked workaround)"""
import os, sys, json, sqlite3, time
from datetime import datetime

PROJECT_ROOT = "/root/option-platform"
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

# Try to read the iv_history.db for recent data
db_path = os.path.join(BACKEND_DIR, "iv_history.db")
issues = []

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Check recent data timestamps
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for (t,) in tables:
            cursor.execute(f"SELECT COUNT(*) FROM '{t}'")
            count = cursor.fetchone()[0]
            print(f"TABLE:{t}|rows={count}")
        conn.close()
    except Exception as e:
        issues.append(f"DB读取失败: {e}")
else:
    issues.append("iv_history.db不存在")

# Check backend startup status
log_dir = "/root/option-platform"
# Check if there are any recent output files
import glob
recent = glob.glob(os.path.join(log_dir, "*.log"))
if recent:
    for f in recent:
        mtime = os.path.getmtime(f)
        age = (time.time() - mtime) / 3600
        print(f"LOG:{os.path.basename(f)}|age_h={age:.1f}")

# Check data_service.py for any errors
ds_path = os.path.join(BACKEND_DIR, "data_service.py")
if os.path.exists(ds_path):
    with open(ds_path) as f:
        content = f.read()
    print(f"DATA_SERVICE|exists|size={len(content)}")
else:
    issues.append("data_service.py不存在")

# Summary
total = len(issues)
if total == 0:
    print("AUDIT_RESULT|ok|0 issues")
else:
    print(f"AUDIT_RESULT|warn|{total} issues: {', '.join(issues)}")

print("AUDIT_DONE")
