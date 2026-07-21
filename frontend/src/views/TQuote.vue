<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// ── State ──
const targets = ref([])
const selectedTarget = ref('510050')
const selectedExpiry = ref('all')
const tquoteData = ref(null)
const loading = ref(false)
const spotPrice = ref(0)
const refreshTimer = ref(null)

// ── Fetch targets for the selector ──
const fetchTargets = async () => {
  try {
    const res = await fetch('/api/targets')
    const data = await res.json()
    targets.value = data.targets || []
  } catch (e) {
    console.error('fetchTargets:', e)
  }
}

// ── Fetch T-quote data ──
const fetchTQuote = async () => {
  loading.value = true
  try {
    const params = selectedExpiry.value !== 'all' ? `?expiry=${selectedExpiry.value}` : ''
    const url = `/api/tquote/${selectedTarget.value}${params}`
    const res = await fetch(url)
    const data = await res.json()
    tquoteData.value = data
    spotPrice.value = data.spot_price || 0

    // Auto-select first expiry if none selected
    if (data.expiries) {
      const keys = Object.keys(data.expiries)
      if (keys.length && selectedExpiry.value === 'all') {
        // default: keep 'all' but populate expiry list
      }
    }
  } catch (e) {
    console.error('fetchTQuote:', e)
  } finally {
    loading.value = false
  }
}

// ── Computed ──
const expiryKeys = computed(() => {
  if (!tquoteData.value?.expiries) return []
  return Object.keys(tquoteData.value.expiries).sort()
})

// Flatten all rows across all selected expiries
const tableRows = computed(() => {
  if (!tquoteData.value?.expiries) return []

  if (selectedExpiry.value === 'all') {
    // Merge all expiries: group by strike, show each expiry as a sub-row
    const byStrike = {}
    for (const [exp, expData] of Object.entries(tquoteData.value.expiries)) {
      for (const row of expData.rows) {
        const strike = row.strike
        if (!byStrike[strike]) {
          byStrike[strike] = { strike, expiries: {} }
        }
        byStrike[strike].expiries[exp] = row
      }
    }
    return Object.values(byStrike).sort((a, b) => a.strike - b.strike)
  } else {
    const expData = tquoteData.value.expiries[selectedExpiry.value]
    return expData ? expData.rows : []
  }
})

const atmStrike = computed(() => {
  if (!spotPrice.value || !tableRows.value.length) return null
  let closest = null
  let minDist = Infinity
  for (const row of tableRows.value) {
    const dist = Math.abs(row.strike - spotPrice.value)
    if (dist < minDist) {
      minDist = dist
      closest = row.strike
    }
  }
  return closest
})

// ── Format helpers ──
function fmtPrice(v) {
  if (v == null) return '--'
  return Number(v).toFixed(4)
}
function fmtDelta(v) {
  if (v == null) return '--'
  return Number(v).toFixed(4)
}
function fmtGamma(v) {
  if (v == null) return '--'
  return Number(v).toFixed(4)
}
function fmtStrike(v) {
  return Number(v).toFixed(3)
}
function fmtSpot(v) {
  return Number(v).toFixed(3)
}
function expiryLabel(exp) {
  // 20260722 → 7月
  if (!exp || exp.length < 6) return exp
  const m = parseInt(exp.substring(4, 6))
  return `${m}月`
}
function contractName(c) {
  return c?.option_name || '--'
}
function changeClass(v) {
  if (v == null) return ''
  const n = Number(v)
  return n > 0 ? 'val-up' : n < 0 ? 'val-down' : ''
}

// ── Go to contract detail ──
function goContract(c) {
  if (!c?.option_code) return
  router.push(`/contract/${c.option_code}`)
}

// ── Lifecycle ──
watch(selectedTarget, () => { selectedExpiry.value = 'all'; fetchTQuote() })
watch(selectedExpiry, () => { fetchTQuote() })

onMounted(() => {
  fetchTargets()
  fetchTQuote()
  refreshTimer.value = setInterval(fetchTQuote, 30000)
})

onUnmounted(() => {
  if (refreshTimer.value) clearInterval(refreshTimer.value)
})
</script>

