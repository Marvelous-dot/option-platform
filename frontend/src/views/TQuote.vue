<template>
  <div class="page">
    <!-- 文案轮播 banner（可关闭，关闭状态持久化） -->
    <PromoBanner v-if="bannerVisible" @close="closeBanner" />

    <!-- 页头 -->
    <div class="page-head">
      <div class="ph-title">
        <span class="ph-kicker">REALTIME T-QUOTE · 30S 自动刷新</span>
        <h1>T 型报价</h1>
        <p class="ph-desc">认购 / 认沽按行权价左右对齐，IV 与 Delta 逐合约展示；行情缺失自动降级 stale 标注，不展示模拟数据。</p>
      </div>
      <div class="ph-actions">
        <button class="refresh-toggle" :class="{ on: autoRefresh }" type="button" @click="toggleAuto">
          {{ autoRefresh ? '● 自动刷新中' : '自动刷新已停' }}
        </button>
        <span class="refresh-cd" v-if="autoRefresh">{{ refreshCountdown > 0 ? refreshCountdown + 's' : '…' }}</span>
      </div>
    </div>

    <!-- 控制栏 -->
    <div class="controls">
      <div class="target-tabs">
        <button
          v-for="t in targets"
          :key="t.target"
          class="tab"
          :class="{ active: selectedTarget === t.target, broken: !t.catalog_ok }"
          @click="selectTarget(t.target)"
        >
          <span class="tab-code">{{ t.target }}</span>
          <span class="tab-name">{{ shortName(t.name) }}</span>
        </button>
      </div>
      <div class="expiry-tabs" v-if="expiries.length">
        <button
          class="tab small"
          :class="{ active: selectedExpiry === exp }"
          v-for="exp in expiries"
          :key="exp"
          @click="selectedExpiry = exp"
        >{{ expiryLabel(exp) }}</button>
      </div>
    </div>

    <!-- 状态条：数据状态必须可见 -->
    <div class="statusbar" :class="statusClass">
      <template v-if="data">
        <span class="status-dot"></span>
        <span class="status-text">{{ statusText }}</span>
        <span class="status-spot" v-if="data.spot">
          <span class="spot-label">标的现价</span>
          <b class="spot-big">{{ data.spot.price.toFixed(3) }}</b>
          <b class="chg" :class="data.spot.change_pct >= 0 ? 'up' : 'down'">
            {{ data.spot.change_pct >= 0 ? '+' : '' }}{{ data.spot.change_pct }}%
          </b>
          <span class="spot-time">{{ fmtMarketTime(data.spot.market_time) }}</span>
        </span>
        <span class="status-spot unavailable" v-else>标的价格不可用</span>
        <span class="status-time">抓取 {{ fmtIso(data.fetched_at) }}</span>
        <span class="status-time" v-if="data.as_of">行情 {{ fmtIso(data.as_of) }}（{{ data.freshness === 'fresh' ? '当日' : '非当日' }}）</span>
        <span class="status-time" v-else>行情时间未知（时效未知，口径未核验）</span>
        <span class="refresh-hint" v-if="lastError">{{ lastError }}</span>
      </template>
      <template v-else>
        <span class="status-dot"></span>
        <span class="status-text">{{ loading ? '加载中…' : '暂无数据' }}</span>
        <span class="status-time" v-if="lastError">{{ lastError }}</span>
      </template>
    </div>

    <!-- T 型表 -->
    <div class="tq-wrap" v-if="rows.length">
      <table class="tq">
        <thead>
          <tr>
            <th colspan="4" class="grp call">认购 CALL</th>
            <th class="grp strike">行权价</th>
            <th colspan="4" class="grp put">认沽 PUT</th>
          </tr>
          <tr class="sub">
            <th>最新价</th><th>Delta</th><th>IV</th><th>名称</th>
            <th></th>
            <th>名称</th><th>IV</th><th>Delta</th><th>最新价</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.key"
            :class="{ atm: isAtm(row.strike) }"
          >
            <td class="num" :class="legClass(row.call)">{{ fmtPrice(row.call?.last_price) }}</td>
            <td class="num">{{ fmtNum(row.call?.delta) }}</td>
            <td class="num iv">{{ fmtIv(row.call?.iv) }}</td>
            <td class="name"><router-link v-if="row.call?.option_code" :to="contractLink(row.call)">{{ row.call.name || row.call.option_code }}</router-link><span v-else>--</span></td>
            <td class="strike">
              <span class="strike-v">{{ fmtStrike(row.strike) }}</span>
              <span class="atm-tag" v-if="isAtm(row.strike)">ATM</span>
            </td>
            <td class="name"><router-link v-if="row.put?.option_code" :to="contractLink(row.put)">{{ row.put.name || row.put.option_code }}</router-link><span v-else>--</span></td>
            <td class="num iv">{{ fmtIv(row.put?.iv) }}</td>
            <td class="num">{{ fmtNum(row.put?.delta) }}</td>
            <td class="num" :class="legClass(row.put)">{{ fmtPrice(row.put?.last_price) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 空态 / 不可用 -->
    <div class="empty" v-else-if="!loading">
      <p class="empty-title">暂无可展示的合约行情</p>
      <p class="empty-detail" v-if="data?.status_detail">{{ data.status_detail }}</p>
      <p class="empty-detail">数据源失败时不展示模拟数据。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { readState, writeState } from '../utils/remember.mjs'
import PromoBanner from '../components/PromoBanner.vue'

const tquoteRemembered = readState('tquote', {})
const targets = ref([])
const selectedTarget = ref(tquoteRemembered.target || '510050')
const selectedExpiry = ref('')
const expiries = ref([])
const data = ref(null)
const loading = ref(false)
const lastError = ref('')
const spotPrice = ref(null)

// 文案轮播 banner：关闭状态持久化，避免每次刷新都再弹
const bannerVisible = ref(!localStorage.getItem('hj_promo_closed'))
function closeBanner() {
  bannerVisible.value = false
  localStorage.setItem('hj_promo_closed', '1')
}

const REFRESH_MS = 30000
const REFRESH_BACKOFF_MAX = 120000   // 连续失败时的最大退避间隔
const contractLink = leg => `/contract/${encodeURIComponent(leg.option_code)}`
// 记住 T 型报价页选中的标的
let firstTquoteWrite = true
watch(selectedTarget, v => {
  if (firstTquoteWrite) { firstTquoteWrite = false; return }
  if (v) writeState('tquote', { target: v })
})

// 自动刷新：可暂停/恢复、标签页隐藏暂停、连续失败指数退避
const autoRefresh = ref(true)
const refreshCountdown = ref(Math.ceil(REFRESH_MS / 1000))
const failStreak = ref(0)
let refreshTick = null
let backoffMs = REFRESH_MS

function backoffFor(streak) {
  return streak <= 0 ? REFRESH_MS : Math.min(REFRESH_MS * 2 ** Math.min(streak, 4), REFRESH_BACKOFF_MAX)
}
function startTick() {
  if (refreshTick) return
  backoffMs = backoffFor(failStreak.value)
  refreshCountdown.value = Math.ceil(backoffMs / 1000)
  refreshTick = setInterval(() => {
    // 标签页隐藏时冻结倒计时、不发起请求
    if (document.visibilityState !== 'visible') return
    refreshCountdown.value -= 1
    if (refreshCountdown.value <= 0) {
      refreshCountdown.value = Math.ceil(backoffMs / 1000)
      fetchTQuote()
    }
  }, 1000)
}
function stopTick() {
  if (refreshTick) { clearInterval(refreshTick); refreshTick = null }
}
function toggleAuto() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) startTick()
  else { stopTick(); refreshCountdown.value = 0 }
}
// 标签页可见/隐藏切换：隐藏暂停，可见恢复并立即刷一次
function onVisibility() {
  if (document.visibilityState === 'visible') {
    if (autoRefresh.value) { startTick(); refreshCountdown.value = Math.ceil(backoffFor(failStreak.value) / 1000); fetchTQuote() }
  } else {
    stopTick()
  }
}

