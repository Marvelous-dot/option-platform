<template>
  <section class="kline-page">
    <div class="page-head">
      <div class="ph-title">
        <span class="ph-kicker">CANDLESTICK · 日K / 分钟K</span>
        <h1>标的 K 线</h1>
        <p class="ph-desc">红涨绿跌（收盘对比开盘）；日 K 落盘缓存可回看历史，分钟 K（5/15/30/60 分）为盘中数据、不复权、仅近期根数。末根可能尚未收盘。</p>
      </div>
      <div class="ph-actions">
        <button v-for="[p, label] in PERIODS" :key="p" type="button" class="range-btn"
          :class="{ active: period === p }" :aria-pressed="period === p" @click="setPeriod(p)">{{ label }}</button>
        <button v-for="d in rangeOptions" :key="d" type="button" class="range-btn"
          :class="{ active: days === d }" :aria-pressed="days === d" @click="days = d">{{ period === 'day' ? d + '日' : d + '根' }}</button>
        <button type="button" class="refresh-btn" :disabled="loading || !target" @click="load">{{ loading ? '加载中…' : '刷新' }}</button>
      </div>
    </div>
    <div class="controls" role="group" aria-label="选择标的">
      <div class="target-tabs">
        <button v-for="t in targets" :key="t.target" type="button" class="tab"
          :class="{ active: target === t.target }" :aria-pressed="target === t.target" @click="target = t.target">
          <span class="tab-code">{{ t.target }}</span><span class="tab-name">{{ t.name }}</span>
        </button>
      </div>
    </div>
    <p v-if="targetLoading" class="note" role="status">正在获取标的目录…</p>
    <p v-if="targetError" role="alert">{{ targetError }} <button type="button" @click="loadTargets">重试目录</button></p>
    <div class="statusbar" :class="loading ? 'loading' : data?.data_status === 'ok' ? 'ok' : 'unavailable'" role="status">
      <span class="status-dot"></span>
      <span class="status-text">{{ loading ? 'K线加载中…' : data?.data_status === 'ok' ? 'K线数据可用' : 'K线不可用' }}</span>
      <span v-if="data">{{ data.status_detail || '数据源未提供状态说明' }}</span>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="data" class="provenance">
      <p>{{ data.target_name || '名称未知' }} · {{ data.target_code || target }} · 来源：{{ data.source || '未知' }} · {{ adjustmentLabel(data.adjust) }} · 获取时间 {{ data.fetched_at || '未知' }}</p>
      <p>末根时间 {{ data.last_date || '未知' }} · 末根收盘字段 {{ formatPrice(data.last_close) }}（可能仍变动）· 源返回 {{ data.count ?? '未知' }} 根 / 请求 {{ rangeLabel }}，图中 {{ bars.length }} 根，按返回时间排列，不填补缺失。</p>
    </div>
    <p v-if="missingPrices || missingVolumes" class="missing" role="status">{{ missingPrices }} 根价格缺失或异常；{{ missingVolumes }} 根成交量不可用。保留日期位置，不绘制伪造柱。</p>
    <div class="chart-card">
      <div class="chart-top">
        <p class="ma-legend">
          <span v-for="p in MA_PERIODS" :key="p" class="ma-chip" :class="'ma-' + p">MA{{ p }}</span>
        </p>
        <dl class="ohlc" aria-live="off">
          <div><dt>{{ dateLabel }}</dt><dd>{{ activeBar?.date || '不可用' }}</dd></div>
          <div v-for="[key, label] in priceFields" :key="key"><dt>{{ label }}</dt><dd>{{ formatPrice(activeBar?.[key]) }}</dd></div>
          <div><dt>成交量</dt><dd>{{ formatVolume(activeBar?.volume) }}</dd></div>
          <div v-for="(p, k) in MA_PERIODS" :key="p"><dt>MA{{ p }}</dt><dd>{{ activeMA[k] == null ? '不可用' : Number(activeMA[k]).toFixed(4) }}</dd></div>
        </dl>
      </div>
      <p v-if="activeBar && !activeBar.validPrice" class="missing">本根 OHLC 不完整或范围异常，蜡烛不可用。</p>
      <div ref="chartHost" class="chart-host" :aria-busy="loading">
        <canvas ref="canvas" v-show="bars.length" tabindex="0" role="img"
          aria-label="标的K线蜡烛与成交量图。移动鼠标、触摸或使用左右方向键查看逐根开高低收。"
          @pointermove="moveCrosshair" @pointerdown="moveCrosshair" @pointerleave="clearCrosshair"
          @keydown.left.prevent="stepCrosshair(-1)" @keydown.right.prevent="stepCrosshair(1)" @blur="clearCrosshair"></canvas>
        <div v-if="!bars.length" class="empty">
          <p class="empty-title">{{ loading ? '正在获取当前条件的K线…' : '暂无可绘制的K线' }}</p>
          <p class="empty-detail">{{ error || data?.status_detail || '数据缺失时不展示模拟行情。' }}</p>
        </div>
      </div>
      <p class="note chart-hint">均线按收盘价本地计算，窗口内缺失收盘则断线不补值；成交量使用原始单位；分钟K不复权、数据源仅提供近期根数。移动鼠标 / 触摸 / 左右方向键查看开高低收，默认详情为末根（未确认收盘）。</p>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { readState, writeState } from '../utils/remember.mjs'

