"""core/contracts.py 测试 — TDD RED 阶段。

覆盖：归一化过滤、T型配对、缺腿不可用（None）、payload 组装。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.contracts import (
    Contract,
    normalize_contracts,
    pair_t_quote,
    parse_underlying,
    t_quote_payload,
)

KNOWN = ("510050", "510300", "510500", "588000", "588080")


def _row(**kw):
    base = {
        "合约编码": "10011255",
        "合约交易代码": "510050C2609M02650",
        "合约简称": "50ETF购9月2650",
        "标的券名称及代码": "50ETF(510050)",
        "类型": "认购",
        "行权价": 2.65,
        "到期日": "20260923",
        "合约单位": 10000,
    }
    base.update(kw)
    return base


# ---------- parse_underlying ----------

def test_parse_underlying_extracts_code():
    assert parse_underlying("50ETF(510050)", KNOWN) == "510050"


def test_parse_underlying_rejects_unknown_target():
    assert parse_underlying("豆粕ETF(159985)", KNOWN) is None


def test_parse_underlying_rejects_garbage():
    assert parse_underlying("", KNOWN) is None
    assert parse_underlying(None, KNOWN) is None


# ---------- normalize_contracts ----------

def test_normalize_keeps_valid_rows():
    rows = [_row(), _row(合约编码="10011299", 合约交易代码="510050P2609M02650",
                        合约简称="50ETF沽9月2650", 类型="认沽")]
    cs = normalize_contracts(rows, KNOWN)
    assert len(cs) == 2
    call = next(c for c in cs if c.option_type == "call")
    assert call.option_code == "510050C2609M02650"
    assert call.contract_id == "10011255"
    assert call.strike == 2.65
    assert call.expiry == "20260923"


def test_normalize_drops_bad_type():
    cs = normalize_contracts([_row(类型="股票")], KNOWN)
    assert cs == []


def test_normalize_drops_bad_strike():
    cs = normalize_contracts([_row(行权价=None)], KNOWN)
    assert cs == []


def test_normalize_drops_bad_expiry():
    cs = normalize_contracts([_row(到期日="2026-09")], KNOWN)
    assert cs == []


def test_normalize_drops_unknown_underlying():
    cs = normalize_contracts([_row(标的券名称及代码="300ETF(159919)")], KNOWN)
    assert cs == []


# ---------- pair_t_quote ----------

def _c(code, cid, typ, strike):
    return Contract(
        option_code=code, contract_id=cid, name=f"测试{typ}{strike}",
        target_code="510050", option_type=typ, strike=strike,
        expiry="20260923", contract_unit=10000,
    )


def test_pair_matches_call_put_by_strike():
    contracts = [_c("510050C1", "1001", "call", 2.65), _c("510050P1", "2001", "put", 2.65)]
    quotes = {
        "1001": {"option_code": "510050C1", "last_price": 0.3155, "data_status": "ok"},
        "2001": {"option_code": "510050P1", "last_price": 0.0102, "data_status": "ok"},
    }
    rows = pair_t_quote(contracts, quotes)
    assert len(rows) == 1
    assert rows[0].strike == 2.65
    assert rows[0].call["last_price"] == 0.3155
    assert rows[0].put["last_price"] == 0.0102


def test_pair_missing_quote_leg_is_none_not_fake():
    """行情拉不到的腿必须是 None——禁止用模拟数据补。"""
    contracts = [_c("510050C1", "1001", "call", 2.65), _c("510050P1", "2001", "put", 2.65)]
    quotes = {"1001": {"option_code": "510050C1", "last_price": 0.3155}}
    rows = pair_t_quote(contracts, quotes)
    assert rows[0].call is not None
    assert rows[0].put is None


def test_pair_missing_contract_leg_is_none():
    contracts = [_c("510050C1", "1001", "call", 2.65)]
    rows = pair_t_quote(contracts, {})
    assert rows[0].call is None
    assert rows[0].put is None


def test_pair_sorted_by_strike():
    contracts = [
        _c("C3", "1003", "call", 2.75), _c("C1", "1001", "call", 2.55),
        _c("C2", "1002", "call", 2.65), _c("P1", "2001", "put", 2.55),
    ]
    rows = pair_t_quote(contracts, {})
    assert [r.strike for r in rows] == [2.55, 2.65, 2.75]


# ---------- t_quote_payload ----------

def test_payload_keeps_missing_spot_as_none():
    rows = pair_t_quote([_c("510050C1", "1001", "call", 2.65)], {})
    payload = t_quote_payload("510050", "50ETF", None, rows, None)
    assert payload["spot"] is None
    assert payload["as_of"] is None
    assert payload["rows"][0]["call"] is None


def test_payload_passes_spot_and_as_of():
    rows = pair_t_quote([], {})
    spot = {"price": 2.962, "change_pct": -0.6, "market_time": "20260917133140", "source": "tencent"}
    payload = t_quote_payload("510050", "50ETF", spot, rows, "2026-09-17T13:31:00")
    assert payload["spot"]["price"] == 2.962
    assert payload["as_of"] == "2026-09-17T13:31:00"
