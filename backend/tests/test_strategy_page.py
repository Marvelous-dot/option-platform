"""Local-only strategy SPA route and source text regression checks."""
from pathlib import Path
from fastapi.testclient import TestClient
from main import app


def test_strategy_spa_route():
    response = TestClient(app).get('/strategy')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']


def test_strategy_page_has_no_corrupt_text():
    page = Path(__file__).resolve().parents[2] / 'frontend/src/views/Strategy.vue'
    assert '\ufffd' not in page.read_text()
    assert '带符号净支出' in page.read_text()


def test_unknown_strategy_path_is_not_spa():
    assert TestClient(app).get('/strategy/unknown').status_code == 404
