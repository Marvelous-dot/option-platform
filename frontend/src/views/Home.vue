<script setup>
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { getCssVars } from '@/utils/cssVar'

const router = useRouter()

const targets = ref([])
const clock = ref('')
const clockTimer = null

// ── K-line chart state ──
const klineTarget = ref('510050')
const klineData = ref([])
const klineLoading = ref(false)
const klineCanvas = ref(null)

const fetchKline = async (targetCode) => {
  if (klineLoading.value) return
  klineLoading.value = true
  try {
    const res = await fetch(`/api/kline/${targetCode}?days=90`)
    const data = await res.json()
    klineData.value = data.data || []
    nextTick(() => renderKlineChart())
  } catch (e) {
    console.error('fetchKline:', e)
  } finally {
    klineLoading.value = false
  }
}

function renderKlineChart() {
  const canvas = klineCanvas.value
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

  // Compute price range from high/low
  const highs = data.map(d => d.high)
  const lows = data.map(d => d.low)
  const minP = Math.min(...lows) * 0.998
  const maxP = Math.max(...highs) * 1.002
  const range = maxP - minP || 0.01

  const pad = { top: 28, right: 50, bottom: 24, left: 56 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const xOf = (i) => pad.left + (i + 0.5) / Math.max(data.length, 1) * cw
  const yOf = (v) => pad.top + ch - (v - minP) / range * ch

  const candleW = Math.max(2, Math.min(20, cw / data.length * 0.6))

  // Clear
  ctx.fillStyle = vars.bgCard
  ctx.fillRect(0, 0, W, H)

  // Grid
  ctx.strokeStyle = vars.border
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ch * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
  }

  // Y labels
  ctx.fillStyle = vars.textDim
  ctx.font = '10px ' + vars.fontMono
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = maxP - range * i / 4
    const y = pad.top + ch * i / 4
    ctx.fillText(v.toFixed(3), pad.left - 8, y + 3)
  }

  // Draw candlesticks
  for (let i = 0; i < data.length; i++) {
    const d = data[i]
    const x = xOf(i)
    const isUp = d.close >= d.open
    const color = isUp ? vars.up : vars.down

    // Wick (high-low line)
    ctx.strokeStyle = color
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, yOf(d.high))
    ctx.lineTo(x, yOf(d.low))
    ctx.stroke()

    // Body (open-close rectangle)
    const yOpen = yOf(d.open)
    const yClose = yOf(d.close)
    const bodyTop = Math.min(yOpen, yClose)
    const bodyH = Math.max(1, Math.abs(yOpen - yClose))

    ctx.fillStyle = color
    ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH)

    // Border for hollow effect on up candles
    if (isUp) {
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.strokeRect(x - candleW / 2, bodyTop, candleW, bodyH)
    }
  }

  // X labels (dates)
  ctx.textAlign = 'center'
  ctx.fillStyle = vars.textDim
  ctx.font = '10px ' + vars.fontMono
  const step = Math.max(1, Math.floor(data.length / 6))
  for (let i = 0; i < data.length; i += step) {
    const x = xOf(i)
    const date = data[i].date ? data[i].date.slice(5, 10) : ''
    ctx.fillText(date, x, H - pad.bottom + 14)
  }

  // Last price label
  const last = data[data.length - 1]
  const lx = xOf(data.length - 1)
  const ly = yOf(last.close)
  ctx.fillStyle = last.close >= last.open ? vars.up : vars.down
  ctx.font = 'bold 11px ' + vars.fontMono
  ctx.textAlign = 'right'
  ctx.fillText(last.close.toFixed(3), W - pad.right + 2, ly + 4)

  // Title
  ctx.fillStyle = vars.textMuted
  ctx.font = '11px ' + vars.fontSans
  ctx.textAlign = 'left'
  ctx.fillText('K线图 (30日)', pad.left, 16)
}

