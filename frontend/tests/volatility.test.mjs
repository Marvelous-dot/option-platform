import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, computed, watch } from 'vue'

// Synthetic fixtures only: never feed these values into production.
const engine = await import('../src/utils/volatility.mjs').catch(() => null)
const api = () => { assert.ok(engine, 'missing volatility module'); return engine }
const today = '2026-09-18'
const row = (strike, iv, extra = {}) => ({
  option_code: `C${strike}`, contract_id: `id${strike}`, option_type: 'call',
  expiry: '2026-09-23', strike, iv, data_status: 'ok', freshness: 'fresh',
  source: 'sina', market_ts: '2026-09-18 14:00:00', fetched_at: '2026-09-18T14:01:00+08:00',
  spot: { price: 3, market_time: '20260918140000', source: 'tencent' }, ...extra,
})
const build = (rows, extra = {}) => api().buildVolatility({ rows, ...extra }, today)

test('smile sorts actual listed strikes and preserves missing positions and side gaps', () => {
  const m = build([row(3.2, 24), row(3, null), row(2.8, 20), row(3.1, 22, { option_type: 'put' })])
  const g = m.groups[0]
  assert.deepEqual(g.strikes, [2.8, 3, 3.1, 3.2])
  assert.deepEqual(g.series[0].slots.map(s => s.points.map(p => p.ivValue)), [[20], [null], [], [24]])
  const chart = api().plotSeries(g.series)
  assert.equal(chart.series[0].points.length, 2)
  assert.deepEqual(chart.series[0].segments, [])
  assert.equal(chart.series[1].points.length, 1)
})

test('source IV percent units are unchanged, never multiplied by 100', () => {
  assert.equal(build([row(3, .4022)]).rows[0].ivValue, .4022)
  assert.equal(api().formatIV(.4022), '0.4022%')
  assert.equal(api().formatIV(21.5), '21.5%')
})

test('missing, empty, nonfinite, boolean, negative and zero IV are invalid without filling', () => {
  for (const iv of [null, undefined, '', ' ', NaN, Infinity, -Infinity, -1, 0, '0', false, 'NaN']) {
    const m = build([row(3, iv)])
    assert.equal(m.rows[0].ivValue, null, `invalid ${iv}`)
    assert.equal(m.coverage.valid, 0)
    assert.equal(api().formatIV(iv), '不可用')
    assert.equal(api().plotSeries(m.groups[0].series).series[0].points.length, 0)
  }
})

test('coverage is valid IV / listed rows, not ok quotes; stale and unknown are not fresh', () => {
  const m = build([
    row(2.7, 20), row(2.8, null), row(2.9, 21, { data_status: 'stale' }),
    row(3, 22, { freshness: 'stale' }), row(3.1, 23, { freshness: 'unknown', market_ts: null }),
    row(3.2, 24, { data_status: 'unavailable' }),
    row(3.3, 25, { market_ts: '2026-09-17 14:00:00' }),
    row(3.4, 26, { market_ts: null }),
  ])
  assert.deepEqual(m.coverage, { total: 8, valid: 6, fresh: 1, stale: 3, unknown: 2, unavailable: 2, okQuotes: 6 })
  assert.equal(m.rows.find(r => r.strike === 3.2).ivValue, null)
  assert.equal(m.rows.find(r => r.strike === 2.9).ivStatus, 'stale')
})

test('ATM chooses nearest listed strike first, tie lower; missing IV must not jump farther', () => {
  const m = build([row(2, null, { spot: { price: 3 } }), row(4, 25, { spot: { price: 3 } })])
  assert.equal(m.groups[0].atm.strike, 2)
  assert.equal(m.groups[0].atm.call.ivValue, null)
  assert.equal(m.groups[0].atm.call.status, 'unavailable')
  assert.deepEqual(m.groups[0].atm.call.codes, ['C2'])
})

test('ATM is selected per expiry using its own spot, includes all expiries even without IV', () => {
  const m = build([row(2.8, 20), row(3, 21),
    row(2.8, 22, { expiry: '2026-10-28', spot: { price: 2.81 } }),
    row(3, 23, { expiry: '2026-10-28', spot: { price: 2.81 } }),
    row(3, null, { expiry: '2026-12-23' })])
  assert.deepEqual(m.expiries, ['2026-09-23', '2026-10-28', '2026-12-23'])
  assert.deepEqual(m.groups.map(g => g.atm.strike), [3, 2.8, 3])
  assert.deepEqual(m.termSeries[0].slots.map(s => s.points[0].ivValue), [21, 22, null])
})

