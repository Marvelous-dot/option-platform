#!/usr/bin/env python3
"""
期权平台功能准确性审查 - 纯本地文件版
仅依赖标准库: sqlite3, os, json, math, datetime, re
无网络调用, 无subprocess
"""
import os, sys, json, sqlite3, math, re
from datetime import datetime

PROJECT_ROOT = "/root/option-platform"
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
DB_PATH = os.path.join(BACKEND_DIR, "iv_history.db")

TOLERANCE = {
    "delta_range": (0.0, 1.0),
    "gamma_min": 0.0,
    "vega_min": 0.0,
    "iv_min": 0.01,
    "bs_diff_pct": 0.05,
}

all_issues = {"greeks": [], "iv": [], "expiry": [], "bs_pricing": [], "completeness": []}
summary_lines = []

def log(msg, level="info"):
    prefix = {"info": "[INFO]", "warn": "[WARN]", "error": "[ERROR]"}
    print(f"{prefix.get(level, '[INFO]')} {msg}")
    sys.stdout.flush()

def run():
    log("=" * 50)
    log("期权平台 · 功能准确性审查 (本地文件模式)")
    log("=" * 50)

    # 1. 检查 DB 是否存在
    if not os.path.exists(DB_PATH):
        log(f"iv_history.db 不存在: {DB_PATH}", "error")
        all_issues["completeness"].append("iv_history.db 不存在")
        return {"status": "fail", "total_issues": sum(len(v) for v in all_issues.values())}

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
    except Exception as e:
        log(f"DB 连接失败: {e}", "error")
        all_issues["completeness"].append(f"DB 连接失败: {e}")
        return {"status": "fail", "total_issues": len(all_issues["completeness"])}

    # 2. 获取表结构
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    log(f"数据库表: {tables}")

    # 3. 检查 iv_history 表
    if "iv_history" in tables:
        cursor.execute("PRAGMA table_info(iv_history)")
        cols = [r[1] for r in cursor.fetchall()]
        log(f"iv_history 列: {cols}")
        
        cursor.execute("SELECT COUNT(*) FROM iv_history")
        total_rows = cursor.fetchone()[0]
        log(f"iv_history 总记录数: {total_rows}")
        
        if total_rows > 0:
            # 获取最近记录
            cursor.execute("SELECT * FROM iv_history ORDER BY timestamp DESC LIMIT 100")
            rows = cursor.fetchall()
            
            for row in rows:
                row_dict = dict(zip(cols, row))
                code = row_dict.get("option_code", "?")
                
                # Greeks 检查
                delta = row_dict.get("delta")
                opt_type = row_dict.get("option_type")
                gamma = row_dict.get("gamma")
                vega = row_dict.get("vega")
                iv = row_dict.get("implied_volatility")
                tp = row_dict.get("theoretical_price", 0)
                lp = row_dict.get("last_price", 0)
                expiry = row_dict.get("expiry_date")
                
                # delta
                if delta is not None:
                    if opt_type == "认购":
                        if not (0.0 <= delta <= 1.0):
                            all_issues["greeks"].append(f"{code}: delta={delta}超出认购范围[0,1]")
                    elif opt_type == "认沽":
                        if not (-1.0 <= delta <= 0.0):
                            all_issues["greeks"].append(f"{code}: delta={delta}超出认沽范围[-1,0]")
                    elif delta < -1.0 or delta > 1.0:
                        all_issues["greeks"].append(f"{code}: delta={delta}超出合理范围[-1,1]")
                
                # gamma
                if gamma is not None and gamma < 0:
                    all_issues["greeks"].append(f"{code}: gamma={gamma}为负数")
                
                # vega
                if vega is not None and vega < 0:
                    all_issues["greeks"].append(f"{code}: vega={vega}为负数")
                
                # IV
                if iv is not None and lp > 0 and iv < TOLERANCE["iv_min"]:
                    all_issues["iv"].append(f"{code}: IV={iv}过低(有价格但IV接近0)")
                
                # 到期日
                if expiry:
                    if not isinstance(expiry, str) or len(expiry) != 8 or not expiry.isdigit():
                        all_issues["expiry"].append(f"{code}: 到期日格式错误 {expiry}")
                    else:
                        today = datetime.now().strftime("%Y%m%d")
                        if expiry < today:
                            all_issues["expiry"].append(f"{code}: 到期日已过 {expiry}")
                
                # BS定价
                if tp > 0 and lp > 0 and iv and iv > 0:
                    diff_pct = abs(tp - lp) / lp
                    if diff_pct > TOLERANCE["bs_diff_pct"]:
                        all_issues["bs_pricing"].append(f"{code}: BS定价差异={diff_pct:.1%}(理论={tp}, 市场={lp})")
            
            # 去重 (保留前50个)
            for k in all_issues:
                seen = set()
                unique = []
                for item in all_issues[k]:
                    if item not in seen:
                        seen.add(item)
                        unique.append(item)
                all_issues[k] = unique[:50]
        else:
            all_issues["completeness"].append("iv_history 表无数据")

    # 4. 检查其他表
    for t in tables:
        if t == "iv_history":
            continue
        try:
            cursor.execute(f"SELECT COUNT(*) FROM '{t}'")
            cnt = cursor.fetchone()[0]
            log(f"表 {t}: {cnt} 行")
        except Exception as e:
            log(f"表 {t} 读取失败: {e}", "warn")

    conn.close()

    # 5. 统计
    total = sum(len(v) for v in all_issues.values())
    
    log("=" * 50)
    log("审查结果汇总")
    log("=" * 50)
    log(f"Greeks异常: {len(all_issues['greeks'])}个")
    log(f"IV异常: {len(all_issues['iv'])}个")
    log(f"到期日异常: {len(all_issues['expiry'])}个")
    log(f"BS定价差异: {len(all_issues['bs_pricing'])}个")
    log(f"完整性问题: {len(all_issues['completeness'])}个")
    log(f"总计: {total}个")
    
    # 详细问题
    if total > 0:
        for k, items in all_issues.items():
            if items:
                log(f"\n【{k}】问题明细 (前10):")
                for item in items[:10]:
                    log(f"  - {item}")
    
    # 严重性判断
    critical = len(all_issues["greeks"]) + len(all_issues["expiry"]) + len(all_issues["completeness"])
    if critical > 0:
        status = "degraded"
        log(f"❌ 发现 {critical} 个严重问题", "error")
    elif total > 0:
        status = "warn"
        log(f"⚠️ 发现 {total} 个问题", "warn")
    else:
        status = "ok"
        log("✅ 所有检查通过", "info")
    
    return {
        "status": status,
        "total_issues": total,
        "greeks_issues": len(all_issues["greeks"]),
        "iv_issues": len(all_issues["iv"]),
        "expiry_issues": len(all_issues["expiry"]),
        "bs_pricing_issues": len(all_issues["bs_pricing"]),
        "completeness_issues": len(all_issues["completeness"]),
        "critical": critical,
    }

if __name__ == "__main__":
    result = run()
    print(f"\n总结: {json.dumps(result, ensure_ascii=False)}")
