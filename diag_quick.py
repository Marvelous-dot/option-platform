#!/usr/bin/env python3
"""Quick diagnostic - terminal blocked, checking via files"""
import os, time

PROJECT_ROOT = "/root/option-platform"

# 1. Frontend build
dist = os.path.join(PROJECT_ROOT, "frontend/dist/index.html")
if os.path.exists(dist):
    mtime = os.path.getmtime(dist)
    age_hours = (time.time() - mtime) / 3600
    print(f"FRONTEND|ok|age_hours={age_hours:.1f}")
else:
    print("FRONTEND|missing")

# 2. Canvas theme
files = {
    "DashboardPanel": os.path.join(PROJECT_ROOT, "frontend/src/components/DashboardPanel.vue"),
    "DashboardChart": os.path.join(PROJECT_ROOT, "frontend/src/components/DashboardChart.vue"),
    "Surface3D": os.path.join(PROJECT_ROOT, "frontend/src/components/Surface3D.vue"),
    "ContractDetail": os.path.join(PROJECT_ROOT, "frontend/src/views/ContractDetail.vue"),
}
for name, path in files.items():
    if os.path.exists(path):
        with open(path) as f:
            content = f.read()
        status = "ok" if "getCssVars" in content else "hardcoded"
    else:
        status = "missing"
    print(f"CANVAS|{name}|{status}")

# 3. vite.config.js
vite_path = os.path.join(PROJECT_ROOT, "frontend/vite.config.js")
if os.path.exists(vite_path):
    with open(vite_path) as f:
        content = f.read()
    has_alias = "fileURLToPath" in content
    print(f"VITE_ALIAS|{'ok' if has_alias else 'missing'}")

# 4. cssVar.js
cssvar_path = os.path.join(PROJECT_ROOT, "frontend/src/utils/cssVar.js")
print(f"CSSVAR_UTIL|{'ok' if os.path.exists(cssvar_path) else 'missing'}")

# 5. Backend db
db_path = os.path.join(PROJECT_ROOT, "backend/iv_history.db")
if os.path.exists(db_path):
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"DB|ok|size_mb={size_mb:.2f}")
else:
    print("DB|missing")

# 6. cleanup_iv.py exists
cleanup_path = os.path.join(PROJECT_ROOT, "backend/cleanup_iv.py")
print(f"CLEANUP_SCRIPT|{'ok' if os.path.exists(cleanup_path) else 'missing'}")

print("DIAG_DONE")