test('adjusted duplicate strike contracts are retained, never overwritten/averaged; ATM ambiguous', () => {
  const m = build([row(2.8, 19), row(3, 20), row(3, 30, { option_code: 'adjusted', contract_id: 'adj' }), row(3.2, 21),
    row(3, 22, { option_type: 'put', option_code: 'P3' })])
  const g = m.groups[0]
  assert.equal(m.rows.length, 5)
  assert.deepEqual(g.atm.call.codes, ['adjusted', 'C3'])
  assert.equal(g.atm.call.status, 'ambiguous')
  assert.equal(g.atm.call.ivValue, null)
  assert.equal(g.atm.put.ivValue, 22)
  const chart = api().plotSeries(g.series)
  assert.equal(chart.series[0].points.length, 4)
  assert.deepEqual(chart.series[0].segments, [])
})

test('plotSeries minGap decimates dense x labels, keeping first and last', () => {
  const rowAt = (strike, iv) => ({ option_code: `C${strike}`, contract_id: `id${strike}`, option_type: 'call',
    expiry: '2026-09-23', strike, iv, data_status: 'ok', freshness: 'fresh',
    source: 'sina', market_ts: '2026-09-18 14:00:00', fetched_at: '2026-09-18T14:01:00+08:00',
    spot: { price: 3.1, market_time: '20260918140000', source: 'tencent' } })
  // 14 等距行权价：默认（minGap=0）全部保留标签
  const rows = [2.65, 2.7, 2.75, 2.8, 2.85, 2.9, 2.95, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6].map(s => rowAt(s, 20))
  const full = api().plotSeries(api().buildVolatility({ rows }, today).groups[0].series)
  assert.equal(full.ticks.length, 14)
  // minGap 抽稀：首尾保留，中间标签间距 >= 46 SVG 单位
  const dense = api().plotSeries(api().buildVolatility({ rows }, today).groups[0].series, { minGap: 46 })
  assert.ok(dense.ticks.length < 14, `expected decimation, got ${dense.ticks.length}`)
  assert.equal(dense.ticks[0].label, '2.65')
  assert.equal(dense.ticks[dense.ticks.length - 1].label, '3.6')
  for (let i = 1; i < dense.ticks.length; i++) {
    const gap = Math.abs(dense.ticks[i].x - dense.ticks[i - 1].x)
    assert.ok(gap >= 46, `gap ${gap} < 46 between ${dense.ticks[i - 1].label} and ${dense.ticks[i].label}`)
  }
  // 点数/折线不受抽稀影响
  assert.deepEqual(dense.series.map(s => s.points.length), full.series.map(s => s.points.length))
  // 少量标签（<2）不抽稀
  const few = api().plotSeries([{ side: 'call', slots: [{ x: 3, label: '3', points: [] }] }], { minGap: 46 })
  assert.equal(few.ticks.length, 1)
})

test('ATM spot missing/invalid cannot select a strike or silently coerce zero', () => {
  for (const spot of [null, {}, { price: null }, { price: '' }, { price: NaN }, { price: Infinity }, { price: 0 }, { price: -1 }]) {
    const atm = build([row(3, 20, { spot })]).groups[0].atm
    assert.equal(atm.strike, null)
    assert.equal(atm.spotStatus, 'unavailable')
    assert.equal(atm.call.ivValue, null)
  }
})

test('spot stale allows labelled historical ATM, unknown time never means fresh; inconsistent spots unavailable', () => {
  const old = build([row(3, 20, { spot: { price: 3, market_time: '20260917140000' } })]).groups[0].atm
  assert.equal(old.spotStatus, 'stale')
  assert.equal(old.call.ivStatus, 'stale')
  assert.equal(old.call.ivValue, 20)
  const unknown = build([row(3, 20, { spot: { price: 3 } })]).groups[0].atm
  assert.equal(unknown.spotStatus, 'unknown')
  assert.equal(unknown.call.ivStatus, 'unknown')
  const inconsistent = build([row(3, 20), row(4, 25, { spot: { price: 4 } })]).groups[0].atm
  assert.equal(inconsistent.spotStatus, 'ambiguous')
  assert.equal(inconsistent.strike, null)
})

test('adjacent valid points connect but stale/fresh changes break, invalid strikes never become zero', () => {
  const m = build([row(2.8, 20), row(3, 21), row(3.2, 22, { data_status: 'stale' }), row(null, 24)])
  const chart = api().plotSeries(m.groups[0].series)
  assert.equal(chart.series[0].segments.length, 1)
  assert.equal(chart.series[0].points.length, 3)
  assert.ok(chart.series[0].points.every(p => Number.isFinite(p.x) && Number.isFinite(p.y)))
  assert.deepEqual(m.groups[0].strikes, [2.8, 3, 3.2])
})

