<template>
  <div class="tickerbar" role="status" aria-label="标的实时行情">
    <span class="tb-live" aria-hidden="true"><i></i>LIVE</span>
    <div class="tb-track">
      <template v-if="tickers.length">
        <span class="tb-item" v-for="t in tickers" :key="t.code"
          :class="t.chg > 0 ? 'up' : t.chg < 0 ? 'down' : ''">
          <b class="tb-code">{{ t.code }}</b>
          <span class="tb-price">{{ t.price }}</span>
          <span class="tb-chg">{{ fmtChg(t.chg) }}</span>
        </span>
      </template>
      <span v-else class="tb-empty">标的行情加载中…</span>
    </div>
    <span class="tb-note" aria-hidden="true">30s 刷新</span>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const CODES = ['510050', '510300', '510500', '588000', '588080']
const tickers = ref([])
let timer = null, alive = true, loading = false

async function load() {
  if (loading || document.visibilityState !== 'visible') return
  loading = true
  try {
    const res = await Promise.all(CODES.map(async c => {
      const r = await fetch(`/api/tquote/${c}`)
      return r.ok ? r.json() : null
    }))
    if (!alive) return
    tickers.value = res
      .filter(Boolean)
      .map(d => ({
        code: d.target_code,
        price: d.spot?.price,
        chg: d.spot?.change_pct,
      }))
      .filter(t => t.price != null)
  } catch { /* 展示条不报警：失败保留上次数据 */ }
  finally { loading = false }
}

function fmtChg(c) { return (c > 0 ? '+' : '') + Number(c).toFixed(2) + '%' }

onMounted(() => {
  load()
  timer = setInterval(load, 30000)
})
onUnmounted(() => { alive = false; if (timer) clearInterval(timer) })
</script>

<style scoped>
.tickerbar {
  display: flex; align-items: center; gap: 14px;
  padding: 0 28px; height: 36px;
  background: rgba(255,255,255,0.9);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.tb-live {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  font-size: 10px; font-weight: 800; letter-spacing: .12em; color: var(--accent-ink);
}
.tb-live i {
  width: 6px; height: 6px; border-radius: 50%; background: var(--up);
  animation: tb-pulse 2s ease-in-out infinite;
}
@keyframes tb-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
.tb-track {
  display: flex; gap: 20px; min-width: 0; flex: 1;
  overflow-x: auto; scrollbar-width: none;
}
.tb-track::-webkit-scrollbar { display: none; }
.tb-item {
  display: inline-flex; align-items: baseline; gap: 7px;
  white-space: nowrap; flex: none; font-variant-numeric: tabular-nums;
}
.tb-code { font-family: var(--font-mono); font-weight: 700; font-size: 11.5px; color: var(--text); }
.tb-price { font-family: var(--font-mono); font-weight: 700; font-size: 12.5px; color: var(--text); }
.tb-chg { font-family: var(--font-mono); font-weight: 700; font-size: 11px; color: var(--text-dim); }
.tb-item.up .tb-price, .tb-item.up .tb-chg { color: var(--up); }
.tb-item.down .tb-price, .tb-item.down .tb-chg { color: var(--down); }
.tb-empty { color: var(--text-muted); font-size: 11.5px; }
.tb-note { flex: none; font-size: 10.5px; color: var(--text-muted); }
@media (max-width: 768px) {
  .tickerbar { padding: 0 14px; gap: 10px; height: 32px; }
  .tb-track { gap: 14px; }
  .tb-note { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .tb-live i { animation: none; }
}
</style>
