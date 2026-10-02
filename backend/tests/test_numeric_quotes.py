"""Synthetic numeric edge cases; never used as production market data."""
import json

import pytest

from core.quotes import normalize_sina_greeks, parse_tencent_spot, quote_as_payload

NOW = '2026-09-17T14:00:00+08:00'


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf'])
def test_nonfinite_optional_fields_are_null(value):
    kv = {name: value for name in (
        'Delta', 'Gamma', 'Theta', 'Vega', '隐含波动率',
        '最高价', '最低价', '理论价值', '成交量',
    )}
    kv['最新价'] = '0.1'
    payload = quote_as_payload(normalize_sina_greeks('test', kv, NOW, None))
    assert payload['data_status'] == 'ok'
    for name in ('delta', 'gamma', 'theta', 'vega', 'iv', 'high', 'low', 'theory_price', 'volume'):
        assert payload[name] is None
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf', '-1'])
def test_invalid_spot_price_is_unavailable(value):
    parts = ['0'] * 40
    parts[3] = value
    assert parse_tencent_spot('~'.join(parts)) is None


def test_signed_greeks_are_preserved():
    payload = quote_as_payload(normalize_sina_greeks(
        'test', {'最新价': '0.1', 'Delta': '-0.4', 'Theta': '-0.02'}, NOW, None,
    ))
    assert payload['delta'] == -0.4
    assert payload['theta'] == -0.02
