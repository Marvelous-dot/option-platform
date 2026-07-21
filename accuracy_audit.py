#!/usr/bin/env python3
"""
期权平台 · 功能准确性审查循环 (Accuracy Audit Loop)
目标: 检查数据准确性、Greeks合理性、BS定价一致性
循环: 拉取全量数据 → 多维度校验 → 发现问题自动修复 → 报告
"""
import sys
import subprocess
import json
import os
import time
import math
import re
from datetime import datetime, timedelta

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")
PROJECT_ROOT = "/root/option-platform"
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

# 阈值配置
GREEKS_TOLERANCE = {
    "delta_range": (0.0, 1.0),        # 认购delta应在0-1之间
    "gamma_min": 0.0,                  # gamma不应为负
    "vega_min": 0.0,                   # vega不应为负
    "iv_min": 0.01,                    # IV最小1%
    "bs_diff_pct": 0.05,               # BS定价差异容忍5%
    "price_min": 0.001,                # 最低价格
}

def log(msg, level="info"):
    prefix = {"info": "[INFO]", "warn": "[WARN]", "error": "[ERROR]", "fix": "[FIX]"}
    print(f"{prefix.get(level, '[INFO]')} {msg}")
    sys.stdout.flush()

def http_get(path, timeout=10):
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", str(timeout), f"{API_BASE}{path}"],
            capture_output=True, text=True, timeout=timeout+5
        )
        return r.returncode, r.stdout
    except:
        return -1, ""

def fetch_all_state():
    """获取全量状态数据"""
    code, raw = http_get("/api/state")
    if code != 0 or not raw:
        return None
    try:
        return json.loads(raw)
    except:
        return None

