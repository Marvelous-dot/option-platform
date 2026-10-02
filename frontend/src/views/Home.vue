<template>
  <div class="home">
    <!-- 顶部滚动进度条 -->
    <div class="h-progress" aria-hidden="true"><i :style="{ transform: `scaleX(${progress})` }"></i></div>

    <!-- 悬浮导航 -->
    <header class="h-nav" :class="{ solid: scrolled }">
      <a class="h-brand" href="#top" @click.prevent="toTop">
        <span class="h-logo">V</span>
        <span class="h-name">海疆期权</span>
        <span class="h-badge">v2</span>
      </a>
      <nav class="h-links" aria-label="页面导览">
        <a v-for="s in navSections" :key="s.id" :href="'#' + s.id" @click.prevent="goTo(s.id)">{{ s.label }}</a>
      </nav>
      <router-link class="h-cta" to="/tquote">进入平台</router-link>
    </header>

    <!-- ============ HERO ============ -->
    <section id="top" class="hero">
      <div class="hero-bg" ref="heroBgEl" aria-hidden="true">
        <i class="orb orb-a"></i><i class="orb orb-b"></i><i class="orb orb-c"></i>
        <i class="grid-lines"></i>
      </div>
      <div class="hero-inner">
        <p class="hero-kicker rv" style="--d:.0s">SHANGHAI ETF OPTIONS · 市场数据工作台</p>
        <h1 class="hero-title">
          <span class="line rv" style="--d:.08s">把期权市场，</span>
          <span class="line rv" style="--d:.18s">一眼看<em>清楚</em>。</span>
        </h1>
        <p class="hero-sub rv" style="--d:.3s">
          海疆期权 v2 —— 面向个人投资者的期权数据工作台：实时 T 型报价、隐含波动率与
          Greeks、全量合约筛选导出、标的 K 线与策略到期推演，全部基于真实挂牌行情。
        </p>
        <div class="hero-actions rv" style="--d:.42s">
          <router-link to="/tquote" class="btn-accent">进入平台 →</router-link>
          <a class="btn-ghost" href="#tquote" @click.prevent="goTo('tquote')">先看看能做什么</a>
        </div>
        <div class="tickers rv" style="--d:.56s" v-if="tickers.length" aria-label="标的实时行情">
          <div class="tk" v-for="t in tickers" :key="t.code">
            <div class="tk-l"><b>{{ t.code }}</b><span>{{ t.name }}</span></div>
            <div class="tk-r">
              <b class="num" :class="chgClass(t.chg)">{{ t.price }}</b>
              <span class="num" :class="chgClass(t.chg)">{{ fmtChg(t.chg) }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="scroll-hint" aria-hidden="true"><i></i><span>向下滚动</span></div>
    </section>

    <!-- ============ 01 T 型报价 ============ -->
    <section id="tquote" class="feat">
      <div class="feat-inner">
        <div class="feat-copy rv">
          <span class="feat-no">01</span>
          <h2>像交易终端一样<em>看盘</em></h2>
          <p>T 型报价把认购与认沽按行权价左右对齐，买卖挂价、隐含波动率、希腊字母逐合约铺开——一屏之内，市场结构尽收眼底。</p>
          <ul class="feat-points">
            <li>认购 / 认沽 T 型对排，虚实值分区清晰</li>
            <li>IV · Delta / Gamma / Theta / Vega 逐合约展示</li>
            <li>30 秒自动刷新，行情缺失自动降级 stale 标注</li>
          </ul>
        </div>
        <div class="feat-visual rv" style="--d:.12s">
          <div class="panel">
            <div class="panel-head"><span class="chip chip-accent">510050 · 50ETF购10月</span><span class="chip">2026-10 到期</span></div>
            <div class="tq-mock">
              <div class="tq-row tq-head">
                <span>购·最新</span><span>购·IV</span><span class="tq-k">行权价</span><span>沽·IV</span><span>沽·最新</span>
              </div>
              <div class="tq-row" v-for="(r, i) in trows" :key="r.k" :class="{ atm: r.atm }" :style="{ '--d': (i * 80) + 'ms' }">
                <span class="num c-up">{{ r.cP }}</span>
                <span class="num c-dim">{{ r.cIv }}</span>
                <span class="tq-k num">{{ r.k }}</span>
                <span class="num c-dim">{{ r.pIv }}</span>
                <span class="num c-down">{{ r.pP }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ 02 全量行情 ============ -->
    <section id="quotes" class="feat flip">
      <div class="feat-inner">
        <div class="feat-copy rv">
          <span class="feat-no">02</span>
          <h2>数百行合约，<em>一键</em>筛到底</h2>
          <p>五只标的全部挂牌合约汇成一张表。按到期月份、虚实值、关键词组合筛选，点列排序，找到目标合约直接跳详情。</p>
          <ul class="feat-points">
            <li>到期日 / 虚实值 / 关键词组合筛选</li>
            <li>任意列排序，点击直达合约详情页</li>
            <li>一键导出 CSV，离线分析随你</li>
          </ul>
        </div>
        <div class="feat-visual rv" style="--d:.12s">
          <div class="panel">
            <div class="panel-head">
              <span class="chip chip-accent">全部标的</span>
              <span class="chip">到期日 ▾</span><span class="chip">虚实值 ▾</span>
              <span class="chip chip-btn">导出 CSV</span>
            </div>
            <div class="q-mock">
              <div class="q-row q-head"><span>代码</span><span>名称</span><span>最新</span><span>IV</span></div>
              <div class="q-row" v-for="(r, i) in qrows" :key="r.code" :style="{ '--d': (i * 70) + 'ms' }">
                <span class="num c-code">{{ r.code }}</span>
                <span>{{ r.name }}</span>
                <span class="num" :class="r.dir > 0 ? 'c-up' : 'c-down'">{{ r.last }}</span>
                <span class="num c-dim">{{ r.iv }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ 03 标的 K 线 ============ -->
    <section id="kline" class="feat">
      <div class="feat-inner">
        <div class="feat-copy rv">
          <span class="feat-no">03</span>
          <h2>行情断了，<em>历史</em>还在</h2>
          <p>标的日 K 全部落盘缓存。上游数据源偶尔抽风没关系——最近的历史依然可看，并以 stale 明确标注，不让你误当成实时。</p>
          <ul class="feat-points">
            <li>五只 ETF 标的日 K · 均线 / 成交量联动</li>
            <li>日 K 落盘缓存，重启后预热秒开</li>
            <li>十字光标查看单日开高低收</li>
          </ul>
        </div>
        <div class="feat-visual rv" style="--d:.12s">
          <div class="panel">
            <div class="panel-head"><span class="chip chip-accent">510050 · 日 K</span><span class="chip">MA5 / MA20</span></div>
            <div class="kwrap">
              <svg viewBox="0 0 440 240" preserveAspectRatio="xMidYMid meet" role="img" aria-label="K线示意">
                <line v-for="gy in [60, 110, 160]" :key="gy" x1="20" :y1="gy" x2="424" :y2="gy" class="kgrid"></line>
                <line x1="20" y1="212" x2="424" y2="212" class="kaxis"></line>
                <g v-for="(c, i) in candles" :key="i" class="candle" :style="{ '--d': (i * 42) + 'ms' }">
                  <line :x1="c.cx" :y1="c.yh" :x2="c.cx" :y2="c.yl" :class="c.up ? 'wick-u' : 'wick-d'"></line>
                  <rect :x="c.cx - 9" :y="c.yt" width="18" :height="c.bh" :class="c.up ? 'cu' : 'cd'" rx="1.5"></rect>
                </g>
                <path :d="maPath" pathLength="1" data-draw class="maline"></path>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ 04 策略实验室 ============ -->
    <section id="lab" class="feat flip">
      <div class="feat-inner">
        <div class="feat-copy rv">
          <span class="feat-no">04</span>
          <h2>先推演，<em>再下单</em></h2>
          <p>用真实挂牌合约搭组合：牛市价差、跨式、勒式……到期盈亏曲线随选腿实时重算，盈亏平衡点一眼定位。再配上波动率曲面，把 IV 立着看。</p>
          <ul class="feat-points">
            <li>真实挂牌合约组合，到期盈亏实时推演</li>
            <li>波动率曲面 / 微笑 / 期限结构多视角</li>
            <li>独立模型假设 · 模拟盘，非投资建议</li>
          </ul>
        </div>
        <div class="feat-visual rv" style="--d:.12s">
          <div class="lab-grid">
            <div class="panel">
              <div class="panel-head"><span class="chip chip-accent">牛市价差 · 到期盈亏</span></div>
              <svg viewBox="0 0 440 220" preserveAspectRatio="xMidYMid meet" role="img" aria-label="到期盈亏示意">
                <line x1="30" y1="120" x2="410" y2="120" class="zeroline"></line>
                <polygon points="40,150 170,150 260,60 400,60 400,120 40,120" class="payoff-area"></polygon>
                <path d="M 40,150 L 170,150 L 260,60 L 400,60" pathLength="1" data-draw class="payoff-line"></path>
                <circle cx="200" cy="120" r="4" class="dot dot-accent"></circle>
                <circle cx="170" cy="150" r="4" class="dot"></circle>
                <circle cx="260" cy="60" r="4" class="dot"></circle>
                <text x="200" y="106" class="svg-txt svg-accent">盈亏平衡</text>
                <text x="148" y="172" class="svg-txt">低行权价</text>
                <text x="278" y="52" class="svg-txt">高行权价</text>
              </svg>
            </div>
            <div class="panel">
              <div class="panel-head"><span class="chip chip-accent">波动率微笑 · IV</span></div>
              <svg viewBox="0 0 440 200" preserveAspectRatio="xMidYMid meet" role="img" aria-label="波动率微笑示意">
                <line x1="30" y1="170" x2="410" y2="170" class="zeroline"></line>
                <path d="M 40,55 C 130,175 310,175 400,55" pathLength="1" data-draw class="smile-line"></path>
                <circle cx="40" cy="55" r="4" class="dot"></circle>
                <circle cx="223" cy="145" r="4" class="dot dot-accent"></circle>
                <circle cx="400" cy="55" r="4" class="dot"></circle>
                <text x="238" y="150" class="svg-txt svg-accent">ATM · IV 低点</text>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ 数据源 ============ -->
    <section id="sources" class="srcs">
      <div class="srcs-inner rv">
        <p class="srcs-label">数据来源</p>
        <div class="srcs-chips">
          <span class="src-chip"><b>上交所</b>合约目录</span>
          <span class="src-chip"><b>新浪财经</b>报价 / IV / Greeks</span>
          <span class="src-chip"><b>腾讯财经</b>标的价格</span>
          <span class="src-chip src-dim"><b>本地缓存</b>日 K 落盘 · stale 降级</span>
        </div>
      </div>
    </section>

    <!-- ============ CTA ============ -->
    <section id="enter" class="outro">
      <div class="outro-inner">
        <h2 class="rv">准备好了吗？<em>行情</em>正在跳动。</h2>
        <p class="rv" style="--d:.1s">打开平台，五只标的、数百份合约、实时 IV 与策略推演，都在等你。</p>
        <div class="rv" style="--d:.2s">
          <router-link to="/tquote" class="btn-accent btn-big">进入平台 →</router-link>
        </div>
      </div>
      <footer class="h-footer">
        <span>© 2026 海疆期权 · v2 市场数据</span>
        <span>所有数据仅作参考，不构成投资建议</span>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const navSections = [
  { id: 'tquote', label: 'T 型报价' },
  { id: 'quotes', label: '全量行情' },
  { id: 'kline', label: '标的 K 线' },
  { id: 'lab', label: '策略实验室' },
]

const progress = ref(0)
const scrolled = ref(false)
const heroBgEl = ref(null)
const tickers = ref([])

const reduced = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/* ---------- 实时行情条（hero） ---------- */
async function loadTickers() {
  const codes = ['510050', '510300', '510500', '588000', '588080']
  try {
    const res = await Promise.all(codes.map(async c => {
      const r = await fetch(`/api/tquote/${c}`)
      return r.ok ? r.json() : null
    }))
    tickers.value = res
      .filter(Boolean)
      .map(d => ({
        code: d.target_code,
        name: (d.target_name || '').replace(/\(.*\)/, ''),
        price: d.spot?.price,
        chg: d.spot?.change_pct,
      }))
      .filter(t => t.price != null)
    // 行情条是异步 v-if 渲染的，挂载时的观察器扫不到它 → 渲染后补挂
    await nextTick()
    setupReveal()
  } catch { tickers.value = [] }
}

function chgClass(c) { return c > 0 ? 'up' : c < 0 ? 'down' : '' }
function fmtChg(c) { return (c > 0 ? '+' : '') + Number(c).toFixed(2) + '%' }

/* ---------- 滚动驱动 ---------- */
let ticking = false
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => {
    ticking = false
    const y = window.scrollY
    const dh = document.documentElement.scrollHeight - window.innerHeight
    progress.value = dh > 0 ? Math.min(1, y / dh) : 0
    scrolled.value = y > 24
    if (!reduced) {
      if (heroBgEl.value && y < window.innerHeight * 1.2) {
        heroBgEl.value.style.transform = `translateY(${y * 0.28}px)`
      }
      drawPaths()
    }
  })
}

function drawPaths() {
  const vh = window.innerHeight
  for (const p of drawItems) {
    const r = p.host.getBoundingClientRect()
    if (r.bottom < -80 || r.top > vh + 80) continue
    const t = clamp((vh * 0.92 - r.top) / (r.height + vh * 0.4), 0, 1)
    p.el.style.strokeDashoffset = String(1 - t)
  }
}

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)) }

