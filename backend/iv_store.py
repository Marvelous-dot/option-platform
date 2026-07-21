"""
IV历史数据存储服务 - SQLite
"""
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "iv_history.db")
_db_lock = threading.Lock()


def _ensure_db_dir():
    """确保数据库目录存在"""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接"""
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """初始化数据库表"""
    _ensure_db_dir()
    with _db_lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS iv_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_code TEXT NOT NULL,
                expiry TEXT NOT NULL,
                strike REAL NOT NULL,
                option_type TEXT NOT NULL,
                iv REAL NOT NULL,
                option_price REAL NOT NULL,
                spot_price REAL NOT NULL,
                days_to_expiry INTEGER NOT NULL,
                ts TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS ivh_target_expiry
                ON iv_history(target_code, expiry);
            CREATE INDEX IF NOT EXISTS ivh_target_ts
                ON iv_history(target_code, ts);
            CREATE INDEX IF NOT EXISTS ivh_target_expiry_strike_type
                ON iv_history(target_code, expiry, strike, option_type);

            CREATE TABLE IF NOT EXISTS iv_daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_code TEXT NOT NULL,
                expiry TEXT NOT NULL,
                atm_iv REAL,
                iv_skew REAL,
                iv_term_slope REAL,
                avg_iv REAL,
                min_iv REAL,
                max_iv REAL,
                iv_25delta REAL,
                iv_75delta REAL,
                spot_price REAL,
                contract_count INTEGER,
                trade_date TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS ivds_target_date
                ON iv_daily_summary(target_code, trade_date);
            CREATE UNIQUE INDEX IF NOT EXISTS ivds_unique
                ON iv_daily_summary(target_code, expiry, trade_date);

            -- iv_history 复合索引（用于窗口函数查询优化）
            CREATE INDEX IF NOT EXISTS ivh_target_expiry_strike_type_ts
                ON iv_history(target_code, expiry, strike, option_type, ts DESC);

            -- 历史波动率 + 标的价格 + PCR 综合走势
            CREATE TABLE IF NOT EXISTS dashboard_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close_price REAL NOT NULL,
                hv_5d REAL,
                hv_10d REAL,
                hv_20d REAL,
                hv_60d REAL,
                iv_atm REAL,
                iv_weighted REAL,
                pcr_call_put_ratio REAL,
                pcr_iv_skew REAL,
                spot_volume REAL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(target_code, trade_date)
            );

            CREATE INDEX IF NOT EXISTS ds_target_date
                ON dashboard_series(target_code, trade_date);

            -- K线日数据表（从东财API回填）
            CREATE TABLE IF NOT EXISTS kline_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open_price REAL NOT NULL,
                high_price REAL NOT NULL,
                low_price REAL NOT NULL,
                close_price REAL NOT NULL,
                volume INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(target_code, trade_date)
            );

            CREATE INDEX IF NOT EXISTS kd_target_date
                ON kline_daily(target_code, trade_date);
        """)
        conn.commit()
        conn.close()


def save_iv_record(target_code: str, expiry: str, strike: float,
                   option_type: str, iv: float, option_price: float,
                   spot_price: float, days_to_expiry: int):
    """保存一条IV记录"""
    with _db_lock:
        conn = _get_conn()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO iv_history 
               (target_code, expiry, strike, option_type, iv, option_price,
                spot_price, days_to_expiry, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (target_code, expiry, strike, option_type, iv, option_price,
             spot_price, days_to_expiry, ts)
        )
        conn.commit()
        conn.close()


def save_iv_batch(records: list[dict]):
    """批量保存IV记录"""
    with _db_lock:
        conn = _get_conn()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.executemany(
            """INSERT INTO iv_history 
               (target_code, expiry, strike, option_type, iv, option_price,
                spot_price, days_to_expiry, ts)
               VALUES (:target_code, :expiry, :strike, :option_type, :iv,
                       :option_price, :spot_price, :days_to_expiry, :ts)""",
            [{**r, 'ts': ts} for r in records]
        )
        conn.commit()
        conn.close()