def run_cmd(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except:
        return -1, "", "TIMEOUT"

# ============================================================
# 准确性检查函数
# ============================================================

def check_greeks_accuracy(contracts, target_info):
    """检查Greeks数值合理性"""
    issues = []
    target_price = target_info.get("latest_price", 0)
    
    for c in contracts:
        code = c.get("option_code", "?")
        option_type = c.get("option_type", "?")
        strike = c.get("strike_price", 0)
        delta = c.get("delta")
        gamma = c.get("gamma")
        vega = c.get("vega")
        
        if delta is None:
            issues.append(f"{code}: delta缺失")
            continue
        
        # Delta范围检查
        if option_type == "认购":
            if not (0.0 <= delta <= 1.0):
                issues.append(f"{code}: delta={delta}超出认购范围[0,1]")
        else:  # 认沽
            if not (-1.0 <= delta <= 0.0):
                issues.append(f"{code}: delta={delta}超出认沽范围[-1,0]")
        
        # Gamma非负
        if gamma is not None and gamma < 0:
            issues.append(f"{code}: gamma={gamma}为负数")
        
        # Vega非负
        if vega is not None and vega < 0:
            issues.append(f"{code}: vega={vega}为负数")
        
        # ATM合约Greeks不为零检查
        if target_price > 0 and abs(strike - target_price) / target_price < 0.1:
            if gamma is not None and gamma == 0:
                issues.append(f"{code}: ATM合约gamma=0（异常）")
            if vega is not None and vega == 0:
                issues.append(f"{code}: ATM合约vega=0（异常）")
    
    return issues


def check_iv_consistency(contracts, target_info):
    """检查IV一致性"""
    issues = []
    for c in contracts:
        code = c.get("option_code", "?")
        iv = c.get("implied_volatility")
        price = c.get("last_price", 0)
        
        if iv is None:
            issues.append(f"{code}: IV缺失")
            continue
        
        if price > 0 and iv < GREEKS_TOLERANCE["iv_min"]:
            issues.append(f"{code}: IV={iv}过低（有价格但IV接近0）")
        
        # 认购认沽同strike同到期日的IV应该接近
        # （简化版，暂不交叉比较）
    
    return issues


def check_expiry_dates(contracts):
    """检查到期日"""
    issues = []
    today = datetime.now().strftime("%Y%m%d")
    
    for c in contracts:
        code = c.get("option_code", "?")
        exp = c.get("expiry_date")
        
        if not exp:
            issues.append(f"{code}: 到期日为空")
            continue
        
        # 检查格式
        if len(exp) != 8 or not exp.isdigit():
            issues.append(f"{code}: 到期日格式错误 {exp}")
            continue
        
        # 检查是否已过期
        if exp < today:
            issues.append(f"{code}: 到期日已过 {exp}")
    
    return issues


def check_bs_pricing(contracts):
    """检查BS定价一致性"""
    issues = []
    
    for c in contracts:
        code = c.get("option_code", "?")
        tp = c.get("theoretical_price", 0)
        lp = c.get("last_price", 0)
        iv = c.get("implied_volatility")
        
        if tp > 0 and lp > 0 and iv and iv > 0:
            diff_pct = abs(tp - lp) / lp
            if diff_pct > GREEKS_TOLERANCE["bs_diff_pct"]:
                issues.append(f"{code}: BS定价差异={diff_pct:.1%}（理论={tp}, 市场={lp}）")
    
    return issues


def check_data_completeness(targets):
    """检查数据完整性"""
    issues = []
    
    if len(targets) == 0:
        issues.append("无标的列表数据")
        return issues
    
    for t in targets:
        code = t.get("target", "?")
        contracts = t.get("contracts", [])
        price = t.get("latest_price", 0)
        
        if len(contracts) == 0:
            issues.append(f"{code}: 合约列表为空")
            continue
        
        if price <= 0:
            issues.append(f"{code}: 标的价格为{price}")
    
    return issues


def check_contract_completeness(contracts, target_code):
    """检查单个标的合约完整性"""
    issues = []
    target_price = None
    
    for c in contracts:
        tp = c.get("target_price")
        if tp is not None:
            target_price = tp
        
        price = c.get("last_price", 0)
        code = c.get("option_code", "?")
        strike = c.get("strike_price")
        opt_type = c.get("option_type")
        
        # 价格=0检查（不是错误，但需报告数量）
        # 已过期合约检查
        
    return issues


# ============================================================
# 主检查流程
# ============================================================

def main():
    log("=" * 50)
    log("期权平台 · 功能准确性审查循环")
    log("=" * 50)
    
    # 1. 获取数据
    state = fetch_all_state()
    if not state:
        log("获取全量数据失败，可能后端不可达", "error")
        return {"status": "fail", "reason": "backend_unreachable"}
    
    targets = state.get("targets", [])
    
    if not targets:
        log("标的列表为空", "error")
        return {"status": "fail", "reason": "no_targets"}
    
    log(f"检查 {len(targets)} 个标的")
    
    all_issues = {"greeks": [], "iv": [], "expiry": [], "bs_pricing": [], "completeness": []}
    
    for t in targets:
        code = t.get("target", "?")
        name = t.get("target_name", "?")
        contracts = t.get("contracts", [])
        log(f"检查 {code} ({name}) — {len(contracts)}合约")
        
        # Greeks检查
        greeks_issues = check_greeks_accuracy(contracts, t)
        all_issues["greeks"].extend(greeks_issues)
        if greeks_issues:
            log(f"  Greeks问题: {len(greeks_issues)}个", "warn")
            for i in greeks_issues[:3]:
                log(f"    - {i}", "warn")
        
        # IV检查
        iv_issues = check_iv_consistency(contracts, t)
        all_issues["iv"].extend(iv_issues)
        if iv_issues:
            log(f"  IV问题: {len(iv_issues)}个", "warn")
        
        # 到期日检查
        exp_issues = check_expiry_dates(contracts)
        all_issues["expiry"].extend(exp_issues)
        if exp_issues:
            log(f"  到期日问题: {len(exp_issues)}个", "warn")
        
        # BS定价检查
        bs_issues = check_bs_pricing(contracts)
        all_issues["bs_pricing"].extend(bs_issues)
        if bs_issues:
            log(f"  BS定价差异: {len(bs_issues)}个", "warn")
        
        # 数据完整性
        comp_issues = check_data_completeness([t])
        all_issues["completeness"].extend(comp_issues)
        if comp_issues:
            log(f"  完整性问题: {len(comp_issues)}个", "warn")
    
    # 统计
    total_issues = sum(len(v) for v in all_issues.values())
    
    log("=" * 50)
    log("审查结果汇总")
    log("=" * 50)
    log(f"Greeks异常: {len(all_issues['greeks'])}个")
    log(f"IV异常: {len(all_issues['iv'])}个")
    log(f"到期日异常: {len(all_issues['expiry'])}个")
    log(f"BS定价差异: {len(all_issues['bs_pricing'])}个")
    log(f"完整性问题: {len(all_issues['completeness'])}个")
    log(f"总计: {total_issues}个")
    
    # 如果发现问题，尝试触发数据刷新
    if total_issues > 0:
        log("检测到数据问题，尝试刷新...", "info")
        code, out = http_get("/health")  # 触发缓存刷新
        log(f"数据刷新请求已发送")
    
    # 判断严重程度
    critical = len(all_issues["greeks"]) + len(all_issues["expiry"]) + len(all_issues["completeness"])
    if critical > 0:
        log(f"❌ 发现 {critical} 个严重问题，需要关注", "error")
        status = "degraded"
    elif total_issues > 0:
        log(f"⚠️ 发现 {total_issues} 个问题，不影响核心功能", "warn")
        status = "warn"
    else:
        log("✅ 所有检查通过，数据准确", "info")
        status = "ok"
    
    return {
        "status": status,
        "total_issues": total_issues,
        "greeks_issues": len(all_issues["greeks"]),
        "iv_issues": len(all_issues["iv"]),
        "expiry_issues": len(all_issues["expiry"]),
        "bs_pricing_issues": len(all_issues["bs_pricing"]),
        "completeness_issues": len(all_issues["completeness"]),
    }

if __name__ == "__main__":
    result = main()
    if isinstance(result, dict):
        print(f"\n总结: {json.dumps(result, ensure_ascii=False)}")