"""期权展示平台 - FastAPI主应用"""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from typing import Optional
from dotenv import load_dotenv

from models import PlatformState
from data_service import fetch_all_data
from iv_store import (
    init_db,
    get_iv_kline, get_atm_iv_series, get_iv_surface_snapshot,
    get_iv_smile, get_term_structure, get_available_expiries,
    get_iv_surface_3d, get_dashboard_series, get_latest_dashboard,
    get_kline_data,
)

# 加载配置
load_dotenv()

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# 全局数据缓存
state_cache: PlatformState = PlatformState(status="idle")
state_cache.poll_interval_sec = POLL_INTERVAL
refresh_task: asyncio.Task | None = None


async def _background_refresh():
    """后台定时刷新数据"""
    global state_cache
    refresh_count = 0
    while True:
        try:
            print(f"[{datetime.now()}] 开始刷新数据...")
            state_cache = fetch_all_data()
            print(f"[{datetime.now()}] 刷新完成: {state_cache.total_contracts}条合约, "
                  f"耗时{state_cache.total_duration:.1f}秒")
            refresh_count += 1
            # 每100次刷新（约50分钟）清理一次过期数据，保留30天
            if refresh_count % 100 == 0:
                try:
                    from iv_store import cleanup_old_data
                    cleanup_old_data(days=7)
                    print(f"[{datetime.now()}] 已清理7天前的IV历史数据")
                except Exception as ce:
                    print(f"[{datetime.now()}] 清理失败: {ce}")
        except Exception as e:
            print(f"[{datetime.now()}] 刷新失败: {e}")
            state_cache.status = "error"
            state_cache.last_error = str(e)
        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print(f"期权展示平台后端启动中...")
    print(f"轮询间隔: {POLL_INTERVAL}秒")
    
    # 初始化数据库表
    try:
        init_db()
        print("数据库初始化完成")
    except Exception as e:
        print(f"WARNING: 数据库初始化失败: {e}")
    
    # 首次立即刷新（带超时保护）
    global state_cache
    try:
        state_cache = await asyncio.wait_for(asyncio.to_thread(fetch_all_data), timeout=60)
        print(f"初始数据加载完成: {state_cache.total_contracts}条合约")
    except asyncio.TimeoutError:
        print("WARNING: 初始数据加载超时，使用空数据启动")
        state_cache.last_error = "初始数据加载超时"
        state_cache.status = "error"
    except Exception as e:
        print(f"WARNING: 初始数据加载失败: {e}")
        state_cache.last_error = str(e)
        state_cache.status = "error"
    
    # 启动后台任务
    global refresh_task
    refresh_task = asyncio.create_task(_background_refresh())
    print("后台刷新任务已启动")
    
    yield
    
    # 关闭时
    print("正在关闭后台刷新任务...")
    if refresh_task:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
    print("后端已关闭")


app = FastAPI(
    title="期权展示平台",
    description="A股ETF期权实时展示平台 - 5标的706合约",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS[0] != "*" else ["*"],
    allow_credentials="true" if os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true" else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/state")
async def get_state():
    """获取平台整体状态"""
    return state_cache.model_dump()


@app.get("/api/targets")
async def get_targets():
    """获取所有标的数据"""
    return {
        "targets": [t.model_dump() for t in state_cache.targets],
        "total_contracts": state_cache.total_contracts,
        "last_updated": state_cache.last_full_update,
        "total_duration": state_cache.total_duration
    }


@app.get("/api/target/{target_code}")
async def get_target(target_code: str):
    """获取指定标的数据"""
    for t in state_cache.targets:
        if t.target == target_code:
            return t.model_dump()
    raise HTTPException(status_code=404, detail=f"标的 {target_code} 不存在")


@app.get("/api/contract/{option_code}")
async def get_contract(option_code: str):
    """获取单个合约详情"""
    for t in state_cache.targets:
        for c in t.contracts:
            if c.option_code == option_code:
                return c.model_dump()
    raise HTTPException(status_code=404, detail=f"合约 {option_code} 不存在")


from pydantic import BaseModel


class BsPnlRequest(BaseModel):
    spot_price: Optional[float] = None
    volatility: Optional[float] = None
    days_to_expiry: Optional[float] = None