<template>
  <div class="page-tquote">
    <!-- Header -->
    <div class="tq-header">
      <div class="tq-header-left">
        <h2 class="page-title">T 型报价</h2>
        <span class="page-subtitle" v-if="tquoteData">
          {{ tquoteData.target_name }} · 现货 {{ fmtSpot(spotPrice) }}
          <span class="badge-dot" :class="loading ? 'loading' : 'live'"></span>
        </span>
      </div>

      <div class="tq-controls">
        <!-- Target selector -->
        <div class="target-tabs">
          <button
            v-for="t in targets"
            :key="t.target"
            class="target-tab"
            :class="{ active: selectedTarget === t.target }"
            @click="selectedTarget = t.target"
          >
            <span class="tab-code">{{ t.target }}</span>
            <span class="tab-name">{{ t.target_name?.slice(0, 6) }}</span>
          </button>
        </div>

        <!-- Expiry filter -->
        <div class="expiry-tabs" v-if="expiryKeys.length">
          <button
            class="expiry-tab"
            :class="{ active: selectedExpiry === 'all' }"
            @click="selectedExpiry = 'all'"
          >全部</button>
          <button
            v-for="exp in expiryKeys"
            :key="exp"
            class="expiry-tab"
            :class="{ active: selectedExpiry === exp }"
            @click="selectedExpiry = exp"
          >{{ expiryLabel(exp) }}</button>
        </div>
      </div>
    </div>

    <!-- T-Quote Table (桌面端) -->
    <div class="tq-table-wrap tq-desktop-table" v-if="tableRows.length">
      <!-- Column groups header -->
      <table class="tq-table">
        <thead>
          <tr>
            <th class="col-call" colspan="4">
              <span class="group-label call-label">认购 CALL</span>
            </th>
            <th class="col-strike">
              <span class="group-label strike-label">行权价</span>
            </th>
            <th class="col-put" colspan="4">
              <span class="group-label put-label">认沽 PUT</span>
            </th>
          </tr>
          <tr class="sub-header">
            <!-- Call sub-headers -->
            <th class="sub-th call-sub" @click="goContract(null)">最新价</th>
            <th class="sub-th call-sub">Delta</th>
            <th class="sub-th call-sub">Gamma</th>
            <th class="sub-th call-sub">名称</th>
            <!-- Strike -->
            <th class="sub-th strike-sub">行权价</th>
            <!-- Put sub-headers -->
            <th class="sub-th put-sub">名称</th>
            <th class="sub-th put-sub">Gamma</th>
            <th class="sub-th put-sub">Delta</th>
            <th class="sub-th put-sub">最新价</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in tableRows" :key="row.strike">
            <!-- When showing single expiry -->
            <tr
              v-if="selectedExpiry !== 'all'"
              class="tq-row"
              :class="{ atm: row.strike === atmStrike }"
            >
              <!-- Call side -->
              <td class="col-val call-val" :class="changeClass(row.call?.change_pct)">
                <span class="cell-link" @click.stop="goContract(row.call)">{{ fmtPrice(row.call?.last_price) }}</span>
              </td>
              <td class="col-val call-val val-mono">{{ fmtDelta(row.call?.delta) }}</td>
              <td class="col-val call-val val-mono">{{ fmtGamma(row.call?.gamma) }}</td>
              <td class="col-val call-val call-name">
                <span class="cell-link" @click.stop="goContract(row.call)">{{ contractName(row.call) }}</span>
              </td>

              <!-- Strike -->
              <td class="col-strike strike-cell" :class="{ 'atm-strike': row.strike === atmStrike }">
                <span class="strike-value">{{ fmtStrike(row.strike) }}</span>
                <span class="strike-tag" v-if="row.strike === atmStrike">ATM</span>
              </td>

              <!-- Put side -->
              <td class="col-val put-val put-name">
                <span class="cell-link" @click.stop="goContract(row.put)">{{ contractName(row.put) }}</span>
              </td>
              <td class="col-val put-val val-mono">{{ fmtGamma(row.put?.gamma) }}</td>
              <td class="col-val put-val val-mono">{{ fmtDelta(row.put?.delta) }}</td>
              <td class="col-val put-val" :class="changeClass(row.put?.change_pct)">
                <span class="cell-link" @click.stop="goContract(row.put)">{{ fmtPrice(row.put?.last_price) }}</span>
              </td>
            </tr>

            <!-- When showing all expiries: one row per strike, sub-rows per expiry -->
            <template v-else>
              <tr
                v-for="(expRow, expIdx) in Object.entries(row.expiries)"
                :key="`${row.strike}-${expIdx}`"
                class="tq-row"
                :class="{ atm: row.strike === atmStrike }"
              >
                <!-- Call -->
                <td class="col-val call-val" :class="changeClass(expRow[1].call?.change_pct)">
                  <span class="cell-link" v-if="expRow[1].call" @click.stop="goContract(expRow[1].call)">
                    {{ fmtPrice(expRow[1].call?.last_price) }}
                  </span>
                  <span v-else>--</span>
                </td>
                <td class="col-val call-val val-mono">{{ fmtDelta(expRow[1].call?.delta) }}</td>
                <td class="col-val call-val val-mono">{{ fmtGamma(expRow[1].call?.gamma) }}</td>
                <td class="col-val call-val call-name">
                  <span class="expiry-tag-mini">{{ expiryLabel(expRow[0]) }}</span>
                  <span class="cell-link" v-if="expRow[1].call" @click.stop="goContract(expRow[1].call)">
                    {{ contractName(expRow[1].call) }}
                  </span>
                </td>

                <!-- Strike (only on first sub-row) -->
                <td
                  v-if="expIdx === 0"
                  class="col-strike strike-cell"
                  :class="{ 'atm-strike': row.strike === atmStrike }"
                  :rowspan="Object.keys(row.expiries).length"
                >
                  <span class="strike-value">{{ fmtStrike(row.strike) }}</span>
                  <span class="strike-tag" v-if="row.strike === atmStrike">ATM</span>
                </td>

                <!-- Put -->
                <td class="col-val put-val put-name">
                  <span class="cell-link" v-if="expRow[1].put" @click.stop="goContract(expRow[1].put)">
                    {{ contractName(expRow[1].put) }}
                  </span>
                  <span v-else>--</span>
                </td>
                <td class="col-val put-val val-mono">{{ fmtGamma(expRow[1].put?.gamma) }}</td>
                <td class="col-val put-val val-mono">{{ fmtDelta(expRow[1].put?.delta) }}</td>
                <td class="col-val put-val" :class="changeClass(expRow[1].put?.change_pct)">
                  <span class="cell-link" v-if="expRow[1].put" @click.stop="goContract(expRow[1].put)">
                    {{ fmtPrice(expRow[1].put?.last_price) }}
                  </span>
                  <span v-else>--</span>
                </td>
              </tr>
            </template>
          </template>
        </tbody>
      </table>
    </div>

    <!-- 移动端卡片视图 -->
    <div class="tq-mobile-cards" v-if="tableRows.length">
      <div
        v-for="row in tableRows"
        :key="row.strike"
        class="tq-card"
        :class="{ atm: row.strike === atmStrike }"
      >
        <!-- 行权价 header -->
        <div class="tq-card-header">
          <span class="tq-card-strike">{{ fmtStrike(row.strike) }}</span>
          <span class="strike-tag" v-if="row.strike === atmStrike">ATM</span>
          <span class="tq-card-expiry" v-if="selectedExpiry !== 'all'">{{ expiryLabel(selectedExpiry) }}</span>
        </div>

        <!-- 认购/认沽 两行 -->
        <div class="tq-card-body">
          <!-- 认购 -->
          <div class="tq-card-side call-side" @click="goContract(row.call)">
            <div class="tq-card-side-label">认购</div>
            <div class="tq-card-fields">
              <span class="tq-card-field">
                <label>最新价</label>
                <b :class="changeClass(row.call?.change_pct)">{{ fmtPrice(row.call?.last_price) }}</b>
              </span>
              <span class="tq-card-field">
                <label>Delta</label>
                <b>{{ fmtDelta(row.call?.delta) }}</b>
              </span>
              <span class="tq-card-field">
                <label>Gamma</label>
                <b>{{ fmtGamma(row.call?.gamma) }}</b>
              </span>
            </div>
          </div>
          <!-- 认沽 -->
          <div class="tq-card-side put-side" @click="goContract(row.put)">
            <div class="tq-card-side-label">认沽</div>
            <div class="tq-card-fields">
              <span class="tq-card-field">
                <label>最新价</label>
                <b :class="changeClass(row.put?.change_pct)">{{ fmtPrice(row.put?.last_price) }}</b>
              </span>
              <span class="tq-card-field">
                <label>Delta</label>
                <b>{{ fmtDelta(row.put?.delta) }}</b>
              </span>
              <span class="tq-card-field">
                <label>Gamma</label>
                <b>{{ fmtGamma(row.put?.gamma) }}</b>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div class="tq-empty" v-else-if="!loading">
      <p>暂无数据</p>
    </div>

    <!-- Loading -->
    <div class="tq-loading" v-if="loading">
      <span class="loading-dot"></span>
      <span>加载中...</span>
    </div>
  </div>
