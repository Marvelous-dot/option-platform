"""服务层 — 组合目录 + 报价 + 标的价，产出带状态的 T 型报价。

设计：
- 进程内缓存（TTL 30s），避免高频打爆新浪接口
- 每次请求如果缓存过期就刷新；刷新失败时返回过期缓存并标注 stale
- 所有字段可溯源：source / fetched_at / market_ts / data_status
- 任何数据缺失都是 None + unavailable，不做默认值填充
"""

from __future__ import annotations

import copy
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core.adapters import (
    fetch_contract_catalog,
    fetch_sina_quotes_batch,
    fetch_tencent_spot,
)
from core.contracts import Contract, normalize_contracts, pair_t_quote, t_quote_payload
from core.quotes import (
    normalize_sina_greeks,
    parse_market_ts,
    parse_tencent_spot,
    quote_as_payload,
    ts_freshness,
)

log = logging.getLogger("optionv2.service")

CN = ZoneInfo("Asia/Shanghai")

TARGETS = {
    "510050": {"name": "50ETF(华夏上证50)", "alias": "50ETF"},
    "510300": {"name": "300ETF(华泰柏瑞沪深300)", "alias": "300ETF"},
    "510500": {"name": "500ETF(南方中证500)", "alias": "500ETF"},
    "588000": {"name": "科创50ETF(华夏)", "alias": "科创50ETF"},
    "588080": {"name": "科创板50ETF(易方达)", "alias": "科创板50ETF"},
}
KNOWN_TARGETS = tuple(TARGETS.keys())

CACHE_TTL = 30.0

# K 线落盘缓存：按标的分文件，重启可预热；上游失败时走 stale 降级
KLINE_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "kline"
KLINE_TTL_DAYS = 7.0

# 标的日K 最近收盘缓存：按标的分文件，用于策略情景分析的现价参考；
# 盘中最新价不缓存（实时价走腾讯现货接口，每次 t_quote 都会重新拉取）
LAST_CLOSE_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "lastclose"
LAST_CLOSE_TTL_DAYS = 365.0