@app.post("/api/contract/{option_code}/bs_pnl")
async def bs_pnl_calc(option_code: str, req: BsPnlRequest):
    """计算单个合约的Black-Scholes盈亏"""
    type_map = {'认购': 'call', '认沽': 'put'}
    for t in state_cache.targets:
        for c in t.contracts:
            if c.option_code == option_code:
                from bs_model import bs_price, BSParams, calc_pnl, RISK_FREE_RATE
                spot = req.spot_price or c.target_price or 3.0
                vol = req.volatility or (c.target_vol_1y if c.target_vol_1y else 0.20)
                days = req.days_to_expiry or (c.days_to_expiry if c.days_to_expiry else 30)
                T = days / 365.0
                opt_type = type_map.get(c.option_type, 'call')

                # Compute theoretical price at current spot
                the_price = bs_price(
                    BSParams(S=spot, K=c.strike_price, T=T, r=RISK_FREE_RATE, sigma=vol),
                    opt_type
                )

                # PnL profile: vary spot price
                profile_points = []
                range_pct = 0.3
                steps = 30
                for i in range(steps):
                    pct = -range_pct + 2 * range_pct * i / (steps - 1)
                    test_spot = spot * (1 + pct)
                    bs = bs_price(
                        BSParams(S=test_spot, K=c.strike_price, T=T, r=RISK_FREE_RATE, sigma=vol),
                        opt_type
                    )
                    pnl = calc_pnl(c.last_price, bs['price'])
                    profile_points.append({
                        'spot_price': round(test_spot, 4),
                        'pnl': round(pnl, 4)
                    })

                return {
                    "theoretical_price": round(the_price['price'], 6),
                    "intrinsic_value": round(the_price.get('intrinsic', 0), 6),
                    "time_value": round(the_price.get('time_value', 0), 6),
                    "price_diff": round(the_price['price'] - (c.last_price or 0), 6),
                    "greeks": {
                        "delta": round(the_price.get('delta', 0), 6),
                        "gamma": round(the_price.get('gamma', 0), 6),
                        "theta": round(the_price.get('theta', 0), 6),
                        "vega": round(the_price.get('vega', 0), 6),
                        "rho": round(the_price.get('rho_call', 0), 6),
                    },
                    "pnl_profile": {"points": profile_points}
                }
    raise HTTPException(status_code=404, detail=f"合约 {option_code} 不存在")


@app.get("/api/tquote/{target_code}")
async def get_tquote(target_code: str, expiry: Optional[str] = None):
    """
    T型报价数据。
    
    返回按行权价分组的认购/认沽合约对。
    如果指定 expiry，只返回该到期日的数据。
    """
    from collections import defaultdict
    
    for t in state_cache.targets:
        if t.target == target_code:
            # 按到期日分组
            by_expiry = defaultdict(lambda: defaultdict(dict))
            for c in t.contracts:
                exp = c.expiry_date
                strike = c.strike_price
                if c.option_type == "认购":
                    by_expiry[exp][strike]["call"] = c.model_dump()
                else:
                    by_expiry[exp][strike]["put"] = c.model_dump()
            
            # 构建响应
            result = {}
            for exp, strikes_data in by_expiry.items():
                if expiry and exp != expiry:
                    continue
                
                rows = []
                for strike in sorted(strikes_data.keys()):
                    row = {
                        "strike": strike,
                        "call": strikes_data[strike].get("call"),
                        "put": strikes_data[strike].get("put"),
                    }
                    rows.append(row)
                
                result[exp] = {
                    "expiry": exp,
                    "rows": rows,
                    "spot_price": t.latest_price,
                    "volatility": t.volatility,
                }
            
            return {
                "target": target_code,
                "target_name": t.target_name,
                "spot_price": t.latest_price,
                "volatility": t.volatility,
                "expiries": result,
            }
    
    raise HTTPException(status_code=404, detail=f"标的 {target_code} 不存在")


# ============================================================
# 波动率数据 API
# ============================================================

@app.get("/api/volatility/expiries/{target_code}")
async def get_vol_expiries(target_code: str):
    """获取某标的的所有可用到期日"""
    expiries = get_available_expiries(target_code)
    return {"target": target_code, "expiries": expiries}


@app.get("/api/volatility/kline/{target_code}")
async def get_vol_kline(target_code: str, expiry: str, days: int = 30):
    """获取IV K线数据（平价期权IV时间序列）"""
    data = get_atm_iv_series(target_code, expiry, days)
    return {
        "target": target_code,
        "expiry": expiry,
        "days": days,
        "data": data,
        "count": len(data)
    }


