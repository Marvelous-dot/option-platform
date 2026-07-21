<script setup>
/**
 * 3D 波动率曲面组件
 * 
 * 使用 Canvas 2D 实现等距投影 (Isometric Projection) 的 3D 曲面图
 * X轴: 行权价 (Strike)
 * Y轴: 到期时间 (Time to Expiry)  
 * Z轴: 隐含波动率 (IV)
 * 
 * 着色: 使用热力色阶 (蓝→青→绿→黄→红) 映射 IV 值
 */
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { getCssVars } from '@/utils/cssVar'

// hex → rgba 转换，用于 Canvas 半透明颜色
function hexToRgba(hex, alpha) {
  const clean = hex.replace('#', '').trim()
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

const props = defineProps({
  data: {
    type: Object,
    default: () => ({ strikes: [], expiries: [], grid: { call: [], put: [] }, spot_price: 0, min_iv: 0, max_iv: 0 })
  },
  optionType: {
    type: String,
    default: 'call' // 'call' | 'put'
  },
  width: {
    type: Number,
    default: 800
  },
  height: {
    type: Number,
    default: 500
  }
})

const canvas = ref(null)
const rotationY = ref(-30) // 水平旋转角度 (度)
const rotationX = ref(25)  // 俯仰角度 (度)
const zoom = ref(1.0)
const isDragging = ref(false)
const lastMouse = ref({ x: 0, y: 0 })
const hoverInfo = ref(null)
const renderRAF = ref(null) // requestAnimationFrame ID for drag debounce

// ── 热力色阶 ──
function ivToColor(iv, minIV, maxIV) {
  if (iv == null || minIV == null || maxIV == null || maxIV <= minIV) return 'hexToRgba(vars.textDim, 0.8)'
  const t = Math.max(0, Math.min(1, (iv - minIV) / (maxIV - minIV)))
  // 热力色阶: 深蓝(0) → 蓝(0.2) → 青(0.4) → 绿(0.5) → 黄(0.7) → 橙(0.85) → 红(1.0)
  let r, g, b
  if (t < 0.2) {
    const s = t / 0.2
    r = 20 + s * 30; g = 40 + s * 80; b = 120 + s * 60
  } else if (t < 0.4) {
    const s = (t - 0.2) / 0.2
    r = 50 - s * 30; g = 120 + s * 60; b = 180 - s * 40
  } else if (t < 0.5) {
    const s = (t - 0.4) / 0.1
    r = 20 + s * 20; g = 180 + s * 20; b = 140 - s * 60
  } else if (t < 0.7) {
    const s = (t - 0.5) / 0.2
    r = 40 + s * 180; g = 200 - s * 20; b = 80 - s * 40
  } else if (t < 0.85) {
    const s = (t - 0.7) / 0.15
    r = 220 + s * 35; g = 180 - s * 80; b = 40 - s * 20
  } else {
    const s = (t - 0.85) / 0.15
    r = 255; g = 100 - s * 60; b = 20 - s * 20
  }
  return `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},0.85)`
}

// ── 3D → 2D 投影 ──
function project3D(x, y, z, cx, cy, scale, rotY, rotX) {
  // 绕 Y 轴旋转 (水平)
  const radY = rotY * Math.PI / 180
  const cosY = Math.cos(radY)
  const sinY = Math.sin(radY)
  let x1 = x * cosY - y * sinY
  let y1 = x * sinY + y * cosY
  let z1 = z
  
  // 绕 X 轴旋转 (俯仰)
  const radX = rotX * Math.PI / 180
  const cosX = Math.cos(radX)
  const sinX = Math.sin(radX)
  const y2 = y1 * cosX - z1 * sinX
  const z2 = y1 * sinX + z1 * cosX
  
  // 正交投影到 2D
  return {
    x: cx + x1 * scale,
    y: cy - y2 * scale,
    z: z2 // 保留 z 用于深度排序
  }
}

// ── 绘制3D曲面 ──
function renderSurface() {
  const cvs = canvas.value
  if (!cvs) return
  const ctx = cvs.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const W = cvs.clientWidth
  const H = cvs.clientHeight
  cvs.width = W * dpr
  cvs.height = H * dpr
  ctx.scale(dpr, dpr)
  
  // 背景
  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)
  
  const data = props.data
  if (!data || !data.strikes || !data.expiries || data.strikes.length < 2 || data.expiries.length < 1) {
    ctx.fillStyle = vars.textMuted
    ctx.font = '14px var(--font-sans)'
    ctx.textAlign = 'center'
    ctx.fillText('暂无3D曲面数据', W / 2, H / 2)
    return
  }
  
  const strikes = data.strikes
  const expiries = data.expiries
  const grid = data.grid?.[props.optionType] || []
  const minIV = data.min_iv ?? 0
  const maxIV = data.max_iv ?? 0.5
  const spotPrice = data.spot_price
  
  // 3D 空间参数
  const nX = strikes.length  // 行权价方向
  const nY = expiries.length // 到期日方向
  
  // 归一化坐标到 [-1, 1]
  const normX = (i) => (nX > 1) ? (2 * i / (nX - 1) - 1) : 0
  const normY = (j) => (nY > 1) ? (2 * j / (nY - 1) - 1) : 0
  const normZ = (iv) => (maxIV > minIV) ? (iv - minIV) / (maxIV - minIV) * 0.8 : 0.2
  
  const baseScale = Math.min(W, H) * 0.32 * zoom.value
  const cx = W / 2
  const cy = H / 2 + 20
  
  // 生成所有面片 (带深度信息)
  const faces = []
  
  for (let j = 0; j < nY - 1; j++) {
    for (let i = 0; i < nX - 1; i++) {
      const iv00 = grid[j]?.[i]
      const iv10 = grid[j]?.[i + 1]
      const iv01 = grid[j + 1]?.[i]
      const iv11 = grid[j + 1]?.[i + 1]
      
      // 跳过全 None 的面片
      if (iv00 == null && iv10 == null && iv01 == null && iv11 == null) continue
      
      // 用有效值的平均 IV 着色
      const validIVs = [iv00, iv10, iv01, iv11].filter(v => v != null)
      const avgIV = validIVs.length > 0 ? validIVs.reduce((a, b) => a + b, 0) / validIVs.length : (minIV + maxIV) / 2
      
      // 四个顶点 (3D → 2D)
      const p00 = project3D(normX(i), normY(j), normZ(iv00 ?? avgIV), cx, cy, baseScale, rotationY.value, rotationX.value)
      const p10 = project3D(normX(i + 1), normY(j), normZ(iv10 ?? avgIV), cx, cy, baseScale, rotationY.value, rotationX.value)
      const p01 = project3D(normX(i), normY(j + 1), normZ(iv01 ?? avgIV), cx, cy, baseScale, rotationY.value, rotationX.value)
      const p11 = project3D(normX(i + 1), normY(j + 1), normZ(iv11 ?? avgIV), cx, cy, baseScale, rotationY.value, rotationX.value)
      
      // 深度 = 四个顶点 z 的平均
      const depth = (p00.z + p10.z + p01.z + p11.z) / 4
      
      faces.push({
        points: [p00, p10, p11, p01],
        color: ivToColor(avgIV, minIV, maxIV),
        depth,
        avgIV,
        strike: strikes[i],
        expiry: expiries[j],
        strikeNext: strikes[i + 1],
        expiryNext: expiries[j + 1],
      })
    }
  }
  
  // 按深度排序 (远面先画，近面后画)
  faces.sort((a, b) => a.depth - b.depth)
  
  // 绘制面片
  for (const face of faces) {
    ctx.beginPath()
    ctx.moveTo(face.points[0].x, face.points[0].y)
    for (let k = 1; k < face.points.length; k++) {
      ctx.lineTo(face.points[k].x, face.points[k].y)
    }
    ctx.closePath()
    ctx.fillStyle = face.color
    ctx.fill()
    // 网格线
    ctx.strokeStyle = 'hexToRgba(vars.textMuted, 0.06)'
    ctx.lineWidth = 0.5
    ctx.stroke()
  }
  
  // ── 绘制坐标轴 ──
  const axisLen = baseScale * 1.15
  const origin = project3D(-1.1, -1.1, 0, cx, cy, baseScale, rotationY.value, rotationX.value)
  
  // X轴 (行权价, 红色)
  const xEnd = project3D(1.2, -1.1, 0, cx, cy, baseScale, rotationY.value, rotationX.value)
  ctx.beginPath()
  ctx.moveTo(origin.x, origin.y)
  ctx.lineTo(xEnd.x, xEnd.y)
  ctx.strokeStyle = 'hexToRgba(vars.up, 0.6)'
  ctx.lineWidth = 1.5
  ctx.stroke()
  
  // Y轴 (到期日, 绿色)  
  const yEnd = project3D(-1.1, 1.2, 0, cx, cy, baseScale, rotationY.value, rotationX.value)
  ctx.beginPath()
  ctx.moveTo(origin.x, origin.y)
  ctx.lineTo(yEnd.x, yEnd.y)
  ctx.strokeStyle = 'hexToRgba(vars.down, 0.6)'
  ctx.lineWidth = 1.5
  ctx.stroke()
  
  // Z轴 (IV, 蓝色)
  const zEnd = project3D(-1.1, -1.1, 0.8, cx, cy, baseScale, rotationY.value, rotationX.value)
  ctx.beginPath()
  ctx.moveTo(origin.x, origin.y)
  ctx.lineTo(zEnd.x, zEnd.y)
  ctx.strokeStyle = 'hexToRgba(vars.accent, 0.6)'
  ctx.lineWidth = 1.5
  ctx.stroke()
  
  // 轴标签
  ctx.font = '11px ' + vars.fontSans
  ctx.fillStyle = 'vars.up'
  ctx.textAlign = 'center'
  ctx.fillText('行权价 →', xEnd.x, xEnd.y + 16)
  ctx.fillStyle = 'vars.down'
  ctx.fillText('到期日 →', yEnd.x, yEnd.y - 8)
  ctx.fillStyle = 'vars.accent'
  ctx.textAlign = 'left'
  ctx.fillText('IV ↑', zEnd.x + 6, zEnd.y)
  
  // ── 行权价刻度 ──
  ctx.fillStyle = vars.textDim
  ctx.font = '9px ' + vars.fontMono
  ctx.textAlign = 'center'
  const strikeStep = Math.max(1, Math.floor(nX / 6))
  for (let i = 0; i < nX; i += strikeStep) {
    const p = project3D(normX(i), -1.1, 0, cx, cy, baseScale, rotationY.value, rotationX.value)
    ctx.fillText(strikes[i].toFixed(2), p.x, p.y + 22)
    // 小刻度线
    ctx.beginPath()
    ctx.moveTo(p.x, p.y)
    ctx.lineTo(p.x, p.y + 4)
    ctx.strokeStyle = 'hexToRgba(vars.up, 0.3)'
    ctx.lineWidth = 1
    ctx.stroke()
  }
  
  // ── 到期日刻度 ──
  for (let j = 0; j < nY; j++) {
    const p = project3D(-1.1, normY(j), 0, cx, cy, baseScale, rotationY.value, rotationX.value)
    const label = expiries[j] ? expiries[j].slice(4, 6) + '/' + expiries[j].slice(6, 8) : ''
    ctx.fillText(label, p.x - 20, p.y + 4)
  }
  
  // ── IV 刻度 (Z轴) ──
  ctx.textAlign = 'right'
  for (let k = 0; k <= 4; k++) {
    const t = k / 4
    const iv = minIV + (maxIV - minIV) * t
    const p = project3D(-1.1, -1.1, t * 0.8, cx, cy, baseScale, rotationY.value, rotationX.value)
    ctx.fillText((iv * 100).toFixed(1) + '%', p.x - 8, p.y + 3)
  }
  
  // ── ATM 标的价格平面标记 ──
  if (spotPrice && strikes.length > 0) {
    // 找到最近的行权价索引
    let atmIdx = 0
    let minDist = Math.abs(strikes[0] - spotPrice)
    for (let i = 1; i < strikes.length; i++) {
      const d = Math.abs(strikes[i] - spotPrice)
      if (d < minDist) { minDist = d; atmIdx = i }
    }
    const atmX = normX(atmIdx)
    // 画一条竖线表示 ATM
    const atmBottom = project3D(atmX, -1.1, 0, cx, cy, baseScale, rotationY.value, rotationX.value)
    const atmTop = project3D(atmX, 1.1, 0, cx, cy, baseScale, rotationY.value, rotationX.value)
    ctx.beginPath()
    ctx.moveTo(atmBottom.x, atmBottom.y)
    ctx.lineTo(atmTop.x, atmTop.y)
    ctx.strokeStyle = 'hexToRgba(vars.accent, 0.5)'
    ctx.lineWidth = 1.5
    ctx.setLineDash([3, 3])
    ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = 'vars.accent'
    ctx.font = '9px var(--font-mono)'
    ctx.textAlign = 'left'
    ctx.fillText('ATM', atmTop.x + 4, atmTop.y - 4)
  }
  
  // ── 标题 ──
  ctx.fillStyle = vars.textMuted
  ctx.font = '12px ' + vars.fontSans
  ctx.textAlign = 'left'
  const typeLabel = props.optionType === 'call' ? '认购' : '认沽'
  ctx.fillText(`3D 波动率曲面 — ${typeLabel}`, 16, 18)
  
  // ── 色阶图例 ──
  drawColorLegend(ctx, W - 120, 30, 100, 12, minIV, maxIV)
}

