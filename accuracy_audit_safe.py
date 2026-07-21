#!/usr/bin/env python3
"""accuracy_audit.py safe wrapper - uses urllib instead of subprocess"""
import urllib.request
import json
import os, sys, math
from datetime import datetime

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")

GREEKS_TOLERANCE = {
    "delta_range": (0.0, 1.0),
    "gamma_min": 0.0,
    "vega_min": 0.0,
    "iv_min": 0.01,
    "bs_diff_pct": 0.05,
    "price_min": 0.001,
}

def safe_http(path, timeout=10):
    try:
        req = urllib.request.Request(f"{API_BASE}{path}", headers={"User-Agent": "audit"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read().decode())
        return data
    except Exception as e:
        return None

def check_greeks(contracts, target_info):
    issues = []
    price = target_info.get("latest_price", 0)
    for c in contracts:
        code = c.get("option_code", "?")
        opt_type = c.get("option_type", "?")
        delta = c.get("delta")
        gamma = c.get("gamma")
        vega = c.get("vega")
        strike = c.get("strike_price", 0)
        if delta is None:
            issues.append(f"{code}: delta缺失")
            continue
        if opt_type == "认购":
            if not (0.0 <= delta <= 1.0):
                issues.append(f"{code}: delta={delta}超出认购范围[0,1]")
        else:
            if not (-1.0 <= delta <= 0.0):
                issues.append(f"{code}: delta={delta}超出认沽范围[-1,0]")
        if gamma is not None and gamma < 0:
            issues.append(f"{code}: gamma={gamma}为负数")
        if vega is not None and vega < 0:
            issues.append(f"{code}: vega={vega}为负数")
        if price > 0 and abs(strike - price) / price < 0.1:
            if gamma is not None and gamma == 0:
                issues.append(f"{code}: ATM合约gamma=0异常")
            if vega is not None and vega == 0:
                issues.append(f"{code}: ATM合约vega=0异常")
    return issues

def check_iv(contracts):
    issues = []
    for c in contracts:
        code = c.get("option_code", "?")
        iv = c.get("implied_volatility")
        price = c.get("last_price", 0)
        if iv is None:
            issues.append(f"{code}: IV缺失")
            continue
        if price > 0 and iv < 0.01:
            issues.append(f"{code}: IV={iv}过低")
    return issues

def check_expiry(contracts):
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
            if diff_pct > 0.05:
                issues.append(f"{code}: BS定价差异={diff_pct:.1%}(理论={tp},市场={lp})")
    return issues

def main():
    state = safe_http("/api/state")
    if not state:
        print("SUMMARY|FAIL|无法连接后端API")
        return
    targets = state.get("targets", [])
    if not targets:
        print("SUMMARY|FAIL|标的列表为空")
        return
    
    all_issues = {"greeks": [], "iv": [], "expiry": [], "bs_pricing": [], "completeness": []}
    
    for t in targets:
        code = t.get("target", "?")
        name = t.get("target_name", "?")
        contracts = t.get("contracts", [])
        
        g = check_greeks(contracts, t)
        all_issues["greeks"].extend(g)
        iv = check_iv(contracts)
        all_issues["iv"].extend(iv)
        e = check_expiry(contracts)
        all_issues["expiry"].extend(e)
        bs = check_bs_pricing(contracts)
        all_issues["bs_pricing"].extend(bs)
        
        if len(contracts) == 0:
            all_issues["completeness"].append(f"{code}: 合约列表为空")
        if t.get("latest_price", 0) <= 0:
            all_issues["completeness"].append(f"{code}: 标的价格异常")
    
    total = sum(len(v) for v in all_issues.values())
    critical = len(all_issues["greeks"]) + len(all_issues["expiry"]) + len(all_issues["completeness"])
    
    if critical > 0:
        status = "degraded"
        verdict = f"❌ 严重问题 {critical}个"
    elif total > 0:
        status = "warn"
        verdict = f"⚠️ 一般问题 {total}个"
    else:
        status = "ok"
        verdict = "✅ 全部通过"
    
    result = {
        "status": status,
        "targets_checked": len(targets),
        "total_issues": total,
        "greeks_issues": len(all_issues["greeks"]),
        "iv_issues": len(all_issues["iv"]),
        "expiry_issues": len(all_issues["expiry"]),
        "bs_pricing_issues": len(all_issues["bs_pricing"]),
        "completeness_issues": len(all_issues["completeness"]),
        "verdict": verdict,
        "details": all_issues,
    }
    print("SUMMARY|JSON|" + json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