@app.get("/api/kline/{target_code}")
async def get_kline(target_code: str, days: int = 90):
    """获取标的OHLC K线数据"""
    data = get_kline_data(target_code, days)
    return {
        "target": target_code,
        "days": days,
        "data": data,
        "count": len(data)
    }


@app.post("/api/kline/backfill/{target_code}")
async def backfill_kline_api(target_code: str, days: int = 60):
    """回填标的历史K线数据"""
    count = backfill_kline_daily(target_code, days)
    return {
        "target": target_code,
        "inserted": count,
        "days": days,
    }


@app.get("/api/volatility/surface/{target_code}")
async def get_vol_surface(target_code: str, expiry: str):
    """获取波动率曲面快照（某到期日所有行权价的IV）"""
    data = get_iv_surface_snapshot(target_code, expiry, cached_targets=state_cache.targets)
    return {
        "target": target_code,
        "expiry": expiry,
        "data": data,
        "count": len(data)
    }


@app.get("/api/volatility/smile/{target_code}")
async def get_vol_smile(target_code: str, expiry: str):
    """获取波动率微笑曲线数据"""
    data = get_iv_smile(target_code, expiry, cached_targets=state_cache.targets)
    calls = [d for d in data if d["option_type"] == "认购"]
    puts = [d for d in data if d["option_type"] == "认沽"]
    return {
        "target": target_code,
        "expiry": expiry,
        "calls": calls,
        "puts": puts,
        "spot_price": data[0]["spot_price"] if data else None,
    }


@app.get("/api/volatility/term/{target_code}")
async def get_vol_term_structure(target_code: str):
    """获取IV期限结构（各到期日的ATM IV）— 使用内存缓存加速"""
    data = get_term_structure(target_code, cached_targets=state_cache.targets)
    return {
        "target": target_code,
        "data": data,
        "count": len(data)
    }


@app.get("/api/volatility/surface3d/{target_code}")
async def get_vol_surface_3d(target_code: str):
    """获取3D波动率曲面数据（行权价×到期日→IV网格）— 使用内存缓存加速"""
    data = get_iv_surface_3d(target_code, cached_targets=state_cache.targets)
    return {
        "target": target_code,
        **data
    }


@app.get("/api/dashboard/series/{target_code}")
async def get_dashboard_series_api(target_code: str, days: int = 90):
    """获取综合走势数据（HV + IV + 标的 + PCR）"""
    data = get_dashboard_series(target_code, days)
    latest = get_latest_dashboard(target_code)
    return {
        "target": target_code,
        "data": data,
        "latest": latest,
        "count": len(data)
    }


@app.get("/api/volatility/contract/{option_code}")
async def get_contract_iv_history(option_code: str, days: int = 30):
    """获取单个合约的IV历史"""
    import re as _re
    m = _re.match(r'^(\d{6})(\d{8})([CP])(\d{4})$', option_code)
    if not m:
        raise HTTPException(status_code=400, detail=f"合约代码格式错误: {option_code}")
    target_code = m.group(1)
    expiry = m.group(2)
    opt_type_code = m.group(3)
    strike_val = int(m.group(4)) / 1000.0
    option_type = "认购" if opt_type_code == "C" else "认沽"
    data = get_iv_kline(target_code, expiry, strike_val, option_type, days)
    return {
        "option_code": option_code,
        "target": target_code,
        "expiry": expiry,
        "strike": strike_val,
        "option_type": option_type,
        "data": data,
        "count": len(data)
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "contracts": state_cache.total_contracts,
        "last_updated": state_cache.last_full_update,
        "poll_interval": POLL_INTERVAL
    }


@app.middleware("http")
async def spa_middleware(request: Request, call_next):
    """SPA middleware: serve static files, then index.html for unmatched GET routes."""
    import pathlib
    dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist"

    if request.method == "GET" and not request.url.path.startswith("/api"):
        if not request.url.path.startswith(".") and dist.exists():
            file_path = dist / request.url.path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                from fastapi.responses import FileResponse
                return FileResponse(str(file_path))

    response = await call_next(request)

    # SPA fallback: if it's a GET and got 404, serve index.html
    if request.method == "GET" and response.status_code == 404:
        idx = dist / "index.html"
        if dist.exists() and idx.exists():
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=idx.read_text(encoding="utf-8"), status_code=200)

    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT)
else:
    # Production: import is module, middleware handles SPA
    pass