</template>

<style scoped>
.page-tquote {
  animation: fadeIn 0.3s ease;
}

/* ── Header ── */
.tq-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}
.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.badge-dot.live { background: var(--down); animation: pulse 2s ease-in-out infinite; }
.badge-dot.loading { background: var(--accent); }

/* ── Controls ── */
.tq-controls {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

/* Target tabs */
.target-tabs {
  display: flex;
  gap: 4px;
}
.target-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  font-size: 12px;
  gap: 2px;
}
.target-tab:hover {
  border-color: var(--accent-dim);
  color: var(--text-primary);
}
.target-tab.active {
  background: var(--accent-soft);
  border-color: var(--accent-dim);
  color: var(--accent);
}
.tab-code {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 13px;
}
.tab-name {
  font-size: 10px;
  opacity: 0.7;
}

/* Expiry tabs */
.expiry-tabs {
  display: flex;
  gap: 4px;
}
.expiry-tab {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-family: var(--font-mono);
  transition: all 0.15s;
}
.expiry-tab:hover {
  border-color: var(--border-light);
  color: var(--text-primary);
}
.expiry-tab.active {
  background: var(--accent-soft);
  border-color: var(--accent-dim);
  color: var(--accent);
  font-weight: 600;
}

/* ── Table ── */
.tq-table-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: auto;
  box-shadow: var(--shadow-card);
  max-height: calc(100vh - 220px);
}
.tq-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 800px;
}

