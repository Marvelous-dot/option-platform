#!/usr/bin/env python3
"""Self-contained audit - reads iv_history.db only, no network."""
import os, sqlite3, json, sys
from datetime import datetime

DB = "/root/option-platform/backend/iv_history.db"
if not os.path.exists(DB):
    print("FAIL|no_db")
    sys.exit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM iv_history")
total = cur.fetchone()[0]
cur.execute("SELECT * FROM iv_history ORDER BY timestamp DESC LIMIT 500")
cols = [r[1] for r in cur.execute("PRAGMA table_info(iv_history)").fetchall()]
rows = cur.fetchall()
conn.close()

today = datetime.now().strftime("%Y%m%d")
issues = {"greeks":[],"iv":[],"expiry":[],"bs":[]}

for row in rows:
    d = dict(zip(cols, row))
    oc = d.get("option_code","?")
    opt = d.get("option_type")
    delta = d.get("delta")
    gamma = d.get("gamma")
    vega = d.get("vega")
    iv = d.get("implied_volatility")
    tp = d.get("theoretical_price") or 0
    lp = d.get("last_price") or 0
    exp = d.get("expiry_date")
    strike = d.get("strike_price")
    spot = d.get("spot_price") or 0

    if delta is not None:
        if opt == "认购" and not (0.0 <= delta <= 1.0):
            issues["greeks"].append(f"{oc}: delta={delta}")
        elif opt == "认沽" and not (-1.0 <= delta <= 0.0):
            issues["greeks"].append(f"{oc}: delta={delta}")
    if gamma is not None and gamma < 0:
        issues["greeks"].append(f"{oc}: gamma={gamma}<0")
    if vega is not None and vega < 0:
        issues["greeks"].append(f"{oc}: vega={vega}<0")
    if iv is not None and lp > 0 and iv < 0.01:
        issues["iv"].append(f"{oc}: iv={iv}")
    if exp:
        s = str(exp)
        if len(s) != 8 or not s.isdigit():
            issues["expiry"].append(f"{oc}: bad_format {exp}")
        elif s < today:
            issues["expiry"].append(f"{oc}: expired {exp}")
    if tp > 0 and lp > 0 and iv and iv > 0:
        diff = abs(tp-lp)/lp
        if diff > 0.05:
            issues["bs"].append(f"{oc}: diff={diff:.1%}")

t = sum(len(v) for v in issues.values())
c = len(issues["greeks"]) + len(issues["expiry"])
status = "degraded" if c > 0 else ("warn" if t > 0 else "ok")

print(json.dumps({
    "status": status, "rows": total, "total": t,
    "greeks": len(issues["greeks"]), "iv": len(issues["iv"]),
    "expiry": len(issues["expiry"]), "bs": len(issues["bs"]),
    "verdict": f"❌ {c} critical" if c else ("⚠️ " + str(t) + " issues" if t else "✅ OK"),
    "details": {k: v[:5] for k,v in issues.items() if v}
}, ensure_ascii=False))
