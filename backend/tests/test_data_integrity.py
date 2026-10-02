"""Regression fixtures are synthetic test data, never production quotes."""
from dataclasses import replace
import importlib
import time

import pytest
from core.contracts import Contract, pair_t_quote
from core.quotes import normalize_sina_greeks, quote_as_payload, parse_tencent_spot

svc = importlib.import_module('core.service')
NOW = '2026-09-17T14:00:00+08:00'
C = Contract('510050C2609M03000', '10000001', '测试购', '510050', 'call', 3, '20260923', 10000)
P = replace(C, option_code='510050P2609M03000', contract_id='10000002', option_type='put')
NEXT = replace(C, option_code='510050C2610M03000', contract_id='10000003', expiry='20261028')


def setup_service(monkeypatch, quotes=True):
    service = svc.OptionService()
    monkeypatch.setattr(service, '_catalog', lambda: [C, P, NEXT])
    monkeypatch.setattr(svc, 'fetch_tencent_spot', lambda code: None)
    def batch(ids):
        contracts = {c.contract_id: c for c in [C, P, NEXT]}
        return ({cid: {'最新价': '0.1', '交易代码': contracts[cid].option_code} for cid in ids} if quotes else {}, [])
    monkeypatch.setattr(svc, 'fetch_sina_quotes_batch', batch)
    return service


def test_pair_rejects_mixed_expiries():
    with pytest.raises(ValueError):
        pair_t_quote([C, NEXT], {})


def test_pair_rejects_mixed_targets():
    with pytest.raises(ValueError):
        pair_t_quote([C, replace(P, target_code='510300')], {})


def test_adjustment_series_not_overwritten():
    adjusted = replace(C, option_code='510050C2609A03000', contract_id='10000004', contract_unit=10100)
    rows = pair_t_quote([C, P, adjusted], {c.contract_id: {'contract_id': c.contract_id} for c in [C,P,adjusted]})
    assert len(rows) == 2
    assert len({row.key for row in rows}) == 2
    assert sum(row.call is not None for row in rows) == 2


def test_duplicate_side_fails_closed():
    with pytest.raises(ValueError):
        pair_t_quote([C, replace(C, contract_id='10000009')], {})


def test_default_expiry_selects_nearest(monkeypatch):
    service = setup_service(monkeypatch)
    d = service.t_quote('510050', None)
    assert d.get('expiry') == '20260923'
    assert d.get('expiries') == ['20260923', '20261028']
    assert d['rows'][0]['call']['contract_id'] == C.contract_id
    assert d['rows'][0]['put']['contract_id'] == P.contract_id


def test_explicit_expiry_is_preserved(monkeypatch):
    d = setup_service(monkeypatch).t_quote('510050', '20261028')
    assert d.get('expiry') == '20261028'
    assert d['rows'][0]['call']['contract_id'] == NEXT.contract_id
    assert d['rows'][0]['put'] is None


def test_no_market_timestamp_never_implies_realtime(monkeypatch):
    d = setup_service(monkeypatch).t_quote('510050', '20260923')
    assert d['as_of'] is None
    assert d.get('fetched_at')
    assert d.get('freshness') == 'unknown'
    assert '实时' not in d['status_detail']
    q = d['rows'][0]['call']
    assert q.get('freshness') == 'unknown'
    assert q.get('analytics_kind') == 'provider_computed_unverified'


def test_all_empty_returns_unavailable(monkeypatch):
    d = setup_service(monkeypatch, False).t_quote('510050', None)
    assert d['data_status'] == 'unavailable'
    assert d.get('available_count') == 0
    assert d['rows'][0]['call']['last_price'] is None


def test_cache_failure_marks_legs_stale_without_changing_observation(monkeypatch):
    service = setup_service(monkeypatch)
    first = service.t_quote('510050', '20260923')
    key = ('510050', '20260923')
    service._tquote_cache[key] = (time.monotonic() - 100, first)
    def fail(*args):
        raise RuntimeError('test source down')
    monkeypatch.setattr(service, '_build_t_quote', fail)
    stale = service.t_quote('510050', '20260923')
    assert stale['data_status'] == 'stale'
    assert stale.get('freshness') == 'stale'
    assert stale['rows'][0]['call']['data_status'] == 'stale'
    assert stale['rows'][0]['call']['fetched_at'] == first['rows'][0]['call']['fetched_at']
    assert first['rows'][0]['call']['data_status'] == 'ok'
    assert service._tquote_cache[key][1] is first


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf', '-1'])
def test_invalid_price_unavailable(value):
    q = normalize_sina_greeks('1', {'最新价':value}, NOW, None)
    assert q.data_status == 'unavailable'
    assert quote_as_payload(q)['last_price'] is None


