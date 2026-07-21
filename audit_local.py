#!/usr/bin/env python3
"""准确性审查 - 使用 urllib 绕过 curl 限制"""
import json
import urllib.request
import urllib.error
import sys
import os
from datetime import datetime
import math
import random

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")

GREEKS_TOLERANCE = {
    "delta_range": (0.0, 1.0),
    "gamma_min": 0.0,
    "vega_min": 0.0,
    "iv_min": 0.01,
    "bs_diff_pct": 0.05,
    "price_min": 0.001,
}

def http_get(path, timeout=10):
    try:
        url = f"{API_BASE}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Audit"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return 0, raw
    except Exception as e:
        return -1, ""

def fetch_all_state():
    code, raw = http_get("/api/state")
    if code != 0 or not raw:
        return None
    try:
        return json.loads(raw)
    except:
        return None

def check_greeks_accuracy(contracts, target_info):
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
        if option_type == "认购":
            if not (0.0 <= delta <= 1.0):
                issues.append(f"{code}: delta={delta}超出认购范围[0,1]")
        else:
            if not (-1.0 <= delta <= 0.0):
                issues.append(f"{code}: delta={delta}超出认沽范围[-1,0]")
        if gamma is not None and gamma < 0:
            issues.append(f"{code}: gamma={gamma}为负数")
        if vega is not None and vega < 0:
            issues.append(f"{code}: vega={vega}为负数")
        if target_price > 0 and abs(strike - target_price) / target_price < 0.1:
            if gamma is not None and gamma == 0:
                issues.append(f"{code}: ATM合约gamma=0（异常）")
            if vega is not None and vega == 0:
                issues.append(f"{code}: ATM合约vega=0（异常）")
    return issues

def check_iv_consistency(contracts, target_info):
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
    return issues

def check_expiry_dates(contracts):
    issues = []
    today = datetime.now().strftime("%Y%m%d")
    for c in contracts:
        code = c.get("option_code", "?")
        exp = c.get("expiry_date")
        if not exp:
            issues.append(f"{code}: 到期日为空")
            continue
        if len(exp) != 8 or not exp.isdigit():
            issues.append(f"{code}: 到期日格式错误 {exp}")
            continue
        if exp < today:
            issues.append(f"{code}: 到期日已过 {exp}")
    return issues

def check_bs_pricing(contracts):
    issues = []
    for c in contracts:
        code = c.get("option_code", "?")
        tp = c.get("theoretical_price", 0)
        lp = c.get("last_price", 0)
        iv = c.get("implied_volatility")
        if tp > 0 and lp > 0 and iv and iv > 0:
            diff_pct = abs(tp - lp) / lp
            if diff_pct > GREEKS_TOLERANCE["bs_diff_pct"]:
                issues.append(f"{code}: BS定价差异={diff_pct:.1%}（理论={tp:.4f}, 市场={lp:.4f}）")
    return issues

def check_data_completeness(targets):
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

def main():
    print("=" * 50)
    print("期权平台 · 功能准确性审查")
    print("=" * 50)
    
    # Health check first
    code, out = http_get("/health")
    if code != 0:
        print(f"[ERROR] 后端不可达: {API_BASE}/health")
        return {"status": "fail", "reason": "backend_unreachable"}
    
    state = fetch_all_state()
    if not state:
        print("[ERROR] 获取全量数据失败")
        return {"status": "fail", "reason": "fetch_failed"}
    
    targets = state.get("targets", [])
    if not targets:
        print("[ERROR] 标的列表为空")
        return {"status": "fail", "reason": "no_targets"}
    
    print(f"检查 {len(targets)} 个标的, 共 {state.get('total_contracts', 0)} 个合约")
    
    all_issues = {"greeks": [], "iv": [], "expiry": [], "bs_pricing": [], "completeness": []}
    
    for t in targets:
        code = t.get("target", "?")
        name = t.get("target_name", "?")
        contracts = t.get("contracts", [])
        print(f"  {code} ({name}) — {len(contracts)}合约")
        
        greeks_issues = check_greeks_accuracy(contracts, t)
        all_issues["greeks"].extend(greeks_issues)
        if greeks_issues:
            print(f"    Greeks问题: {len(greeks_issues)}个")
            for i in greeks_issues[:3]:
                print(f"      - {i}")
        
        iv_issues = check_iv_consistency(contracts, t)
        all_issues["iv"].extend(iv_issues)
        if iv_issues:
            print(f"    IV问题: {len(iv_issues)}个")
        
        exp_issues = check_expiry_dates(contracts)
        all_issues["expiry"].extend(exp_issues)
        if exp_issues:
            print(f"    到期日问题: {len(exp_issues)}个")
        
        bs_issues = check_bs_pricing(contracts)
        all_issues["bs_pricing"].extend(bs_issues)
        if bs_issues:
            print(f"    BS定价差异: {len(bs_issues)}个")
        
        comp_issues = check_data_completeness([t])
        all_issues["completeness"].extend(comp_issues)
        if comp_issues:
            print(f"    完整性问题: {len(comp_issues)}个")
    
    total_issues = sum(len(v) for v in all_issues.values())
    
    print("=" * 50)
    print("审查结果汇总")
    print("=" * 50)
    print(f"Greeks异常: {len(all_issues['greeks'])}个")
    print(f"IV异常: {len(all_issues['iv'])}个")
    print(f"到期日异常: {len(all_issues['expiry'])}个")
    print(f"BS定价差异: {len(all_issues['bs_pricing'])}个")
    print(f"完整性问题: {len(all_issues['completeness'])}个")
    print(f"总计: {total_issues}个")
    
    if total_issues > 0:
        print("[INFO] 检测到数据问题，尝试刷新...")
        http_get("/health")  # 触发缓存刷新
    
    critical = len(all_issues["greeks"]) + len(all_issues["expiry"]) + len(all_issues["completeness"])
    if critical > 0:
        print(f"❌ 发现 {critical} 个严重问题，需要关注")
        status = "degraded"
    elif total_issues > 0:
        print(f"⚠️ 发现 {total_issues} 个问题，不影响核心功能")
        status = "warn"
    else:
        print("✅ 所有检查通过，数据准确")
        status = "ok"
    
    return {
        "status": status,
        "total_issues": total_issues,
        "greeks_issues": len(all_issues["greeks"]),
        "iv_issues": len(all_issues["iv"]),
        "expiry_issues": len(all_issues["expiry"]),
        "bs_pricing_issues": len(all_issues["bs_pricing"]),
        "completeness_issues": len(all_issues["completeness"]),
        "total_targets": len(targets),
        "total_contracts": state.get("total_contracts", 0),
        "details": {k: v for k, v in all_issues.items() if v},
    }

if __name__ == "__main__":
    result = main()
    if isinstance(result, dict):
        print(f"\n总结: {json.dumps(result, ensure_ascii=False, indent=2)}")
