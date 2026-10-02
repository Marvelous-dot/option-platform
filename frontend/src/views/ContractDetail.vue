<template>
  <section class="detail">
    <div class="detail-toolbar"><router-link to="/tquote">← 返回 T 型报价</router-link></div>
    <p v-if="error" role="alert" :class="['error', { 'error-404': errorStatus === 404, 'error-503': errorStatus === 503 }]">{{ error }}</p>
    <p v-if="error" class="error-actions">
      <router-link to="/tquote">← 返回 T 型报价</router-link>
      <button type="button" @click="load" :disabled="loading">重试</button>
    </p>
    <p v-else-if="loading">正在获取合约数据…</p>
    <template v-else-if="data">
      <div class="page-head">
        <div class="ph-title">
          <span class="ph-kicker">CONTRACT DETAIL · {{ data.contract.option_code }}</span>
          <h1>{{ data.contract.name }}</h1>
          <p class="ph-desc">{{ data.contract.option_code }} · {{ data.contract.contract_id }} · {{ statusLabel }} · {{ freshnessLabel }}。IV / Greeks 为数据源计算值，口径未核验。</p>
        </div>
        <div class="ph-actions">
          <button @click="load" :disabled="loading">{{ loading ? '加载中…' : '刷新' }}</button>
        </div>
      </div>
      <dl class="metrics">
        <div><dt>最新价（元/份）</dt><dd>{{ fmt(q.last_price) }}</dd></div>
        <div><dt>标的代码</dt><dd>{{ data.contract.target_code }}</dd></div>
        <div><dt>方向</dt><dd>{{ data.contract.option_type === 'call' ? '认购' : '认沽' }}</dd></div>
        <div><dt>行权价</dt><dd>{{ fmt(data.contract.strike) }}</dd></div>
        <div><dt>到期日</dt><dd>{{ data.contract.expiry }}</dd></div>
        <div><dt>合约单位（份/张）</dt><dd>{{ data.contract.contract_unit ?? '--' }}</dd></div>
        <div><dt>IV</dt><dd>{{ q.iv == null ? '--' : fmt(q.iv * 100, 2) + '%' }}</dd></div>
        <div v-for="field in ['delta', 'gamma', 'theta', 'vega']" :key="field"><dt>{{ field }}</dt><dd>{{ fmt(q[field]) }}</dd></div>
        <div><dt>成交量（源返回值）</dt><dd>{{ q.volume ?? '--' }}</dd></div>
        <div><dt>最高价</dt><dd>{{ fmt(q.high) }}</dd></div>
        <div><dt>最低价</dt><dd>{{ fmt(q.low) }}</dd></div>
      </dl>
      <div class="provenance">
        <p>挂牌目录：{{ data.catalog_source }} · 报价来源：{{ q.source || '--' }}</p>
        <p>抓取时间：{{ q.fetched_at || '--' }}</p>
        <p>行情时间：{{ q.market_ts || '未知，不代表实时' }}</p>
        <p>标的价格：{{ fmt(data.spot?.price) }} · 来源：{{ data.spot?.source || '--' }} · 源时间：{{ data.spot?.market_time || '未知' }}</p>
        <p>本页只展示基础详情；情景定价与盈亏曲线尚未实现。缺失字段不补零。</p>
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const data = ref(null), error = ref(''), errorStatus = ref(null), loading = ref(false)
let controller, sequence = 0
const q = computed(() => data.value?.quote || {})
const statusLabel = computed(() => ({ ok: '报价可用', stale: '过期报价', unavailable: '报价不可用' }[q.value.data_status] || '报价不可用'))
const freshnessLabel = computed(() => ({ fresh: '当日数据（非实时保证）', stale: '过期数据', unknown: '时效未知' }[q.value.freshness] || '时效未知'))
function fmt(value, digits = 4) { return value == null || !Number.isFinite(Number(value)) ? '--' : Number(value).toFixed(digits) }
async function load() {
  const id = ++sequence
  controller?.abort()
  controller = new AbortController()
  data.value = null; error.value = ''; errorStatus.value = null; loading.value = true
  try {
    const response = await fetch(`/api/contract/${encodeURIComponent(route.params.code)}`, { signal: controller.signal })
    const result = await response.json()
    if (!response.ok) {
      const e = new Error(result.detail || `HTTP ${response.status}`)
      e.status = response.status
      throw e
    }
    if (id === sequence) data.value = result
  } catch (e) {
    if (id === sequence && e.name !== 'AbortError') {
      errorStatus.value = e.status || null
      error.value = e.status === 404
        ? `合约 ${route.params.code} 未在上交所当日挂牌目录中，可能已摘牌、到期或代码有误。可返回 T 型报价重新选择。`
        : e.status === 503
          ? '合约行情暂不可用：数据源（上交所目录或新浪行情）本次未返回有效数据，非合约本身无效。可稍后点击刷新重试。'
          : `合约详情获取失败：${e.message}`
    }
  } finally {
    if (id === sequence) loading.value = false
  }
}
watch(() => route.params.code, load, { immediate: true })
onUnmounted(() => { ++sequence; controller?.abort() })
</script>

