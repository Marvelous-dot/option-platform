<template>
  <section class="quotes-page">
    <div class="page-head">
      <div class="ph-title">
        <span class="ph-kicker">ALL CONTRACTS · 筛选 / 排序 / 导出</span>
        <h1>全量行情</h1>
        <p class="ph-desc">按标的查看全部挂牌到期合约，点表头排序、点合约进详情。IV / Greeks 为数据源计算值，口径未核验；报价可用不等于实时。</p>
      </div>
      <div class="ph-actions">
        <button type="button" class="export" @click="exportCsv" :disabled="loading || !data?.rows?.length">导出 CSV</button>
      </div>
    </div>

    <form class="filters filter-card" @submit.prevent="load">
      <label>标的<select v-model="target" @change="changeTarget"><option v-for="t in targets" :key="t.target" :value="t.target">{{ t.target }} {{ t.name }}</option></select></label>
      <label>到期日<select v-model="expiry"><option value="">全部到期日</option><option v-for="e in expiries" :key="e" :value="e">{{ e }}</option></select></label>
      <label>方向<select v-model="type"><option value="">全部</option><option value="call">认购</option><option value="put">认沽</option></select></label>
      <label>虚实值<select v-model="money"><option value="all">全部</option><option value="atm">ATM（最近行权价）</option><option value="otm">虚值</option></select></label>
      <label>搜索<input v-model="search" placeholder="合约代码 / 名称" /></label>
      <label>排序<select v-model="sort"><option v-for="[key, label] in sorts" :key="key" :value="key">{{ label }}</option></select></label>
      <label>顺序<select v-model="order"><option value="asc">升序</option><option value="desc">降序</option></select></label>
      <label>每页<select :value="pageSize" @change="changePageSize(Number($event.target.value))">
        <option :value="0">全部</option><option :value="50">50</option><option :value="100">100</option><option :value="200">200</option>
      </select></label>
      <button type="submit" :disabled="loading">{{ loading ? '加载中…' : '查询 / 刷新' }}</button>
    </form>

    <div class="toolbar">
      <span class="toolbar-label">快捷视图</span>
      <button type="button" @click="quick(0, 'atm')" :disabled="loading || !expiries.length">近月 ATM</button>
      <button type="button" @click="quick(1, 'atm')" :disabled="loading || expiries.length < 2">次近月 ATM</button>
      <button type="button" @click="quick(0, 'otm')" :disabled="loading || !expiries.length">近月虚值</button>
      <button type="button" @click="quick(1, 'otm')" :disabled="loading || expiries.length < 2">次近月虚值</button>
      <span class="toolbar-info" v-if="data">{{ status(data.data_status) }} · {{ data.status_detail }} · 查询范围 {{ data.contract_count }} 个挂牌合约</span>
    </div>

    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="data" class="ts-bar">
      <span class="ts-dot"></span>
      本批数据抓取于 {{ data.rows?.[0]?.fetched_at || '--' }} · 非实时快照，缺失字段显示"不可用" · 虚实值按各到期日快照的标的价格判断（可能非当日）
    </p>
    <div class="pager" v-if="pageSize > 0 && data?.rows?.length">
      <button type="button" :disabled="!hasPrev() || loading" @click="prevPage">上一页</button>
      <span class="pager-info">第 {{ page + 1 }} / {{ Math.max(1, Math.ceil(totalRows() / pageSize)) }} 页 · 共 {{ totalRows() }} 条</span>
      <button type="button" :disabled="!hasNext() || loading" @click="nextPage">下一页</button>
    </div>
    <div class="table-wrap" v-if="data?.rows.length">
      <table>
        <thead><tr>
          <th>合约</th><th>方向</th><th>到期日</th>
          <th class="sortable" :class="{ active: sort === 'strike', desc: sort === 'strike' && order === 'desc' }" @click="sortBy('strike')">行权价</th>
          <th class="sortable" :class="{ active: sort === 'last_price', desc: sort === 'last_price' && order === 'desc' }" @click="sortBy('last_price')">最新价</th>
          <th class="sortable" :class="{ active: sort === 'iv', desc: sort === 'iv' && order === 'desc' }" @click="sortBy('iv')">IV</th>
          <th class="sortable" :class="{ active: sort === 'delta', desc: sort === 'delta' && order === 'desc' }" @click="sortBy('delta')">Delta</th>
          <th class="sortable" :class="{ active: sort === 'gamma', desc: sort === 'gamma' && order === 'desc' }" @click="sortBy('gamma')">Gamma</th>
          <th class="sortable" :class="{ active: sort === 'theta', desc: sort === 'theta' && order === 'desc' }" @click="sortBy('theta')">Theta</th>
          <th class="sortable" :class="{ active: sort === 'vega', desc: sort === 'vega' && order === 'desc' }" @click="sortBy('vega')">Vega</th>
          <th class="sortable" :class="{ active: sort === 'volume', desc: sort === 'volume' && order === 'desc' }" @click="sortBy('volume')">成交量</th>
          <th>可用性 / 时效</th><th>来源 / 时间</th>
        </tr></thead>
        <tbody><tr v-for="r in data.rows" :key="r.option_code">
          <td><router-link :to="contractLink(r)">{{ r.name }}</router-link><small>{{ r.option_code }}</small></td>
          <td>{{ r.option_type === 'call' ? '认购' : '认沽' }}</td><td>{{ r.expiry }}</td>
          <td>{{ number(r.strike) }}</td><td>{{ number(r.last_price) }}</td><td>{{ number(r.iv, true) }}</td>
          <td v-for="key in ['delta', 'gamma', 'theta', 'vega']" :key="key">{{ number(r[key]) }}</td>
          <td>{{ r.volume ?? '--' }}</td><td>{{ status(r.data_status) }}<small>{{ freshness(r.freshness) }}</small></td>
          <td>{{ r.source || '--' }}<small>行情：{{ r.market_ts || '未知，不代表实时' }}</small><small>抓取：{{ r.fetched_at || '--' }}</small><small>标的：{{ number(r.spot?.price) }} · {{ r.spot?.source || '--' }} · {{ r.spot?.market_time || '源时间未知' }}</small></td>
        </tr></tbody>
      </table>
    </div>
    <p v-else-if="!loading && data">当前条件下没有合约。数据源缺失时不生成模拟行情。</p>
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { readState, writeState } from '../utils/remember.mjs'
const remembered = readState('quotes', {})
const targets = ref([]), expiries = ref([])
const target = ref(remembered.target || '510050')
const expiry = ref(remembered.expiry || ''), type = ref(remembered.type || ''), money = ref(remembered.money || 'all')
const search = ref(remembered.search || '')
const sort = ref(remembered.sort || 'option_code'), order = ref(remembered.order || 'asc')
const data = ref(null), loading = ref(false), error = ref('')
const pageSize = ref(remembered.pageSize || 50)  // 0 = 全部
const page = ref(0)       // 0-indexed
const sorts = [['option_code', '合约代码'], ['strike', '行权价'], ['last_price', '最新价'], ['iv', 'IV'], ['delta', 'Delta'], ['gamma', 'Gamma'], ['theta', 'Theta'], ['vega', 'Vega'], ['volume', '成交量']]
// Persist user-chosen filters (not the fetched data). Skip the first target change
// which is part of initial restore.
const firstTargetChange = { value: true }
watch([target, expiry, type, money, search, sort, order, pageSize], () => {
  if (firstTargetChange.value) { firstTargetChange.value = false; return }
  writeState('quotes', { target: target.value, expiry: expiry.value, type: type.value, money: money.value, search: search.value, sort: sort.value, order: order.value, pageSize: pageSize.value })
})
let controller, generation = 0
const contractLink = r => `/contract/${encodeURIComponent(r.option_code)}`
const number = (v, percent = false) => v == null || !Number.isFinite(Number(v)) ? '--' : percent ? (v * 100).toFixed(2) + '%' : Number(v).toFixed(4)
const status = s => ({ok: '报价可用', partial: '部分可用', stale: '过期快照', unavailable: '不可用'}[s] || '未知')
const freshness = s => ({fresh: '当日源时间', stale: '过期', unknown: '时效未知'}[s] || '时效未知')
const totalRows = () => data.value?.total ?? data.value?.rows?.length ?? 0
const currentPageCount = () => data.value?.rows?.length ?? 0
const hasPrev = () => page.value > 0
// A next page exists only when the current window is full AND more rows remain
// beyond it. An exactly-full last page correctly reports no next page.
const hasNext = () => pageSize.value > 0 && currentPageCount() === pageSize.value
  && (page.value + 1) * pageSize.value < totalRows()