/* ---------- 揭示动画 ---------- */
let io = null
function setupReveal() {
  const els = document.querySelectorAll('.rv')
  if (reduced || !('IntersectionObserver' in window)) {
    els.forEach(el => el.classList.add('in'))
    return
  }
  if (!io) {
    io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) }
      })
    }, { threshold: 0.15, rootMargin: '0px 0px -6% 0px' })
  }
  els.forEach(el => { if (!el.classList.contains('in')) io.observe(el) })
}

/* ---------- 导航 ---------- */
function goTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
}
function toTop() { window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' }) }

/* ---------- K 线 mock 数据（svg 坐标） ---------- */
const kRaw = [0.30, 0.36, 0.33, 0.42, 0.40, 0.48, 0.45, 0.55, 0.52, 0.61, 0.58, 0.68, 0.65, 0.75]
const Y = v => 212 - v * 190
const candles = kRaw.map((c, i) => {
  const o = i === 0 ? c - 0.04 : kRaw[i - 1]
  const up = c >= o
  const h = Math.max(o, c) + 0.035
  const l = Math.min(o, c) - 0.035
  const cx = 26 + i * 29
  const yt = Y(Math.max(o, c))
  return { cx, up, yh: Y(h), yl: Y(l), yt, bh: Math.max(2, Math.abs(Y(o) - Y(c))) }
})

function smoothPath(pts) {
  if (!pts.length) return ''
  let d = `M ${pts[0][0]},${pts[0][1]}`
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1]
    const [x1, y1] = pts[i]
    const mx = (x0 + x1) / 2
    d += ` C ${mx},${y0} ${mx},${y1} ${x1},${y1}`
  }
  return d
}
const maPath = smoothPath(kRaw.map((v, i) => [26 + i * 29, Y(v)]))