// Pure helpers start
function finiteNumber(value) {
  if (typeof value !== 'number' && typeof value !== 'string') return null
  if (typeof value === 'string' && !value.trim()) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}
function formatPrice(value) {
  const n = finiteNumber(value)
  return n === null ? '不可用' : n.toFixed(4)
}
function formatVolume(value) {
  const n = finiteNumber(value)
  return n === null || n < 0 ? '不可用' : String(n)
}
function adjustmentLabel(value) {
  return /^qfq(?:$|[（(])/.test(value || '') ? '前复权（qfq）' : value || '口径未知'
}
function normalizeBars(input) {
  if (!Array.isArray(input)) return []
  return input.map(row => {
    const b = { date: row?.date || '日期未知' }
    for (const key of ['open', 'close', 'high', 'low', 'volume']) b[key] = finiteNumber(row?.[key])
    if (b.volume !== null && b.volume < 0) b.volume = null
    b.validPrice = ['open', 'close', 'high', 'low'].every(key => b[key] !== null && b[key] > 0)
      && b.high >= Math.max(b.open, b.close) && b.low <= Math.min(b.open, b.close)
    return b
  }).sort((a, b) => String(a.date).localeCompare(String(b.date)))
}
function chartGeometry(rows, width, height) {
  if (!rows.length || width <= 0 || height <= 0) return null
  const prices = rows.filter(b => b.validPrice)
  const volumes = rows.map(b => b.volume).filter(v => v !== null)
  let min = prices.length ? Math.min(...prices.map(b => b.low)) : 0
  let max = prices.length ? Math.max(...prices.map(b => b.high)) : 1
  const padding = Math.max((max - min) * .08, max * .005, .0001)
  min -= padding; max += padding
  const left = width < 500 ? 58 : 72, right = width - 12
  return { left, right, top: 18, bottom: height * .65, volumeTop: height * .73,
    volumeBottom: height - 30, min, max, hasPrices: prices.length > 0,
    volumeMax: volumes.length ? Math.max(...volumes) : null,
    step: Math.max(1, right - left) / rows.length }
}
function indexAt(x, geometry, count) {
  if (!geometry || !count) return -1
  return Math.max(0, Math.min(count - 1, Math.floor((x - geometry.left) / geometry.step)))
}
// Simple moving average of closes, aligned so output[i] is the mean of
// closes[i-win+1 .. i]. A window that contains any missing close (null)
// yields null — we never impute or zero-fill, consistent with the
// "no fabricated data" rule.
function movingAverage(closes, win) {
  if (!Array.isArray(closes) || !(Number.isInteger(win) && win > 0)) return []
  const out = new Array(closes.length).fill(null)
  for (let i = win - 1; i < closes.length; i++) {
    let sum = 0
    for (let k = i - win + 1; k <= i; k++) {
      const v = closes[k]
      if (typeof v !== 'number' || !Number.isFinite(v)) { sum = null; break }
      sum += v
    }
    if (sum !== null) out[i] = sum / win
  }
  return out
}
// Pure helpers end

const klineRemembered = readState('kline', {})
const targets = ref([]), target = ref(klineRemembered.target || ''), days = ref(klineRemembered.days || 120)
const PERIODS = [['day', '日K'], ['5m', '5分'], ['15m', '15分'], ['30m', '30分'], ['60m', '60分']]
const period = ref(klineRemembered.period || 'day')
const rangeOptions = computed(() => period.value === 'day' ? [60, 120, 250] : [96, 240, 480])
const rangeLabel = computed(() => period.value === 'day' ? `${days.value}日` : `${days.value}根`)
const dateLabel = computed(() => period.value === 'day' ? '日期' : '时间')
function setPeriod(p) {
  if (period.value === p) return
  period.value = p
  const opts = p === 'day' ? [60, 120, 250] : [96, 240, 480]
  if (!opts.includes(days.value)) days.value = p === 'day' ? 120 : 240
}
const data = ref(null), loading = ref(false), error = ref('')
const targetLoading = ref(false), targetError = ref('')
const chartHost = ref(null), canvas = ref(null), hovered = ref(-1)
const priceFields = [['open', '开'], ['high', '高'], ['low', '低'], ['close', '收']]
const bars = computed(() => data.value?.data_status === 'ok' ? normalizeBars(data.value.bars) : [])
const activeBar = computed(() => bars.value[hovered.value >= 0 ? hovered.value : bars.value.length - 1])
const missingPrices = computed(() => bars.value.filter(b => !b.validPrice).length)
const missingVolumes = computed(() => bars.value.filter(b => b.volume === null).length)
const MA_PERIODS = [5, 20, 60]
const closes = computed(() => bars.value.map(b => b.close))
const mas = computed(() => MA_PERIODS.map(p => movingAverage(closes.value, p)))
const activeMA = computed(() => {
  const i = hovered.value >= 0 ? hovered.value : bars.value.length - 1
  return i >= 0 ? MA_PERIODS.map((p, k) => mas.value[k][i]) : []
})
let controller, targetController, sequence = 0, targetSequence = 0, disposed = false
let resizeObserver, themeObserver, frame = null, geometry = null, pointerY = null
// 记住 K线页选中的标的、周期与根数范围
watch([target, days, period], () => {
  if (!target.value) return
  writeState('kline', { target: target.value, days: days.value, period: period.value })
}, { immediate: false })

async function loadTargets() {
  const id = ++targetSequence
  targetController?.abort()
  targetController = new AbortController()
  targetLoading.value = true; targetError.value = ''
  try {
    const res = await fetch('/api/targets', { signal: targetController.signal })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const result = await res.json()
    if (id !== targetSequence || disposed) return
    targets.value = Array.isArray(result.targets) ? result.targets : []
    if (!targets.value.length) throw new Error('标的目录为空')
    if (!targets.value.some(t => t.target === target.value)) target.value = targets.value[0].target
  } catch (e) {
    if (id === targetSequence && !disposed && e.name !== 'AbortError') targetError.value = `标的目录获取失败：${e.message}`
  } finally {
    if (id === targetSequence && !disposed) targetLoading.value = false
  }
}
async function load() {
  const id = ++sequence, code = target.value, range = days.value, periodValue = period.value
  controller?.abort()
  controller = new AbortController()
  data.value = null; error.value = ''; hovered.value = -1; pointerY = null
  // Clear pixels synchronously as well as data: old candles must not survive a query change.
  geometry = null
  const el = canvas.value
  el?.getContext('2d')?.clearRect(0, 0, el.width, el.height)
  loading.value = Boolean(code)
  scheduleDraw()
  if (!code) return
  try {
    const res = await fetch(`/api/kline/${encodeURIComponent(code)}?days=${range}&period=${periodValue}`, { signal: controller.signal })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || `HTTP ${res.status}`)
    }
    const result = await res.json()
    if (id !== sequence || disposed) return
    if (result.target_code !== code) throw new Error('返回标的与当前查询不一致')
    data.value = result
    scheduleDraw()
  } catch (e) {
    if (id === sequence && !disposed && e.name !== 'AbortError') error.value = `K线获取失败：${e.message}`
  } finally {
    if (id === sequence && !disposed) loading.value = false
  }
}
function scheduleDraw() {
  if (disposed || frame !== null) return
  frame = requestAnimationFrame(() => { frame = null; draw() })
}
function draw() {
  const el = canvas.value, host = chartHost.value
  if (!el || !host) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const { width, height } = host.getBoundingClientRect()
  if (!width || !height) return
  const dpr = window.devicePixelRatio || 1
  el.width = Math.round(width * dpr); el.height = Math.round(height * dpr)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const css = getComputedStyle(el)
  const color = name => css.getPropertyValue(name).trim()
  ctx.fillStyle = color('--bg-panel'); ctx.fillRect(0, 0, width, height)
  geometry = chartGeometry(bars.value, width, height)
  if (!geometry) return
  const g = geometry
  const yPrice = p => g.bottom - (p - g.min) / (g.max - g.min) * (g.bottom - g.top)
  const xAt = i => g.left + (i + .5) * g.step
  const maLines = mas.value
  function line(x1, y1, x2, y2, stroke) {
    ctx.strokeStyle = stroke; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
  }
  ctx.font = '11px sans-serif'; ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = g.top + (g.bottom - g.top) * i / 4
    line(g.left, y, g.right, y, color('--border'))
    ctx.fillStyle = color('--text-dim'); ctx.textAlign = 'right'
    ctx.fillText(g.hasPrices ? (g.max - (g.max - g.min) * i / 4).toFixed(4) : '--', g.left - 7, y + 4)
  }
  line(g.left, g.volumeBottom, g.right, g.volumeBottom, color('--border'))
  ctx.fillStyle = color('--text-dim'); ctx.textAlign = 'left'
  ctx.fillText('成交量（原始单位）', g.left, g.volumeTop - 9)
  const candleWidth = Math.max(.6, Math.min(12, g.step * .68))
  bars.value.forEach((b, i) => {
    const x = xAt(i), tone = b.validPrice ? color(b.close >= b.open ? '--up' : '--down') : color('--text-dim')
    ctx.fillStyle = tone
    if (b.validPrice) {
      line(x, yPrice(b.high), x, yPrice(b.low), tone)
      ctx.fillRect(x - candleWidth / 2, Math.min(yPrice(b.open), yPrice(b.close)), candleWidth, Math.max(1, Math.abs(yPrice(b.open) - yPrice(b.close))))
    } else {
      ctx.fillStyle = color('--warn'); ctx.textAlign = 'center'; ctx.fillText('×', x, g.bottom - 6)
    }
    if (b.volume === null) {
      ctx.fillStyle = color('--warn'); ctx.textAlign = 'center'; ctx.fillText('×', x, g.volumeBottom - 4)
    } else if (b.volume > 0 && g.volumeMax > 0) {
      const h = b.volume / g.volumeMax * (g.volumeBottom - g.volumeTop)
      ctx.fillStyle = tone; ctx.fillRect(x - candleWidth / 2, g.volumeBottom - h, candleWidth, h)
    }
  })
  // Moving-average overlays (MA5/MA20/MA60) drawn as polylines over the
  // price pane. A segment is skipped whenever the window at that bar
  // contains a missing close (null) — never imputed.
  ctx.lineWidth = 1.5
  maLines.forEach((series, k) => {
    ctx.strokeStyle = color(['--ma5', '--ma20', '--ma60'][k])
    ctx.beginPath()
    let pen = false
    series.forEach((v, i) => {
      if (v == null) { pen = false; return }
      const x = xAt(i), y = yPrice(v)
      if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true }
    })
    ctx.stroke()
  })
  const count = bars.value.length
  const dateIndices = width < 500 ? [0, count - 1] : [0, Math.floor((count - 1) / 2), count - 1]
  const axisFmt = period.value === 'day' ? (s) => s : (s) => String(s).slice(5, 16) // 分钟K: MM-DD HH:MM
  ctx.fillStyle = color('--text-dim')
  for (const i of new Set(dateIndices)) {
    ctx.textAlign = i === 0 ? 'left' : i === count - 1 ? 'right' : 'center'
    ctx.fillText(axisFmt(bars.value[i].date), i === 0 ? g.left : i === count - 1 ? g.right : xAt(i), height - 8)
  }
  if (hovered.value >= 0 && hovered.value < count) {
    const x = xAt(hovered.value), b = bars.value[hovered.value]
    const y = pointerY ?? (b.validPrice ? yPrice(b.close) : g.bottom)
    ctx.setLineDash([4, 4])
    line(x, g.top, x, g.volumeBottom, color('--accent'))
    line(g.left, y, g.right, y, color('--accent'))
    ctx.setLineDash([])
  }
}
function moveCrosshair(event) {
  if (!geometry) return
  const rect = canvas.value.getBoundingClientRect(), g = geometry
  const x = event.clientX - rect.left, y = event.clientY - rect.top
  if (x < g.left || x > g.right || y < g.top || y > g.volumeBottom) { clearCrosshair(); return }
  hovered.value = indexAt(x, g, bars.value.length)
  pointerY = y; scheduleDraw()
}
function clearCrosshair() { hovered.value = -1; pointerY = null; scheduleDraw() }
function stepCrosshair(delta) {
  if (!bars.value.length) return
  const start = hovered.value < 0 ? bars.value.length - 1 : hovered.value
  hovered.value = Math.max(0, Math.min(bars.value.length - 1, start + delta))
  pointerY = null; scheduleDraw()
}
watch([target, days, period], load)
onMounted(() => {
  resizeObserver = new ResizeObserver(scheduleDraw)
  resizeObserver.observe(chartHost.value)
  themeObserver = new MutationObserver(scheduleDraw)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] })
  window.addEventListener('resize', scheduleDraw)
  loadTargets()
})
onUnmounted(() => {
  disposed = true; ++sequence; ++targetSequence
  controller?.abort(); targetController?.abort()
  resizeObserver?.disconnect(); themeObserver?.disconnect()
  window.removeEventListener('resize', scheduleDraw)
  if (frame !== null) cancelAnimationFrame(frame)
})
</script>