const fetchTargets = async () => {
  try {
    const res = await fetch('/api/targets')
    targets.value = (await res.json()).targets || []
  } catch (e) { console.error('fetchTargets:', e) }
}

onMounted(() => {
  fetchTargets()
  clockTimer = setInterval(() => {
    clock.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  }, 1000)
})

// Fetch K-line when targets are loaded
watch(targets, (newTargets) => {
  if (newTargets.length && !klineData.value.length) {
    fetchKline(klineTarget.value)
  }
}, { immediate: false })

const refreshInterval = setInterval(() => {
  fetchTargets()
}, 30000)

onUnmounted(() => {
  clearInterval(refreshInterval)
  if (clockTimer) clearInterval(clockTimer)
})

// ── Computed ──
const totalCall = computed(() => targets.value.reduce((s, t) => s + (t.call_count || 0), 0))
const totalPut  = computed(() => targets.value.reduce((s, t) => s + (t.put_count || 0), 0))
const totalCallPct = computed(() => {
  const total = totalCall.value + totalPut.value
  return total ? Math.round(totalCall.value / total * 100) : 50
})

// All contracts flattened, sorted by "interesting": ATM first, then by time_value
const topContracts = computed(() => {
  const all = []
  for (const t of targets.value) {
    const spot = t.latest_price || 0
    for (const c of (t.contracts || [])) {
      const dist = spot > 0 ? Math.abs(c.strike_price - spot) / spot : 1
      all.push({
        ...c,
        target_code: t.target,
        target_name: t.target_name,
        spot,
        isCall: c.option_type === '认购',
        // nearness score: lower = more interesting
        _score: dist,
      })
    }
  }
  // Sort by closeness to ATM, take 20
  all.sort((a, b) => a._score - b._score)
  return all.slice(0, 20)
})

// ── Helpers ──
function statusText() {
  if (!targets.value.length) return '连接中...'
  return '实时同步中'
}
function statusColor() {
  if (!targets.value.length) return 'var(--text-muted)'
  return 'var(--down)'
}
function fmtPrice(v) {
  if (v == null) return '--'
  return Number(v).toFixed(3)
}
function fmtChange(v) {
  if (v == null) return { text: '--', cls: 'val-neu' }
  const n = Number(v)
  const sign = n > 0 ? '+' : ''
  const cls = n > 0 ? 'val-up' : n < 0 ? 'val-down' : 'val-neu'
  return { text: sign + n.toFixed(3), cls }
}
function fmtVol(v) {
  if (v == null) return '--'
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return v.toLocaleString()
}
function getPrice(t) {
  if (t.latest_price != null) return Number(t.latest_price).toFixed(3)
  return '--'
}
function getVol(t) {
  if (t.volatility != null) return (Number(t.volatility) * 100).toFixed(1) + '%'
  return '--'
}
function callPct(t) {
  const total = (t.call_count || 0) + (t.put_count || 0)
  if (!total) return 50
  return Math.round((t.call_count || 0) / total * 100)
}
function contractLabel(c) {
  if (c.option_type === '认购') return 'Call'
  return 'Put'
}
function contractColor(c) {
  return c.option_type === '认购' ? 'var(--up)' : 'var(--down)'
}
function strikeClass(c) {
  if (c.spot <= 0) return ''
  const dist = Math.abs(c.strike_price - c.spot)
  if (dist < 0.001) return 'strike-atm'
  if (dist / c.spot < 0.03) return 'strike-near'
  return ''
}
</script>