async function load() {
  controller?.abort()
  controller = new AbortController()
  const request = ++generation
  const signal = controller.signal
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const params = new URLSearchParams({expiry: expiry.value, option_type: type.value, search: search.value, moneyness: money.value, sort: sort.value, order: order.value})
    if (pageSize.value > 0) {
      params.set('limit', String(pageSize.value))
      params.set('offset', String(page.value * pageSize.value))
    }
    const res = await fetch(`/api/quotes/${target.value}?${params}`, {signal})
    const result = await res.json()
    if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`)
    if (request !== generation) return
    data.value = result
    expiries.value = result.expiries || []
  } catch (e) {
    if (request === generation && e.name !== 'AbortError') error.value = `获取失败：${e.message}`
  } finally {
    if (request === generation) loading.value = false
  }
}
function changeTarget() {
  expiry.value = ''
  expiries.value = []
  page.value = 0
  load()
}
// Header click = set the sort column; clicking the active column toggles direction.
function sortBy(key) {
  if (sort.value === key) {
    order.value = order.value === 'asc' ? 'desc' : 'asc'
  } else {
    sort.value = key
    order.value = 'asc'
  }
  page.value = 0
  load()
}
function quick(index, value) {
  expiry.value = expiries.value[index]
  money.value = value
  search.value = ''
  type.value = ''
  page.value = 0
  load()
}
function changePageSize(n) {
  pageSize.value = n
  page.value = 0
  load()
}
// CSV 导出：拉当前筛选全量（不受分页 limit 约束），null 原样留空，带 BOM 供 Excel
const CSV_COLS = [
  ['合约代码', r => r.option_code], ['名称', r => r.name], ['标的代码', () => target.value],
  ['方向', r => r.option_type === 'call' ? '认购' : '认沽'], ['到期日', r => r.expiry],
  ['行权价', r => r.strike], ['最新价', r => r.last_price], ['IV', r => r.iv],
  ['Delta', r => r.delta], ['Gamma', r => r.gamma], ['Theta', r => r.theta], ['Vega', r => r.vega],
  ['成交量', r => r.volume], ['最高价', r => r.high], ['最低价', r => r.low],
  ['理论价', r => r.theory_price], ['可用性', r => r.data_status], ['时效', r => r.freshness],
  ['来源', r => r.source], ['行情时间', r => r.market_ts], ['抓取时间', r => r.fetched_at],
  ['标的价格', r => r.spot?.price ?? null], ['标的来源', r => r.spot?.source ?? ''],
]
function csvCell(v) {
  if (v == null) return ''
  const s = String(v)
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}
async function exportCsv() {
  const params = new URLSearchParams({expiry: expiry.value, option_type: type.value, search: search.value, moneyness: money.value, sort: sort.value, order: order.value})
  const res = await fetch(`/api/quotes/${target.value}?${params}`)
  const d = await res.json()
  if (!res.ok) throw new Error(d.detail || `HTTP ${res.status}`)
  const rows = d.rows || []
  const head = CSV_COLS.map(c => c[0]).join(',')
  const lines = rows.map(r => CSV_COLS.map(c => csvCell(c[1](r))).join(','))
  const csv = '\uFEFF' + [head, ...lines].join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `quotes_${target.value}_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a); a.click(); document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
