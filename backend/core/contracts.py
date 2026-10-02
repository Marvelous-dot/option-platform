"""合约目录与 T 型报价配对 — 纯函数，可独立测试。

数据来源：akshare option_current_day_sse()（上交所当日挂牌合约目录）。
原始字段（中文列名）：合约编码/合约交易代码/合约简称/标的券名称及代码/类型/行权价/到期日/合约单位
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Contract:
    option_code: str      # 合约交易代码 e.g. 510050C2609M02650
    contract_id: str      # 合约编码（新浪行情用）e.g. 10011255
    name: str             # 合约简称 e.g. 50ETF购9月2650
    target_code: str      # 标的 e.g. 510050
    option_type: str      # call / put
    strike: float
    expiry: str           # YYYYMMDD
    contract_unit: int


def parse_underlying(underlying_str: str, known_targets: tuple[str, ...]) -> str | None:
    """从 '50ETF(510050)' 提取 510050；仅接受白名单标的。"""
    m = re.search(r"\((\d{6})\)", underlying_str or "")
    if not m:
        return None
    code = m.group(1)
    return code if code in known_targets else None


def normalize_contracts(rows: list[dict], known_targets: tuple[str, ...]) -> list[Contract]:
    """把上交所合约目录原始行转成 Contract 列表；非法行直接丢弃（宁缺毋假）。"""
    out = []
    for row in rows:
        try:
            target = parse_underlying(str(row.get("标的券名称及代码", "")), known_targets)
            if not target:
                continue
            opt_type_raw = str(row.get("类型", "")).strip()
            option_type = {"认购": "call", "认沽": "put"}.get(opt_type_raw)
            if not option_type:
                continue
            strike = float(row.get("行权价"))
            expiry = re.sub(r"\D", "", str(row.get("到期日", "")))
            if len(expiry) != 8:
                continue
            out.append(Contract(
                option_code=str(row.get("合约交易代码", "")).strip(),
                contract_id=str(row.get("合约编码", "")).strip(),
                name=str(row.get("合约简称", "")).strip(),
                target_code=target,
                option_type=option_type,
                strike=strike,
                expiry=expiry,
                contract_unit=int(float(row.get("合约单位", 10000))),
            ))
        except (TypeError, ValueError, KeyError):
            continue
    return out


@dataclass(frozen=True)
class TQuoteRow:
    strike: float
    key: str            # 到期日|系列|行权价，前端 :key 用
    call: dict | None   # {"option_code","contract_id","name","last_price","delta",...,"data_status"}
    put: dict | None


def _series(option_code: str) -> str:
    """从合约交易代码提取系列：六位标的 + C/P + 四位年月 + 系列 + 五位价格码。"""
    m = re.fullmatch(r"\d{6}[CP]\d{4}([A-Z])\d{5}", option_code or "")
    return m.group(1) if m else "?"


def pair_t_quote(
    contracts: list[Contract],
    quotes: dict[str, dict],
) -> list[TQuoteRow]:
    """按行权价配对认购/认沽。

    contracts: 同一标的同一到期日的合约列表（混入即抛错，宁可不展示也不配错对）
    quotes: contract_id -> 报价 dict（可能缺某些合约）
    报价缺失的腿为 None，前端显示"不可用"，不用模拟数据补。
    不同调整系列（合约单位不同）同一行权价各占一行，不互相覆盖。
    """
    if contracts:
        targets = {c.target_code for c in contracts}
        if len(targets) > 1:
            raise ValueError(f"pair_t_quote 混入多个标的: {sorted(targets)}")
        expiries = {c.expiry for c in contracts}
        if len(expiries) > 1:
            raise ValueError(f"pair_t_quote 混入多个到期日: {sorted(expiries)}")

    by_key: dict[tuple[float, str], dict[str, Contract]] = {}
    for c in contracts:
        key = (c.strike, _series(c.option_code))
        side = by_key.setdefault(key, {})
        if c.option_type in side:
            raise ValueError(
                f"同边重复合约: {key} {c.option_type} "
                f"{side[c.option_type].contract_id} 与 {c.contract_id}"
            )
        side[c.option_type] = c

    rows = []
    for (strike, series) in sorted(by_key):
        legs = by_key[(strike, series)]
        call = legs.get("call")
        put = legs.get("put")
        rows.append(TQuoteRow(
            strike=strike,
            key=f"{contracts[0].expiry}|{series}|{strike:g}" if contracts else f"{series}|{strike:g}",
            call=quotes.get(call.contract_id) if call else None,
            put=quotes.get(put.contract_id) if put else None,
        ))
    return rows


def t_quote_payload(
    target_code: str,
    target_name: str,
    spot: dict | None,
    rows: list[TQuoteRow],
    as_of: str | None,
) -> dict:
    """组装 API 响应。spot/as_of 缺失时如实标注，不填默认值。"""
    return {
        "target_code": target_code,
        "target_name": target_name,
        "spot": spot,          # None = 标的价格不可用
        "as_of": as_of,        # None = 行情时间未知
        "rows": [
            {
                "strike": r.strike,
                "call": r.call,
                "put": r.put,
            }
            for r in rows
        ],
    }
