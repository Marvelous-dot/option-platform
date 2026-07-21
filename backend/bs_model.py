"""Black-Scholes期权定价与盈亏计算模块"""
import math
import os
from dataclasses import dataclass, field
from typing import Optional

# 可配置的无风险利率（环境变量优先，默认2.5%）
RISK_FREE_RATE = float(os.environ.get('OPTION_RISK_FREE_RATE', '0.025'))


@dataclass
class BSParams:
    """BS模型输入参数"""
    S: float            # 标的现价
    K: float            # 行权价
    T: float            # 到期时间(年)
    r: float = RISK_FREE_RATE  # 无风险利率(年化)
    sigma: float = 0.25 # 波动率(年化)


def _validate_params(S: float, K: float, T: float, r: float, sigma: float) -> bool:
    """验证BS模型输入参数的合理性"""
    if S <= 0:
        raise ValueError(f"标的价格 S 必须 > 0, 当前: {S}")
    if K <= 0:
        raise ValueError(f"行权价 K 必须 > 0, 当前: {K}")
    if T < 0:
        raise ValueError(f"到期时间 T 必须 >= 0, 当前: {T}")
    if sigma <= 0:
        raise ValueError(f"波动率 sigma 必须 > 0, 当前: {sigma}")
    return True


def norm_cdf(x: float) -> float:
    """标准正态分布累积函数（近似）"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(params: BSParams, option_type: str) -> dict:
    """
    计算Black-Scholes期权价格和希腊字母。
    
    返回:
        {
            'price': 期权理论价格,
            'delta': Delta,
            'gamma': Gamma,
            'vega': Vega,
            'theta': Theta (年),
            'rho_call': Rho(认购),
            'rho_put': Rho(认沽),
            'intrinsic': 内在价值,
            'time_value': 时间价值
        }
    """
    S, K, T, r, sigma = params.S, params.K, params.T, params.r, params.sigma

    # 输入参数验证
    try:
        _validate_params(S, K, T, r, sigma)
    except ValueError as e:
        # 返回零值而非抛出异常，避免中断整个流程
        return {
            'price': 0.0, 'delta': 0.0, 'gamma': 0.0, 'vega': 0.0,
            'theta': 0.0, 'rho_call': 0.0, 'rho_put': 0.0,
            'intrinsic': 0.0, 'time_value': 0.0, 'error': str(e)
        }

    if T <= 0 or sigma <= 0:
        # 到期日或波动率为0，直接返回内在价值
        intrinsic = max(S - K, 0) if option_type == 'call' else max(K - S, 0)
        return {
            'price': intrinsic,
            'delta': 1.0 if option_type == 'call' and S > K else (0.0 if option_type == 'call' and S < K else (-1.0 if option_type == 'put' and S < K else 0.0)),
            'gamma': 0.0,
            'vega': 0.0,
            'theta': 0.0,
            'rho_call': 0.0,
            'rho_put': 0.0,
            'intrinsic': intrinsic,
            'time_value': 0.0
        }

    d1 = (math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == 'call':
        price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
        delta = norm_cdf(d1)
        rho = K * T * math.exp(-r * T) * norm_cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
        delta = norm_cdf(d1) - 1
        rho = -K * T * math.exp(-r * T) * norm_cdf(-d2)

    sqrt_T = math.sqrt(T) if T > 0 else 0.0

    # Gamma: 当 T 接近 0 时数值不稳定，需要保护
    if S > 0 and sigma > 0 and T > 1e-10:
        numerator = math.exp(-d1 * d1 / 2) / (math.sqrt(2 * math.pi))
        gamma = numerator / (S * sigma * sqrt_T)
    else:
        gamma = 0.0

    vega = S * math.exp(-d1 * d1 / 2) / (math.sqrt(2 * math.pi)) * sqrt_T if S > 0 and sigma > 0 and T > 0 else 0.0

    # Theta (年)
    if option_type == 'call':
        theta = (-S * math.exp(-d1 * d1 / 2) * sigma / (math.sqrt(2 * math.pi) * 2 * sqrt_T)
                 - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365
    else:
        theta = (-S * math.exp(-d1 * d1 / 2) * sigma / (math.sqrt(2 * math.pi) * 2 * sqrt_T)
                 + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365

    intrinsic = max(S - K, 0) if option_type == 'call' else max(K - S, 0)
    time_value = price - intrinsic

    return {
        'price': round(price, 4),
        'delta': round(delta, 4),
        'gamma': round(gamma, 6),
        'vega': round(vega, 4),
        'theta': round(theta, 4),
        'rho_call': round(rho, 4),
        'rho_put': round(rho, 4),
        'intrinsic': round(intrinsic, 4),
        'time_value': round(time_value, 4)
    }


def calc_pnl(real_price: float, bs_theoretical: float) -> float:
    """计算盈亏：实际价格 vs BS理论价格"""
    return round(bs_theoretical - real_price, 4)


def calc_future_pnl(S_current: float, K: float, T: float, sigma: float, 
                    r: float = 0.025, S_future: Optional[float] = None) -> float:
    """
    计算未来标的价格下的期权理论价格。
    
    返回: 未来理论价格
    """
    if S_future is None:
        return 0.0
    params = BSParams(S=S_future, K=K, T=T, r=r, sigma=sigma)
    result = bs_price(params, 'call')  # 默认用认购算
    return result['price']


def implied_volatility(market_price: float, S: float, K: float, T: float,
                       option_type: str, r: float = 0.025,
                       tol: float = 1e-6, max_iter: int = 100) -> Optional[float]:
    """
    用牛顿迭代法从期权市场价格反算隐含波动率(IV)。
    
    参数:
        market_price: 期权市场价格
        S: 标的现价
        K: 行权价
        T: 到期时间(年)
        option_type: 'call' 或 'put'
        r: 无风险利率
        tol: 收敛容差
        max_iter: 最大迭代次数
    
    返回:
        隐含波动率(float)，或 None(无法收敛)
    """
    if market_price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None

    # 初始猜测：用20%作为起点
    sigma = 0.20

    for i in range(max_iter):
        params = BSParams(S=S, K=K, T=T, r=r, sigma=sigma)
        result = bs_price(params, option_type)
        price = result['price']
        vega = result['vega']

        diff = price - market_price

        # 如果价格已经足够接近，返回
        if abs(diff) < tol:
            return round(sigma, 6)

        # 如果vega太小，改用二分法
        if vega < 1e-8:
            break

        # 牛顿迭代
        sigma_new = sigma - diff / vega

        # 限制波动率范围 [0.01, 5.0]
        sigma_new = max(0.01, min(5.0, sigma_new))

        if abs(sigma_new - sigma) < tol:
            return round(sigma_new, 6)

        sigma = sigma_new

    # 牛顿法不收敛，回退到二分法
    return _iv_bisection(market_price, S, K, T, option_type, r, tol)


def _iv_bisection(market_price: float, S: float, K: float, T: float,
                  option_type: str, r: float, tol: float) -> Optional[float]:
    """二分法求隐含波动率（备用）"""
    lo, hi = 0.01, 5.0

    for _ in range(200):
        mid = (lo + hi) / 2.0
        params = BSParams(S=S, K=K, T=T, r=r, sigma=mid)
        price = bs_price(params, option_type)['price']

        if abs(price - market_price) < tol:
            return round(mid, 6)

        if price > market_price:
            hi = mid
        else:
            lo = mid

        if hi - lo < tol:
            return round((lo + hi) / 2.0, 6)

    return round((lo + hi) / 2.0, 6)
