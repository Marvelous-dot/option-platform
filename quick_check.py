#!/usr/bin/env python3.11
"""Quick platform health check"""
import json, os, sys, time, subprocess

PROJECT_ROOT = "/root/option-platform"
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

# 1. Frontend dist age
dist = os.path.join(FRONTEND_DIR, "dist", "index.html")
if os.path.exists(dist):
    age_h = (time.time() - os.path.getmtime(dist)) / 3600
    print(f"FRONTEND_DIST: exists, age={age_h:.1f}h")
else:
    print("FRONTEND_DIST: MISSING")

# 2. Backend process
code, out, err = run("ps aux | grep 'python.*main.py' | grep -v grep")
if code == 0 and out.strip():
    print(f"BACKEND_PROC: running ({out.strip()[:80]})")
else:
    print("BACKEND_PROC: NOT RUNNING")

# 3. Backend health check
code, out = run(f"curl -s -m 3 http://localhost:8000/health")
if code == 0:
    try:
        data = json.loads(out)
        print(f"BACKEND_HEALTH: {json.dumps(data)}")
    except:
        print(f"BACKEND_HEALTH: degraded ({out[:200]})")
else:
    print(f"BACKEND_HEALTH: DOWN (curl exit={code})")

# 4. Data issues
code, out = run(f"curl -s -m 3 http://localhost:8000/api/state")
if code == 0:
    try:
        data = json.loads(out)
        issues = []
        if data.get("greeks_all_zero", False):
            issues.append("Greeks全为0")
        if data.get("iv_data_empty", False):
            issues.append("IV数据为空")
        print(f"DATA_ISSUES: {json.dumps(issues) if issues else 'none'}")
    except:
        print("DATA_ISSUES: parse_error")
else:
    print("DATA_ISSUES: cannot_check")

# 5. Accuracy audit
code, out, err = run(f"python3.11 /root/option-platform/accuracy_audit.py", 30)
print(f"ACCURACY_AUDIT: {'ok' if code == 0 else 'issues_found'}")

# 6. Cleanup
code, out, err = run(f"cd {BACKEND_DIR} && python3.11 cleanup_iv.py 2>/dev/null || true")
print(f"CLEANUP: {'ok' if code == 0 else 'failed'}")
