<script setup>
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getCssVars } from '@/utils/cssVar'

const route = useRoute()
const router = useRouter()

// ── State ──
const contract = ref(null)
const bsPnl = ref(null)
const loading = ref(true)
const bsLoading = ref(false)
const lastRefresh = ref('')
const pnlChart = ref(null)
let chartInstance = null

// ── BS inputs ──
const bsSpot = ref(0)
const bsVol = ref(0.20)
const bsDays = ref(30)

// ── Fetch ──
const fetchContract = async () => {
  loading.value = true
  try {
    const res = await fetch(`/api/contract/${route.params.code}`)
    contract.value = await res.json()
    lastRefresh.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })

    // Init BS inputs from contract data
    bsSpot.value = contract.value.target_price || 0
    bsVol.value = contract.value.target_vol_1y || contract.value.implied_volatility || 0.20
    bsDays.value = calcDays(contract.value.expiry_date)

    // Auto-fetch BS on load
    await fetchBsPnl()
  } catch (e) {
    console.error('fetchContract:', e)
  } finally {
    loading.value = false
  }
}

const fetchBsPnl = async () => {
  if (!contract.value) return
  bsLoading.value = true
  try {
    const res = await fetch(`/api/contract/${route.params.code}/bs_pnl`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        spot_price: bsSpot.value,
        volatility: bsVol.value,
        days_to_expiry: bsDays.value,
      })
    })
    bsPnl.value = await res.json()
    nextTick(renderChart)
  } catch (e) {
    console.error('fetchBsPnl:', e)
  } finally {
    bsLoading.value = false
  }
}

// ── Helpers ──
function calcDays(expiry) {
  if (!expiry) return 30
  try {
    const s = String(expiry).replace(/[-\/]/g, '')
    if (s.length === 8) {
      const d = new Date(+s.slice(0,4), +s.slice(4,6)-1, +s.slice(6,8))
      return Math.max(Math.round((d - Date.now()) / 86400000), 1)
    }
  } catch(e) {}
  return 30
}

function fmt(v, d=4) {
  if (v == null) return '--'
  return Number(v).toFixed(d)
}
function fmtPrice(v) { return fmt(v, 3) }
function fmtPct(v) {
  if (v == null) return '--'
  return (Number(v) * 100).toFixed(1) + '%'
}
function chgClass(v) {
  if (v == null) return 'val-neu'
  return Number(v) >= 0 ? 'val-up' : 'val-down'
}
function isCall() { return contract.value?.option_type === '认购' }
function typeColor() { return isCall() ? 'var(--up)' : 'var(--down)' }
function typeLabel() { return isCall() ? 'Call' : 'Put' }
function moneyness() {
  if (!contract.value || !contract.value.target_price) return '--'
  const s = contract.value.target_price
  const k = contract.value.strike_price
  if (isCall()) {
    return s > k ? 'ITM' : s < k ? 'OTM' : 'ATM'
  } else {
    return s < k ? 'ITM' : s > k ? 'OTM' : 'ATM'
  }
}
function moneynessColor() {
  const m = moneyness()
  if (m === 'ITM') return 'var(--accent)'
  if (m === 'ATM') return 'var(--up)'
  return 'var(--text-muted)'
}

