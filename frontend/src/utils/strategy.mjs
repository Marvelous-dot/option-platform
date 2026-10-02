// Local European Black–Scholes assumptions only. Rates in blackScholes are decimals;
// simulateStrategy's form rates/vol/q are percentages. All tenors use ACT/365.
export const PRESETS = [
  ['long-call', '买入 Call'], ['short-call', '卖出 Call'],
  ['long-put', '买入 Put'], ['short-put', '卖出 Put'],
  ['protective-put', '保护性 Put'], ['covered-call', '备兑 Call'],
  ['bull-call', '牛市 Call 价差'], ['bear-put', '熊市 Put 价差'],
  ['long-straddle', '买入跨式 Straddle'], ['short-straddle', '卖出跨式 Straddle'],
  ['long-strangle', '买入宽跨式 Strangle'], ['short-strangle', '卖出宽跨式 Strangle'],
  ['call-butterfly', 'Call 蝶式（1 / −2 / 1）'],
].map(([id, name]) => ({ id, name }))

function number(value, label, min = -Infinity, max = Infinity, integer = false) {
  if (!['number', 'string'].includes(typeof value) || (typeof value === 'string' && !value.trim())) throw new Error(`${label}不能为空，须为有限数值`)
  const n = Number(value)
  if (!Number.isFinite(n)) throw new Error(`${label}须为有限数值`)
  if (n < min || n > max || (integer && !Number.isSafeInteger(n))) throw new Error(`${label}须在 ${min} 至 ${max} 之间${integer ? '，且为整数' : ''}`)
  return n
}
function finite(value) {
  if (!Number.isFinite(value)) throw new Error('计算超出数值范围，请缩小参数')
  return value
}

// Rational approximation of the normal tail (absolute error about 1e-14).
function normalCDF(x) {
  const y = Math.abs(x)
  let tail = 0
  if (y < 37) {
    const e = Math.exp(-y * y / 2)
    if (y < 7.07106781186547) {
      const numerator = ((((((.0352624965998911 * y + .700383064443688) * y + 6.37396220353165) * y + 33.912866078383) * y + 112.079291497871) * y + 221.213596169931) * y + 220.206867912376)
      const denominator = (((((((.0883883476483184 * y + 1.75566716318264) * y + 16.064177579207) * y + 86.7807322029461) * y + 296.564248779674) * y + 637.333633378831) * y + 793.826512519948) * y + 440.413735824752)
      tail = e * numerator / denominator
    } else tail = e / (y + 1 / (y + 2 / (y + 3 / (y + 4 / (y + .65))))) / Math.sqrt(2 * Math.PI)
  }
  return x > 0 ? 1 - tail : tail
}

export function blackScholes(input) {
  const { type } = input
  if (type !== 'call' && type !== 'put') throw new Error('期权类型须为 call 或 put')
  const spot = number(input.spot, '标的价格', 0, 1e9)
  const strike = number(input.strike, '行权价', Number.MIN_VALUE, 1e9)
  const time = number(input.time, '年期限', 0, 100)
  const vol = number(input.vol, '波动率', 0, 10)
  const rate = number(input.rate, '利率', -1, 1), q = number(input.q, '股息率', -1, 1)
  const direction = type === 'call' ? 1 : -1
  const discountQ = finite(Math.exp(-q * time))
  const a = finite(spot * discountQ), b = finite(strike * Math.exp(-rate * time))
  const difference = a - b
  if (time === 0 || vol === 0) {
    const kink = Math.abs(difference) <= 8 * Number.EPSILON * Math.max(a, b)
    return { price: Math.max(direction * difference, 0), delta: kink ? null : direction * difference > 0 ? direction * discountQ : 0 }
  }
  if (spot === 0) return { price: type === 'call' ? 0 : b, delta: type === 'call' ? 0 : -discountQ }
  const width = vol * Math.sqrt(time)
  // log difference avoids an overflowing spot / strike ratio.
  const d1 = (Math.log(spot) - Math.log(strike) + (rate - q) * time) / width + width / 2
  const d2 = d1 - width
  return {
    price: finite(Math.max(0, direction * (a * normalCDF(direction * d1) - b * normalCDF(direction * d2)))),
    delta: finite(direction * discountQ * normalCDF(direction * d1)),
  }
}