function prevPage() {
  if (pageSize.value === 0 || page.value <= 0) return
  page.value -= 1
  load()
}
function nextPage() {
  if (pageSize.value === 0) return
  if (hasNext()) { page.value += 1; load() }
}
onMounted(async () => {
  try {
    const res = await fetch('/api/targets')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    targets.value = (await res.json()).targets || []
    if (!targets.value.length) throw new Error('标的目录为空')
    await load()
  } catch (e) { error.value = `标的目录获取失败：${e.message}` }
})
onUnmounted(() => { generation++; controller?.abort() })
</script>

<style scoped>
.filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; align-items: end; }
label { display: grid; gap: 7px; font-size: 12px; color: var(--text-dim); }
select, input, button { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 9px; font: inherit; }
select:focus, input:focus { outline: 2px solid var(--accent); outline-offset: 1px; border-color: transparent; }
button { cursor: pointer; font-weight: 600; }
.toolbar button { background: var(--bg); border: 1px solid var(--border); border-radius: var(--pill); padding: 7px 16px; font-size: 13px; color: var(--text); font-weight: 500; }
.toolbar button:hover:not(:disabled) { border-color: var(--accent); background: var(--accent-glow); }
.filters button[type=submit] { background: var(--accent); color: var(--accent-text); border: none; border-radius: var(--pill); padding: 9px 22px; font-weight: 700; }
.filters button[type=submit]:hover { background: var(--accent-hover); }
button:disabled { opacity: .5; cursor: wait; }
.export { background: transparent; color: var(--accent-ink); border: 1px solid var(--border); border-radius: var(--pill); padding: 8px 18px; font-weight: 700; }
.export:hover:not(:disabled) { border-color: var(--accent); background: var(--accent-glow); }
.pager { display: flex; align-items: center; gap: 14px; margin: 14px 0; font-size: 13px; }
.pager button { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: var(--pill); padding: 7px 18px; font-size: 13px; font-weight: 600; }
.pager button:hover:not(:disabled) { background: var(--bg-hover); }
.pager-info { color: var(--text-dim); font-variant-numeric: tabular-nums; }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: 13px; }
th { background: var(--bg-elevated); position: sticky; top: 0; }
th, td { padding: 12px 14px; white-space: nowrap; border-bottom: 1px solid var(--border); text-align: right; }
th { color: var(--text-dim); font-weight: 600; font-size: 12px; }
th.sortable { cursor: pointer; user-select: none; position: relative; }
th.sortable:hover { color: var(--text); background: var(--bg-hover); }
th.sortable::after { content: '↕'; margin-left: 6px; font-size: 12px; opacity: .55; }
th.sortable:hover::after { opacity: .9; color: var(--accent-ink); }
th.sortable.active { color: var(--accent-ink); }
th.sortable.active::after { content: '↑'; opacity: 1; color: var(--accent-ink); font-size: 13px; }
th.sortable.active.desc::after { content: '↓'; opacity: 1; color: var(--accent-ink); font-size: 13px; }
tbody tr:hover { background: var(--bg-hover); }
th:first-child, td:first-child, td:last-child { text-align: left; }
td small { display: block; opacity: .65; margin-top: 5px; font-size: 11px; }
a { color: var(--accent-ink); font-weight: 600; }
a:hover { text-decoration: underline; }
[role=alert] { color: var(--err); }
/* 窄屏：筛选表单单列堆叠、快捷按钮换行、表头不吸顶、表格字号缩小 */
@media (max-width: 768px) {
  .filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .toolbar { gap: 6px; }
  .toolbar button { flex: 1 1 calc(50% - 6px); text-align: center; padding: 8px 10px; font-size: 12px; }
  .toolbar-info { flex-basis: 100%; margin-left: 0; }
  .pager { flex-wrap: wrap; gap: 8px; justify-content: center; text-align: center; }
  th { position: static; }
  th, td { padding: 10px 10px; font-size: 12px; }
  td small { font-size: 10px; }
}
</style>