// ── 色阶图例 ──
function drawColorLegend(ctx, x, y, w, h, minIV, maxIV) {
  const steps = 40
  const stepW = w / steps
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1)
    const iv = minIV + (maxIV - minIV) * t
    ctx.fillStyle = ivToColor(iv, minIV, maxIV)
    ctx.fillRect(x + i * stepW, y, stepW + 1, h)
  }
  ctx.strokeStyle = 'hexToRgba(vars.textMuted, 0.15)'
  ctx.lineWidth = 1
  ctx.strokeRect(x, y, w, h)
  
  ctx.fillStyle = vars.textMuted
  ctx.font = '9px ' + vars.fontMono
  ctx.textAlign = 'left'
  ctx.fillText((minIV * 100).toFixed(1) + '%', x, y + h + 12)
  ctx.textAlign = 'right'
  ctx.fillText((maxIV * 100).toFixed(1) + '%', x + w, y + h + 12)
  ctx.textAlign = 'center'
  ctx.fillText('IV', x + w / 2, y - 4)
}

// ── 鼠标交互 ──
function onMouseDown(e) {
  isDragging.value = true
  lastMouse.value = { x: e.clientX, y: e.clientY }
  // Bind to window so dragging continues even when cursor leaves canvas
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e) {
  if (!isDragging.value) return
  const dx = e.clientX - lastMouse.value.x
  const dy = e.clientY - lastMouse.value.y
  rotationY.value += dx * 0.5
  rotationX.value = Math.max(-10, Math.min(60, rotationX.value - dy * 0.5))
  lastMouse.value = { x: e.clientX, y: e.clientY }
  // Debounce render with requestAnimationFrame
  if (renderRAF.value) cancelAnimationFrame(renderRAF.value)
  renderRAF.value = requestAnimationFrame(() => {
    renderSurface()
    renderRAF.value = null
  })
}

