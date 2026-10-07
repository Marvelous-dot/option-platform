<template>
  <div class="vs3d" ref="wrap">
    <canvas ref="cv" role="img"
      aria-label="3D 波动率曲面：横轴行权价，纵深到期日，高度为隐含波动率。拖拽旋转视角，滚轮缩放，双击复位，悬停可查看具体合约。"
      :style="{ cursor: dragging ? 'grabbing' : 'grab' }">浏览器不支持 Canvas，无法渲染 3D 曲面</canvas>
    <div v-if="tip.show" class="tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      <div class="tip-strong">{{ tip.exp }} · K {{ tip.strike }}</div>
      <div>IV {{ tip.iv }}</div>
      <div class="tip-dim">{{ tip.code }}</div>
    </div>
    <div class="hud">
      <div class="legend" aria-hidden="true">
        <span>{{ loLabel }}</span>
        <i></i>
        <span>{{ hiLabel }}</span>
      </div>
      <button type="button" class="reset" @click="resetView">重置视角</button>
    </div>
    <p v-if="!ready" class="vs3d-empty">{{ emptyReason }}</p>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  // buildVolatility 的 groups：[{ expiry, rows: [{ strikeValue, ivValue, option_type, option_code, name }] }]
  groups: { type: Array, default: () => [] },
  spot: { type: Number, default: null },
})

const wrap = ref(null), cv = ref(null)
const dragging = ref(false)
const tip = reactive({ show: false, x: 0, y: 0, exp: '', strike: '', iv: '', code: '' })

// ---------- 数据构建：OTM 惯例 + 退化 IV 剔除 ----------
const surface = computed(() => {
  const gs = props.groups, spot = Number(props.spot)
  if (!Array.isArray(gs) || gs.length < 2 || !Number.isFinite(spot) || spot <= 0) return null
  const strikeKeys = new Map()
  const perExp = []
  for (const g of gs) {
    const map = new Map()
    for (const r of g.rows || []) {
      const k = Number(r.strikeValue), iv = Number(r.ivValue)
      if (!Number.isFinite(k) || k <= 0 || !Number.isFinite(iv)) continue
      if (iv < 0.02 || iv > 2) continue // 深度实值等退化 IV（如 0.0009）剔除
      const side = k < spot ? 'put' : 'call' // OTM 惯例：虚值侧取数
      if (r.option_type !== side) continue
      if (!map.has(k)) map.set(k, { iv, code: r.option_code || '', name: r.name || '' })
      strikeKeys.set(k, true)
    }
    perExp.push({ expiry: String(g.expiry || ''), map })
  }
  const strikes = [...strikeKeys.keys()].sort((a, b) => a - b)
  if (strikes.length < 3) return null
  const grid = perExp.map(p => strikes.map(k => p.map.get(k) || null))
  const ivs = grid.flat().filter(Boolean).map(c => c.iv)
  if (ivs.length < 6) return null
  return {
    strikes, expiries: perExp.map(p => p.expiry), grid,
    minIv: Math.min(...ivs), maxIv: Math.max(...ivs),
  }
})
const ready = computed(() => !!surface.value)
const emptyReason = computed(() =>
  props.groups.length < 2 ? '到期日不足两张，无法构成曲面'
    : !Number.isFinite(Number(props.spot)) ? '标的参考价不可用，无法定位 OTM 侧'
    : '有效 IV 点不足，无法绘制曲面')
const pct = v => (v * 100).toFixed(1) + '%'
const loLabel = computed(() => surface.value ? pct(surface.value.minIv) : '')
const hiLabel = computed(() => surface.value ? pct(surface.value.maxIv) : '')