def save_daily_summary(target_code: str, expiry: str, atm_iv: float,
                       iv_skew: float, iv_term_slope: float, avg_iv: float,
                       min_iv: float, max_iv: float, iv_25delta: float,
                       iv_75delta: float, spot_price: float,
                       contract_count: int):
    """保存每日IV汇总（INSERT OR REPLACE，同一天同到期日只保留最新一条）"""
    with _db_lock:
        conn = _get_conn()
        trade_date = datetime.now().strftime("%Y-%m-%d")
        # 唯一索引 ivds_unique 已在 init_db 中创建，无需每次检查
        conn.execute(
            """INSERT OR REPLACE INTO iv_daily_summary 
               (target_code, expiry, atm_iv, iv_skew, iv_term_slope,
                avg_iv, min_iv, max_iv, iv_25delta, iv_75delta,
                spot_price, contract_count, trade_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (target_code, expiry, atm_iv, iv_skew, iv_term_slope,
             avg_iv, min_iv, max_iv, iv_25delta, iv_75delta,
             spot_price, contract_count, trade_date)
        )
        conn.commit()
        conn.close()


def get_iv_kline(target_code: str, expiry: str, strike: float,
                 option_type: str, days: int = 30) -> list[dict]:
    """获取单个合约的IV K线数据"""
    with _db_lock:
        conn = _get_conn()
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT ts, iv, option_price, spot_price, days_to_expiry
               FROM iv_history
               WHERE target_code = ? AND expiry = ? AND strike = ?
                 AND option_type = ? AND ts >= ?
               ORDER BY ts ASC""",
            (target_code, expiry, strike, option_type, since)
        ).fetchall()
        conn.close()
    return [
        {
            "ts": r[0],
            "iv": r[1],
            "option_price": r[2],
            "spot_price": r[3],
            "days_to_expiry": r[4]
        }
        for r in rows
    ]


def get_atm_iv_series(target_code: str, expiry: str, days: int = 30) -> list[dict]:
    """获取平价期权IV时间序列（用于K线图）— 优化版：只取ATM附近+按小时降采样"""
    with _db_lock:
        conn = _get_conn()
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Step 1: 获取最新 spot_price 以确定 ATM 行权价
        spot_row = conn.execute(
            """SELECT spot_price FROM iv_history
               WHERE target_code = ? AND expiry = ?
               ORDER BY ts DESC LIMIT 1""",
            (target_code, expiry)
        ).fetchone()
        spot_price = spot_row[0] if spot_row else 0

        if spot_price <= 0:
            conn.close()
            return []

        # Step 2: 只取 ATM 附近行权价（范围查询用索引），按小时降采样
        atm_low = spot_price - 0.05
        atm_high = spot_price + 0.05
        rows = conn.execute(
            """SELECT strftime('%Y-%m-%d %H:00:00', ts) as hour_bucket,
                      MAX(iv) as iv, MAX(spot_price) as spot_price,
                      MAX(strike) as strike, MAX(option_price) as option_price
               FROM iv_history
               WHERE target_code = ? AND expiry = ?
                 AND option_type = '认购'
                 AND ts >= ?
                 AND strike BETWEEN ? AND ?
               GROUP BY hour_bucket
               ORDER BY hour_bucket ASC""",
            (target_code, expiry, since, atm_low, atm_high)
        ).fetchall()
        conn.close()
    return [
        {"ts": r[0], "iv": r[1], "spot_price": r[2], "strike": r[3],
         "option_price": r[4]}
        for r in rows
    ]


