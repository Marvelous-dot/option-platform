"""标的日K线 — 合成 fixtures，无网络。"""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from main import app, service

BARS = [
    {'date': '2026-09-11', 'open': 2.90, 'close': 2.93, 'high': 2.95, 'low': 2.89, 'volume': 1200000.0},
    {'date': '2026-09-10', 'open': 2.88, 'close': 2.91, 'high': 2.92, 'low': 2.87, 'volume': 1100000.0},
    {'date': '2026-09-14', 'open': 2.93, 'close': 2.90, 'high': 2.94, 'low': 2.88, 'volume': 900000.0},
    {'date': '2026-09-15', 'open': 2.90, 'close': 2.96, 'high': 2.97, 'low': 2.90, 'volume': 1500000.0},
    {'date': '2026-09-16', 'open': 2.96, 'close': 2.94, 'high': 2.98, 'low': 2.92, 'volume': 800000.0},
    {'date': '2026-09-17', 'open': 2.94, 'close': 2.958, 'high': 2.985, 'low': 2.932, 'volume': 700000.0},
]


def test_kline_payload_sorted_and_sliced(monkeypatch):
    monkeypatch.setattr('core.adapters.fetch_tencent_kline',
                        lambda code, days: BARS[-days:])
    d = service.kline('510050', days=5)
    assert d['target_code'] == '510050'
    assert d['count'] == 5
    dates = [b['date'] for b in d['bars']]
    assert dates == sorted(dates)
    assert dates[-1] == '2026-09-17'
    for b in d['bars']:
        assert b['high'] >= max(b['open'], b['close'])
        assert b['low'] <= min(b['open'], b['close'])
        assert b['high'] >= b['low']
    assert d['source'] == 'tencent'
    assert d['data_status'] == 'ok'
    assert '收盘' in d['status_detail']
    assert d['fetched_at']


def test_kline_upstream_failure_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "kline_cache_dir", tmp_path)
    monkeypatch.setattr('core.adapters.fetch_tencent_kline', lambda code, days: None)
    d = service.kline('510050', days=60)
    assert d['data_status'] == 'unavailable'
    assert d['bars'] == [] and d['count'] == 0
    assert '日K' in d['status_detail']


def test_kline_upstream_failure_with_cache_is_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "kline_cache_dir", tmp_path)
    # 预写一份新鲜落盘缓存
    service._save_kline_cache('510050', {
        'target_code': '510050', 'target_name': '50ETF(华夏上证50)',
        'days': 120, 'bars': BARS, 'count': len(BARS),
        'first_date': BARS[0]['date'], 'last_date': BARS[-1]['date'],
        'last_close': BARS[-1]['close'], 'source': 'tencent',
        'adjust': 'qfq(前复权)', 'volume_unit': 'source_raw',
        'fetched_at': '2026-09-17T10:00:00+08:00', 'data_status': 'ok',
    })
    monkeypatch.setattr('core.adapters.fetch_tencent_kline', lambda code, days: None)
    d = service.kline('510050', days=60)
    assert d['data_status'] == 'stale'
    assert d['count'] == len(BARS)
    assert d['last_date'] == BARS[-1]['date']
    assert '落盘缓存快照' in d['status_detail']
    assert 'cached_at' in d


def test_kline_cache_expiry_returns_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "kline_cache_dir", tmp_path)
    service._save_kline_cache('510050', {
        'target_code': '510050', 'target_name': '50ETF(华夏上证50)',
        'days': 120, 'bars': BARS, 'count': len(BARS),
        'fetched_at': '2026-01-01T10:00:00+08:00', 'data_status': 'ok',
    })
    # 手工把 cached_at 改成超期
    f = tmp_path / '510050.json'
    data = json.loads(f.read_text(encoding='utf-8'))
    data['cached_at'] = '2020-01-01T00:00:00+08:00'
    f.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr('core.adapters.fetch_tencent_kline', lambda code, days: None)
    d = service.kline('510050', days=60)
    assert d['data_status'] == 'unavailable'
    assert d['bars'] == []


def test_kline_params_and_routes(monkeypatch):
    monkeypatch.setattr('core.adapters.fetch_tencent_kline',
                        lambda code, days: [b for b in BARS if b['date'] >= '2026-09-11'])
    client = TestClient(app)
    r = client.get('/api/kline/510050')
    assert r.status_code == 200
    assert r.json()['count'] == 5
    import pytest
    for bad in ('abc', '0', '-5', '99999'):
        with pytest.raises(ValueError):
            service.kline('510050', days=bad)
    # 非整数 days 由 FastAPI 类型校验拒绝（422）；业务范围校验返回 400
    assert client.get('/api/kline/510050', params={'days': 'abc'}).status_code == 422
    assert client.get('/api/kline/510050', params={'days': '99999'}).status_code == 400
    assert client.get('/api/kline/NOPE').status_code == 404
    assert client.get('/kline').status_code == 200
    src = Path(__file__).resolve().parents[2] / 'frontend/src'
    assert "path: '/kline'" in (src / 'main.js').read_text()
    text = (src / 'views/Kline.vue').read_text()
    assert '实时' not in text
    assert 'canvas' in text
    assert 'getComputedStyle' in text  # canvas 配色取自 CSS 变量，不硬编码
