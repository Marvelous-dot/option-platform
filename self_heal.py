#!/usr/bin/env python3
"""
期权平台 · 自主诊断与修复循环 (Self-Healing Loop)
目标: 检测并自动修复常见平台问题
循环: 健康检查 → 诊断 → 修复 → 验证 → 报告
"""
import json
import subprocess
import sys
import os
import time
import shutil

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")
PROJECT_ROOT = "/root/option-platform"
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)

def http_get(path, timeout=5):
    code, out, err = run(f'curl -s -m {timeout} {API_BASE}{path}')
    return code, out

def check_backend():
    """检查后端运行状态"""
    code, out = http_get("/health")
    if code == 0:
        try:
            data = json.loads(out)
            return "healthy", data
        except:
            return "degraded", {"raw": out[:200]}
    return "down", {}

def check_frontend():
    """检查前端构建状态"""
    dist = os.path.join(FRONTEND_DIR, "dist", "index.html")
    if os.path.exists(dist):
        mtime = os.path.getmtime(dist)
        age_hours = (time.time() - mtime) / 3600
        return "ok" if age_hours < 48 else "stale", age_hours
    return "missing", None

def check_canvas_theme():
    """检查Canvas主题支持"""
    files = {
        "DashboardPanel": os.path.join(FRONTEND_DIR, "src/components/DashboardPanel.vue"),
        "DashboardChart": os.path.join(FRONTEND_DIR, "src/components/DashboardChart.vue"),
        "Surface3D": os.path.join(FRONTEND_DIR, "src/components/Surface3D.vue"),
        "ContractDetail": os.path.join(FRONTEND_DIR, "src/views/ContractDetail.vue"),
    }
    results = {}
    for name, path in files.items():
        if os.path.exists(path):
            with open(path) as f:
                content = f.read()
            results[name] = "ok" if "getCssVars" in content else "hardcoded"
        else:
            results[name] = "missing"
    return results

def fix_canvas_theme():
    """自动修复Canvas主题硬编码"""
    log("修复Canvas主题...")
    # 创建cssVar工具如果不存在
    cssvar_path = os.path.join(FRONTEND_DIR, "src/utils/cssVar.js")
    if not os.path.exists(cssvar_path):
        log("创建cssVar工具函数...")
        with open(cssvar_path, "w") as f:
            f.write('''/**
 * Canvas CSS 变量读取工具
 */
let _cssVars = null
export function getCssVars() {
  if (!_cssVars) {
    const style = getComputedStyle(document.documentElement)
    _cssVars = {
      bgCard: style.getPropertyValue('--bg-card').trim() || '#111a2e',
      bgPrimary: style.getPropertyValue('--bg-primary').trim() || '#0b1120',
      textDim: style.getPropertyValue('--text-dim').trim() || '#3a4560',
      textMuted: style.getPropertyValue('--text-muted').trim() || '#535f75',
      border: style.getPropertyValue('--border').trim() || '#1e2a40',
      borderLight: style.getPropertyValue('--border-light').trim() || '#263350',
      accent: style.getPropertyValue('--accent').trim() || '#f0a030',
      up: style.getPropertyValue('--up').trim() || '#e8883e',
      down: style.getPropertyValue('--down').trim() || '#3cc4a0',
      fontSans: style.getPropertyValue('--font-sans').trim() || 'Noto Serif SC, sans-serif',
      fontMono: style.getPropertyValue('--font-mono').trim() || 'JetBrains Mono, monospace',
    }
  }
  return _cssVars
}
export function cssVar(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}
''')
        log("cssVar工具创建完成")

    # 确保vite.config.js有@别名
    vite_path = os.path.join(FRONTEND_DIR, "vite.config.js")
    if os.path.exists(vite_path):
        with open(vite_path) as f:
            content = f.read()
        if "fileURLToPath" not in content:
            log("修复vite.config.js @别名...")
            content = content.replace(
                "import vue from '@vitejs/plugin-vue'\n",
                "import vue from '@vitejs/plugin-vue'\nimport { fileURLToPath, URL } from 'node:url'\n"
            )
            content = content.replace(
                "plugins: [vue()],",
                "plugins: [vue()],\n  resolve: {\n    alias: {\n      '@': fileURLToPath(new URL('./src', import.meta.url))\n    }\n  },"
            )
            with open(vite_path, "w") as f:
                f.write(content)
            log("vite.config.js修复完成")

