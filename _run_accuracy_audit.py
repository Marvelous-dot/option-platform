#!/usr/bin/env python3
"""Audit runner using urllib only - no subprocess"""
import urllib.request
import json, os, sys
from datetime import datetime

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")

def get(path):
    try:
        req = urllib.request.Request(f"{API_BASE}{path}", headers={"User-Agent": "audit"})
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read().decode())
    except:
        return None

def main():
    state = get("/api/state")
    if not state:
        print("SUMMARY|FAIL|后端不可达 (localhost:8000)")
        return
    
    targets = state.get("targets", [])
    if not targets:
        print("SUMMARY|FAIL|标的列表为空")
        return
    
    greeks, ivs, expiry, bs, comp = [], [], [], [], []
    today = datetime.now().strftime("%Y%m%d")
    
    for t in targets:
        code = t.get("target","?")
        name = t.get("target_name","?")
        contracts = t.get("contracts",[])
        price = t.get("latest_price",0)
        
        if not contracts:
            comp.append(f"{code}: 合约列表为空")
        if price <= 0:
            comp.append(f"{code}: 标的价格为{price}")
        
        for c in contracts:
            oc = c.get("option_code","?")
            otype = c.get("option_type","?")
            strike = c.get("strike_price",0)
            delta = c.get("delta")
            gamma = c.get("gamma")
            vega = c.get("vega")
            imp = c.get("implied_volatility")
            tp = c.get("theoretical_price",0)
            lp = c.get("last_price",0)
            exp = c.get("expiry_date")
            
            # Greeks
            if delta is None: greeks.append(f"{oc}: delta缺失")
            elif otype=="认购" and not(0<=delta<=1): greeks.append(f"{oc}: delta={delta}超认购范围")
            elif otype=="认沽" and not(-1<=delta<=0): greeks.append(f"{oc}: delta={delta}超认沽范围")
            if gamma is not None and gamma<0: greeks.append(f"{oc}: gamma={gamma}为负")
            if vega is not None and vega<0: greeks.append(f"{oc}: vega={vega}为负")
            if price>0 and abs(strike-price)/price<0.1:
                if gamma is not None and gamma==0: greeks.append(f"{oc}: ATM gamma=0异常")
                if vega is not None and vega==0: greeks.append(f"{oc}: ATM vega=0异常")
            
            # IV
            if imp is None: ivs.append(f"{oc}: IV缺失")
            elif lp>0 and imp<0.01: ivs.append(f"{oc}: IV={imp}过低")
            
            # Expiry
            if not exp: expiry.append(f"{oc}: 到期日为空")
            elif len(exp)!=8 or not exp.isdigit(): expiry.append(f"{oc}: 到期日格式错误 {exp}")
            elif exp<today: expiry.append(f"{oc}: 到期日已过 {exp}")
            
            # BS pricing
            if tp>0 and lp>0 and imp and imp>0:
                diff = abs(tp-lp)/lp
                if diff>0.05: bs.append(f"{oc}: BS差异={diff:.1%}(理论={tp},市场={lp})")
    
    total = len(greeks)+len(ivs)+len(expiry)+len(bs)+len(comp)
    crit = len(greeks)+len(expiry)+len(comp)
    
    if crit>0: status="degraded"; verdict=f"❌ 严重问题{crit}个"
    elif total>0: status="warn"; verdict=f"⚠️ 一般问题{total}个"
    else: status="ok"; verdict="✅ 全部通过"
    
    result = {"status":status,"targets":len(targets),"total":total,
              "greeks":len(greeks),"iv":len(ivs),"expiry":len(expiry),
              "bs":len(bs),"comp":len(comp),"verdict":verdict,
              "details":{"greeks":greeks[:5],"iv":ivs[:5],"expiry":expiry[:5],
                         "bs":bs[:5],"comp":comp[:5]}}
    print("SUMMARY|JSON|"+json.dumps(result, ensure_ascii=False))

if __name__=="__main__": main()