<style scoped>
.detail { max-width: 1280px; margin: auto; padding: 8px 0 24px; }
.detail-toolbar { display:flex; justify-content:space-between; align-items:center; gap:16px; }
.detail-toolbar a {
  color: var(--accent-ink); text-decoration: none; font-size: 13px; font-weight: 500;
  padding: 7px 14px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg);
  transition: background-color 0.15s, border-color 0.15s;
}
.detail-toolbar a:hover { background: var(--bg-hover); border-color: var(--border); }
.detail-toolbar a:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.detail-toolbar button {
  padding: 7px 18px; cursor: pointer;
  background: var(--accent); color: var(--accent-text); border: none; border-radius: 8px;
  font: inherit; font-size: 13px; font-weight: 500;
  transition: background-color 0.15s;
}
.detail-toolbar button:hover:not(:disabled) { background: var(--accent-hover); }
.detail-toolbar button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.detail-toolbar button:active:not(:disabled) { transform: translateY(1px); }
.detail-toolbar button:disabled { opacity: 0.5; cursor: not-allowed; }
h1 { margin:0; font-size: 24px; font-weight: 600; letter-spacing: -0.5px; }
p:not(.notice) { color: var(--text-dim); font-size: 13px; }
.error { color: var(--err); background: var(--err-dim); border: 1px solid color-mix(in srgb, var(--err) 30%, white);
  border-radius: 10px; padding: 14px 18px; margin: 18px 0 0; line-height: 1.7; }
.error-503 { color: var(--warn); background: var(--warn-dim); border-color: color-mix(in srgb, var(--warn) 35%, white); }
.error-actions { display: flex; gap: 14px; align-items: center; margin: 14px 0 0; }
.error-actions a { color: var(--accent-ink); font-weight: 600; text-decoration: none; font-size: 13px; }
.error-actions a:hover { text-decoration: underline; }
.error-actions button { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: var(--pill);
  padding: 7px 18px; font-size: 13px; font-weight: 600; }
.error-actions button:hover { background: var(--bg-hover); }
.notice {
  padding:14px 18px; border:1px solid var(--warn); margin:20px 0;
  border-radius: 10px; font-size: 13px; color: var(--warn);
  background: var(--warn-dim);
}
.metrics {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--radius-lg); overflow: hidden;
}
.metrics div { padding:18px; background: var(--bg); outline: 1px solid var(--border); outline-offset: -1px; }
dt { color: var(--text-muted); font-size:12px; font-weight:500; }
dd { margin:10px 0 0; font-size:21px; font-weight:600; color: var(--text);
  font-variant-numeric:tabular-nums; font-family: var(--font-mono); }
.provenance {
  margin-top:24px; line-height:1.9; overflow-wrap:anywhere; font-size:13px;
  color: var(--text-dim);
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: var(--radius-lg); padding: 16px 18px;
}
/* 窄屏：工具栏纵排、指标卡 2 列、字号收敛 */
@media (max-width: 768px) {
  .detail { padding: 16px 14px; }
  .detail-toolbar { flex-direction: column; align-items: stretch; gap: 10px; }
  .detail-toolbar a, .detail-toolbar button { width: 100%; text-align: center; }
  h1 { font-size: 20px; margin: 18px 0 6px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics div { padding: 12px 14px; }
  dd { font-size: 18px; }
  .notice { padding: 12px 14px; font-size: 12px; }
  .provenance { margin-top: 16px; padding: 14px; font-size: 12px; line-height: 1.7; }
}
</style>