function parameters(input) {
  const p = {}
  for (const [key, label] of [['spot', '标的价格'], ['lowStrike', '低行权价'], ['midStrike', '中行权价'], ['highStrike', '高行权价']]) p[key] = number(input[key], label, key === 'spot' ? 0 : Number.MIN_VALUE, 1e9)
  if (!(p.lowStrike < p.midStrike && p.midStrike < p.highStrike)) throw new Error('须满足 0 < 低行权价 < 中行权价 < 高行权价')
  p.days = number(input.days, '剩余天数', 0, 36500)
  p.vol = number(input.vol, '波动率 (%)', 0, 1000)
  p.rate = number(input.rate, '利率 (%)', -100, 100)
  p.q = number(input.q, '股息率 (%)', -100, 100)
  p.multiplier = number(input.multiplier, '乘数', 1, 1e9, true)
  p.qty = number(input.qty, '组数', 1, 1e6, true)
  return p
}

function buildLegs(id, p) {
  const c = (units, strike = p.midStrike) => ({ type: 'call', units, strike })
  const put = (units, strike = p.midStrike) => ({ type: 'put', units, strike })
  const stock = { type: 'stock', units: 1, strike: null }
  const choices = {
    'long-call': [c(1)], 'short-call': [c(-1)], 'long-put': [put(1)], 'short-put': [put(-1)],
    'protective-put': [stock, put(1)], 'covered-call': [stock, c(-1)],
    'bull-call': [c(1, p.lowStrike), c(-1, p.highStrike)],
    'bear-put': [put(1, p.highStrike), put(-1, p.lowStrike)],
    'long-straddle': [c(1), put(1)], 'short-straddle': [c(-1), put(-1)],
    'long-strangle': [put(1, p.lowStrike), c(1, p.highStrike)],
    'short-strangle': [put(-1, p.lowStrike), c(-1, p.highStrike)],
    'call-butterfly': [c(1, p.lowStrike), c(-2), c(1, p.highStrike)],
  }
  if (!Object.hasOwn(choices, id)) throw new Error('未知策略')
  return choices[id]
}

// On each [lo, hi], terminal P&L = slope * S + intercept. Build from active
// legs, not two sampled prices, so the net tail slope is exact and hedges cancel.
export function analyzePayoff(legs, entryCost) {
  number(entryCost, '建仓净支出')
  if (!Array.isArray(legs) || !legs.length) throw new Error('组合须包含至少一条腿')
  for (const leg of legs) {
    if (!['stock', 'call', 'put'].includes(leg.type)) throw new Error('未知腿类型')
    number(leg.units, '腿数量', -1e6, 1e6, true)
    if (leg.type !== 'stock') number(leg.strike, '行权价', Number.MIN_VALUE, 1e9)
  }
  const knots = [...new Set([0, ...legs.filter(l => l.type !== 'stock').map(l => l.strike)])].sort((a, b) => a - b)
  const segments = knots.map((lo, i) => {
    let slope = 0, intercept = -entryCost
    for (const l of legs) {
      if (l.type === 'stock') slope += l.units
      else if (l.type === 'call' && l.strike <= lo) { slope += l.units; intercept -= l.units * l.strike }
      else if (l.type === 'put' && l.strike > lo) { slope -= l.units; intercept += l.units * l.strike }
    }
    return { lo, hi: knots[i + 1] ?? Infinity, slope: finite(slope), intercept: finite(intercept) }
  })
  const values = segments.map(s => finite(s.slope * s.lo + s.intercept))
  const tailSlope = segments.at(-1).slope
  const minPnl = tailSlope < 0 ? -Infinity : Math.min(...values)
  const maxPnl = tailSlope > 0 ? Infinity : Math.max(...values)
  const points = [], intervals = []
  const scale = Math.max(Math.abs(entryCost), ...legs.map(l => Math.abs(l.units) * (l.strike ?? 0)), Number.MIN_VALUE)
  const eps = 16 * Number.EPSILON * scale
  for (const s of segments) {
    if (s.slope === 0) {
      if (Math.abs(s.intercept) <= eps) {
        if (intervals.length && intervals.at(-1)[1] === s.lo) intervals.at(-1)[1] = s.hi
        else intervals.push([s.lo, s.hi])
      }
    } else {
      const root = finite(-s.intercept / s.slope)
      if (root >= s.lo - eps && root <= s.hi + eps) points.push(Math.max(s.lo, Math.min(s.hi, root)))
    }
  }
  const unique = points.sort((a, b) => a - b).filter((x, i, all) => (i === 0 || x - all[i - 1] > eps) && !intervals.some(([lo, hi]) => x >= lo - eps && x <= hi + eps))
  return { segments, knots, tailSlope, risk: { minPnl, maxPnl, maxProfit: Math.max(0, maxPnl), maxLoss: Math.max(0, -minPnl) }, breakEven: { points: unique, intervals } }
}

