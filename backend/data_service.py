"""期权数据获取服务 - 腾讯财经标的价格 + BS模型模拟"""
import math
import random
import re
import time
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from models import OptionContract, TargetData, PlatformState
from bs_model import bs_price, calc_pnl, BSParams, implied_volatility
from iv_store import save_iv_batch, save_dashboard_snapshot, save_daily_summary


# 标的映射
TARGET_MAP = {
    "510050": {"name": "上证50ETF华夏", "code": "510050", "price": 3.00, "vol": 0.20},
    "510300": {"name": "沪深300ETF华泰柏瑞", "code": "510300", "price": 4.95, "vol": 0.22},
    "510500": {"name": "中证500ETF南方", "code": "510500", "price": 8.75, "vol": 0.28},
    "588000": {"name": "科创50ETF华夏", "code": "588000", "price": 1.94, "vol": 0.35},
    "588080": {"name": "科创50ETF易方达", "code": "588080", "price": 1.88, "vol": 0.35},
}

# 行权价间距规则 (单位: 元)
# 价格区间 -> 间距
STRIKE_RULES = [
    (3.0, 0.05),   # 3.0以下: 0.05
    (5.0, 0.10),   # 3.0-5.0: 0.10
    (10.0, 0.25),  # 5.0-10.0: 0.25
    (20.0, 0.50),  # 10.0-20.0: 0.50
    (50.0, 1.00),  # 20.0-50.0: 1.00
    (100.0, 2.00), # 50.0-100.0: 2.00
    (float('inf'), 5.00), # 100以上: 5.00
]

# 到期月份: 当月、下月、随后两个季度月
EXPIRY_MONTHS_AHEAD = [0, 1, 3, 6]  # 相对当前月的偏移


def fetch_tencent_prices() -> dict:
    """从腾讯财经获取标的实时价格"""
    codes = [f"sh{info['code']}" for info in TARGET_MAP.values()]
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    
    result = {}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode('gbk')
        
        for line in raw.strip().split(';'):
            if not line or '~' not in line:
                continue
            parts = line.split('~')
            if len(parts) > 40:
                code = parts[2]
                try:
                    price = float(parts[3])
                    change_pct = float(parts[32])
                    high52w = float(parts[47]) if len(parts) > 47 and parts[47] else 0
                    low52w = float(parts[48]) if len(parts) > 48 and parts[48] else 0
                    # 成交量（手）
                    volume = float(parts[36]) if len(parts) > 36 and parts[36] else 0
                    # 用52周高低估算年化波动率
                    if low52w > 0 and high52w > low52w:
                        # Parkinsons estimator: vol ≈ (high-low)/low / (2.5 for annual)
                        est_vol = (high52w - low52w) / ((high52w + low52w) / 2) / 2.5
                    else:
                        est_vol = 0.20
                    result[code] = {
                        "price": price,
                        "change_pct": change_pct,
                        "vol": max(min(est_vol, 0.60), 0.15),
                        "volume": volume,
                    }
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        print(f"腾讯财经获取失败: {e}")
    
    return result


def generate_strikes(spot: float, num_each_side: int = 8) -> list:
    """根据标的价格生成行权价列表"""
    if spot <= 0:
        return []
    
    # 确定间距
    step = 0.05
    for threshold, s in STRIKE_RULES:
        if spot < threshold:
            step = s
            break
    
    # 找到最接近的整数倍行权价
    atm = round(spot / step) * step
    
    strikes = []
    for i in range(-num_each_side, num_each_side + 1):
        k = round(atm + i * step, 3)
        if k > 0:
            strikes.append(k)
    
    return sorted(set(strikes))


def get_expiry_dates() -> list:
    """生成到期日列表"""
    today = datetime.now()
    expiries = []
    
    for month_offset in EXPIRY_MONTHS_AHEAD:
        # 计算目标月份
        target_month = today.month + month_offset
        target_year = today.year + (target_month - 1) // 12
        target_month = (target_month - 1) % 12 + 1
        
        # 当月第四个周三
        first_day = datetime(target_year, target_month, 1)
        # 找到第一个周三
        day_of_week = first_day.weekday()  # 0=周一
        days_to_wed = (2 - day_of_week) % 7
        first_wed = first_day + timedelta(days=days_to_wed)
        # 第四个周三 = 第一个周三 + 21天
        fourth_wed = first_wed + timedelta(days=21)
        
        # 如果已过，跳过（除非是当月且还没到）
        if fourth_wed < today:
            continue
        
        expiries.append(fourth_wed.strftime("%Y%m%d"))
    
    return expiries