def get_iv_surface_snapshot(target_code: str, expiry: str, cached_targets: list = None) -> list[dict]:
    """
    获取某标的某到期日的最新波动率曲面快照 — 优化版：支持从内存缓存构建。
    """
    if cached_targets:
        # 快速路径：从内存缓存构建（<1ms）
        target = None
        for t in cached_targets:
            if t.target == target_code:
                target = t
                break
        if not target:
            return []
        result = []
        for c in target.contracts:
            if c.expiry_date == expiry:
                result.append({
                    "strike": c.strike_price,
                    "option_type": c.option_type,
                    "iv": c.implied_volatility or 0,
                    "option_price": c.theoretical_price or 0,
                    "spot_price": target.latest_price or 0,
                    "ts": target.last_updated or "",
                })
        return sorted(result, key=lambda x: (x["strike"], x["option_type"]))

    # 慢路径：数据库窗口函数查询
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT strike, option_type, iv, option_price, spot_price,
                      days_to_expiry, ts
               FROM (
                   SELECT strike, option_type, iv, option_price, spot_price,
                          days_to_expiry, ts,
                          ROW_NUMBER() OVER (
                              PARTITION BY strike, option_type ORDER BY ts DESC
                          ) as rn
                   FROM iv_history
                   WHERE target_code = ? AND expiry = ?
               )
               WHERE rn = 1
               ORDER BY strike ASC, option_type DESC""",
            (target_code, expiry)
        ).fetchall()
        conn.close()
    return [
        {
            "strike": r[0],
            "option_type": r[1],
            "iv": r[2],
            "option_price": r[3],
            "spot_price": r[4],
            "days_to_expiry": r[5],
            "ts": r[6]
        }
        for r in rows
    ]


def get_iv_smile(target_code: str, expiry: str, cached_targets: list = None) -> list[dict]:
    """
    获取波动率微笑曲线数据（最新快照，按行权价排序）— 优化版：支持从内存缓存构建。
    """
    if cached_targets:
        target = None
        for t in cached_targets:
            if t.target == target_code:
                target = t
                break
        if not target:
            return []
        result = []
        for c in target.contracts:
            if c.expiry_date == expiry:
                result.append({
                    "strike": c.strike_price,
                    "option_type": c.option_type,
                    "iv": c.implied_volatility or 0,
                    "option_price": c.theoretical_price or 0,
                    "spot_price": target.latest_price or 0,
                    "ts": target.last_updated or "",
                })
        return sorted(result, key=lambda x: (x["strike"], x["option_type"]))

    snap = get_iv_surface_snapshot(target_code, expiry)
    return sorted(snap, key=lambda x: (x["strike"], x["option_type"]))


def get_iv_surface_3d(target_code: str, cached_targets: list = None) -> dict:
    """
    获取3D波动率曲面数据 — 优化版：从内存缓存构建，避免全表窗口函数。

    如果提供 cached_targets（state_cache.targets），直接从内存数据构建；
    否则回退到数据库查询（慢路径）。

    返回结构:
    {
        "strikes": [行权价列表],
        "expiries": [到期日列表],
        "grid": {
            "call": [[IV值二维数组 (expiry_idx x strike_idx)]],
            "put": [[IV值二维数组]]
        },
        "spot_price": 标的价格,
        "min_iv": 最小IV,
        "max_iv": 最大IV
    }
    """
    if cached_targets:
        # 快速路径：从内存缓存构建（<1ms）
        target = None
        for t in cached_targets:
            if t.target == target_code:
                target = t
                break
        if not target:
            return {"strikes": [], "expiries": [], "grid": {"call": [], "put": []}, "spot_price": 0, "min_iv": 0, "max_iv": 0}

        # 从合约数据收集 strikes/expiries/grids
        strike_set = set()
        expiry_set = set()
        call_map = {}  # (expiry, strike) -> iv
        put_map = {}

        for c in target.contracts:
            strike_set.add(c.strike_price)
            expiry_set.add(c.expiry_date)
            iv = c.implied_volatility or 0
            if c.option_type == '认购':
                call_map[(c.expiry_date, c.strike_price)] = iv
            else:
                put_map[(c.expiry_date, c.strike_price)] = iv

        if not strike_set:
            return {"strikes": [], "expiries": [], "grid": {"call": [], "put": []}, "spot_price": 0, "min_iv": 0, "max_iv": 0}

        strikes = sorted(strike_set)
        expiries = sorted(expiry_set)
        strike_idx = {s: i for i, s in enumerate(strikes)}
        expiry_idx = {e: i for i, e in enumerate(expiries)}

        n_exp = len(expiries)
        n_strk = len(strikes)

        call_grid = [[None] * n_strk for _ in range(n_exp)]
        put_grid = [[None] * n_strk for _ in range(n_exp)]

        all_ivs = []
        for (exp, strk), iv in call_map.items():
            ei = expiry_idx.get(exp)
            si = strike_idx.get(strk)
            if ei is not None and si is not None and iv > 0:
                call_grid[ei][si] = round(iv, 6)
                all_ivs.append(iv)
        for (exp, strk), iv in put_map.items():
            ei = expiry_idx.get(exp)
            si = strike_idx.get(strk)
            if ei is not None and si is not None and iv > 0:
                put_grid[ei][si] = round(iv, 6)
                all_ivs.append(iv)

        spot_price = target.latest_price or 0
        min_iv = round(min(all_ivs), 4) if all_ivs else 0
        max_iv = round(max(all_ivs), 4) if all_ivs else 0

        return {
            "strikes": strikes,
            "expiries": expiries,
            "grid": {"call": call_grid, "put": put_grid},
            "spot_price": spot_price,
            "min_iv": min_iv,
            "max_iv": max_iv,
        }

    # 慢路径：无缓存时回退数据库查询
    with _db_lock:
        conn = _get_conn()
        expiry_rows = conn.execute(
            "SELECT DISTINCT expiry FROM iv_history WHERE target_code = ? ORDER BY expiry ASC",
            (target_code,)
        ).fetchall()
        expiries = [r[0] for r in expiry_rows]

        if not expiries:
            conn.close()
            return {"strikes": [], "expiries": [], "grid": {"call": [], "put": []}, "spot_price": 0, "min_iv": 0, "max_iv": 0}

        strike_rows = conn.execute(
            "SELECT DISTINCT strike FROM iv_history WHERE target_code = ? ORDER BY strike ASC",
            (target_code,)
        ).fetchall()
        strikes = [r[0] for r in strike_rows]

        if not strikes:
            conn.close()
            return {"strikes": [], "expiries": [], "grid": {"call": [], "put": []}, "spot_price": 0, "min_iv": 0, "max_iv": 0}

        all_data = conn.execute(
            """SELECT expiry, strike, option_type, iv, spot_price, days_to_expiry
               FROM (
                   SELECT expiry, strike, option_type, iv, spot_price, days_to_expiry,
                          ROW_NUMBER() OVER (PARTITION BY expiry, strike, option_type ORDER BY ts DESC) as rn
                   FROM iv_history
                   WHERE target_code = ?
               )
               WHERE rn = 1""",
            (target_code,)
        ).fetchall()

        spot_row = conn.execute(
            "SELECT spot_price FROM iv_history WHERE target_code = ? ORDER BY ts DESC LIMIT 1",
            (target_code,)
        ).fetchone()
        spot_price = spot_row[0] if spot_row else 0

        conn.close()

    strike_idx = {s: i for i, s in enumerate(strikes)}
    expiry_idx = {e: i for i, e in enumerate(expiries)}
    n_exp = len(expiries)
    n_strk = len(strikes)
    call_grid = [[None] * n_strk for _ in range(n_exp)]
    put_grid = [[None] * n_strk for _ in range(n_exp)]

    all_ivs = []
    for row in all_data:
        exp, strk, opt_type, iv, sp, dte = row
        ei = expiry_idx.get(exp)
        si = strike_idx.get(strk)
        if ei is not None and si is not None and iv is not None:
            if opt_type == '认购':
                call_grid[ei][si] = round(iv, 6)
            else:
                put_grid[ei][si] = round(iv, 6)
            all_ivs.append(iv)

    if not all_ivs:
        return {"strikes": strikes, "expiries": expiries, "grid": {"call": call_grid, "put": put_grid}, "spot_price": spot_price, "min_iv": 0, "max_iv": 0}

    return {
        "strikes": strikes,
        "expiries": expiries,
        "grid": {"call": call_grid, "put": put_grid},
        "spot_price": spot_price,
        "min_iv": round(min(all_ivs), 4),
        "max_iv": round(max(all_ivs), 4),
    }


def get_term_structure(target_code: str, cached_targets: list = None) -> list[dict]:
    """
    获取期限结构（各到期日的ATM IV）— 优化版：从内存缓存构建。

    如果提供 cached_targets，直接从内存数据计算各到期日平均IV；
    否则回退到数据库窗口函数查询（慢路径）。
    """
    if cached_targets:
        # 快速路径：从内存缓存构建（<1ms）
        target = None
        for t in cached_targets:
            if t.target == target_code:
                target = t
                break
        if not target:
            return []

        # 按到期日聚合 IV
        expiry_ivs = {}
        expiry_spots = {}
        for c in target.contracts:
            exp = c.expiry_date
            iv = c.implied_volatility or 0
            if iv > 0:
                if exp not in expiry_ivs:
                    expiry_ivs[exp] = []
                expiry_ivs[exp].append(iv)
            expiry_spots[exp] = target.latest_price or 0

        result = []
        for exp in sorted(expiry_ivs.keys()):
            ivs = expiry_ivs[exp]
            avg_iv = sum(ivs) / len(ivs) if ivs else 0
            result.append({
                "expiry": exp,
                "atm_iv": round(avg_iv, 4),
                "spot_price": expiry_spots.get(exp, 0),
                "ts": target.last_updated or "",
            })
        return result

    # 慢路径：数据库窗口函数查询
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT expiry, AVG(iv) as avg_iv, MAX(spot_price) as spot_price, MAX(ts) as ts
               FROM (
                   SELECT expiry, iv, spot_price, ts,
                          ROW_NUMBER() OVER (
                              PARTITION BY expiry, strike, option_type ORDER BY ts DESC
                          ) as rn
                   FROM iv_history
                   WHERE target_code = ? AND option_type = '认购'
               )
               WHERE rn = 1
               GROUP BY expiry
               ORDER BY expiry ASC""",
            (target_code,)
        ).fetchall()
        conn.close()
    return [
        {"expiry": r[0], "atm_iv": round(r[1], 4), "spot_price": r[2], "ts": r[3]}
        for r in rows
    ]


