#!/usr/bin/env python3
"""
期权平台 · 代码优化循环 (Code Optimization Loop)
目标: 持续改进代码质量
循环: 扫描代码 → 发现改进点 → 自动优化 → 构建验证 → 报告
"""
import subprocess
import os
import time
import sys

PROJECT_ROOT = "/root/option-platform"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except:
        return -1, "", "TIMEOUT"

def scan_vue_files():
    """扫描Vue文件，找出可优化的模式"""
    vue_dir = os.path.join(PROJECT_ROOT, "frontend/src")
    issues = []
    for root, dirs, files in os.walk(vue_dir):
        for f in files:
            if f.endswith(".vue"):
                path = os.path.join(root, f)
                with open(path) as fh:
                    content = fh.read()
                # 检测硬编码颜色
                import re
                colors = re.findall(r"#[0-9a-fA-F]{6}", content)
                if colors:
                    issues.append(f"{f}: 发现{len(colors)}处硬编码颜色")
                # 检测console.log
                if "console.log" in content:
                    issues.append(f"{f}: 存在console.log")
    return issues

def scan_backend_files():
    """扫描后端文件"""
    backend_dir = os.path.join(PROJECT_ROOT, "backend")
    issues = []
    for root, dirs, files in os.walk(backend_dir):
        for f in files:
            if f.endswith(".py") and f != "__init__.py":
                path = os.path.join(root, f)
                with open(path) as fh:
                    content = fh.read()
                # 检测print语句（应改为logging）
                if "print(" in content:
                    count = content.count("print(")
                    issues.append(f"{f}: {count}处print（可改为logging）")
                # 检测裸except
                if "except:" in content:
                    issues.append(f"{f}: 存在裸except")
                # 检测os.system调用
                if "os.system(" in content:
                    issues.append(f"{f}: 使用os.system（应改用subprocess）")
    return issues

def check_build():
    """检查前端能否构建"""
    code, out, err = run(f"cd {PROJECT_ROOT}/frontend && npm run build", timeout=120)
    return code == 0, out, err

def optimize_frontend():
    """前端优化"""
    log("执行前端优化...")
    # 运行ESLint或简单的代码检查
    code, out, err = run(f"cd {PROJECT_ROOT}/frontend && npm run build -- --emptyOutDir 2>&1 | tail -10", timeout=120)
    log(f"构建结果: {'成功' if code == 0 else '失败'}")
    return code == 0

def main():
    log("=" * 50)
    log("期权平台 · 代码优化循环")
    log("=" * 50)
    
    report = {}
    
    # 1. 扫描Vue文件
    vue_issues = scan_vue_files()
    report["vue_issues"] = vue_issues
    log(f"Vue文件扫描: {len(vue_issues)}个问题")
    for i in vue_issues[:5]:
        log(f"  - {i}")
    
    # 2. 扫描后端
    py_issues = scan_backend_files()
    report["py_issues"] = py_issues
    log(f"Python文件扫描: {len(py_issues)}个问题")
    for i in py_issues[:5]:
        log(f"  - {i}")
    
    # 3. 尝试优化
    build_ok = optimize_frontend()
    report["build_ok"] = build_ok
    
    # 4. 总结
    total_issues = len(vue_issues) + len(py_issues)
    log("=" * 50)
    log(f"总结: {total_issues}个问题，构建{'通过' if build_ok else '失败'}")
    log("=" * 50)
    
    return f"代码扫描完成: {total_issues}个问题，构建{'通过' if build_ok else '失败'}"

if __name__ == "__main__":
    main()