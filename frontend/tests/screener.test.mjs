// screener.mjs 单元自测：合成数据 + 边界用例（口径：平值区扫描 / LOO / 中位数校正）
import { buildSignals, quadFit, SIGNAL_TYPES, daysToExpiry, bsVegaPerPp, ivEnvironment, filterSignals } from '../src/utils/screener.mjs'

let pass = 0, fail = 0
function ok(cond, name) {
  if (cond) { pass++; console.log(`  ok - ${name}`) }
  else { fail++; console.error(`  FAIL - ${name}`) }
}

// ---- quadFit 基础 ----
{
  const pts = Array.from({ length: 11 }, (_, i) => {
    const m = -0.2 + i * 0.04
    return { m, y: 20 + 300 * m * m + 10 * m }
  })
  const c = quadFit(pts)
  ok(c && Math.abs(c[0] - 300) < 1e-6 && Math.abs(c[1] - 10) < 1e-6 && Math.abs(c[2] - 20) < 1e-6, `quadFit 精确恢复系数 [a,b,c] ${c}`)
  ok(quadFit([]) === null, 'quadFit 空输入 → null')
  ok(quadFit([{ m: 0, y: 1 }, { m: 0.1, y: 2 }]) === null, 'quadFit 点不足 → null')
}

// ---- 合成场景：1 个标的，2 个到期日，行权价全部落在 |m|≤10% 平值区 ----
// expA 标准微笑 iv=20+300m²，K2.7 购埋 +5pp 尖点（LOO 检出）
// expB 整体高 2pp（contango 常态），K2.5 沽埋 +6pp（C-P 价差异常）
const S = 2.5
function row(code, expiry, type, strike, iv, extra = {}) {
  return {
    option_code: code, expiry, option_type: type, strike, iv, data_status: 'ok',
    last_price: extra.last ?? null, volume: extra.volume ?? null,
    theory_price: extra.theory ?? null, delta: extra.delta ?? null,
    spot: { price: S, data_status: 'ok' },
  }
}
const strikes = [2.3, 2.35, 2.4, 2.45, 2.5, 2.55, 2.6, 2.65, 2.7]
const rows = []
const expA = '20261125', expB = '20261223'
for (const K of strikes) {
  const m = (K - S) / S
  const base = 20 + 300 * m * m
  rows.push(row(`A${K}C`, expA, 'call', K, K === 2.7 ? base + 5 : base))
  rows.push(row(`A${K}P`, expA, 'put', K, base))
}
for (const K of strikes) {
  const m = (K - S) / S
  const base = 22 + 300 * m * m
  rows.push(row(`B${K}C`, expB, 'call', K, base))
  rows.push(row(`B${K}P`, expB, 'put', K, K === 2.5 ? base + 6 : base))
}
// ④ 理论价：6 条候选（5 条贴曲线的正常行 dev≈0 + T1 dev +60%），需 ≥5 条才启用中位数校正
// T2 深虚彩票：delta 0.01 + 权利金 <0.0050，双重过滤必须排除
for (const [i, K] of [2.465, 2.475, 2.485, 2.515, 2.525].entries()) {
  const m = (K - S) / S
  rows.push(row(`N${i}`, expA, 'call', K, 20 + 300 * m * m, { last: 0.05, theory: 0.05, volume: 900, delta: 0.5 }))
}
{
  const m = (2.55 - S) / S
  rows.push(row('T1', expA, 'call', 2.55, 20 + 300 * m * m, { last: 0.08, theory: 0.05, volume: 900, delta: 0.5 }))
}
rows.push(row('T2', expA, 'call', 2.95, 30, { last: 0.0001, theory: 0.00002, volume: 900, delta: 0.01 }))

// 固定"今天"= 2026-10-01：expA(20261125) 距 55 天、expB(20261223) 距 83 天，均通过 7 天过滤
const NOW = new Date('2026-10-01T04:00:00Z')
const r = buildSignals([{ code: '510050', name: '50ETF', spot: S, rows }], { now: NOW })

ok(r.summary.contracts === rows.length, `summary.contracts=${r.summary.contracts}（应为 ${rows.length}）`)
ok(r.summary.ivRows === rows.length, `ivRows=${r.summary.ivRows} 全部有效`)

