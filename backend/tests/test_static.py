"""静态资源与 SPA 回退回归测试 — 修复"assets 返回 text/html 导致白屏"。

RED 阶段断言：
- /assets/*.js 必须 200 且 Content-Type 为 javascript（当前错误：text/html）
- / 与 /tquote 回退 index.html（text/html）
- 未知路径保持 404，不得回退成 200
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from main import DIST, app

client = TestClient(app)


def _first_asset(suffix: str) -> Path:
    assets = sorted((DIST / "assets").glob(f"*{suffix}"))
    assert assets, f"dist/assets 下没有 {suffix} 产物，请先 npm run build"
    return assets[0]


def test_asset_js_served_as_javascript():
    asset = _first_asset(".js")
    r = client.get(f"/assets/{asset.name}")
    assert r.status_code == 200
    ct = r.headers["content-type"]
    assert "javascript" in ct, f"JS 被当作 {ct} 返回，浏览器会拒绝执行（白屏根因）"


def test_asset_css_served_as_css():
    asset = _first_asset(".css")
    r = client.get(f"/assets/{asset.name}")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_root_serves_index_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="app"' in r.text


def test_spa_route_falls_back_to_index():
    r = client.get("/tquote")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="app"' in r.text


def test_unknown_path_stays_404():
    r = client.get("/no-such-page.js")
    assert r.status_code == 404, "未知路径不应回退成 200 HTML"


def test_unknown_api_stays_404():
    r = client.get("/api/no-such-endpoint")
    assert r.status_code == 404
