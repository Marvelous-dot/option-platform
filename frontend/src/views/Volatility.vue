<script setup>
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import Surface3D from '../components/Surface3D.vue'
import DashboardChart from '../components/DashboardChart.vue'
import DashboardPanel from '../components/DashboardPanel.vue'
import { getCssVars } from '@/utils/cssVar'

// ── State ──
const loading = ref(true)
const loadingKline = ref(false)
const loadingSurface = ref(false)
const loadingSmile = ref(false)
const loadingTerm = ref(false)
const loading3D = ref(false)
const loadingDashboard = ref(false)
const loadingDashboardPanel = ref(false)
const targets = ref([])
const selectedTarget = ref('510050')
const expiries = ref([])
const selectedExpiry = ref('')
const activeTab = ref('dashboardPanel') // dashboardPanel | dashboard | kline | surface | smile | term | surface3d

// Data
const klineData = ref([])
const surfaceData = ref([])
const smileData = ref({ calls: [], puts: [], spot_price: null })
const termData = ref([])
const surface3dData = ref({ strikes: [], expiries: [], grid: { call: [], put: [] }, spot_price: 0, min_iv: 0, max_iv: 0 })
const surface3dType = ref('call')
const dashboardData = ref([])
const dashboardLatest = ref(null)
const ivStats = ref({ current: 0, high: 0, low: 0, avg: 0, change: 0 })

// Chart refs
const klineChart = ref(null)
const surfaceChart = ref(null)
const smileChart = ref(null)
const termChart = ref(null)
let refreshTimer = null

// ── Target options ──
const targetOptions = [
  { code: '510050', name: '上证50ETF' },
  { code: '510300', name: '沪深300ETF' },
  { code: '510500', name: '中证500ETF' },
  { code: '588000', name: '科创50ETF' },
  { code: '588080', name: '科创50ETF易方达' },
]

const selectedTargetName = computed(() => {
  const t = targetOptions.find(t => t.code === selectedTarget.value)
  return t ? t.name : ''
})

// ── API calls ──
const fetchTargets = async () => {
  try {
    const res = await fetch('/api/targets')
    const data = await res.json()
    targets.value = data.targets || []
  } catch (e) {
    console.error('fetchTargets:', e)
  }
}

const fetchExpiries = async (targetCode) => {
  try {
    const res = await fetch(`/api/volatility/expiries/${targetCode}`)
    const data = await res.json()
    expiries.value = data.expiries || []
    if (expiries.value.length > 0 && !selectedExpiry.value) {
      selectedExpiry.value = expiries.value[0]
    }
  } catch (e) {
    console.error('fetchExpiries:', e)
  }
}

const fetchKline = async () => {
  if (loadingKline.value || !selectedTarget.value) return
  loadingKline.value = true
  try {
    const res = await fetch(`/api/volatility/kline/${selectedTarget.value}`)
    const data = await res.json()
    klineData.value = data.data || []
    computeIvStats()
    nextTick(() => renderKlineChart())
  } catch (e) {
    console.error('fetchKline:', e)
  } finally {
    loadingKline.value = false
  }
}

const fetchSurface = async () => {
  if (loadingSurface.value || !selectedExpiry.value) return
  loadingSurface.value = true
  try {
    const res = await fetch(`/api/volatility/surface/${selectedTarget.value}?expiry=${selectedExpiry.value}`)
    const data = await res.json()
    surfaceData.value = data.data || []
    nextTick(() => renderSurfaceChart())
  } catch (e) {
    console.error('fetchSurface:', e)
  } finally {
    loadingSurface.value = false
  }
}

const fetchSmile = async () => {
  if (loadingSmile.value || !selectedExpiry.value) return
  loadingSmile.value = true
  try {
    const res = await fetch(`/api/volatility/smile/${selectedTarget.value}?expiry=${selectedExpiry.value}`)
    const data = await res.json()
    smileData.value = { calls: data.calls || [], puts: data.puts || [], spot_price: data.spot_price }
    nextTick(() => renderSmileChart())
  } catch (e) {
    console.error('fetchSmile:', e)
  } finally {
    loadingSmile.value = false
  }
}

const fetchTerm = async () => {
  if (loadingTerm.value || !selectedTarget.value) return
  loadingTerm.value = true
  try {
    const res = await fetch(`/api/volatility/term/${selectedTarget.value}`)
    const data = await res.json()
    termData.value = data.data || []
    nextTick(() => renderTermChart())
  } catch (e) {
    console.error('fetchTerm:', e)
  } finally {
    loadingTerm.value = false
  }
}

