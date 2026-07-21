<script setup>
/**
 * 综合仪表盘面板 (2x2 网格)
 * 左上: 标的价格走势 (面积图)
 * 右上: HV/IV 对比 (多线图)
 * 左下: PCR 量比 + IV Skew (柱状+折线)
 * 右下: IV 期限结构 (柱状图)
 */
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { getCssVars } from '@/utils/cssVar'

const props = defineProps({
  data: { type: Array, default: () => [] },
  latest: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  targetName: { type: String, default: '' }
})

// Canvas refs
const spotCanvas = ref(null)
const hvivCanvas = ref(null)
const pcrCanvas = ref(null)
const termCanvas = ref(null)

// ── 工具函数 ──
function fmtPct(v) {
  if (v == null || isNaN(v)) return '--'
  return (Number(v) * 100).toFixed(1) + '%'
}
function fmtPrice(v) {
  if (v == null || isNaN(v)) return '--'
  return Number(v).toFixed(3)
}
function chgColor(v) {
  if (v == null) return 'var(--text-muted)'
  return Number(v) >= 0 ? '#dc6464' : '#3cc4a0'
}

// ── 1. 标的价格走势 ──
function renderSpotChart() {
  const cvs = spotCanvas.value
  if (!cvs) return
  const data = props.data
  const ctx = cvs.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const W = cvs.clientWidth, H = cvs.clientHeight
  cvs.width = W * dpr; cvs.height = H * dpr
  ctx.scale(dpr, dpr)

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  if (!data.length) {
    ctx.fillStyle = vars.textDim; ctx.font = '12px ' + vars.fontSans
    ctx.textAlign = 'center'; ctx.fillText('暂无数据', W / 2, H / 2)
    return
  }

  const pad = { top: 28, right: 40, bottom: 24, left: 40 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const closes = data.map(d => d.close)
  const minC = Math.min(...closes) * 0.998
  const maxC = Math.max(...closes) * 1.002
  const range = maxC - minC || 0.01

  const xOf = (i) => pad.left + i / Math.max(data.length - 1, 1) * cw
  const yOf = (v) => pad.top + ch - (v - minC) / range * ch

  // Grid
  ctx.strokeStyle = vars.border; ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ch * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // Area fill
  ctx.beginPath()
  ctx.moveTo(xOf(0), yOf(closes[0]))
  for (let i = 1; i < closes.length; i++) ctx.lineTo(xOf(i), yOf(closes[i]))
  ctx.lineTo(xOf(closes.length - 1), pad.top + ch)
  ctx.lineTo(xOf(0), pad.top + ch)
  ctx.closePath()
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch)
  grad.addColorStop(0, 'rgba(100,180,255,0.18)')
  grad.addColorStop(1, 'rgba(100,180,255,0.02)')
  ctx.fillStyle = grad; ctx.fill()

  // Line
  ctx.beginPath()
  ctx.moveTo(xOf(0), yOf(closes[0]))
  for (let i = 1; i < closes.length; i++) ctx.lineTo(xOf(i), yOf(closes[i]))
  ctx.strokeStyle = '#64b4ff'; ctx.lineWidth = 2
  ctx.shadowColor = '#64b4ff'; ctx.shadowBlur = 4; ctx.stroke(); ctx.shadowBlur = 0

  // Last dot + label
  const lx = xOf(closes.length - 1), ly = yOf(closes[closes.length - 1])
  ctx.beginPath(); ctx.arc(lx, ly, 4, 0, Math.PI * 2)
  ctx.fillStyle = '#64b4ff'; ctx.fill()
  ctx.strokeStyle = '#080e1a'; ctx.lineWidth = 2; ctx.stroke()

  ctx.fillStyle = '#64b4ff'; ctx.font = 'bold 10px var(--font-mono)'; ctx.textAlign = 'left'
  const lbl = closes[closes.length - 1].toFixed(3)
  const lblX = lx + 10 < W - pad.right ? lx + 10 : lx - 50
  ctx.fillText(lbl, lblX, ly + 4)

  // Y labels
  ctx.fillStyle = vars.textDim; ctx.font = '9px ' + vars.fontMono; ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = maxC - range * i / 4
    ctx.fillText(v.toFixed(3), pad.left - 6, pad.top + ch * i / 4 + 3)
  }

  // X labels
  ctx.textAlign = 'center'; ctx.fillStyle = vars.textDim
  const step = Math.max(1, Math.floor(data.length / 5))
  for (let i = 0; i < data.length; i += step) {
    ctx.fillText(data[i].date?.slice(5, 10) || '', xOf(i), H - pad.bottom + 12)
  }

  // Title
  ctx.fillStyle = vars.textMuted; ctx.font = '11px ' + vars.fontSans; ctx.textAlign = 'left'
  ctx.fillText('标的价格', pad.left, 16)
}