export function payoffAt(result, terminalSpot) {
  const s = number(terminalSpot, '到期标的价格', 0)
  const segment = result.segments.find(segment => s < segment.hi) ?? result.segments.at(-1)
  return finite(segment.slope * s + segment.intercept)
}

// 左侧策略分组（单选，含所有 13 个原子策略）
export const PRESET_GROUPS = [
  { id: 'long',  label: '做多 / 买入', items: ['long-call', 'long-put', 'long-straddle', 'long-strangle'] },
  { id: 'short', label: '做空 / 卖出', items: ['short-call', 'short-put', 'short-straddle', 'short-strangle'] },
  { id: 'combo', label: '组合策略',   items: ['protective-put', 'covered-call', 'bull-call', 'bear-put', 'call-butterfly'] },
]
export const PRESET_BY_ID = Object.fromEntries(PRESETS.map(p => [p.id, p]))

// 把策略 id 展开成原始腿；与 buildLegs 等价但可被引擎外直接复用
export function strategyLegs(id, p) {
  return buildLegs(id, p)
}

// 市场合约页（真实挂牌合约）可使用的预设策略：仅期权腿，排除含现货腿
// （protective-put / covered-call 需要持有标的现货，挂牌合约目录无现货腿）。
// 展开成 { type: 'call'|'put', side: 'buy'|'sell', units } 腿模板，
// 行权价留空由用户为每条腿选择具体挂牌合约。
export const MARKET_PRESETS = PRESETS
  .filter(p => !buildLegs(p.id, { lowStrike: 1, midStrike: 2, highStrike: 3 }).some(l => l.type === 'stock'))
  .map(p => ({
    id: p.id,
    name: p.name,
    legs: buildLegs(p.id, { lowStrike: 1, midStrike: 2, highStrike: 3 })
      .map(l => ({ type: l.type, side: l.units > 0 ? 'buy' : 'sell', units: Math.abs(l.units) })),
  }))

export function simulateStrategy(id, input) {
  const params = parameters(input), scale = params.multiplier * params.qty
  const legs = buildLegs(id, params).map(leg => ({ ...leg, ...(leg.type === 'stock' ? { price: params.spot, delta: 1 } : blackScholes({ type: leg.type, spot: params.spot, strike: leg.strike, time: params.days / 365, vol: params.vol / 100, rate: params.rate / 100, q: params.q / 100 })) }))
  const entryCost = finite(legs.reduce((sum, l) => sum + l.units * l.price, 0))
  const analysis = analyzePayoff(legs, entryCost)
  // At expiry the derivative is undefined only if the *net* portfolio has a kink.
  let delta = legs.some(l => l.delta === null) ? null : finite(legs.reduce((sum, l) => sum + l.units * l.delta, 0))
  if (delta === null && params.days === 0) {
    const right = analysis.segments.find(s => params.spot >= s.lo && params.spot < s.hi)
    const left = analysis.segments.find(s => s.hi === params.spot)
    if (!left || left.slope === right.slope) delta = right.slope
  }
  const totalRisk = Object.fromEntries(Object.entries(analysis.risk).map(([key, value]) => [key, Number.isFinite(value) ? finite(value * scale) : value]))
  return { id, params, legs, scale, entryCost, totalEntryCost: finite(entryCost * scale), delta, totalDelta: delta === null ? null : finite(delta * scale), stockShares: legs.filter(l => l.type === 'stock').reduce((sum, l) => sum + l.units * scale, 0), ...analysis, totalRisk }
}

