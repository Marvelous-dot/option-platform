import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// Pure helpers stay in the SFC to keep the change scoped to this page.
const source = readFileSync(new URL('../src/views/Kline.vue', import.meta.url), 'utf8')
const helpers = source.match(/\/\/ Pure helpers start([\s\S]*?)\/\/ Pure helpers end/)
assert.ok(helpers, 'Kline.vue must expose its pure calculation section')
const { normalizeBars, chartGeometry, indexAt, formatPrice, formatVolume, adjustmentLabel, movingAverage } = new Function(`${helpers[1]}; return { normalizeBars, chartGeometry, indexAt, formatPrice, formatVolume, adjustmentLabel, movingAverage }`)()
const bar = { date: '2026-09-17', open: 3, close: 3.2, high: 3.3, low: 2.9, volume: 12000 }

test('missing volume is retained as null, while genuine zero is retained', () => {
  const rows = normalizeBars([{ ...bar, volume: null }, { ...bar, volume: 0 }, { ...bar, volume: '' }])
  assert.deepEqual(rows.map(r => r.volume), [null, 0, null])
  assert.equal(formatVolume(null), '不可用')
  assert.equal(formatVolume(0), '0')
  assert.equal(formatVolume(12000), '12000')
})

test('sorts without mutating input, keeps incomplete candles as visible gaps', () => {
  const input = [{ ...bar, date: '2026-09-18', high: null }, bar]
  const rows = normalizeBars(input)
  assert.equal(rows[0].date, bar.date)
  assert.equal(input[0].date, '2026-09-18')
  assert.equal(rows.length, 2)
  assert.equal(rows[1].validPrice, false)
  assert.equal(rows[0].validPrice, true)
  assert.equal(normalizeBars([{ ...bar, high: 2 }])[0].validPrice, false)
})

test('non-finite and blank prices never become zero', () => {
  for (const value of [null, undefined, '', ' ', NaN, Infinity, false]) assert.equal(formatPrice(value), '不可用')
  assert.equal(formatPrice(3.2), '3.2000')
  assert.equal(normalizeBars([{ ...bar, open: '' }])[0].open, null)
})

test('geometry supports flat prices, single candle, empty and all-missing data', () => {
  const rows = normalizeBars([{ ...bar, open: 3, close: 3, high: 3, low: 3, volume: null }])
  const g = chartGeometry(rows, 320, 360)
  assert.ok(g.max > 3 && g.min < 3)
  assert.equal(g.volumeMax, null)
  assert.ok(g.step > 0 && Number.isFinite(g.step))
  assert.equal(chartGeometry([], 320, 360), null)
  const gaps = chartGeometry(normalizeBars([{ ...bar, high: null }]), 320, 360)
  assert.equal(gaps.hasPrices, false)
  assert.equal(chartGeometry(normalizeBars([{ ...bar, volume: 0 }]), 320, 360).volumeMax, 0)
})

test('crosshair index clamps to candle bounds on narrow mobile charts', () => {
  const g = chartGeometry(normalizeBars([bar, bar]), 320, 360)
  assert.equal(indexAt(-100, g, 2), 0)
  assert.equal(indexAt(9999, g, 2), 1)
  assert.equal(indexAt(g.left + g.step * 1.5, g, 2), 1)
  assert.equal(indexAt(20, null, 0), -1)
})

test('adjustment accepts both documented qfq formats and preserves unknown values', () => {
  assert.equal(adjustmentLabel('qfq'), '前复权（qfq）')
  assert.equal(adjustmentLabel('qfq(前复权)'), '前复权（qfq）')
  assert.equal(adjustmentLabel(null), '口径未知')
  assert.equal(adjustmentLabel('hfq'), 'hfq')
})

 test('route and primary navigation expose the page', () => {
  assert.match(readFileSync(new URL('../src/main.js', import.meta.url), 'utf8'), /path: '\/kline'/)
  assert.match(readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8'), /to="\/kline"[^>]*>标的K线/)
})

test('movingAverage returns window-aligned closes, leaving insufficient history as null', () => {
  const closes = [1, 2, 3, 4, 5, 6]
  // MA5: first 4 bars have <5 samples -> null; bar5=(1..5)/5; bar6=(2..6)/5
  assert.deepEqual(movingAverage(closes, 5), [null, null, null, null, 3, 4])
  // MA1 = identity
  assert.deepEqual(movingAverage(closes, 1), [1, 2, 3, 4, 5, 6])
  // larger than array -> all null
  assert.deepEqual(movingAverage(closes, 99), [null, null, null, null, null, null])
})

test('movingAverage skips missing closes (gap-safe), no zero-fill, null window', () => {
  // close missing at index 2 -> MA3 at idx3 uses idx1,2,3 but 2 is null => null (no imputation)
  const closes = [2, 4, null, 6, 8]
  assert.deepEqual(movingAverage(closes, 3), [null, null, null, null, null])
  // a gap earlier does not poison later full windows
  const closes2 = [null, 10, 20, 30, 40, 50]
  const ma = movingAverage(closes2, 3)
  assert.equal(ma[2], null)  // window [null,10,20] incomplete
  assert.equal(ma[3], (10 + 20 + 30) / 3)
  assert.equal(ma[4], (20 + 30 + 40) / 3)
  assert.equal(ma[5], (30 + 40 + 50) / 3)
})

 test('source retains provenance, missing data, request and drawing safeguards', () => {
  for (const marker of ['getComputedStyle', 'AbortController', 'ResizeObserver', 'onUnmounted', 'cancelAnimationFrame', '/api/targets', '/api/kline/', '原始单位', '盘中末根日K可能尚未收盘，获取时间不代表行情时间']) assert.ok(source.includes(marker), marker)
  assert.ok(!source.includes('实时'))
})
