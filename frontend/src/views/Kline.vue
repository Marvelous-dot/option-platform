<template>
  <section class="kline-page">
    <div class="page-head">
      <div class="ph-title">
        <span class="ph-kicker">CANDLESTICK · 日K / 分钟K</span>
        <h1>标的 K 线</h1>
        <p class="ph-desc">红涨绿跌（收盘对比开盘）；日 K 落盘缓存可回看历史，分钟 K（5/15/30/60 分）为盘中数据、不复权、仅近期根数。末根可能尚未收盘。</p>
      </div>
      <div class="ph-actions">
        <div class="btn-group" role="group" aria-label="K线周期">
          <button v-for="[p, label] in PERIODS" :key="p" type="button" class="range-btn"
            :class="{ active: period === p }" :aria-pressed="period === p" @click="setPeriod(p)">{{ label }}</button>
        </div>
        <div class="btn-group" role="group" aria-label="K线范围">
          <button v-for="opt in rangeOptions" :key="opt.size" type="button" class="range-btn"
            :class="{ active: viewCount === opt.size }" :aria-pressed="viewCount === opt.size"
            @click="applyRange(opt.size)">{{ opt.label }}</button>
          <button type="button" class="refresh-btn" :disabled="loading || !target" @click="load">{{ loading ? '加载中…' : '刷新' }}</button>
        </div>
      </div>
    </div>
    <div class="controls" role="group" aria-label="选择标的">
      <div class="target-tabs">
        <button v-for="t in targets" :key="t.target" type="button" class="tab"
          :class="{ active: target === t.target }" :aria-pressed="target === t.target" @click="target = t.target">
          <span class="tab-code">{{ t.target }}</span><span class="tab-name">{{ t.name }}</span>
        </button>
      </div>
      <div v-if="spot" class="spot-quote" :class="spotCls" role="status" aria-label="标的实时行情">
        <span class="sq-code">{{ target }}</span>
        <b class="sq-price">{{ fmtSpot(spot.price) }}</b>
        <span class="sq-chg">{{ fmtChg(spot.chg) }}</span>
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
      <p>末根时间 {{ data.last_date || '未知' }} · 末根收盘字段 {{ formatPrice(data.last_close) }}（可能仍变动）· 源返回 {{ data.count ?? '未知' }} 根 / 请求 {{ rangeLabel }}，已载入 {{ bars.length }} 根，当前窗口 {{ visibleCount }} 根，按返回时间排列，不填补缺失。</p>
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
      <div class="chart-tools">
        <span class="ct-count">显示 {{ visibleCount }} / {{ bars.length }} 根</span>
        <span class="ct-hint">滚轮 / 双指缩放 · 拖动平移</span>
        <button type="button" class="ct-reset" @click="resetView">复位</button>
      </div>
      <p v-if="activeBar && !activeBar.validPrice" class="missing">本根 OHLC 不完整或范围异常，蜡烛不可用。</p>
      <div ref="chartHost" class="chart-host" :aria-busy="loading">
        <canvas ref="canvas" v-show="bars.length" tabindex="0" role="img"
          aria-label="标的K线蜡烛与成交量图。滚轮或双指缩放、拖动平移、双击复位；轻点或用左右方向键查看逐根开高低收。"
          @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp"
          @pointercancel="onPointerUp" @pointerleave="onPointerLeave" @wheel.prevent="onWheel"
          @dblclick="resetView"
          @keydown.left.prevent="stepCrosshair(-1)" @keydown.right.prevent="stepCrosshair(1)" @blur="clearCrosshair"></canvas>
        <div v-if="!bars.length" class="empty">
          <p class="empty-title">{{ loading ? '正在获取当前条件的K线…' : '暂无可绘制的K线' }}</p>
          <p class="empty-detail">{{ error || data?.status_detail || '数据缺失时不展示模拟行情。' }}</p>
        </div>
      </div>
      <p class="note chart-hint">均线按收盘价本地计算，窗口内缺失收盘则断线不补值；成交量使用原始单位；分钟K不复权、数据源仅提供近期根数。滚轮或双指缩放、拖动平移、双击复位；移动鼠标 / 触摸 / 左右方向键查看开高低收，默认详情为窗口右端那根（未确认收盘）。</p>
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
// 可见窗口（根）——一屏默认 45~66 根，保证蜡烛够粗；缩放/平移只改这个窗口，不重新取数
function windowRange() {
  const n = bars.value.length
  const size = Math.max(6, Math.min(viewCount.value, n || 6))
  const end = Math.min(Math.max(viewEnd.value, size - 1), Math.max(n - 1, 0))
  return { start: Math.max(0, end - size + 1), end, size }
}
function defaultViewSize(width) {
  return width < 460 ? 45 : width < 900 ? 66 : 90
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
const targets = ref([]), target = ref(klineRemembered.target || '')
const PERIODS = [['day', '日K'], ['5m', '5分'], ['15m', '15分'], ['30m', '30分'], ['60m', '60分']]
const period = ref(klineRemembered.period || 'day')
// 常规门户的做法：一次取足历史（日 300 / 分 480），屏幕上只画一个可缩放窗口。
// 好处是放大到近月时 MA60 仍有足够前置数据，向左平移也有历史可看。
const FETCH_BARS = { day: 300, '5m': 480, '15m': 480, '30m': 480, '60m': 480 }
const fetchBars = computed(() => FETCH_BARS[period.value] || 300)
const DAY_PRESETS = [{ size: 22, label: '1月' }, { size: 66, label: '3月' }, { size: 132, label: '6月' }, { size: 250, label: '1年' }]
const MIN_PRESETS = [{ size: 60, label: '60根' }, { size: 120, label: '120根' }, { size: 240, label: '240根' }]
const rangeOptions = computed(() => period.value === 'day' ? DAY_PRESETS : MIN_PRESETS)
const rangeLabel = computed(() => period.value === 'day' ? `${fetchBars.value}日` : `${fetchBars.value}根`)
const dateLabel = computed(() => period.value === 'day' ? '日期' : '时间')
// 可见窗口：viewCount = 一屏根数，viewEnd = 右边界在 bars 中的绝对下标
const viewCount = ref(66)   // 一屏根数；首次绘制时按画布宽度收敛（窄屏 45 / 桌面 90）
const viewEnd = ref(0)
let windowTouched = false   // 用户手动缩放/平移后，不再按容器宽度自动改窗口
function setPeriod(p) {
  if (period.value === p) return
  period.value = p
}
const data = ref(null), loading = ref(false), error = ref('')
const targetLoading = ref(false), targetError = ref('')
// 标的实时涨跌（复用 T 型报价的 spot 快照，30s 轮询）
const spot = ref(null)
const spotCls = computed(() => {
  const c = Number(spot.value?.chg)
  return c > 0 ? 'up' : c < 0 ? 'down' : ''
})
function fmtSpot(v) { const n = Number(v); return Number.isFinite(n) ? n.toFixed(4) : '--' }
function fmtChg(c) { const n = Number(c); return Number.isFinite(n) ? (n > 0 ? '+' : '') + n.toFixed(2) + '%' : '--' }
let spotSeq = 0
async function loadSpot() {
  const code = target.value
  if (!code) return
  const id = ++spotSeq
  try {
    const r = await fetch(`/api/tquote/${encodeURIComponent(code)}`)
    if (!r.ok) return
    const d = await r.json()
    if (id !== spotSeq || disposed || code !== target.value) return
    if (d.spot?.price != null) spot.value = { price: d.spot.price, chg: d.spot.change_pct }
  } catch { /* 展示性数据：失败保留上次快照 */ }
}
const chartHost = ref(null), canvas = ref(null), hovered = ref(-1)
const priceFields = [['open', '开'], ['high', '高'], ['low', '低'], ['close', '收']]
const bars = computed(() => data.value?.data_status === 'ok' ? normalizeBars(data.value.bars) : [])
const activeIndex = computed(() => hovered.value >= 0 ? hovered.value : windowRange().end)
const activeBar = computed(() => bars.value[activeIndex.value])
const visibleCount = computed(() => windowRange().size)
const missingPrices = computed(() => bars.value.filter(b => !b.validPrice).length)
const missingVolumes = computed(() => bars.value.filter(b => b.volume === null).length)
const MA_PERIODS = [5, 20, 60]
const closes = computed(() => bars.value.map(b => b.close))
const mas = computed(() => MA_PERIODS.map(p => movingAverage(closes.value, p)))
const activeMA = computed(() => {
  const i = activeIndex.value
  return i >= 0 ? MA_PERIODS.map((p, k) => mas.value[k][i]) : []
})
let controller, targetController, sequence = 0, targetSequence = 0, disposed = false
let resizeObserver, themeObserver, frame = null, geometry = null, pointerY = null
let spotTimer = null
// 记住 K线页选中的标的、周期与根数范围
watch([target, period], () => {
  if (!target.value) return
  writeState('kline', { target: target.value, period: period.value })
}, { immediate: false })
// 切换标的立即刷新实时报价
watch(target, () => { spot.value = null; loadSpot() })

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
  const id = ++sequence, code = target.value, range = fetchBars.value, periodValue = period.value
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
    // 新数据回到默认视图：贴右缘（最新根），一屏根数交给 draw 按实际画布宽度决定
    windowTouched = false
    viewEnd.value = Math.max(0, (result.bars?.length || 1) - 1)
    hovered.value = -1
    scheduleDraw()
  } catch (e) {
    if (id === sequence && !disposed && e.name !== 'AbortError') error.value = `K线获取失败：${e.message}`
  } finally {
    if (id === sequence && !disposed) loading.value = false
  }
}
// 预设按钮只改可见窗口，不重新请求数据（MA60 因此始终有足够前置数据）
function applyRange(size) {
  windowTouched = true
  viewCount.value = size
  viewEnd.value = Math.max(0, bars.value.length - 1)
  hovered.value = -1
  pointerY = null
  scheduleDraw()
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
  const rows = bars.value
  if (!rows.length) { geometry = null; return }
  // 窗口宽度随容器变化（旋转屏幕 / 窗口缩放）：用户没手动调过就跟着自适应
  if (!windowTouched) {
    const want = Math.max(6, Math.min(defaultViewSize(width), rows.length))
    if (want !== viewCount.value) { viewCount.value = want; viewEnd.value = rows.length - 1 }
  }
  const win = windowRange()
  const visible = rows.slice(win.start, win.end + 1)
  geometry = chartGeometry(visible, width, height)
  if (!geometry) return
  const g = geometry
  const yPrice = p => g.bottom - (p - g.min) / (g.max - g.min) * (g.bottom - g.top)
  // xAt 接受 bars 的绝对下标，窗口外的点会落在绘图区之外（不绘制）
  const xAt = i => g.left + (i - win.start + .5) * g.step
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
  const candleWidth = Math.max(.8, Math.min(14, g.step * .7))
  visible.forEach((b, k) => {
    const i = win.start + k
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
    for (let i = win.start; i <= win.end; i++) {
      const v = series[i]
      if (v == null) { pen = false; continue }
      const x = xAt(i), y = yPrice(v)
      if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true }
    }
    ctx.stroke()
  })
  const count = visible.length
  const dateIndices = width < 500 ? [0, count - 1] : [0, Math.floor((count - 1) / 2), count - 1]
  const axisFmt = period.value === 'day' ? (s) => s : (s) => String(s).slice(5, 16) // 分钟K: MM-DD HH:MM
  ctx.fillStyle = color('--text-dim')
  for (const k of new Set(dateIndices)) {
    const i = win.start + k
    ctx.textAlign = k === 0 ? 'left' : k === count - 1 ? 'right' : 'center'
    ctx.fillText(axisFmt(rows[i].date), k === 0 ? g.left : k === count - 1 ? g.right : xAt(i), height - 8)
  }
  if (hovered.value >= win.start && hovered.value <= win.end) {
    const x = xAt(hovered.value), b = bars.value[hovered.value]
    const y = pointerY ?? (b.validPrice ? yPrice(b.close) : g.bottom)
    ctx.setLineDash([4, 4])
    line(x, g.top, x, g.volumeBottom, color('--accent'))
    line(g.left, y, g.right, y, color('--accent'))
    ctx.setLineDash([])
  }
}
function clearCrosshair() { hovered.value = -1; pointerY = null; scheduleDraw() }
// 窗口操作：改 viewCount（缩放）与 viewEnd（平移），不重新请求数据
function setWindow(size, anchorIndex, anchorRatio) {
  const n = bars.value.length
  if (!n) return
  windowTouched = true
  const next = Math.round(Math.max(6, Math.min(size, n)))
  const start = Math.round(anchorIndex - anchorRatio * (next - 1))
  viewCount.value = next
  viewEnd.value = Math.min(n - 1, Math.max(next - 1, start + next - 1))
  hovered.value = -1
  scheduleDraw()
}
function zoomTo(size, anchorRatio) {
  const cur = windowRange()
  const ratio = Math.min(1, Math.max(0, anchorRatio))
  setWindow(size, cur.start + ratio * (cur.size - 1), ratio)
}
function panToEnd(end) {
  const n = bars.value.length
  if (!n) return
  windowTouched = true
  const next = Math.min(Math.max(windowRange().size - 1, end), n - 1)
  if (next === viewEnd.value) return
  viewEnd.value = next
  hovered.value = -1
  scheduleDraw()
}
function resetView() {
  const n = bars.value.length
  if (!n) return
  windowTouched = false
  const w = chartHost.value?.getBoundingClientRect().width || 0
  viewCount.value = Math.max(6, Math.min(defaultViewSize(w), n))
  viewEnd.value = n - 1
  hovered.value = -1
  scheduleDraw()
}
let activePointers = new Map(), dragState = null, pinchState = null
function canvasPoint(event) {
  const rect = canvas.value?.getBoundingClientRect()
  return { x: event.clientX - (rect?.left || 0), y: event.clientY - (rect?.top || 0) }
}
function hoverAt(point) {
  const g = geometry
  if (!g) return
  if (point.x < g.left || point.x > g.right || point.y < g.top || point.y > g.volumeBottom) { clearCrosshair(); return }
  const { start, end } = windowRange()
  hovered.value = Math.max(start, Math.min(end, start + Math.floor((point.x - g.left) / g.step)))
  pointerY = point.y
  scheduleDraw()
}
function axisRatio(point) {
  const g = geometry
  if (!g) return .5
  return Math.min(1, Math.max(0, (point.x - g.left) / Math.max(1, g.right - g.left)))
}
function onPointerDown(event) {
  const point = canvasPoint(event)
  canvas.value?.setPointerCapture?.(event.pointerId)
  activePointers.set(event.pointerId, point)
  if (activePointers.size === 1) {
    dragState = { x: point.x, end: windowRange().end, moved: false }
    pinchState = null
  } else if (activePointers.size === 2) {
    const [a, b] = [...activePointers.values()]
    pinchState = { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, size: windowRange().size, mid: (a.x + b.x) / 2 }
    dragState = null
  }
}
function onPointerMove(event) {
  const point = canvasPoint(event)
  if (!activePointers.has(event.pointerId)) { hoverAt(point); return }
  activePointers.set(event.pointerId, point)
  if (pinchState && activePointers.size >= 2) {
    const [a, b] = [...activePointers.values()]
    const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1
    zoomTo(pinchState.size * (pinchState.dist / dist), axisRatio({ x: pinchState.mid }))
    return
  }
  if (dragState) {
    const dx = point.x - dragState.x
    if (!dragState.moved && Math.abs(dx) < 4) return
    dragState.moved = true
    panToEnd(dragState.end - Math.round(dx / Math.max(1, geometry?.step || 6)))
    return
  }
  hoverAt(point)
}
function onPointerUp(event) {
  const wasTap = Boolean(dragState && !dragState.moved)
  activePointers.delete(event.pointerId)
  if (!activePointers.size) { dragState = null; pinchState = null }
  if (wasTap) hoverAt(canvasPoint(event))
}
function onPointerLeave() { if (!activePointers.size) clearCrosshair() }
function onWheel(event) {
  if (!geometry) return
  zoomTo(windowRange().size * (event.deltaY > 0 ? 1.2 : 1 / 1.2), axisRatio(canvasPoint(event)))
}
function stepCrosshair(delta) {
  const n = bars.value.length
  if (!n) return
  const { start, end } = windowRange()
  const cur = hovered.value < 0 ? end : hovered.value
  const next = Math.max(0, Math.min(n - 1, cur + delta))
  if (next < start) panToEnd(viewEnd.value - 1)
  else if (next > end) panToEnd(viewEnd.value + 1)
  hovered.value = next
  pointerY = null
  scheduleDraw()
}
watch([target, period], load)
onMounted(() => {
  resizeObserver = new ResizeObserver(scheduleDraw)
  resizeObserver.observe(chartHost.value)
  themeObserver = new MutationObserver(scheduleDraw)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] })
  window.addEventListener('resize', scheduleDraw)
  loadTargets()
  loadSpot()
  spotTimer = setInterval(loadSpot, 30000)
})
onUnmounted(() => {
  disposed = true; ++sequence; ++targetSequence
  controller?.abort(); targetController?.abort()
  if (spotTimer) clearInterval(spotTimer)
  resizeObserver?.disconnect(); themeObserver?.disconnect()
  window.removeEventListener('resize', scheduleDraw)
  if (frame !== null) cancelAnimationFrame(frame)
})
</script>

