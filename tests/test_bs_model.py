"""期权定价模型测试 - Black-Scholes 核心功能"""
import math
import sys
import os
import pytest

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from bs_model import BSParams, bs_price, calc_pnl, calc_future_pnl, implied_volatility, _validate_params


class TestParamValidation:
    """参数验证测试"""

    def test_valid_params(self):
        assert _validate_params(S=5000, K=5000, T=0.5, r=0.025, sigma=0.25) is True

    def test_invalid_s_zero(self):
        with pytest.raises(ValueError):
            _validate_params(S=0, K=5000, T=0.5, r=0.025, sigma=0.25)

    def test_invalid_s_negative(self):
        with pytest.raises(ValueError):
            _validate_params(S=-100, K=5000, T=0.5, r=0.025, sigma=0.25)

    def test_invalid_k_zero(self):
        with pytest.raises(ValueError):
            _validate_params(S=5000, K=0, T=0.5, r=0.025, sigma=0.25)

    def test_invalid_k_negative(self):
        with pytest.raises(ValueError):
            _validate_params(S=5000, K=-1, T=0.5, r=0.025, sigma=0.25)

    def test_invalid_t_negative(self):
        with pytest.raises(ValueError):
            _validate_params(S=5000, K=5000, T=-0.1, r=0.025, sigma=0.25)

    def test_invalid_sigma_zero(self):
        with pytest.raises(ValueError):
            _validate_params(S=5000, K=5000, T=0.5, r=0.025, sigma=0)

    def test_invalid_sigma_negative(self):
        with pytest.raises(ValueError):
            _validate_params(S=5000, K=5000, T=0.5, r=0.025, sigma=-0.1)


