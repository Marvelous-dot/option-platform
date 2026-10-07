<template>
  <div class="app-shell">
    <div class="top-sticky" v-if="!isHome">
      <header class="topbar">
        <router-link to="/" class="brand" title="返回首页">
        <span class="brand-logo">V</span>
        <span class="brand-name">海疆期权</span>
        <span class="brand-badge">v2 · 市场数据</span>
      </router-link>
      <div class="search">
        <form class="search-form" @submit.prevent="onSearch">
          <input v-model="q" class="search-input" placeholder="搜索合约代码 / 名称…" autocomplete="off" />
          <button type="submit" class="search-btn" :disabled="searching">{{ searching ? '…' : '搜索' }}</button>
        </form>
        <div class="search-results" v-if="results.length">
          <router-link
            v-for="r in results"
            :key="r.option_code"
            :to="`/contract/${r.option_code}`"
            class="search-result"
            @click="hideResults"
          >
            <span class="sr-code">{{ r.option_code }}</span>
            <span class="sr-name">{{ r.name }}</span>
            <span class="sr-target">{{ r.target_code }} · {{ r.expiry }}</span>
          </router-link>
        </div>
      </div>
      <nav class="nav">
        <router-link to="/tquote" class="nav-link">T 型报价</router-link>
        <router-link to="/quotes" class="nav-link">全量行情</router-link>
        <router-link to="/kline" class="nav-link">标的K线</router-link>
        <router-link to="/strategy" class="nav-link">策略模拟</router-link>
        <router-link to="/volatility" class="nav-link">波动率</router-link>
        <router-link to="/screener" class="nav-link">机会筛选</router-link>
      </nav>
      </header>
      <TickerBar />
    </div>
    <main class="main" :class="{ 'main-bare': isHome }">
      <router-view />
    </main>
    <footer class="footer" v-if="!isHome">
      <span>行情来源：上交所（合约目录）· 新浪财经（合约报价/IV/Greeks）· 腾讯财经（标的价格）</span>
      <span class="footer-note">行情缺失时显示"不可用"；策略模拟基于真实挂牌合约报价做到期盈亏推演，非行情本身</span>
    </footer>

    <!-- 移动端底部 TabBar：补齐 768px 以下被隐藏的导航（首页自带导航，不显示） -->
    <nav class="tabbar" v-if="!isHome">
      <router-link to="/tquote" class="tabbar-item" :class="{ active: route.path.startsWith('/tquote') }">
        <span class="tb-ic">T</span><span class="tb-lb">T型报价</span>
      </router-link>
      <router-link to="/quotes" class="tabbar-item" :class="{ active: route.path.startsWith('/quotes') }">
        <span class="tb-ic">＄</span><span class="tb-lb">行情</span>
      </router-link>
      <router-link to="/kline" class="tabbar-item" :class="{ active: route.path.startsWith('/kline') }">
        <span class="tb-ic">K</span><span class="tb-lb">K线</span>
      </router-link>
      <router-link to="/strategy" class="tabbar-item" :class="{ active: route.path.startsWith('/strategy') }">
        <span class="tb-ic">策</span><span class="tb-lb">策略</span>
      </router-link>
      <router-link to="/volatility" class="tabbar-item" :class="{ active: route.path.startsWith('/volatility') }">
        <span class="tb-ic">σ</span><span class="tb-lb">波动率</span>
      </router-link>
      <router-link to="/screener" class="tabbar-item" :class="{ active: route.path.startsWith('/screener') }">
        <span class="tb-ic">◎</span><span class="tb-lb">筛选</span>
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import TickerBar from './components/TickerBar.vue'

const router = useRouter()
const route = useRoute()
const isHome = computed(() => route.path === '/')
const q = ref('')
const results = ref([])
const searching = ref(false)
let lastResultsFor = ''
let hideTimer = null

const TARGETS = ['510050', '510300', '510500', '588000', '588080']

async function onSearch() {
  const term = q.value.trim()
  if (!term) { results.value = []; lastResultsFor = ''; return }
  searching.value = true
  results.value = []
  lastResultsFor = term
  try {
    // 并发查所有标的（limit=20 足够覆盖常见搜索），命中唯一 → 直接跳；多条 → 列结果
    const all = await Promise.all(TARGETS.map(async code => {
      try {
        const res = await fetch(`/api/quotes/${code}?search=${encodeURIComponent(term)}&limit=20`)
        const d = res.ok ? await res.json() : null
        return d?.rows || []
      } catch { return [] }
    }))
    if (lastResultsFor !== term) return
    const rows = all.flat()
    results.value = rows.slice(0, 12)
    if (rows.length === 1) {
      router.push(`/contract/${rows[0].option_code}`)
      results.value = []
      q.value = ''
      lastResultsFor = ''
    }
  } catch (e) {
    if (lastResultsFor === term) results.value = []
  } finally {
    if (lastResultsFor === term) searching.value = false
  }
}

function hideResults() {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => { results.value = []; q.value = ''; lastResultsFor = '' }, 120)
}
</script>

<style scoped>
/* topbar 与常驻行情条作为一个整体吸顶；
   topbar 自身的 sticky 规则在 wrapper 内等效不动，不冲突 */
.top-sticky { position: sticky; top: 0; z-index: 100; }
/* 注意：不要在此设置 .nav 的 display —— 全局移动端媒体查询靠 display:none 隐藏导航，
   scoped 规则 specificity 更高会压过它（历史 bug）。这里只调间距。 */
.nav { gap: 4px; }
.brand { text-decoration: none; display: flex; align-items: center; }
.main-bare { padding: 0; max-width: none; }
.search { position: relative; flex: 1; min-width: 120px; max-width: 380px; margin: 0 8px; }
.search-form { display: flex; gap: 6px; }
.search-input {
  flex: 1; min-width: 0; height: 32px; padding: 0 12px;
  border: 1px solid var(--border); border-radius: 16px;
  background: var(--bg-elevated); color: var(--text);
  font-size: 13px; outline: none; transition: border-color .15s, box-shadow .15s;
}
.search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.search-btn {
  height: 32px; padding: 0 14px; border-radius: 16px; border: 1px solid var(--border);
  background: var(--bg); color: var(--text); font-size: 13px; cursor: pointer;
  transition: border-color .15s, background .15s;
}
.search-btn:hover:not(:disabled) { border-color: var(--accent); }
.search-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.search-btn:active:not(:disabled) { transform: translateY(1px); }
.search-btn:disabled { opacity: .5; cursor: not-allowed; }
.search-results {
  position: absolute; top: 40px; left: 0; right: 0; z-index: 60;
  background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  box-shadow: var(--shadow); max-height: 280px; overflow: auto;
}
.search-result {
  display: grid; grid-template-columns: 130px 1fr auto; gap: 8px; align-items: center;
  padding: 10px 14px; font-size: 12.5px; color: var(--text-dim);
  border-bottom: 1px solid var(--border); cursor: pointer; transition: background .12s;
}
.search-result:last-child { border-bottom: none; }
.search-result:hover { background: var(--bg-hover); }
.sr-code { font-family: var(--font-mono); color: var(--text); font-weight: 600; }
.sr-target { font-size: 11px; color: var(--text-muted); }
@media (max-width: 640px) {
  .topbar { height: auto; min-height: 52px; padding: 12px; gap: 12px; flex-wrap: wrap; }
  .search { max-width: 100%; width: 100%; }
  .nav { width: 100%; flex-wrap: wrap; }
  .nav-link { padding: 8px 10px; }
}
</style>
