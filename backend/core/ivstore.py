"""历史 IV 库 — 每日收盘快照落 SQLite，供 IV Rank / Percentile / VRP 使用。

设计原则：
- 只存当日真实可得的数据；某标的缺报价就跳过，绝不补零或插值造数据
- 一行一个合约（chain_snapshot）供曲面回放；另按标的每日一行（iv_index）供快速统计
- iv30 = 30 天恒定到期 ATM IV（由近月/远月线性插值），全部分析口径统一为百分数
- IVR/IVP 需 >= MIN_SAMPLES 个交易日样本，不足时如实返回 None 并给出采集进度

IV 口径说明：新浪 /api/quotes 返回的 iv 常态为小数（0.17），本模块入库前统一 ×100。
"""

from __future__ import annotations

import logging
import math
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("optionv2.ivstore")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "iv_history.db"

MIN_SAMPLES = 20          # 出 IVR 所需最少交易日样本
DEFAULT_WINDOW = 252      # 统计窗口（约一年交易日）
TARGET_DAYS = 30          # 恒定到期目标天数

_init_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS chain_snapshot (
    trade_date    TEXT NOT NULL,
    target_code   TEXT NOT NULL,
    expiry        TEXT NOT NULL,
    option_type   TEXT NOT NULL,
    strike        REAL NOT NULL,
    option_code   TEXT NOT NULL,
    contract_id   TEXT,
    iv_pct        REAL,
    last_price    REAL,
    bid           REAL,
    ask           REAL,
    volume        INTEGER,
    open_interest INTEGER,
    spot          REAL,
    dte           INTEGER,
    fetched_at    TEXT,
    PRIMARY KEY (trade_date, option_code)
);
CREATE INDEX IF NOT EXISTS ix_chain_target_date ON chain_snapshot(target_code, trade_date);
CREATE TABLE IF NOT EXISTS iv_index (
    trade_date  TEXT NOT NULL,
    target_code TEXT NOT NULL,
    iv30        REAL,
    atm_near    REAL,
    atm_far     REAL,
    near_days   INTEGER,
    far_days    INTEGER,
    spot        REAL,
    contracts   INTEGER,
    kind        TEXT NOT NULL DEFAULT 'close',
    PRIMARY KEY (trade_date, target_code)
);
"""


# ---------- 基础 ----------

def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def init() -> None:
    """建库建表；幂等，启动时调用一次即可。"""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=15)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            _ensure_schema(conn)
            conn.commit()
        finally:
            conn.close()
        _initialized = True
        log.info("iv store ready at %s", DB_PATH)


def _conn() -> sqlite3.Connection:
    init()
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def normalize_iv(value) -> float | None:
    """统一成百分数；异常值（<=0 / 非有限 / >400%）一律丢弃，不做兜底填充。"""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0:
        return None
    f = f * 100 if f < 1.5 else f
    if f > 400:
        return None
    return f


def _expiry_date(expiry: str) -> date | None:
    try:
        return datetime.strptime(str(expiry), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


# ---------- 计算 ----------

def atm_map(rows: list[dict], spot: float | None,
            trade_day: date | None = None) -> dict[str, tuple[float, float, float]]:
    """每个到期日 → (平值行权价, 平值 IV, 距今天数)。平值取最接近现价的行权价，
    call 与 put 同时有效时取两者均值（单一方向缺腿时只用现有腿，不臆造）。"""
    if not spot or spot <= 0:
        return {}
    groups: dict[str, list[tuple[float, str, float]]] = {}
    for r in rows:
        iv = normalize_iv(r.get("iv"))
        if iv is None:
            continue
        strike = r.get("strike")
        otype = r.get("option_type")
        expiry = str(r.get("expiry") or "")
        if otype not in ("call", "put") or not expiry:
            continue
        if not isinstance(strike, (int, float)) or strike <= 0:
            continue
        groups.setdefault(expiry, []).append((float(strike), otype, iv))

    out: dict[str, tuple[float, float, float]] = {}
    today = trade_day or datetime.now().date()
    for expiry, items in groups.items():
        strikes = sorted({k for k, _, _ in items})
        if not strikes:
            continue
        atm_strike = min(strikes, key=lambda k: (abs(k - spot), k))
        ivs = [iv for k, _, iv in items if k == atm_strike]
        if not ivs:
            continue
        day = _expiry_date(expiry)
        days = (day - today).days if day else None
        out[expiry] = (atm_strike, sum(ivs) / len(ivs), days if days is not None else -1)
    return out


def term_iv30(atms: dict[str, tuple[float, float, float]],
              trade_day: date) -> tuple[float | None, float | None, float | None,
                                        int | None, int | None]:
    """按剩余天数线性插值出 30 天 ATM IV。返回 (iv30, 近端 IV, 远端 IV, 近端天数, 远端天数)。

    结构不足（无有效到期 / 全部已到期）时返回 None，不以外推充数；
    只有单侧可用时取最近一条并如实标记，调用方可据此判断可信度。
    """
    pts: list[tuple[int, float]] = []
    for expiry, (_strike, iv, _days) in atms.items():
        day = _expiry_date(expiry)
        if not day:
            continue
        dte = (day - trade_day).days
        if dte <= 0:
            continue
        pts.append((dte, iv))
    if not pts:
        return None, None, None, None, None
    pts.sort()
    near_days, near_iv = pts[0]
    far_days, far_iv = pts[-1]
    below = [p for p in pts if p[0] <= TARGET_DAYS]
    above = [p for p in pts if p[0] >= TARGET_DAYS]
    if below and above:
        d0, i0 = below[-1]
        d1, i1 = above[0]
        iv30 = i0 if d1 == d0 else i0 + (i1 - i0) * (TARGET_DAYS - d0) / (d1 - d0)
    elif above:
        iv30 = above[0][1]
    else:
        iv30 = below[-1][1]
    return iv30, near_iv, far_iv, near_days, far_days


def realized_vol(closes: list[float], window: int = 20) -> float | None:
    """已实现波动率（年化百分数）：对数收益样本标准差 × √252。
    样本不足 window+1 个收盘价时返回 None。"""
    vals = [float(c) for c in closes if isinstance(c, (int, float)) and c > 0]
    if len(vals) < window + 1:
        return None
    vals = vals[-(window + 1):]
    rets = [math.log(vals[i] / vals[i - 1]) for i in range(1, len(vals))]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    return math.sqrt(var) * math.sqrt(252) * 100


# ---------- 写入 ----------

def has_day(trade_date: str) -> bool:
    """当日是否已有「收盘」快照。盘中补写的 intraday 记录不算数，收盘后会被覆盖。"""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM iv_index WHERE trade_date = ? AND kind = 'close'",
            (trade_date,)).fetchone()
        return bool(row and row["c"])
    finally:
        conn.close()


def write_day(trade_date: str, targets: list[dict], kind: str = "close") -> dict:
    """落盘一天的快照。targets: [{code, name, spot, rows}]。

    kind: 'close' 收盘快照（统计只认这个）/ 'intraday' 盘中手动补采。
    返回写入统计；单标的失败不影响其他标的，异常汇总在 errors 里。
    """
    day = _expiry_date(trade_date.replace("-", "")) or datetime.now().date()
    iso = day.isoformat()
    conn = _conn()
    written = {}
    errors = []
    try:
        with conn:
            for t in targets:
                code = t.get("code")
                try:
                    rows = t.get("rows") or []
                    spot = t.get("spot")
                    chain_vals = []
                    for r in rows:
                        expiry = str(r.get("expiry") or "")
                        otype = r.get("option_type")
                        strike = r.get("strike")
                        ocode = r.get("option_code")
                        if not (expiry and otype in ("call", "put") and ocode):
                            continue
                        if not isinstance(strike, (int, float)):
                            continue
                        d = _expiry_date(expiry)
                        dte = (d - day).days if d else None
                        chain_vals.append((
                            iso, code, expiry, otype, float(strike), ocode,
                            r.get("contract_id"), normalize_iv(r.get("iv")),
                            r.get("last_price"), r.get("bid"), r.get("ask"),
                            r.get("volume"), r.get("open_interest"),
                            spot, dte, r.get("fetched_at") or t.get("fetched_at"),
                        ))
                    conn.executemany(
                        "INSERT OR REPLACE INTO chain_snapshot (trade_date, target_code, expiry,"
                        " option_type, strike, option_code, contract_id, iv_pct, last_price,"
                        " bid, ask, volume, open_interest, spot, dte, fetched_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", chain_vals)
                    atms = atm_map(rows, spot, day)
                    iv30, near_iv, far_iv, near_d, far_d = term_iv30(atms, day)
                    conn.execute(
                        "INSERT OR REPLACE INTO iv_index (trade_date, target_code, iv30, atm_near,"
                        " atm_far, near_days, far_days, spot, contracts, kind)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (iso, code, iv30, near_iv, far_iv, near_d, far_d, spot,
                         len(chain_vals), kind))
                    written[code] = {"contracts": len(chain_vals), "iv30": iv30,
                                     "expiries": len(atms)}
                except Exception as exc:  # 单标的失败不打断整批
                    log.exception("iv snapshot failed for %s", code)
                    errors.append({"code": code, "error": str(exc)})
    finally:
        conn.close()
    log.info("iv snapshot %s: %s", iso, {k: v["contracts"] for k, v in written.items()})
    return {"trade_date": iso, "kind": kind, "written": written, "errors": errors,
            "total_contracts": sum(v["contracts"] for v in written.values())}


# ---------- 读取 ----------

def stats(target_code: str, window: int = DEFAULT_WINDOW) -> dict:
    """滚动窗口内的 IVR / IVP 与序列。样本不足时给采集进度而不是假数字。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT trade_date, iv30, spot, near_days, far_days FROM iv_index"
            " WHERE target_code = ? AND kind = 'close'"
            " ORDER BY trade_date DESC LIMIT ?",
            (target_code, window)).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM iv_index WHERE target_code = ? AND kind = 'close'",
            (target_code,)).fetchone()["c"]
        first = conn.execute(
            "SELECT MIN(trade_date) AS d FROM iv_index WHERE target_code = ? AND kind = 'close'",
            (target_code,)).fetchone()["d"]
    finally:
        conn.close()

    series = [{"date": r["trade_date"], "iv30": r["iv30"]} for r in reversed(rows)]
    out = {
        "target_code": target_code,
        "iv30": None, "ivr": None, "ivp": None,
        "window_high": None, "window_low": None,
        "samples": 0, "min_samples": MIN_SAMPLES, "window": window,
        "trade_date": None, "first_date": first, "series": series,
        "data_status": "unavailable", "status_detail": f"尚无历史快照，需先跑一次收盘采样",
    }
    if not rows:
        out["status_detail"] = "尚无历史快照；每个交易日收盘后自动落盘一次"
        return out

    latest = rows[0]
    vals = [r["iv30"] for r in rows if r["iv30"] is not None]
    out["trade_date"] = latest["trade_date"]
    out["iv30"] = latest["iv30"]
    out["samples"] = len(vals)

    if latest["iv30"] is None:
        out["status_detail"] = f"最新快照（{latest['trade_date']}）缺有效 ATM IV，无法计算 IVR"
        return out
    if len(vals) < MIN_SAMPLES:
        out["data_status"] = "warming"
        out["status_detail"] = (
            f"已采集 {len(vals)}/{MIN_SAMPLES} 个交易日，样本不足暂不出 IVR；"
            f"最近一条 {latest['trade_date']}")
        return out

    lo, hi = min(vals), max(vals)
    out["window_low"], out["window_high"] = lo, hi
    out["ivr"] = 50.0 if hi - lo < 1e-9 else (latest["iv30"] - lo) / (hi - lo) * 100
    out["ivp"] = sum(1 for v in vals if v < latest["iv30"]) / len(vals) * 100
    out["data_status"] = "ok"
    out["status_detail"] = (
        f"{len(vals)} 个交易日窗口（{rows[-1]['trade_date']}~{latest['trade_date']}），"
        f"IV30 区间 {lo:.1f}%~{hi:.1f}%")
    return out