class TestCallOptionPricing:
    """看涨期权定价测试"""

    def test_atm_call_positive(self):
        """ATM call 价格应 > 0"""
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        result = bs_price(params, "call")
        assert result["price"] > 0

    def test_itm_call_more_expensive(self):
        """ITM call 比 ATM call 贵"""
        atm = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        itm = BSParams(S=5000, K=4800, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(itm, "call")["price"] > bs_price(atm, "call")["price"]

    def test_otm_call_cheaper(self):
        """OTM call 比 ATM call 便宜"""
        atm = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        otm = BSParams(S=5000, K=5200, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(otm, "call")["price"] < bs_price(atm, "call")["price"]

    def test_higher_volatility_higher_price(self):
        """更高波动率 -> 更高 call 价格"""
        low = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.15)
        high = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.35)
        assert bs_price(high, "call")["price"] > bs_price(low, "call")["price"]

    def test_longer_maturity_higher_price(self):
        """更长期限 -> 更高 call 价格"""
        short = BSParams(S=5000, K=5000, T=0.1, r=0.025, sigma=0.25)
        long = BSParams(S=5000, K=5000, T=0.5, r=0.025, sigma=0.25)
        assert bs_price(long, "call")["price"] > bs_price(short, "call")["price"]

    def test_higher_strike_lower_price(self):
        """更高行权价 -> 更低 call 价格"""
        low_k = BSParams(S=5000, K=4800, T=0.25, r=0.025, sigma=0.25)
        high_k = BSParams(S=5000, K=5200, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(low_k, "call")["price"] > bs_price(high_k, "call")["price"]


class TestPutOptionPricing:
    """看跌期权定价测试"""

    def test_atm_put_positive(self):
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        result = bs_price(params, "put")
        assert result["price"] > 0

    def test_itm_put_more_expensive(self):
        atm = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        itm = BSParams(S=5000, K=5200, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(itm, "put")["price"] > bs_price(atm, "put")["price"]

    def test_otm_put_cheaper(self):
        atm = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        otm = BSParams(S=5000, K=4800, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(otm, "put")["price"] < bs_price(atm, "put")["price"]


class TestGreeks:
    """Greeks 计算测试"""

    def test_call_delta_in_range(self):
        """Call delta 应在 (0, 1) 之间"""
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        result = bs_price(params, "call")
        assert 0 < result["delta"] < 1

    def test_put_delta_in_range(self):
        """Put delta 应在 (-1, 0) 之间"""
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        result = bs_price(params, "put")
        assert -1 < result["delta"] < 0

    def test_call_delta_itm_higher(self):
        """ITM call delta 接近 1"""
        itm = BSParams(S=5000, K=4800, T=0.25, r=0.025, sigma=0.25)
        at = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(itm, "call")["delta"] > bs_price(at, "call")["delta"]

    def test_call_delta_otm_lower(self):
        """OTM call delta 接近 0"""
        otm = BSParams(S=5000, K=5200, T=0.25, r=0.025, sigma=0.25)
        at = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(otm, "call")["delta"] < bs_price(at, "call")["delta"]

    def test_gamma_positive(self):
        """Gamma 应为正数"""
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        call_result = bs_price(params, "call")
        put_result = bs_price(params, "put")
        assert call_result["gamma"] > 0
        assert put_result["gamma"] > 0

    def test_gamma_atm_largest(self):
        """ATM 期权 Gamma 最大"""
        atm = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        otm = BSParams(S=5000, K=5200, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(atm, "call")["gamma"] > bs_price(otm, "call")["gamma"]

    def test_vega_positive(self):
        """Vega 应为正数"""
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        result = bs_price(params, "call")
        assert result["vega"] > 0

    def test_vega_atm_largest(self):
        """ATM 期权 Vega 最大"""
        atm = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        otm = BSParams(S=5000, K=5200, T=0.25, r=0.025, sigma=0.25)
        assert bs_price(atm, "call")["vega"] > bs_price(otm, "call")["vega"]

    def test_vega_same_for_call_put(self):
        """Call 和 Put 的 Vega 应该相同"""
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=0.25)
        call_vega = bs_price(params, "call")["vega"]
        put_vega = bs_price(params, "put")["vega"]
        assert math.isclose(call_vega, put_vega, rel_tol=1e-9)


class TestPutCallParity:
    """Put-Call Parity 检验"""

    def test_put_call_parity(self):
        """检验 put-call parity: C - P = S - K*e^(-rT)"""
        S = 5000; K = 5000; T = 0.25; r = 0.025; sigma = 0.25
        params = BSParams(S=S, K=K, T=T, r=r, sigma=sigma)
        call_price = bs_price(params, "call")["price"]
        put_price = bs_price(params, "put")["price"]
        parity_rhs = S - K * math.exp(-r * T)
        parity_lhs = call_price - put_price
        assert math.isclose(parity_lhs, parity_rhs, rel_tol=1e-5)


class TestEdgeCases:
    """边界情况测试"""

    def test_zero_time_itm_call(self):
        """到期时 ITM call = 内在价值"""
        params = BSParams(S=5200, K=5000, T=0, r=0.025, sigma=0.25)
        result = bs_price(params, "call")
        assert result["price"] == 200

    def test_zero_time_otm_call(self):
        """到期时 OTM call = 0"""
        params = BSParams(S=4800, K=5000, T=0, r=0.025, sigma=0.25)
        result = bs_price(params, "call")
        assert result["price"] == 0

    def test_zero_time_itm_put(self):
        """到期时 ITM put = 内在价值"""
        params = BSParams(S=4800, K=5000, T=0, r=0.025, sigma=0.25)
        result = bs_price(params, "put")
        assert result["price"] == 200

    def test_invalid_params_return_zero(self):
        """无效参数应返回零值字典"""
        params = BSParams(S=0, K=5000, T=0.5, r=0.025, sigma=0.25)
        result = bs_price(params, "call")
        assert result["price"] == 0
        assert "error" in result


class TestImpliedVolatility:
    """隐含波动率反算测试"""

    def test_iv_atm(self):
        """ATM 期权隐含波动率反算"""
        sigma_true = 0.25
        params = BSParams(S=5000, K=5000, T=0.25, r=0.025, sigma=sigma_true)
        theoretical_price = bs_price(params, "call")["price"]
        iv = implied_volatility(theoretical_price, S=5000, K=5000, T=0.25,
                                option_type="call", r=0.025)
        assert iv is not None
        assert math.isclose(iv, sigma_true, rel_tol=1e-4)

    def test_iv_itm(self):
        """ITM 期权隐含波动率反算"""
        sigma_true = 0.30
        params = BSParams(S=5200, K=5000, T=0.25, r=0.025, sigma=sigma_true)
        theoretical_price = bs_price(params, "call")["price"]
        iv = implied_volatility(theoretical_price, S=5200, K=5000, T=0.25,
                                option_type="call", r=0.025)
        assert iv is not None
        assert math.isclose(iv, sigma_true, rel_tol=1e-4)

    def test_iv_otm(self):
        """OTM 期权隐含波动率反算"""
        sigma_true = 0.20
        params = BSParams(S=4800, K=5000, T=0.25, r=0.025, sigma=sigma_true)
        theoretical_price = bs_price(params, "put")["price"]
        iv = implied_volatility(theoretical_price, S=4800, K=5000, T=0.25,
                                option_type="put", r=0.025)
        assert iv is not None
        assert math.isclose(iv, sigma_true, rel_tol=1e-4)

    def test_iv_invalid_price(self):
        """无效价格应返回 None"""
        assert implied_volatility(0, S=5000, K=5000, T=0.25, option_type="call") is None
        assert implied_volatility(-1, S=5000, K=5000, T=0.25, option_type="call") is None


class TestUtilityFunctions:
    """辅助函数测试"""

    def test_calc_pnl(self):
        """盈亏计算"""
        assert calc_pnl(real_price=30.0, bs_theoretical=35.0) == 5.0
        assert calc_pnl(real_price=35.0, bs_theoretical=30.0) == -5.0

    def test_calc_future_pnl_no_future(self):
        """无未来价格返回 0"""
        assert calc_future_pnl(5000, 5000, 0.25, 0.25) == 0.0

    def test_calc_future_pnl_with_future(self):
        """有未来价格正常计算"""
        result = calc_future_pnl(5000, 5000, 0.25, 0.25, S_future=5200)
        assert result > 0
