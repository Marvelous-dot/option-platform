#!/usr/bin/env python3
import urllib.request, json, os, sys
from datetime import datetime

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")
GREEKS_TOL = {"delta_range": (0.0,1.0), "gamma_min": 0.0, "vega_min": 0.0, "iv_min": 0.01, "bs_diff_pct": 0.05}

def http(path, timeout=10):
    try:
        req = urllib.request.Request(f"{API_BASE}{path}", headers={"User-Agent":"audit"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as e:
        return None

def check_greeks(contracts, t):
    issues=[]
    price=t.get("latest_price",0)
    for c in contracts:
        code=c.get("option_code","?"); opt=c.get("option_type","?"); delta=c.get("delta")
        gamma=c.get("gamma"); vega=c.get("vega"); strike=c.get("strike_price",0)
        if delta is None: issues.append(f"{code}: delta缺失"); continue
        if opt=="认购" and not(0<=delta<=1): issues.append(f"{code}: delta={delta}超范围")
        elif opt=="认沽" and not(-1<=delta<=0): issues.append(f"{code}: delta={delta}超范围")
        if gamma is not None and gamma<0: issues.append(f"{code}: gamma={gamma}为负")
        if vega is not None and vega<0: issues.append(f"{code}: vega={vega}为负")
        if price>0 and abs(strike-price)/price<0.1:
            if gamma==0: issues.append(f"{code}: ATM gamma=0异常")
            if vega==0: issues.append(f"{code}: ATM vega=0异常")
    return issues

def check_iv(contracts):
    issues=[]
    for c in contracts:
        code=c.get("option_code","?"); iv=c.get("implied_volatility"); p=c.get("last_price",0)
        if iv is None: issues.append(f"{code}: IV缺失"); continue
        if p>0 and iv<0.01: issues.append(f"{code}: IV={iv}过低")
    return issues

def check_expiry(contracts):
    issues=[]; today=datetime.now().strftime("%Y%m%d")
    for c in contracts:
        code=c.get("option_code","?"); exp=c.get("expiry_date")
        if not exp: issues.append(f"{code}: 到期日为空"); continue
        if len(exp)!=8 or not exp.isdigit(): issues.append(f"{code}: 到期日格式错误 {exp}"); continue
        if exp<today: issues.append(f"{code}: 到期日已过 {exp}")
    return issues

def check_bs(contracts):
    issues=[]
    for c in contracts:
        code=c.get("option_code","?"); tp=c.get("theoretical_price",0); lp=c.get("last_price",0); iv=c.get("implied_volatility")
        if tp>0 and lp>0 and iv and iv>0:
            if abs(tp-lp)/lp>0.05: issues.append(f"{code}: BS差异={abs(tp-lp)/lp:.1%}")
    return issues

state=http("/api/state")
if not state:
    print("SUMMARY|FAIL|后端API不可达")
    sys.exit(1)
targets=state.get("targets",[])
if not targets:
    print("SUMMARY|FAIL|标的列表为空")
    sys.exit(1)

all_issues={"greeks":[],"iv":[],"expiry":[],"bs_pricing":[],"completeness":[]}
for t in targets:
    code=t.get("target","?"); name=t.get("target_name","?"); contracts=t.get("contracts",[])
    all_issues["greeks"].extend(check_greeks(contracts,t))
    all_issues["iv"].extend(check_iv(contracts))
    all_issues["expiry"].extend(check_expiry(contracts))
    all_issues["bs_pricing"].extend(check_bs(contracts))
    if len(contracts)==0: all_issues["completeness"].append(f"{code}: 合约列表为空")
    if t.get("latest_price",0)<=0: all_issues["completeness"].append(f"{code}: 标的价格异常")

total=sum(len(v) for v in all_issues.values())
critical=len(all_issues["greeks"])+len(all_issues["expiry"])+len(all_issues["completeness"])
if critical>0: status="degraded"; verdict=f"严重问题 {critical}个"
elif total>0: status="warn"; verdict=f"一般问题 {total}个"
else: status="ok"; verdict="全部通过"

# Trigger data refresh if issues found
if total>0:
    try:
        urllib.request.urlopen(f"{API_BASE}/health", timeout=5)
    except: pass

result={"status":status,"targets":len(targets),"total_issues":total,
        "greeks":len(all_issues["greeks"]),"iv":len(all_issues["iv"]),
        "expiry":len(all_issues["expiry"]),"bs_pricing":len(all_issues["bs_pricing"]),
        "completeness":len(all_issues["completeness"]),"verdict":verdict,
        "details":all_issues}
print("SUMMARY|JSON|"+json.dumps(result, ensure_ascii=False))