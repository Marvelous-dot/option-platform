// Source IV is a percentage value passed through core/quotes.py unchanged.
// These are provider-computed, unverified analytics, never local implied-vol solves.
const positive = v => (typeof v === 'number' || (typeof v === 'string' && v.trim())) && Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : null
const sides = ['call', 'put']

export function formatIV(value) {
  const n = positive(value)
  return n === null ? '不可用' : `${Number(n.toFixed(4))}%`
}

export function chinaDay(now = new Date()) {
  return new Date(now.getTime() + 8 * 3600000).toISOString().slice(0, 10)
}

function sourceDay(ts) {
  if (typeof ts !== 'string') return null
  const m = ts.match(/^(\d{4})-?(\d{2})-?(\d{2})(?:[ T]|\d{6}$|$)/)
  if (!m) return null
  const day = `${m[1]}-${m[2]}-${m[3]}`
  const d = new Date(`${day}T00:00:00Z`)
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === day ? day : null
}

function freshness(item, ts, today) {
  if (item?.data_status === 'stale' || item?.freshness === 'stale') return 'stale'
  const day = sourceDay(ts)
  if (day && day !== today) return 'stale'
  if (!day || item?.freshness === 'unknown') return 'unknown'
  return 'fresh'
}

function coverage(rows) {
  const c = { total: rows.length, valid: 0, fresh: 0, stale: 0, unknown: 0, unavailable: 0, okQuotes: 0 }
  for (const r of rows) {
    if (r.data_status === 'ok') c.okQuotes++
    if (r.ivValue === null) c.unavailable++
    else { c.valid++; c[r.ivStatus]++ }
  }
  return c
}

function atmFor(rows, strikes, today) {
  const spots = rows.map(r => r.spot)
  let spotStatus = 'unavailable', spot = spots[0] || null, strike = null
  if (spots.length && spots.every(s => positive(s?.price) !== null && s?.data_status !== 'unavailable')) {
    if (spots.some(s => Number(s.price) !== Number(spot.price))) spotStatus = 'ambiguous'
    else {
      const statuses = spots.map(s => freshness(s, s.market_time, today))
      spotStatus = statuses.includes('stale') ? 'stale' : statuses.includes('unknown') ? 'unknown' : 'fresh'
      // Choose from all listed strikes BEFORE checking side or IV availability.
      strike = strikes.reduce((best, k) => best === null || Math.abs(k - spot.price) < Math.abs(best - spot.price) - 1e-12 ? k : best, null)
    }
  }
  const atm = { strike, spot, spotStatus }
  for (const side of sides) {
    const candidates = strike === null ? [] : rows.filter(r => r.option_type === side && r.strikeValue === strike)
    const status = candidates.length > 1 ? 'ambiguous' : candidates.length === 1 && candidates[0].ivValue !== null ? 'available' : 'unavailable'
    const r = candidates[0]
    const ivStatus = status !== 'available' ? 'unavailable'
      : r.ivStatus === 'stale' || spotStatus === 'stale' ? 'stale'
      : r.ivStatus === 'unknown' || spotStatus === 'unknown' ? 'unknown' : 'fresh'
    atm[side] = { status, codes: candidates.map(r => r.option_code), ivValue: status === 'available' ? r.ivValue : null, ivStatus }
  }
  return atm
}