// ── 2. HV/IV 对比 ──
function renderHVIVChart() {
  const cvs = hvivCanvas.value
  if (!cvs) return
  const data = props.data
  const ctx = cvs.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const W = cvs.clientWidth, H = cvs.clientHeight
  cvs.width = W * dpr; cvs.height = H * dpr
  ctx.scale(dpr, dpr)

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  if (!data.length) {
    ctx.fillStyle = vars.textDim; ctx.font = '12px ' + vars.fontSans
    ctx.textAlign = 'center'; ctx.fillText('暂无数据', W / 2, H / 2)
    return
  }

  const pad = { top: 28, right: 40, bottom: 24, left: 40 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  // Collect all vol values for range
  const allVols = []
  data.forEach(d => {
    if (d.iv_atm) allVols.push(d.iv_atm * 100)
    if (d.iv_weighted) allVols.push(d.iv_weighted * 100)
    if (d.hv5) allVols.push(d.hv5 * 100)
    if (d.hv20) allVols.push(d.hv20 * 100)
    if (d.hv60) allVols.push(d.hv60 * 100)
  })
  const minV = allVols.length ? Math.min(...allVols) * 0.9 : 5
  const maxV = allVols.length ? Math.max(...allVols) * 1.1 : 60
  const vRange = maxV - minV || 1

  const xOf = (i) => pad.left + i / Math.max(data.length - 1, 1) * cw
  const yOf = (v) => pad.top + ch - (v - minV) / vRange * ch

  // Grid
  ctx.strokeStyle = vars.border; ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ch * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // HV60 (最淡)
  const hv60Pts = data.map((d, i) => d.hv60 ? { x: xOf(i), y: yOf(d.hv60 * 100) } : null).filter(Boolean)
  if (hv60Pts.length > 1) {
    ctx.beginPath(); ctx.moveTo(hv60Pts[0].x, hv60Pts[0].y)
    for (let i = 1; i < hv60Pts.length; i++) ctx.lineTo(hv60Pts[i].x, hv60Pts[i].y)
    ctx.strokeStyle = 'rgba(60,196,160,0.3)'; ctx.lineWidth = 1; ctx.stroke()
  }

  // HV20
  const hv20Pts = data.map((d, i) => d.hv20 ? { x: xOf(i), y: yOf(d.hv20 * 100) } : null).filter(Boolean)
  if (hv20Pts.length > 1) {
    ctx.beginPath(); ctx.moveTo(hv20Pts[0].x, hv20Pts[0].y)
    for (let i = 1; i < hv20Pts.length; i++) ctx.lineTo(hv20Pts[i].x, hv20Pts[i].y)
    ctx.strokeStyle = '#3cc4a0'; ctx.lineWidth = 1.5; ctx.setLineDash([3, 2]); ctx.stroke(); ctx.setLineDash([])
  }

  // HV5
  const hv5Pts = data.map((d, i) => d.hv5 ? { x: xOf(i), y: yOf(d.hv5 * 100) } : null).filter(Boolean)
  if (hv5Pts.length > 1) {
    ctx.beginPath(); ctx.moveTo(hv5Pts[0].x, hv5Pts[0].y)
    for (let i = 1; i < hv5Pts.length; i++) ctx.lineTo(hv5Pts[i].x, hv5Pts[i].y)
    ctx.strokeStyle = '#3cc4a0'; ctx.lineWidth = 1; ctx.setLineDash([2, 2]); ctx.stroke(); ctx.setLineDash([])
  }

  // IV ATM
  const ivPts = data.map((d, i) => d.iv_atm ? { x: xOf(i), y: yOf(d.iv_atm * 100) } : null).filter(Boolean)
  if (ivPts.length > 1) {
    ctx.beginPath(); ctx.moveTo(ivPts[0].x, ivPts[0].y)
    for (let i = 1; i < ivPts.length; i++) ctx.lineTo(ivPts[i].x, ivPts[i].y)
    ctx.strokeStyle = '#f0a030'; ctx.lineWidth = 2; ctx.stroke()
  }

  // IV Weighted
  const ivwPts = data.map((d, i) => d.iv_weighted ? { x: xOf(i), y: yOf(d.iv_weighted * 100) } : null).filter(Boolean)
  if (ivwPts.length > 1) {
    ctx.beginPath(); ctx.moveTo(ivwPts[0].x, ivwPts[0].y)
    for (let i = 1; i < ivwPts.length; i++) ctx.lineTo(ivwPts[i].x, ivwPts[i].y)
    ctx.strokeStyle = '#f0a030'; ctx.lineWidth = 1; ctx.setLineDash([4, 2]); ctx.stroke(); ctx.setLineDash([])
  }

  // Y labels
  ctx.fillStyle = vars.textDim; ctx.font = '9px ' + vars.fontMono; ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = maxV - vRange * i / 4
    ctx.fillText(v.toFixed(0) + '%', pad.left - 6, pad.top + ch * i / 4 + 3)
  }

  // X labels
  ctx.textAlign = 'center'; ctx.fillStyle = vars.textDim
  const step = Math.max(1, Math.floor(data.length / 5))
  for (let i = 0; i < data.length; i += step) {
    ctx.fillText(data[i].date?.slice(5, 10) || '', xOf(i), H - pad.bottom + 12)
  }

  // Legend
  ctx.font = '10px ' + vars.fontSans; ctx.textAlign = 'left'
  let lx = pad.left
  ctx.fillStyle = vars.accent; ctx.fillText('— IV', lx, 16); lx += 45
  ctx.fillStyle = vars.down; ctx.fillText('-- HV20', lx, 16); lx += 55
  ctx.fillStyle = 'rgba(60,196,160,0.5)'; ctx.fillText('· HV60', lx, 16)

  // Title
  ctx.fillStyle = vars.textMuted; ctx.font = '11px ' + vars.fontSans
  ctx.fillText('HV / IV 对比', pad.left + 170, 16)
}

