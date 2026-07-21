#!/usr/bin/env python3
"""期权平台健康检查脚本 - 自动诊断数据质量、性能、前端构建状态"""
import json
import subprocess
import sys
import os
import time

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")

def http_get(path):
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "5", f"{API_BASE}{path}"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout, result.returncode
    except:
        return "", -1

def check_health():
    """基础健康检查"""
    resp, code = http_get("/health")
    if code != 0:
        return "❌ 后端不可达"
    try:
        data = json.loads(resp)
        contracts = data.get("contracts", 0)
        last = data.get("last_updated", "?")
        return f"✅ 后端正常 ({contracts}合约, 更新:{last})"
    except:
        return f"❌ 健康检查返回异常: {resp[:100]}"

def check_frontend():
    """前端构建状态"""
    dist_path = "/root/option-platform/frontend/dist/index.html"
    if os.path.exists(dist_path):
        mtime = os.path.getmtime(dist_path)
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 24:
            return f"✅ 前端已构建 (24h内, {age_hours:.1f}h前)"
        else:
            return f"⚠️ 前端需重新构建 ({age_hours:.0f}h前构建)"
    else:
        return "❌ 前端未构建"

def check_data_quality():
    """数据质量检查"""
    checks = []
    
    # 检查合约数据
    resp, code = http_get("/api/state")
    if code == 0:
        try:
            data = json.loads(resp)
            total = data.get("total_contracts", 0)
            if total > 500:
                checks.append(f"✅ 合约数: {total}")
            else:
                checks.append(f"⚠️ 合约数偏少: {total}")
            
            status = data.get("status", "?")
            if status == "idle":
                checks.append("✅ 数据状态: 正常")
            else:
                checks.append(f"⚠️ 数据状态: {status}")
        except:
            checks.append("❌ state API 解析失败")
    else:
        checks.append("❌ state API 不可达")
    
    # 检查标的列表
    resp, code = http_get("/api/targets")
    if code == 0:
        try:
            data = json.loads(resp)
            targets = data if isinstance(data, list) else data.get("targets", [])
            checks.append(f"✅ 标的数: {len(targets)}")
        except:
            checks.append("❌ targets API 解析失败")
    
    return "\n".join(checks)

def check_canvas_theme():
    """检查Canvas主题CSS变量是否已接入"""
    files = [
        "/root/option-platform/frontend/src/components/DashboardPanel.vue",
        "/root/option-platform/frontend/src/components/DashboardChart.vue",
        "/root/option-platform/frontend/src/components/Surface3D.vue",
        "/root/option-platform/frontend/src/views/ContractDetail.vue",
    ]
    results = []
    for f in files:
        if os.path.exists(f):
            with open(f) as fh:
                content = fh.read()
            if "getCssVars" in content:
                results.append(f"✅ {os.path.basename(f)}: 已接入CSS变量")
            else:
                results.append(f"❌ {os.path.basename(f)}: 未接入CSS变量")
        else:
            results.append(f"❌ {os.path.basename(f)}: 文件不存在")
    return "\n".join(results)

def main():
    print("=" * 50)
    print("海疆期权平台 · 健康检查报告")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    print()
    print(check_health())
    print(check_frontend())
    print()
    print("--- 数据质量 ---")
    print(check_data_quality())
    print()
    print("--- Canvas主题支持 ---")
    print(check_canvas_theme())
    print()
    print("=" * 50)

if __name__ == "__main__":
    main()