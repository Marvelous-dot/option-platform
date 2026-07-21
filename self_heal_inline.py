import sys
import subprocess
import os
import json
import time

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")
PROJECT_ROOT = "/root/option-platform"
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def http_get(path, timeout=5):
    code, out, err = run(f'curl -s -m {timeout} {API_BASE}{path}')
    return code, out

def main():
    report = {}
    fixes = []
    failures = []

    # 1. Check backend
    code, out = http_get("/health")
    if code == 0:
        try:
            data = json.loads(out)
            status = "healthy"
        except:
            status = "degraded"
    else:
        status = "down"
    report["backend"] = status

    if status == "down":
        print("Backend down, restarting...")
        run("pkill -f 'python3.11 main.py' || true")
        time.sleep(2)
        run(f"cd {BACKEND_DIR} && nohup python3.11 main.py > /tmp/option_backend.log 2>&1 &")
        time.sleep(5)
        code, out = http_get("/health")
        if code == 0:
            report["backend"] = "healthy"
            fixes.append("重启后端服务")
        else:
            report["backend"] = "down"
            failures.append("重启后端失败")

    # 2. Check frontend
    dist = os.path.join(FRONTEND_DIR, "dist", "index.html")
    if os.path.exists(dist):
        mtime = os.path.getmtime(dist)
        age_hours = (time.time() - mtime) / 3600
        frontend_status = "ok" if age_hours < 48 else "stale"
    else:
        frontend_status = "missing"
    report["frontend"] = frontend_status

    if frontend_status in ("missing", "stale"):
        print(f"Frontend {frontend_status}, rebuilding...")
        code, out, err = run(f"cd {FRONTEND_DIR} && npm run build", timeout=120)
        if code == 0:
            fixes.append("重建前端")
        else:
            failures.append("前端重建失败")

    # 3. Check canvas theme
    files = {
        "DashboardPanel": os.path.join(FRONTEND_DIR, "src/components/DashboardPanel.vue"),
        "DashboardChart": os.path.join(FRONTEND_DIR, "src/components/DashboardChart.vue"),
        "Surface3D": os.path.join(FRONTEND_DIR, "src/components/Surface3D.vue"),
        "ContractDetail": os.path.join(FRONTEND_DIR, "src/views/ContractDetail.vue"),
    }
    canvas_results = {}
    for name, path in files.items():
        if os.path.exists(path):
            with open(path) as f:
                content = f.read()
            canvas_results[name] = "ok" if "getCssVars" in content else "hardcoded"
        else:
            canvas_results[name] = "missing"
    report["canvas_theme"] = canvas_results

    has_canvas_issue = any(v != "ok" for v in canvas_results.values())
    if has_canvas_issue:
        print("Canvas theme issue, fixing...")
        cssvar_path = os.path.join(FRONTEND_DIR, "src/utils/cssVar.js")
        if not os.path.exists(cssvar_path):
            with open(cssvar_path, "w") as f:
                f.write('''let _cssVars = null\nexport function getCssVars() {\n  if (!_cssVars) {\n    const style = getComputedStyle(document.documentElement)\n    _cssVars = {\n      bgCard: style.getPropertyValue('--bg-card').trim() || '#111a2e',\n      bgPrimary: style.getPropertyValue('--bg-primary').trim() || '#0b1120',\n      textDim: style.getPropertyValue('--text-dim').trim() || '#3a4560',\n      textMuted: style.getPropertyValue('--text-muted').trim() || '#535f75',\n      border: style.getPropertyValue('--border').trim() || '#1e2a40',\n      borderLight: style.getPropertyValue('--border-light').trim() || '#263350',\n      accent: style.getPropertyValue('--accent').trim() || '#f0a030',\n      up: style.getPropertyValue('--up').trim() || '#e8883e',\n      down: style.getPropertyValue('--down').trim() || '#3cc4a0',\n      fontSans: style.getPropertyValue('--font-sans').trim() || 'Noto Serif SC, sans-serif',\n      fontMono: style.getPropertyValue('--font-mono').trim() || 'JetBrains Mono, monospace',\n    }\n  }\n  return _cssVars\n}\n''')
        fixes.append("创建cssVar工具")
        code, out, err = run(f"cd {FRONTEND_DIR} && npm run build", timeout=120)
        if code == 0:
            fixes.append("Canvas主题修复并重建前端")
        else:
            failures.append("Canvas主题修复后前端重建失败")

    # 4. Data issues
    code, out = http_get("/api/state")
    data_issues = []
    if code == 0:
        try:
            data = json.loads(out)
            if data.get("greeks_all_zero"):
                data_issues.append("Greeks全为0")
            if data.get("iv_data_empty"):
                data_issues.append("IV数据为空")
        except:
            pass
    report["data_issues"] = data_issues

    # 5. Accuracy audit
    code, out, err = run("python3.11 /root/option-platform/accuracy_audit.py", 60)
    report["accuracy_audit"] = "ok" if code == 0 else "issues_found"

    # 6. Cleanup
    code, out, err = run(f"cd {BACKEND_DIR} && python3.11 cleanup_iv.py 2>/dev/null || true")
    report["cleanup"] = code == 0

    # Output report
    print("=" * 50)
    print("修复完成 · 状态汇总")
    print("=" * 50)
    for k, v in report.items():
        print(f"  {k}: {v}")
    print(f"\n修复项: {fixes}")
    print(f"失败项: {failures}")

main()