class OptionService:
    # K 线落盘目录（实例级，便于测试覆盖；默认 backend/cache/kline/）
    kline_cache_dir = KLINE_CACHE_DIR
    lastclose_cache_dir = LAST_CLOSE_CACHE_DIR

    def __init__(self) -> None:
        self._catalog_cache: list[Contract] | None = None
        self._catalog_ts: float = 0.0        # monotonic，仅用于 TTL
        self._catalog_loaded_at: str | None = None  # 自然时钟，用于展示
        self._catalog_error: str | None = None
        self._tquote_cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self._lock = threading.Lock()

    # ---------- 合约目录 ----------

    def _catalog(self, refresh: bool = False) -> list[Contract]:
        with self._lock:
            now = time.monotonic()
            if (
                not refresh
                and self._catalog_cache is not None
                and now - self._catalog_ts < 300.0
            ):
                return self._catalog_cache
            rows = fetch_contract_catalog()
            contracts = normalize_contracts(rows, KNOWN_TARGETS)
            if not contracts:
                raise RuntimeError("合约目录归一化后为空")
            self._catalog_cache = contracts
            self._catalog_ts = now
            self._catalog_loaded_at = datetime.now(CN).isoformat(timespec="seconds")
            self._catalog_error = None
            return contracts

    def catalog_status(self) -> dict:
        return {
            "loaded": self._catalog_cache is not None,
            "loaded_at": self._catalog_loaded_at,
            "error": self._catalog_error,
        }

    def expiries(self, target_code: str) -> list[str]:
        contracts = self._catalog()
        return sorted({c.expiry for c in contracts if c.target_code == target_code})

    def targets(self) -> list[dict]:
        """标的状态含目录健康度，前端可如实展示。"""
        try:
            contracts = self._catalog()
            error = None
        except Exception as e:
            contracts, error = (self._catalog_cache or []), str(e)
        by_target: dict[str, int] = {t: 0 for t in TARGETS}
        for c in contracts:
            by_target[c.target_code] = by_target.get(c.target_code, 0) + 1
        return [
            {
                "target": code,
                "name": info["name"],
                "contract_count": by_target.get(code, 0),
                "catalog_ok": error is None,
                "catalog_error": error,
            }
            for code, info in TARGETS.items()
        ]

    def contract_detail(self, option_code: str) -> dict:
        """按挂牌代码查询，复用同到期日的已校验报价快照。"""
        from dataclasses import asdict
        from core.quotes import Quote

        contract = next((c for c in self._catalog() if c.option_code == option_code), None)
        if contract is None:
            raise KeyError(option_code)
        snapshot = self.t_quote(contract.target_code, contract.expiry)
        quote = quote_as_payload(Quote(
            contract_id=contract.contract_id, option_code=contract.option_code,
            name=contract.name, fetched_at=snapshot.get("fetched_at"),
        ))
        for row in snapshot.get("rows", []):
            for side in ("call", "put"):
                leg = row.get(side)
                if (leg and leg.get("contract_id") == contract.contract_id
                        and leg.get("option_code") == contract.option_code):
                    quote = dict(leg)
        return {
            "contract": asdict(contract), "catalog_source": "sse",
            "quote": quote, "spot": snapshot.get("spot"),
            "status_detail": snapshot.get("status_detail"),
        }

    def all_quotes(self, target_code: str, *, expiry: str | None = None,
                   option_type: str | None = None, search: str = "",
                   moneyness: str = "all", sort: str = "option_code",
                   order: str = "asc", limit: int = 0, offset: int = 0) -> dict:
        """按挂牌目录展开各到期日快照；缺腿保留身份，缺失值不补零。

        limit=0 表示不限制（向后兼容）；offset 必须非负。分页在
        筛选 + 排序完成后作用于最终行序列，total 反映筛选后全量。
        """
        from dataclasses import asdict
        from core.quotes import Quote

        if isinstance(limit, bool) or isinstance(offset, bool):
            raise ValueError("limit/offset 必须是整数")
        try:
            limit = int(limit); offset = int(offset)
        except (TypeError, ValueError):
            raise ValueError("limit/offset 必须是整数")
        if limit < 0 or offset < 0:
            raise ValueError("limit/offset 不能为负")
        sortable = {"option_code", "name", "expiry", "strike", "last_price",
                    "change_pct", "iv", "delta", "gamma", "theta", "vega", "volume"}
        if target_code not in TARGETS:
            raise ValueError("未知标的")
        if (sort not in sortable or order not in {"asc", "desc"}
                or option_type not in {None, "", "call", "put"}
                or moneyness not in {"all", "atm", "otm"}):
            raise ValueError("不支持的筛选或排序参数")
        contracts = [c for c in self._catalog() if c.target_code == target_code]
        expiries = sorted({c.expiry for c in contracts})
        pool = [c for c in contracts if not expiry or c.expiry == expiry]
        snapshots = {e: self.t_quote(target_code, e) for e in sorted({c.expiry for c in pool})}
        rows = []
        missing_spot = False
        for e, snapshot in snapshots.items():
            legs = {}
            for pair in snapshot.get("rows", []):
                for side in ("call", "put"):
                    leg = pair.get(side)
                    if leg:
                        legs[(leg.get("contract_id"), leg.get("option_code"))] = leg
            group = [c for c in pool if c.expiry == e]
            spot = snapshot.get("spot")
            price = (spot or {}).get("price")
            usable_spot = isinstance(price, (int, float)) and price > 0
            if moneyness != "all" and not usable_spot:
                missing_spot = True
            nearest = min((c.strike for c in group), key=lambda k: (abs(k - price), k)) if usable_spot else None
            for c in group:
                quote = quote_as_payload(Quote(contract_id=c.contract_id, option_code=c.option_code,
                                               name=c.name, fetched_at=snapshot.get("fetched_at")))
                quote.update(legs.get((c.contract_id, c.option_code), {}))
                row = {**quote, **asdict(c), "spot": spot, "catalog_source": "sse"}
                if option_type and c.option_type != option_type:
                    continue
                if search.strip().casefold() not in f"{c.option_code} {c.contract_id} {c.name}".casefold():
                    continue
                if usable_spot and moneyness == "atm" and c.strike != nearest:
                    continue
                if usable_spot and moneyness == "otm":
                    if not (c.strike > price if c.option_type == "call" else c.strike < price):
                        continue
                rows.append(row)
        present = sorted((r for r in rows if r.get(sort) is not None),
                         key=lambda r: r[sort], reverse=order == "desc")
        rows = present + [r for r in rows if r.get(sort) is None]
        total = len(rows)
        if limit > 0:
            rows = rows[offset:offset + limit]
        ok_n = sum(r["data_status"] == "ok" for r in rows)
        stale_n = sum(r["data_status"] == "stale" for r in rows)
        status = ("ok" if rows and ok_n == len(rows) else "partial" if ok_n
                  else "stale" if stale_n else "unavailable")
        return {
            "target_code": target_code, "expiries": expiries,
            "contract_count": len(pool), "filtered_count": total, "available_count": ok_n,
            "limit": limit, "offset": offset, "total": total,
            "data_status": status, "rows": rows,
            "status_detail": f"筛选结果 {total} 个；本页返回 {len(rows)} 个；报价可用 {ok_n} 个；过期 {stale_n} 个"
                + ("；标的价格缺失，对应到期日未应用虚实值筛选" if missing_spot else ""),
        }

    # ---------- 标的日K线 ----------

    KLINE_LIMITS = (5, 750)

    def kline(self, target_code: str, days: int = 120, *, persist: bool = True) -> dict:
        """标的 ETF 前复权日K。仅真实行情接口，失败如实标 unavailable。

        落盘缓存：按标的分文件存 KLINE_CACHE_DIR，重启可预热；
        上游失败或数据过期(>KLINE_TTL_DAYS)时降级为 stale（不冒充当日数据）。
        """
        from core.adapters import fetch_tencent_kline

        if target_code not in TARGETS:
            raise ValueError("未知标的")
        if isinstance(days, (bool, float)):
            raise ValueError("days 必须是整数")
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise ValueError("days 必须是整数")
        if not self.KLINE_LIMITS[0] <= days <= self.KLINE_LIMITS[1]:
            raise ValueError(f"days 取值范围 {self.KLINE_LIMITS[0]}-{self.KLINE_LIMITS[1]}")
        fetched_at = datetime.now(CN).isoformat(timespec="seconds")

        cached = self._load_kline_cache(target_code)
        bars = fetch_tencent_kline(target_code, days)
        if not bars:
            if cached:
                cached["data_status"] = "stale"
                cached["status_detail"] = (
                    f"上游不可用，展示落盘缓存快照 {cached.get('cached_at', '未知')}；"
                    "获取时间不代表行情时间"
                )
                return cached
            return {
                "target_code": target_code, "target_name": TARGETS[target_code]["name"],
                "days": days, "bars": [], "count": 0,
                "source": "tencent", "fetched_at": fetched_at,
                "data_status": "unavailable",
                "status_detail": "日K数据不可用（数据源失败或返回空）",
            }

        bars = sorted(bars, key=lambda b: b["date"])
        if cached:
            # 新数据按日期覆盖旧 bar，保留更长历史
            merged = {b["date"]: b for b in cached.get("bars", []) + bars}
            bars = [merged[d] for d in sorted(merged)]
        bars = bars[-days:]
        last = bars[-1]
        payload = {
            "target_code": target_code, "target_name": TARGETS[target_code]["name"],
            "days": days, "bars": bars, "count": len(bars),
            "first_date": bars[0]["date"], "last_date": last["date"],
            "last_close": last["close"], "source": "tencent",
            "adjust": "qfq(前复权)", "volume_unit": "source_raw",
            "fetched_at": fetched_at, "data_status": "ok",
            "status_detail": (
                f"{len(bars)} 根日K，最新 {last['date']}；盘中末根可能尚未收盘，"
                "获取时间不代表行情时间"
            ),
        }
        self._save_kline_cache(target_code, payload) if persist else None
        return payload

    def _load_kline_cache(self, target_code: str) -> dict | None:
        """重启预热：读落盘缓存，缺失/损坏/过期(>KLINE_TTL_DAYS)返回 None。"""
        f = self.kline_cache_dir / f"{target_code}.json"
        try:
            if not f.is_file():
                return None
            data = json.loads(f.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(data.get("cached_at", ""))
            if datetime.now(CN) - cached_at > timedelta(days=KLINE_TTL_DAYS):
                return None
            if not data.get("bars"):
                return None
            return data
        except Exception:
            log.warning("kline cache %s unreadable, ignore", target_code)
            return None

    def _save_kline_cache(self, target_code: str, payload: dict) -> None:
        """成功取数后落盘；写失败只记日志，不影响当次返回。"""
        try:
            self.kline_cache_dir.mkdir(parents=True, exist_ok=True)
            snapshot = {k: v for k, v in payload.items() if k != "status_detail"}
            snapshot["cached_at"] = datetime.now(CN).isoformat(timespec="seconds")
            f = self.kline_cache_dir / f"{target_code}.json"
            f.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            log.warning("kline cache save %s failed", target_code)


    # ---------- T 型报价 ----------

    def t_quote(self, target_code: str, expiry: str | None) -> dict:
        """主链路：目录 → 标的价 → 并发行情 → 配对。任何一环失败如实标注。"""
        cache_key = (target_code, expiry or "all")
        with self._lock:
            cached = self._tquote_cache.get(cache_key)
            now = time.monotonic()

            if cached and now - cached[0] < CACHE_TTL:
                return cached[1]

        try:
            payload = self._build_t_quote(target_code, expiry, previous=cached[1] if cached else None)
        except Exception as e:
            # 刷新失败：有缓存 → 深拷贝标 stale 返回，缓存保留原快照与原时间戳；
            # 无缓存 → 完全不可用
            if cached:
                payload = copy.deepcopy(cached[1])
                payload["data_status"] = "stale"
                payload["freshness"] = "stale"
                payload["status_detail"] = f"刷新失败，展示过期快照: {e}"
                for row in payload.get("rows", []):
                    for leg in ("call", "put"):
                        if row.get(leg) and row[leg].get("data_status") == "ok":
                            row[leg]["data_status"] = "stale"
                            row[leg]["freshness"] = "stale"
                return payload
            log.exception("t_quote build failed for %s", target_code)
            return {
                "target_code": target_code,
                "target_name": TARGETS.get(target_code, {}).get("name", target_code),
                "spot": None,
                "as_of": None,
                "rows": [],
                "data_status": "unavailable",
                "status_detail": f"行情不可用: {e}",
            }

        with self._lock:
            self._tquote_cache[cache_key] = (now, payload)
        return payload

    def _build_t_quote(
        self,
        target_code: str,
        expiry: str | None,
        previous: dict | None = None,
    ) -> dict:
        target_info = TARGETS.get(target_code)
        if not target_info:
            raise ValueError(f"未知标的 {target_code}")

        # 1) 合约目录
        contracts = self._catalog()
        target_contracts = [c for c in contracts if c.target_code == target_code]
        expiries = sorted({c.expiry for c in target_contracts})
        if not expiry:
            expiry = expiries[0] if expiries else None
        pool = [c for c in target_contracts if c.expiry == expiry]
        if not pool:
            raise RuntimeError(f"{target_code} 无到期日 {expiry or '(无可用到期日)'} 的挂牌合约")

        # 2) 标的实时价（失败 → spot=None，前端显示不可用）
        spot = None
        raw_spot = fetch_tencent_spot(target_code)
        if raw_spot:
            spot = parse_tencent_spot(raw_spot)

        # 3) 并发拉全部腿的实时行情
        ids = [c.contract_id for c in pool]
        ok_kvs, failed_ids = fetch_sina_quotes_batch(ids)
        fetched_at = datetime.now(CN).isoformat(timespec="seconds")
        prev_legs: dict[str, dict] = {}
        if previous:
            for row in previous.get("rows", []):
                for leg in ("call", "put"):
                    q = row.get(leg)
                    if q and q.get("data_status") == "ok":
                        prev_legs[q["contract_id"]] = q
        quotes: dict[str, dict] = {}
        latest_market_ts: str | None = None
        for c in pool:
            kv = ok_kvs.get(c.contract_id)
            q = normalize_sina_greeks(c.contract_id, kv or {}, fetched_at, None)
            if not q.name:
                q.name = c.name
            # 身份校验：数据源必须回传与挂牌合约一致的交易代码（fail-closed），
            # 缺失或错配都视为本次无有效观测
            identity_ok = bool(kv) and q.option_code == c.option_code
            if not identity_ok and c.contract_id in prev_legs:
                # 本次没取到（或身份错配）但上一份快照有 → 保留旧观测，如实标 stale
                old = dict(prev_legs[c.contract_id])
                old["data_status"] = "stale"
                old["freshness"] = "stale"
                quotes[c.contract_id] = old
                continue
            quotes[c.contract_id] = quote_as_payload(q, expected_option_code=c.option_code)
            if q.market_ts:
                qdt = parse_market_ts(q.market_ts)
                if qdt and (
                    latest_market_ts is None or qdt > parse_market_ts(latest_market_ts)
                ):
                    latest_market_ts = q.market_ts

        ok_n = sum(1 for c in pool if quotes[c.contract_id]["data_status"] == "ok")
        stale_n = sum(1 for c in pool if quotes[c.contract_id]["data_status"] == "stale")
        n_fresh = sum(
            1 for q in quotes.values() if q["data_status"] == "ok" and q["freshness"] == "fresh"
        )
        failed_n = len(failed_ids)
        rows = pair_t_quote(pool, quotes)
        as_of = latest_market_ts

        if ok_n == 0 and stale_n:
            # 本次一个新数据都没拿到，整页来自旧快照 → 如实沿用旧观测时间
            data_status = "stale"
            freshness = "stale"
            fetched_at = (previous or {}).get("fetched_at") or fetched_at
        elif ok_n == 0:
            data_status = "unavailable"
            freshness = "unknown"
        elif ok_n < len(pool) or failed_n:
            # 只有部分合约拿到有效行情 → partial，不冒充完整可用
            data_status = "partial"
            freshness = ts_freshness(latest_market_ts)
        else:
            data_status = "ok"
            freshness = ts_freshness(latest_market_ts)

        return t_quote_payload(target_code, target_info["name"], spot, rows, as_of) | {
            "expiry": expiry,
            "expiries": expiries,
            "fetched_at": fetched_at,
            "freshness": freshness,
            "data_status": data_status,
            "available_count": ok_n,
            "contract_count": len(pool),
            "status_detail": (
                f"{n_fresh}/{len(pool)} 合约为当日数据"
                + (f"；{len(failed_ids)} 个取数失败" if failed_ids else "")
            ),
        }

    # ---------- 策略场景：真实合约 + 行情 + 标的参考价 ----------

    def strategy_market(
        self,
        target_code: str,
        expiry: str | None = None,
        option_type: str | None = None,
        search: str = "",
        limit: int = 0,
    ) -> dict:
        """策略页左侧选腿用：真实挂牌合约 + 真实报价 + 标的参考价。

        - contracts: 同标的（可选同到期日/方向/搜索词）的挂牌合约展开行，
          每行含合约身份 + 报价快照 + 快照的 spot，语义与 all_quotes 一致。
        - spot: 最新一次 t_quote 快照的标的价（实时腾讯现货；缺失为 None）。
        - reference_spot: 情景分析（盈亏曲线横轴基准）用的参考价，优先
          最新 t_quote spot，缺失时用 K 线落盘缓存的最近收盘（stale，注明时间）；
          两者都不可用才返回 None（曲线可算，只是横轴基准取 0 附近，由前端提示）。
        """
        if target_code not in TARGETS:
            raise ValueError("未知标的")
        if isinstance(limit, bool) or isinstance(limit, float):
            raise ValueError("limit 必须是整数")
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise ValueError("limit 必须是整数")
        if limit < 0:
            raise ValueError("limit 不能为负")

        contract_rows = self.all_quotes(
            target_code,
            expiry=expiry,
            option_type=option_type,
            search=search,
            limit=limit,
            sort="option_code",
            order="asc",
        )

        # 最新 t_quote 快照的 spot（实时价，30s TTL；失败如实返回）
        snapshot = self.t_quote(target_code, expiry)
        spot = snapshot.get("spot")

        # 情景参考 spot：实时 spot 缺失时回落到 K 线缓存最近收盘（标 stale）
        reference_spot = spot
        reference_spot_source = "tencent" if spot and isinstance(spot.get("price"), (int, float)) else None
        if reference_spot_source is None:
            cached = self._load_lastclose_cache(target_code)
            if cached:
                reference_spot = {
                    "price": cached["price"],
                    "source": "kline_cache",
                    "market_time": cached.get("cached_at"),
                    "stale": True,
                }
                reference_spot_source = "kline_cache"
        # 顺带把最新 K 线收盘写回缓存（不依赖策略页是否命中 t_quote）
        try:
            payload = self.kline(target_code, days=5, persist=False)
            if payload.get("data_status") == "ok" and payload.get("last_close"):
                self._save_lastclose_cache(target_code, payload["last_close"], payload["last_date"])
        except Exception:
            pass  # 缓存写失败只影响下次参考 spot，不影响本次返回

        return {
            "target_code": target_code,
            "target_name": TARGETS[target_code]["name"],
            "expiry": expiry,
            "expiries": contract_rows["expiries"],
            "spot": spot,
            "reference_spot": reference_spot,
            "reference_spot_source": reference_spot_source,
            "snapshots": contract_rows,
            "fetched_at": snapshot.get("fetched_at"),
            "data_status": contract_rows["data_status"],
            "status_detail": contract_rows["status_detail"],
        }

    def _load_lastclose_cache(self, target_code: str) -> dict | None:
        f = self.lastclose_cache_dir / f"{target_code}.json"
        try:
            if not f.is_file():
                return None
            data = json.loads(f.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(data.get("cached_at", ""))
            if datetime.now(CN) - cached_at > timedelta(days=LAST_CLOSE_TTL_DAYS):
                return None
            if not isinstance(data.get("price"), (int, float)):
                return None
            return data
        except Exception:
            log.warning("lastclose cache %s unreadable, ignore", target_code)
            return None

    def _save_lastclose_cache(self, target_code: str, price: float, date: str) -> None:
        try:
            self.lastclose_cache_dir.mkdir(parents=True, exist_ok=True)
            f = self.lastclose_cache_dir / f"{target_code}.json"
            f.write_text(
                json.dumps(
                    {"price": price, "date": date,
                     "cached_at": datetime.now(CN).isoformat(timespec="seconds")},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            log.warning("lastclose cache save %s failed", target_code)


service = OptionService()