const smile = r.signals.filter(s => s.type === 'smile')
const smile27c = smile.find(s => s.strike === 2.7 && s.option_type === 'call')
ok(!!smile27c && smile27c.metric >= 2, `①微笑(LOO)：K2.7 购 +5pp 尖点被检出（z=${smile27c?.metric?.toFixed(1)}）`)
ok(!smile.some(s => s.expiry === expA && s.strike === 2.5 && s.option_type === 'put' && Math.abs(s.metric) >= 2), '①微笑：expA K2.5 沽 ATM 无误报（expB K2.5 沽是埋的真异常，允许触发）')
ok(smile.every(s => Number.isFinite(s.iv) && s.option_code), '①微笑：信号字段完整（iv/option_code 有值）')
ok(smile.every(s => Math.abs(s.strike - S) / S <= 0.1001), '①微笑：全部落在 |m|≤10% 平值区')

const cp = r.signals.filter(s => s.type === 'cp')
ok(cp.length === 2, `②C-P：恰 2 条（expB K2.5 沽 + expA K2.7 购，got ${cp.length}）`)
ok(cp.some(s => s.expiry === expB && s.strike === 2.5 && s.option_type === 'put' && s.codes.length === 2), '②C-P：expB K2.5 主推 put，codes 含购沽')
ok(cp.some(s => s.expiry === expA && s.strike === 2.7), '②C-P：expA K2.7 价差 +5pp 检出')

const term = r.signals.filter(s => s.type === 'term')
ok(term.length === 0, `③期限：contango 常态无倒挂误报（got ${term.length}）`)

ok(!r.signals.some(s => s.type === 'theory'), '④已下线：不再产出 theory 信号（交易所参考价测的是模型误差，不是定价错误）')
ok(SIGNAL_TYPES.length === 3 && !SIGNAL_TYPES.some(t => t.id === 'theory'), '信号类型只剩三类')
ok(r.signals.every(s => Number.isInteger(s.pct) && s.pct >= 0 && s.pct <= 100), '每条信号带 0~100 的类内百分位（仅展示，不参与排序）')
ok(r.signals.every((s, i) => i === 0 || r.signals[i - 1].strength >= s.strength), '排序：按 strength 降序（三类口径统一为"几倍阈值"）')

// ---- 期限倒挂场景：近月整体 IV 高于远月 ----
{
  const rows2 = []
  for (const K of strikes) {
    const m = (K - S) / S
    rows2.push(row(`A${K}C`, '20261125', 'call', K, 26 + 300 * m * m))
    rows2.push(row(`A${K}P`, '20261125', 'put', K, 26 + 300 * m * m))
    rows2.push(row(`B${K}C`, '20261223', 'call', K, 22 + 300 * m * m))
    rows2.push(row(`B${K}P`, '20261223', 'put', K, 22 + 300 * m * m))
  }
  const r2 = buildSignals([{ code: '510050', name: '50ETF', spot: S, rows: rows2 }], { now: NOW })
  const term2 = r2.signals.filter(s => s.type === 'term')
  ok(term2.length === 2 && term2.every(s => s.expiry === '20261125'), `③期限：购沽各 1 条倒挂（got ${term2.length}）`)
  ok(term2[0]?.strength >= 2, `③期限：强度=inv/2（inv=4pp → ×2）got ×${term2[0]?.strength}`)
  ok(term2[0]?.detail.includes('全段') && term2[0]?.detail.includes('首末差'), '③期限：detail 展示全段 IV 序列与首末差')
}

// ---- 期限倒挂：全段斜率，连续倒挂只报一条 ----
// 25 → 22 → 19 若只比相邻会拆成两条 3pp，全段口径应只报 1 条、幅度 6pp（×3）
{
  const rows2b = []
  for (const [exp, iv] of [['20261125', 25], ['20261223', 22], ['20270127', 19]]) {
    for (const K of strikes) {
      const m = (K - S) / S
      rows2b.push(row(`A${K}C${exp}`, exp, 'call', K, iv + 300 * m * m))
      rows2b.push(row(`A${K}P${exp}`, exp, 'put', K, iv + 300 * m * m))
    }
  }
  const r2b = buildSignals([{ code: '510050', name: '50ETF', spot: S, rows: rows2b }], { now: NOW })
  const t2b = r2b.signals.filter(s => s.type === 'term')
  ok(t2b.length === 2, `③期限全段：连续倒挂不拆分，购沽各 1 条（got ${t2b.length}）`)
  ok(t2b.every(s => Math.abs(s.metric - 6) < 0.6), `③期限全段：幅度为首末差 6pp 而非相邻 3pp（got ${t2b.map(s => s.metric.toFixed(1))}）`)
}