def _build_contract(option_code: str, option_name: str, target_info: dict,
                    strike: float, expiry_str: str, S: float, sigma: float,
                    option_type: str, target_change_pct: float = 0.0) -> OptionContract:
    """用BS模型构造一个期权合约。
    
    优化：直接用 sigma 作为 IV（数据源本身就是 BS 生成，无需反算），
    同时复用 bs_price 结果计算 ±10% 盈亏，避免重复调用。
    """
    try:
        expiry = datetime.strptime(expiry_str, "%Y%m%d")
        days = (expiry - datetime.now()).days
        T = max(days / 365.0, 0.001)
        bs_type = "call" if option_type == "认购" else "put"
        K = strike

        # 模拟真实波动率微笑：ATM 最低，远离 ATM 时 IV 升高
        # 真实市场特征：
        #   1) 微笑曲线: IV = sigma + alpha * (dist_from_atm)^2
        #      alpha 控制曲率，典型值让最远行权价比 ATM 高 20-40%
        #   2) 认沽偏斜: Put IV 系统性高于 Call（约 2-8%）
        #   3) 期限结构: 远月 ATM IV 略高，但曲面更平（微笑幅度小）
        dist_from_atm = abs(K - S) / S  # 距 ATM 的相对距离 (如 0.1 = 10%)

        # 微笑幅度：让最远行权价(约30%距离)比 ATM 高 ~30%
        # sigma + smile_slope * dist^2, 其中 smile_slope = sigma * 3.0
        smile_slope = sigma * 3.0
        smile_iv = sigma + smile_slope * (dist_from_atm ** 2)

        # 期限结构：远月 ATM IV 略高(+5%/年)，但微笑幅度衰减
        # time_factor: 近月=1.0(完整微笑), 远月=0.3(平坦)
        time_factor = 1.0 / (1.0 + T * 0.5)  # T=0.25->0.89, T=0.5->0.67, T=1->0.5
        # ATM IV 随期限微升
        atm_premium = 1.0 + T * 0.05  # 每年 +5%
        base_iv = smile_iv * time_factor * atm_premium + sigma * (1.0 - time_factor)

        # 认沽偏斜: Put IV 系统性高于 Call
        skew = 1.04 if option_type == "认沽" else 1.00  # Put 高 4%

        # 微小噪声（不掩盖微笑形态，只增加真实感）
        random.seed(hash(f"{option_code}"))
        noise = random.gauss(0, sigma * 0.01)  # 1% 标准差

        computed_iv = max(0.05, min(2.0, base_iv * skew + noise))

        # 用合约自己的 IV 计算理论价格
        from bs_model import RISK_FREE_RATE
        params = BSParams(S=S, K=K, T=T, r=RISK_FREE_RATE, sigma=computed_iv)
        bs = bs_price(params, bs_type)
        
        # 构造名称
        expiry_short = expiry_str[2:6]  # eg: 2607

        # 复用 T 计算 ±10% 盈亏（只改 S，其他参数相同）
        from bs_model import RISK_FREE_RATE
        bs_up = bs_price(BSParams(S=S*1.1, K=K, T=T, r=RISK_FREE_RATE, sigma=computed_iv), bs_type)
        bs_dn = bs_price(BSParams(S=S*0.9, K=K, T=T, r=RISK_FREE_RATE, sigma=computed_iv), bs_type)

        return OptionContract(
            option_code=option_code,
            option_name=option_name,
            target_name=target_info["name"],
            option_type=option_type,
            strike_price=K,
            expiry_date=expiry_str,
            last_price=bs["price"],
            change_pct=target_change_pct,  # 用标的涨跌幅作为合约涨跌幅参考
            delta=bs["delta"],
            gamma=bs["gamma"],
            vega=bs["vega"],
            rho=bs["rho_call"] if option_type == "认购" else bs["rho_put"],
            theta=bs["theta"],
            time_value=bs["time_value"],
            intrinsic_value=bs["intrinsic"],
            implied_volatility=computed_iv,
            theoretical_price=bs["price"],
            target_price=S,
            target_vol_1y=sigma,
            leverage_ratio=S / bs["price"] if bs["price"] > 0 else 0,
            real_leverage=S / bs["price"] if bs["price"] > 0 else 0,
            # BS盈亏
            bs_pnl_atm=0.0,  # last_price == theoretical, 所以盈亏为0
            bs_pnl_up10=calc_pnl(bs["price"], bs_up["price"]),
            bs_pnl_down10=calc_pnl(bs["price"], bs_dn["price"]),
        )
    except Exception as e:
        print(f"构建合约失败 {option_code}: {e}")
        return None


