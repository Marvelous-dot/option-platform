<script setup>
/**
 * 综合走势面板
 * 叠加显示: 标的走势 + HV + IV + PCR
 * 主图: 标的价格(左轴) + IV/HV(右轴)
 * 副图: PCR 柱状图
 */
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { getCssVars } from '@/utils/cssVar'

// hex → rgba 转换
function hexToRgba(hex, alpha) {
  const clean = hex.replace('#', '').trim()
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  latest: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const mainCanvas = ref(null)
const pcrCanvas = ref(null)
const activeOverlay = ref('both') // both | iv | hv | none
const selectedHV = ref('hv20') // hv5 | hv10 | hv20 | hv60

// ── 绘制主图 ──
function renderMainChart() {
  const cvs = mainCanvas.value
  if (!cvs || !props.data.length) return
  const ctx = cvs.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const W = cvs.clientWidth
  const H = cvs.clientHeight
  cvs.width = W * dpr
  cvs.height = H * dpr
  ctx.scale(dpr, dpr)

  const data = props.data
  const pad = { top: 28, right: 56, bottom: 28, left: 56 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  // 背景
  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // 数据范围
  const closes = data.map(d => d.close)
  const minClose = Math.min(...closes) * 0.998
  const maxClose = Math.max(...closes) * 1.002
  const closeRange = maxClose - minClose || 0.01

  // IV/HV 范围 (右轴)
  const volValues = []
  data.forEach(d => {
    if (activeOverlay.value === 'both' || activeOverlay.value === 'iv') {
      if (d.iv_atm) volValues.push(d.iv_atm * 100)
      if (d.iv_weighted) volValues.push(d.iv_weighted * 100)
    }
    if (activeOverlay.value === 'both' || activeOverlay.value === 'hv') {
      const hvKey = selectedHV.value
      if (d[hvKey]) volValues.push(d[hvKey] * 100)
    }
  })
  const minVol = volValues.length ? Math.min(...volValues) * 0.9 : 10
  const maxVol = volValues.length ? Math.max(...volValues) * 1.1 : 50
  const volRange = maxVol - minVol || 1

  // 函数
  const xOf = (i) => pad.left + i / Math.max(data.length - 1, 1) * cw
  const yClose = (v) => pad.top + ch - (v - minClose) / closeRange * ch
  const yVol = (v) => pad.top + ch - (v - minVol) / volRange * ch

  // 网格
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

  // ── 标的走势 (面积填充) ──
  ctx.beginPath()
  ctx.moveTo(xOf(0), yClose(closes[0]))
  for (let i = 1; i < closes.length; i++) {
    ctx.lineTo(xOf(i), yClose(closes[i]))
  }
  ctx.lineTo(xOf(closes.length - 1), pad.top + ch)
  ctx.lineTo(xOf(0), pad.top + ch)
  ctx.closePath()
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch)
  grad.addColorStop(0, 'hexToRgba(vars.accent, 0.15)')
  grad.addColorStop(1, 'hexToRgba(vars.accent, 0.02)')
  ctx.fillStyle = grad
  ctx.fill()

  ctx.beginPath()
  ctx.moveTo(xOf(0), yClose(closes[0]))
  for (let i = 1; i < closes.length; i++) {
    ctx.lineTo(xOf(i), yClose(closes[i]))
  }
  ctx.strokeStyle = 'vars.accent'
  ctx.lineWidth = 2
  ctx.shadowColor = 'vars.accent'
  ctx.shadowBlur = 4
  ctx.stroke()
  ctx.shadowBlur = 0

  // 最新价标记
  const lastX = xOf(closes.length - 1)
  const lastY = yClose(closes[closes.length - 1])
  ctx.beginPath()
  ctx.arc(lastX, lastY, 5, 0, Math.PI * 2)
  ctx.fillStyle = 'vars.accent'
  ctx.fill()
  ctx.strokeStyle = 'vars.bgDeep'
  ctx.lineWidth = 2
  ctx.stroke()

  // 最新价标签
  ctx.fillStyle = 'vars.accent'
  ctx.font = 'bold 10px var(--font-mono)'
  ctx.textAlign = 'left'
  const priceLabel = closes[closes.length - 1].toFixed(3)
  const labelX = lastX + 8 < W - pad.right ? lastX + 8 : lastX - 50
  ctx.fillText(priceLabel, labelX, lastY + 4)

  // ── IV 曲线 ──
  if (activeOverlay.value === 'both' || activeOverlay.value === 'iv') {
    // ATM IV
    const ivPoints = data.map((d, i) => d.iv_atm ? { x: xOf(i), y: yVol(d.iv_atm * 100) } : null).filter(Boolean)
    if (ivPoints.length > 1) {
      ctx.beginPath()
      ctx.moveTo(ivPoints[0].x, ivPoints[0].y)
      for (let i = 1; i < ivPoints.length; i++) {
        ctx.lineTo(ivPoints[i].x, ivPoints[i].y)
      }
      ctx.strokeStyle = 'vars.accent'
      ctx.lineWidth = 1.5
      ctx.setLineDash([4, 2])
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Weighted IV
    const ivwPoints = data.map((d, i) => d.iv_weighted ? { x: xOf(i), y: yVol(d.iv_weighted * 100) } : null).filter(Boolean)
    if (ivwPoints.length > 1) {
      ctx.beginPath()
      ctx.moveTo(ivwPoints[0].x, ivwPoints[0].y)
      for (let i = 1; i < ivwPoints.length; i++) {
        ctx.lineTo(ivwPoints[i].x, ivwPoints[i].y)
      }
      ctx.strokeStyle = 'vars.accent'
      ctx.lineWidth = 2
      ctx.stroke()
    }
  }

  // ── HV 曲线 ──
  if (activeOverlay.value === 'both' || activeOverlay.value === 'hv') {
    const hvKey = selectedHV.value
    const hvLabel = { hv5: 'HV5', hv10: 'HV10', hv20: 'HV20', hv60: 'HV60' }[hvKey]
    const hvColor = { hv5: 'vars.down', hv10: 'vars.down', hv20: 'vars.down', hv60: 'vars.down' }[hvKey]
    const hvPoints = data.map((d, i) => d[hvKey] ? { x: xOf(i), y: yVol(d[hvKey] * 100) } : null).filter(Boolean)
    if (hvPoints.length > 1) {
      ctx.beginPath()
      ctx.moveTo(hvPoints[0].x, hvPoints[0].y)
      for (let i = 1; i < hvPoints.length; i++) {
        ctx.lineTo(hvPoints[i].x, hvPoints[i].y)
      }
      ctx.strokeStyle = hvColor
      ctx.lineWidth = 1.5
      ctx.setLineDash([2, 2])
      ctx.stroke()
      ctx.setLineDash([])
    }
  }

  // ── Y轴标签 (左: 价格) ──
  ctx.fillStyle = vars.textDim
  ctx.font = '10px ' + vars.fontMono
  ctx.textAlign = 'right'
  for (let i = 0; i <= 5; i++) {
    const v = maxClose - closeRange * i / 5
    const y = pad.top + ch * i / 5
    ctx.fillText(v.toFixed(3), pad.left - 8, y + 3)
  }

  // ── Y轴标签 (右: IV/HV%) ──
  ctx.fillStyle = vars.textDim
  ctx.textAlign = 'left'
  for (let i = 0; i <= 5; i++) {
    const v = maxVol - volRange * i / 5
    const y = pad.top + ch * i / 5
    ctx.fillText(v.toFixed(1) + '%', W - pad.right + 6, y + 3)
  }

  // ── X轴标签 (日期) ──
  ctx.fillStyle = vars.textDim
  ctx.font = '9px ' + vars.fontMono
  ctx.textAlign = 'center'
  const step = Math.max(1, Math.floor(data.length / 6))
  for (let i = 0; i < data.length; i += step) {
    const x = xOf(i)
    const d = data[i]
    const label = d.date ? d.date.slice(5, 10) : ''
    ctx.fillText(label, x, H - pad.bottom + 14)
  }

  // ── 图例 ──
  ctx.font = '11px ' + vars.fontSans
  let legendX = pad.left
  const legendY = 16

  // 标的
  ctx.fillStyle = vars.textDim
  ctx.textAlign = 'left'
  ctx.fillText('● 标的', legendX, legendY)
  legendX += 60

  if (activeOverlay.value === 'both' || activeOverlay.value === 'iv') {
    ctx.fillStyle = vars.accent
    ctx.fillText('— IV(加权)', legendX, legendY)
    legendX += 80
    ctx.setLineDash([4, 2])
    ctx.fillStyle = vars.accent
    ctx.globalAlpha = 0.5
    ctx.fillText('-- IV(ATM)', legendX, legendY)
    ctx.globalAlpha = 1
    ctx.setLineDash([])
    legendX += 80
  }

  if (activeOverlay.value === 'both' || activeOverlay.value === 'hv') {
    ctx.fillStyle = vars.down
    ctx.fillText(`-- ${selectedHV.value.toUpperCase()}`, legendX, legendY)
    legendX += 70
  }

  // 标题
  ctx.fillStyle = vars.textMuted
  ctx.font = '11px ' + vars.fontSans
  ctx.textAlign = 'left'
  ctx.fillText('综合走势', pad.left, legendY)
}

// ── 绘制 PCR 副图 ──
function renderPCRChart() {
  const cvs = pcrCanvas.value
  if (!cvs || !props.data.length) return
  const ctx = cvs.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const W = cvs.clientWidth
  const H = cvs.clientHeight
  cvs.width = W * dpr
  cvs.height = H * dpr
  ctx.scale(dpr, dpr)

  const data = props.data
  const pad = { top: 16, right: 56, bottom: 28, left: 56 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // PCR 范围
  const pcrValues = data.map(d => d.pcr_ratio).filter(v => v != null)
  const pcrSkewValues = data.map(d => d.pcr_iv_skew).filter(v => v != null)
  const allPcr = [...pcrValues, ...pcrSkewValues]
  if (!allPcr.length) return

  const minPCR = Math.max(0, Math.min(...allPcr) * 0.8)
  const maxPCR = Math.max(...allPcr) * 1.2
  const pcrRange = maxPCR - minPCR || 0.1

  const xOf = (i) => pad.left + i / Math.max(data.length - 1, 1) * cw
  const yPcr = (v) => pad.top + ch - (v - minPCR) / pcrRange * ch

  // 网格
  ctx.strokeStyle = vars.border
  ctx.lineWidth = 1
  for (let i = 0; i <= 3; i++) {
    const y = pad.top + ch * i / 3
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // 1.0 参考线
  if (minPCR < 1.0 && maxPCR > 1.0) {
    const y1 = yPcr(1.0)
    ctx.strokeStyle = 'hexToRgba(vars.accent, 0.3)'
    ctx.lineWidth = 1
    ctx.setLineDash([3, 3])
    ctx.beginPath(); ctx.moveTo(pad.left, y1); ctx.lineTo(W - pad.right, y1); ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = 'vars.accent'
    ctx.font = '9px var(--font-mono)'
    ctx.textAlign = 'right'
    ctx.fillText('1.0', pad.left - 4, y1 + 3)
  }

  // PCR 柱状图
  const barWidth = Math.max(1, cw / data.length * 0.6)
  for (let i = 0; i < data.length; i++) {
    const d = data[i]
    if (d.pcr_ratio == null) continue
    const x = xOf(i)
    const y = yPcr(d.pcr_ratio)
    const baseY = yPcr(1.0)
    const h = baseY - y
    ctx.fillStyle = d.pcr_ratio >= 1.0 ? hexToRgba(vars.up, 0.5) : hexToRgba(vars.down, 0.5)
    ctx.fillRect(x - barWidth / 2, Math.min(y, baseY), barWidth, Math.abs(h))
  }

  // PCR IV Skew 线
  const skewPoints = data.map((d, i) => d.pcr_iv_skew ? { x: xOf(i), y: yPcr(d.pcr_iv_skew) } : null).filter(Boolean)
  if (skewPoints.length > 1) {
    ctx.beginPath()
    ctx.moveTo(skewPoints[0].x, skewPoints[0].y)
    for (let i = 1; i < skewPoints.length; i++) {
      ctx.lineTo(skewPoints[i].x, skewPoints[i].y)
    }
    ctx.strokeStyle = 'vars.up'
    ctx.lineWidth = 1.5
    ctx.stroke()
  }

  // Y轴标签
  ctx.fillStyle = vars.textMuted
  ctx.font = '9px ' + vars.fontMono
  ctx.textAlign = 'right'
  for (let i = 0; i <= 3; i++) {
    const v = maxPCR - pcrRange * i / 3
    const y = pad.top + ch * i / 3
    ctx.fillText(v.toFixed(2), pad.left - 6, y + 3)
  }

  // X轴标签
  ctx.textAlign = 'center'
  const step = Math.max(1, Math.floor(data.length / 6))
  for (let i = 0; i < data.length; i += step) {
    const x = xOf(i)
    const d = data[i]
    const label = d.date ? d.date.slice(5, 10) : ''
    ctx.fillText(label, x, H - pad.bottom + 14)
  }

  // 图例
  ctx.font = '10px ' + vars.fontSans
  ctx.textAlign = 'left'
  ctx.fillStyle = 'hexToRgba(vars.up, 0.7)'
  ctx.fillText('■ PCR(量比)', pad.left, 12)
  ctx.fillStyle = vars.up
  ctx.fillText('— IV Skew', pad.left + 90, 12)

  ctx.fillStyle = vars.textMuted
  ctx.fillText('PCR', pad.left + 170, 12)
}

// ── 渲染 ──
function render() {
  renderMainChart()
  renderPCRChart()
}

watch(() => props.data, () => { nextTick(render) }, { deep: true })
watch(activeOverlay, () => render())
watch(selectedHV, () => render())

onMounted(() => {
  nextTick(render)
  window.addEventListener('resize', render)
})

onUnmounted(() => {
  window.removeEventListener('resize', render)
})
</script>

<template>
  <div class="dashboard-chart" v-if="!loading && data.length">
    <!-- 工具栏 -->
    <div class="dash-toolbar">
      <div class="dash-overlay-toggle">
        <span class="dash-toggle-label">叠加:</span>
        <button :class="{ active: activeOverlay === 'both' }" @click="activeOverlay = 'both'">全部</button>
        <button :class="{ active: activeOverlay === 'iv' }" @click="activeOverlay = 'iv'">仅IV</button>
        <button :class="{ active: activeOverlay === 'hv' }" @click="activeOverlay = 'hv'">仅HV</button>
        <button :class="{ active: activeOverlay === 'none' }" @click="activeOverlay = 'none'">无</button>
      </div>
      <div class="dash-hv-toggle" v-if="activeOverlay === 'both' || activeOverlay === 'hv'">
        <span class="dash-toggle-label">HV:</span>
        <button :class="{ active: selectedHV === 'hv5' }" @click="selectedHV = 'hv5'">5日</button>
        <button :class="{ active: selectedHV === 'hv10' }" @click="selectedHV = 'hv10'">10日</button>
        <button :class="{ active: selectedHV === 'hv20' }" @click="selectedHV = 'hv20'">20日</button>
        <button :class="{ active: selectedHV === 'hv60' }" @click="selectedHV = 'hv60'">60日</button>
      </div>
    </div>

    <!-- 最新数据卡片 -->
    <div class="dash-cards" v-if="latest">
      <div class="dash-card">
        <span class="dash-card-label">标的</span>
        <span class="dash-card-val">{{ latest.close?.toFixed(3) || '--' }}</span>
      </div>
      <div class="dash-card">
        <span class="dash-card-label">IV(ATM)</span>
        <span class="dash-card-val accent-orange">{{ latest.iv_atm ? (latest.iv_atm * 100).toFixed(1) + '%' : '--' }}</span>
      </div>
      <div class="dash-card">
        <span class="dash-card-label">HV20</span>
        <span class="dash-card-val accent-green">{{ latest.hv20 ? (latest.hv20 * 100).toFixed(1) + '%' : '--' }}</span>
      </div>
      <div class="dash-card">
        <span class="dash-card-label">PCR</span>
        <span class="dash-card-val" :class="latest.pcr_ratio >= 1 ? 'accent-red' : 'accent-green'">
          {{ latest.pcr_ratio?.toFixed(2) || '--' }}
        </span>
      </div>
      <div class="dash-card">
        <span class="dash-card-label">IV Skew</span>
        <span class="dash-card-val accent-orange">{{ latest.pcr_iv_skew?.toFixed(2) || '--' }}</span>
      </div>
      <div class="dash-card">
        <span class="dash-card-label">HV/IV</span>
        <span class="dash-card-val">
          {{ latest.hv20 && latest.iv_atm ? (latest.hv20 / latest.iv_atm).toFixed(2) : '--' }}
        </span>
      </div>
    </div>

    <!-- 主图 -->
    <div class="dash-chart-wrap">
      <canvas ref="mainCanvas" class="dash-canvas"></canvas>
    </div>

    <!-- PCR 副图 -->
    <div class="dash-pcr-wrap">
      <canvas ref="pcrCanvas" class="dash-pcr-canvas"></canvas>
    </div>
  </div>

  <div class="dash-empty" v-else-if="!loading">
    <p>暂无走势数据，等待数据积累...</p>
  </div>
</template>

<style scoped>
.dashboard-chart {
  width: 100%;
}

.dash-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.dash-overlay-toggle, .dash-hv-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dash-toggle-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-right: 4px;
}

.dash-overlay-toggle button, .dash-hv-toggle button {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.dash-overlay-toggle button.active, .dash-hv-toggle button.active {
  background: var(--accent);
  color: var(--bg-deep);
  border-color: var(--accent);
}

.dash-overlay-toggle button:hover, .dash-hv-toggle button:hover {
  color: var(--text-primary);
}

/* 数据卡片 */
.dash-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.dash-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  min-width: 80px;
}

.dash-card-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.dash-card-val {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.dash-card-val.accent-orange { color: var(--accent); }
.dash-card-val.accent-green { color: var(--down); }
.dash-card-val.accent-red { color: var(--up); }

/* 图表 */
.dash-chart-wrap {
  position: relative;
  width: 100%;
  height: 320px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
}

.dash-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.dash-pcr-wrap {
  position: relative;
  width: 100%;
  height: 120px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.dash-pcr-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.dash-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