def test_tencent_open_uses_index_five():
    parts = ['0'] * 40
    parts[1], parts[3], parts[5], parts[30] = '50ETF', '3.1', '3.0', '20260917140000'
    assert parse_tencent_spot('~'.join(parts))['open'] == 3.0


def test_provider_timestamp_is_not_claimed_verified():
    q = normalize_sina_greeks('1', {'最新价':'0.1'}, NOW, None)
    assert quote_as_payload(q).get('freshness') == 'unknown'


@pytest.mark.parametrize('option_code', ['wrong', '', None])
def test_mismatched_quote_identity_is_unavailable(monkeypatch, option_code):
    service = setup_service(monkeypatch)
    monkeypatch.setattr(svc, 'fetch_sina_quotes_batch', lambda ids: ({cid:{'最新价':'0.1','交易代码':option_code} for cid in ids}, []))
    d = service.t_quote('510050','20260923')
    assert d['data_status'] == 'unavailable'
    assert d['rows'][0]['call']['option_code'] == C.option_code
    assert d['rows'][0]['call']['last_price'] is None


def test_partial_failure_is_not_full_ok(monkeypatch):
    service = setup_service(monkeypatch)
    monkeypatch.setattr(svc, 'fetch_sina_quotes_batch', lambda ids: ({C.contract_id:{'最新价':'0.1', '交易代码':C.option_code}}, [P.contract_id]))
    d = service.t_quote('510050','20260923')
    assert d['data_status'] == 'partial'
    assert d.get('available_count') == 1
    assert d.get('contract_count') == 2
    assert d['rows'][0]['put']['last_price'] is None


def test_all_fetch_failures_preserve_previous_snapshot_as_stale(monkeypatch):
    service = setup_service(monkeypatch)
    first = service.t_quote('510050', '20260923')
    service._tquote_cache[('510050','20260923')] = (time.monotonic()-100, first)
    monkeypatch.setattr(svc, 'fetch_sina_quotes_batch', lambda ids: ({}, ids))
    d = service.t_quote('510050', '20260923')
    assert d['data_status'] == 'stale'
    assert d['rows'][0]['call']['last_price'] == 0.1
    assert d['fetched_at'] == first['fetched_at']
    assert d['spot'] is None


def test_timestamped_snapshot_is_unverified_not_fresh():
    q = normalize_sina_greeks('1', {'最新价':'0.1'}, NOW, '2026-09-16 15:00:00')
    assert quote_as_payload(q).get('freshness') != 'fresh'
    assert quote_as_payload(q).get('market_ts') == '2026-09-16 15:00:00'


def test_unknown_expiry_does_not_fetch_quotes(monkeypatch):
    service = setup_service(monkeypatch)
    monkeypatch.setattr(svc, 'fetch_sina_quotes_batch', lambda ids: pytest.fail('unexpected quote fetch'))
    assert service.t_quote('510050','20990101')['data_status'] == 'unavailable'


def test_stale_quote_serializer_preserves_price():
    q = normalize_sina_greeks('1', {'最新价':'0.1'}, NOW, None)
    q.data_status = 'stale'
    d = quote_as_payload(q)
    assert d['data_status'] == 'stale'
    assert d['last_price'] == 0.1
    assert d.get('freshness') == 'stale'
    assert d['fetched_at'] == NOW


def test_ui_does_not_label_unknown_time_realtime():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'frontend/src'
    content = (root / 'views/TQuote.vue').read_text()
    assert '实时行情' not in content
    assert "if (s === 'ok') return `当日数据" not in content
    assert '时效未知' in content
    assert 'data.fetched_at' in content
    assert ':key="row.key"' in content
    assert '口径未核验' in content
    assert '真实行情' not in (root / 'App.vue').read_text()
    service_text = (Path(__file__).resolve().parents[1] / 'core/service.py').read_text()
    assert '合约有实时行情' not in service_text


def test_catalog_timestamp_is_wall_clock(monkeypatch):
    from datetime import datetime
    service = svc.OptionService()
    monkeypatch.setattr(svc, 'fetch_contract_catalog', lambda: [{'合约编码':C.contract_id,'合约交易代码':C.option_code,'合约简称':C.name,'标的券名称及代码':'50ETF(510050)','类型':'认购','行权价':3,'到期日':'20260923','合约单位':10000}])
    service._catalog()
    assert abs(datetime.fromisoformat(service.catalog_status()['loaded_at']).timestamp()-time.time()) < 10