function onMouseUp() {
  if (!isDragging.value) return
  isDragging.value = false
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

function onWheel(e) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.08 : 0.08
  zoom.value = Math.max(0.4, Math.min(2.5, zoom.value + delta))
  renderSurface()
}

// ── 重置视角 ──
function resetView() {
  rotationY.value = -30
  rotationX.value = 25
  zoom.value = 1.0
  renderSurface()
}

// ── 预设视角 ──
function setViewFront() { rotationY.value = 0; rotationX.value = 0; renderSurface() }
function setViewSide() { rotationY.value = 90; rotationX.value = 0; renderSurface() }
function setViewTop() { rotationY.value = -30; rotationX.value = 60; renderSurface() }
function setViewIso() { rotationY.value = -30; rotationX.value = 25; renderSurface() }

defineExpose({ resetView, setViewFront, setViewSide, setViewTop, setViewIso, renderSurface })

// ── 生命周期 ──
watch(() => props.data, () => { renderSurface() }, { deep: true })
watch(() => props.optionType, () => { renderSurface() })

onMounted(() => {
  renderSurface()
  window.addEventListener('resize', renderSurface)
})

onUnmounted(() => {
  window.removeEventListener('resize', renderSurface)
})
</script>

<template>
  <div class="surface3d-container">
    <!-- 工具栏 -->
    <div class="surface3d-toolbar">
      <div class="surface3d-type-toggle">
        <button :class="{ active: optionType === 'call' }" @click="$emit('update:optionType', 'call')">认购</button>
        <button :class="{ active: optionType === 'put' }" @click="$emit('update:optionType', 'put')">认沽</button>
      </div>
      <div class="surface3d-view-btns">
        <button @click="setViewIso()" title="等距视角">等距</button>
        <button @click="setViewFront()" title="正面">正面</button>
        <button @click="setViewSide()" title="侧面">侧面</button>
        <button @click="setViewTop()" title="俯视">俯视</button>
        <button @click="resetView()" title="重置">重置</button>
      </div>
      <div class="surface3d-hint">拖拽旋转 · 滚轮缩放</div>
    </div>
    
    <!-- Canvas -->
    <div class="surface3d-canvas-wrap">
      <canvas
        ref="canvas"
        class="surface3d-canvas"
        @mousedown="onMouseDown"
        @wheel="onWheel"
      ></canvas>
    </div>
  </div>
</template>

<style scoped>
.surface3d-container {
  width: 100%;
}

.surface3d-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.surface3d-type-toggle {
  display: flex;
  gap: 2px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px;
}

.surface3d-type-toggle button {
  padding: 4px 12px;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.surface3d-type-toggle button.active {
  background: var(--accent);
  color: var(--bg-deep);
}

.surface3d-view-btns {
  display: flex;
  gap: 2px;
}

.surface3d-view-btns button {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.surface3d-view-btns button:hover {
  color: var(--text-primary);
  border-color: var(--accent-dim);
}

.surface3d-hint {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: auto;
}

.surface3d-canvas-wrap {
  position: relative;
  width: 100%;
  height: 480px;
  background: vars.bgDeep;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.surface3d-canvas {
  width: 100%;
  height: 100%;
  display: block;
  cursor: grab;
}

.surface3d-canvas:active {
  cursor: grabbing;
}
</style>
