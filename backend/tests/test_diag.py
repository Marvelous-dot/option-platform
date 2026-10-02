"""P2 运维：/health 细化 + /api/diag 数据源可达性诊断。"""
import main
from fastapi.testclient import TestClient


def test_health_is_static_and_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DIST", tmp_path)
    c = TestClient(main.app)
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "up"
    assert body["version"] == "2.0.0"
    assert "uptime_s" in body
    assert body["uptime_s"] >= 0
    # 再次调用不报错、结构稳定
    r2 = c.get("/health")
    assert set(r2.json().keys()) >= {"status", "version", "uptime_s", "data_store"}
    assert "kline:disk" in r2.json()["data_store"]  # 日K已落盘缓存


def test_diag_reports_source_reachability_with_fake_service(monkeypatch):
    class FakeService:
        def targets(self):
            return [{"code": "510050", "name": "50ETF"}]

        def expiries(self, code):
            return ["20260923", "20261028"]

    monkeypatch.setattr(main, "service", FakeService())
    c = TestClient(main.app)
    r = c.get("/api/diag")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] in {"ok", "degraded", "unavailable"}
    assert "services" in body
    # 静态 targets 与合约目录（mock 成功）应 ok
    assert body["services"]["targets"]["status"] == "ok"
    assert body["services"]["contracts"]["status"] == "ok"


def test_diag_degraded_when_contracts_fail(monkeypatch):
    class FailService:
        def targets(self):
            return [{"code": "510050"}]

        def expiries(self, code):
            raise RuntimeError("upstream down")

    monkeypatch.setattr(main, "service", FailService())
    c = TestClient(main.app)
    r = c.get("/api/diag")
    assert r.status_code == 200  # 诊断端点恒 200，下游失败不 500
    assert r.json()["services"]["contracts"]["status"] == "unavailable"
    assert r.json()["overall"] in {"degraded", "unavailable"}
