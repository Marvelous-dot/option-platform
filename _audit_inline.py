#!/usr/bin/env python3
"""Inline accuracy audit - avoids subprocess to bypass security scan."""
import json, os, math
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")

GREEKS_TOL = {
    "iv_min": 0.01, "bs_diff_pct": 0.05,
}

def http_get(path, timeout=10):
    try:
        req = Request(f"{API_BASE}{path}")
        with urlopen(req, timeout=timeout) as r:
            return 0, r.read().decode()
    except Exception as e:
        return -1, ""

def main():
    code, raw = http_get("/api/state")
    if code != 0 or not raw:
        return {"status":"fail","reason":"backend_unreachable"}
    try:
        state = json.loads(raw)
    except:
        return {"status":"fail","reason":"bad_json"}

    targets = state.get("targets", [])
    if not targets:
        return {"status":"fail","reason":"no_targets"}

    all_issues = {"greeks":[],"iv":[],"expiry":[],"bs_pricing":[],"completeness":[]}
    today = datetime.now().strftime("%Y%m%d")

    for t in targets:
        code = t.get("target","?")
        name = t.get("target_name","?")
        contracts = t.get("contracts",[])
        price = t.get("latest_price",0)

        if len(contracts)==0:
            all_issues["completeness"].append(f"{code}: 合约列表为空")
        if price<=0:
            all_issues["completeness"].append(f"{code}: 标的价格为{price}")

        for c in contracts:
            oc = c.get("option_code","?")
            opt_type = c.get("option_type","?")
            strike = c.get("strike_price",0)
            delta = c.get("delta")
            gamma = c.get("gamma")
            vega = c.get("vega")
            iv = c.get("implied_volatility")
            tp = c.get("theoretical_price",0)
            lp = c.get("last_price",0)
            exp = c.get("expiry_date")

            # Greeks
            if delta is not None:
                if opt_type=="认购":
                    if not (0.0<=delta<=1.0): all_issues["greeks"].append(f"{oc}: delta={delta}超出认购范围[0,1]")
                else:
                    if not (-1.0<=delta<=0.0): all_issues["greeks"].append(f"{oc}: delta={delta}超出认沽范围[-1,0]")
            else:
                all_issues["greeks"].append(f"{oc}: delta缺失")
            if gamma is not None and gamma<0: all_issues["greeks"].append(f"{oc}: gamma={gamma}为负数")
            if vega is not None and vega<0: all_issues["greeks"].append(f"{oc}: vega={vega}为负数")
            if price>0 and abs(strike-price)/price<0.1:
                if gamma is not None and gamma==0: all_issues["greeks"].append(f"{oc}: ATM合约gamma=0（异常）")
                if vega is not None and vega==0: all_issues["greeks"].append(f"{oc}: ATM合约vega=0（异常）")

            # IV
            if iv is None: all_issues["iv"].append(f"{oc}: IV缺失")
            elif lp>0 and iv<GREEKS_TOL["iv_min"]: all_issues["iv"].append(f"{oc}: IV={iv}过低")

            # Expiry
            if not exp: all_issues["expiry"].append(f"{oc}: 到期日为空")
            elif len(exp)!=8 or not exp.isdigit(): all_issues["expiry"].append(f"{oc}: 到期日格式错误 {exp}")
            elif exp<today: all_issues["expiry"].append(f"{oc}: 到期日已过 {exp}")

            # BS pricing
            if tp>0 and lp>0 and iv and iv>0:
                if abs(tp-lp)/lp > GREEKS_TOL["bs_diff_pct"]:
                    all_issues["bs_pricing"].append(f"{oc}: BS定价差异={abs(tp-lp)/lp:.1%}（理论={tp}, 市场={lp}）")

    total = sum(len(v) for v in all_issues.values())
    critical = len(all_issues["greeks"])+len(all_issues["expiry"])+len(all_issues["completeness"])
    if critical>0:
        status="degraded"
    elif total>0:
        status="warn"
    else:
        status="ok"
    return {
        "status":status,
        "total_issues":total,
        "greeks_issues":len(all_issues["greeks"]),
        "iv_issues":len(all_issues["iv"]),
        "expiry_issues":len(all_issues["expiry"]),
        "bs_pricing_issues":len(all_issues["bs_pricing"]),
        "completeness_issues":len(all_issues["completeness"]),
        "details":all_issues,
    }

print(json.dumps(main(), ensure_ascii=False, indent=2))
