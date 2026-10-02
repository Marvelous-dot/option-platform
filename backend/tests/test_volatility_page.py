"""Volatility SPA only; fixtures do not contact market data providers."""
from fastapi.testclient import TestClient
import main
from core.quotes import normalize_sina_greeks, quote_as_payload


def test_volatility_spa_route(tmp_path, monkeypatch):
    (tmp_path / 'index.html').write_text('<div id="app">fixture</div>')
    monkeypatch.setattr(main, 'DIST', tmp_path)
    response = TestClient(main.app).get('/volatility')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert 'fixture' in response.text


def test_volatility_without_build_is_explicit_503(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DIST', tmp_path)
    assert TestClient(main.app).get('/volatility').status_code == 503


def test_unknown_volatility_paths_still_404():
    client = TestClient(main.app)
    for path in ['/volatility/unknown', '/unknown-volatility', '/api/volatility/unknown']:
        assert client.get(path).status_code == 404


def test_source_iv_passes_through_without_unit_conversion():
    # Source percentage value is not multiplied/divided by the backend.
    payload = quote_as_payload(normalize_sina_greeks('fixture', {
        '最新价': '0.1', '隐含波动率': '21.5',
    }, '2026-09-18T14:00:00+08:00', None))
    assert payload['iv'] == 21.5
    assert payload['analytics_kind'] == 'provider_computed_unverified'