def generate_contracts_for_target(target_code: str, target_info: dict,
                                  S: float, sigma: float,
                                  target_change_pct: float = 0.0) -> list:
    """为单个标的所有到期日、行权价、认购/认沽生成合约"""
    contracts = []
    strikes = generate_strikes(S)
    expiries = get_expiry_dates()
    
    seq = 1
    for expiry in expiries:
        expiry_short = expiration_short(expiry)
        for strike in strikes:
            for opt_type in ["认购", "认沽"]:
                type_code = "C" if opt_type == "认购" else "P"
                option_code = f"{target_code}{expiry}{type_code}{int(strike*1000):04d}"
                option_name = f"{target_info['name'][:2]}{opt_type}{expiry_short}{strike}"
                
                contract = _build_contract(
                    option_code, option_name, target_info,
                    strike, expiry, S, sigma, opt_type,
                    target_change_pct
                )
                if contract:
                    contracts.append(contract)
                seq += 1
    
    return contracts


def expiration_short(expiry_str: str) -> str:
    """20260719 -> 6月"""
    m = int(expiry_str[4:6])
    return f"{m}月"


def fetch_all_data() -> PlatformState:
    """
    获取所有标的的期权数据。
    
    流程：
    1. 腾讯财经获取标的现价
    2. 本地生成合约列表 + BS模型定价
    3. 按标的分组
    """
    start_time = time.time()
    state = PlatformState()
    state.status = "refreshing"
    
    try:
        # Step 1: 获取标的实时价格
        tencent_data = fetch_tencent_prices()
        
        # Step 2: 按标的分组生成合约
        targets = []
        for target_code, target_info in TARGET_MAP.items():
            # 获取实时价格
            tcode = target_code
            if tcode in tencent_data:
                S = tencent_data[tcode]["price"]
                sigma = tencent_data[tcode]["vol"]
                target_change_pct = tencent_data[tcode].get("change_pct", 0.0)
            else:
                # 降级用默认值
                S = target_info["price"]
                sigma = target_info["vol"]
                target_change_pct = 0.0
            
            # 生成期权合约
            contracts = generate_contracts_for_target(target_code, target_info, S, sigma, target_change_pct)
            
            if contracts:
                target_data = TargetData(
                    target=target_code,
                    target_name=target_info["name"],
                    contract_count=len(contracts),
                    call_count=sum(1 for c in contracts if c.option_type == "认购"),
                    put_count=sum(1 for c in contracts if c.option_type == "认沽"),
                    contracts=contracts,
                    last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    update_duration=time.time() - start_time,
                    latest_price=S,
                    volatility=sigma,
                )
                targets.append(target_data)
                state.total_contracts += len(contracts)
        
        state.targets = targets
        state.total_targets = len(targets)
        state.last_full_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state.total_duration = time.time() - start_time
        state.status = "idle"

        # Step 3: 保存IV历史数据 + 在内存中预计算 dashboard/summary 数据
        # 优化：Step 3 已遍历全量合约，直接复用 iv_records 构建 snap_cache，
        # 避免 Step 4 逐标循环查询 get_available_expiries + get_iv_surface_snapshot（窗口函数在大表上很慢）
        try:
            iv_records = []
            # 同时按 (target, expiry) 分组，用于 Step 4 的 snap_cache
            snap_cache_by_target = {}  # {target_code: {expiry: [{strike, option_type, iv, ...}]}}
            for t in targets:
                snap_cache_by_target[t.target] = {}
                for c in t.contracts:
                    if c.implied_volatility and c.implied_volatility > 0:
                        rec = {
                            "target_code": t.target,
                            "expiry": c.expiry_date,
                            "strike": c.strike_price,
                            "option_type": c.option_type,
                            "iv": c.implied_volatility,
                            "option_price": c.last_price,
                            "spot_price": t.latest_price,
                            "days_to_expiry": max((datetime.strptime(c.expiry_date, "%Y%m%d") - datetime.now()).days, 0),
                        }
                        iv_records.append(rec)
                        # 同步构建 snap_cache
                        snap_cache_by_target[t.target].setdefault(c.expiry_date, []).append({
                            "strike": c.strike_price,
                            "option_type": c.option_type,
                            "iv": c.implied_volatility,
                            "option_price": c.last_price,
                            "spot_price": t.latest_price,
                            "days_to_expiry": rec["days_to_expiry"],
                        })
            if iv_records:
                save_iv_batch(iv_records)
                print(f"  IV历史保存: {len(iv_records)}条")
        except Exception as e:
            print(f"  IV历史保存失败: {e}")

        # Step 4: 保存综合走势快照 (HV + IV + 标的 + PCR)
        # 优化：直接用 snap_cache_by_target（内存数据），不再逐标查库
        try:
            for t in targets:
                # 计算 HV（用 iv_history 中的标的价格序列）
                from iv_store import get_dashboard_series
                prev_series = get_dashboard_series(t.target, days=60)
                closes = [s["close"] for s in prev_series]
                closes.append(t.latest_price)
                
                def calc_hv(prices, window):
                    if len(prices) < window + 1:
                        return None
                    import math
                    log_returns = []
                    for i in range(len(prices) - window, len(prices)):
                        if prices[i] > 0 and prices[i-1] > 0:
                            log_returns.append(math.log(prices[i] / prices[i-1]))
                    if len(log_returns) < 2:
                        return None
                    mean_r = sum(log_returns) / len(log_returns)
                    var = sum((r - mean_r) ** 2 for r in log_returns) / (len(log_returns) - 1)
                    return math.sqrt(var * 252)  # 年化
                
                hv5 = calc_hv(closes, 5)
                hv10 = calc_hv(closes, 10)
                hv20 = calc_hv(closes, 20)
                hv60 = calc_hv(closes, 60)
                
                # ATM IV + 加权 IV（直接用内存中的 snap_cache，无需查库）
                atm_iv = None
                iv_weighted = None
                snap_cache = snap_cache_by_target.get(t.target, {})
                if snap_cache:
                    first_exp = min(snap_cache.keys())
                    first_snap = snap_cache[first_exp]
                    spot = t.latest_price
                    atm_record = min(first_snap, key=lambda x: abs(x["strike"] - spot))
                    atm_iv = atm_record["iv"]
                    valid = [s for s in first_snap if s["iv"] > 0]
                    if valid:
                        weights = [1.0 / (1.0 + abs(s["strike"] - spot)) for s in valid]
                        iv_weighted = sum(s["iv"] * w for s, w in zip(valid, weights)) / sum(weights)

                # PCR (Put-Call Ratio)
                put_count = sum(1 for c in t.contracts if c.option_type == "认沽")
                call_count = sum(1 for c in t.contracts if c.option_type == "认购")
                pcr_ratio = put_count / call_count if call_count > 0 else 1.0

                # 方法2: 虚值认沽 IV / 虚值认购 IV (skew-based PCR)
                pcr_iv_skew = None
                try:
                    spot = t.latest_price
                    otm_puts = [c for c in t.contracts if c.option_type == "认沽" and c.strike_price < spot]
                    otm_calls = [c for c in t.contracts if c.option_type == "认购" and c.strike_price > spot]
                    if otm_puts and otm_calls:
                        avg_put_iv = sum(c.implied_volatility for c in otm_puts) / len(otm_puts)
                        avg_call_iv = sum(c.implied_volatility for c in otm_calls) / len(otm_calls)
                        pcr_iv_skew = avg_put_iv / avg_call_iv if avg_call_iv > 0 else 1.0
                except Exception:
                    pass

                # 成交量
                tcode = t.target
                spot_volume = tencent_data.get(tcode, {}).get("volume", 0)

                save_dashboard_snapshot(
                    target_code=t.target,
                    close_price=t.latest_price,
                    hv_5d=hv5, hv_10d=hv10, hv_20d=hv20, hv_60d=hv60,
                    iv_atm=atm_iv, iv_weighted=iv_weighted,
                    pcr_ratio=pcr_ratio, pcr_iv_skew=pcr_iv_skew,
                    spot_volume=spot_volume,
                )
                print(f"  Dashboard快照: {t.target} close={t.latest_price} hv20={hv20} atm_iv={atm_iv} pcr={pcr_ratio:.2f}")

                # 保存IV日汇总（复用 snap_cache，不再重复查询）
                try:
                    for exp, snap in snap_cache.items():
                        spot2 = t.latest_price
                        atm_rec2 = min(snap, key=lambda x: abs(x["strike"] - spot2))
                        atm_iv_val = atm_rec2["iv"]
                        otm_puts2 = [s for s in snap if s["option_type"] == "认沽" and s["strike"] < spot2]
                        otm_calls2 = [s for s in snap if s["option_type"] == "认购" and s["strike"] > spot2]
                        skew = (sum(s["iv"] for s in otm_puts2) / len(otm_puts2)) / (sum(s["iv"] for s in otm_calls2) / len(otm_calls2)) if otm_puts2 and otm_calls2 else 1.0
                        all_ivs = [s["iv"] for s in snap if s["iv"] > 0]
                        save_daily_summary(
                            target_code=t.target,
                            expiry=exp,
                            atm_iv=atm_iv_val,
                            iv_skew=skew,
                            iv_term_slope=0.0,
                            avg_iv=sum(all_ivs) / len(all_ivs) if all_ivs else 0,
                            min_iv=min(all_ivs) if all_ivs else 0,
                            max_iv=max(all_ivs) if all_ivs else 0,
                            iv_25delta=atm_iv_val,
                            iv_75delta=atm_iv_val,
                            spot_price=spot2,
                            contract_count=len(snap),
                        )
                except Exception as de:
                    print(f"  IV日汇总保存失败: {de}")
        except Exception as e:
            print(f"  Dashboard快照保存失败: {e}")
        
    except Exception as e:
        state.status = "error"
        state.last_error = str(e)
    
    return state