// ── 3. PCR 量比 + IV Skew ──
function renderPCRChart() {
  const cvs = pcrCanvas.value
  if (!cvs) return
  const data = props.data
  const ctx = cvs.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const W = cvs.clientWidth, H = cvs.clientHeight
  cvs.width = W * dpr; cvs.height = H * dpr
  ctx.scale(dpr, dpr)

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  if (!data.length) {
    ctx.fillStyle = vars.textDim; ctx.font = '12px ' + vars.fontSans
    ctx.textAlign = 'center'; ctx.fillText('暂无数据', W / 2, H / 2)
    return
  }

  const pad = { top: 28, right: 40, bottom: 24, left: 40 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const pcrVals = data.map(d => d.pcr_ratio).filter(v => v != null)
  const skewVals = data.map(d => d.pcr_iv_skew).filter(v => v != null)
  const allP = [...pcrVals, ...skewVals, 1.0]
  const minP = Math.max(0, Math.min(...allP) * 0.8)
  const maxP = Math.max(...allP) * 1.2
  const pRange = maxP - minP || 0.1

  const xOf = (i) => pad.left + i / Math.max(data.length - 1, 1) * cw
  const yOf = (v) => pad.top + ch - (v - minP) / pRange * ch

  // Grid
  ctx.strokeStyle = vars.border; ctx.lineWidth = 1
  for (let i = 0; i <= 3; i++) {
    const y = pad.top + ch * i / 3
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // 1.0 参考线
  if (minP < 1.0 && maxP > 1.0) {
    const y1 = yOf(1.0)
    ctx.strokeStyle = 'rgba(240,160,48,0.3)'; ctx.lineWidth = 1; ctx.setLineDash([3, 3])
    ctx.beginPath(); ctx.moveTo(pad.left, y1); ctx.lineTo(W - pad.right, y1); ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = '#f0a030'; ctx.font = '9px var(--font-mono)'; ctx.textAlign = 'right'
    ctx.fillText('1.0', pad.left - 4, y1 + 3)
  }

  // PCR 柱状图
  const barW = Math.max(1, cw / data.length * 0.5)
  for (let i = 0; i < data.length; i++) {
    if (data[i].pcr_ratio == null) continue
    const x = xOf(i)
    const y = yOf(data[i].pcr_ratio)
    const baseY = yOf(Math.max(minP, Math.min(maxP, 1.0)))
    const h = baseY - y
    ctx.fillStyle = data[i].pcr_ratio >= 1.0 ? 'rgba(220,80,80,0.45)' : 'rgba(80,200,120,0.45)'
    ctx.fillRect(x - barW / 2, Math.min(y, baseY), barW, Math.abs(h))
  }

  // IV Skew 线
  const skewPts = data.map((d, i) => d.pcr_iv_skew ? { x: xOf(i), y: yOf(d.pcr_iv_skew) } : null).filter(Boolean)
  if (skewPts.length > 1) {
    ctx.beginPath(); ctx.moveTo(skewPts[0].x, skewPts[0].y)
    for (let i = 1; i < skewPts.length; i++) ctx.lineTo(skewPts[i].x, skewPts[i].y)
    ctx.strokeStyle = '#e8883e'; ctx.lineWidth = 1.5; ctx.stroke()
    for (const p of skewPts) {
      ctx.beginPath(); ctx.arc(p.x, p.y, 2, 0, Math.PI * 2)
      ctx.fillStyle = '#e8883e'; ctx.fill()
    }
  }

  // Y labels
  ctx.fillStyle = vars.textDim; ctx.font = '9px ' + vars.fontMono; ctx.textAlign = 'right'
  for (let i = 0; i <= 3; i++) {
    const v = maxP - pRange * i / 3
    ctx.fillText(v.toFixed(2), pad.left - 6, pad.top + ch * i / 3 + 3)
  }

  // X labels
  ctx.textAlign = 'center'; ctx.fillStyle = vars.textDim
  const step = Math.max(1, Math.floor(data.length / 5))
  for (let i = 0; i < data.length; i += step) {
    ctx.fillText(data[i].date?.slice(5, 10) || '', xOf(i), H - pad.bottom + 12)
  }

  // Legend
  ctx.font = '10px ' + vars.fontSans; ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(220,80,80,0.7)'; ctx.fillText('■ PCR量比', pad.left, 16)
  ctx.fillStyle = vars.up; ctx.fillText('— IV Skew', pad.left + 85, 16)

  // Title
  ctx.fillStyle = vars.textMuted; ctx.font = '11px ' + vars.fontSans
  ctx.fillText('PCR 情绪指标', pad.left + 180, 16)
}

// ── 4. IV 期限结构 (简化柱状) ──
function renderTermChart() {
  const cvs = termCanvas.value
  if (!cvs) return
  const data = props.data
  const ctx = cvs.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const W = cvs.clientWidth, H = cvs.clientHeight
  cvs.width = W * dpr; cvs.height = H * dpr
  ctx.scale(dpr, dpr)

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // 从最新一条数据取各期限IV (这里用历史数据的 iv_atm 近似)
  // 实际期限结构需要后端 term 接口，这里展示 HV 期限结构作为替代
  if (!data.length) {
    ctx.fillStyle = vars.textDim; ctx.font = '12px ' + vars.fontSans
    ctx.textAlign = 'center'; ctx.fillText('暂无数据', W / 2, H / 2)
    return
  }

  const pad = { top: 28, right: 40, bottom: 32, left: 40 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  // 取最近20个数据点，展示 HV5/HV20/HV60 的最近值分布
  const recent = data.slice(-20)
  const ivVals = recent.map(d => d.iv_atm).filter(v => v != null)
  const hv5Vals = recent.map(d => d.hv5).filter(v => v != null)
  const hv20Vals = recent.map(d => d.hv20).filter(v => v != null)
  const hv60Vals = recent.map(d => d.hv60).filter(v => v != null)

  // 计算均值
  const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
  const bars = [
    { label: 'IV(ATM)', val: avg(ivVals) * 100, color: '#f0a030' },
    { label: 'HV5', val: avg(hv5Vals) * 100, color: '#3cc4a0' },
    { label: 'HV20', val: avg(hv20Vals) * 100, color: '#3cc4a0' },
    { label: 'HV60', val: avg(hv60Vals) * 100, color: '#3cc4a0' },
  ].filter(b => b.val > 0)

  if (!bars.length) {
    ctx.fillStyle = '#3a4a60'; ctx.font = '12px var(--font-sans)'
    ctx.textAlign = 'center'; ctx.fillText('暂无数据', W / 2, H / 2)
    return
  }

  const maxVal = Math.max(...bars.map(b => b.val)) * 1.2 || 1
  const barW = Math.min(60, cw / bars.length * 0.5)
  const gap = cw / bars.length

  // Grid
  ctx.strokeStyle = vars.border; ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ch * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // Y labels
  ctx.fillStyle = vars.textDim; ctx.font = '9px ' + vars.fontMono; ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = maxVal * (4 - i) / 4
    ctx.fillText(v.toFixed(0) + '%', pad.left - 6, pad.top + ch * i / 4 + 3)
  }

  // Bars
  bars.forEach((b, i) => {
    const x = pad.left + gap * i + gap / 2
    const barH = (b.val / maxVal) * ch
    const y = pad.top + ch - barH

    // Bar
    const grad = ctx.createLinearGradient(0, y, 0, pad.top + ch)
    grad.addColorStop(0, b.color + 'cc')
    grad.addColorStop(1, b.color + '22')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.roundRect(x - barW / 2, y, barW, barH, [3, 3, 0, 0])
    ctx.fill()

    // Value on top
    ctx.fillStyle = b.color; ctx.font = 'bold 10px var(--font-mono)'; ctx.textAlign = 'center'
    ctx.fillText(b.val.toFixed(1) + '%', x, y - 5)

    // Label below
    ctx.fillStyle = '#535f75'; ctx.font = '10px var(--font-sans)'
    ctx.fillText(b.label, x, H - pad.bottom + 14)
  })

  // Title
  ctx.fillStyle = vars.textMuted; ctx.font = '11px ' + vars.fontSans; ctx.textAlign = 'left'
  ctx.fillText('波动率期限结构 (均值)', pad.left, 16)
}

// ── 渲染全部 ──
function renderAll() {
  renderSpotChart()
  renderHVIVChart()
  renderPCRChart()
  renderTermChart()
}

watch(() => props.data, () => { nextTick(renderAll) }, { deep: true })

onMounted(() => {
  nextTick(renderAll)
  window.addEventListener('resize', renderAll)
})

onUnmounted(() => {
  window.removeEventListener('resize', renderAll)
})
</script>

<template>
  <div class="dp-wrap" v-if="!loading && data.length">
    <!-- 最新数据卡片条 -->
    <div class="dp-cards" v-if="latest">
      <div class="dp-card dp-card-spot">
        <span class="dp-card-label">标的价格</span>
        <span class="dp-card-val">{{ fmtPrice(latest.close) }}</span>
      </div>
      <div class="dp-card">
        <span class="dp-card-label">IV (ATM)</span>
        <span class="dp-card-val dp-orange">{{ fmtPct(latest.iv_atm) }}</span>
      </div>
      <div class="dp-card">
        <span class="dp-card-label">IV (加权)</span>
        <span class="dp-card-val dp-orange">{{ fmtPct(latest.iv_weighted) }}</span>
      </div>
      <div class="dp-card">
        <span class="dp-card-label">HV20</span>
        <span class="dp-card-val dp-green">{{ fmtPct(latest.hv20) }}</span>
      </div>
      <div class="dp-card">
        <span class="dp-card-label">PCR 量比</span>
        <span class="dp-card-val" :style="{ color: latest.pcr_ratio >= 1 ? '#dc6464' : '#3cc4a0' }">
          {{ latest.pcr_ratio?.toFixed(2) || '--' }}
        </span>
      </div>
      <div class="dp-card">
        <span class="dp-card-label">IV Skew</span>
        <span class="dp-card-val dp-orange">{{ latest.pcr_iv_skew?.toFixed(2) || '--' }}</span>
      </div>
      <div class="dp-card">
        <span class="dp-card-label">HV/IV</span>
        <span class="dp-card-val">
          {{ latest.hv20 && latest.iv_atm ? (latest.hv20 / latest.iv_atm).toFixed(2) : '--' }}
        </span>
      </div>
      <div class="dp-card">
        <span class="dp-card-label">日期</span>
        <span class="dp-card-val dp-date">{{ latest.date || '--' }}</span>
      </div>
    </div>

    <!-- 2x2 图表网格 -->
    <div class="dp-grid">
      <!-- 左上: 标的价格 -->
      <div class="dp-cell">
        <canvas ref="spotCanvas" class="dp-canvas"></canvas>
      </div>

      <!-- 右上: HV/IV 对比 -->
      <div class="dp-cell">
        <canvas ref="hvivCanvas" class="dp-canvas"></canvas>
      </div>

      <!-- 左下: PCR -->
      <div class="dp-cell">
        <canvas ref="pcrCanvas" class="dp-canvas"></canvas>
      </div>

      <!-- 右下: 期限结构 -->
      <div class="dp-cell">
        <canvas ref="termCanvas" class="dp-canvas"></canvas>
      </div>
    </div>
  </div>

  <div class="dp-empty" v-else-if="!loading">
    <p>暂无走势数据，等待数据积累...</p>
  </div>
</template>

<style scoped>
.dp-wrap {
  width: 100%;
}

/* 数据卡片条 */
.dp-cards {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.dp-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  min-width: 72px;
}

.dp-card-spot {
  border-color: rgba(100, 180, 255, 0.3);
}

.dp-card-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.dp-card-val {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.dp-card-val.dp-orange { color: #f0a030; }
.dp-card-val.dp-green { color: #3cc4a0; }
.dp-card-val.dp-date { font-size: 12px; font-weight: 400; }

/* 2x2 网格 */
.dp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 12px;
}

.dp-cell {
  position: relative;
  background: #080e1a;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  height: 240px;
}

.dp-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.dp-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