<style scoped>
.kline-page { min-width: 0; }
/* 标的实时报价 chip：跟随当前标的，涨红跌绿 */
.spot-quote {
  display: inline-flex; align-items: baseline; gap: 9px;
  font-variant-numeric: tabular-nums; white-space: nowrap;
  padding: 7px 16px; border: 1px solid var(--border); border-radius: var(--pill);
  background: var(--bg-elevated);
}
.spot-quote .sq-code { font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--text-dim); }
.spot-quote .sq-price { font-family: var(--font-mono); font-size: 15px; font-weight: 800; color: var(--text); }
.spot-quote .sq-chg { font-family: var(--font-mono); font-size: 12.5px; font-weight: 800; }
.spot-quote.up { border-color: var(--up-dim); background: var(--up-dim); }
.spot-quote.up .sq-price, .spot-quote.up .sq-chg { color: var(--up); }
.spot-quote.down { border-color: var(--down-dim); background: var(--down-dim); }
.spot-quote.down .sq-price, .spot-quote.down .sq-chg { color: var(--down); }
.note { color: var(--text-dim); font-size: 13px; line-height: 1.7; margin: 12px 0; }

button:disabled { opacity: .5; cursor: wait; }
.btn-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
/* 宽屏两组按钮同一行：加一条竖线，避免「60分」和「1月」读起来像同一维度 */
@media (min-width: 769px) {
  .btn-group + .btn-group { margin-left: 4px; padding-left: 14px; border-left: 1px solid var(--border); }
}
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
.chart-tools { display: flex; align-items: center; gap: 10px; margin: 0 0 4px; font-size: 11.5px; }
.ct-count { font-variant-numeric: tabular-nums; font-weight: 600; color: var(--text-dim); }
.ct-hint { color: var(--text-muted); }
.ct-reset {
  margin-left: auto; background: none; border: 1px solid var(--border); color: var(--text-dim);
  font-size: 11px; font-weight: 600; padding: 3px 11px; border-radius: var(--pill); cursor: pointer;
}
.ct-reset:hover { border-color: var(--accent); color: var(--text); }
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
/* 窄屏重排：.controls 原来是 flex，.target-tabs 的 flex:1（等价 flex-basis:0）
   会与现价 chip 抢同一行，把标的卡网格压到 158px（每张 75px，代码被迫竖排）。
   改为块级后卡占满整行、chip 独占一行，不再叠压。 */
