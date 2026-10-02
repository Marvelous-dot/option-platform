"""Synthetic fixtures only; no network requests."""
from pathlib import Path
from fastapi.testclient import TestClient
from main import app, service
from core.contracts import Contract

CODE = '510050C2609M03000'
C = Contract(CODE, '10000001', '测试购', '510050', 'call', 3.0, '20260923', 10000)


def test_contract_detail_and_missing(monkeypatch):
    monkeypatch.setattr(service, '_catalog', lambda: [C])
    calls = []
    def quote(target, expiry):
        calls.append((target, expiry))
        return {'rows': [{'call': {'contract_id': C.contract_id, 'option_code': CODE,
                    'last_price': 0.1, 'data_status': 'ok', 'freshness': 'unknown'}, 'put': None}],
                'spot': None, 'fetched_at': '2026-09-17T15:00:00+08:00'}
    monkeypatch.setattr(service, 't_quote', quote)
    client = TestClient(app)
    r = client.get('/api/contract/' + CODE)
    assert r.status_code == 200
    d = r.json()
    assert d['contract']['contract_unit'] == 10000
    assert d['contract']['expiry'] == '20260923'
    assert d['quote']['last_price'] == 0.1
    assert d['quote']['freshness'] == 'unknown'
    assert calls == [('510050', '20260923')]
    assert client.get('/api/contract/NOT-LISTED').status_code == 404
    assert len(calls) == 1


def test_missing_quote_preserves_contract(monkeypatch):
    monkeypatch.setattr(service, '_catalog', lambda: [C])
    monkeypatch.setattr(service, 't_quote', lambda *args: {'rows': [], 'spot': None})
    d = TestClient(app).get('/api/contract/' + CODE)
    assert d.status_code == 200
    assert d.json()['contract']['option_code'] == CODE
    assert d.json()['quote']['last_price'] is None
    assert d.json()['quote']['data_status'] == 'unavailable'


def test_detail_route_and_entry():
    r = TestClient(app).get('/contract/' + CODE)
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']
    src = Path(__file__).resolve().parents[2] / 'frontend/src'
    assert "path: '/contract/:code'" in (src / 'main.js').read_text()
    text = (src / 'views/TQuote.vue').read_text()
    assert 'contractLink(row.call)' in text
    assert 'contractLink(row.put)' in text
    assert (src / 'views/ContractDetail.vue').is_file()