// A single computed state prevents invalid inputs retaining a previous result.
export function evaluateStrategy(id, input) {
  try { return { result: simulateStrategy(id, input), error: '' } }
  catch (error) { return { result: null, error: error.message } }
}

// Terminal P&L of a single listed contract (1 leg) priced at its market/quoted
// premium, scaled by the listed contract unit. No time value assumptions: the
// payoff is purely intrinsic minus paid premium at expiry. Premium is the
// quoted last price (source value, unverified) — not a model value.
export function singleContract(input) {
  const type = input?.type
  if (type !== 'call' && type !== 'put') throw new Error('期权类型须为 call 或 put')
  const strike = number(input.strike, '行权价', Number.MIN_VALUE, 1e9)
  const premium = input?.premium === null || input?.premium === undefined ? null : number(input.premium, '权利金', 0, 1e9)
  const multiplier = number(input.multiplier, '合约单位', 1, 1e9, true)
  const result = analyzePayoff([{ type, units: 1, strike }], premium === null ? 0 : premium)
  const scale = premium === null ? 0 : multiplier
  // analyzePayoff's risk caps maxProfit/maxLoss at 0 for unbounded tails, which
  // is correct for net-credit (short) strategies. For a long single contract
  // the per-unit P&L range is: loss bounded by premium, profit unbounded for
  // calls (S → ∞) or bounded by strike − premium for puts (S → 0).
  // Recompute from the per-unit values directly.
  const perUnitMaxPnl = result.risk.maxPnl, perUnitMinPnl = result.risk.minPnl
  const scaled = value => Number.isFinite(value) ? value * scale : value
  const risk = {
    minPnl: scaled(perUnitMinPnl),
    maxPnl: scaled(perUnitMaxPnl),
    maxProfit: perUnitMaxPnl === null || perUnitMaxPnl === Infinity
      ? Infinity
      : scaled(Math.max(0, perUnitMaxPnl)),
    maxLoss: perUnitMinPnl === null || perUnitMinPnl === -Infinity
      ? Infinity
      : scaled(Math.max(0, -perUnitMinPnl)),
  }
  return { type, strike, premium, multiplier,
    premiumUsable: premium !== null,
    entryCost: premium, perUnitCost: premium === null ? null : premium * multiplier,
    payoff: result, segments: result.segments, breakEven: result.breakEven,
    risk, scale }
}
export function singleContractAt(result, terminalSpot) {
  // analyzePayoff already folds entryCost (the premium) into the P&L intercept,
  // so payoffAt is P&L per unit; scale by the listed contract unit only when a
  // usable premium exists.
  return payoffAt(result, terminalSpot) * (result.premiumUsable ? result.scale : 0)
}