// ---- 边界：stale 行保留但打标；bad status 剔除；IV 过低剔除（小数口径 0.0004→0.04%）----
{
  const rows3 = [row('X1', '20261125', 'call', 2.5, 25)]
  rows3[0].data_status = 'stale'
  rows3.push(row('X2', '20261125', 'put', 2.5, 0.0004))
  rows3.push(row('X3', '20261125', 'call', 2.6, 25, {}))
  rows3[2].data_status = 'unavailable'
  const r3 = buildSignals([{ code: '510050', name: '50ETF', spot: S, rows: rows3 }], { now: NOW })
  ok(r3.summary.ivRows === 1, `边界：IV≤2 与 unavailable 被剔除（ivRows=${r3.summary.ivRows}）`)
}

// ---- DTE 过滤：近月整条链不参与扫描 ----
{
  ok(daysToExpiry('20261125', new Date('2026-11-23T04:00:00Z')) === 2, 'daysToExpiry：11-23 → 11-25 = 2 天')
  ok(daysToExpiry('20261223', new Date('2026-11-23T04:00:00Z')) === 30, 'daysToExpiry：11-23 → 12-23 = 30 天')
  ok(daysToExpiry('20261124', new Date('2026-11-23T16:30:00Z')) === 0, 'daysToExpiry：中国时区跨日界（16:30Z = 次日 00:30 → DTE 0）')
  ok(daysToExpiry('bogus', NOW) === null, 'daysToExpiry：非法 expiry → null')

  const rows5 = []
  for (const K of strikes) {
    const m = (K - S) / S
    rows5.push(row(`N${K}C`, '20261125', 'call', K, 20 + 300 * m * m))
    rows5.push(row(`N${K}P`, '20261125', 'put', K, 20 + 300 * m * m))
  }
  rows5[strikes.indexOf(2.7) * 2].iv += 8   // 埋 +8pp 尖点：若被扫到必出 smile 信号
  const r5 = buildSignals([{ code: '510050', name: '50ETF', spot: S, rows: rows5 }], { now: new Date('2026-11-23T04:00:00Z') })
  ok(r5.signals.length === 0, `DTE 过滤：2 天后到期的整条链不产出信号（got ${r5.signals.length} 条）`)
  ok(r5.summary.droppedDte === rows5.length, `DTE 过滤：droppedDte 如实计数（got ${r5.summary.droppedDte}/${rows5.length}）`)
}

// ---- 排序：强度降序 ----
ok(r.signals.every((s, i) => i === 0 || r.signals[i - 1].strength >= s.strength), '排序：strength 降序')