async function fetchTargets() {
  try {
    const res = await fetch('/api/targets')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const d = await res.json()
    targets.value = d.targets || []
  } catch (e) {
    lastError.value = `标的列表获取失败: ${e.message}`
  }
}

async function fetchExpiries() {
  expiries.value = []
  try {
    const res = await fetch(`/api/expiries/${selectedTarget.value}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const d = await res.json()
    expiries.value = d.expiries || []
    if (expiries.value.length && !expiries.value.includes(selectedExpiry.value)) {
      selectedExpiry.value = expiries.value[0]
    }
  } catch (e) {
    lastError.value = `到期日列表获取失败: ${e.message}`
  }
}

async function fetchTQuote() {
  loading.value = true
  try {
    const p = selectedExpiry.value ? `?expiry=${selectedExpiry.value}` : ''
    const res = await fetch(`/api/tquote/${selectedTarget.value}${p}`)
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || `HTTP ${res.status}`)
    }
    const d = await res.json()
    data.value = d
    spotPrice.value = d.spot?.price ?? null
    lastError.value = d.data_status === 'stale' ? (d.status_detail || '展示的是过期缓存') : ''
    // 成功：退避计数清零，恢复默认 30s 间隔
    failStreak.value = 0
    if (autoRefresh.value && refreshTick) {
      backoffMs = backoffFor(0)
      refreshCountdown.value = Math.ceil(backoffMs / 1000)
    }
  } catch (e) {
    lastError.value = `T 型报价获取失败: ${e.message}`
    if (!data.value) data.value = null
    // 失败：累加退避计数，缩短请求频率避免打爆数据源
    failStreak.value += 1
    if (autoRefresh.value && refreshTick) {
      backoffMs = backoffFor(failStreak.value)
      refreshCountdown.value = Math.ceil(backoffMs / 1000)
    }
  } finally {
    loading.value = false
  }
}

function selectTarget(code) {
  if (code === selectedTarget.value) return
  selectedTarget.value = code
  selectedExpiry.value = ''
}

const rows = computed(() => data.value?.rows || [])

const isAtm = (strike) => {
  if (spotPrice.value == null || !rows.value.length) return false
  let best = null, min = Infinity
  for (const r of rows.value) {
    const d = Math.abs(r.strike - spotPrice.value)
    if (d < min) { min = d; best = r.strike }
  }
  return strike === best
}

const statusClass = computed(() => {
  if (!data.value) return loading.value ? 'loading' : 'unavailable'
  return ['ok', 'partial'].includes(data.value.data_status) ? 'ok'
    : data.value.data_status === 'stale' ? 'stale' : 'unavailable'
})

const statusText = computed(() => {
  if (!data.value) return loading.value ? '加载中…' : '暂无数据'
  const s = data.value.data_status
  if (s === 'ok') return `报价可用 · ${data.value.status_detail || ''}`
  if (s === 'partial') return `部分可用 · ${data.value.status_detail || ''}`
  if (s === 'stale') return `过期数据 · ${data.value.status_detail || ''}`
  return `不可用 · ${data.value.status_detail || ''}`
})

function fmtPrice(v) { return v == null ? '--' : Number(v).toFixed(4) }
function fmtNum(v) { return v == null ? '--' : Number(v).toFixed(4) }
function fmtIv(v) { return v == null ? '--' : (Number(v) * 100).toFixed(2) + '%' }
function fmtStrike(v) { return Number(v).toFixed(4).replace(/0+$/, '').replace(/\.$/, '') }
function fmtIso(s) { return s ? s.replace('T', ' ').slice(5, 19) : '--' }
function fmtMarketTime(t) {
  if (!t || t.length < 12) return t || '--'
  return `${t.slice(4,6)}-${t.slice(6,8)} ${t.slice(8,10)}:${t.slice(10,12)}:${t.slice(12,14)}`
}
function expiryLabel(exp) {
  if (!exp || exp.length < 6) return exp
  return `${parseInt(exp.slice(4, 6))}月${exp.slice(6, 8) !== '00' ? exp.slice(6,8) + '日' : ''}`
}
function shortName(n) { return (n || '').split('(')[0] }
function legClass(leg) {
  if (!leg || leg.data_status !== 'ok') return 'unavailable'
  return ''
}

watch(selectedTarget, () => { selectedExpiry.value = ''; fetchExpiries() })
watch(selectedExpiry, (v) => { if (v) fetchTQuote() })

onMounted(() => {
  fetchTargets()
  fetchExpiries()
  startTick()
  document.addEventListener('visibilitychange', onVisibility)
})

onUnmounted(() => {
  stopTick()
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<style scoped>
/* 窄屏（600px 以下）：控件区纵排、tab 整行左右分布，触控面积更足 */
@media (max-width: 600px) {
  .controls { flex-direction: column; align-items: stretch; gap: 12px; }
  .target-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .tab { flex-direction: row; justify-content: space-between; min-width: 0; width: 100%; padding: 10px 14px; }
  .tab.active::before { top: 8px; bottom: 8px; }
  .tab.small { flex: none; min-height: 36px; }
  .expiry-tabs { gap: 6px; }
  .statusbar { padding: 10px 12px; gap: 8px; font-size: 12px; }
  .spot-big { font-size: 17px; }
}
.tab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
