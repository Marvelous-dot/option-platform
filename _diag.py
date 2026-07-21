#!/usr/bin/env python3
"""Manual diagnostic - minimal version"""
import os, time, json

PROJECT_ROOT = "/root/option-platform"
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

results = {}

# 1. Check frontend dist
dist = os.path.join(FRONTEND_DIR, "dist", "index.html")
if os.path.exists(dist):
    mtime = os.path.getmtime(dist)
    age_hours = (time.time() - mtime) / 3600
    results["frontend"] = "ok" if age_hours < 48 else "stale"
    results["frontend_age_hours"] = round(age_hours, 1)
else:
    results["frontend"] = "missing"

# 2. Check canvas theme
files = {
    "DashboardPanel": os.path.join(FRONTEND_DIR, "src/components/DashboardPanel.vue"),
    "DashboardChart": os.path.join(FRONTEND_DIR, "src/components/DashboardChart.vue"),
    "Surface3D": os.path.join(FRONTEND_DIR, "src/components/Surface3D.vue"),
    "ContractDetail": os.path.join(FRONTEND_DIR, "src/views/ContractDetail.vue"),
}
canvas = {}
for name, path in files.items():
    if os.path.exists(path):
        with open(path) as f:
            content = f.read()
        canvas[name] = "ok" if "getCssVars" in content else "hardcoded"
    else:
        canvas[name] = "missing"
results["canvas_theme"] = canvas

# 3. Check cssVar tool
cssvar = os.path.join(FRONTEND_DIR, "src/utils/cssVar.js")
results["cssvar_tool"] = os.path.exists(cssvar)

# 4. Check backend files
results["backend_main"] = os.path.exists(os.path.join(BACKEND_DIR, "main.py"))
results["backend_cleanup"] = os.path.exists(os.path.join(BACKEND_DIR, "cleanup_iv.py"))

# 5. Check accuracy audit
results["accuracy_audit_exists"] = os.path.exists(os.path.join(PROJECT_ROOT, "accuracy_audit.py"))

print(json.dumps(results, ensure_ascii=False, indent=2))