<template>
  <div class="dashboard">

    <!-- ═══ HERO TOP BAR ═══ -->
    <div class="hero-bar">
      <div class="hero-left">
        <div class="hero-clock">{{ clock || '--:--:--' }}</div>
        <div class="hero-date">{{ new Date().toLocaleDateString('zh-CN', { year:'numeric', month:'long', day:'numeric', weekday:'short' }) }}</div>
      </div>
      <div class="hero-center">
        <div class="hero-stat">
          <div class="hero-stat-label">覆盖标的</div>
          <div class="hero-stat-value accent">{{ targets.length || '--' }}</div>
        </div>
        <div class="hero-divider"></div>
        <div class="hero-stat">
          <div class="hero-stat-label">合约总数</div>
          <div class="hero-stat-value">{{ totalCall + totalPut || '--' }}</div>
        </div>
        <div class="hero-divider"></div>
        <div class="hero-stat">
          <div class="hero-stat-label">认购 / 认沽</div>
          <div class="hero-stat-value hero-ratio">
            <span class="ratio-call">{{ totalCall }}</span>
            <span class="ratio-sep">:</span>
            <span class="ratio-put">{{ totalPut }}</span>
          </div>
        </div>
        <div class="hero-divider"></div>
        <div class="hero-stat">
          <div class="hero-stat-label">多空比</div>
          <div class="hero-stat-value">
            <span class="ratio-call">{{ totalCallPct }}</span><span class="ratio-pct">%</span>
          </div>
        </div>
      </div>
      <div class="hero-right">
        <div class="status-indicator" :style="{ '--dot-color': statusColor() }">
          <span class="status-dot"></span>
          <span class="status-label">{{ statusText() }}</span>
        </div>
        <div class="hero-refresh">标的数 {{ targets.length }}</div>
      </div>
    </div>

    <!-- ═══ K-LINE CHART ═══ -->
    <section class="section-kline">
      <div class="section-header">
        <h2 class="section-title">标的价格走势</h2>
        <div class="kline-targets">
          <button
            v-for="t in targets"
            :key="t.target"
            :class="['kline-target-btn', { active: klineTarget === t.target }]"
            @click="klineTarget = t.target; fetchKline(t.target)"
          >
            {{ t.target }}
          </button>
        </div>
      </div>
      <div class="kline-chart-wrap">
        <canvas ref="klineCanvas" class="kline-canvas"></canvas>
        <div class="kline-empty" v-if="!klineData.length && !klineLoading">
          <div class="empty-icon">◈</div>
          <p>加载中...</p>
        </div>
      </div>
    </section>

    <!-- ═══ TARGET CARDS ROW ═══ -->
    <section class="section-targets">
      <div class="section-header">
        <h2 class="section-title">标的概览</h2>
        <span class="section-hint">点击跳转 T 型报价</span>
      </div>
      <div class="targets-cards">
        <div
          class="target-card"
          v-for="t in targets"
          :key="t.target"
          @click="router.push('/tquote')"
        >
          <!-- Card header -->
          <div class="tc-header">
            <div class="tc-symbol">
              <span class="tc-code">{{ t.target }}</span>
              <span class="tc-badge">ETF</span>
            </div>
            <div class="tc-contracts">
              <span class="tc-num">{{ t.contract_count }}</span>
              <span class="tc-unit">合约</span>
            </div>
          </div>

          <!-- Name -->
          <div class="tc-name">{{ t.target_name }}</div>

          <!-- Price big -->
          <div class="tc-price-block">
            <span class="tc-price">{{ getPrice(t) }}</span>
            <span class="tc-vol-badge">
              <span class="tc-vol-lbl">IV</span>
              <span class="tc-vol-val">{{ getVol(t) }}</span>
            </span>
          </div>

          <!-- Call/Put ratio bar -->
          <div class="tc-ratio-bar">
            <div class="tc-bar-call" :style="{ width: callPct(t) + '%' }">
              <span v-if="callPct(t) > 20" class="tc-bar-text">C {{ t.call_count }}</span>
            </div>
            <div class="tc-bar-put" :style="{ width: (100 - callPct(t)) + '%' }">
              <span v-if="(100 - callPct(t)) > 20" class="tc-bar-text">P {{ t.put_count }}</span>
            </div>
          </div>
          <div class="tc-ratio-labels">
            <span class="tc-lbl-call">认购 {{ t.call_count }}</span>
            <span class="tc-lbl-put">认沽 {{ t.put_count }}</span>
          </div>

          <!-- Quick stats row -->
          <div class="tc-footer">
            <div class="tc-stat">
              <span class="tc-st-lbl">认购</span>
              <span class="tc-st-val" style="color:var(--up)">{{ t.call_count }}</span>
            </div>
            <div class="tc-sep"></div>
            <div class="tc-stat">
              <span class="tc-st-lbl">认沽</span>
              <span class="tc-st-val" style="color:var(--down)">{{ t.put_count }}</span>
            </div>
            <div class="tc-sep"></div>
            <div class="tc-stat">
              <span class="tc-st-lbl">波动率</span>
              <span class="tc-st-val">{{ getVol(t) }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ ACTIVE CONTRACTS TABLE ═══ -->
    <section class="section-contracts">
      <div class="section-header">
        <h2 class="section-title">ATM 附近合约</h2>
        <span class="section-hint">距现货最近的 20 条合约 · 点击查看详情</span>
      </div>
      <div class="contracts-table-wrap" v-if="topContracts.length">
        <table class="contracts-table">
          <thead>
            <tr>
              <th class="th-code">合约</th>
              <th class="th-type">方向</th>
              <th class="th-num">行权价</th>
              <th class="th-num">最新价</th>
              <th class="th-num">Delta</th>
              <th class="th-num">Gamma</th>
              <th class="th-num">Theta</th>
              <th class="th-num">IV</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in topContracts"
              :key="c.option_code"
              class="c-row"
              @click="router.push(`/contract/${c.option_code}`)"
            >
              <!-- Code + name + target -->
              <td class="td-cell td-code">
                <div class="c-code-badge">
                  <span class="c-direction" :style="{ background: contractColor(c) }">{{ contractLabel(c) }}</span>
                  <div class="c-code-name">
                    <span class="c-code">{{ c.option_code }}</span>
                    <span class="c-target">{{ c.target_code }}</span>
                  </div>
                </div>
              </td>
              <!-- Type label -->
              <td class="td-cell td-type">
                <span class="c-type-tag" :style="{ color: contractColor(c), borderColor: contractColor(c) + '33' }">
                  {{ c.option_type }}
                </span>
              </td>
              <!-- Strike -->
              <td class="td-cell td-num">
                <span class="strike-val" :class="strikeClass(c)">{{ c.strike_price?.toFixed(3) }}</span>
              </td>
              <!-- Price -->
              <td class="td-cell td-num">
                <span class="c-price">{{ c.last_price?.toFixed(4) }}</span>
              </td>
              <!-- Greeks -->
              <td class="td-cell td-num td-greek">
                <span class="greek-val" :class="c.delta > 0 ? 'val-up' : 'val-down'">
                  {{ c.delta?.toFixed(4) }}
                </span>
              </td>
              <td class="td-cell td-num td-greek">
                <span class="greek-val">{{ c.gamma?.toFixed(4) }}</span>
              </td>
              <td class="td-cell td-num td-greek">
                <span class="greek-val" :class="c.theta < 0 ? 'val-down' : ''">
                  {{ c.theta?.toFixed(4) }}
                </span>
              </td>
              <td class="td-cell td-num td-greek">
                <span class="greek-val">{{ (c.implied_volatility * 100)?.toFixed(1) }}%</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="contracts-empty" v-else>
        <div class="empty-icon">◈</div>
        <p>数据加载中...</p>
      </div>
    </section>

  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════
   Dashboard Layout
   ═══════════════════════════════════════════ */
.dashboard {
  animation: fadeIn 0.4s ease;
}

/* ═══ HERO BAR ═══ */
.hero-bar {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-primary) 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px 28px;
  margin-bottom: 24px;
  position: relative;
  overflow: hidden;
}

