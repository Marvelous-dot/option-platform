"""Network-boundary fixtures for Tencent qfq bars; no live requests."""
import io
import json
import pytest
from core.adapters import fetch_tencent_kline

ROW = ['2026-09-17', '2.94', '2.958', '2.985', '2.932', '700000']

def stub(monkeypatch, payload):
    monkeypatch.setattr('core.adapters.urllib.request.urlopen',
                        lambda *a, **k: io.BytesIO(json.dumps(payload).encode()))

def payload(rows, field='qfqday'):
    return {'code': 0, 'data': {'sh510050': {field: rows}}}

def test_parse_valid_qfq(monkeypatch):
    stub(monkeypatch, payload([ROW]))
    bars = fetch_tencent_kline('510050', 5)
    assert bars == [{'date': '2026-09-17', 'open': 2.94, 'close': 2.958,
                     'high': 2.985, 'low': 2.932, 'volume': 700000.0}]

@pytest.mark.parametrize('index,value', [(0,'bad'),(0,'2026-02-30'),(1,'NaN'),(2,'Infinity'),
    (1,'0'),(3,'2'),(4,'3'),(5,'-1'),(5,'Infinity')])
def test_reject_invalid_bar(monkeypatch, index, value):
    row = list(ROW); row[index] = value
    stub(monkeypatch, payload([row]))
    assert fetch_tencent_kline('510050', 5) is None

@pytest.mark.parametrize('bad', [[], {'data': []}, {'data': {'sh510050': []}},
    {'code':1, 'data': {'sh510050': {'qfqday':[ROW]}}}, payload([ROW], 'day'),
    payload([ROW, ROW]), payload([{}]), payload('bad')])
def test_reject_ambiguous_structure_or_adjustment(monkeypatch, bad):
    stub(monkeypatch, bad)
    assert fetch_tencent_kline('510050', 5) is None

def test_missing_volume_stays_null(monkeypatch):
    stub(monkeypatch, payload([ROW[:5]]))
    assert fetch_tencent_kline('510050', 5)[0]['volume'] is None

def test_network_failure(monkeypatch):
    def fail(*a, **k): raise TimeoutError('fixture')
    monkeypatch.setattr('core.adapters.urllib.request.urlopen', fail)
    assert fetch_tencent_kline('510050', 5) is None


def test_service_takes_latest_sorted_days(monkeypatch):
    from main import service
    bars = [dict(date=f'2026-09-{day:02}', open=2., close=2., high=2., low=2., volume=None)
            for day in (17, 11, 15, 10, 16, 14)]
    monkeypatch.setattr('core.adapters.fetch_tencent_kline', lambda *a: bars)
    data = service.kline('510050', days=5)
    assert [b['date'] for b in data['bars']] == ['2026-09-11','2026-09-14','2026-09-15','2026-09-16','2026-09-17']
    assert data['count'] == 5
    assert bars[0]['date'] == '2026-09-17'  # do not mutate adapter result
    assert '可能尚未收盘' in data['status_detail']
    assert data['volume_unit'] == 'source_raw'

@pytest.mark.parametrize('bad', [5.5, True, None])
def test_service_reject_non_integer(monkeypatch, bad):
    from main import service
    monkeypatch.setattr('core.adapters.fetch_tencent_kline', lambda *a: [])
    with pytest.raises(ValueError): service.kline('510050', days=bad)