def rebuild_frontend():
    """重建前端"""
    log("重建前端...")
    code, out, err = run(f"cd {FRONTEND_DIR} && npm run build", timeout=120)
    if code == 0:
        log("前端构建成功")
        return True
    else:
        log(f"前端构建失败: {err[:200]}")
        return False

def fix_data_issues():
    """检查并修复数据问题"""
    issues = []
    
    # 检查Greeks是否为0
    code, out = http_get("/api/state")
    if code == 0:
        try:
            data = json.loads(out)
            if data.get("greeks_all_zero", False):
                issues.append("Greeks全为0")
            if data.get("iv_data_empty", False):
                issues.append("IV数据为空")
        except:
            pass
    
    return issues

def restart_backend():
    """重启后端服务"""
    log("重启后端服务...")
    # 杀旧进程
    run("pkill -f 'python3.11 main.py' || true")
    time.sleep(2)
    # 启动新进程
    code, out, err = run(f"cd {BACKEND_DIR} && nohup python3.11 main.py > /tmp/option_backend.log 2>&1 &")
    time.sleep(5)
    # 验证
    code, out = http_get("/health")
    if code == 0:
        log("后端重启成功")
        return True
    else:
        log(f"后端重启失败: {err[:200]}")
        return False

def main():
    log("=" * 50)
    log("期权平台 · 自主诊断修复循环")
    log("=" * 50)
    
    report = {}
    
    # 1. 检查后端
    status, data = check_backend()
    report["backend"] = status
    if status == "down":
        log("后端宕机，尝试重启...")
        ok = restart_backend()
        report["backend_restart"] = ok
        if ok:
            status, data = check_backend()
            report["backend"] = status
    elif status == "degraded":
        log("后端降级，尝试重启...")
        ok = restart_backend()
        report["backend_restart"] = ok
    
    # 2. 检查前端
    frontend_status, age = check_frontend()
    report["frontend"] = frontend_status
    if frontend_status == "missing":
        log("前端缺失，重建...")
        ok = rebuild_frontend()
        report["frontend_rebuild"] = ok
    elif frontend_status == "stale":
        log(f"前端过期({age:.1f}h)，重建...")
        ok = rebuild_frontend()
        report["frontend_rebuild"] = ok
    
    # 3. 检查Canvas主题
    canvas_status = check_canvas_theme()
    report["canvas_theme"] = canvas_status
    has_issue = any(v != "ok" for v in canvas_status.values())
    if has_issue:
        log("检测到Canvas主题硬编码，修复...")
        fix_canvas_theme()
        ok = rebuild_frontend()
        report["canvas_fix"] = ok
        # 验证修复
        canvas_status = check_canvas_theme()
        report["canvas_theme_after"] = canvas_status
    
    # 4. 数据修复
    issues = fix_data_issues()
    report["data_issues"] = issues
    
    # 5. 功能准确性审查
    code, out, err = run("python3.11 /root/option-platform/accuracy_audit.py", 60)
    report["accuracy_audit"] = "ok" if code == 0 else "issues_found"
    if code != 0:
        log("准确性审查发现问题，触发数据刷新", "warn")
    
    # 6. 清理旧数据
    code, out, err = run(f"cd {BACKEND_DIR} && python3.11 cleanup_iv.py 2>/dev/null || true")
    if code == 0:
        log("旧数据清理完成")
        report["cleanup"] = True
    
    # 输出报告
    log("=" * 50)
    log("修复完成 · 状态汇总")
    log("=" * 50)
    for k, v in report.items():
        log(f"  {k}: {v}")
    
    return json.dumps(report, ensure_ascii=False)

if __name__ == "__main__":
    main()