// ---- 深链：strategyDeepLink 四类信号的腿规格 ----
{
  const { strategyDeepLink, resolveLegSpecs } = await import('../src/utils/screener.mjs')
  const smileUp = strategyDeepLink({ type: 'smile', option_type: 'call', metric: 3, strike: 2.6 })
  ok(smileUp.legs === 'sell:call:2.6,buy:call:out' && !smileUp.note, `深链①smile 偏贵 call → 卖本腿+买外侧（got ${smileUp.legs}）`)
  const smileDn = strategyDeepLink({ type: 'smile', option_type: 'put', metric: -3, strike: 2.4 })
  ok(smileDn.legs === 'buy:put:2.4,sell:put:out', `深链①smile 偏便宜 put → 买本腿+卖外侧（got ${smileDn.legs}）`)
  const cpNeg = strategyDeepLink({ type: 'cp', option_type: 'call', metric: -4, strike: 2.5 })
  ok(cpNeg.legs === 'buy:call:2.5,sell:put:2.5', `深链②cp dev<0 → 预填合成多头两腿（got ${cpNeg.legs}）`)
  ok(cpNeg.note.includes('反向转换') && cpNeg.note.includes('融券'), '深链②cp dev<0 → 提示反向转换需融券，不再说成"价差回归"')
  const cpPos = strategyDeepLink({ type: 'cp', option_type: 'put', metric: 4, strike: 2.5 })
  ok(cpPos.legs === 'sell:call:2.5,buy:put:2.5', `深链②cp dev>0 → 预填合成空头两腿（got ${cpPos.legs}）`)
  ok(cpPos.note.includes('转换套利') && cpPos.note.includes('标的'), '深链②cp dev>0 → 提示转换套利需补标的腿')
  const term = strategyDeepLink({ type: 'term', option_type: 'call', metric: 3, strike: 2.5 })
  ok(term.legs === 'sell:call:near' && term.note.includes('日历'), `深链③term → 近月卖出腿 + 日历提示（got ${term.legs}）`)

  // resolveLegSpecs：精确 K / out / near / 缺 K 回落
  const contracts = [
    { contract_id: 'C24', option_type: 'call', strike: 2.4, last_price: 0.1 },
    { contract_id: 'C25', option_type: 'call', strike: 2.5, last_price: 0.08 },
    { contract_id: 'C26', option_type: 'call', strike: 2.6, last_price: 0.06 },
    { contract_id: 'P25', option_type: 'put', strike: 2.5, last_price: 0.09 },
    { contract_id: 'P24', option_type: 'put', strike: 2.4, last_price: null },
  ]
  const rs = resolveLegSpecs(
    [{ side: 'sell', type: 'call', strikeSpec: '2.5' }, { side: 'buy', type: 'call', strikeSpec: 'out' }],
    contracts, 2.5)
  ok(rs[0]?.contractId === 'C25' && rs[1]?.contractId === 'C26', `resolve：精确 K + out=锚上一档（got ${rs[0]?.contractId},${rs[1]?.contractId}）`)
  const rp = resolveLegSpecs([{ side: 'buy', type: 'put', strikeSpec: 'out' }], contracts, 2.5)
  ok(rp[0]?.contractId === 'P25', `resolve：out 缺锚 → 就近平值回落（got ${rp[0]?.contractId}）`)
  const rn = resolveLegSpecs([{ side: 'sell', type: 'put', strikeSpec: 'near' }], contracts, 2.52)
  ok(rn[0]?.contractId === 'P25', `resolve：near=距现价最近（got ${rn[0]?.contractId}）`)
  const rx = resolveLegSpecs([{ side: 'buy', type: 'put', strikeSpec: '2.55' }], contracts, null)
  ok(rx[0]?.contractId === 'P25', `resolve：精确 K 缺失 → 就近回落 P25（got ${rx[0]?.contractId}）`)
}