const fetchSurface3D = async () => {
  try {
    const res = await fetch(`/api/volatility/surface3d/${selectedTarget.value}`)
    const data = await res.json()
    surface3dData.value = data || { strikes: [], expiries: [], grid: { call: [], put: [] }, spot_price: 0, min_iv: 0, max_iv: 0 }
  } catch (e) {
    console.error('fetchSurface3D:', e)
  }
}

const fetchDashboard = async () => {
  try {
    const res = await fetch(`/api/dashboard/series/${selectedTarget.value}?days=90`)
    const data = await res.json()
    dashboardData.value = data.data || []
    dashboardLatest.value = data.latest || null
  } catch (e) {
    console.error('fetchDashboard:', e)
  }
}

const loadAllData = async () => {
  loading.value = true
  await fetchTargets()
  await fetchExpiries(selectedTarget.value)
  await Promise.all([fetchKline(), fetchSurface(), fetchSmile(), fetchTerm(), fetchSurface3D(), fetchDashboard()])
  loading.value = false
}

// ── IV Stats ──
const computeIvStats = () => {
  const data = klineData.value
  if (!data.length) {
    ivStats.value = { current: 0, high: 0, low: 0, avg: 0, change: 0 }
    return
  }
  const ivs = data.map(d => d.iv).filter(v => v > 0)
  if (!ivs.length) return
  const current = ivs[ivs.length - 1]
  const prev = ivs.length > 1 ? ivs[ivs.length - 2] : current
  ivStats.value = {
    current: (current * 100).toFixed(2),
    high: (Math.max(...ivs) * 100).toFixed(2),
    low: (Math.min(...ivs) * 100).toFixed(2),
    avg: (ivs.reduce((a, b) => a + b, 0) / ivs.length * 100).toFixed(2),
    change: prev !== 0 ? ((current - prev) / prev * 100).toFixed(2) : '0.00',
  }
}

// ── Canvas Charts ──
function renderKlineChart() {
  const canvas = klineChart.value
  if (!canvas || !klineData.value.length) return
  const ctx = canvas.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)
  const W = rect.width, H = rect.height
  const data = klineData.value

  const ivs = data.map(d => d.iv * 100)
  const minIV = Math.min(...ivs) * 0.95
  const maxIV = Math.max(...ivs) * 1.05
  const range = maxIV - minIV || 1

  const pad = { top: 24, right: 50, bottom: 32, left: 56 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const xOf = (i) => pad.left + i / Math.max(data.length - 1, 1) * cw
  const yOf = (v) => pad.top + ch - (v - minIV) / range * ch

  // Clear
  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = vars.border
  ctx.lineWidth = 1
  for (let i = 0; i <= 5; i++) {
    const y = pad.top + ch * i / 5
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }
  for (let i = 0; i <= 6; i++) {
    const x = pad.left + cw * i / 6
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, H - pad.bottom); ctx.stroke()
  }

  // Y labels
  ctx.fillStyle = vars.textDim
  ctx.font = '10px var(--font-mono)'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 5; i++) {
    const v = maxIV - range * i / 5
    const y = pad.top + ch * i / 5
    ctx.fillText(v.toFixed(1) + '%', pad.left - 8, y + 3)
  }

  // X labels (dates)
  ctx.textAlign = 'center'
  ctx.fillStyle = vars.textDim
  const step = Math.max(1, Math.floor(data.length / 6))
  for (let i = 0; i < data.length; i += step) {
    const x = xOf(i)
    const ts = data[i].ts
    const date = ts ? ts.slice(5, 10) : ''
    ctx.fillText(date, x, H - pad.bottom + 14)
  }

  // IV area fill
  ctx.beginPath()
  ctx.moveTo(xOf(0), yOf(ivs[0]))
  for (let i = 1; i < ivs.length; i++) {
    ctx.lineTo(xOf(i), yOf(ivs[i]))
  }
  ctx.lineTo(xOf(ivs.length - 1), pad.top + ch)
  ctx.lineTo(xOf(0), pad.top + ch)
  ctx.closePath()
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch)
  grad.addColorStop(0, 'rgba(240,160,48,0.25)')
  grad.addColorStop(1, 'rgba(240,160,48,0.02)')
  ctx.fillStyle = grad
  ctx.fill()

  // IV line
  ctx.beginPath()
  ctx.moveTo(xOf(0), yOf(ivs[0]))
  for (let i = 1; i < ivs.length; i++) {
    ctx.lineTo(xOf(i), yOf(ivs[i]))
  }
  ctx.strokeStyle = vars.accent
  ctx.lineWidth = 2
  ctx.shadowColor = vars.accent
  ctx.shadowBlur = 6
  ctx.stroke()
  ctx.shadowBlur = 0

  // Current dot
  const lastX = xOf(ivs.length - 1)
  const lastY = yOf(ivs[ivs.length - 1])
  ctx.beginPath()
  ctx.arc(lastX, lastY, 4, 0, Math.PI * 2)
  ctx.fillStyle = vars.accent
  ctx.fill()
  ctx.strokeStyle = vars.bgPrimary
  ctx.lineWidth = 2
  ctx.stroke()

  // Title
  ctx.fillStyle = vars.textMuted
  ctx.font = '11px var(--font-sans)'
  ctx.textAlign = 'left'
  ctx.fillText('IV走势', pad.left, 16)
}

