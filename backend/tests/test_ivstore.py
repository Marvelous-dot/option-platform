"""历史 IV 库：插值口径、已实现波动、IVR 阈值与快照类型隔离。

这些断言锁定的都是"宁可缺一天也不猜"的规则：
- IV 统一百分数，退化值直接丢弃
- 30 天恒定到期只能插值，不外推
- 样本不足只报采集进度，不给假 IVR
- 盘中快照不得进入统计
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import main
from core import ivstore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(ivstore, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ivstore, "DB_PATH", tmp_path / "iv.db")
    monkeypatch.setattr(ivstore, "_initialized", False)
    yield tmp_path
    ivstore._initialized = False


def _rows(expiry: str, iv: float, spot: float = 2.5) -> list[dict]:
    return [{
        "expiry": expiry, "option_type": t, "strike": spot, "option_code": f"{expiry}{t}",
        "iv": iv, "last_price": 0.05, "bid": 0.049, "ask": 0.051, "volume": 100,
        "open_interest": 900, "spot": {"price": spot},
    } for t in ("call", "put")]


def _payload(rows, spot=2.5):
    return [{"code": "510050", "name": "50ETF", "spot": spot, "rows": rows}]


def test_normalize_iv_keeps_fraction_and_percent_apart():
    assert ivstore.normalize_iv(0.1734) == pytest.approx(17.34)
    assert ivstore.normalize_iv(17.34) == pytest.approx(17.34)
    for bad in (None, 0, -1, 500, "x"):
        assert ivstore.normalize_iv(bad) is None


def test_iv30_interpolates_between_two_expiries():
    day = date(2026, 11, 24)
    rows = _rows("20261204", 0.20) + _rows("20270103", 0.30)   # 10 天 / 40 天
    atms = ivstore.atm_map(rows, 2.5, day)
    iv30, near, far, near_d, far_d = ivstore.term_iv30(atms, day)
    assert iv30 == pytest.approx(26.6667, abs=1e-3)
    assert (near_d, far_d) == (10, 40)
    assert near == pytest.approx(20.0) and far == pytest.approx(30.0)


def test_iv30_does_not_extrapolate_with_single_expiry():
    day = date(2026, 11, 24)
    iv30, *_ = ivstore.term_iv30(ivstore.atm_map(_rows("20261204", 0.20), 2.5, day), day)
    assert iv30 == pytest.approx(20.0)     # 10 天到期不外推到 30 天


def test_atm_requires_spot():
    assert ivstore.atm_map(_rows("20261204", 0.20), None) == {}
    assert ivstore.atm_map(_rows("20261204", 0.20), 0) == {}


def test_realized_vol_is_zero_for_smooth_growth():
    closes = [2.5 * 1.001 ** i for i in range(30)]
    assert ivstore.realized_vol(closes, 20) == pytest.approx(0, abs=1e-9)
    assert ivstore.realized_vol([2.5] * 10, 20) is None    # 样本不足


def test_stats_reports_warming_before_enough_samples(store):
    ivstore.write_day("2026-11-23", _payload(_rows("20261204", 0.20)))
    st = ivstore.stats("510050")
    assert st["data_status"] == "warming"
    assert st["samples"] == 1 and st["ivr"] is None and st["iv30"] == pytest.approx(20.0)


def test_ivr_and_ivp_after_enough_samples(store):
    base = date(2026, 10, 1)
    for i in range(25):
        day = (base + timedelta(days=i)).isoformat()
        ivstore.write_day(day, _payload(_rows("20261204", (18 + i * 0.5) / 100)))
    st = ivstore.stats("510050")
    assert st["data_status"] == "ok"
    assert st["samples"] == 25
    assert st["ivr"] == pytest.approx(100.0)             # 最新值即窗口最高
    assert st["ivp"] == pytest.approx(96.0)              # 24/25 个交易日低于当前
    assert st["trade_date"] == "2026-10-25"


def test_intraday_snapshot_never_counts(store):
    ivstore.write_day("2026-11-24", _payload(_rows("20261204", 0.20)), kind="intraday")
    assert ivstore.has_day("2026-11-24") is False
    assert ivstore.stats("510050")["data_status"] == "unavailable"


def test_close_snapshot_is_idempotent(store):
    ivstore.write_day("2026-11-24", _payload(_rows("20261204", 0.20)))
    ivstore.write_day("2026-11-24", _payload(_rows("20261204", 0.20)))   # 覆盖不重复
    assert ivstore.stats("510050")["samples"] == 1
    assert ivstore.stats("510050")["trade_date"] == "2026-11-24"


def test_unknown_target_rejected_by_api():
    assert TestClient(main.app).get("/api/ivstats/999999").status_code == 404