def get_available_expiries(target_code: str) -> list[str]:
    """获取某标的所有可用到期日"""
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT DISTINCT expiry FROM iv_history
               WHERE target_code = ?
               ORDER BY expiry ASC""",
            (target_code,)
        ).fetchall()
        conn.close()
    return [r[0] for r in rows]


def get_kline_data(target_code: str, days: int = 30) -> list[dict]:
    """
    从 kline_daily 表读取标的 OHLC K线数据。
    优先用 kline_daily（东财API回填），fallback 到 iv_history 聚合。

    返回: [{date, open, high, low, close, volume}, ...]
    """
    import requests

    # 1. 尝试从 kline_daily 读取
    with _db_lock:
        conn = _get_conn()
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT trade_date, open_price, high_price, low_price, close_price, volume
               FROM kline_daily
               WHERE target_code = ? AND trade_date >= ?
               ORDER BY trade_date ASC""",
            (target_code, since),
        ).fetchall()
        conn.close()

    if rows:
        return [
            {
                "date": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
            }
            for r in rows
        ]

    # 2. Fallback: 从 iv_history 聚合（旧逻辑）
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT strftime('%Y-%m-%d', ts) as trade_date,
                   MIN(spot_price) as low_price,
                   MAX(spot_price) as high_price,
                   COUNT(*) as volume
            FROM iv_history
            WHERE target_code = ? AND ts >= ?
            GROUP BY trade_date
            ORDER BY trade_date ASC
            """,
            (target_code, since),
        ).fetchall()
        conn.close()

    result = []
    for row in rows:
        trade_date = row[0]
        low = row[1]
        high = row[2]
        vol = row[3]

        with _db_lock:
            conn = _get_conn()
            open_row = conn.execute(
                "SELECT spot_price FROM iv_history WHERE target_code = ? AND ts >= ? AND ts < ? ORDER BY id ASC LIMIT 1",
                (target_code, trade_date, trade_date + " 23:59:59"),
            ).fetchone()
            close_row = conn.execute(
                "SELECT spot_price FROM iv_history WHERE target_code = ? AND ts >= ? AND ts < ? ORDER BY id DESC LIMIT 1",
                (target_code, trade_date, trade_date + " 23:59:59"),
            ).fetchone()
            conn.close()

        open_price = open_row[0] if open_row else high
        close_price = close_row[0] if close_row else high

        result.append({
            "date": trade_date,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": vol,
        })

    return result


def _get_market_code(target_code: str) -> str:
    """获取东财secid: 1.代码(上海) / 0.代码(深圳)"""
    if target_code.startswith(("510", "588")):
        return f"1.{target_code}"
    elif target_code.startswith(("159", "500")):
        return f"0.{target_code}"
    else:
        # 默认上海
        return f"1.{target_code}"


def backfill_kline_daily(target_code: str, days: int = 60) -> int:
    """
    从新浪财经K线API回填标的历史日K线数据到 kline_daily 表。
    返回：成功写入的条数。
    """
    import urllib.request
    import json
    import re

    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var_/CN_MarketDataService.getKLineData?symbol=sh{target_code}&scale=240&ma=no&datalen={days}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        text = resp.read().decode("utf-8")
        m = re.search(r"var_\((.*)\);?\s*$", text.strip())
        if not m:
            return 0
        data = json.loads(m.group(1))
    except Exception as e:
        print(f"backfill_kline {target_code} API error: {e}")
        return 0

    if not data:
        return 0

    inserted = 0
    with _db_lock:
        conn = _get_conn()
        for d in data:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO kline_daily
                       (target_code, trade_date, open_price, high_price, low_price, close_price, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (target_code, d["day"], float(d["open"]), float(d["high"]),
                     float(d["low"]), float(d["close"]), int(d["volume"])),
                )
                inserted += 1
            except Exception:
                pass
        conn.commit()
        conn.close()

    return inserted


def cleanup_old_data(days: int = 7):
    """清理超过N天的历史数据"""
    with _db_lock:
        conn = _get_conn()
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM iv_history WHERE ts < ?", (cutoff,))
        conn.commit()
        conn.close()


# ============================================================
# 综合走势数据 (HV + IV + 标的 + PCR)
# ============================================================

def save_dashboard_snapshot(target_code: str, close_price: float,
                             hv_5d: float, hv_10d: float, hv_20d: float, hv_60d: float,
                             iv_atm: float, iv_weighted: float,
                             pcr_ratio: float, pcr_iv_skew: float,
                             spot_volume: float):
    """保存每日综合走势快照"""
    with _db_lock:
        conn = _get_conn()
        trade_date = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            """INSERT OR REPLACE INTO dashboard_series
               (target_code, trade_date, close_price, hv_5d, hv_10d, hv_20d, hv_60d,
                iv_atm, iv_weighted, pcr_call_put_ratio, pcr_iv_skew, spot_volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (target_code, trade_date, close_price, hv_5d, hv_10d, hv_20d, hv_60d,
             iv_atm, iv_weighted, pcr_ratio, pcr_iv_skew, spot_volume)
        )
        conn.commit()
        conn.close()


