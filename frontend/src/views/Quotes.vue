<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'

const router = useRouter()

const state = ref(null)
const targets = ref([])
const loading = ref(true)
const lastRefresh = ref('')

const searchQuery = ref('')
const targetFilter = ref('all')
const typeFilter = ref('all')
const expiryFilter = ref('all')
const quickView = ref('none')
const sortField = ref('option_code')
const sortOrder = ref('asc')
const currentPage = ref(1)
const pageSize = 30

const quickViews = [
  { label: '当月ATM', value: 'atm_near' },
  { label: '当月全部', value: 'near_month' },
  { label: '次月ATM', value: 'atm_next' },
  { label: '虚值认购', value: 'otm_calls' },
  { label: '虚值认沽', value: 'otm_puts' },
  { label: '清除', value: 'none' },
]

const fetchState = async () => {
  try {
    const res = await fetch('/api/state')
    state.value = await res.json()
    lastRefresh.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (e) {
    console.error('Failed to fetch state:', e)
  }
}

const fetchTargets = async () => {
  try {
    const res = await fetch('/api/targets')
    targets.value = (await res.json()).targets || []
  } catch (e) {
    console.error('Failed to fetch targets:', e)
  }
}

onMounted(() => {
  fetchState()
  fetchTargets()
})

const refreshInterval = setInterval(() => {
  fetchState()
  fetchTargets()
}, 30000)

onUnmounted(() => clearInterval(refreshInterval))

// Flatten all contracts into a single array
const allContracts = computed(() => {
  const contracts = []
  for (const t of targets.value) {
    for (const c of (t.contracts || [])) {
      contracts.push({ ...t, ...c })
    }
  }
  return contracts
})

// Available expiry dates
const availableExpiries = computed(() => {
  const set = new Set()
  for (const c of allContracts.value) {
    if (c.expiry_date) set.add(c.expiry_date)
  }
  return Array.from(set).sort()
})

// Filtered + searched contracts
const filteredContracts = computed(() => {
  let result = allContracts.value

  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(c =>
      String(c.option_code).includes(q) ||
      (c.option_name || '').toLowerCase().includes(q)
    )
  }

  if (targetFilter.value !== 'all') {
    result = result.filter(c => c.target === targetFilter.value)
  }

  if (typeFilter.value !== 'all') {
    result = result.filter(c => c.option_type === typeFilter.value)
  }

  if (expiryFilter.value !== 'all') {
    result = result.filter(c => c.expiry_date === expiryFilter.value)
  }

  // Quick view filters
  if (quickView.value && quickView.value !== 'none') {
    const now = new Date()
    const nearMonth = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}`
    const nextMonthDate = new Date(now.getFullYear(), now.getMonth() + 1, 1)
    const nextMonth = `${nextMonthDate.getFullYear()}${String(nextMonthDate.getMonth() + 1).padStart(2, '0')}`

    if (quickView.value === 'near_month') {
      result = result.filter(c => c.expiry_date && c.expiry_date.startsWith(nearMonth))
    } else if (quickView.value === 'atm_near' || quickView.value === 'atm_next') {
      const prefix = quickView.value === 'atm_near' ? nearMonth : nextMonth
      result = result.filter(c => c.expiry_date && c.expiry_date.startsWith(prefix))
      // Keep only ATM ± 3 strikes
      if (result.length > 0) {
        const spotPrices = [...new Set(result.map(c => c.target_price))]
        if (spotPrices.length > 0) {
          const spot = spotPrices[0]
          const strikes = [...new Set(result.map(c => c.strike_price))].sort((a, b) => a - b)
          const atmIdx = strikes.reduce((best, s, i) =>
            Math.abs(s - spot) < Math.abs(strikes[best] - spot) ? i : best, 0)
          const minIdx = Math.max(0, atmIdx - 3)
          const maxIdx = Math.min(strikes.length - 1, atmIdx + 3)
          const allowed = new Set(strikes.slice(minIdx, maxIdx + 1))
          result = result.filter(c => allowed.has(c.strike_price))
        }
      }
    } else if (quickView.value === 'otm_calls') {
      result = result.filter(c => c.option_type === '认购' && c.strike_price > c.target_price)
    } else if (quickView.value === 'otm_puts') {
      result = result.filter(c => c.option_type === '认沽' && c.strike_price < c.target_price)
    }
  }

  // Sort
  result.sort((a, b) => {
    let aVal = a[sortField.value]
    let bVal = b[sortField.value]
    if (aVal == null) aVal = ''
    if (bVal == null) bVal = ''
    if (typeof aVal === 'string') aVal = aVal.toLowerCase()
    if (typeof bVal === 'string') bVal = bVal.toLowerCase()
    if (aVal < bVal) return sortOrder.value === 'asc' ? -1 : 1
    if (aVal > bVal) return sortOrder.value === 'asc' ? 1 : -1
    return 0
  })

  return result
})

// Paginated
const pagedContracts = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredContracts.value.slice(start, start + pageSize)
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredContracts.value.length / pageSize)))

function handleSort(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'asc'
  }
}

const changeClass = (v) => {
  if (v == null) return 'val-neu'
  return v >= 0 ? 'val-up' : 'val-down'
}

const getTagClass = (type) => type === '认购' ? 'tag-call' : 'tag-put'

const totalContracts = computed(() => filteredContracts.value.length)

// ── Methods (migrated from options API) ──
function applyQuickView(value) {
  quickView.value = quickView.value === value ? 'none' : value
  if (quickView.value === 'none') {
    expiryFilter.value = 'all'
    typeFilter.value = 'all'
  }
  currentPage.value = 1
}

function formatVolume(v) {
  if (v == null) return '--'
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return v.toLocaleString()
}

function formatExpiry(expiryStr) {
  if (!expiryStr || expiryStr.length < 8) return expiryStr
  const m = parseInt(expiryStr.slice(4, 6))
  const d = parseInt(expiryStr.slice(6, 8))
  return `${m}月${d}日`
}

// ── Pagination computed (migrated from options API) ──
const visiblePages = computed(() => {
  const total = totalPages.value
  const current = currentPage.value
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages = []
  const start = Math.max(1, current - 2)
  const end = Math.min(total, current + 2)
  if (start > 1) { pages.push(1); if (start > 2) pages.push('...') }
  for (let i = start; i <= end; i++) pages.push(i)
  if (end < total) { if (end < total - 1) pages.push('...'); pages.push(total) }
  return pages
})

// Reset to page 1 when filters change
onMounted(() => {
  watch([searchQuery, targetFilter, typeFilter, expiryFilter], () => {
    currentPage.value = 1
  })
})
</script>

<template>
  <div class="page-quotes">
    <div class="page-header">
      <h2 class="page-title">全量合约行情</h2>
      <div class="page-meta">
        <span class="meta-count">{{ totalContracts }} 条合约</span>
        <span class="meta-sep">·</span>
        <span class="meta-time">最后更新 {{ lastRefresh || '--' }}</span>
        <el-button :link="true" @click="fetchState" class="refresh-btn">
          <el-icon><Refresh /></el-icon>
          <span>刷新</span>
        </el-button>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <div class="filter-row">
        <el-input
          v-model="searchQuery"
          placeholder="搜索合约代码或名称"
          clearable
          :clearable="true"
          class="filter-search"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-select
          v-model="targetFilter"
          placeholder="全部标的"
          clearable
          :clearable="true"
          class="filter-target"
        >
          <el-option label="全部标的" value="all" />
          <el-option
            v-for="t in targets"
            :key="t.target"
            :label="`${t.target} ${t.target_name}`"
            :value="t.target"
          />
        </el-select>

        <el-radio-group v-model="typeFilter" class="filter-type">
          <el-radio-button :value="'all'">全部</el-radio-button>
          <el-radio-button :value="'认购'">认购</el-radio-button>
          <el-radio-button :value="'认沽'">认沽</el-radio-button>
        </el-radio-group>

        <el-select
          v-model="expiryFilter"
          placeholder="全部到期日"
          clearable
          :clearable="true"
          class="filter-expiry"
        >
          <el-option label="全部到期日" value="all" />
          <el-option
            v-for="exp in availableExpiries"
            :key="exp"
            :label="formatExpiry(exp)"
            :value="exp"
          />
        </el-select>

        <!-- 快捷视图 -->
        <div class="filter-quick">
          <button
            v-for="qv in quickViews"
            :key="qv.value"
            :class="['quick-btn', { active: quickView === qv.value }]"
            @click="applyQuickView(qv.value)"
          >
            {{ qv.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="table-wrapper">
      <table class="contract-table">
        <thead>
          <tr>
            <th @click="handleSort('option_code')" class="sortable" :class="{ active: sortField === 'option_code' }">
              合约代码 <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th>合约名称</th>
            <th @click="handleSort('target')" class="sortable" :class="{ active: sortField === 'target' }">
              标的 <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('expiry_date')" class="sortable" :class="{ active: sortField === 'expiry_date' }">
              到期日 <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('strike_price')" class="sortable numeric" :class="{ active: sortField === 'strike_price' }">
              行权价 <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('last_price')" class="sortable numeric" :class="{ active: sortField === 'last_price' }">
              最新价 <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('change_pct')" class="sortable numeric" :class="{ active: sortField === 'change_pct' }">
              涨跌幅 <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('delta')" class="sortable numeric" :class="{ active: sortField === 'delta' }">
              DELTA <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('gamma')" class="sortable numeric" :class="{ active: sortField === 'gamma' }">
              GAMMA <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('theta')" class="sortable numeric" :class="{ active: sortField === 'theta' }">
              THETA <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('vega')" class="sortable numeric" :class="{ active: sortField === 'vega' }">
              VEGA <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th @click="handleSort('implied_volatility')" class="sortable numeric" :class="{ active: sortField === 'implied_volatility' }">
              IV <span class="sort-arrow">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th>类型</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in pagedContracts"
            :key="c.option_code"
            class="contract-row"
            :class="c.option_type === '认购' ? 'row-call' : 'row-put'"
            @click="router.push(`/contract/${c.option_code}`)"
          >
            <td class="cell-code">{{ c.option_code }}</td>
            <td class="cell-name">{{ c.option_name }}</td>
            <td>
              <span class="cell-target" @click.stop="router.push('/quotes')">
                {{ c.target }}
              </span>
            </td>
            <td class="cell-mono">{{ c.expiry_date ? formatExpiry(c.expiry_date) : '--' }}</td>
            <td class="cell-mono">{{ c.strike_price != null ? Number(c.strike_price).toFixed(3) : '--' }}</td>
            <td class="cell-mono cell-price">{{ c.last_price != null ? Number(c.last_price).toFixed(4) : '--' }}</td>
            <td class="cell-mono" :class="changeClass(c.change_pct)">
              {{ c.change_pct != null ? (c.change_pct >= 0 ? '+' : '') + Number(c.change_pct).toFixed(2) + '%' : '--' }}
            </td>
            <td class="cell-mono">{{ c.delta != null ? Number(c.delta).toFixed(4) : '--' }}</td>
            <td class="cell-mono">{{ c.gamma != null ? Number(c.gamma).toFixed(4) : '--' }}</td>
            <td class="cell-mono">{{ c.theta != null ? Number(c.theta).toFixed(4) : '--' }}</td>
            <td class="cell-mono">{{ c.vega != null ? Number(c.vega).toFixed(4) : '--' }}</td>
            <td class="cell-mono">{{ c.implied_volatility != null ? (Number(c.implied_volatility) * 100).toFixed(1) + '%' : '--' }}</td>
            <td>
              <span class="cell-tag" :class="getTagClass(c.option_type)">{{ c.option_type }}</span>
            </td>
            <td>
              <span class="cell-action" @click.stop="router.push(`/contract/${c.option_code}`)">详情 →</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="pagedContracts.length === 0" class="empty-state">
        <p>暂无数据</p>
      </div>
    </div>

    <!-- Pagination -->
    <div class="pagination-bar" v-if="totalPages > 1">
      <div class="pagination-info">
        第 {{ currentPage }} / {{ totalPages }} 页，共 {{ totalContracts }} 条
      </div>
      <div class="pagination-btns">
        <button
          class="page-btn"
          :disabled="currentPage <= 1"
          @click="currentPage--"
        >
          ‹
        </button>
        <button
          v-for="pg in visiblePages"
          :key="pg"
          class="page-btn"
          :class="{ active: pg === currentPage }"
          @click="currentPage = pg"
        >
          {{ pg }}
        </button>
        <button
          class="page-btn"
          :disabled="currentPage >= totalPages"
          @click="currentPage++"
        >
          ›
        </button>
      </div>
    </div>
  </div>
</template>



<style scoped>
.page-quotes {
  animation: fadeIn 0.3s ease;
}

/* -- Page Header -- */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}
.page-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}
.meta-sep {
  color: var(--text-muted);
}
.refresh-btn {
  color: var(--text-secondary) !important;
  padding: 4px 8px !important;
}
.refresh-btn:hover {
  color: var(--accent) !important;
}

/* -- Filter Bar -- */
.filter-bar {
  margin-bottom: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-search {
  flex: 1;
  min-width: 200px;
}
.filter-target {
  width: 180px;
}
.filter-expiry {
  width: 150px;
}
.filter-type {
  display: flex;
}

.filter-quick {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.quick-btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.quick-btn:hover {
  color: var(--text-primary);
  border-color: var(--accent-dim);
}

.quick-btn.active {
  background: var(--accent);
  color: var(--bg-deep);
  border-color: var(--accent);
}

/* -- Custom Table -- */
.table-wrapper {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.contract-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.contract-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
}
.contract-table th {
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 11px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 12px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
  white-space: nowrap;
}
.contract-table th.numeric {
  text-align: right;
}
.contract-table th.sortable {
  cursor: pointer;
  user-select: none;
  transition: color 0.15s;
}
.contract-table th.sortable:hover {
  color: var(--text-primary);
}
.contract-table th.sortable.active {
  color: var(--accent);
}
.sort-arrow {
  font-size: 10px;
  margin-left: 2px;
  opacity: 0.5;
}
.sort-arrow:hover {
  opacity: 1;
}

.contract-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
}
.contract-table tbody tr {
  transition: background 0.1s;
}
.contract-table tbody tr.row-call {
  border-left: 2px solid var(--up, rgba(232,136,62,0.5));
}
.contract-table tbody tr.row-put {
  border-left: 2px solid var(--down, rgba(60,196,160,0.5));
}
.contract-table tbody tr:hover {
  background: var(--bg-row-hover);
}
.contract-table tbody tr:last-child td {
  border-bottom: none;
}

/* Cell styles */
.cell-code {
  font-family: var(--font-mono);
  color: var(--accent);
  font-weight: 600;
  font-size: 12px;
}
.cell-name {
  font-size: 13px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cell-target {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}
.cell-target:hover {
  color: var(--accent);
}
.cell-mono {
  font-family: var(--font-mono);
  font-size: 12px;
}
.cell-price {
  font-weight: 600;
  text-align: right;
}
.cell-volume {
  text-align: right;
  color: var(--text-secondary);
}
.cell-tag {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.tag-call {
  background: var(--tag-认购-bg);
  color: var(--tag-认购-text);
}
.tag-put {
  background: var(--tag-认沽-bg);
  color: var(--tag-认沽-text);
}
.cell-action {
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
  transition: color 0.15s;
}
.cell-action:hover {
  color: var(--accent);
}

/* Empty state */
.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}

/* -- Pagination -- */
.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  padding: 0 4px;
}
.pagination-info {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.pagination-btns {
  display: flex;
  gap: 4px;
}
.page-btn {
  min-width: 32px;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.page-btn:hover:not(:disabled):not(.active) {
  background: var(--bg-row-hover);
  color: var(--text-primary);
  border-color: var(--border-light);
}
.page-btn.active {
  background: var(--accent);
  color: var(--bg-deep);
  border-color: var(--accent);
  font-weight: 700;
}
.page-btn:disabled {
  opacity: 0.3;
  cursor: default;
}

@media (max-width: 1100px) {
  .contract-table {
    font-size: 12px;
  }
  .filter-row {
    flex-direction: column;
    align-items: stretch;
  }
  .filter-search, .filter-target {
    min-width: auto;
  }
}
</style>
