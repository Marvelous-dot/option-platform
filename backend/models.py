"""期权数据模块定义"""
from pydantic import BaseModel
from typing import Optional


class OptionContract(BaseModel):
    """单个期权合约数据"""
    # 基本信息
    option_code: str = ""            # 期权代码
    option_name: str = ""            # 期权名称
    target_name: str = ""            # 标的名称
    option_type: str = ""            # 认购/认沽
    strike_price: float = 0.0        # 行权价
    expiry_date: str = ""            # 到期日

    # 行情数据
    last_price: float = 0.0          # 最新价
    change_pct: float = 0.0          # 涨跌幅(%)

    # 希腊字母
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    theta: float = 0.0

    # 价值分析
    time_value: float = 0.0          # 时间价值
    intrinsic_value: float = 0.0     # 内在价值
    implied_volatility: float = 0.0  # 隐含波动率
    theoretical_price: float = 0.0   # 理论价格

    # 标的信息
    target_price: float = 0.0        # 标的最新价
    target_vol_1y: float = 0.0       # 标的近一年波动率

    # 杠杆
    leverage_ratio: float = 0.0      # 杠杆比率
    real_leverage: float = 0.0       # 实际杠杆比率

    # 盈亏计算（BS模型）
    bs_pnl_atm: Optional[float] = None   # ATM时BS盈亏
    bs_pnl_up10: Optional[float] = None  # 标的+10%时BS盈亏
    bs_pnl_down10: Optional[float] = None  # 标的-10%时BS盈亏


class TargetData(BaseModel):
    """单个标的汇总数据"""
    target: str                        # 标的代码
    target_name: str                   # 标的名称
    contract_count: int = 0            # 合约数量
    call_count: int = 0                # 认购数量
    put_count: int = 0                 # 认沽数量
    latest_price: Optional[float] = None  # 标的最新价（从合约聚合）
    volatility: Optional[float] = None    # 标的波动率（从合约聚合）
    contracts: list[OptionContract] = []
    last_updated: str = ""             # 最后更新时间
    update_duration: float = 0.0       # 本次更新耗时(秒)


class PlatformState(BaseModel):
    """平台整体状态"""
    targets: list[TargetData] = []
    total_contracts: int = 0
    total_targets: int = 0
    last_full_update: str = ""
    total_duration: float = 0.0
    status: str = "idle"  # idle, refreshing, error
    last_error: Optional[str] = None
    poll_interval_sec: int = 30