.hero-bar::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  opacity: 0.6;
}

.hero-bar::after {
  content: '';
  position: absolute;
  top: -50%; right: -20%;
  width: 400px; height: 400px;
  background: radial-gradient(circle, var(--accent-glow) 0%, transparent 60%);
  border-radius: 50%;
  pointer-events: none;
}

.hero-left {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  flex-shrink: 0;
  min-width: 140px;
}
.hero-clock {
  font-family: var(--font-mono);
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.04em;
  line-height: 1;
}
.hero-date {
  font-size: 12px;
  color: var(--text-muted);
}

.hero-center {
  display: flex;
  align-items: center;
  gap: 28px;
  flex: 1;
  justify-content: center;
}
.hero-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.hero-stat-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  font-weight: 600;
}
.hero-stat-value {
  font-family: var(--font-mono);
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  line-height: 1;
}
.hero-stat-value.accent {
  color: var(--accent);
}
.hero-divider {
  width: 1px;
  height: 36px;
  background: var(--border);
  flex-shrink: 0;
}

.hero-ratio {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.ratio-call { color: var(--up); }
.ratio-put  { color: var(--down); }
.ratio-sep  { color: var(--text-muted); font-size: 18px; }
.ratio-pct  { font-size: 14px; color: var(--text-muted); margin-left: 2px; }

.hero-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 6px;
  flex-shrink: 0;
  min-width: 140px;
}
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--dot-color);
  display: inline-block;
  animation: pulse 2s ease-in-out infinite;
}
.status-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--dot-color);
}
.hero-refresh {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

/* ═══ SECTIONS ═══ */
section {
  margin-bottom: 24px;
}
.section-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 14px;
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-title::before {
  content: '';
  width: 3px;
  height: 16px;
  background: var(--accent);
  border-radius: 2px;
  display: inline-block;
}
.section-hint {
  font-size: 12px;
  color: var(--text-muted);
}

/* ═══ TARGET CARDS ═══ */
.targets-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.target-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
  animation: fadeInUp 0.4s ease both;
}
.target-card:nth-child(1) { animation-delay: 0.05s; }
.target-card:nth-child(2) { animation-delay: 0.1s; }
.target-card:nth-child(3) { animation-delay: 0.15s; }
.target-card:nth-child(4) { animation-delay: 0.2s; }
.target-card:nth-child(5) { animation-delay: 0.25s; }
.target-card:nth-child(6) { animation-delay: 0.3s; }
.target-card::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-light), transparent);
}
.target-card:hover {
  border-color: var(--accent-dim);
  box-shadow: 0 4px 20px rgba(0,0,0,0.4), 0 0 1px var(--accent-soft);
  transform: translateY(-2px);
}

