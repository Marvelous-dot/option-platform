"""数据适配层 — 只做网络获取和解析，不做任何默认值填充。

三个源（2026-09-17 实测可用）：
  1. akshare option_current_day_sse()   — 上交所当日挂牌合约目录
  2. akshare option_sse_greeks_sina(id) — 新浪单合约实时行情 + 市场隐含波动率 + Greeks
  3. 腾讯 qt.gtimg.cn                   — 标的 ETF 实时价
失败向上抛错或返回 None，由服务层决定状态，绝不静默降级为模拟数据。
"""

from __future__ import annotations

import logging
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger("optionv2.adapters")

TENCENT_URL = "https://qt.gtimg.cn/q={code}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_contract_catalog() -> list[dict]:
    """上交所当日全部挂牌合约。抛错 = 目录不可用，由调用方处理。"""
    import akshare as ak
    df = ak.option_current_day_sse()
    if df is None or df.empty:
        raise RuntimeError("option_current_day_sse 返回空")
    return df.to_dict("records")


def fetch_sina_quote(contract_id: str) -> dict | None:
    """新浪单合约实时行情。返回 (字段,值) dict；网络失败抛错，空数据返回 None。"""
    import akshare as ak
    g = ak.option_sse_greeks_sina(contract_id)
    if g is None or getattr(g, "empty", True):
        return None
    return dict(zip(g["字段"], g["值"]))


def fetch_sina_quotes_batch(
    contract_ids: list[str],
    max_workers: int = 8,
) -> tuple[dict[str, dict], list[str]]:
    """并发拉一批。返回 (成功的 {id: kv}, 失败的 [id])。"""
    ok: dict[str, dict] = {}
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fetch_sina_quote, cid): cid for cid in contract_ids}
        for fut in as_completed(futs):
            cid = futs[fut]
            try:
                kv = fut.result()
            except Exception as e:
                log.warning("sina quote %s failed: %s", cid, e)
                failed.append(cid)
                continue
            if kv:
                ok[cid] = kv
            else:
                failed.append(cid)  # 新浪对无行情合约返回空
    return ok, failed


KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh{code},day,,,{days},qfq"


def fetch_tencent_kline(target_code: str, days: int) -> list[dict] | None:
    """腾讯前复权日K。返回 [date, open, close, high, low, volume] 拆解后的 dict 列表；
    网络失败/结构异常返回 None（不可用），不填默认值。"""
    url = KLINE_URL.format(code=target_code, days=max(1, int(days)))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        import json
        data = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
    except Exception as e:
        log.warning("tencent kline %s failed: %s", target_code, e)
        return None
    from datetime import date
    from math import isfinite
    try:
        if not isinstance(data, dict) or str(data.get("code", 0)) != "0":
            return None
        node = data["data"][f"sh{target_code}"]
        # 不能把未复权 day 字段默认为前复权。
        rows = node.get("qfqday")
        if not isinstance(rows, list) or not rows:
            return None
        bars, dates = [], set()
        for r in rows:
            if not isinstance(r, list) or len(r) < 5:
                return None
            day = date.fromisoformat(r[0]).isoformat()
            if day != r[0] or day in dates:
                return None
            dates.add(day)
            o, c, h, l = [float(v) for v in r[1:5]]
            if not all(isfinite(v) and v > 0 for v in (o, c, h, l)):
                return None
            if not l <= min(o, c) <= max(o, c) <= h:
                return None
            volume = float(r[5]) if len(r) > 5 and r[5] not in (None, '') else None
            if volume is not None and (not isfinite(volume) or volume < 0):
                return None
            bars.append(dict(date=day, open=o, close=c, high=h, low=l, volume=volume))
        return bars
    except (TypeError, ValueError, KeyError, IndexError, AttributeError):
        log.warning("tencent kline %s invalid payload", target_code)
        return None


def fetch_tencent_spot(target_code: str) -> dict | None:
    """标的实时价。失败返回 None（不可用），不填默认值。"""
    url = TENCENT_URL.format(code=f"sh{target_code}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=10).read().decode("gbk")
    except Exception as e:
        log.warning("tencent spot %s failed: %s", target_code, e)
        return None
    return raw