function renderSurfaceChart() {
  const canvas = surfaceChart.value
  if (!canvas || !surfaceData.value.length) return
  const ctx = canvas.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)
  const W = rect.width, H = rect.height
  const data = surfaceData.value

  const calls = data.filter(d => d.option_type === '认购').sort((a, b) => a.strike - b.strike)
  const puts = data.filter(d => d.option_type === '认沽').sort((a, b) => a.strike - b.strike)

  const allIVs = data.map(d => d.iv * 100)
  const minIV = Math.min(...allIVs) * 0.95
  const maxIV = Math.max(...allIVs) * 1.05
  const range = maxIV - minIV || 1

  const allStrikes = [...new Set(data.map(d => d.strike))].sort((a, b) => a - b)
  const minStrike = Math.min(...allStrikes)
  const maxStrike = Math.max(...allStrikes)
  const strikeRange = maxStrike - minStrike || 1

  const pad = { top: 24, right: 50, bottom: 32, left: 56 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const xOf = (s) => pad.left + (s - minStrike) / strikeRange * cw
  const yOf = (v) => pad.top + ch - (v - minIV) / range * ch

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = vars.border
  ctx.lineWidth = 1
  for (let i = 0; i <= 5; i++) {
    const y = pad.top + ch * i / 5
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // Y labels
  ctx.fillStyle = vars.textDim
  ctx.font = '10px var(--font-mono)'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 5; i++) {
    const v = maxIV - range * i / 5
    const y = pad.top + ch * i / 5
    ctx.fillText(v.toFixed(1) + '%', pad.left - 8, y + 3)
  }

  // X labels
  ctx.textAlign = 'center'
  const strikeStep = Math.max(1, Math.floor(allStrikes.length / 5))
  for (let i = 0; i < allStrikes.length; i += strikeStep) {
    const x = xOf(allStrikes[i])
    ctx.fillText(allStrikes[i].toFixed(2), x, H - pad.bottom + 14)
  }

  // Call line
  if (calls.length > 1) {
    ctx.beginPath()
    ctx.moveTo(xOf(calls[0].strike), yOf(calls[0].iv * 100))
    for (let i = 1; i < calls.length; i++) {
      ctx.lineTo(xOf(calls[i].strike), yOf(calls[i].iv * 100))
    }
    ctx.strokeStyle = 'vars.up'
    ctx.lineWidth = 2
    ctx.stroke()
  }

  // Put line
  if (puts.length > 1) {
    ctx.beginPath()
    ctx.moveTo(xOf(puts[0].strike), yOf(puts[0].iv * 100))
    for (let i = 1; i < puts.length; i++) {
      ctx.lineTo(xOf(puts[i].strike), yOf(puts[i].iv * 100))
    }
    ctx.strokeStyle = 'vars.down'
    ctx.lineWidth = 2
    ctx.stroke()
  }

  // Legend
  ctx.font = '11px var(--font-sans)'
  ctx.fillStyle = 'vars.up'
  ctx.textAlign = 'left'
  ctx.fillText('■ 认购', pad.left, 16)
  ctx.fillStyle = 'vars.down'
  ctx.fillText('■ 认沽', pad.left + 70, 16)
  ctx.fillStyle = vars.textMuted
  ctx.fillText('波动率曲面', pad.left + 140, 16)
}