.tc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.tc-symbol {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tc-code {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--accent);
}
.tc-badge {
  font-size: 9px;
  font-weight: 700;
  color: var(--text-muted);
  background: var(--bg-deep);
  border: 1px solid var(--border);
  padding: 1px 5px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.tc-contracts {
  display: flex;
  align-items: baseline;
  gap: 3px;
}
.tc-num {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.tc-unit {
  font-size: 10px;
  color: var(--text-muted);
}

.tc-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 14px;
}

/* Price block */
.tc-price-block {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}
.tc-price {
  font-family: var(--font-mono);
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  line-height: 1;
}
.tc-vol-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 8px;
}
.tc-vol-lbl {
  font-size: 8px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  font-weight: 700;
}
.tc-vol-val {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
}

/* Ratio bar */
.tc-ratio-bar {
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  background: var(--bg-deep);
  margin-bottom: 6px;
}
.tc-bar-call {
  background: var(--up);
  height: 100%;
  transition: width 0.4s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 2px;
}
.tc-bar-put {
  background: var(--down);
  height: 100%;
  transition: width 0.4s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 2px;
}
.tc-bar-text {
  font-size: 8px;
  font-weight: 700;
  color: var(--bg-deep);
  white-space: nowrap;
}
.tc-ratio-labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  margin-bottom: 12px;
}
.tc-lbl-call { color: var(--up); }
.tc-lbl-put  { color: var(--down); }