@media (max-width: 768px) {
  .controls { display: block; }
  .spot-quote {
    display: flex; width: 100%; margin-top: 10px;
    padding: 9px 14px; border-radius: var(--radius);
  }
  .spot-quote .sq-price { margin-left: auto; }   /* 代码左、价格与涨跌靠右 */

  /* 窄屏先看图：页头 → 选标的 → 图表，数据状态与来源说明降为图后附注。
     否则状态条 + 来源块会把图表顶到 850px 之外，首屏几乎全是说明文字。 */
  .kline-page { display: flex; flex-direction: column; }
  .page-head { order: 1; }
  .controls { order: 2; }
  .note, [role="alert"] { order: 3; }
  .chart-card { order: 4; }
  .statusbar { order: 5; margin-top: 14px; }
  .provenance { order: 6; margin-top: 10px; }
  .missing { order: 7; }

  .ph-actions { flex-direction: column; align-items: flex-start; gap: 8px; width: 100%; padding-bottom: 0; }
}
@media (max-width: 600px) {
  .page-head { gap: 8px; margin-bottom: 14px; }
  .page-head h1 { font-size: 21px; }
  .ph-kicker { margin-bottom: 5px; }
  .ph-desc { margin-top: 6px; font-size: 12px; line-height: 1.55; }
  .provenance { font-size: 11px; line-height: 1.7; padding: 9px 13px; }
  .chart-card { padding: 12px; }
  .chart-host { height: 360px; }
  .chart-tools { font-size: 11px; gap: 8px; }
  .ct-hint { display: none; }   /* 窄屏省一行：手势说明留在图下方的 chart-hint */
  .ohlc { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 8px; }
  .target-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  /* 5 只标的排 2 列会剩一个孤位，让末张卡横跨两列，视觉上收口 */
  .target-tabs .tab:last-child:nth-child(odd) { grid-column: span 2; }
  /* OHLC 由「标签在上/数值在下」改为同行左右对齐：9 个字段从 3 行 200px 压到 3 行 96px，
     蜡烛图回到首屏；数值不准断行，避免 2026-11-23 被拆成两行 */
  .chart-top { gap: 10px; margin-bottom: 10px; }
  .ohlc { gap: 8px 10px; }
  .ohlc > div { display: flex; align-items: baseline; justify-content: space-between; gap: 5px; }
  .ohlc dt { margin-bottom: 0; font-size: 10.5px; }
  .ohlc dd { font-size: 12px; white-space: nowrap; }
  /* 代码与名称上下排，名称单行省略——横排时 177px 里只能塞两三个字 */
  .tab { flex-direction: column; align-items: flex-start; gap: 3px; min-width: 0; width: 100%; padding: 10px 13px; }
  .tab-name { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tab.active::before { top: 8px; bottom: 8px; }
  .tab.small { flex: none; min-height: 36px; }
  .ph-actions { width: 100%; gap: 6px; }
  .range-btn, .refresh-btn { padding: 7px 13px; font-size: 12.5px; }
}
</style>