// ── Helper: hex to rgba ──
function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// ── Chart (pure canvas, no echarts) ──
function renderChart() {
  const canvas = pnlChart.value
  if (!canvas || !bsPnl.value?.pnl_profile?.points) return
  const ctx = canvas.getContext('2d')
  const vars = getCssVars()
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)
  const W = rect.width
  const H = rect.height

  const data = bsPnl.value.pnl_profile.points
  const prices = data.map(d => d.spot_price)
  const pnls   = data.map(d => d.pnl)
  const minP = Math.min(...prices), maxP = Math.max(...prices)
  const minV = Math.min(...pnls),   maxV = Math.max(...pnls)
  const rangeV = maxV - minV || 1
  const rangeP = maxP - minP || 1

  const pad = { top: 20, right: 16, bottom: 28, left: 50 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const xOf = (p) => pad.left + (p - minP) / rangeP * cw
  const yOf = (v) => pad.top + ch - (v - minV) / rangeV * ch

  // Clear
  ctx.clearRect(0, 0, W, H)

  // Background
  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = vars.border
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ch * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }
  for (let i = 0; i <= 5; i++) {
    const x = pad.left + cw * i / 5
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, H - pad.bottom); ctx.stroke()
  }

  // Y axis labels
  ctx.fillStyle = vars.textDim
  ctx.font = '10px ' + vars.fontMono
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = maxV - rangeV * i / 4
    const y = pad.top + ch * i / 4
    ctx.fillText(v.toFixed(2), pad.left - 6, y + 3)
  }

  // X axis labels
  ctx.textAlign = 'center'
  for (let i = 0; i <= 4; i++) {
    const p = minP + rangeP * i / 4
    const x = pad.left + cw * i / 4
    ctx.fillText(p.toFixed(2), x, H - pad.bottom + 14)
  }

  // Zero line
  if (minV < 0 && maxV > 0) {
    const zy = yOf(0)
    ctx.strokeStyle = vars.borderLight
    ctx.lineWidth = 1
    ctx.setLineDash([4, 3])
    ctx.beginPath(); ctx.moveTo(pad.left, zy); ctx.lineTo(W - pad.right, zy); ctx.stroke()
    ctx.setLineDash([])
  }

  // Spot price vertical line
  const spotX = xOf(bsSpot.value)
  if (spotX >= pad.left && spotX <= W - pad.right) {
    ctx.strokeStyle = hexToRgba(vars.accent, 0.4)
    ctx.lineWidth = 1
    ctx.setLineDash([3, 2])
    ctx.beginPath(); ctx.moveTo(spotX, pad.top); ctx.lineTo(spotX, H - pad.bottom); ctx.stroke()
    ctx.setLineDash([])
    // Label
    ctx.fillStyle = vars.accent
    ctx.font = '9px ' + vars.fontMono
    ctx.textAlign = 'center'
    ctx.fillText('现价', spotX, pad.top - 6)
  }

  // PnL curve
  ctx.beginPath()
  for (let i = 0; i < data.length; i++) {
    const x = xOf(data[i].spot_price)
    const y = yOf(data[i].pnl)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  const hasProfit = pnls.some(v => v > 0)
  ctx.strokeStyle = hasProfit ? vars.up : vars.down
  ctx.lineWidth = 2
  ctx.shadowColor = ctx.strokeStyle
  ctx.shadowBlur = 8
  ctx.stroke()
  ctx.shadowBlur = 0

  // Fill area between curve and zero
  const zeroY = yOf(0)
  ctx.lineTo(xOf(data[data.length - 1].spot_price), zeroY)
  ctx.lineTo(xOf(data[0].spot_price), zeroY)
  ctx.closePath()
  const grad = ctx.createLinearGradient(0, pad.top, 0, H - pad.bottom)
  if (hasProfit) {
    grad.addColorStop(0, hexToRgba(vars.up, 0.15))
    grad.addColorStop(1, hexToRgba(vars.up, 0.02))
  } else {
    grad.addColorStop(0, hexToRgba(vars.down, 0.02))
    grad.addColorStop(1, hexToRgba(vars.down, 0.15))
  }
  ctx.fillStyle = grad
  ctx.fill()

  // Current PnL dot
  const curPnl = bsPnl.value.price_diff
  const curX = xOf(bsSpot.value)
  const curY = yOf(curPnl)
  ctx.beginPath()
  ctx.arc(curX, curY, 4, 0, Math.PI * 2)
  ctx.fillStyle = curPnl >= 0 ? vars.up : vars.down
  ctx.fill()
  ctx.strokeStyle = vars.bgPrimary
  ctx.lineWidth = 2
  ctx.stroke()
}

// ── Lifecycle ──
onMounted(fetchContract)
onUnmounted(() => { chartInstance = null })

// ── Greeks for display ──
const displayGreeks = computed(() => {
  if (!contract.value) return null
  return {
    delta: contract.value.delta,
    gamma: contract.value.gamma,
    theta: contract.value.theta,
    vega: contract.value.vega,
    rho: contract.value.rho,
  }
})

const bsGreeks = computed(() => {
  if (!bsPnl.value?.greeks) return null
  return bsPnl.value.greeks
})

// Intrinsic / Time value for pie
const valueBreakdown = computed(() => {
  if (!contract.value) return { intrinsic: 0, time: 0 }
  return {
    intrinsic: Math.max(contract.value.intrinsic_value || 0, 0),
    time: Math.max(contract.value.time_value || 0, 0),
  }
})
</script>

