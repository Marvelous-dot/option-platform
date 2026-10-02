"""Synthetic fixtures only; no network requests."""
from fastapi.testclient import TestClient
from main import app, service
from core.contracts import Contract


def make_rows(n):
    return [Contract(f'510050C2609M{i:04d}', f'id{i}', f'测试{i}', '510050', 'call', 3.0, '20260923', 10000) for i in range(n)]


def quote_with_rows(rows):
    def t_quote(target, expiry):
        return {'rows': [{'call': {'contract_id': c.contract_id, 'option_code': c.option_code,
                                     'last_price': 0.1, 'data_status': 'ok', 'freshness': 'unknown'}}
                          for c in rows if c.expiry == expiry],
                'spot': None, 'fetched_at': '2026-09-17T15:00:00+08:00'}
    return t_quote


def test_all_quotes_without_limit_returns_full_rows(monkeypatch):
    """Backward compatibility: omitting limit/offset keeps the full payload."""
    rows = make_rows(7)
    monkeypatch.setattr(service, '_catalog', lambda: rows)
    monkeypatch.setattr(service, 't_quote', quote_with_rows(rows))
    d = TestClient(app).get('/api/quotes/510050').json()
    assert len(d['rows']) == 7
    assert d['filtered_count'] == 7
    assert d['limit'] == 0            # 0 = unlimited, explicit in payload
    assert d['offset'] == 0
    assert d['total'] == 7


def test_all_quotes_limit_offset_slices_after_sort_and_filters(monkeypatch):
    """Pagination applies AFTER filter+sort; total reflects the full filtered set."""
    rows = make_rows(6)
    monkeypatch.setattr(service, '_catalog', lambda: rows)
    monkeypatch.setattr(service, 't_quote', quote_with_rows(rows))
    d = TestClient(app).get('/api/quotes/510050?limit=2&offset=2&sort=strike&order=desc').json()
    assert d['limit'] == 2 and d['offset'] == 2
    assert d['total'] == 6                       # filtered set size, not page size
    assert len(d['rows']) == 2
    # offset/limit never changes total or status; just which window is returned
    d2 = TestClient(app).get('/api/quotes/510050?limit=2&offset=4&sort=strike&order=desc').json()
    assert len(d2['rows']) == 2
    assert d['rows'][0]['option_code'] != d2['rows'][0]['option_code']


def test_all_quotes_offset_beyond_total_yields_empty_page_not_error(monkeypatch):
    rows = make_rows(3)
    monkeypatch.setattr(service, '_catalog', lambda: rows)
    monkeypatch.setattr(service, 't_quote', quote_with_rows(rows))
    d = TestClient(app).get('/api/quotes/510050?limit=5&offset=10').json()
    assert d['rows'] == []
    assert d['total'] == 3


def test_all_quotes_rejects_bad_limit_offset(monkeypatch):
    rows = make_rows(3)
    monkeypatch.setattr(service, '_catalog', lambda: rows)
    monkeypatch.setattr(service, 't_quote', quote_with_rows(rows))
    # Negative values surface as 400 (domain rule); non-integral query params
    # are rejected by FastAPI's own int coercion as 422 — both are rejected.
    assert TestClient(app).get('/api/quotes/510050?limit=-1').status_code == 400
    assert TestClient(app).get('/api/quotes/510050?offset=-2').status_code == 400
    assert TestClient(app).get('/api/quotes/510050?limit=abc').status_code in {400, 422}