/* ---------- T 型报价 mock ---------- */
const trows = [
  { k: '2.850', cP: '0.0965', cIv: '26.8', pIv: '27.4', pP: '0.0081' },
  { k: '2.900', cP: '0.0648', cIv: '25.6', pIv: '26.2', pP: '0.0172' },
  { k: '2.950', cP: '0.0402', cIv: '24.9', pIv: '25.5', pP: '0.0334', atm: true },
  { k: '3.000', cP: '0.0231', cIv: '24.7', pIv: '25.9', pP: '0.0671' },
  { k: '3.050', cP: '0.0120', cIv: '25.2', pIv: '26.6', pP: '0.1068' },
]

/* ---------- 全量行情 mock ---------- */
const qrows = [
  { code: '10007345', name: '50ETF购10月2900', last: '0.0648', iv: '25.6', dir: 1 },
  { code: '10007351', name: '50ETF沽10月2900', last: '0.0172', iv: '26.2', dir: -1 },
  { code: '10007402', name: '300ETF购10月4000', last: '0.0891', iv: '21.4', dir: 1 },
  { code: '10007418', name: '500ETF购10月6500', last: '0.0453', iv: '23.8', dir: 1 },
  { code: '10007455', name: '科创50购10月1050', last: '0.0327', iv: '31.5', dir: -1 },
]

