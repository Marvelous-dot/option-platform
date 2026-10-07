"""FastAPI 入口 — v2 后端。端口 8001，不与旧服务(8000)冲突。"""

from __future__ import annotations

import logging
import pathlib
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from core.service import TARGETS, service
import core.log as log

# 使用 P2 结构化日志替代基本配置；级别/目标可由环境变量覆盖
log.setup_logging()
logger = log.get_logger("option-v2")

app = FastAPI(title="海疆期权 v2", version="2.0.0")

DIST = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "dist"
START_TIME = time.monotonic()


app.mount("/assets", StaticFiles(directory=DIST / "assets", check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
@app.get("/tquote", include_in_schema=False)
@app.get("/quotes", include_in_schema=False)
@app.get("/kline", include_in_schema=False)
@app.get("/volatility", include_in_schema=False)
@app.get("/screener", include_in_schema=False)
@app.get("/strategy", include_in_schema=False)
@app.get("/contract/{option_code}", include_in_schema=False)
def spa_page():
    """仅已知前端路由返回入口；静态资源与未知路径不做 HTML 回退。"""
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="前端尚未构建")
    return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-cache"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "up",
        "version": "2.0.0",
        "uptime_s": int(time.monotonic() - START_TIME),
        "data_store": "memory+kline:disk",  # 行情内存快照；日K落盘缓存(cache/kline/)，重启可预热
    }


def _probe_targets():
    try:
        t = service.targets()
        ok = isinstance(t, list) and len(t) > 0
        return {"status": "ok" if ok else "degraded", "count": len(t) if ok else 0}
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


def _probe_contracts():
    code = next(iter(TARGETS))
    try:
        exp = service.expiries(code)
        ok = isinstance(exp, list) and len(exp) > 0
        return {"status": "ok" if ok else "degraded", "target": code, "expiries": len(exp) if ok else 0}
    except Exception as e:
        return {"status": "unavailable", "target": code, "error": str(e)}


@app.get("/api/diag")
def api_diag():
    """P2 运维：数据源可达性诊断。恒 200，下游失败标记为 degraded/unavailable。"""
    services = {"targets": _probe_targets(), "contracts": _probe_contracts()}
    statuses = [s["status"] for s in services.values()]
    if "unavailable" in statuses:
        overall = "unavailable" if all(s == "unavailable" for s in statuses) else "degraded"
    else:
        overall = "degraded" if "degraded" in statuses else "ok"
    return {"overall": overall, "services": services}


@app.get("/api/targets")
def api_targets():
    return {"targets": service.targets()}


@app.get("/api/expiries/{target_code}")
def api_expiries(target_code: str):
    if target_code not in TARGETS:
        raise HTTPException(status_code=404, detail=f"未知标的 {target_code}")
    try:
        return {"expiries": service.expiries(target_code)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"合约目录不可用: {e}")


@app.get("/api/tquote/{target_code}")
def api_tquote(target_code: str, expiry: str | None = None):
    if target_code not in TARGETS:
        raise HTTPException(status_code=404, detail=f"未知标的 {target_code}")
    return service.t_quote(target_code, expiry)


@app.get("/api/quotes/{target_code}")
def api_quotes(target_code: str, expiry: str | None = None,
               option_type: str | None = None, search: str = "",
               moneyness: str = "all", sort: str = "option_code", order: str = "asc",
               limit: int = 0, offset: int = 0):
    if target_code not in TARGETS:
        raise HTTPException(status_code=404, detail="未知标的")
    try:
        return service.all_quotes(target_code, expiry=expiry, option_type=option_type,
                                  search=search, moneyness=moneyness, sort=sort, order=order,
                                  limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logging.getLogger(__name__).exception("all quotes unavailable")
        raise HTTPException(status_code=503, detail="合约行情暂不可用")


@app.get("/api/kline/{target_code}")
def api_kline(target_code: str, days: int = 120, period: str = "day"):
    """K线。period=day 为腾讯前复权日K（days=交易日数，落盘缓存）；
    period=5m/15m/30m/60m 为新浪分钟K（days 复用为根数 datalen，内存缓存 60s）。"""
    if target_code not in TARGETS:
        raise HTTPException(status_code=404, detail="未知标的")
    try:
        if period in ("", "day"):
            return service.kline(target_code, days=days)
        return service.minkline(target_code, period, datalen=days)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logging.getLogger(__name__).exception("kline unavailable")
        raise HTTPException(status_code=503, detail="K线数据暂不可用")


@app.get("/api/contract/{option_code}")
def api_contract(option_code: str):
    try:
        return service.contract_detail(option_code)
    except KeyError:
        raise HTTPException(status_code=404, detail="未找到挂牌合约")
    except Exception:
        logging.getLogger(__name__).exception("contract detail unavailable")
        raise HTTPException(status_code=503, detail="合约数据暂不可用")


@app.get("/api/strategy/market/{target_code}")
def api_strategy_market(target_code: str, expiry: str | None = None,
                        option_type: str | None = None, search: str = "",
                        limit: int = 0):
    """策略页左侧选腿：真实挂牌合约 + 真实报价 + 标的参考价（实时 spot，
    缺失时回落到 K 线落盘缓存最近收盘并明确标 stale）。"""
    if target_code not in TARGETS:
        raise HTTPException(status_code=404, detail="未知标的")
    try:
        return service.strategy_market(
            target_code, expiry=expiry, option_type=option_type,
            search=search, limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logging.getLogger(__name__).exception("strategy market unavailable")
        raise HTTPException(status_code=503, detail="策略市场数据暂不可用")