// Generic multi-leg strategy composed from user-selected listed contracts.
// Each leg: { type: 'call'|'put', units: int (张数，带符号：买入为正、卖出为负),
// strike, premium (nullable quoted value, 元/份), multiplier (合约单位 股/张) }.
//
// 每份标的净支出 = Σ units × premium。权利金是市场报价（非模型值）；任一腿
// premium 为 null 即整组合标记 unusable（不补零、不降级）。
//
// 总盈亏（每组合）= Σ legs units × (per-share 内在价值盈亏) × multiplier，
// 直接按腿累加（多腿不同乘数/张数仍精确）。风险边界：per-share 极值由
// analyzePayoff 分段求解；net-debit 多头组合的一尾无界（认购 S→∞ / 认沽 S→0），
// 边界直接保留 ±Infinity，不再二次截断。
export function buildCustomStrategy(legs) {
  if (!Array.isArray(legs) || !legs.length) throw new Error('组合须包含至少一条腿')
  const clean = legs.map((leg, i) => {
    const type = leg?.type
    if (type !== 'call' && type !== 'put') throw new Error(`第 ${i + 1} 条腿的期权类型须为 call 或 put`)
    const units = number(leg.units, `第 ${i + 1} 条腿张数`, -1e6, 1e6, true)
    const strike = number(leg.strike, `第 ${i + 1} 条腿行权价`, Number.MIN_VALUE, 1e9)
    const multiplier = number(leg.multiplier, `第 ${i + 1} 条腿合约单位`, 1, 1e9, true)
    const premium = leg.premium === null || leg.premium === undefined ? null : number(leg.premium, `第 ${i + 1} 条腿权利金`, 0, 1e9)
    return { ...leg, type, units, strike, multiplier, premium }
  })
  const allUsable = clean.every(l => l.premium !== null)
  // 每份标的净支出（未乘合约单位）
  const perShareEntryCost = allUsable ? clean.reduce((sum, l) => sum + l.units * l.premium, 0) : null
  // 总权利金（每组合，元）= Σ units × premium × multiplier（正值=净支出，负值=净收入）
  // 注意：units 带符号（买入正、卖出负），所以是净支出而非毛权利金
  const totalEntryCost = allUsable
    ? clean.reduce((sum, l) => sum + l.units * l.premium * l.multiplier, 0)
    : null
  const result = analyzePayoff(clean, allUsable ? perShareEntryCost : 0)

  // 每组合总盈亏 = Σ legs [units × intrinsic × multiplier] − 总权利金（建仓净支出）
  // 多头腿：units > 0，payoff 为正（+）；空头腿：units < 0，payoff 为负（−）
  const totalPnlAt = s => {
    if (!allUsable) return null
    let total = 0
    for (const l of clean) {
      const intrinsic = l.type === 'call' ? Math.max(s - l.strike, 0) : Math.max(l.strike - s, 0)
      total += l.units * intrinsic * l.multiplier
    }
    total -= totalEntryCost
    return total
  }

  // 风险边界（每组合）：在 S=0、各折点、±∞ 取极值
  const bounds = [0, ...result.knots, Infinity]
  let minTotal = Infinity, maxTotal = -Infinity
  for (const b of bounds) {
    const v = b === Infinity
      ? (result.tailSlope > 0 ? Infinity : (result.tailSlope < 0 ? -Infinity : totalPnlAt(result.knots.at(-1) ?? 0)))
      : totalPnlAt(b)
    if (v === null) continue
    if (Number.isFinite(v)) { if (v < minTotal) minTotal = v; if (v > maxTotal) maxTotal = v }
    else if (v === Infinity) maxTotal = Infinity
    else if (v === -Infinity) minTotal = -Infinity
  }
  // 中间折点也要逐一取（上下界可能在中间折点而非端点）
  for (const k of result.knots) {
    const v = totalPnlAt(k)
    if (v !== null && Number.isFinite(v)) { if (v < minTotal) minTotal = v; if (v > maxTotal) maxTotal = v }
  }
  const risk = {
    minPnl: minTotal,
    maxPnl: maxTotal,
    maxProfit: maxTotal === Infinity ? Infinity : Math.max(0, maxTotal),
    maxLoss: minTotal === -Infinity ? Infinity : Math.max(0, -minTotal),
  }

  return {
    legs: clean,
    allUsable,
    entryCost: perShareEntryCost,
    totalEntryCost,
    perShareEntryCost,
    totalPnlAt,
    risk,
    totalRisk: risk,
    breakEven: result.breakEven,
    segments: result.segments,
    tailSlope: result.tailSlope,
    knots: result.knots,
  }
}

// 每组合情景盈亏（S 到期价 → 总盈亏，元；allUsable=false 时返回 null）
export function customStrategyAt(result, terminalSpot) {
  if (!result || typeof result.totalPnlAt !== 'function') return null
  if (terminalSpot == null) return null // Number(null)=0，须显式挡住 null/undefined
  const s = Number(terminalSpot)
  if (!Number.isFinite(s) || s < 0) return null
  return result.totalPnlAt(s)
}