/* ---------- 生命周期 ---------- */
let drawItems = []
onMounted(() => {
  setupReveal()
  drawItems = Array.from(document.querySelectorAll('[data-draw]')).map(el => ({
    el,
    host: el.closest('section') || el.ownerSVGElement?.parentElement,
  }))
  if (reduced) {
    drawItems.forEach(p => { p.el.style.strokeDashoffset = '0' })
  } else {
    drawPaths()
  }
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll, { passive: true })
  onScroll()
  loadTickers()
})
onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  io?.disconnect()
})
</script>

<style scoped>
/* ================= 进度条 ================= */
.h-progress {
  position: fixed; top: 0; left: 0; right: 0; height: 3px; z-index: 300;
  background: transparent; pointer-events: none;
}
.h-progress i {
  display: block; height: 100%; background: var(--accent);
  transform: scaleX(0); transform-origin: left;
}

/* ================= 导航 ================= */
.h-nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 200;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 28px; height: 60px;
  transition: background .25s, box-shadow .25s, border-color .25s;
  border-bottom: 1px solid transparent;
}
.h-nav.solid {
  background: rgba(255,255,255,.88);
  backdrop-filter: blur(10px);
  border-bottom-color: var(--border);
}
.h-brand { display: flex; align-items: center; gap: 8px; cursor: pointer; text-decoration: none; }
.h-logo {
  width: 28px; height: 28px; border-radius: 8px;
  background: var(--accent); color: var(--accent-text);
  font-weight: 800; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}