<template>
  <div class="cd-page" v-if="contract">

    <!-- ═══ TOP BAR ═══ -->
    <div class="cd-topbar">
      <button class="cd-back" @click="router.back()">
        <span class="cd-back-icon">←</span>
        <span>返回</span>
      </button>

      <div class="cd-title-block">
        <div class="cd-title-row">
          <span class="cd-direction-badge" :style="{ background: typeColor() }">{{ typeLabel() }}</span>
          <h1 class="cd-code">{{ contract.option_code }}</h1>
          <span class="cd-name">{{ contract.option_name }}</span>
          <span class="cd-moneyness" :style="{ color: moneynessColor() }">{{ moneyness() }}</span>
        </div>
        <div class="cd-sub-row">
          <span class="cd-target-badge">{{ contract.target_name }}</span>
          <span class="cd-sep">·</span>
          <span>到期 {{ contract.expiry_date }}</span>
          <span class="cd-sep">·</span>
          <span>更新 {{ lastRefresh }}</span>
        </div>
      </div>

      <button class="cd-refresh-btn" @click="fetchContract" :disabled="loading">
        <span :class="{ spin: loading }">↻</span>
      </button>
    </div>

    <!-- ═══ HERO METRICS ═══ -->
    <div class="cd-hero">
      <div class="cd-hero-main">
        <div class="cd-price-big">
          <span class="cd-price-label">最新价</span>
          <span class="cd-price-val">{{ fmt(contract.last_price) }}</span>
        </div>
        <div class="cd-price-big cd-strike">
          <span class="cd-price-label">行权价</span>
          <span class="cd-price-val accent">{{ fmtPrice(contract.strike_price) }}</span>
        </div>
        <div class="cd-price-big">
          <span class="cd-price-label">标的价</span>
          <span class="cd-price-val">{{ fmtPrice(contract.target_price) }}</span>
        </div>
      </div>
      <div class="cd-hero-sub">
        <div class="cd-chip">
          <span class="cd-chip-lbl">剩余</span>
          <span class="cd-chip-val">{{ calcDays(contract.expiry_date) }}<em>天</em></span>
        </div>
        <div class="cd-chip">
          <span class="cd-chip-lbl">IV</span>
          <span class="cd-chip-val">{{ fmtPct(contract.implied_volatility) }}</span>
        </div>
        <div class="cd-chip">
          <span class="cd-chip-lbl">理论价</span>
          <span class="cd-chip-val">{{ fmt(contract.theoretical_price) }}</span>
        </div>
        <div class="cd-chip">
          <span class="cd-chip-lbl">杠杆</span>
          <span class="cd-chip-val">{{ contract.leverage_ratio?.toFixed(1) }}x</span>
        </div>
      </div>
    </div>

    <!-- ═══ MAIN GRID ═══ -->
    <div class="cd-grid">

      <!-- ── LEFT COLUMN ── -->
      <div class="cd-col-left">

        <!-- Greeks dashboard -->
        <div class="cd-card">
          <div class="cd-card-title">希腊字母</div>
          <div class="cd-greeks-grid">
            <div class="cd-greek-item" v-for="(g, key) in [
              { key:'delta', label:'Delta', val: displayGreeks?.delta, color: displayGreeks?.delta >= 0 ? 'var(--up)' : 'var(--down)' },
              { key:'gamma', label:'Gamma', val: displayGreeks?.gamma },
              { key:'theta', label:'Theta', val: displayGreeks?.theta, color: 'var(--down)' },
              { key:'vega',  label:'Vega',  val: displayGreeks?.vega },
              { key:'rho',   label:'Rho',   val: displayGreeks?.rho },
            ]" :key="g.key">
              <div class="cd-greek-label">{{ g.label }}</div>
              <div class="cd-greek-val" :style="{ color: g.color || 'var(--text-primary)' }">
                {{ fmt(g.val) }}
              </div>
              <!-- Mini bar visualization -->
              <div class="cd-greek-bar">
                <div
                  class="cd-greek-bar-fill"
                  :style="{
                    width: Math.min(Math.abs(g.val) * 100, 100) + '%',
                    background: g.color || 'var(--accent)',
                    opacity: 0.3
                  }"
                ></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Value breakdown -->
        <div class="cd-card">
          <div class="cd-card-title">价值分解</div>
          <div class="cd-value-breakdown">
            <div class="cd-vb-item">
              <div class="cd-vb-dot" style="background:var(--accent)"></div>
              <div class="cd-vb-info">
                <span class="cd-vb-lbl">内在价值</span>
                <span class="cd-vb-val">{{ fmt(valueBreakdown.intrinsic) }}</span>
              </div>
              <div class="cd-vb-pct" v-if="contract.last_price > 0">
                {{ (valueBreakdown.intrinsic / contract.last_price * 100).toFixed(0) }}%
              </div>
            </div>
            <div class="cd-vb-item">
              <div class="cd-vb-dot" style="background:var(--text-muted)"></div>
              <div class="cd-vb-info">
                <span class="cd-vb-lbl">时间价值</span>
                <span class="cd-vb-val">{{ fmt(valueBreakdown.time) }}</span>
              </div>
              <div class="cd-vb-pct" v-if="contract.last_price > 0">
                {{ (valueBreakdown.time / contract.last_price * 100).toFixed(0) }}%
              </div>
            </div>
          </div>
          <!-- Visual bar -->
          <div class="cd-value-bar">
            <div class="cd-vb-fill" :style="{
              width: contract.last_price > 0 ? (valueBreakdown.intrinsic / contract.last_price * 100) + '%' : '50%',
              background: 'var(--accent)'
            }"></div>
            <div class="cd-vb-rest" :style="{
              width: contract.last_price > 0 ? (valueBreakdown.time / contract.last_price * 100) + '%' : '50%',
            }"></div>
          </div>
        </div>

        <!-- Contract info -->
        <div class="cd-card">
          <div class="cd-card-title">合约信息</div>
          <div class="cd-info-list">
            <div class="cd-info-row">
              <span class="cd-info-lbl">期权代码</span>
              <span class="cd-info-val mono">{{ contract.option_code }}</span>
            </div>
            <div class="cd-info-row">
              <span class="cd-info-lbl">期权名称</span>
              <span class="cd-info-val">{{ contract.option_name }}</span>
            </div>
            <div class="cd-info-row">
              <span class="cd-info-lbl">标的名称</span>
              <span class="cd-info-val">{{ contract.target_name }}</span>
            </div>
            <div class="cd-info-row">
              <span class="cd-info-lbl">到期日</span>
              <span class="cd-info-val mono">{{ contract.expiry_date }}</span>
            </div>
            <div class="cd-info-row">
              <span class="cd-info-lbl">行权价</span>
              <span class="cd-info-val mono accent">{{ fmtPrice(contract.strike_price) }}</span>
            </div>
            <div class="cd-info-row">
              <span class="cd-info-lbl">类型</span>
              <span class="cd-info-val" :style="{ color: typeColor() }">{{ contract.option_type }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── RIGHT COLUMN ── -->
      <div class="cd-col-right">

        <!-- BS Calculator -->
        <div class="cd-card bs-card">
          <div class="cd-card-title">BS 定价计算器</div>

          <div class="cd-bs-inputs">
            <div class="cd-bs-input">
              <label>标的价格</label>
              <input type="number" v-model.number="bsSpot" :step="0.01" @change="fetchBsPnl" />
            </div>
            <div class="cd-bs-input">
              <label>波动率</label>
              <input type="number" v-model.number="bsVol" :step="0.01" @change="fetchBsPnl" />
            </div>
            <div class="cd-bs-input">
              <label>距到期(天)</label>
              <input type="number" v-model.number="bsDays" :step="1" @change="fetchBsPnl" />
            </div>
          </div>

          <button class="cd-bs-calc-btn" @click="fetchBsPnl" :disabled="bsLoading">
            <span v-if="bsLoading">计算中...</span>
            <span v-else>重新计算</span>
          </button>

          <!-- BS Result -->
          <div class="cd-bs-result" v-if="bsPnl">
            <div class="cd-bs-main-metrics">
              <div class="cd-bs-metric highlight">
                <span class="cd-bs-lbl">理论价格</span>
                <span class="cd-bs-val">{{ fmt(bsPnl.theoretical_price) }}</span>
              </div>
              <div class="cd-bs-metric">
                <span class="cd-bs-lbl">内在价值</span>
                <span class="cd-bs-val">{{ fmt(bsPnl.intrinsic_value) }}</span>
              </div>
              <div class="cd-bs-metric">
                <span class="cd-bs-lbl">时间价值</span>
                <span class="cd-bs-val">{{ fmt(bsPnl.time_value) }}</span>
              </div>
              <div class="cd-bs-metric">
                <span class="cd-bs-lbl">价差</span>
                <span class="cd-bs-val" :class="chgClass(bsPnl.price_diff)">{{ fmt(bsPnl.price_diff) }}</span>
              </div>
            </div>

            <!-- BS Greeks comparison -->
            <div class="cd-bs-greeks" v-if="bsGreeks">
              <div class="cd-bs-greek-row" v-for="g in [
                { key:'delta', label:'Delta' },
                { key:'gamma', label:'Gamma' },
                { key:'theta', label:'Theta' },
                { key:'vega',  label:'Vega' },
                { key:'rho',   label:'Rho' },
              ]" :key="g.key">
                <span class="cd-bs-glbl">{{ g.label }}</span>
                <span class="cd-bs-gval" :class="bsGreeks[g.key] >= 0 ? 'val-up' : 'val-down'">
                  {{ fmt(bsGreeks[g.key]) }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- PnL Chart -->
        <div class="cd-card chart-card" v-if="bsPnl?.pnl_profile">
          <div class="cd-card-title">盈亏曲线</div>
          <div class="cd-chart-wrap">
            <canvas ref="pnlChart" class="cd-pnl-canvas"></canvas>
          </div>
          <div class="cd-chart-legend">
            <span class="cd-legend-item">
              <span class="cd-legend-dot" style="background:var(--accent)"></span>
              当前标的价格 {{ fmtPrice(bsSpot) }}
            </span>
            <span class="cd-legend-item">
              <span class="cd-legend-dot" :style="{ background: bsPnl.price_diff >= 0 ? 'var(--up)' : 'var(--down)' }"></span>
              当前盈亏 {{ fmt(bsPnl.price_diff) }}
            </span>
          </div>
        </div>

      </div>
    </div>
  </div>

  <!-- Loading -->
  <div class="cd-loading" v-else>
    <div class="cd-loading-spinner"></div>
    <p>加载合约数据...</p>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════
   Contract Detail Page
   ═══════════════════════════════════════════ */
.cd-page {
  animation: fadeIn 0.35s ease;
}

/* ═══ TOP BAR ═══ */
.cd-topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.cd-back {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.cd-back:hover {
  border-color: var(--accent-dim);
  color: var(--text-primary);
}
.cd-back-icon {
  font-size: 16px;
  line-height: 1;
}

.cd-title-block {
  flex: 1;
  min-width: 0;
}
.cd-title-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.cd-direction-badge {
  font-size: 10px;
  font-weight: 700;
  color: var(--bg-deep);
  padding: 2px 7px;
  border-radius: 3px;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}
.cd-code {
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  margin: 0;
  line-height: 1.2;
}
.cd-name {
  font-size: 14px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cd-moneyness {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border: 1px solid currentColor;
  border-radius: 3px;
  flex-shrink: 0;
}

.cd-sub-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  flex-wrap: wrap;
}
.cd-target-badge {
  font-weight: 600;
  color: var(--text-secondary);
}
.cd-sep {
  color: var(--border-light);
}

.cd-refresh-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 18px;
  flex-shrink: 0;
  transition: all 0.15s;
}
.cd-refresh-btn:hover {
  border-color: var(--accent-dim);
  color: var(--accent);
}
.cd-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ═══ HERO METRICS ═══ */
.cd-hero {
  background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-primary) 100%);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
  margin-bottom: 20px;
  position: relative;
  overflow: hidden;
}
.cd-hero::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, v-bind('typeColor()'), transparent);
  opacity: 0.4;
}

