"""全量行情 /quotes — 合成 fixtures，无网络。"""
from pathlib import Path
from fastapi.testclient import TestClient
from main import app, service
from core.contracts import Contract

C_CALL = Contract('510050C2609M02650', '10011255', '50ETF购9月2650', '510050', 'call', 2.65, '20260923', 10000)
C_PUT = Contract('510050P2609M02650', '10011256', '50ETF沽9月2650', '510050', 'put', 2.65, '20260923', 10000)
C_CALL2 = Contract('510050C2612M03000', '10011300', '50ETF购12月3000', '510050', 'call', 3.0, '20261223', 10000)

SNAP_09 = {
    'rows': [{'call': {'contract_id': '10011255', 'option_code': '510050C2609M02650',
                       'name': '50ETF购9月2650', 'last_price': 0.3117, 'iv': 0.4605,
                       'delta': 1.0, 'volume': 204, 'data_status': 'ok', 'freshness': 'unknown',
                       'market_ts': None},
              'put': {'contract_id': '10011256', 'option_code': '510050P2609M02650',
                      'name': '50ETF沽9月2650', 'last_price': 0.0003, 'iv': 0.3517,
                      'delta': -1.0, 'volume': 5, 'data_status': 'ok', 'freshness': 'unknown',
                      'market_ts': None}}],
    'spot': {'price': 2.958, 'source': 'tencent'},
    'fetched_at': '2026-09-17T15:00:00+08:00',
    'data_status': 'ok', 'status_detail': '2/2 合约为当日数据',
}
SNAP_12 = {
    'rows': [{'call': {'contract_id': '10011300', 'option_code': '510050C2612M03000',
                       'name': '50ETF购12月3000', 'last_price': 0.2, 'iv': 0.28,
                       'delta': 0.5, 'volume': None, 'data_status': 'ok', 'freshness': 'unknown',
                       'market_ts': None},
              'put': None}],
    'spot': {'price': 2.958, 'source': 'tencent'},
    'fetched_at': '2026-09-17T15:00:00+08:00',
    'data_status': 'partial', 'status_detail': '1/2 合约为当日数据',
}


def _setup(monkeypatch):
    monkeypatch.setattr(service, '_catalog', lambda: [C_CALL, C_PUT, C_CALL2])
    def quote(target, expiry):
        return SNAP_09 if expiry == '20260923' else SNAP_12
    monkeypatch.setattr(service, 't_quote', quote)


def test_all_quotes_lists_all_contracts_with_identity(monkeypatch):
    _setup(monkeypatch)
    d = service.all_quotes('510050')
    assert d['target_code'] == '510050'
    assert d['contract_count'] == 3
    codes = {r['option_code'] for r in d['rows']}
    assert codes == {'510050C2609M02650', '510050P2609M02650', '510050C2612M03000'}
    for r in d['rows']:
        assert r['option_type'] in ('call', 'put')
        assert r['expiry'] in ('20260923', '20261223')
        assert 'data_status' in r and 'freshness' in r
    assert d['data_status'] in ('ok', 'partial')
    assert '实时' not in d['status_detail']


def test_unavailable_quote_keeps_identity_not_zero(monkeypatch):
    _setup(monkeypatch)
    # 12月快照里只有 call，put 合约（此处为 C_PUT 同到期日规则外）——
    # 直接造一个快照缺腿的场景：只返回 call
    monkeypatch.setattr(service, 't_quote', lambda t, e: {
        'rows': [{'call': SNAP_12['rows'][0]['call'], 'put': None}],
        'spot': None, 'fetched_at': None, 'data_status': 'partial'})
    d = service.all_quotes('510050')
    put_row = next(r for r in d['rows'] if r['option_type'] == 'put')
    assert put_row['option_code'] == '510050P2609M02650'  # 身份保留
    assert put_row['last_price'] is None                   # 不补 0
    assert put_row['data_status'] == 'unavailable'


def test_filters_search_and_moneyness(monkeypatch):
    _setup(monkeypatch)
    assert all(r['option_type'] == 'call'
               for r in service.all_quotes('510050', option_type='call')['rows'])
    d = service.all_quotes('510050', search='2650')
    assert {r['option_code'] for r in d['rows']} == {'510050C2609M02650', '510050P2609M02650'}
    d = service.all_quotes('510050', expiry='20261223')
    assert {r['expiry'] for r in d['rows']} == {'20261223'}
    # 虚值筛选：spot=2.958 → call strike>spot 为虚值；spot 缺失时筛选不生效并如实说明
    d = service.all_quotes('510050', moneyness='otm')
    assert all(r['strike'] > 2.958 for r in d['rows'] if r['option_type'] == 'call')
    monkeypatch.setattr(service, 't_quote', lambda t, e: {**SNAP_09, 'spot': None})
    d = service.all_quotes('510050', moneyness='otm')
    assert len(d['rows']) == 3
    assert '标的价格缺失' in d['status_detail']


def test_sort_whitelist_none_last(monkeypatch):
    _setup(monkeypatch)
    rows = service.all_quotes('510050', sort='iv', order='desc')['rows']
    ivs = [r['iv'] for r in rows if r['iv'] is not None]
    assert ivs == sorted(ivs, reverse=True)
    for order in ('asc', 'desc'):
        volume_rows = service.all_quotes('510050', sort='volume', order=order)['rows']
        assert volume_rows[-1]['volume'] is None
        volumes = [r['volume'] for r in volume_rows[:-1]]
        assert volumes == sorted(volumes, reverse=order == 'desc')
    import pytest
    with pytest.raises(ValueError):
        service.all_quotes('510050', sort='evil_field; drop')


def test_atm_per_expiry_and_partial_status(monkeypatch):
    _setup(monkeypatch)
    d = service.all_quotes('510050', moneyness='atm')
    assert len(d['rows']) == 3  # nearest listed strike per expiry, both sides
    monkeypatch.setattr(service, 't_quote', lambda t, e: SNAP_09 if e == '20260923' else {'rows': []})
    d = service.all_quotes('510050')
    assert d['data_status'] == 'partial'
    assert d['available_count'] == 2
    missing = next(r for r in d['rows'] if r['option_code'] == C_CALL2.option_code)
    assert missing['last_price'] is None
    assert missing['data_status'] == 'unavailable'


def test_quotes_api_routes(monkeypatch):
    _setup(monkeypatch)
    client = TestClient(app)
    r = client.get('/api/quotes/510050')
    assert r.status_code == 200
    assert r.json()['contract_count'] == 3
    assert client.get('/api/quotes/NOPE').status_code == 404
    assert client.get('/api/quotes/510050', params={'sort': 'bad'}).status_code == 400
    assert client.get('/quotes').status_code == 200
    src = Path(__file__).resolve().parents[2] / 'frontend/src'
    assert "path: '/quotes'" in (src / 'main.js').read_text()
    text = (src / 'views/Quotes.vue').read_text()
    assert 'contractLink' in text                    # 进合约详情
    assert '实时行情' not in text                      # 数据诚实红线
    assert (src / 'views/ContractDetail.vue').is_file()