<style scoped>
.kline-page { min-width: 0; }
.note { color: var(--text-dim); font-size: 13px; line-height: 1.7; margin: 12px 0; }

button:disabled { opacity: .5; cursor: wait; }
button:focus-visible, canvas:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.range-btn, .refresh-btn {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  border-radius: var(--pill); padding: 8px 16px; font-size: 13px; font-weight: 600;
}
.range-btn:hover:not(:disabled), .refresh-btn:hover:not(:disabled) { border-color: var(--accent); }
.range-btn.active { border-color: var(--text); background: var(--accent); border-color: var(--accent); color: var(--accent-text); font-weight: 700; }
.refresh-btn { color: var(--accent-ink); }
.provenance { color: var(--text-dim); font-size: 12px; line-height: 1.9; overflow-wrap: anywhere; background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 16px; margin: 0 0 12px; }
.provenance p { margin: 2px 0; }
.missing, [role=alert] { color: var(--warn); font-size: 13px; line-height: 1.7; margin: 10px 0; }
.chart-card {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--radius-lg); padding: 20px;
  box-shadow: var(--shadow);
}
.chart-top { display: grid; grid-template-columns: minmax(200px, 240px) minmax(0, 1fr); gap: 20px; align-items: start; margin-bottom: 14px; }
.ohlc { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px 16px; font-variant-numeric: tabular-nums; }
.ma-legend { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 0; }
.ma-chip {
  font-size: 11px; font-weight: 700; padding: 2px 10px 2px 20px; border-radius: var(--pill);
  border: 1px solid; font-variant-numeric: tabular-nums; position: relative;
}
.ma-chip::before {
  content: ""; position: absolute; left: 7px; top: 50%; transform: translateY(-50%);
  width: 9px; height: 9px; border-radius: 50%; background: currentColor;
}
.ma-chip.ma-5 { color: var(--ma5); border-color: color-mix(in srgb, var(--ma5) 45%, white); background: color-mix(in srgb, var(--ma5) 10%, white); }
.ma-chip.ma-20 { color: var(--ma20); border-color: color-mix(in srgb, var(--ma20) 45%, white); background: color-mix(in srgb, var(--ma20) 10%, white); }
.ma-chip.ma-60 { color: var(--ma60); border-color: color-mix(in srgb, var(--ma60) 45%, white); background: color-mix(in srgb, var(--ma60) 10%, white); }
.ohlc dt { color: var(--text-muted); font-size: 11px; margin-bottom: 5px; }
.ohlc dd { font-size: 13.5px; font-family: var(--font-mono); font-weight: 600; overflow-wrap: anywhere; }
.chart-host { width: 100%; height: 500px; margin-top: 6px; position: relative; }
/* 纵向手势交给浏览器滚动页面（pan-y）；横向手势由 canvas 捕获用于逐日查看 K 线。
   若 touch-action 含 pan-x，横向拖动会被浏览器接管去横向滚动，pointermove 停止，
   手指就无法平移查看 K 线，故必须保持仅 pan-y。 */
canvas { display: block; width: 100%; height: 100%; touch-action: pan-y; }
.empty { height: 100%; display: flex; flex-direction: column; justify-content: center; }
.chart-hint { margin-bottom: 0; margin-top: 14px; }
@media (max-width: 900px) {
  .chart-top { grid-template-columns: 1fr; }
  .ohlc { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .chart-card { padding: 12px; }
  .chart-host { height: 360px; }
  .ohlc { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 8px; }
  .target-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .tab { flex-direction: row; justify-content: space-between; min-width: 0; width: 100%; padding: 10px 14px; }
  .tab.active::before { top: 8px; bottom: 8px; }
  .tab.small { flex: none; min-height: 36px; }
  .ph-actions { width: 100%; }
}
</style>
