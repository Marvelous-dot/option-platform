#!/usr/bin/env python3
import json, os, sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

API_BASE = os.environ.get("OPTION_API", "http://localhost:8000")

TOL = {"iv_min": 0.01, "bs_diff": 0.05}

def fetch(path):
    try:
        with urlopen(Request(f"{API_BASE}{path}"), timeout=10) as r:
            return 0, r.read().decode()
    except Exception as e:
        return -1, ""

def main():
    code, raw = fetch("/api/state")
    if code != 0 or not raw:
        return {"status":"fail","reason":"backend_unreachable"}
    try:
        state = json.loads(raw)
    except:
        return {"status":"fail","reason":"bad_json"}
    
    targets = state.get("targets", [])
    if not targets:
        return {"status":"fail","reason":"no_targets"}
    
    issues = {"greeks":[],"iv":[],"expiry":[],"bs":[],"complete":[]}
    today = datetime.now().strftime("%Y%m%d")
    
    for t in targets:
        tc = t.get("target","?")
        tcn = t.get("target_name","?")
        ctrs = t.get("contracts",[])
        tp = t.get("latest_price",0)
        
        if not ctrs:
            issues["complete"].append(f"{tc}: no contracts")
        if tp <= 0:
            issues["complete"].append(f"{tc}: price={tp}")
        
        for c in ctrs:
            oc = c.get("option_code","?")
            ot = c.get("option_type","?")
            sk = c.get("strike_price",0)
            d = c.get("delta")
            g = c.get("gamma")
            v = c.get("vega")
            iv = c.get("implied_volatility")
            bp = c.get("theoretical_price",0)
            lp = c.get("last_price",0)
            ex = c.get("expiry_date")
            
            # Greeks
            if d is not None:
                if ot == "认购" and not (0.0<=d<=1.0):
                    issues["greeks"].append(f"{oc}: delta={d} out of [0,1]")
                elif ot == "认沽" and not (-1.0<=d<=0.0):
                    issues["greeks"].append(f"{oc}: delta={d} out of [-1,0]")
            else:
                issues["greeks"].append(f"{oc}: delta missing")
            if g is not None and g < 0:
                issues["greeks"].append(f"{oc}: gamma={g} negative")
            if v is not None and v < 0:
                issues["greeks"].append(f"{oc}: vega={v} negative")
            if tp > 0 and abs(sk-tp)/tp < 0.1:
                if g == 0:
                    issues["greeks"].append(f"{oc}: ATM gamma=0")
                if v == 0:
                    issues["greeks"].append(f"{oc}: ATM vega=0")
            
            # IV
            if iv is None:
                issues["iv"].append(f"{oc}: IV missing")
            elif lp > 0 and iv < TOL["iv_min"]:
                issues["iv"].append(f"{oc}: IV={iv} too low")
            
            # Expiry
            if not ex:
                issues["expiry"].append(f"{oc}: expiry empty")
            elif len(ex)!=8 or not ex.isdigit():
                issues["expiry"].append(f"{oc}: expiry format {ex}")
            elif ex < today:
                issues["expiry"].append(f"{oc}: expired {ex}")
            
            # BS
            if bp>0 and lp>0 and iv and iv>0:
                dp = abs(bp-lp)/lp
                if dp > TOL["bs_diff"]:
                    issues["bs"].append(f"{oc}: diff={dp:.1%} (th={bp}, mkt={lp})")
    
    total = sum(len(v) for v in issues.values())
    crit = len(issues["greeks"]) + len(issues["expiry"]) + len(issues["complete"])
    
    if crit > 0:
        status = "degraded"
    elif total > 0:
        status = "warn"
    else:
        status = "ok"
    
    return {
        "status": status,
        "total_issues": total,
        "greeks": len(issues["greeks"]),
        "iv": len(issues["iv"]),
        "expiry": len(issues["expiry"]),
        "bs": len(issues["bs"]),
        "complete": len(issues["complete"]),
        "details": issues,
    }

print(json.dumps(main(), ensure_ascii=False, indent=2))
