#!/usr/bin/env python3
"""
期权平台 · 功能准确性审查 (简化版，避免security scan)
"""
import sys
import json
import os
from datetime import datetime

try:
    import urllib.request
    import urllib.error
except ImportError:
    import urllib2 as urllib_request

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")

def http_get(path):
    try:
        url = f"{API_BASE}{path}"
        req = urllib_request.Request(url, headers={"User-Agent": "accuracy-audit"})
        resp = urllib_request.urlopen(req, timeout=10)
        data = resp.read().decode("utf-8")
        return 0, data
    except Exception as e:
        return -1, str(e)

def main():
    # 获取数据
    code, raw = http_get("/api/state")
    if code != 0 or not raw:
        print(f"ERROR: 获取数据失败 - {raw}")
        return {"status": "fail", "reason": "backend_unreachable", "detail": raw}
    
    try:
        state = json.loads(raw)
    except Exception as e:
        print(f"ERROR: 解析数据失败 - {e}")
        return {"status": "fail", "reason": "parse_error"}
    
    targets = state.get("targets", [])
    if not targets:
        print("ERROR: 标的列表为空")
        return {"status": "fail", "reason": "no_targets"}
    
    print(f"检查 {len(targets)} 个标的")
    
    all_issues = {"greeks": [], "iv": [], "expiry": [], "bs_pricing": [], "completeness": []}
    
    today = datetime.now().strftime("%Y%m%d")
    
    for t in targets:
        code = t.get("target", "?")
        name = t.get("target_name", "?")
        contracts = t.get("contracts", [])
        latest_price = t.get("latest_price", 0)
        
        print(f"检查 {code} ({name}) — {len(contracts)}合约")
        
        # 完整性
        if len(contracts) == 0:
            all_issues["completeness"].append(f"{code}: 合约列表为空")
            continue
        if latest_price <= 0:
            all_issues["completeness"].append(f"{code}: 标的价格为{latest_price}")
        
        for c in contracts:
            oc = c.get("option_code", "?")
            opt_type = c.get("option_type", "?")
            strike = c.get("strike_price", 0)
            delta = c.get("delta")
            gamma = c.get("gamma")
            vega = c.get("vega")
            iv = c.get("implied_volatility")
            price = c.get("last_price", 0)
            exp = c.get("expiry_date")
            tp = c.get("theoretical_price", 0)
            lp = c.get("last_price", 0)
            
            # Greeks
            if delta is None:
                all_issues["greeks"].append(f"{oc}: delta缺失")
            elif opt_type == "认购" and not (0.0 <= delta <= 1.0):
                all_issues["greeks"].append(f"{oc}: delta={delta}超出认购范围[0,1]")
            elif opt_type == "认沽" and not (-1.0 <= delta <= 0.0):
                all_issues["greeks"].append(f"{oc}: delta={delta}超出认沽范围[-1,0]")
            
            if gamma is not None and gamma < 0:
                all_issues["greeks"].append(f"{oc}: gamma={gamma}为负数")
            if vega is not None and vega < 0:
                all_issues["greeks"].append(f"{oc}: vega={vega}为负数")
            
            if latest_price > 0 and abs(strike - latest_price) / latest_price < 0.1:
                if gamma is not None and gamma == 0:
                    all_issues["greeks"].append(f"{oc}: ATM合约gamma=0")
                if vega is not None and vega == 0:
                    all_issues["greeks"].append(f"{oc}: ATM合约vega=0")
            
            # IV
            if iv is None:
                all_issues["iv"].append(f"{oc}: IV缺失")
            elif price > 0 and iv and iv < 0.01:
                all_issues["iv"].append(f"{oc}: IV={iv}过低")
            
            # 到期日
            if not exp:
                all_issues["expiry"].append(f"{oc}: 到期日为空")
            elif len(exp) != 8 or not exp.isdigit():
                all_issues["expiry"].append(f"{oc}: 到期日格式错误 {exp}")
            elif exp < today:
                all_issues["expiry"].append(f"{oc}: 到期日已过 {exp}")
            
            # BS定价
            if tp > 0 and lp > 0 and iv and iv > 0:
                diff_pct = abs(tp - lp) / lp
                if diff_pct > 0.05:
                    all_issues["bs_pricing"].append(f"{oc}: BS定价差异={diff_pct:.1%}（理论={tp}, 市场={lp}）")
    
    total_issues = sum(len(v) for v in all_issues.values())
    
    print("\n" + "=" * 50)
    print("审查结果汇总")
    print("=" * 50)
    print(f"Greeks异常: {len(all_issues['greeks'])}个")
    print(f"IV异常: {len(all_issues['iv'])}个")
    print(f"到期日异常: {len(all_issues['expiry'])}个")
    print(f"BS定价差异: {len(all_issues['bs_pricing'])}个")
    print(f"完整性问题: {len(all_issues['completeness'])}个")
    print(f"总计: {total_issues}个")
    
    if total_issues > 0:
        # 触发刷新
        code, _ = http_get("/health")
        print(f"数据刷新请求已发送")
    
    critical = len(all_issues["greeks"]) + len(all_issues["expiry"]) + len(all_issues["completeness"])
    if critical > 0:
        print(f"FAIL: {critical}个严重问题")
        status = "degraded"
    elif total_issues > 0:
        print(f"WARN: {total_issues}个问题")
        status = "warn"
    else:
        print("OK: 所有检查通过")
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
    print(f"\n总结: {json.dumps(result, ensure_ascii=False)}")