// ---- 成本口径：价差成本（往返）vs 信号幅度（ATM 近似 vega）----
{
  const S6 = 2.5, EXP = '20261223'   // T=2026-11-23 → DTE 30，落在扫描区内
  const T = new Date('2026-11-23T04:00:00Z')
  const mk = (code, type, K, iv, bid, ask, ts = '2026-12-23 14:30:00') => ({
    option_code: code, expiry: EXP, option_type: type, strike: K, iv,
    data_status: 'ok', last_price: bid && ask ? (bid + ask) / 2 : null,
    volume: 500, bid, ask, market_ts: ts, spot: { price: S6, data_status: 'ok' },
  })
  const rs = []
  for (const K of strikes) {
    const m = (K - S6) / S6
    const base = 20 + 300 * m * m
    rs.push(mk(`C${K}`, 'call', K, base, K === 2.5 ? 0.0790 : null, K === 2.5 ? 0.0810 : null))
    // K2.5 沽埋 +6pp → C-P 偏离中位 -6pp（阈值 3pp）
    rs.push(mk(`P${K}`, 'put', K, K === 2.5 ? base + 6 : base,
      K === 2.5 ? 0.0770 : null, K === 2.5 ? 0.0790 : null,
      K === 2.5 ? '2026-12-23 14:55:00' : undefined))
  }
  const rc = buildSignals([{ code: '510050', name: '50ETF', spot: S6, rows: rs }], { now: T })
  const cp = rc.signals.find(s => s.type === 'cp')
  ok(!!cp, '成本：构造出 C-P 信号')
  // 往返成本 = 两腿 (卖一−买一)/中间价 之和 = 2.500% + 2.564% ≈ 5.06%
  ok(Math.abs(cp.cost_pct - 5.064) < 0.05, `成本：两腿价差相加（got ${cp.cost_pct?.toFixed(3)}%）`)
  // 折成 IV 点数：价差(元/份) ÷ vega(元/份/pp)，两腿各约 0.7pp
  ok(cp.cost_pp > 1.2 && cp.cost_pp < 1.7, `成本：价差折成 IV 点数（got ${cp.cost_pp?.toFixed(2)}pp）`)
  ok(Math.abs(cp.net_pp - (cp.edge_pp - cp.cost_pp)) < 1e-9 && cp.net_pp > 0 && cp.executable,
    `成本：净额 = 幅度−成本(pp)，>0 → 可执行（got ${cp.net_pp?.toFixed(2)}pp）`)
  ok(Math.abs(cp.net_pp - (6 - cp.cost_pp)) < 1e-9, '成本：净额与信号幅度同为 pp 单位')
  ok(cp.market_ts === '2026-12-23 14:55:00', `成本：时效取涉及腿的最新行情时间（got ${cp.market_ts}）`)
  ok(cp.wide_spread === true, '成本：往返价差 >4% 标「宽」')

  // BS vega：虚值腿必须显著小于平值腿（ATM 近似会把虚值腿高估一个量级）
  const vAtm = bsVegaPerPp(S6, 2.5, 20, EXP, T)
  const vOtm = bsVegaPerPp(S6, 2.8, 20, EXP, T)
  ok(vAtm > 0 && vOtm > 0 && vAtm / vOtm > 2, `成本：虚值腿 vega 显著低于平值（ATM/OTM=${(vAtm / vOtm).toFixed(1)}×）`)
  ok(bsVegaPerPp(S6, 2.5, 20, EXP, T) === 0.002855 || Math.abs(bsVegaPerPp(S6, 2.5, 20, EXP, T) - 0.002855) < 1e-5,
    `成本：平值 vega 与手算一致（got ${bsVegaPerPp(S6, 2.5, 20, EXP, T)?.toFixed(6)}）`)

  // 无五档 → 成本/净额为 null（不拿最新价冒充价差），时效也留空
  const rs2 = rs.map(r => ({ ...r, bid: null, ask: null, market_ts: null }))
  const rc2 = buildSignals([{ code: '510050', name: '50ETF', spot: S6, rows: rs2 }], { now: T })
  const cp2 = rc2.signals.find(s => s.type === 'cp')
  ok(cp2 && cp2.cost_pct === null && cp2.cost_pp === null && cp2.net_pp === null
    && cp2.executable === false && cp2.market_ts === null,
    '成本：缺买一/卖一 → 成本与时效均为 null，不冒充可执行')

  // 单腿信号（微笑）成本 = 该腿价差；期限信号成本 = 近月腿 + 远月腿
  const smile = rc.signals.find(s => s.type === 'smile')
  ok(!!smile && (smile.cost_pct === null || smile.cost_pct <= cp.cost_pct), '成本：单腿信号不超过双腿结构成本')
}