def get_dashboard_series(target_code: str, days: int = 90) -> list[dict]:
    """获取综合走势数据（HV + IV + 标的 + PCR）"""
    with _db_lock:
        conn = _get_conn()
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT trade_date, close_price, hv_5d, hv_10d, hv_20d, hv_60d,
                      iv_atm, iv_weighted, pcr_call_put_ratio, pcr_iv_skew, spot_volume
               FROM dashboard_series
               WHERE target_code = ? AND trade_date >= ?
               ORDER BY trade_date ASC""",
            (target_code, since)
        ).fetchall()
        conn.close()
    return [
        {
            "date": r[0],
            "close": r[1],
            "hv5": r[2], "hv10": r[3], "hv20": r[4], "hv60": r[5],
            "iv_atm": r[6], "iv_weighted": r[7],
            "pcr_ratio": r[8], "pcr_iv_skew": r[9],
            "volume": r[10],
        }
        for r in rows
    ]


def get_latest_dashboard(target_code: str) -> dict | None:
    """获取最新一天的综合走势数据"""
    with _db_lock:
        conn = _get_conn()
        row = conn.execute(
            """SELECT trade_date, close_price, hv_5d, hv_10d, hv_20d, hv_60d,
                      iv_atm, iv_weighted, pcr_call_put_ratio, pcr_iv_skew, spot_volume
               FROM dashboard_series
               WHERE target_code = ?
               ORDER BY trade_date DESC LIMIT 1""",
            (target_code,)
        ).fetchone()
        conn.close()
    if not row:
        return None
    return {
        "date": row[0], "close": row[1],
        "hv5": row[2], "hv10": row[3], "hv20": row[4], "hv60": row[5],
        "iv_atm": row[6], "iv_weighted": row[7],
        "pcr_ratio": row[8], "pcr_iv_skew": row[9],
        "volume": row[10],
    }