/* Group header row */
.tq-table thead tr:first-child th {
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border);
  padding: 10px 0 6px;
  text-align: center;
}
.group-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.call-label { color: var(--up); }
.put-label { color: var(--down); }
.strike-label { color: var(--accent); }

/* Sub-header row */
.sub-header th {
  background: var(--bg-card);
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border-light);
  white-space: nowrap;
}
.sub-th.call-sub { text-align: right; }
.sub-th.strike-sub { text-align: center; }
.sub-th.put-sub { text-align: left; }

/* Column widths */
.col-call { width: auto; }
.col-strike { width: 90px; }
.col-put { width: auto; }

/* Data rows */
.tq-row {
  transition: background 0.1s;
  border-bottom: 1px solid var(--border);
}
.tq-row:hover {
  background: var(--bg-row-hover);
}
.tq-row.atm {
  background: var(--accent, rgba(240,160,48,0.06));
}
.tq-row.atm:hover {
  background: var(--accent, rgba(240,160,48,0.1));
}

/* Cells */
.col-val {
  padding: 8px 10px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: nowrap;
}
.call-val {
  text-align: right;
  color: var(--up);
}
.put-val {
  text-align: left;
  color: var(--down);
}
.call-name {
  text-align: right;
  font-size: 11px;
  color: var(--text-secondary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.put-name {
  text-align: left;
  font-size: 11px;
  color: var(--text-secondary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Strike cell */
.strike-cell {
  text-align: center;
  background: var(--bg-primary);
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  padding: 8px 6px;
  position: relative;
}
.strike-value {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
}
.strike-tag {
  display: inline-block;
  font-size: 9px;
  font-weight: 700;
  background: var(--accent);
  color: var(--bg-deep);
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 4px;
  vertical-align: middle;
}
.atm-strike {
  background: var(--accent, rgba(240,160,48,0.08)) !important;
  border-left: 2px solid var(--accent) !important;
  border-right: 2px solid var(--accent) !important;
}

/* Clickable cell links */
.cell-link {
  cursor: pointer;
  transition: color 0.15s;
}
.cell-link:hover {
  color: var(--accent);
  text-decoration: underline;
}

/* Mini expiry tag in all-expiry mode */
.expiry-tag-mini {
  display: inline-block;
  font-size: 9px;
  font-weight: 600;
  background: var(--bg-deep);
  color: var(--text-muted);
  padding: 1px 4px;
  border-radius: 2px;
  margin-right: 4px;
  border: 1px solid var(--border);
}

/* ── Empty / Loading ── */
.tq-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.tq-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px;
  color: var(--text-secondary);
  font-size: 13px;
}
.loading-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse 1s ease-in-out infinite;
}

/* ── Responsive ── */
/* ── 移动端卡片（默认隐藏） ── */
.tq-mobile-cards { display: none; }
.tq-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
}
.tq-card.atm { border-color: var(--accent-dim); }
.tq-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border);
}
.tq-card-strike {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 700;
  color: var(--accent);
}
.tq-card-expiry {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
}
.tq-card-body { display: flex; }
.tq-card-side {
  flex: 1;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}
.tq-card-side:hover { background: var(--bg-row-hover); }
.call-side { border-right: 1px solid var(--border); }
.tq-card-side-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.call-side .tq-card-side-label { color: var(--up); }
.put-side .tq-card-side-label { color: var(--down); }
.tq-card-fields {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tq-card-field {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.tq-card-field label {
  color: var(--text-muted);
  font-size: 11px;
}
.tq-card-field b {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .tq-desktop-table { display: none; }
  .tq-mobile-cards { display: block; }
  .tq-header { flex-direction: column; align-items: flex-start; gap: 12px; }
  .tq-controls { align-items: flex-start; width: 100%; }
  .target-tabs { flex-wrap: wrap; width: 100%; }
  .target-tab { flex: 1; min-width: 60px; padding: 6px 8px; }
  .tab-name { display: none; }
  .expiry-tabs { flex-wrap: wrap; }
  .page-title { font-size: 16px; }
}
@media (min-width: 769px) {
  .tq-mobile-cards { display: none !important; }
}
</style>