test('empty payload is empty and calculations do not mutate inputs', () => {
  const rows = [row(3.2, 23), row(3, null), row(2.8, 21)]
  const before = structuredClone(rows)
  const freeze = o => { if (o && typeof o === 'object') { Object.values(o).forEach(freeze); Object.freeze(o) }; return o }
  const m = build(freeze(rows))
  api().plotSeries(m.groups[0].series)
  assert.deepEqual(rows, before)
  assert.deepEqual(build([]).groups, [])
  assert.equal(build([]).coverage.total, 0)
  assert.deepEqual(api().plotSeries([]).series, [])
})

function pageHarness(fetch) {
  const path = new URL('../src/views/Volatility.vue', import.meta.url)
  let source = ''; try { source = readFileSync(path, 'utf8') } catch {}
  assert.ok(source, 'missing volatility page')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  let unmount
  const names = Object.keys(api())
  // Stubs for the remember helpers the SFC references; memory is out of scope for unit tests.
  const readState = (_page, fallback) => fallback
  const writeState = () => {}
  return new Function('ref', 'computed', 'onMounted', 'onUnmounted', 'watch', 'fetch', 'readState', 'writeState', ...names,
    script + '\nreturn {target, expiry, data, loading, error, model, selected, load, changeTarget, dispose: () => cleanup()}')(
      ref, computed, () => {}, cb => { unmount = cb }, watch, fetch, readState, writeState, ...names.map(k => api()[k]))
}
const deferredFetch = () => {
  const requests = []
  const fetch = (url, opts) => new Promise((resolve, reject) => requests.push({ url, opts, resolve, reject }))
  const reply = (i, rows, ok = true) => requests[i].resolve({ ok, status: ok ? 200 : 503, json: async () => ({ rows, detail: '测试失败' }) })
  return { fetch, requests, reply }
}

test('page target change synchronously clears old data, aborts pending and ignores late success', async () => {
  const f = deferredFetch(), p = pageHarness(f.fetch)
  let pending = p.load(); f.reply(0, [row(3, 20)]); await pending
  assert.equal(p.model.value.coverage.total, 1)
  pending = p.load()
  p.target.value = '588080'; p.expiry.value = '2026-10-28'
  const latest = p.changeTarget()
  assert.equal(p.data.value, null)
  assert.equal(p.model.value.coverage.total, 0)
  assert.equal(p.expiry.value, '')
  assert.equal(f.requests[1].opts.signal.aborted, true)
  assert.match(f.requests[2].url, /\/api\/quotes\/588080/)
  f.reply(2, [row(3.2, 24)]); await latest
  f.reply(1, [row(3, 99)]); await pending
  assert.equal(p.model.value.rows[0].ivValue, 24)
  assert.equal(p.loading.value, false)
})

test('page late errors cannot override new request; error/empty/invalid response never retains chart', async () => {
  const f = deferredFetch(), p = pageHarness(f.fetch)
  const old = p.load(), latest = p.load()
  f.requests[0].reject(new Error('late')); await old
  assert.equal(p.error.value, '')
  assert.equal(p.loading.value, true)
  f.reply(1, [row(3, 20)]); await latest
  const failed = p.load(); assert.equal(p.selected.value, null)
  f.reply(2, [], false); await failed
  assert.match(p.error.value, /测试失败/)
  assert.equal(p.selected.value, null)
  const empty = p.load(); f.reply(3, []); await empty
  assert.equal(p.error.value, '')
  assert.equal(p.selected.value, null)
  const malformed = p.load(); f.reply(4, null); await malformed
  assert.ok(p.error.value)
  assert.equal(p.selected.value, null)
})

test('expiry computed switches without retained series; unmount invalidates outstanding request', async () => {
  const f = deferredFetch(), p = pageHarness(f.fetch)
  const first = p.load(); f.reply(0, [row(3, 20), row(3, null, { expiry: '2026-10-28' })]); await first
  p.expiry.value = '2026-10-28'
  assert.equal(p.selected.value.series[0].slots[0].points[0].ivValue, null)
  p.expiry.value = 'missing'
  assert.equal(p.selected.value, null)
  const pending = p.load(); p.dispose()
  assert.equal(f.requests[1].opts.signal.aborted, true)
  f.reply(1, [row(3, 99)]); await pending
  assert.equal(p.data.value, null)
})

test('page exposes required source boundaries, SVG, responsive layout and navigation', () => {
  const p = readFileSync(new URL('../src/views/Volatility.vue', import.meta.url), 'utf8')
  for (const text of ['数据源计算', '口径未核验', '不能推断有效0IV', '历史IV', 'IV与K线叠加', '3D', '暂不可用', '<svg', '<circle', '<polyline', '/contract/', '@media', 'market_ts', 'fetched_at']) assert.ok(p.includes(text), text)
  assert.match(readFileSync(new URL('../src/main.js', import.meta.url), 'utf8'), /path: '\/volatility'/)
  assert.match(readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8'), /to="\/volatility"/)
})
