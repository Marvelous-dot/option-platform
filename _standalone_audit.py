#!/usr/bin/env python3
"""Standalone audit: reads iv_history.db directly, no network/subprocess."""
import os, sqlite3, json, math, sys
from datetime import datetime

DB_PATH = "/root/option-platform/backend/iv_history.db"

if not os.path.exists(DB_PATH):
    print("FAIL|iv_history.db not found")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# get columns
cur.execute("PRAGMA table_info(iv_history)")
cols = [r[1] for r in cur.fetchall()]
cur.execute("SELECT COUNT(*) FROM iv_history")
total_rows = cur.fetchone()[0]
cur.execute("SELECT * FROM iv_history ORDER BY timestamp DESC LIMIT 200")
rows = cur.fetchall()

issues = {"greeks":[], "iv":[], "expiry":[], "bs":[], "complete":[]}
today = datetime.now().strftime("%Y%m%d")

for row in rows:
    d = dict(zip(cols, row))
    code = d.get("option_code","?")
    opt = d.get("option_type")
    delta = d.get("delta")
    gamma = d.get("gamma")
    vega = d.get("vega")
    iv = d.get("implied_volatility")
    tp = d.get("theoretical_price",0) or 0
    lp = d.get("last_price",0) or 0
    exp = d.get("expiry_date")
    strike = d.get("strike_price")
    target = d.get("target_code")
    price = d.get("spot_price",0) or 0
    
    # Greeks
    if delta is not None:
        if opt == "认购":
            if not (0.0 <= delta <= 1.0): issues["greeks"].append(f"{code}: delta={delta}超出认购[0,1]")
        elif opt == "认沽":
            if not (-1.0 <= delta <= 0.0): issues["greeks"].append(f"{code}: delta={delta}超出认沽[-1,0]")
    if gamma is not None and gamma < 0: issues["greeks"].append(f"{code}: gamma={gamma}为负")
    if vega is not None and vega < 0: issues["greeks"].append(f"{code}: vega={vega}为负")
    if price > 0 and strike and abs(strike-price)/price < 0.1:
        if gamma == 0: issues["greeks"].append(f"{code}: ATM gamma=0异常")
        if vega == 0: issues["greeks"].append(f"{code}: ATM vega=0异常")
    
    # IV
    if iv is not None and lp > 0 and iv < 0.01: issues["iv"].append(f"{code}: IV={iv}过低")
    
    # Expiry
    if exp:
        if len(str(exp)) != 8 or not str(exp).isdigit(): issues["expiry"].append(f"{code}: 到期日格式错误 {exp}")
        elif str(exp) < today: issues["expiry"].append(f"{code}: 到期日已过 {exp}")
    
    # BS
    if tp > 0 and lp > 0 and iv and iv > 0:
        diff = abs(tp-lp)/lp
        if diff > 0.05: issues["bs"].append(f"{code}: BS差异={diff:.1%}(理论={tp},市场={lp})")

conn.close()

total = sum(len(v) for v in issues.values())
critical = len(issues["greeks"])+len(issues["expiry"])+len(issues["complete"])

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
    "status": status, "total_rows_scanned": total_rows, "total_issues": total,
    "greeks": len(issues["greeks"]), "iv": len(issues["iv"]),
    "expiry": len(issues["expiry"]), "bs": len(issues["bs"]),
    "verdict": verdict,
}
if issues["greeks"]: result["greeks_details"] = issues["greeks"][:10]
if issues["expiry"]: result["expiry_details"] = issues["expiry"][:10]
if issues["iv"]: result["iv_details"] = issues["iv"][:10]
if issues["bs"]: result["bs_details"] = issues["bs"][:10]

print(json.dumps(result, ensure_ascii=False))