// ---------- 颜色（与 legend 渐变保持一致） ----------
const STOPS = [[77, 124, 193], [79, 174, 155], [200, 224, 75]] // 蓝 → 青 → 黄绿
function colorFor(t) {
  const seg = t < 0.5 ? 0 : 1, tt = t < 0.5 ? t * 2 : (t - 0.5) * 2
  const a = STOPS[seg], b = STOPS[seg + 1]
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * tt)).join(',')})`
}

// ---------- 视角状态 ----------
const yaw = ref(0.62), pitch = ref(0.52), zoomV = ref(1)
function resetView() { yaw.value = 0.62; pitch.value = 0.52; zoomV.value = 1; hideTip(); requestDraw() }
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

// ---------- 绘制 ----------
let ptsCache = [] // 悬停拾取用：{x, y, iv, strike, expiry, code, name}
let raf = 0
function requestDraw() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw() }) }

function draw() {
  const cvEl = cv.value, wrapEl = wrap.value, sf = surface.value
  if (!cvEl || !wrapEl || !sf) return
  const w = wrapEl.clientWidth, h = wrapEl.clientHeight
  if (w < 10 || h < 10) return
  const dpr = window.devicePixelRatio || 1
  const bw = Math.round(w * dpr), bh = Math.round(h * dpr)
  if (cvEl.width !== bw || cvEl.height !== bh) { cvEl.width = bw; cvEl.height = bh }
  const ctx = cvEl.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  const style = getComputedStyle(wrapEl)
  const cDim = style.getPropertyValue('--text-dim').trim() || '#5a6572'
  const cMut = style.getPropertyValue('--text-muted').trim() || '#8a94a0'
  const cAcc = style.getPropertyValue('--accent').trim() || '#cdf64e'
  const cInk = style.getPropertyValue('--text').trim() || '#10151c'

  const { strikes, expiries, grid, minIv, maxIv } = sf
  const S = strikes.length, R = expiries.length
  const ivSpan = Math.max(1e-9, maxIv - minIv)
  const cosY = Math.cos(yaw.value), sinY = Math.sin(yaw.value)
  const cosP = Math.cos(pitch.value), sinP = Math.sin(pitch.value)
  const VX = i => S > 1 ? i / (S - 1) : 0.5
  const VY = j => R > 1 ? j / (R - 1) : 0.5
  const VZ = iv => (iv - minIv) / ivSpan
  const raw = (x, y, z) => {
    const u = x * cosY - y * sinY
    const d = x * sinY + y * cosY
    return [u, z * cosP + d * sinP, d]
  }
  // 自适应取景：投影单位立方体 8 角，留出标签边距
  let uMin = 1e9, uMax = -1e9, vMin = 1e9, vMax = -1e9
  for (const x of [0, 1]) for (const y of [0, 1]) for (const z of [0, 1]) {
    const [u, v] = raw(x, y, z)
    uMin = Math.min(uMin, u); uMax = Math.max(uMax, u)
    vMin = Math.min(vMin, v); vMax = Math.max(vMax, v)
  }
  const margin = 46
  const scale = Math.min((w - 2 * margin) / Math.max(1e-6, uMax - uMin), (h - 2 * margin) / Math.max(1e-6, vMax - vMin)) * zoomV.value
  const cx = w / 2 - ((uMin + uMax) / 2) * scale
  const cy = h / 2 + ((vMin + vMax) / 2) * scale
  const P = (x, y, z) => { const [u, v, d] = raw(x, y, z); return { x: cx + u * scale, y: cy - v * scale, d } }

  // 顶点投影（含数据）
  const pts = grid.map((row, j) => row.map((cell, i) => {
    if (!cell) return null
    const p = P(VX(i), VY(j), VZ(cell.iv))
    return { ...p, iv: cell.iv, strike: strikes[i], expiry: expiries[j], code: cell.code, name: cell.name }
  }))
  ptsCache = pts.flat().filter(Boolean)

  ctx.lineWidth = 1
  ctx.font = '10px system-ui, sans-serif'

  // 底面网格（z=0 平面）
  ctx.strokeStyle = 'rgba(20,28,36,.10)'
  ctx.beginPath()
  for (let i = 0; i < S; i++) { const a = P(VX(i), 0, 0), b = P(VX(i), 1, 0); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y) }
  for (let j = 0; j < R; j++) { const a = P(0, VY(j), 0), b = P(1, VY(j), 0); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y) }
  ctx.stroke()

  // 坐标轴三条棱
  ctx.strokeStyle = 'rgba(20,28,36,.45)'
  ctx.beginPath()
  const o = P(0, 0, 0)
  const ax = P(1, 0, 0), ay = P(0, 1, 0), az = P(0, 0, 1)
  ctx.moveTo(o.x, o.y); ctx.lineTo(ax.x, ax.y)
  ctx.moveTo(o.x, o.y); ctx.lineTo(ay.x, ay.y)
  ctx.moveTo(o.x, o.y); ctx.lineTo(az.x, az.y)
  ctx.stroke()

  // 曲面片：painter 算法，远的先画
  const quads = []
  for (let j = 0; j < R - 1; j++) for (let i = 0; i < S - 1; i++) {
    const a = pts[j][i], b = pts[j][i + 1], c = pts[j + 1][i + 1], e = pts[j + 1][i]
    if (a && b && c && e) quads.push({ a, b, c, e, d: (a.d + b.d + c.d + e.d) / 4, t: (a.iv + b.iv + c.iv + e.iv) / 4 })
  }
  quads.sort((p, q) => q.d - p.d)
  for (const q of quads) {
    ctx.beginPath()
    ctx.moveTo(q.a.x, q.a.y); ctx.lineTo(q.b.x, q.b.y); ctx.lineTo(q.c.x, q.c.y); ctx.lineTo(q.e.x, q.e.y)
    ctx.closePath()
    ctx.fillStyle = colorFor((q.t - minIv) / ivSpan)
    ctx.globalAlpha = 0.93
    ctx.fill()
    ctx.globalAlpha = 1
    ctx.strokeStyle = 'rgba(15,25,35,.28)'
    ctx.lineWidth = 0.6
    ctx.stroke()
  }

  // 实际数据点
  for (const p of ptsCache) {
    ctx.beginPath(); ctx.arc(p.x, p.y, 2.3, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(13,18,24,.55)'; ctx.fill()
  }

  // ---- 轴标签 ----
  ctx.fillStyle = cMut
  // 行权价刻度（前边缘 y=0）
  ctx.textAlign = 'center'
  const nX = S <= 8 ? S : 6
  for (let k = 0; k < nX; k++) {
    const i = Math.round(k * (S - 1) / (nX - 1))
    const p = P(VX(i), 0, 0)
    ctx.fillText(String(strikes[i]), p.x, p.y + 16)
  }
  ctx.fillText('行权价 →', (o.x + ax.x) / 2, Math.max(o.y, ax.y) + 30)
  // 到期日刻度（左边缘 x=0）
  ctx.textAlign = 'right'
  for (let j = 0; j < R; j++) {
    const p = P(0, VY(j), 0)
    const e = expiries[j]
    ctx.fillText(e.length === 8 ? `${e.slice(4, 6)}-${e.slice(6, 8)}` : e, p.x - 8, p.y + 3)
  }
  const yl = P(0, 1, 0)
  ctx.fillText('到期日 →', yl.x - 12, yl.y - 12)
  // IV 纵轴刻度（z 棱）
  ctx.textAlign = 'right'
  for (let k = 0; k <= 3; k++) {
    const t = k / 3, p = P(0, 0, t)
    ctx.fillText(pct(minIv + t * ivSpan), p.x - 8, p.y + 3)
  }
  ctx.textAlign = 'left'
  ctx.fillStyle = cDim
  ctx.fillText('IV', az.x - 4, az.y - 8)

  // 悬停高亮
  if (tip.show && hoverPt.value) {
    ctx.beginPath(); ctx.arc(hoverPt.value.x, hoverPt.value.y, 5, 0, Math.PI * 2)
    ctx.strokeStyle = cInk; ctx.lineWidth = 1.6; ctx.stroke()
    ctx.beginPath(); ctx.arc(hoverPt.value.x, hoverPt.value.y, 2.6, 0, Math.PI * 2)
    ctx.fillStyle = cAcc; ctx.fill()
  }
}

// ---------- 交互 ----------
const hoverPt = ref(null)
function hideTip() { tip.show = false; hoverPt.value = null }
let lastX = 0, lastY = 0
function onDown(e) {
  dragging.value = true
  lastX = e.clientX; lastY = e.clientY
  cv.value?.setPointerCapture?.(e.pointerId)
}
function onMove(e) {
  if (dragging.value) {
    const dx = e.clientX - lastX, dy = e.clientY - lastY
    lastX = e.clientX; lastY = e.clientY
    yaw.value = clamp(yaw.value + dx * 0.0075, -1.35, 1.35)
    pitch.value = clamp(pitch.value + dy * 0.006, 0.12, 1.4)
    hideTip()
    requestDraw()
    return
  }
  // 悬停拾取最近数据点
  const rect = cv.value?.getBoundingClientRect()
  if (!rect) return
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  let best = null, bd = 18 * 18
  for (const p of ptsCache) {
    const dd = (p.x - mx) ** 2 + (p.y - my) ** 2
    if (dd < bd) { bd = dd; best = p }
  }
  if (best) {
    hoverPt.value = best
    const w = wrap.value?.clientWidth || 300
    tip.exp = best.expiry.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3')
    tip.strike = String(best.strike)
    tip.iv = pct(best.iv)
    tip.code = best.name ? `${best.name}（${best.code}）` : best.code
    tip.x = clamp(best.x + 14, 8, Math.max(8, w - 170))
    tip.y = Math.max(8, best.y - 64)
    tip.show = true
    requestDraw()
  } else if (tip.show) { hideTip(); requestDraw() }
}
function onUp(e) {
  dragging.value = false
  cv.value?.releasePointerCapture?.(e.pointerId)
}
function onWheel(e) {
  e.preventDefault()
  zoomV.value = clamp(zoomV.value * (e.deltaY > 0 ? 0.92 : 1.085), 0.55, 2.4)
  requestDraw()
}

let ro = null
onMounted(() => {
  ro = new ResizeObserver(() => requestDraw())
  ro.observe(wrap.value)
  const el = cv.value
  el.addEventListener('pointerdown', onDown)
  el.addEventListener('pointermove', onMove)
  el.addEventListener('pointerup', onUp)
  el.addEventListener('pointercancel', onUp)
  el.addEventListener('pointerleave', () => { if (!dragging.value) { hideTip(); requestDraw() } })
  el.addEventListener('wheel', onWheel, { passive: false })
  el.addEventListener('dblclick', resetView)
  requestDraw()
})
onUnmounted(() => {
  ro?.disconnect()
  if (raf) cancelAnimationFrame(raf)
})
watch(surface, () => { hideTip(); requestDraw() })
</script>

<style scoped>
.vs3d { position: relative; height: clamp(340px, 44vw, 540px); }
canvas { display: block; width: 100%; height: 100%; touch-action: none; }
.tip {
  position: absolute; z-index: 5; pointer-events: none;
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: var(--shadow); padding: 8px 11px; font-size: 12px; line-height: 1.55;
  color: var(--text); min-width: 130px;
}
.tip-strong { font-weight: 700; }
.tip-dim { color: var(--text-dim); font-size: 11px; }
.hud {
  position: absolute; right: 10px; top: 10px; z-index: 4;
  display: flex; align-items: center; gap: 10px;
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: blur(4px); border: 1px solid var(--border);
  border-radius: 999px; padding: 5px 12px;
}
.legend { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.legend i { display: block; width: 72px; height: 8px; border-radius: 4px; background: linear-gradient(90deg, #4d7cc1, #4fae9b, #c8e04b); }
.reset { border: 1px solid var(--border); background: var(--bg); border-radius: 999px; font-size: 11px; padding: 3px 10px; cursor: pointer; color: var(--text-dim); }
.reset:hover { color: var(--text); border-color: var(--text-dim); }
.vs3d-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--text-dim); font-size: 13px; margin: 0;
}
@media (max-width: 640px) {
  .vs3d { height: 340px; }
  .legend { display: none; }
  .hud { padding: 4px 8px; }
}
</style>
