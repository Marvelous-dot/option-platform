"""数据状态与报价归一 — P0 核心：市场观测必须带来源与时间，缺失标不可用。

three states:
  ok         — 拿到实时数据
  stale      — 拿到带原时间的过期数据（如实标注时间）
  unavailable— 拿不到数据，字段为 None，禁止默认值伪装
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CN = ZoneInfo("Asia/Shanghai")


@dataclass
class Quote:
    contract_id: str
    option_code: str = ""
    name: str = ""
    last_price: float | None = None
    change_pct: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    iv: float | None = None            # 新浪按市场价反推的真实市场 IV
    volume: int | None = None
    high: float | None = None
    low: float | None = None
    theory_price: float | None = None  # 新浪理论价值（交易所参考价，如实标注来源）
    source: str = "sina"
    fetched_at: str | None = None      # 本系统抓取时间
    market_ts: str | None = None       # 数据源端市场时间（若有）
    data_status: str = "unavailable"


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _i(v) -> int | None:
    x = _f(v)
    return int(x) if x is not None else None


def parse_market_ts(ts: str | None) -> datetime | None:
    """解析数据源市场时间戳，支持常见格式；失败返回 None。"""
    if not ts:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(ts.strip(), fmt)
        except ValueError:
            continue
    return None


def ts_freshness(ts: str | None) -> str:
    """按数据源市场时间戳判定 fresh / stale / unknown（与当前自然日比较）。

    fetched_at 是本系统抓取时间，绝不参与判定；无市场时间戳 → unknown。
    """
    dt = parse_market_ts(ts)
    if dt is None:
        return "unknown"
    return "fresh" if dt.date() == datetime.now(CN).date() else "stale"


def normalize_sina_greeks(contract_id: str, kv: dict, fetched_at: str, quote_ts: str | None) -> Quote:
    """新浪 option_sse_greeks_sina 返回 (字段,值) 键值对 → Quote。

    最新价为 0 / 缺失 → unavailable（新浪对无行情合约返回空或 0）。
    """
    q = Quote(contract_id=contract_id, fetched_at=fetched_at)
    if not kv:
        return q

    q.last_price = _f(kv.get("最新价"))
    if q.last_price is not None and q.last_price < 0:
        q.last_price = None
    q.delta = _f(kv.get("Delta"))
    q.gamma = _f(kv.get("Gamma"))
    q.theta = _f(kv.get("Theta"))
    q.vega = _f(kv.get("Vega"))
    q.iv = _f(kv.get("隐含波动率"))
    q.high = _f(kv.get("最高价"))
    q.low = _f(kv.get("最低价"))
    q.volume = _i(kv.get("成交量"))
    q.theory_price = _f(kv.get("理论价值"))
    q.option_code = str(kv.get("交易代码", "")).strip()
    q.name = str(kv.get("期权合约简称", "")).strip()
    q.market_ts = quote_ts

    # 最新价缺失或为 0 且成交量也为 0 → 无有效行情
    if q.last_price is None or (q.last_price == 0 and not q.volume):
        return q
    q.data_status = "ok"
    return q


def parse_tencent_spot(raw: str) -> dict | None:
    """腾讯 qt.gtimg.cn 返回 '~' 分隔串 → 标的实时价。

    返回 None 表示解析失败（不可用），不返回默认 0。
    """
    parts = (raw or "").split("~")
    if len(parts) < 33:
        return None
    price = _f(parts[3])
    if price is None or price <= 0:
        return None
    return {
        "price": price,
        "open": _f(parts[5]),
        "high": _f(parts[33]) if len(parts) > 33 else None,
        "low": _f(parts[34]) if len(parts) > 34 else None,
        "yesterday_close": _f(parts[4]),
        "change_pct": _f(parts[32]),
        "market_time": parts[30] if len(parts) > 30 else None,  # e.g. 20260917133140
        "source": "tencent",
    }


def quote_as_payload(q: Quote, *, expected_option_code: str | None = None) -> dict:
    """Quote → API 输出。

    unavailable/stale 时价格字段清 None（身份与来源保留）；
    freshness 只依据数据源市场时间戳（market_ts），抓取时间 fetched_at
    是本系统时间，绝不冒充行情时间。
    expected_option_code 传入时校验返回的 option_code 必须与挂牌合约一致，
    不一致（含缺失）按 unavailable 处理，绝不接受错配行情。
    """
    fresh = ts_freshness(q.market_ts)
    identity_ok = not expected_option_code or q.option_code == expected_option_code
    if q.data_status == "unavailable" or not identity_ok:
        # 无数据或身份错配：价格字段全 None，仅保留挂牌合约身份信息
        return {
            "contract_id": q.contract_id,
            "option_code": (expected_option_code if not identity_ok else None)
            or (q.option_code or None),
            "name": q.name or None,
            "last_price": None,
            "change_pct": None,
            "delta": None, "gamma": None, "theta": None, "vega": None,
            "iv": None, "volume": None,
            "high": None, "low": None,
            "theory_price": None,
            "source": q.source,
            "fetched_at": q.fetched_at,
            "market_ts": None,
            "freshness": fresh,
            "data_status": "unavailable",
        }
    # ok / stale：stale 是带原时间的过期数据，如实保留观测值
    if q.data_status == "stale":
        fresh = "stale"
    return {
        "contract_id": q.contract_id,
        "option_code": q.option_code or None,
        "name": q.name or None,
        "last_price": q.last_price,
        "change_pct": q.change_pct,
        "delta": q.delta, "gamma": q.gamma, "theta": q.theta, "vega": q.vega,
        "iv": q.iv, "volume": q.volume,
        "high": q.high, "low": q.low,
        "theory_price": q.theory_price,
        "source": q.source,
        "fetched_at": q.fetched_at,
        "market_ts": q.market_ts,
        "freshness": fresh,
        "data_status": q.data_status,
        "analytics_kind": "provider_computed_unverified",
    }