/* Footer stats */
.tc-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.tc-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.tc-st-lbl {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.tc-st-val {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
}
.tc-sep {
  width: 1px;
  height: 24px;
  background: var(--border);
}

/* ═══ CONTRACTS TABLE ═══ */
.contracts-table-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: auto;
  box-shadow: var(--shadow-card);
  max-height: 520px;
}

.contracts-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 700px;
}

.contracts-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
}

.contracts-table th {
  background: var(--bg-primary);
  color: var(--text-muted);
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 10px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
  white-space: nowrap;
}
.contracts-table th.th-num {
  text-align: right;
}

.contracts-table td {
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.c-row {
  cursor: pointer;
  transition: background 0.1s;
}
.c-row:hover {
  background: var(--bg-row-hover);
}
.c-row:last-child td {
  border-bottom: none;
}

/* Code cell */
.td-code { min-width: 180px; }
.c-code-badge {
  display: flex;
  align-items: center;
  gap: 8px;
}
.c-direction {
  font-size: 9px;
  font-weight: 700;
  color: var(--bg-deep);
  padding: 2px 5px;
  border-radius: 3px;
  flex-shrink: 0;
  letter-spacing: 0.04em;
}
.c-code-name {
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow: hidden;
}
.c-code {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.c-target {
  font-size: 10px;
  color: var(--text-muted);
}

/* Type tag */
.td-type { width: 60px; }
.c-type-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid;
  background: transparent;
}

/* Numbers */
.td-num {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: nowrap;
}
.td-greek {
  color: var(--text-secondary);
}

.strike-val {
  font-weight: 600;
  color: var(--text-primary);
}
.strike-atm {
  color: var(--accent);
  font-weight: 700;
  position: relative;
}
.strike-atm::after {
  content: 'ATM';
  font-size: 8px;
  font-weight: 700;
  background: var(--accent);
  color: var(--bg-deep);
  padding: 1px 4px;
  border-radius: 2px;
  margin-left: 4px;
  vertical-align: middle;
}
.strike-near {
  color: var(--accent-dim);
}

.c-price {
  font-weight: 600;
  color: var(--text-primary);
}
.greek-val {
  font-size: 12px;
}

/* Empty state */
.contracts-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.empty-icon {
  font-size: 32px;
  margin-bottom: 12px;
  color: var(--border-light);
}

/* ═══ K-LINE CHART ═══ */
.section-kline {
  margin-bottom: 24px;
}

.kline-chart-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--shadow-card);
  position: relative;
  height: 240px;
}

.kline-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.kline-targets {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.kline-target-btn {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-deep);
  color: var(--text-muted);
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.kline-target-btn:hover {
  border-color: var(--accent-dim);
  color: var(--text-secondary);
}

.kline-target-btn.active {
  background: var(--accent);
  color: var(--bg-deep);
  border-color: var(--accent);
}

.kline-empty {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.kline-empty .empty-icon {
  font-size: 28px;
  margin-bottom: 10px;
  color: var(--border-light);
}

.kline-empty p {
  font-size: 12px;
  margin: 0;
}

/* ═══ Responsive ═══ */
@media (max-width: 900px) {
  .hero-bar {
    flex-direction: column;
    gap: 16px;
    padding: 16px;
  }
  .hero-center {
    gap: 16px;
    flex-wrap: wrap;
  }
  .hero-stat-value {
    font-size: 20px;
  }
  .hero-right {
    align-items: flex-start;
  }
  .targets-cards {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
  .tc-price {
    font-size: 26px;
  }
}
@media (max-width: 768px) {
  .hero-bar { padding: 12px 14px; }
  .hero-stat-value { font-size: 16px; }
  .hero-stat-label { font-size: 9px; }
  .targets-cards { grid-template-columns: 1fr; }
  .tc-card { padding: 14px; }
  .tc-price { font-size: 22px; }
  .tc-change { font-size: 12px; }
  .tc-detail-grid { grid-template-columns: 1fr 1fr; }
  .section-title { font-size: 12px; }
}
</style>
