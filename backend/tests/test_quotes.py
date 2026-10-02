"""core/quotes.py 测试 — 数据状态机是 P0 验收核心。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.quotes import (
    Quote,
    normalize_sina_greeks,
    parse_tencent_spot,
    quote_as_payload,
)

NOW = "2026-09-17T13:31:00+08:00"
TS = "2026-09-17 13:30:00"


def _kv(**kw):
    base = {
        "期权合约简称": "50ETF购9月2650",
        "成交量": "166",
        "Delta": "1",
        "Gamma": "0",
        "Theta": "-0.1059",
        "Vega": "0.001",
        "隐含波动率": "0.4022",
        "最高价": "0.3354",
        "最低价": "0.3090",
        "交易代码": "510050C2609M02650",
        "行权价": "2.6500",
        "最新价": "0.3155",
        "理论价值": "0.3147",
    }
    base.update(kw)
    return base


# ---------- normalize_sina_greeks ----------

def test_normalize_ok_quote():
    q = normalize_sina_greeks("10011255", _kv(), NOW, TS)
    assert q.data_status == "ok"
    assert q.last_price == 0.3155
    assert q.iv == 0.4022
    assert q.delta == 1.0
    assert q.option_code == "510050C2609M02650"
    assert q.fetched_at == NOW
    assert q.market_ts == TS
    assert q.source == "sina"


def test_normalize_empty_kv_unavailable():
    q = normalize_sina_greeks("10011259", {}, NOW, None)
    assert q.data_status == "unavailable"
    assert q.last_price is None


def test_normalize_zero_price_no_volume_unavailable():
    """价 0 且无成交 → 无效行情，不伪装。"""
    q = normalize_sina_greeks("10011259", _kv(最新价="0", 成交量="0"), NOW, TS)
    assert q.data_status == "unavailable"


def test_normalize_zero_price_with_volume_is_ok():
    """深度虚值可以以 0.0001 成交；价为 0 但有量则如实保留。"""
    q = normalize_sina_greeks("10011259", _kv(最新价="0", 成交量="500"), NOW, TS)
    assert q.data_status == "ok"
    assert q.last_price == 0.0


def test_normalize_garbage_fields_become_none():
    q = normalize_sina_greeks("x", _kv(最新价="abc", Delta=""), NOW, TS)
    assert q.last_price is None
    assert q.delta is None
    assert q.data_status == "unavailable"


# ---------- parse_tencent_spot ----------

def test_parse_tencent_spot_ok():
    raw = "v_sh510050=\"1~510050~50ETF~2.962~2.981~2.970~" + "~".join(["0"] * 40) + "\";"
    # 重建符合位置的串：index0=1,1=510050,2=50ETF,3=2.962,4=昨收2.970,30=时间,32=涨跌幅,33=最高,34=最低
    parts = raw.split("~")
    parts[30] = "20260917133140"
    parts[32] = "-0.60"
    parts[33] = "2.980"
    parts[34] = "2.955"
    raw = "~".join(parts)
    spot = parse_tencent_spot(raw)
    assert spot is not None
    assert spot["price"] == 2.962
    assert spot["market_time"] == "20260917133140"
    assert spot["change_pct"] == -0.6
    assert spot["source"] == "tencent"


def test_parse_tencent_spot_garbage_returns_none():
    assert parse_tencent_spot("") is None
    assert parse_tencent_spot("v_sh510050=\"short\";") is None
    assert parse_tencent_spot(None) is None


# ---------- quote_as_payload ----------

def test_payload_unavailable_hides_price_fields():
    q = normalize_sina_greeks("10011259", {}, NOW, None)
    p = quote_as_payload(q)
    assert p["data_status"] == "unavailable"
    assert p["last_price"] is None
    assert p["delta"] is None
    assert p["iv"] is None
    assert p["fetched_at"] == NOW  # 抓取时间保留，便于诊断


def test_payload_ok_keeps_all_fields():
    q = normalize_sina_greeks("10011255", _kv(), NOW, TS)
    p = quote_as_payload(q)
    assert p["data_status"] == "ok"
    assert p["last_price"] == 0.3155
    assert p["theory_price"] == 0.3147
    assert p["market_ts"] == TS