function renderSmileChart() {
  const canvas = smileChart.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)
  const W = rect.width, H = rect.height

  const calls = smileData.value.calls || []
  const puts = smileData.value.puts || []
  const spotPrice = smileData.value.spot_price

  if (!calls.length && !puts.length) {
    ctx.fillStyle = vars.bgCard
    ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = vars.textMuted
    ctx.font = '13px var(--font-sans)'
    ctx.textAlign = 'center'
    ctx.fillText('暂无数据', W / 2, H / 2)
    return
  }

  const allData = [...calls, ...puts]
  const allIVs = allData.map(d => d.iv * 100)
  const minIV = Math.min(...allIVs) * 0.95
  const maxIV = Math.max(...allIVs) * 1.05
  const range = maxIV - minIV || 1

  const allStrikes = [...new Set(allData.map(d => d.strike))].sort((a, b) => a - b)
  const minStrike = Math.min(...allStrikes)
  const maxStrike = Math.max(...allStrikes)
  const strikeRange = maxStrike - minStrike || 1

  const pad = { top: 24, right: 50, bottom: 32, left: 56 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const xOf = (s) => pad.left + (s - minStrike) / strikeRange * cw
  const yOf = (v) => pad.top + ch - (v - minIV) / range * ch

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = vars.border
  ctx.lineWidth = 1
  for (let i = 0; i <= 5; i++) {
    const y = pad.top + ch * i / 5
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // Y labels
  ctx.fillStyle = vars.textDim
  ctx.font = '10px var(--font-mono)'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 5; i++) {
    const v = maxIV - range * i / 5
    const y = pad.top + ch * i / 5
    ctx.fillText(v.toFixed(1) + '%', pad.left - 8, y + 3)
  }

  // X labels
  ctx.textAlign = 'center'
  const strikeStep = Math.max(1, Math.floor(allStrikes.length / 5))
  for (let i = 0; i < allStrikes.length; i += strikeStep) {
    const x = xOf(allStrikes[i])
    ctx.fillText(allStrikes[i].toFixed(2), x, H - pad.bottom + 14)
  }

  // Spot price line
  if (spotPrice) {
    const sx = xOf(spotPrice)
    if (sx >= pad.left && sx <= W - pad.right) {
      ctx.strokeStyle = 'rgba(240,160,48,0.4)'
      ctx.lineWidth = 1
      ctx.setLineDash([4, 3])
      ctx.beginPath(); ctx.moveTo(sx, pad.top); ctx.lineTo(sx, H - pad.bottom); ctx.stroke()
      ctx.setLineDash([])
      ctx.fillStyle = 'vars.accent'
      ctx.font = '9px var(--font-mono)'
      ctx.textAlign = 'center'
      ctx.fillText('现价', sx, pad.top - 6)
    }
  }

  // Call smile
  if (calls.length > 1) {
    ctx.beginPath()
    const sorted = [...calls].sort((a, b) => a.strike - b.strike)
    ctx.moveTo(xOf(sorted[0].strike), yOf(sorted[0].iv * 100))
    for (let i = 1; i < sorted.length; i++) {
      ctx.lineTo(xOf(sorted[i].strike), yOf(sorted[i].iv * 100))
    }
    ctx.strokeStyle = 'vars.up'
    ctx.lineWidth = 2
    ctx.stroke()
    // Dots
    for (const c of sorted) {
      ctx.beginPath()
      ctx.arc(xOf(c.strike), yOf(c.iv * 100), 3, 0, Math.PI * 2)
      ctx.fillStyle = 'vars.up'
      ctx.fill()
    }
  }

  // Put smile
  if (puts.length > 1) {
    ctx.beginPath()
    const sorted = [...puts].sort((a, b) => a.strike - b.strike)
    ctx.moveTo(xOf(sorted[0].strike), yOf(sorted[0].iv * 100))
    for (let i = 1; i < sorted.length; i++) {
      ctx.lineTo(xOf(sorted[i].strike), yOf(sorted[i].iv * 100))
    }
    ctx.strokeStyle = 'vars.down'
    ctx.lineWidth = 2
    ctx.stroke()
    for (const p of sorted) {
      ctx.beginPath()
      ctx.arc(xOf(p.strike), yOf(p.iv * 100), 3, 0, Math.PI * 2)
      ctx.fillStyle = 'vars.down'
      ctx.fill()
    }
  }

  // Legend
  ctx.font = '11px var(--font-sans)'
  ctx.fillStyle = 'vars.up'
  ctx.textAlign = 'left'
  ctx.fillText('● 认购', pad.left, 16)
  ctx.fillStyle = 'vars.down'
  ctx.fillText('● 认沽', pad.left + 70, 16)
  ctx.fillStyle = vars.textMuted
  ctx.fillText('波动率微笑', pad.left + 140, 16)
}

