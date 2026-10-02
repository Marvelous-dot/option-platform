import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, reactive, ref } from 'vue'

// Keep every specification visible in RED even before the module exists.
const engine = await import('../src/utils/strategy.mjs').catch(() => null)
const api = () => { assert.ok(engine, 'missing local strategy calculation module'); return engine }
const defaults = { spot: 3, lowStrike: 2.8, midStrike: 3, highStrike: 3.2, days: 30, vol: 20, rate: 2, q: 0, multiplier: 10000, qty: 1 }
const near = (actual, expected, tolerance = 1e-9) => assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`)
const bsInput = { spot: 100, strike: 100, time: 1, vol: .2, rate: .05, q: 0 }

test('BS standard call/put prices and deltas', () => {
  const { blackScholes } = api()
  const c = blackScholes({ ...bsInput, type: 'call' }), p = blackScholes({ ...bsInput, type: 'put' })
  near(c.price, 10.450583572185565, 2e-6)
  near(p.price, 5.573526022256971, 2e-6)
  near(c.delta, .6368306511756191, 2e-7)
  near(p.delta, -.3631693488243809, 2e-7)
})

test('put-call parity and delta parity include continuous dividend yield q', () => {
  const { blackScholes } = api()
  for (const spot of [0, 50, 100, 150]) for (const q of [-.01, .03, .1]) {
    const input = { ...bsInput, spot, q }
    const c = blackScholes({ ...input, type: 'call' }), p = blackScholes({ ...input, type: 'put' })
    near(c.price - p.price, spot * Math.exp(-q) - 100 * Math.exp(-.05))
    near(c.delta - p.delta, Math.exp(-q))
  }
  near(blackScholes({ ...bsInput, q: .03, type: 'call' }).price, 8.652528553942709, 2e-6)
})

test('T=0 uses intrinsic value, kink delta is explicitly undefined', () => {
  const { blackScholes } = api()
  assert.deepEqual(blackScholes({ ...bsInput, spot: 110, time: 0, type: 'call' }), { price: 10, delta: 1 })
  assert.deepEqual(blackScholes({ ...bsInput, spot: 90, time: 0, type: 'put' }), { price: 10, delta: -1 })
  assert.deepEqual(blackScholes({ ...bsInput, time: 0, type: 'call' }), { price: 0, delta: null })
  assert.deepEqual(blackScholes({ ...bsInput, time: 0, type: 'put' }), { price: 0, delta: null })
})

test('sigma=0 uses discounted deterministic payoff and discounted delta', () => {
  const { blackScholes } = api()
  const c = blackScholes({ ...bsInput, vol: 0, q: .02, type: 'call' })
  near(c.price, 100 * Math.exp(-.02) - 100 * Math.exp(-.05))
  near(c.delta, Math.exp(-.02))
  assert.deepEqual(blackScholes({ ...bsInput, vol: 0, q: .02, type: 'put' }), { price: 0, delta: 0 })
  assert.equal(blackScholes({ ...bsInput, rate: 0, vol: 0, type: 'call' }).delta, null)
})

const shapes = {
  'long-call': [['call', 1, 3]], 'short-call': [['call', -1, 3]],
  'long-put': [['put', 1, 3]], 'short-put': [['put', -1, 3]],
  'protective-put': [['stock', 1, null], ['put', 1, 3]],
  'covered-call': [['stock', 1, null], ['call', -1, 3]],
  'bull-call': [['call', 1, 2.8], ['call', -1, 3.2]],
  'bear-put': [['put', 1, 3.2], ['put', -1, 2.8]],
  'long-straddle': [['call', 1, 3], ['put', 1, 3]],
  'short-straddle': [['call', -1, 3], ['put', -1, 3]],
  'long-strangle': [['put', 1, 2.8], ['call', 1, 3.2]],
  'short-strangle': [['put', -1, 2.8], ['call', -1, 3.2]],
  'call-butterfly': [['call', 1, 2.8], ['call', -2, 3], ['call', 1, 3.2]],
}
for (const [id, shape] of Object.entries(shapes)) test(`preset ${id}: exact legs, signed entry, delta and terminal payoff`, () => {
  const { simulateStrategy, blackScholes, payoffAt } = api()
  const r = simulateStrategy(id, defaults)
  assert.deepEqual(r.legs.map(l => [l.type, l.units, l.strike]), shape)
  let cost = 0, delta = 0
  for (const [type, units, strike] of shape) {
    const model = type === 'stock' ? { price: 3, delta: 1 } : blackScholes({ spot: 3, strike, time: 30 / 365, vol: .2, rate: .02, q: 0, type })
    cost += units * model.price; delta += units * model.delta
  }
  near(r.entryCost, cost); near(r.delta, delta); near(r.totalEntryCost, cost * 10000)
  for (const s of [0, 1, 2.8, 3, 3.2, 5, 100]) {
    const terminal = shape.reduce((sum, [type, units, k]) => sum + units * (type === 'stock' ? s : type === 'call' ? Math.max(s - k, 0) : Math.max(k - s, 0)), 0)
    near(payoffAt(r, s), terminal - cost)
  }
})

test('13 presets have correct whole-portfolio finite/infinite risk bounds', () => {
  const { simulateStrategy, PRESETS } = api()
  assert.equal(PRESETS.length, 13)
  for (const id of Object.keys(shapes)) {
    const r = simulateStrategy(id, defaults), c = r.entryCost
    const expected = {
      'long-call': [-c, Infinity], 'short-call': [-Infinity, -c],
      'long-put': [-c, 3 - c], 'short-put': [-3 - c, -c],
      'protective-put': [3 - c, Infinity], 'covered-call': [-c, 3 - c],
      'bull-call': [-c, .4 - c], 'bear-put': [-c, .4 - c],
      'long-straddle': [-c, Infinity], 'short-straddle': [-Infinity, -c],
      'long-strangle': [-c, Infinity], 'short-strangle': [-Infinity, -c],
      'call-butterfly': [-c, .2 - c],
    }[id]
    expected.forEach((v, i) => Number.isFinite(v) ? near(i ? r.risk.maxPnl : r.risk.minPnl, v) : assert.equal(i ? r.risk.maxPnl : r.risk.minPnl, v))
    assert.equal(r.risk.maxLoss, Math.max(0, -r.risk.minPnl))
    assert.equal(r.risk.maxProfit, Math.max(0, r.risk.maxPnl))
  }
})

test('break-even roots are analytic, independent of plotting, and match every preset', () => {
  const { simulateStrategy, payoffAt } = api()
  for (const id of Object.keys(shapes)) {
    const r = simulateStrategy(id, defaults), c = r.entryCost
    const expected = {
      'long-call': [3 + c], 'short-call': [3 - c], 'long-put': [3 - c], 'short-put': [3 + c],
      'protective-put': [c], 'covered-call': [c], 'bull-call': [2.8 + c], 'bear-put': [3.2 - c],
      'long-straddle': [3 - c, 3 + c], 'short-straddle': [3 + c, 3 - c],
      'long-strangle': [2.8 - c, 3.2 + c], 'short-strangle': [2.8 + c, 3.2 - c],
      'call-butterfly': [2.8 + c, 3.2 - c],
    }[id]
    assert.equal(r.breakEven.points.length, expected.length, id)
    r.breakEven.points.forEach((x, i) => { near(x, expected[i]); near(payoffAt(r, x), 0) })
    assert.deepEqual(r.breakEven.intervals, [])
  }
})

test('piecewise solver detects whole zero intervals, isolated knots, no root and distant roots', () => {
  const { analyzePayoff } = api()
  const call = [{ type: 'call', units: 1, strike: 3 }]
  assert.deepEqual(analyzePayoff(call, 0).breakEven, { points: [], intervals: [[0, 3]] })
  assert.deepEqual(analyzePayoff(call, -1).breakEven, { points: [], intervals: [] })
  assert.deepEqual(analyzePayoff(call, 1000000).breakEven.points, [1000003])
  const butterfly = shapes['call-butterfly'].map(([type, units, strike]) => ({ type, units, strike }))
  near(analyzePayoff(butterfly, .2).breakEven.points[0], 3)
  assert.equal(analyzePayoff(butterfly, .2).breakEven.points.length, 1)
  const cancel = [...call, { ...call[0], units: -1 }]
  assert.deepEqual(analyzePayoff(cancel, 0).breakEven, { points: [], intervals: [[0, Infinity]] })
  assert.equal(analyzePayoff(cancel, 0).risk.maxLoss, 0)
  assert.equal(analyzePayoff(cancel, 0).risk.maxProfit, 0)
})

test('unequal-wing butterfly retains finite tail value, never assumes symmetric wings', () => {
  const { simulateStrategy, payoffAt } = api()
  const r = simulateStrategy('call-butterfly', { ...defaults, highStrike: 3.5 })
  near(r.risk.minPnl, -.3 - r.entryCost)
  near(r.risk.maxPnl, .2 - r.entryCost)
  near(payoffAt(r, 1e10), -.3 - r.entryCost, 1e-8)
  assert.equal(r.tailSlope, 0)
})

test('multiplier and groups scale totals only; covered stock is multiplier shares per group', () => {
  const { simulateStrategy } = api()
  for (const id of Object.keys(shapes)) {
    const a = simulateStrategy(id, defaults), b = simulateStrategy(id, { ...defaults, multiplier: 200, qty: 3 })
    near(a.entryCost, b.entryCost); near(a.delta, b.delta)
    near(b.totalEntryCost, b.entryCost * 600); near(b.totalDelta, b.delta * 600)
    assert.deepEqual(a.breakEven, b.breakEven)
    assert.equal(b.totalRisk.maxLoss, b.risk.maxLoss * 600)
    assert.equal(b.totalRisk.maxProfit, b.risk.maxProfit * 600)
  }
  assert.equal(simulateStrategy('covered-call', { ...defaults, multiplier: 200, qty: 3 }).stockShares, 600)
})

test('blank, non-finite, wrong-type and invalid ranges are rejected without fallback zeros', () => {
  const { evaluateStrategy, simulateStrategy, blackScholes } = api()
  for (const key of Object.keys(defaults)) for (const bad of ['', '  ', null, undefined, false, [], {}, NaN, Infinity, -Infinity, 'abc']) {
    const state = evaluateStrategy('long-call', { ...defaults, [key]: bad })
    assert.equal(state.result, null, `${key}=${bad}`); assert.ok(state.error)
  }
  for (const values of [{ spot: -1 }, { lowStrike: 0 }, { midStrike: 2.8 }, { highStrike: 2.9 }, { days: -1 }, { vol: -1 }, { multiplier: 0 }, { qty: 1.2 }, { qty: 0 }, { multiplier: 1.2 }, { multiplier: Number.MAX_VALUE }, { rate: -1e308 }, { q: -1e308 }, { spot: 1e308 }]) {
    assert.throws(() => simulateStrategy('long-call', { ...defaults, ...values }), undefined, JSON.stringify(values))
  }
  assert.throws(() => simulateStrategy('unknown', defaults))
  for (const values of [{ type: 'other' }, { time: -1 }, { vol: -1 }, { q: Infinity }, { spot: '' }, { strike: 0 }]) assert.throws(() => blackScholes({ ...bsInput, type: 'call', ...values }))
  assert.equal(evaluateStrategy('long-call', Object.fromEntries(Object.entries(defaults).map(([k, v]) => [k, String(v)]))).error, '')
})

test('zero days/vol are accepted in simulation and unknown kink delta is not shown as zero', () => {
  const { evaluateStrategy } = api()
  for (const id of Object.keys(shapes)) for (const values of [{ days: 0 }, { vol: 0 }, { vol: 0, days: 0 }]) {
    const state = evaluateStrategy(id, { ...defaults, ...values })
    assert.equal(state.error, '', id); assert.ok(Number.isFinite(state.result.entryCost))
  }
  const r = evaluateStrategy('long-call', { ...defaults, days: 0 }).result
  assert.equal(r.delta, null); assert.equal(r.totalDelta, null)
})

test('strategy page reads real listed contracts and market premiums via api/strategy/market', () => {
  const source = readFileSync(new URL('../src/views/Strategy.vue', import.meta.url), 'utf8')
  // 新页面：左侧选真实挂牌合约 + 实际报价，不再是本地 mock 表单
  for (const text of [
    'api/strategy/market', 'api/expiries/', 'buildCustomStrategy', 'customStrategyAt',
    '合约单位', '报价', '盈亏平衡点', 'role="alert"', '到期盈亏曲线',
  ]) assert.ok(source.includes(text), `missing: ${text}`)
  // 不再要求本地 mock 假设
  assert.ok(!source.includes('mock / 模型模拟'))
  assert.ok(!source.includes('ACT/365'))
  assert.ok(!source.includes('v-else-if="state.result"'))
  // 页面脚本可以调用 fetch（数据来自后端市场端点）
  assert.ok(source.includes('fetch('), 'page should fetch market data')
})

test('route, navigation and footer separate model simulation from market provenance', () => {
  const main = readFileSync(new URL('../src/main.js', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  assert.match(main, /path: '\/strategy'/)
  assert.match(app, /to="\/strategy"[^>]*>策略模拟/)
  assert.ok(!app.includes('不提供模拟数据'))
  assert.ok(app.includes('策略模拟'))
})

// ── singleContract: one listed contract priced at its quoted premium ──
test('singleContract: break-even = strike ± premium; risk bounds scale by multiplier', () => {
  const { singleContract } = api()
  const call = singleContract({ type: 'call', strike: 3, premium: 0.2, multiplier: 10000 })
  assert.equal(call.breakEven.points.length, 1)
  near(call.breakEven.points[0], 3.2)
  near(call.risk.maxLoss, 0.2 * 10000)
  assert.equal(call.risk.maxProfit, Infinity)
  near(call.perUnitCost, 0.2 * 10000)
  assert.equal(call.premiumUsable, true)
  const put = singleContract({ type: 'put', strike: 3, premium: 0.15, multiplier: 10000 })
  near(put.breakEven.points[0], 2.85)
  near(put.risk.maxProfit, (3 - 0.15) * 10000)
  near(put.risk.maxLoss, 0.15 * 10000)
  const { singleContractAt } = api()
  // singleContractAt = P&L per unit (intrinsic payoff − premium) × contract unit
  // call: strike=3, premium=0.2 → payoff(3.1)=0.1-0.2=-0.1 → -1000
  // put:  strike=3, premium=0.15 → payoff(3.2)=0-0.15=-0.15 → -1500
  near(singleContractAt(call, 3.5), (3.5 - 3 - 0.2) * 10000)   // 1000
  near(singleContractAt(call, 3.1), -0.1 * 10000)               // -1000
  near(singleContractAt(put, 2.5), (3 - 2.5 - 0.15) * 10000)   // 3500
  near(singleContractAt(put, 3.2), -0.15 * 10000)              // -1500
})

test('singleContract: missing premium keeps contract identity but disables scaling and roots stay valid', () => {
  const { singleContract, singleContractAt } = api()
  const noPremium = singleContract({ type: 'call', strike: 3, premium: null, multiplier: 10000 })
  assert.equal(noPremium.premiumUsable, false)
  assert.equal(noPremium.perUnitCost, null)
  // entry cost treated as 0 → intrinsic payoff; per-unit values are 0-scale
  near(singleContractAt(noPremium, 5), 0)
  near(singleContractAt(noPremium, 1), 0)
})

test('singleContract: invalid inputs are rejected without fallback zeros', () => {
  const { singleContract } = api()
  assert.throws(() => singleContract({ type: 'other', strike: 3, premium: 1, multiplier: 100 }))
  assert.throws(() => singleContract({ type: 'call', strike: 0, premium: 1, multiplier: 100 }))
  assert.throws(() => singleContract({ type: 'call', strike: 3, premium: 'abc', multiplier: 100 }))
  assert.throws(() => singleContract({ type: 'call', strike: 3, premium: 1, multiplier: 0 }))
  assert.throws(() => singleContract({ type: 'call', strike: 3, premium: 1, multiplier: 1.5 }))
})

// Entry cost must be >= 0 for a long single leg. A "net credit" case belongs to
// short strategies (simulateStrategy), not singleContract.
test('singleContract: zero premium (ATM intrinsic 0) gives strike as the only root', () => {
  const { singleContract } = api()
  const zero = singleContract({ type: 'call', strike: 3, premium: 0, multiplier: 1000 })
  assert.deepEqual(zero.breakEven, { points: [], intervals: [[0, 3]] })
})

// ── buildCustomStrategy: multi-leg strategies from user-selected listed contracts ──
test('buildCustomStrategy: multi-leg bull call spread sums entry, risk and roots', () => {
  const { buildCustomStrategy, customStrategyAt } = api()
  // 买 3 张 strike=3 call（权利金 0.15），卖 2 张 strike=3.5 call（权利金 0.08）
  const legs = [
    { type: 'call', units: 3, strike: 3,   premium: 0.15, multiplier: 10000 },
    { type: 'call', units: -2, strike: 3.5, premium: 0.08, multiplier: 10000 },
  ]
  const r = buildCustomStrategy(legs)
  assert.equal(r.allUsable, true)
  // 每份标的净支出 = 3 × 0.15 − 2 × 0.08 = 0.29
  near(r.entryCost, 0.29)
  // 总权利金（每组合，元）= Σ units × premium × multiplier = 3×0.15×10000 − 2×0.08×10000 = 2900（净支出）
  near(r.totalEntryCost, 2900)
  // 风险（每组合）：
  //   S < 3:      P&L = 3×(S−3)×10000 − 2×(S−3.5)×10000 − 2900
  //              S=0 → 0 − 0 − 2900 = −2900
  //   3 ≤ S < 3.5: 斜率 +10000（净多头 1 张 call）
  //   S ≥ 3.5:    斜率 +10000，无界上升
  assert.equal(r.risk.maxProfit, Infinity)
  near(r.risk.maxLoss, 2900)
  assert.equal(r.risk.minPnl, -2900)
  assert.equal(r.risk.maxPnl, Infinity)
  // 盈亏平衡点（每份标的）：3 ≤ S < 3.5 段 3S − 9 − 0.29 = 0 → S = 3.0967
  assert.equal(r.breakEven.points.length, 1)
  near(r.breakEven.points[0], 9.29 / 3, 1e-9)
  // 情景盈亏（每组合，元）= 毛收益 − 总权利金
  near(customStrategyAt(r, 3.2), 3100)   // 3×0.2×10000 − 2×0×10000 − 2900 = 6000 − 2900
  near(customStrategyAt(r, 3.6), 13100)  // 3×0.6×10000 − 2×0.1×10000 − 2900 = 16000 − 2000 − 2900
})

test('buildCustomStrategy: missing premium keeps identity but disables scaling', () => {
  const { buildCustomStrategy, customStrategyAt } = api()
  const r = buildCustomStrategy([
    { type: 'call', units: 1, strike: 3, premium: 0.15, multiplier: 10000 },
    { type: 'put',  units: 1, strike: 3, premium: null,   multiplier: 10000 },
  ])
  assert.equal(r.allUsable, false)
  assert.equal(r.entryCost, null)
  assert.equal(r.totalEntryCost, null)
  assert.equal(customStrategyAt(r, 3.5), null)
})

test('buildCustomStrategy: invalid legs are rejected without fallback zeros', () => {
  const { buildCustomStrategy } = api()
  assert.throws(() => buildCustomStrategy([]))
  assert.throws(() => buildCustomStrategy([{ type: 'other', units: 1, strike: 3, premium: 0.1, multiplier: 100 }]))
  assert.throws(() => buildCustomStrategy([{ type: 'call', units: 1.5, strike: 3, premium: 0.1, multiplier: 100 }]))
  assert.throws(() => buildCustomStrategy([{ type: 'call', units: 1, strike: 0, premium: 0.1, multiplier: 100 }]))
  assert.throws(() => buildCustomStrategy([{ type: 'call', units: 1, strike: 3, premium: 'abc', multiplier: 100 }]))
  assert.throws(() => buildCustomStrategy([{ type: 'call', units: 1, strike: 3, premium: 0.1, multiplier: 0 }]))
})

test('buildCustomStrategy: short single call leg yields unbounded loss and finite max profit', () => {
  const { buildCustomStrategy } = api()
  // 卖 1 张 strike=3 call（权利金 0.2，合约单位 10000 股）→ 认购：亏损无界，盈利有限
  const r = buildCustomStrategy([{ type: 'call', units: -1, strike: 3, premium: 0.2, multiplier: 10000 }])
  assert.equal(r.risk.maxLoss, Infinity)
  assert.equal(r.risk.minPnl, -Infinity)
  // 最大盈利 = S→0 时 payoff = −(0 − 0.2) × (−1) × 10000 = 2000
  near(r.risk.maxProfit, 2000)
  near(r.risk.maxPnl, 2000)
})

test('buildCustomStrategy: covered call with stock leg is not supported (stock not a listed option leg)', () => {
  const { buildCustomStrategy } = api()
  assert.throws(() => buildCustomStrategy([{ type: 'stock', units: 1, strike: null, premium: null, multiplier: 10000 }]))
})