export function buildVolatility(payload, today = chinaDay()) {
  const rows = (Array.isArray(payload?.rows) ? payload.rows : []).map(r => {
    const ivValue = ['ok', 'stale'].includes(r.data_status) ? positive(r.iv) : null
    return { ...r, strikeValue: positive(r.strike), ivValue,
      ivStatus: ivValue === null ? 'unavailable' : freshness(r, r.market_ts, today) }
  }).sort((a, b) => String(a.expiry).localeCompare(String(b.expiry))
    || (a.strikeValue ?? Infinity) - (b.strikeValue ?? Infinity)
    || String(a.option_code).localeCompare(String(b.option_code)))
  const expiries = [...new Set(rows.map(r => r.expiry).filter(Boolean))].sort()
  const groups = expiries.map(expiry => {
    const groupRows = rows.filter(r => r.expiry === expiry)
    const strikes = [...new Set(groupRows.map(r => r.strikeValue).filter(k => k !== null))].sort((a, b) => a - b)
    return { expiry, rows: groupRows, strikes, coverage: coverage(groupRows), atm: atmFor(groupRows, strikes, today),
      series: sides.map(side => ({ side, slots: strikes.map(x => ({ x, label: String(x),
        points: groupRows.filter(r => r.option_type === side && r.strikeValue === x) })) })) }
  })
  const termSeries = sides.map(side => ({ side, slots: groups.map(g => ({
    x: sourceDay(g.expiry) ? Date.parse(`${g.expiry}T00:00:00Z`) / 86400000 : null,
    label: g.expiry, points: [{ ...g.atm[side], option_code: g.atm[side].codes.join(' / '), strike: g.atm.strike }],
  })) }))
  return { rows, expiries, groups, coverage: coverage(rows), termSeries }
}

// Minimum-gap decimation for x-axis labels: keep the first tick, then greedily
// keep any tick far enough from the last kept one, and always keep the last
// tick (so the furthest strike is still labeled even when dense).
// Returns a monotonic subset of `ticks` (same objects, same order).
function pickTicks(ticks, minGap) {
  if (ticks.length < 2 || minGap <= 0) return ticks
  const kept = [ticks[0]]
  let last = ticks[0]
  for (let i = 1; i < ticks.length - 1; i++) {
    const t = ticks[i]
    if (Math.abs(t.x - last.x) >= minGap) {
      kept.push(t)
      last = t
    }
  }
  const tail = ticks[ticks.length - 1]
  if (kept[kept.length - 1] !== tail) kept.push(tail)
  return kept
}

// Shared SVG geometry: actual x spacing, no interpolation across absent/ambiguous slots.
// Multiple contracts at a strike remain separate points, with no arbitrary joining.
export function plotSeries(series, { minGap = 0, fontSize = 9 } = {}) {
  const xs = series.flatMap(s => s.slots.map(s => s.x)).filter(Number.isFinite)
  const ys = series.flatMap(s => s.slots.flatMap(s => s.points.map(p => p.ivValue))).filter(v => positive(v) !== null)
  const minX = xs.length ? Math.min(...xs) : 0, maxX = xs.length ? Math.max(...xs) : 1
  const minY = ys.length ? Math.min(...ys) : 0, maxY = ys.length ? Math.max(...ys) : 1
  const padding = Math.max((maxY - minY) * .12, maxY * .02, .01)
  const yLow = Math.max(0, minY - padding), yHigh = maxY + padding
  const x = v => maxX === minX ? 325 : 65 + (v - minX) / (maxX - minX) * 520
  const y = v => 245 - (v - yLow) / (yHigh - yLow) * 210
  const rawTicks = [...new Map(series.flatMap(s => s.slots).filter(s => Number.isFinite(s.x)).map(s => [s.x, { x: x(s.x), label: s.label }])).values()]
  // 窄容器下保持最小水平间距：等距序列从两端向中间隔位取舍，保证首尾标签保留且不重叠
  const ticks = rawTicks.length > 1 && minGap > 0
    ? pickTicks(rawTicks, minGap)
    : rawTicks
  return {
    ticks, yTicks: [yLow, (yLow + yHigh) / 2, yHigh].map(value => ({ value, y: y(value) })),
    series: series.map(s => {
      const points = [], segments = []
      let previous = null
      for (const slot of s.slots) {
        const valid = Number.isFinite(slot.x) ? slot.points.filter(p => positive(p.ivValue) !== null) : []
        const positioned = valid.map(p => ({ ...p, x: x(slot.x), y: y(p.ivValue), label: slot.label }))
        points.push(...positioned)
        const current = slot.points.length === 1 && positioned.length === 1 ? positioned[0] : null
        if (previous && current && previous.ivStatus === current.ivStatus) segments.push(`${previous.x},${previous.y} ${current.x},${current.y}`)
        previous = current
      }
      return { side: s.side, points, segments }
    }),
  }
}