// ---- IV 环境（IVR / VRP）----
{
  // 归一化：IVR 优先 → VRP 兜底 → none（不臆造水位）
  const eIvr = ivEnvironment({ ivr: 85, ivp: 92, vrp: 0.5, iv30: 20, samples: 120, min_samples: 20 })
  ok(eIvr.basis === 'ivr' && eIvr.level === 'high', `环境：IVR=85 → ivr/high（got ${eIvr.basis}/${eIvr.level}）`)
  ok(ivEnvironment({ ivr: 70 }).level === 'high', '环境：IVR=70 恰为高位阈值（≥70）')
  ok(ivEnvironment({ ivr: 50, vrp: 8 }).level === 'mid', '环境：IVR 可用时 VRP 不参与判定（50 → mid）')
  ok(ivEnvironment({ ivr: 30 }).level === 'low', '环境：IVR=30 恰为低位阈值（≤30）')

  const eVrp = ivEnvironment({ ivr: null, vrp: 5.8, samples: 1 })
  ok(eVrp.basis === 'vrp' && eVrp.level === 'high',
    `环境：IVR 未就绪 → 退 VRP，+5.8pp 判偏贵（got ${eVrp.basis}/${eVrp.level}）`)
  ok(ivEnvironment({ ivr: null, vrp: -6.1 }).level === 'low', '环境：VRP −6.1pp → 偏便宜')
  ok(ivEnvironment({ ivr: null, vrp: 0.5 }).level === 'mid', '环境：VRP 0.5pp → 中性')
  ok(ivEnvironment(null).basis === 'none' && ivEnvironment(null).level === null,
    '环境：无数据 → none/null，不臆造水位')
  ok(ivEnvironment({ ivr: null, vrp: null, samples: 3 }).samples === 3, '环境：样本数透传供 UI 显示进度')

  // 合成一条平值区 call 链 + 同形 put 链，在 K2.55 埋 ±6pp 尖点
  const mkEnv = (spotPt, ivEnv) => {
    const strikes = [2.3, 2.35, 2.4, 2.45, 2.5, 2.55, 2.6, 2.65, 2.7]
    const curve = K => 20 + 300 * ((K - 2.5) / 2.5) ** 2
    const base = {
      expiry: '20261223', last_price: 0.05, volume: 500, data_status: 'ok',
      bid: 0.049, ask: 0.051, market_ts: '2026-12-23 14:30:00', spot: { price: 2.5, data_status: 'ok' },
    }
    const rows = strikes.flatMap(K => [
      { ...base, option_code: `C${K}`, option_type: 'call', strike: K,
        iv: curve(K) + (Math.abs(K - 2.55) < 1e-9 ? spotPt : 0) },
      { ...base, option_code: `P${K}`, option_type: 'put', strike: K, iv: curve(K) },
    ])
    return buildSignals([{ code: '510050', name: '50ETF', spot: 2.5, rows }],
      { now: new Date('2026-11-23T04:00:00Z'), ivEnv })
  }
  const highEnv = { 510050: { ivr: 88, vrp: 5, samples: 120, min_samples: 20 } }
  const lowEnv = { 510050: { ivr: 12, vrp: -5, samples: 120, min_samples: 20 } }

  const sHigh = mkEnv(+6, highEnv).signals.find(s => s.type === 'smile')
  ok(!!sHigh, '环境：构造出微笑信号（+6pp 尖点）')
  ok(sHigh.env_bias === 'sell' && sHigh.env_fit === 1,
    `环境：偏贵腿 × 高水位 → 卖方向顺风（got ${sHigh?.env_bias}/${sHigh?.env_fit}）`)
  ok(sHigh.env_basis === 'ivr' && sHigh.env_ivr === 88, '环境：信号携带 IVR 原值（供 tooltip）')

  const sLow = mkEnv(+6, lowEnv).signals.find(s => s.type === 'smile')
  ok(sLow.env_fit === -1, `环境：偏贵腿 × 低水位 → 逆风（got ${sLow?.env_fit}）`)

  const sCheap = mkEnv(-6, lowEnv).signals.find(s => s.type === 'smile')
  ok(sCheap.env_bias === 'buy' && sCheap.env_fit === 1,
    `环境：偏便宜腿 × 低水位 → 买方向顺风（got ${sCheap?.env_bias}/${sCheap?.env_fit}）`)

  const relatives = mkEnv(+6, highEnv).signals.filter(s => s.type === 'cp' || s.type === 'term')
  ok(relatives.length > 0 && relatives.every(s => s.env_bias === 'neutral' && s.env_fit === 0),
    '环境：C-P / 期限是相对价值结构，整体水位对它们中性（fit 恒 0）')

  // 不传 ivEnv → 全部降级，且 strength 口径完全不受影响
  const withEnv = mkEnv(+6, highEnv).signals
  const noEnv = mkEnv(+6, null).signals
  ok(noEnv.length > 0 && noEnv.every(s => s.env_basis === 'none' && s.env_level === null && s.env_fit === 0),
    '环境：不传 ivEnv 时全部降级 none，向后兼容')
  const key = s => `${s.type}|${s.option_code}|${s.strike}|${s.expiry}`
  ok(withEnv.length === noEnv.length && withEnv.every(s => {
    const o = noEnv.find(x => key(x) === key(s))
    return o && Math.abs(o.strength - s.strength) < 1e-12
  }), '环境：水位不改变 strength（阈值口径不受影响，只影响标注与次序）')

  // 过滤：只看顺风
  const fav = filterSignals(withEnv, {
    types: new Set(['smile', 'cp', 'term']), targets: new Set(['510050']), minStrength: 1, onlyFavorable: true,
  })
  ok(fav.length > 0 && fav.every(s => s.env_fit > 0), '环境：只看顺风 → 仅保留 env_fit>0')
  ok(filterSignals(withEnv, {
    types: new Set(['smile', 'cp', 'term']), targets: new Set(['510050']), minStrength: 1,
  }).length === withEnv.length, '环境：不开顺风过滤时不丢行')

  // summary 交代判据来源（UI 用来提示「IVR 未就绪、暂用 VRP」）
  ok(mkEnv(+6, highEnv).summary.envBasis?.ivr === 1, '环境：summary.envBasis 统计判据来源')
  ok(mkEnv(+6, null).summary.envBasis?.none === 1, '环境：无水位时 summary.envBasis.none 计数')
}

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