.h-name { font-weight: 800; font-size: 15px; color: var(--text); letter-spacing: -0.02em; }
.h-badge {
  font-size: 10px; font-weight: 700; color: var(--accent-ink);
  border: 1px solid var(--accent); border-radius: var(--pill); padding: 1px 7px;
}
.h-links { display: flex; gap: 22px; }
.h-links a {
  font-size: 13px; color: var(--text-dim); text-decoration: none; font-weight: 600;
  transition: color .15s; position: relative;
}
.h-links a:hover { color: var(--text); }
.h-links a::after {
  content: ''; position: absolute; left: 0; right: 100%; bottom: -4px; height: 2px;
  background: var(--accent); transition: right .25s;
}
.h-links a:hover::after { right: 0; }
.h-cta {
  background: var(--accent); color: var(--accent-text);
  font-weight: 700; font-size: 13px; text-decoration: none;
  padding: 8px 18px; border-radius: var(--pill); transition: background .15s, transform .15s;
}
.h-cta:hover { background: var(--accent-hover); }

/* ================= HERO ================= */
.hero {
  position: relative; min-height: 100vh; min-height: 100svh;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; padding: 120px 28px 80px;
}
.hero-bg { position: absolute; inset: -12% 0 0 0; pointer-events: none; will-change: transform; }
.orb { position: absolute; border-radius: 50%; filter: blur(60px); }
.orb-a { width: 420px; height: 420px; left: 6%; top: 8%; background: rgba(205,246,78,.16); }
.orb-b { width: 360px; height: 360px; right: 4%; top: 30%; background: rgba(37,99,235,.07); }
.orb-c { width: 300px; height: 300px; left: 38%; bottom: -4%; background: rgba(205,246,78,.10); }
.grid-lines {
  position: absolute; inset: 0; opacity: .5;
  background-image:
    linear-gradient(var(--border-subtle) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: radial-gradient(ellipse 75% 65% at 50% 42%, #000 35%, transparent 78%);
  -webkit-mask-image: radial-gradient(ellipse 75% 65% at 50% 42%, #000 35%, transparent 78%);
}
.hero-inner { position: relative; max-width: 1120px; width: 100%; text-align: center; }
.hero-kicker {
  font-size: 12px; font-weight: 700; letter-spacing: .22em;
  color: var(--accent-ink); margin-bottom: 22px;
}
.hero-title {
  font-size: clamp(38px, 6.6vw, 78px); line-height: 1.08;
  font-weight: 800; letter-spacing: -0.035em; color: var(--text);
}
.hero-title .line { display: block; }
.hero-title em {
  font-style: normal; position: relative; white-space: nowrap;
  background: linear-gradient(transparent 62%, var(--accent) 62%);
  padding: 0 .06em;
}
.hero-sub {
  max-width: 640px; margin: 26px auto 0;
  font-size: clamp(14px, 1.5vw, 16.5px); line-height: 1.75; color: var(--text-dim);
}
.hero-actions { display: flex; gap: 14px; justify-content: center; margin-top: 34px; flex-wrap: wrap; }
.btn-accent {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--accent); color: var(--accent-text); text-decoration: none;
  font-weight: 800; font-size: 14.5px; padding: 13px 30px; border-radius: var(--pill);
  box-shadow: 0 6px 22px var(--accent-glow);
  transition: transform .18s, box-shadow .18s, background .15s;
}
.btn-accent:hover { background: var(--accent-hover); transform: translateY(-2px); box-shadow: 0 10px 28px var(--accent-glow); }
.btn-ghost {
  display: inline-flex; align-items: center;
  border: 1px solid var(--border); color: var(--text); text-decoration: none;
  font-weight: 700; font-size: 14.5px; padding: 13px 26px; border-radius: var(--pill);
  background: rgba(255,255,255,.7); transition: border-color .15s, transform .18s;
}
.btn-ghost:hover { border-color: var(--text); transform: translateY(-2px); }
.btn-big { font-size: 16px; padding: 16px 40px; }

/* 实时行情条 */
.tickers {
  display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;
  margin-top: 46px;
}
.tk {
  display: flex; align-items: center; gap: 12px;
  background: rgba(255,255,255,.82); border: 1px solid var(--border);
  border-radius: 12px; padding: 10px 14px; box-shadow: var(--shadow);
  min-width: 168px; text-align: left;
}
.tk-l { display: flex; flex-direction: column; gap: 1px; }
.tk-l b { font-size: 12.5px; font-family: var(--font-mono); color: var(--text); }
.tk-l span { font-size: 10.5px; color: var(--text-muted); }
.tk-r { display: flex; flex-direction: column; align-items: flex-end; gap: 1px; margin-left: auto; }
.tk-r b { font-size: 14px; font-family: var(--font-mono); }
.tk-r span { font-size: 11px; font-family: var(--font-mono); }
.num.up { color: var(--up); }
.num.down { color: var(--down); }

.scroll-hint {
  position: absolute; bottom: 26px; left: 50%; transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  color: var(--text-muted); font-size: 11px; letter-spacing: .18em;
}
.scroll-hint i {
  width: 1px; height: 34px; background: var(--border); position: relative; overflow: hidden;
}
.scroll-hint i::after {
  content: ''; position: absolute; left: 0; top: -40%; width: 100%; height: 40%;
  background: var(--accent-ink); animation: hint 1.8s ease-in-out infinite;
}
@keyframes hint { to { top: 110%; } }

/* ================= 揭示动画 ================= */
.rv {
  opacity: 0; transform: translateY(26px);
  transition: opacity .7s ease var(--d, 0s), transform .7s cubic-bezier(.22,.61,.36,1) var(--d, 0s);
}
.rv.in { opacity: 1; transform: none; }

/* ================= 功能 section ================= */
.feat { position: relative; }
.feat-inner {
  max-width: 1120px; margin: 0 auto; padding: 110px 28px;
  display: grid; grid-template-columns: 5fr 6fr; gap: 64px; align-items: center;
}
.feat.flip .feat-inner { grid-template-columns: 6fr 5fr; }
.feat.flip .feat-copy { order: 2; }
.feat.flip .feat-visual { order: 1; }
.feat-copy { position: relative; padding-left: 26px; }
.feat-copy::before {
  content: ''; position: absolute; left: 0; top: 8px; bottom: 8px; width: 3px;
  border-radius: 2px; background: linear-gradient(var(--accent), transparent);
  transform: scaleY(0); transform-origin: top; transition: transform .8s cubic-bezier(.22,.61,.36,1) .15s;
}
.feat-copy.in::before { transform: scaleY(1); }
.feat-no {
  display: block; font-size: 76px; font-weight: 800; line-height: 1;
  color: transparent; -webkit-text-stroke: 1.5px var(--border);
  margin-bottom: 6px; letter-spacing: -0.04em; user-select: none;
}
.feat-copy h2 {
  font-size: clamp(24px, 3vw, 34px); font-weight: 800; letter-spacing: -0.03em;
  color: var(--text); line-height: 1.25; margin-bottom: 14px;
}
.feat-copy h2 em {
  font-style: normal; background: linear-gradient(transparent 64%, var(--accent) 64%);
  padding: 0 .05em;
}
.feat-copy p { font-size: 14.5px; line-height: 1.8; color: var(--text-dim); margin-bottom: 20px; }
.feat-points { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.feat-points li {
  position: relative; padding-left: 22px;
  font-size: 13.5px; color: var(--text-dim); line-height: 1.6;
}
.feat-points li::before {
  content: ''; position: absolute; left: 0; top: .5em;
  width: 12px; height: 6px; border-radius: 4px;
  border-left: 2.5px solid var(--accent-ink); border-bottom: 2.5px solid var(--accent-ink);
  transform: rotate(-45deg) translateY(-1px);
}

/* 面板 */
.panel {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow); padding: 18px;
}
.panel-head { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.chip {
  font-size: 11px; font-weight: 700; color: var(--text-dim);
  border: 1px solid var(--border); border-radius: var(--pill); padding: 4px 11px;
  background: var(--bg-elevated); white-space: nowrap;
}
.chip-accent { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
.chip-btn { background: var(--text); color: #fff; border-color: var(--text); }

/* T 型 mock */
.tq-mock { display: flex; flex-direction: column; gap: 4px; }
.tq-row {
  display: grid; grid-template-columns: 1fr 1fr 1.1fr 1fr 1fr; gap: 4px; align-items: center;
  padding: 9px 10px; border-radius: 8px; font-size: 12.5px;
  opacity: 0; transform: translateX(18px);
  transition: opacity .5s ease var(--d, 0s), transform .5s ease var(--d, 0s);
}
.rv.in .tq-row { opacity: 1; transform: none; }
.tq-row.tq-head { font-size: 10.5px; color: var(--text-muted); font-weight: 700; }
.tq-row:not(.tq-head):hover { background: var(--bg-hover); }
.tq-row.atm { background: var(--accent-glow); outline: 1px solid var(--accent); }
.tq-k { text-align: center; font-weight: 800; color: var(--text); }
.tq-head .tq-k { color: var(--text-muted); font-weight: 700; }
.c-up { color: var(--up); }
.c-down { color: var(--down); }
.c-dim { color: var(--text-dim); }
.c-code { color: var(--text); font-weight: 600; }
.tq-row .num, .q-row .num { font-family: var(--font-mono); font-size: 12px; }

/* 行情 mock */
.q-mock { display: flex; flex-direction: column; }
.q-row {
  display: grid; grid-template-columns: 90px 1fr 76px 56px; gap: 10px; align-items: center;
  padding: 9px 10px; font-size: 12.5px; border-bottom: 1px solid var(--border-subtle);
  opacity: 0; transform: translateY(12px);
  transition: opacity .5s ease var(--d, 0s), transform .5s ease var(--d, 0s);
}
.rv.in .q-row { opacity: 1; transform: none; }
.q-row:last-child { border-bottom: none; }
.q-row:not(.q-head):hover { background: var(--bg-hover); }
.q-head { font-size: 10.5px; color: var(--text-muted); font-weight: 700; border-bottom: 1px solid var(--border); }

/* K线 svg */
.kwrap svg { width: 100%; height: auto; display: block; }
.kgrid { stroke: var(--border-subtle); stroke-dasharray: 3 5; }
.kaxis { stroke: var(--border); }
.candle { transform: scaleY(0); transform-origin: 0 212px; }
.rv.in .candle { transform: scaleY(1); transition: transform .55s cubic-bezier(.22,.61,.36,1) var(--d, 0s); }
.cu { fill: var(--up); }
.cd { fill: var(--down); }
.wick-u { stroke: var(--up); stroke-width: 1.4; }
.wick-d { stroke: var(--down); stroke-width: 1.4; }
.maline {
  fill: none; stroke: var(--ma20); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round;
  stroke-dasharray: 1; stroke-dashoffset: 1;
}

/* 策略/波动率 */
.lab-grid { display: flex; flex-direction: column; gap: 16px; }
.lab-grid svg { width: 100%; height: auto; display: block; }
.zeroline { stroke: var(--border); stroke-dasharray: 4 5; }
.payoff-line, .smile-line {
  fill: none; stroke: var(--accent-ink); stroke-width: 3;
  stroke-linecap: round; stroke-linejoin: round;
  stroke-dasharray: 1; stroke-dashoffset: 1;
}
.payoff-area { fill: var(--accent-glow); opacity: 0; transition: opacity .8s ease .5s; }
.rv.in .payoff-area { opacity: 1; }
.dot { fill: #fff; stroke: var(--text-dim); stroke-width: 2; }
.dot-accent { fill: var(--accent); stroke: var(--accent-ink); }
.svg-txt { font-size: 11px; fill: var(--text-muted); font-weight: 600; }
.svg-accent { fill: var(--accent-ink); }

/* ================= 数据源 ================= */
.srcs { padding: 60px 28px 30px; }
.srcs-inner { max-width: 1120px; margin: 0 auto; text-align: center; }
.srcs-label {
  font-size: 11px; font-weight: 700; letter-spacing: .22em; color: var(--text-muted);
  margin-bottom: 18px;
}
.srcs-chips { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
.src-chip {
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid var(--border); border-radius: var(--pill);
  padding: 9px 18px; font-size: 12.5px; color: var(--text-dim); background: var(--bg-elevated);
}
.src-chip b { color: var(--text); font-weight: 800; }
.src-dim { border-style: dashed; }

/* ================= CTA / footer ================= */
.outro {
  padding: 130px 28px 0; text-align: center; position: relative; overflow: hidden;
}
.outro::before {
  content: ''; position: absolute; left: 50%; bottom: -180px; transform: translateX(-50%);
  width: 640px; height: 320px; border-radius: 50%;
  background: rgba(205,246,78,.14); filter: blur(70px); pointer-events: none;
}
.outro-inner { position: relative; max-width: 720px; margin: 0 auto; }
.outro h2 {
  font-size: clamp(30px, 4.6vw, 52px); font-weight: 800; letter-spacing: -0.03em;
  color: var(--text); line-height: 1.2; margin-bottom: 16px;
}
.outro h2 em {
  font-style: normal; background: linear-gradient(transparent 62%, var(--accent) 62%);
  padding: 0 .06em;
}
.outro p { color: var(--text-dim); font-size: 15px; line-height: 1.75; margin-bottom: 30px; }
.h-footer {
  position: relative; max-width: 1120px; margin: 90px auto 0;
  padding: 18px 0 26px; border-top: 1px solid var(--border);
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  font-size: 12px; color: var(--text-muted);
}

/* ================= 响应式 ================= */
@media (max-width: 960px) {
  .feat-inner, .feat.flip .feat-inner { grid-template-columns: 1fr; gap: 36px; padding: 80px 20px; }
  .feat.flip .feat-copy { order: 1; }
  .feat.flip .feat-visual { order: 2; }
  .feat-no { font-size: 56px; }
}
@media (max-width: 768px) {
  .h-nav { padding: 0 16px; height: 54px; }
  .h-links { display: none; }
  .hero { padding: 96px 16px 70px; }
  .hero-actions .btn-accent, .hero-actions .btn-ghost { width: 100%; justify-content: center; }
  .tickers { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .tk { min-width: 0; }
  .scroll-hint { display: none; }
  .srcs { padding: 40px 16px 10px; }
  .outro { padding: 90px 16px 0; }
  .h-footer { margin-top: 60px; flex-direction: column; align-items: center; gap: 4px; }
}
@media (max-width: 420px) {
  .tickers { grid-template-columns: 1fr; }
}

/* ================= 降低动效 ================= */
@media (prefers-reduced-motion: reduce) {
  .rv, .tq-row, .q-row, .candle, .feat-copy::before, .payoff-area { transition: none !important; }
  .rv, .tq-row, .q-row { opacity: 1 !important; transform: none !important; }
  .candle { transform: none !important; }
  .feat-copy::before { transform: scaleY(1) !important; }
  .payoff-area { opacity: 1 !important; }
  .maline, .payoff-line, .smile-line { stroke-dashoffset: 0 !important; }
  .scroll-hint i::after { animation: none; }
}
</style>
