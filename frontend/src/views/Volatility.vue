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

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!model && !loading" class="empty">加载中或暂无数据</p>

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
              <line :x1="40" :x2="620" :y1="tick.y" :y2="tick.y" class="grid-line" />
              <text x="36" :y="tick.y + 4" text-anchor="end">{{ formatIV(tick.value) }}</text>
            </g>
            <g v-for="series in smileChart.series" :key="series.side">
              <polyline v-for="seg in series.segments" :key="'seg' + seg" :points="seg"
                :class="series.side === 'call' ? 'smile-call' : 'smile-put'" />
              <g v-for="p in series.points" :key="p.option_code">
                <circle :cx="p.x" :cy="p.y" r="3" :class="`pt-${p.ivStatus || 'unavailable'}`" />
              </g>
            </g>
            <text x="620" y="272" text-anchor="end">行权价</text>
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
              <line :x1="40" :x2="620" :y1="tick.y" :y2="tick.y" class="grid-line" />
              <text x="36" :y="tick.y + 4" text-anchor="end">{{ formatIV(tick.value) }}</text>
            </g>
            <g v-for="series in termChart.series" :key="series.side">
              <polyline v-for="seg in series.segments" :key="'seg' + seg" :points="seg"
                :class="series.side === 'call' ? 'term-call' : 'term-put'" />
              <g v-for="(p, i) in series.points" :key="i">
                <circle :cx="p.x" :cy="p.y" r="3" :class="`pt-${p.ivStatus || 'unavailable'}`" />
              </g>
            </g>
            <text x="620" y="272" text-anchor="end">到期日</text>
            <text x="40" y="18">IV（%）</text>
          </svg>
        </div>
      </div>

      <div class="table-card">
        <h2>原始明细</h2>
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
    </template>

    <div class="unavailable">
      <h2>暂未接入的能力</h2>
      <ul>
        <li><strong>历史 IV 曲线</strong>：需要数据库历史 IV 表，暂不可用。</li>
        <li><strong>历史IV与K线叠加</strong>：需历史 IV 与日 K 对齐，暂不可用。</li>
        <li><strong>3D 波动率曲面</strong>：需多到期日、多行权价三维数据，暂不可用。</li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { buildVolatility, plotSeries, formatIV } from '../utils/volatility.mjs'
import { readState, writeState } from '../utils/remember.mjs'

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

onMounted(load)
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
.chart-card, .table-card, .unavailable { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; background: var(--bg); box-shadow: var(--shadow); }
.chart-card h2, .table-card h2, .unavailable h2 { font-size: 15px; margin-bottom: 8px; }
svg { display: block; width: 100%; height: auto; }
.grid-line { stroke: var(--border); stroke-width: 1; }
.smile-call, .term-call { fill: none; stroke: var(--accent); stroke-width: 2; }
.smile-put, .term-put { fill: none; stroke: var(--warn); stroke-width: 2; stroke-dasharray: 4 4; }
.pt-fresh { fill: var(--text); }
.pt-stale { fill: var(--warn); }
.pt-unavailable { fill: var(--text-dim); opacity: .4; }
.unavailable ul { margin: 8px 0 0 20px; font-size: 13px; color: var(--text-dim); }
.table-wrap { overflow-x: auto; margin-top: 12px; }
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
}
</style>