function renderTermChart() {
  const canvas = termChart.value
  if (!canvas || !termData.value.length) return
  const ctx = canvas.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)
  const W = rect.width, H = rect.height
  const data = termData.value

  const ivs = data.map(d => d.atm_iv * 100)
  const minIV = Math.min(...ivs) * 0.95
  const maxIV = Math.max(...ivs) * 1.05
  const range = maxIV - minIV || 1

  const pad = { top: 24, right: 50, bottom: 32, left: 56 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const xOf = (i) => pad.left + i / Math.max(data.length - 1, 1) * cw
  const yOf = (v) => pad.top + ch - (v - minIV) / range * ch

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = vars.border
  ctx.lineWidth = 1
  for (let i = 0; i <= 5; i++) {
    const y = pad.top + ch * i / 5
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // Y labels
  ctx.fillStyle = vars.textDim
  ctx.font = '10px var(--font-mono)'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 5; i++) {
    const v = maxIV - range * i / 5
    const y = pad.top + ch * i / 5
    ctx.fillText(v.toFixed(1) + '%', pad.left - 8, y + 3)
  }

  // X labels
  ctx.textAlign = 'center'
  for (let i = 0; i < data.length; i++) {
    const x = xOf(i)
    const exp = data[i].expiry
    const label = exp ? exp.slice(4, 6) + '/' + exp.slice(6, 8) : ''
    ctx.fillText(label, x, H - pad.bottom + 14)
  }

  // Area fill
  ctx.beginPath()
  ctx.moveTo(xOf(0), yOf(ivs[0]))
  for (let i = 1; i < ivs.length; i++) {
    ctx.lineTo(xOf(i), yOf(ivs[i]))
  }
  ctx.lineTo(xOf(ivs.length - 1), pad.top + ch)
  ctx.lineTo(xOf(0), pad.top + ch)
  ctx.closePath()
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch)
  grad.addColorStop(0, 'rgba(240,160,48,0.2)')
  grad.addColorStop(1, 'rgba(240,160,48,0.02)')
  ctx.fillStyle = grad
  ctx.fill()

  // Line
  ctx.beginPath()
  ctx.moveTo(xOf(0), yOf(ivs[0]))
  for (let i = 1; i < ivs.length; i++) {
    ctx.lineTo(xOf(i), yOf(ivs[i]))
  }
  ctx.strokeStyle = 'vars.accent'
  ctx.lineWidth = 2
  ctx.shadowColor = 'vars.accent'
  ctx.shadowBlur = 6
  ctx.stroke()
  ctx.shadowBlur = 0

  // Dots
  for (let i = 0; i < ivs.length; i++) {
    ctx.beginPath()
    ctx.arc(xOf(i), yOf(ivs[i]), 4, 0, Math.PI * 2)
    ctx.fillStyle = 'vars.accent'
    ctx.fill()
    ctx.strokeStyle = 'vars.bgPrimary'
    ctx.lineWidth = 2
    ctx.stroke()
  }

  // Title
  ctx.fillStyle = vars.textMuted
  ctx.font = '11px var(--font-sans)'
  ctx.textAlign = 'left'
  ctx.fillText('IV期限结构', pad.left, 16)
}

// ── Watchers ──
watch(selectedTarget, async (val) => {
  selectedExpiry.value = ''
  await fetchExpiries(val)
  await loadAllData()
})

watch(selectedExpiry, async () => {
  if (activeTab.value === 'kline') await fetchKline()
  else if (activeTab.value === 'surface') { await fetchSurface(); await fetchSmile() }
  else if (activeTab.value === 'smile') { await fetchSmile(); await fetchSurface() }
})

