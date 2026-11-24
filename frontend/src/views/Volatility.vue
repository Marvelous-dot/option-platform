<template>
  <section class="volatility-page">
    <div class="page-head">
      <div class="ph-title">
        <span class="ph-kicker">VOLATILITY · IV 微笑 / 期限结构 / 跨期对比</span>
        <h1>波动率分析</h1>
        <p class="ph-desc">IV 为数据源（新浪财经）计算值原样透传，并非本地反推的市场隐含波动率，也未经验证；数据缺失、空值、NaN、负值与 0 均判为无效，过期数据标 stale。</p>
      </div>
      <div class="ph-actions">
        <span class="ph-note warn">数据源计算 · 口径未核验</span>
      </div>
    </div>

    <div class="controls">
      <label class="field">标的
        <select v-model="target" @change="changeTarget">
          <option v-for="t in targets" :key="t.code" :value="t.code">{{ t.name }}</option>
        </select>
      </label>
      <label class="field">到期日
        <select v-model="expiry">
          <option value="">全部到期日</option>
          <option v-for="e in expiries" :key="e" :value="e">{{ fmtExpiry(e) }}</option>
        </select>
      </label>
      <button class="refresh-btn" type="button" @click="load()" :disabled="loading">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div v-if="ivCur" class="table-card iv-level">
      <div class="lv-head">
        <h2>IV 水位<span class="lv-sub">恒定 30 天平值 · 每日收盘采样</span></h2>
        <span class="lv-date">{{ ivCur.trade_date || '--' }} 收盘</span>
      </div>
      <div class="lv-grid">
        <div class="lv-cell">
          <span class="lv-k">IV30</span>
          <span class="lv-v">{{ fmtIv(ivCur.iv30) }}<i>%</i></span>
          <span class="lv-h">30 天平值隐含波动</span>
        </div>
        <div class="lv-cell">
          <span class="lv-k">RV20</span>
          <span class="lv-v">{{ fmtIv(ivCur.rv20) }}<i>%</i></span>
          <span class="lv-h">20 日实际波动年化</span>
        </div>
        <div class="lv-cell">
          <span class="lv-k">VRP</span>
          <span class="lv-v" :class="ivCur.vrp == null ? '' : (ivCur.vrp > 0 ? 'pos' : 'neg')">{{ vrpText }}</span>
          <span class="lv-h">正＝期权偏贵</span>
        </div>
        <div class="lv-gauge-row">
          <div class="gauge-top">
            <span class="lv-k">IV Rank</span>
            <template v-if="ivCur.ivr != null">
              <span class="gauge-val" :class="ivrTone">{{ ivCur.ivr.toFixed(0) }}<i>/100</i></span>
              <span class="gauge-pct">IV Percentile {{ ivCur.ivp != null ? ivCur.ivp.toFixed(0) : '--' }}%</span>
            </template>
            <span v-else class="gauge-val dim">--</span>
          </div>
          <div v-if="ivCur.ivr != null" class="gauge">
            <div class="gauge-track">
              <span class="gauge-fill" :class="ivrTone" :style="{ width: ivCur.ivr + '%' }"></span>
              <span class="gauge-dot" :class="ivrTone" :style="{ left: ivCur.ivr + '%' }"></span>
            </div>
            <div class="gauge-ticks"><span>便宜（适合买方）</span><span>中性</span><span>贵（适合卖方）</span></div>
          </div>
          <div v-else class="warm">
            <div class="warm-track"><span :style="{ width: warmPct + '%' }"></span></div>
            <span class="warm-txt">还需 {{ Math.max(0, ivCur.min_samples - ivCur.samples) }} 日</span>
          </div>
          <span class="lv-h">{{ ivCur.status_detail }}</span>
        </div>
      </div>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!model && !loading" class="empty">加载中或暂无数据</p>

    <div v-if="model.groups && model.groups.length" class="chart-card surface-card">
      <h2>3D 波动率曲面</h2>
      <p class="note">
        行权价 × 到期日 × IV 三维视角；取数遵循 OTM 惯例（行权价低于现价取认沽 IV、不低于现价取认购 IV），
        并剔除 IV &lt; 2% 的退化值（深度实值认购的源数据伪值）。相邻挂牌点之间线性过渡、不外推、不补缺失。
        IV 为数据源计算值原样透传、口径未核验。本图始终使用全部到期日，不受上方到期日筛选影响。
        拖拽旋转视角，滚轮缩放，双击或点「重置视角」复位，悬停数据点可查看具体合约。
      </p>
      <VolSurface3D v-if="model.groups.length >= 2" :groups="model.groups" :spot="surfaceSpot" />
      <p v-else class="empty">到期日不足两张，无法构成曲面。</p>
    </div>

    <template v-if="selected">
      <div class="meta-bar">
        <span>来源：{{ selected.source || 'sina' }}</span>
        <span>报价时间：{{ formatTs(selected.marketTs) }}</span>
        <span>获取时间：{{ formatTs(selected.fetchedAt) }}</span>
        <span class="ts-note">非实时快照</span>
        <span :class="'status-' + selected.status">{{ statusLabel(selected.status) }}</span>
        <span v-if="staleFlag" class="warn">过期数据，仅供参考</span>
      </div>

      <div class="charts">
        <div class="chart-card">
          <h2>IV 微笑</h2>
          <p class="note">横轴：行权价；纵轴：IV（%）。call/put 分别绘制，缺失/无效 IV 留空不补零。</p>
          <svg viewBox="0 0 650 280" role="img" aria-label="IV 微笑">
            <g v-for="tick in smileChart.ticks" :key="'xt' + tick.label">
              <text :x="tick.x" y="255" text-anchor="middle">{{ tick.label }}</text>
            </g>
            <g v-for="tick in smileChart.yTicks" :key="'yt' + tick.value">
              <line :x1="62" :x2="620" :y1="tick.y" :y2="tick.y" class="grid-line" />
              <text x="70" :y="tick.y + 4" text-anchor="end" class="axis-label">{{ formatTick(tick.value) }}</text>
            </g>
            <g v-for="series in smileChart.series" :key="series.side">
              <polyline v-for="seg in series.segments" :key="'seg' + seg" :points="seg"
                :class="series.side === 'call' ? 'smile-call' : 'smile-put'" />
              <g v-for="p in series.points" :key="p.option_code">
                <circle :cx="p.x" :cy="p.y" r="3" :class="`pt-${p.ivStatus || 'unavailable'}`" />
              </g>
            </g>
            <text x="620" y="16" text-anchor="end" class="axis-label">行权价 →</text>
            <text x="40" y="18">IV（%）</text>
          </svg>
        </div>

        <div class="chart-card">
          <h2>ATM 期限结构</h2>
          <p class="note">每个到期日取最接近标的现价的挂牌行权价，展示该合约 IV；ATM 缺失时留空。</p>
          <svg viewBox="0 0 650 280" role="img" aria-label="ATM 期限结构">
            <g v-for="tick in termChart.ticks" :key="'xt' + tick.label">
              <text :x="tick.x" y="255" text-anchor="middle">{{ tick.label }}</text>
            </g>
            <g v-for="tick in termChart.yTicks" :key="'yt' + tick.value">
              <line :x1="62" :x2="620" :y1="tick.y" :y2="tick.y" class="grid-line" />
              <text x="70" :y="tick.y + 4" text-anchor="end" class="axis-label">{{ formatTick(tick.value) }}</text>
            </g>
            <g v-for="series in termChart.series" :key="series.side">
              <polyline v-for="seg in series.segments" :key="'seg' + seg" :points="seg"
                :class="series.side === 'call' ? 'term-call' : 'term-put'" />
              <g v-for="(p, i) in series.points" :key="i">
                <circle :cx="p.x" :cy="p.y" r="3" :class="`pt-${p.ivStatus || 'unavailable'}`" />
              </g>
            </g>
            <text v-if="!termChart.series.some(s => s.points.length)" x="325" y="140"
              text-anchor="middle" class="chart-empty">暂无可用的 ATM IV（现价或该行权价合约缺失）</text>
            <text x="620" y="16" text-anchor="end" class="axis-label">到期日 →</text>
            <text x="40" y="18">IV（%）</text>
          </svg>
        </div>
      </div>

      <div class="table-card">
        <h2>跨期 IV 对比</h2>
        <p class="note">
          每个到期日取最接近标的现价的 ATM 行权价，列出认购 / 认沽 ATM 的 IV 与价差。
          价差 = 认购 IV − 认沽 IV，缺失/不可用时显示"不可用"，不做插值。仅对比，不做曲面。
        </p>
        <div class="table-wrap">
          <table class="term-table">
            <thead>
              <tr>
                <th>到期日</th>
                <th>ATM 行权价</th>
                <th>认购 ATM IV</th>
                <th>认沽 ATM IV</th>
                <th>价差（认−购）</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in termComparison" :key="t.expiry">
                <td>{{ fmtExpiry(t.expiry) }}</td>
                <td>{{ t.strike ?? '不可用' }}</td>
                <td :class="{ dim: t.callStatus === 'unavailable' }">{{ t.callIv == null ? '不可用' : formatIV(t.callIv) }}<small v-if="t.callCodes.length">{{ t.callCodes.join(' / ') }}</small></td>
                <td :class="{ dim: t.putStatus === 'unavailable' }">{{ t.putIv == null ? '不可用' : formatIV(t.putIv) }}<small v-if="t.putCodes.length">{{ t.putCodes.join(' / ') }}</small></td>
                <td :class="{ dim: t.diff == null }">{{ t.diff == null ? '不可用' : (t.diff >= 0 ? '+' : '') + t.diff.toFixed(4) }}</td>
                <td class="status-cell">
                  <span :class="'tag-' + t.callStatus">认购{{ t.callStatus === 'unavailable' ? '不可用' : '' }}</span>
                  <span :class="'tag-' + t.putStatus">认沽{{ t.putStatus === 'unavailable' ? '不可用' : '' }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!termComparison.length" class="empty">暂无跨期对比数据。</p>
      </div>

      <details class="table-card raw-card">
        <summary class="raw-head">
          <h2>原始明细</h2>
          <span class="raw-meta">{{ selectedRows.length }} 行 · <span class="raw-open-txt">展开</span><span class="raw-close-txt">收起</span></span>
        </summary>
        <p class="note">按到期日与行权价排序；IV 缺失标记"不可用"；点击合约代码进入详情页。</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>到期日</th><th>行权价</th><th>类型</th><th>合约代码</th>
                <th>IV（%）</th><th>状态</th><th>报价时间</th><th>获取时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in selectedRows" :key="i">
                <td>{{ fmtExpiry(row.expiry) }}</td>
                <td>{{ row.strike }}</td>
                <td>{{ row.option_type }}</td>
                <td><router-link :to="`/contract/${row.option_code}`">{{ row.option_code }}</router-link></td>
                <td>{{ formatIV(row.ivValue) }}</td>
                <td>{{ row.data_status }}</td>
                <td>{{ formatTs(row.market_ts) }}</td>
                <td>{{ formatTs(row.fetched_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>

    <div class="table-card iv-note">
      <h2>IV 口径说明</h2>
      <ul>
        <li><strong>数据来源</strong>：新浪财经按最新价反推的隐含波动率（provider-computed），非本系统 BS 反解，随报价实时变动。</li>
        <li><strong>跨链差异</strong>：同一行权价上认沽 IV 普遍高于认购，且价差随到期拉长而扩大；该价差只宜作相对参考，不宜直接当作套利幅度。</li>
        <li><strong>退化值</strong>：深度实值合约的价格趋近纯内在价值，反推 IV 会趋近 0%（如 0.07%）；3D 曲面已剔除小于 2% 的样本，折线图仍如实保留。</li>
        <li><strong>IV 水位</strong>：IV30 取各到期日平值（最接近现价的行权价，购沽均值）后按剩余天数线性插值到恒定 30 天，不外推；每个交易日 15:35 落盘一次。IVR =（当前 − 窗口最低）/（窗口最高 − 最低）×100，IVP = 窗口内低于当前的天数占比，窗口 252 个交易日，不足 20 个交易日不出值。</li>
        <li><strong>VRP</strong>：IV30 − RV20，RV20 为标的前复权日 K 对数收益的 20 日年化标准差。正数表示期权隐含波动高于近期实际波动（对卖方有利），负数反之；两者时间尺度不同，只作方向参考，不等于可套利空间。</li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { buildVolatility, plotSeries, formatIV, formatTick } from '../utils/volatility.mjs'
import { readState, writeState } from '../utils/remember.mjs'
import VolSurface3D from '../components/VolSurface3D.vue'

const targets = [
  { code: '510050', name: '50ETF(华夏上证50)' },
  { code: '510300', name: '300ETF(华泰柏瑞沪深300)' },
  { code: '510500', name: '500ETF(南方中证500)' },
  { code: '588000', name: '科创50ETF(华夏)' },
  { code: '588080', name: '科创板50ETF(易方达)' },
]
const remembered = readState('volatility', {})
const target = ref(remembered.target || '510050')
const expiry = ref(remembered.expiry || '')
const data = ref(null)
const model = ref(null)
// 始终保持 { coverage: { total: 0 } } 形状，避免 null 引用；清空时 total 归零
model.value = { coverage: { total: 0 } }
const error = ref('')
const loading = ref(false)
const staleFlag = ref(false)
// ---------- IV 水位（历史 IV 库：IV30 / IVR / IVP / VRP）----------
// 与行情快照解耦：历史库不可用时整块隐藏，不影响主图
const ivAll = ref([])
const ivCur = computed(() => ivAll.value.find(t => t.target_code === target.value) || null)
const warmPct = computed(() => {
  const c = ivCur.value
  if (!c || !c.min_samples) return 0
  return Math.min(100, (c.samples / c.min_samples) * 100)
})
const vrpText = computed(() => {
  const v = ivCur.value?.vrp
  if (v == null) return '--'
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}pp`
})
const ivrTone = computed(() => {
  const v = ivCur.value?.ivr
  if (v == null) return ''
  return v >= 70 ? 'high' : v <= 30 ? 'low' : 'mid'
})
const fmtIv = v => (v == null ? '--' : Number(v).toFixed(1))
async function loadIv() {
  try {
    const res = await fetch('/api/ivstats', { headers: { Accept: 'application/json' } })
    if (!res.ok) return
    const payload = await res.json()
    ivAll.value = payload?.targets || []
  } catch {
    ivAll.value = []
  }
}
let abortController = null
// 记住用户选择的标的（到期日依赖快照有效性，不在恢复时强制保留）
const firstTargetWrite = { value: true }
watch(target, () => {
  if (firstTargetWrite.value) { firstTargetWrite.value = false; return }
  writeState('volatility', { target: target.value })
})

// 到期日切换时即时重算选中组，避免旧序列残留
const selected = computed(() => {
  if (!model.value?.groups?.length) return null
  if (expiry.value) {
    const found = model.value.groups.find(g => g.expiry === expiry.value)
    if (!found) return null
    return found
  }
  return model.value.groups[0]
})
const selectedRows = computed(() => selected.value?.rows || [])
const smileChart = computed(() => selected.value ? plotSeries(selected.value.series, { minGap: 46 }) : { ticks: [], yTicks: [], series: [] })
const termChart = computed(() => model.value ? plotSeries(model.value.termSeries, { minGap: 46 }) : { ticks: [], yTicks: [], series: [] })
const expiries = computed(() => model.value?.expiries || [])
// 3D 曲面的标的参考价：优先取各组 ATM 的现价，退而求其次扫行内 spot
const surfaceSpot = computed(() => {
  const gs = model.value?.groups || []
  for (const g of gs) {
    const p = Number(g.atm?.spot?.price)
    if (Number.isFinite(p) && p > 0) return p
  }
  for (const g of gs) for (const r of g.rows || []) {
    const p = Number(r.spot?.price)
    if (Number.isFinite(p) && p > 0) return p
  }
  return null
})
// 跨期 IV 对比表：每个到期日一行，列出 ATM call / ATM put 的 IV 与差值。
// 数据来自 buildVolatility 已算好的 groups[].atm，不引入新的数据来源。
const termComparison = computed(() => {
  if (!model.value?.groups?.length) return []
  return model.value.groups.map(g => {
    const call = g.atm?.call, put = g.atm?.put
    const callIv = call?.status === 'available' ? call.ivValue : null
    const putIv = put?.status === 'available' ? put.ivValue : null
    const diff = callIv != null && putIv != null ? callIv - putIv : null
    return {
      expiry: g.expiry,
      strike: g.atm?.strike,
      callStatus: call?.status || 'unavailable',
      putStatus: put?.status || 'unavailable',
      callIv, putIv, diff,
      callCodes: call?.codes || [],
      putCodes: put?.codes || [],
      spot: g.atm?.spot,
      spotStatus: g.atm?.spotStatus,
    }
  })
})

// 到期日友好显示：20260923 → 2026-09-23
function fmtExpiry(e) {
  const m = String(e).match(/^(\d{4})(\d{2})(\d{2})$/)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : e
}

function cleanup() {
  if (abortController) { abortController.abort(); abortController = null }
  loading.value = false
}

async function load() {
  cleanup()
  const ctrl = new AbortController()
  abortController = ctrl
  loading.value = true
  error.value = ''
  data.value = null
  model.value = { coverage: { total: 0 } }
  staleFlag.value = false
  const sig = ctrl.signal
  const code = target.value
  try {
    const qs = new URLSearchParams()
    if (expiry.value) qs.set('expiry', expiry.value)
    const res = await fetch(`/api/quotes/${code}?${qs.toString()}`, { signal: sig, headers: { Accept: 'application/json' } })
    if (sig.aborted) return
    if (!res.ok) {
      let detail = ''
      try { detail = (await res.json())?.detail || '' } catch {}
      throw new Error(detail || `HTTP ${res.status}`)
    }
    const payload = await res.json()
    if (sig.aborted) return
    if (!payload || !Array.isArray(payload.rows)) throw new Error('响应格式无效')
    const built = buildVolatility(payload)
    data.value = payload
    model.value = built
    staleFlag.value = built.coverage.stale > 0
    if (!built.expiries.includes(expiry.value)) expiry.value = ''
    return
  } catch (e) {
    if (sig.aborted || e.name === 'AbortError') return
    error.value = e.message || '加载失败'
    data.value = null
    model.value = { coverage: { total: 0 } }
    staleFlag.value = false
  } finally {
    if (!sig.aborted) loading.value = false
  }
}

function changeTarget() {
  expiry.value = ''
  staleFlag.value = false
  error.value = ''
  load()
}

onMounted(() => { load(); loadIv() })
onUnmounted(cleanup)

function formatTs(ts) {
  return ts ? String(ts) : '—'
}
function statusLabel(status) {
  if (status === 'stale') return '过期'
  if (status === 'unavailable') return '不可用'
  if (status === 'partial') return '部分可用'
  if (status === 'ok') return '正常'
  return '未知'
}
</script>

<style scoped>
.volatility-page { display: grid; gap: 16px; }
.model-badge { color: var(--warn); border: 1px solid var(--warn); border-radius: 20px; padding: 4px 10px; font-size: 12px; }
.note { color: var(--text-dim); font-size: 12px; line-height: 1.7; }
.controls { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-dim); min-width: 180px; }
.field select { background: var(--bg-panel); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 8px; font-size: 14px; }
.refresh-btn { background: var(--accent); color: var(--bg); border: none; border-radius: 6px; padding: 9px 16px; font-size: 14px; cursor: pointer; }
.refresh-btn:disabled { opacity: .5; cursor: not-allowed; }
.error { color: var(--err); border: 1px solid var(--err); border-radius: 8px; padding: 12px; }
.empty { color: var(--text-dim); padding: 24px; text-align: center; }
.meta-bar { display: flex; gap: 16px; flex-wrap: wrap; border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; background: var(--bg-panel); font-size: 12px; color: var(--text-dim); }
.warn { color: var(--warn); }
.ts-note { color: var(--text-muted); font-weight: 500; }
.charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.chart-card, .table-card { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; background: var(--bg); box-shadow: var(--shadow); }
.chart-card h2, .table-card h2 { font-size: 15px; margin-bottom: 8px; }
svg { display: block; width: 100%; height: auto; }
.grid-line { stroke: var(--border); stroke-width: 1; }
.smile-call, .term-call { fill: none; stroke: var(--accent); stroke-width: 2; }
.smile-put, .term-put { fill: none; stroke: var(--warn); stroke-width: 2; stroke-dasharray: 4 4; }
.pt-fresh { fill: var(--text); }
.pt-stale { fill: var(--warn); }
.pt-unavailable { fill: var(--text-dim); opacity: .4; }
.chart-empty { fill: var(--text-dim); font-size: 12px; }
.axis-label { font-size: 11px; font-variant-numeric: tabular-nums; }
.iv-note ul { margin: 8px 0 0 20px; font-size: 13px; line-height: 1.75; color: var(--text-dim); }
.iv-note li + li { margin-top: 6px; }
.iv-note strong { color: var(--text); font-weight: 600; }
.table-wrap { overflow-x: auto; margin-top: 12px; }
/* 原始明细：默认折叠，只在需要核对原始报价时展开，避免长表格顶掉整屏 */
.table-card.raw-card { padding: 0; }
/* ---------- IV 水位 ---------- */
.iv-level { margin-bottom: 18px; }
.lv-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.lv-head h2 { font-size: 15px; margin: 0; }
.lv-sub { margin-left: 8px; font-size: 11px; font-weight: 400; color: var(--text-dim); }
.lv-date { font-size: 12px; color: var(--text-dim); font-family: var(--font-mono); }
.lv-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid var(--border); }
.lv-cell { padding: 14px 14px 2px 0; display: flex; flex-direction: column; gap: 5px; }
.lv-cell + .lv-cell { padding-left: 14px; border-left: 1px solid var(--border); }
.lv-k { font-size: 11px; letter-spacing: .06em; color: var(--text-dim); }
.lv-v { font-size: 26px; font-weight: 700; line-height: 1.1; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.lv-v i { font-style: normal; font-size: 13px; font-weight: 400; color: var(--text-dim); margin-left: 2px; }
.lv-v.pos { color: var(--warn); }
.lv-v.neg { color: var(--accent); }
.lv-h { font-size: 11px; color: var(--text-dim); line-height: 1.5; }
.lv-gauge-row { grid-column: 1 / -1; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
.gauge-top { display: flex; align-items: baseline; gap: 10px; }
.gauge-val { font-size: 20px; font-weight: 700; font-family: var(--font-mono); }
.gauge-val i { font-style: normal; font-size: 12px; font-weight: 400; color: var(--text-dim); }
.gauge-val.high { color: var(--warn); }
.gauge-val.low { color: var(--accent); }
.gauge-pct { font-size: 12px; color: var(--text-dim); margin-left: auto; font-family: var(--font-mono); }
.gauge-track { position: relative; height: 6px; border-radius: 3px; background: var(--border); }
.gauge-fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; background: var(--text-dim); opacity: .35; }
.gauge-fill.high { background: var(--warn); opacity: .5; }
.gauge-fill.low { background: var(--accent); opacity: .45; }
.gauge-dot { position: absolute; top: 50%; width: 12px; height: 12px; margin-left: -6px; border-radius: 50%; transform: translateY(-50%); background: var(--text-dim); border: 2px solid var(--bg); box-sizing: border-box; }
.gauge-dot.high { background: var(--warn); }
.gauge-dot.low { background: var(--accent); }
.gauge-ticks { display: flex; justify-content: space-between; margin-top: 6px; font-size: 11px; color: var(--text-dim); }
.warm { display: flex; align-items: center; gap: 10px; max-width: 480px; }
.warm-track { flex: 1; max-width: 320px; height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }
.warm-track span { display: block; height: 100%; background: var(--accent); opacity: .75; }
.warm-txt { font-size: 11px; color: var(--text-dim); white-space: nowrap; }
.raw-head { display: flex; align-items: center; gap: 10px; padding: 14px 18px; cursor: pointer; list-style: none; user-select: none; }
.raw-head::-webkit-details-marker { display: none; }
.raw-head:hover { background: var(--bg-panel); }
.raw-head h2 { font-size: 15px; margin: 0; }
.raw-meta { font-size: 12px; color: var(--text-dim); font-weight: 400; }
.raw-close-txt { display: none; }
.raw-card[open] .raw-open-txt { display: none; }
.raw-card[open] .raw-close-txt { display: inline; }
.raw-head::after { content: ''; margin-left: auto; width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid var(--text-dim); transition: transform .18s; }
.raw-card[open] .raw-head::after { transform: rotate(180deg); }
.raw-card[open] .raw-head { border-bottom: 1px solid var(--border); }
.raw-card .note { padding: 12px 18px 0; }
.raw-card .table-wrap { margin: 10px 18px 16px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 9px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
thead th { font-size: 12px; color: var(--text-dim); }
a { color: var(--accent); text-decoration: underline; }
/* 跨期 IV 对比表 */
.term-table td small { display: block; opacity: .6; font-size: 11px; margin-top: 4px; }
.term-table td.dim { opacity: .5; }
.term-table td.status-cell { text-align: left; display: flex; gap: 8px; flex-wrap: wrap; }
.tag-ok, .tag-fresh { color: var(--ok, #2e7d32); }
.tag-stale, .tag-unknown { color: var(--warn); }
.tag-unavailable, .tag-ambiguous { color: var(--err); opacity: .85; }
@media (max-width: 1000px) { .charts { grid-template-columns: 1fr; } }
@media (max-width: 640px) {
  .volatility-page { min-width: 0; }
  .volatility-page > * { min-width: 0; }
  .controls { flex-direction: column; align-items: stretch; gap: 10px; }
  .field { min-width: 0; }
  .refresh-btn { width: 100%; }
  .volatility-page h1 { font-size: 20px; }
  .meta-bar { font-size: 11px; padding: 8px 10px; gap: 8px; }
  .table-wrap th, .table-wrap td { padding: 8px 8px; font-size: 12px; }
  .chart-card, .table-card { padding: 14px; }
  .lv-sub { display: none; }
  .lv-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .lv-cell { padding: 10px 8px 2px 0; }
  .lv-cell + .lv-cell { padding-left: 8px; border-left: 1px solid var(--border); border-top: 0; padding-top: 10px; }
  .lv-k { font-size: 10px; }
  .lv-v { font-size: 19px; }
  .lv-h { font-size: 10px; }
  .gauge-pct { display: none; }
  .warm-txt { white-space: normal; }
}
</style>