.cd-hero-main {
  display: flex;
  align-items: flex-end;
  gap: 32px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.cd-price-big {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cd-price-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.cd-price-val {
  font-family: var(--font-mono);
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  line-height: 1;
}
.cd-price-val.accent {
  color: var(--accent);
}
.cd-strike .cd-price-val {
  color: var(--accent);
}

.cd-hero-sub {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.cd-chip {
  display: flex;
  align-items: baseline;
  gap: 6px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 12px;
}
.cd-chip-lbl {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.cd-chip-val {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.cd-chip-val em {
  font-style: normal;
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 2px;
}

/* ═══ MAIN GRID ═══ */
.cd-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}
.cd-col-left, .cd-col-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Cards ── */
.cd-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 18px;
  box-shadow: var(--shadow-card);
}
.cd-card-title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.cd-card-title::before {
  content: '';
  width: 3px;
  height: 12px;
  background: var(--accent);
  border-radius: 2px;
  display: inline-block;
}

/* ── Greeks ── */
.cd-greeks-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}
.cd-greek-item {
  text-align: center;
  padding: 10px 6px;
  background: var(--bg-primary);
  border-radius: 6px;
  border: 1px solid var(--border);
}
.cd-greek-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 4px;
}
.cd-greek-val {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 6px;
}
.cd-greek-bar {
  height: 3px;
  background: var(--bg-deep);
  border-radius: 2px;
  overflow: hidden;
}
.cd-greek-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

/* ── Value Breakdown ── */
.cd-value-breakdown {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.cd-vb-item {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cd-vb-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cd-vb-info {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.cd-vb-lbl {
  font-size: 13px;
  color: var(--text-secondary);
}
.cd-vb-val {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.cd-vb-pct {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  min-width: 36px;
  text-align: right;
}
.cd-value-bar {
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  display: flex;
  background: var(--bg-deep);
}
.cd-vb-fill {
  height: 100%;
  transition: width 0.4s;
}
.cd-vb-rest {
  height: 100%;
  background: var(--text-dim);
  transition: width 0.4s;
}

/* ── Info List ── */
.cd-info-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cd-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid var(--border);
}
.cd-info-row:last-child { border-bottom: none; }
.cd-info-lbl {
  font-size: 12px;
  color: var(--text-muted);
}
.cd-info-val {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}
.cd-info-val.mono {
  font-family: var(--font-mono);
}
.cd-info-val.accent {
  color: var(--accent);
  font-weight: 700;
}

/* ── BS Calculator ── */
.bs-card {
  border-color: rgba(240,160,48,0.15);
}
.cd-bs-inputs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}
.cd-bs-input label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 4px;
}
.cd-bs-input input {
  width: 100%;
  padding: 8px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
  -moz-appearance: textfield;
}
.cd-bs-input input:focus {
  border-color: var(--accent-dim);
}
.cd-bs-input input::-webkit-inner-spin-button,
.cd-bs-input input::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.cd-bs-calc-btn {
  width: 100%;
  padding: 8px;
  background: var(--accent-soft);
  border: 1px solid var(--accent-dim);
  border-radius: 5px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 14px;
}
.cd-bs-calc-btn:hover {
  background: rgba(240,160,48,0.15);
}
.cd-bs-calc-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* BS Result */
.cd-bs-result {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px;
}
.cd-bs-main-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}
.cd-bs-metric {
  text-align: center;
  padding: 8px 4px;
  border-radius: 4px;
}
.cd-bs-metric.highlight {
  background: var(--accent-soft);
  border: 1px solid rgba(240,160,48,0.2);
}
.cd-bs-metric.highlight .cd-bs-val {
  color: var(--accent);
  font-size: 18px;
}
.cd-bs-lbl {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 3px;
}
.cd-bs-val {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

/* BS Greeks */
.cd-bs-greeks {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.cd-bs-greek-row {
  text-align: center;
}
.cd-bs-glbl {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  font-weight: 600;
  display: block;
  margin-bottom: 2px;
}
.cd-bs-gval {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}

/* ── Chart ── */
.chart-card {
  padding-bottom: 14px;
}
.cd-chart-wrap {
  position: relative;
  margin-bottom: 10px;
}
.cd-pnl-canvas {
  width: 100%;
  height: 220px;
  border-radius: 6px;
  display: block;
}
.cd-chart-legend {
  display: flex;
  gap: 16px;
  justify-content: center;
  font-size: 11px;
  color: var(--text-muted);
}
.cd-legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.cd-legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

/* ═══ Loading ═══ */
.cd-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  color: var(--text-muted);
  gap: 16px;
}
.cd-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ═══ Responsive ═══ */
@media (max-width: 900px) {
  .cd-grid {
    grid-template-columns: 1fr;
  }
  .cd-hero-main {
    gap: 20px;
  }
  .cd-price-val {
    font-size: 28px;
  }
  .cd-greeks-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .cd-bs-main-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
  .cd-bs-greeks {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