watch(activeTab, async (tab) => {
  if (tab === 'kline') await fetchKline()
  else if (tab === 'surface') { await fetchSurface(); await fetchSmile() }
  else if (tab === 'smile') { await fetchSmile(); await fetchSurface() }
  else if (tab === 'term') await fetchTerm()
  else if (tab === 'surface3d') await fetchSurface3D()
  else if (tab === 'dashboard') await fetchDashboard()
  else if (tab === 'dashboardPanel') await fetchDashboard()
})

// ── Lifecycle ──
onMounted(async () => {
  await loadAllData()
  // Auto refresh every 60s
  refreshTimer = setInterval(async () => {
    if (activeTab.value === 'kline') await fetchKline()
    else if (activeTab.value === 'surface') { await fetchSurface(); await fetchSmile() }
    else if (activeTab.value === 'smile') { await fetchSmile(); await fetchSurface() }
    else if (activeTab.value === 'term') await fetchTerm()
    else if (activeTab.value === 'surface3d') await fetchSurface3D()
    else if (activeTab.value === 'dashboard') await fetchDashboard()
    else if (activeTab.value === 'dashboardPanel') await fetchDashboard()
  }, 60000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

// ── Helpers ──
function fmtPct(v) {
  if (v == null) return '--'
  return (Number(v)).toFixed(2) + '%'
}
function chgClass(v) {
  if (v == null) return 'val-neu'
  return Number(v) >= 0 ? 'val-up' : 'val-down'
}
</script>

<template>
  <div class="vol-page" v-if="!loading">
    <!-- ═══ TOP BAR ═══ -->
    <div class="vol-topbar">
      <div class="vol-title">
        <span class="vol-title-icon">📊</span>
        <h1>波动率分析</h1>
      </div>

      <!-- Target selector -->
      <div class="vol-controls">
        <div class="vol-target-tabs">
          <button
            v-for="t in targetOptions"
            :key="t.code"
            :class="['vol-target-tab', { active: selectedTarget === t.code }]"
            @click="selectedTarget = t.code"
          >
            {{ t.name }}
          </button>
        </div>

        <div class="vol-expiry-select" v-if="expiries.length">
          <label>到期日</label>
          <select v-model="selectedExpiry" class="vol-select">
            <option v-for="exp in expiries" :key="exp" :value="exp">
              {{ exp.slice(0,4) }}-{{ exp.slice(4,6) }}-{{ exp.slice(6,8) }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- ═══ IV STATS BAR ═══ -->
    <div class="vol-stats-bar">
      <div class="vol-stat">
        <span class="vol-stat-label">当前IV</span>
        <span class="vol-stat-val accent">{{ ivStats.current }}%</span>
      </div>
      <div class="vol-stat">
        <span class="vol-stat-label">IV变化</span>
        <span class="vol-stat-val" :class="chgClass(ivStats.change)">{{ ivStats.change }}%</span>
      </div>
      <div class="vol-stat">
        <span class="vol-stat-label">最高</span>
        <span class="vol-stat-val">{{ ivStats.high }}%</span>
      </div>
      <div class="vol-stat">
        <span class="vol-stat-label">最低</span>
        <span class="vol-stat-val">{{ ivStats.low }}%</span>
      </div>
      <div class="vol-stat">
        <span class="vol-stat-label">平均</span>
        <span class="vol-stat-val">{{ ivStats.avg }}%</span>
      </div>
      <div class="vol-stat">
        <span class="vol-stat-label">标的</span>
        <span class="vol-stat-val">{{ selectedTargetName }}</span>
      </div>
    </div>

    <!-- ═══ TAB NAV ═══ -->
    <div class="vol-tabs">
      <button :class="['vol-tab', { active: activeTab === 'dashboardPanel' }]" @click="activeTab = 'dashboardPanel'">
        <span class="vol-tab-icon">📊</span>
        综合仪表盘
      </button>
      <button :class="['vol-tab', { active: activeTab === 'dashboard' }]" @click="activeTab = 'dashboard'">
        <span class="vol-tab-icon">📈</span>
        综合走势
      </button>
      <button :class="['vol-tab', { active: activeTab === 'kline' }]" @click="activeTab = 'kline'">
        <span class="vol-tab-icon">📉</span>
        IV走势
      </button>
      <button :class="['vol-tab', { active: activeTab === 'smile' }]" @click="activeTab = 'smile'">
        <span class="vol-tab-icon">😊</span>
        波动率微笑
      </button>
      <button :class="['vol-tab', { active: activeTab === 'surface3d' }]" @click="activeTab = 'surface3d'">
        <span class="vol-tab-icon">🏔️</span>
        3D曲面
      </button>
      <button :class="['vol-tab', { active: activeTab === 'surface' }]" @click="activeTab = 'surface'">
        <span class="vol-tab-icon">📊</span>
        IV对比
      </button>
      <button :class="['vol-tab', { active: activeTab === 'term' }]" @click="activeTab = 'term'">
        <span class="vol-tab-icon">📅</span>
        期限结构
      </button>
    </div>

    <!-- ═══ CHART AREA ═══ -->
    <div class="vol-chart-area">
      <!-- 综合仪表盘 (2x2) -->
      <div class="vol-chart-panel" v-show="activeTab === 'dashboardPanel'">
        <div class="vol-chart-header">
          <h3>综合仪表盘 — {{ selectedTargetName }}</h3>
          <span class="vol-chart-sub">标的 + HV + IV + PCR · 一屏概览</span>
        </div>
        <DashboardPanel :data="dashboardData" :latest="dashboardLatest" :loading="loading" :targetName="selectedTargetName" />
      </div>

      <!-- 综合走势 -->
      <div class="vol-chart-panel" v-show="activeTab === 'dashboard'">
        <div class="vol-chart-header">
          <h3>综合走势 — {{ selectedTargetName }}</h3>
          <span class="vol-chart-sub">标的 + HV + IV + PCR</span>
        </div>
        <DashboardChart :data="dashboardData" :latest="dashboardLatest" :loading="loading" />
      </div>
      <!-- IV KLine -->
      <div class="vol-chart-panel" v-show="activeTab === 'kline'">
        <div class="vol-chart-header">
          <h3>IV走势 — {{ selectedTargetName }} {{ selectedExpiry ? selectedExpiry.slice(4,6) + '/' + selectedExpiry.slice(6,8) : '' }}</h3>
          <span class="vol-chart-sub">近30日平价期权隐含波动率</span>
        </div>
        <div class="vol-chart-wrap">
          <canvas ref="klineChart" class="vol-canvas"></canvas>
        </div>
        <div class="vol-chart-footer" v-if="klineData.length">
          <span>数据点: {{ klineData.length }}</span>
          <span>更新: {{ klineData[klineData.length-1]?.ts?.slice(0,16) || '--' }}</span>
        </div>
      </div>

      <!-- Smile -->
      <div class="vol-chart-panel" v-show="activeTab === 'smile'">
        <div class="vol-chart-header">
          <h3>波动率微笑 — {{ selectedTargetName }} {{ selectedExpiry ? selectedExpiry.slice(4,6) + '/' + selectedExpiry.slice(6,8) : '' }}</h3>
          <span class="vol-chart-sub">各行权价IV分布（现价标记）</span>
        </div>
        <div class="vol-chart-wrap">
          <canvas ref="smileChart" class="vol-canvas"></canvas>
        </div>
      </div>

      <!-- Surface -->
      <div class="vol-chart-panel" v-show="activeTab === 'surface'">
        <div class="vol-chart-header">
          <h3>波动率曲面 — {{ selectedTargetName }} {{ selectedExpiry ? selectedExpiry.slice(4,6) + '/' + selectedExpiry.slice(6,8) : '' }}</h3>
          <span class="vol-chart-sub">认购/认沽IV对比</span>
        </div>
        <div class="vol-chart-wrap">
          <canvas ref="surfaceChart" class="vol-canvas"></canvas>
        </div>
      </div>

      <!-- Term Structure -->
      <div class="vol-chart-panel" v-show="activeTab === 'term'">
        <div class="vol-chart-header">
          <h3>IV期限结构 — {{ selectedTargetName }}</h3>
          <span class="vol-chart-sub">各到期日平价IV</span>
        </div>
        <div class="vol-chart-wrap">
          <canvas ref="termChart" class="vol-canvas"></canvas>
        </div>
        <div class="vol-term-table" v-if="termData.length">
          <table>
            <thead>
              <tr><th>到期日</th><th>ATM IV</th><th>标的价</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in termData" :key="t.expiry">
                <td>{{ t.expiry.slice(0,4) }}-{{ t.expiry.slice(4,6) }}-{{ t.expiry.slice(6,8) }}</td>
                <td class="val-mono accent">{{ fmtPct(t.atm_iv) }}</td>
                <td class="val-mono">{{ t.spot_price?.toFixed(3) || '--' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 3D Surface -->
      <div class="vol-chart-panel" v-show="activeTab === 'surface3d'">
        <div class="vol-chart-header">
          <h3>3D波动率曲面 — {{ selectedTargetName }}</h3>
          <span class="vol-chart-sub">行权价 × 到期日 × IV · 热力着色</span>
        </div>
        <Surface3D :data="surface3dData" v-model:optionType="surface3dType" />
      </div>
    </div>
  </div>

  <!-- Loading -->
  <div class="vol-loading" v-else>
    <div class="vol-loading-spinner"></div>
    <p>加载波动率数据...</p>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════
   Volatility Analysis Page
   ═══════════════════════════════════════════ */
.vol-page {
  animation: fadeIn 0.35s ease;
  padding-bottom: 40px;
}

/* ═══ TOP BAR ═══ */
.vol-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
}
.vol-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.vol-title-icon {
  font-size: 24px;
}
.vol-title h1 {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.vol-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.vol-target-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px;
}
.vol-target-tab {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.vol-target-tab:hover {
  color: var(--text-primary);
  background: var(--bg-row-hover);
}
.vol-target-tab.active {
  background: var(--accent);
  color: var(--bg-deep);
}
.vol-expiry-select {
  display: flex;
  align-items: center;
  gap: 8px;
}
.vol-expiry-select label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
}
.vol-select {
  padding: 6px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
  cursor: pointer;
}
.vol-select:focus {
  border-color: var(--accent-dim);
}

/* ═══ STATS BAR ═══ */
.vol-stats-bar {
  display: flex;
  gap: 24px;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.vol-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.vol-stat-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.vol-stat-val {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}
.vol-stat-val.accent {
  color: var(--accent);
}

/* ═══ TABS ═══ */
.vol-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
}
.vol-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: -1px;
}
.vol-tab:hover {
  color: var(--text-secondary);
  border-bottom-color: var(--border-light);
}
.vol-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.vol-tab-icon {
  font-size: 14px;
}

/* ═══ CHART AREA ═══ */
.vol-chart-area {
  min-height: 400px;
}
.vol-chart-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  box-shadow: var(--shadow-card);
}
.vol-chart-header {
  margin-bottom: 16px;
}
.vol-chart-header h3 {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}
.vol-chart-sub {
  font-size: 12px;
  color: var(--text-muted);
}
.vol-chart-wrap {
  position: relative;
  margin-bottom: 12px;
}
.vol-canvas {
  width: 100%;
  height: 360px;
  border-radius: 6px;
  display: block;
}
.vol-chart-footer {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

/* ═══ TERM TABLE ═══ */
.vol-term-table {
  margin-top: 16px;
  overflow-x: auto;
}
.vol-term-table table {
  width: 100%;
  border-collapse: collapse;
}
.vol-term-table th {
  padding: 8px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
}
.vol-term-table td {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border);
}
.vol-term-table tr:hover td {
  background: var(--bg-row-hover);
}

/* ═══ Loading ═══ */
.vol-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  color: var(--text-muted);
  gap: 16px;
}
.vol-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ═══ Responsive ═══ */
@media (max-width: 768px) {
  .vol-topbar {
    flex-direction: column;
    align-items: flex-start;
  }
  .vol-stats-bar {
    gap: 16px;
  }
  .vol-tabs {
    overflow-x: auto;
  }
  .vol-canvas {
    height: 280px;
  }
  .vol-controls { width: 100%; flex-direction: column; align-items: flex-start; gap: 10px; }
  .vol-target-tabs { width: 100%; overflow-x: auto; flex-wrap: nowrap; }
  .vol-target-tab { flex: 1; min-width: 60px; padding: 6px 8px; font-size: 11px; }
  .vol-expiry-select { width: 100%; }
  .vol-select { flex: 1; }
  .vol-stats-bar { gap: 12px; padding: 12px 14px; }
  .vol-stat-val { font-size: 15px; }
  .vol-tabs { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .vol-tab { padding: 8px 12px; font-size: 12px; white-space: nowrap; }
  .vol-chart-panel { padding: 14px; }
  .vol-chart-header h3 { font-size: 13px; }
}
</style>
