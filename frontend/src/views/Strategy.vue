<template>
  <section class="strategy-page">
    <div class="page-head">
      <div class="ph-title">
        <span class="ph-kicker">STRATEGY LAB · 真实挂牌合约推演</span>
        <h1>策略模拟</h1>
        <p class="ph-desc">三步完成推演：① 选策略 → ② 选标的与到期日 → ③ 为每条腿挑真实挂牌合约（或一键自动配对）。权利金取市场实际报价（元 / 份，未乘合约单位）；到期盈亏 = 到期组合内在价值 − 建仓净支出，按合约单位放大。</p>
      </div>
      <div class="ph-actions">
        <span class="ph-note warn">仅到期推演 · 不含时间价值与交易成本</span>
      </div>
    </div>
    <div class="assumptions">
      <p>忽略手续费、融资、保证金与分红现金流；各行权价处分段线性解析求盈亏平衡点。权利金报价缺失的腿会保留合约身份，但组合盈亏不可用；到期价情景曲线横轴基准为标的参考价（实时现货缺失时取 K 线最近收盘并标 stale）。</p>
    </div>

    <div v-if="deepNote" class="deep-note" role="note">
      <span class="dn-badge">来自机会筛选</span>{{ deepNote }}
    </div>

    <div class="strategy-layout">
      <aside class="strategy-side">
        <!-- STEP 1 选择策略 -->
        <div class="legs-card step-card">
          <h2><span class="step-no">1</span> 选择策略</h2>
          <div class="preset-groups">
            <div class="preset-group" v-for="g in presetGroups" :key="g.id">
              <p class="group-label">{{ g.label }}</p>
              <button type="button"
                v-for="p in g.items" :key="p.id"
                class="preset-item" :class="{ active: presetMode === p.id }"
                @click="onPresetChange(p.id)">
                <span class="pi-name">{{ p.name }}</span>
                <span class="pi-desc">{{ p.desc }}</span>
                <div class="pi-legs">
                  <span v-for="l in p.legs" :key="l.key"
                    :class="l.side === 'buy' ? 'leg-buy' : 'leg-sell'">
                    {{ l.side === 'buy' ? '买' : '卖' }}{{ l.type === 'call' ? '购' : '沽' }}{{ l.units > 1 ? '×' + l.units : '' }}
                  </span>
                </div>
              </button>
            </div>
            <div class="preset-group">
              <button type="button" class="preset-item" :class="{ active: presetMode === FREE_MODE }" @click="onPresetChange(FREE_MODE)">
                <span class="pi-name">自由组合</span>
                <span class="pi-desc">逐腿自定义：方向 × 张数 × 真实合约，任意拼价差 / 跨式 / 蝶式…</span>
              </button>
            </div>
          </div>
        </div>

        <!-- STEP 2 标的与到期日 -->
        <div class="target-card step-card">
          <h2><span class="step-no">2</span> 标的与到期日</h2>
          <div class="target-pickers">
            <label for="strategy-target">标的</label>
            <select id="strategy-target" v-model="target" @change="onTargetChange">
              <option v-for="t in targetOptions" :key="t.code" :value="t.code">{{ t.code }} · {{ shortName(t.name) }}</option>
            </select>
          </div>
          <div class="target-pickers">
            <label for="strategy-expiry">到期日</label>
            <select id="strategy-expiry" v-model="expiry">
              <option v-for="e in expiryOptions" :key="e" :value="e">{{ expiryLabel(e) }}</option>
            </select>
          </div>
          <div class="spot-line" v-if="spot != null">
            <span>参考价 {{ fmt(spot, 4) }} 元</span>
            <span :class="spotSource?.stale ? 'stale-tag' : 'fresh-tag'">{{ spotSource?.stale ? 'K线缓存（stale）' : '实时现货' }}</span>
            <span class="spot-time" v-if="spotSource?.marketTime">{{ fmtMarketTime(spotSource.marketTime) }}</span>
          </div>
          <p class="note" v-if="marketError">{{ marketError }}</p>
          <p class="note" v-if="!contractsLoading && !marketError && !expiryOptions.length">该标的暂无挂牌合约目录</p>
        </div>

        <!-- STEP 3 选择合约 -->
        <div class="legs-card step-card">
          <div class="step-h">
            <h2><span class="step-no">3</span> 选择合约</h2>
            <button type="button" class="auto-btn" @click="autoAssign"
              :disabled="!contracts.length || contractsLoading"
              title="按参考价就近为每条腿自动挑选合约">⚡ 自动配对</button>
          </div>
          <p class="note" v-if="contractsLoading">正在加载挂牌合约…</p>
          <p class="note" v-else-if="!contracts.length && !marketError">请先在上方选择标的与到期日，加载挂牌合约后即可为每条腿挑合约（默认会自动配对）。</p>
          <template v-else>
            <template v-if="presetMode !== FREE_MODE">
              <p class="note">
                已选「{{ presetById(presetMode)?.name }}」：腿方向与沽/购已锁定（{{ presetLegsText }}），
                每条腿下拉可换行权价，默认已按参考价自动配对。
              </p>
              <div class="leg-row" v-for="(leg, i) in presetLegs" :key="'p'+i">
                <div class="leg-controls leg-locked">
                  <span class="leg-side-static">{{ leg.side === 'buy' ? '买入' : '卖出' }}</span>
                  <span class="leg-type-tag">{{ leg.type === 'call' ? '购 Call' : '沽 Put' }}</span>
                  <span class="leg-units-static">× {{ leg.units }} 张</span>
                </div>
                <label class="leg-contract" :for="`preset-contract-${i}`">
                  <select :id="`preset-contract-${i}`" :value="leg.contractId" @change="onPresetSelect(i, $event)">
                    <option value="" disabled>选择{{ leg.type === 'call' ? '购' : '沽' }}权合约…</option>
                    <option v-for="c in contractsForLeg(leg)" :key="c.contract_id" :value="c.contract_id">
                      {{ c.name || c.option_code }} · K {{ fmt(c.strike, 4) }} · 价 {{ c.last_price == null ? '--' : fmt(c.last_price, 4) }}
                    </option>
                  </select>
                </label>
                <p class="note leg-missing" v-if="selectedContract(leg) && selectedContract(leg).last_price == null">该合约报价缺失，组合盈亏暂不可用</p>
              </div>
            </template>
            <template v-else>
              <p class="note">每行一条腿：方向 × 张数 × 合约，同一到期日不同行权价可混合（价差、跨式、蝶式…）。张数为正整数。</p>
              <div class="leg-row" v-for="(leg, i) in legs" :key="'f'+i">
                <div class="leg-controls">
                  <label class="leg-side">
                    <input type="radio" value="buy" v-model="leg.side" /> 买
                  </label>
                  <label class="leg-side">
                    <input type="radio" value="sell" v-model="leg.side" /> 卖
                  </label>
                  <label class="leg-units">张数
                    <input :value="leg.units" type="number" min="1" max="1000000" step="1" required
                      @input="onUnitsInput(leg, $event)" aria-label="张数" />
                  </label>
                </div>
                <label class="leg-contract">
                  <select v-model="leg.contractId">
                    <option value="" disabled>选择合约…</option>
                    <option v-for="c in availableContracts" :key="c.contract_id" :value="c.contract_id">
                      {{ c.name || c.option_code }} · K {{ fmt(c.strike, 4) }} · 价 {{ c.last_price == null ? '--' : fmt(c.last_price, 4) }}
                    </option>
                  </select>
                </label>
                <p class="note leg-missing" v-if="selectedContract(leg) && selectedContract(leg).last_price == null">该合约报价缺失，组合盈亏暂不可用</p>
                <button type="button" class="leg-remove" @click="removeLeg(i)" :disabled="legs.length === 1" aria-label="删除该腿">移除</button>
              </div>
              <button type="button" class="leg-add" @click="addLeg">＋ 增加一条腿</button>
            </template>
          </template>
        </div>
      </aside>

      <div class="strategy-main">
        <p v-if="marketError" class="error" role="alert">{{ marketError }}</p>
        <div v-else-if="!result" class="guide" role="status">
          <template v-if="contractsLoading">⏳ 正在加载挂牌合约…</template>
          <template v-else-if="!contracts.length">👆 请先在左侧完成第 2 步：选择标的与到期日</template>
          <template v-else-if="!anyLegSelected">👆 第 3 步：在左侧为每条腿选择合约（或点「⚡ 自动配对」），选完立即生成盈亏曲线</template>
          <template v-else>⚠️ 至少一条腿报价缺失，补齐后自动生成盈亏曲线</template>
        </div>
        <template v-else>
          <div class="metrics">
            <article>
              <h2>建仓净支出</h2>
              <strong v-if="totalEntryCost != null">{{ fmt(totalEntryCost) }} 元</strong>
              <strong v-else class="na">不可用</strong>
              <p>正数为净付出，负数为净收入；按张数 × 报价 × 合约单位累计</p>
            </article>
            <article>
              <h2>最大收益</h2>
              <strong v-if="Number.isFinite(result.risk.maxProfit)">{{ fmt(result.risk.maxProfit) }} 元</strong>
              <strong v-else-if="result.risk.maxProfit === Infinity" class="unbounded">无上限</strong>
              <strong v-else class="na">不可用</strong>
              <p>到期价全域上界</p>
            </article>
            <article>
              <h2>最大亏损</h2>
              <strong v-if="Number.isFinite(result.risk.maxLoss)">{{ fmt(result.risk.maxLoss) }} 元</strong>
              <strong v-else-if="result.risk.maxLoss === Infinity" class="unbounded">无上限</strong>
              <strong v-else class="na">不可用</strong>
              <p>到期价全域下界</p>
            </article>
            <article>
              <h2>到期盈亏曲线</h2>
              <strong>{{ result ? '已生成' : '等待合约' }}</strong>
              <p>横轴为到期标的价格，纵轴为组合盈亏（元）</p>
            </article>
          </div>

          <div class="result-card">
            <h2>组合明细</h2>
            <div class="table-wrap"><table>
              <thead><tr><th scope="col">腿</th><th scope="col">合约</th><th scope="col">方向</th><th scope="col">张数</th><th scope="col">行权价 K（元）</th><th scope="col">报价（元/份）</th><th scope="col">合约单位</th><th scope="col">净支出（元）</th></tr></thead>
              <tbody>
                <tr v-for="(leg, index) in activeLegs" :key="index">
                  <th scope="row">{{ index + 1 }}</th>
                  <td>{{ (selectedContract(leg)?.name) || '—' }}</td>
                  <td>{{ leg.side === 'buy' ? '买入' : '卖出' }}</td>
                  <td>{{ leg.units }}</td>
                  <td>{{ selectedContract(leg) ? fmt(selectedContract(leg).strike, 4) : '—' }}</td>
                  <td>{{ selectedContract(leg)?.last_price == null ? '—' : fmt(selectedContract(leg).last_price, 4) }}</td>
                  <td>{{ selectedContract(leg)?.contract_unit ?? '—' }}</td>
                  <td>{{ legNetCost(leg) == null ? '—' : fmt(legNetCost(leg)) }}</td>
                </tr>
              </tbody>
            </table></div>
            <p class="note" v-if="!allUsable">至少一条腿报价缺失，组合净支出与盈亏曲线不可用；补齐报价后自动恢复。</p>
          </div>

          <div class="result-card">
            <h2>解析盈亏平衡点 <span class="note">到期标的价格 S ≥ 0</span></h2>
            <p class="roots">{{ breakEvenText }}</p>
            <p class="note">按各行权价处分段线性解析求根（基于实际报价权利金）；零盈亏整段单独列为区间。</p>
            <p class="note">尾部斜率 {{ result.tailSlope > 0 ? '+1（S→∞ 收益无上限）' : result.tailSlope < 0 ? '−1（S→0 亏损无上限）' : '0（尾部平坦，风险有限）' }}；按组合净头寸判断，非按单腿。</p>
          </div>

          <div v-if="chart" class="result-card">
            <h2>到期盈亏曲线 <span class="note">横轴 S（元），纵轴盈亏（元）</span></h2>
            <svg viewBox="0 0 880 350" role="img" aria-labelledby="payoff-title payoff-desc">
              <title id="payoff-title">到期盈亏</title>
              <desc id="payoff-desc">横轴到期标的价格，纵轴组合盈亏（元）。虚线为零盈亏线，点线为盈亏平衡点。</desc>
              <g v-for="tick in chart.yTicks" :key="'y'+tick.value"><line x1="88" x2="850" :y1="tick.y" :y2="tick.y" class="grid-line"/><text x="78" :y="tick.y + 4" text-anchor="end">{{ fmt(tick.value, 0) }}</text></g>
              <line x1="88" x2="850" :y1="chart.zeroY" :y2="chart.zeroY" class="zero-line"/>
              <g v-for="tick in chart.xTicks" :key="'x'+tick.value"><text :x="tick.x" y="322" text-anchor="middle">{{ fmt(tick.value, 2) }}</text></g>
              <polyline :points="chart.points" class="payoff-line"/>
              <line v-for="root in chart.roots" :key="root" :x1="chart.x(root)" :x2="chart.x(root)" y1="25" y2="300" class="root-line"/>
              <circle :cx="chart.x(probe.spot)" :cy="chart.y(probe.pnl)" r="5" class="probe-dot"/>
              <text x="850" y="345" text-anchor="end">到期标的价格 S（元）</text>
            </svg>
            <label for="strategy-probe">到期价格情景：{{ fmt(probe.spot) }} 元
              <input id="strategy-probe" v-model="probePosition" type="range" min="0" max="1000" step="1"
                :aria-valuetext="`${fmt(probe.spot)} 元，组合盈亏 ${probe.pnl == null ? '不可用' : fmt(probe.pnl) + ' 元'}`" />
            </label>
            <p class="scenario" aria-live="polite">情景到期盈亏：<strong v-if="probe.pnl != null">{{ fmt(probe.pnl) }} 元</strong><strong v-else>不可用（报价缺失）</strong> · 占净支出比例 <strong>{{ probePct }}</strong></p>
            <p class="note">滑块支持方向键 / Home / End。图窗仅展示 0–{{ fmt(chart.maxS) }}，不代表价格预测；窗口外平衡点仍列于上方。</p>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { buildCustomStrategy, customStrategyAt, PRESET_GROUPS, PRESET_BY_ID, MARKET_PRESETS } from '../utils/strategy.mjs'
import { resolveLegSpecs } from '../utils/screener.mjs'

const route = useRoute()

const targetOptions = [
  { code: '510050', name: '50ETF（上证50）' },
  { code: '510300', name: '300ETF（沪深300）' },
  { code: '510500', name: '500ETF（中证500）' },
  { code: '588000', name: '科创50ETF' },
  { code: '588080', name: '科创100ETF' },
]
const target = ref('510050')
const expiry = ref('')
const expiryOptions = ref([])
const spot = ref(null)
const spotSource = ref(null)
const contracts = ref([])
const marketError = ref('')
const contractsLoading = ref(false)
const deepNote = ref('')
let pendingLegSpecs = null   // 深链预填的腿规格，等合约列表就绪后 resolve

const legs = reactive([
  { side: 'buy', units: 1, contractId: '' },
])

const FREE_MODE = 'free'
const presetMode = ref(FREE_MODE)

// 常用策略的一句话说明（展示在左侧策略卡片上，帮用户快速理解腿结构）
const PRESET_DESC = {
  'long-call': '纯多头：到期 S 高于行权价才盈利，亏损上限 = 权利金',
  'short-call': '纯空头：到期 S 低于行权价盈利，S 上涨亏损无上限',
  'long-put': '看跌：到期 S 低于行权价才盈利，亏损上限 = 权利金',
  'short-put': '看多：到期 S 高于行权价盈利，S 下跌亏损无上限',
  'long-straddle': '同价同月买购 + 买沽，赌大幅波动（方向不定）',
  'short-straddle': '同价同月卖购 + 卖沽，赌窄幅震荡，两侧尾部无界',
  'long-strangle': '低行权价买沽 + 高行权价买购，比跨式便宜、需更大波动',
  'short-strangle': '低行权价卖沽 + 高行权价卖购，比卖出跨式风险更宽',
  'bull-call': '低行权价买购 + 高行权价卖购，中等看涨，最大盈亏均有界',
  'bear-put': '高行权价买沽 + 低行权价卖沽，中等看跌，最大盈亏均有界',
  'call-butterfly': '低买 1 + 中卖 2 + 高买 1，赌到期价贴近中行权价',
}

// 左侧「常用策略」分组列表（按钮式选择，含腿摘要）；点选即切到对应预设模式
const presetGroups = computed(() => PRESET_GROUPS.map(g => ({
  id: g.id,
  label: g.label,
  items: g.items.map(id => {
    const m = MARKET_PRESETS.find(p => p.id === id)
    return {
      id,
      name: PRESET_BY_ID[id].name,
      desc: PRESET_DESC[id] || '',
      legs: m ? m.legs.map((l, i) => ({ ...l, key: `${id}-${i}` })) : [],
    }
  }),
})))

// 预设腿的合约选择（索引与模板腿对应）
const presetSelections = ref([])

function presetById(id) {
  return MARKET_PRESETS.find(p => p.id === id) || null
}

// 预设模式下的腿（含已选合约），供模板渲染
const presetLegs = computed(() => {
  if (presetMode.value === FREE_MODE) return []
  const p = presetById(presetMode.value)
  if (!p) return []
  return p.legs.map((t, i) => ({ ...t, contractId: presetSelections.value[i] || '' }))
})

const presetLegsText = computed(() =>
  presetLegs.value.map(l => (l.side === 'buy' ? '买' : '卖') + (l.type === 'call' ? '购' : '沽')).join(' · ')
)

// 当前生效的腿：预设模式 → 策略模板腿（方向/沽购/张数锁定）；自由模式 → 可编辑 legs
const activeLegs = computed(() => {
  if (presetMode.value === FREE_MODE) return legs
  return presetLegs.value
})

const anyLegSelected = computed(() =>
  activeLegs.value.some(l => l.contractId)
)

// 各腿可选手盘：按腿的沽/购（call/put）过滤真实挂牌合约
function contractsForLeg(leg) {
  if (leg.type) return contracts.value.filter(c => c.option_type === leg.type)
  return contracts.value
}

function onPresetSelect(i, event) {
  presetSelections.value[i] = event.target.value
}

// ⚡ 自动配对：按参考价就近为每条腿挑合约。
// 同类型（同 call/put）的多条腿取距离参考价最近的 n 个不同行权价，
// 升序后按腿模板顺序分配（模板腿天然按低→中→高定义，如牛市价差/蝶式）。
function autoAssign() {
  const isFree = presetMode.value === FREE_MODE
  const n = isFree ? legs.length : (presetById(presetMode.value)?.legs.length || 0)
  if (!n || !contracts.value.length) return
  const typeOf = i => (isFree ? null : presetById(presetMode.value).legs[i].type)
  const groups = new Map()
  for (let i = 0; i < n; i++) {
    const t = typeOf(i) || 'any'
    if (!groups.has(t)) groups.set(t, [])
    groups.get(t).push(i)
  }
  const base = spot.value ?? (() => {
    const ks = contracts.value.map(c => c.strike).sort((a, b) => a - b)
    return ks[Math.floor(ks.length / 2)] ?? 0
  })()
  const sel = new Array(n).fill('')
  for (const [t, idxs] of groups) {
    let pool = contracts.value.filter(c => t === 'any' || c.option_type === t)
    if (!pool.length) pool = contracts.value.slice()
    const uniq = [...new Set(pool.map(c => c.strike))]
    const chosen = uniq
      .sort((a, b) => Math.abs(a - base) - Math.abs(b - base))
      .slice(0, idxs.length)
      .sort((a, b) => a - b)
    idxs.forEach((legIdx, j) => {
      const k = chosen[Math.min(j, chosen.length - 1)]
      const c = pool.find(c => c.strike === k && c.last_price != null) || pool.find(c => c.strike === k)
      if (c) sel[legIdx] = c.contract_id
    })
  }
  if (isFree) {
    legs.forEach((l, i) => { if (sel[i]) l.contractId = sel[i] })
  } else {
    presetSelections.value = sel
  }
}

function onPresetChange(id) {
  presetMode.value = id
  if (id === FREE_MODE) {
    // 回到自由模式：把预设里已选的合约并入自由 legs，避免丢选择
    for (const cid of presetSelections.value.filter(Boolean)) {
      const c = contracts.value.find(x => x.contract_id === cid)
      if (c && !legs.some(l => l.contractId === cid)) {
        const slot = legs.find(l => !l.contractId)
        if (slot) slot.contractId = cid
        else legs.push({ side: 'buy', units: 1, contractId: cid })
      }
    }
  } else if (contracts.value.length) {
    // 切到预设策略：合约已加载则立即自动配对，直接出图
    autoAssign()
  }
}

function onTargetChange() {
  expiry.value = ''
  contracts.value = []
  presetSelections.value = []
  for (const leg of legs) leg.contractId = ''
  fetchExpiries()
}

async function fetchExpiries() {
  expiryOptions.value = []
  spot.value = null
  try {
    const res = await fetch(`/api/expiries/${target.value}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const d = await res.json()
    expiryOptions.value = d.expiries || []
    if (expiryOptions.value.length && !expiryOptions.value.includes(expiry.value)) expiry.value = expiryOptions.value[0]
  } catch (e) {
    marketError.value = `到期日列表获取失败：${e.message}`
  }
}

async function fetchContracts() {
  if (!expiry.value) return
  contractsLoading.value = true
  marketError.value = ''
  try {
    const res = await fetch(`/api/strategy/market/${target.value}?expiry=${expiry.value}`)
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || `HTTP ${res.status}`)
    }
    const d = await res.json()
    contracts.value = d.snapshots?.rows || []
    // 参考价：优先实时现货，缺失回落 K 线缓存（stale）
    const ref = d.reference_spot || {}
    if (ref.price != null) {
      spot.value = ref.price
      spotSource.value = { stale: ref.stale === true, marketTime: ref.market_time || null }
    }
    // 新到期日的合约全集：清掉旧选择
    presetSelections.value = []
    for (const leg of legs) if (!contracts.value.some(c => c.contract_id === leg.contractId)) leg.contractId = ''
    // 深链预填优先于默认自动配对：按信号规格解析真实合约（方向/行权价/腿数全部落位）
    // 只有成功解析出合约才消耗规格（到期日回落会触发两次 fetch，首次空列表不浪费预填）
    if (pendingLegSpecs) {
      const resolved = resolveLegSpecs(pendingLegSpecs, contracts.value, spot.value)
      if (resolved.some(r => r.contractId)) {
        legs.forEach((l, i) => {
          if (!resolved[i]) return
          l.side = resolved[i].side
          if (resolved[i].contractId) l.contractId = resolved[i].contractId
        })
        pendingLegSpecs = null
      }
    }
    // 尚无任何选择 → 自动按参考价配对，直接出图
    if (!activeLegs.value.some(l => l.contractId)) autoAssign()
  } catch (e) {
    marketError.value = `合约报价获取失败：${e.message}`
    contracts.value = []
  } finally {
    contractsLoading.value = false
  }
}

watch(expiry, () => { fetchContracts() })
onMounted(() => {
  // 深链支持（来自机会筛选页）：
  //   基础：/strategy?code=510050&expiry=20261125
  //   预填：&legs=sell:call:2.85,buy:call:out  → 自由组合模式按规格预填腿（side:type:strikeSpec）
  //   说明：&note=...  → 顶部提示条（如日历价差跨到期日的降级说明）
  // 先设 target/expiry 再拉到期日列表；到期日不在列表内会被 fetchExpiries 回落到最近值
  const qc = String(route.query.code || '')
  if (targetOptions.some(t => t.code === qc)) target.value = qc
  const qe = String(route.query.expiry || '')
  if (/^\d{8}$/.test(qe)) expiry.value = qe
  const ql = String(route.query.legs || '')
  if (ql) {
    const specs = ql.split(',').map(seg => {
      const [side, type, strikeSpec] = seg.split(':')
      return { side, type, strikeSpec: String(strikeSpec || 'near') }
    }).filter(x => (x.side === 'buy' || x.side === 'sell') && (x.type === 'call' || x.type === 'put'))
    if (specs.length) {
      pendingLegSpecs = specs
      // 切到自由组合模式并按腿数重建空腿，等 fetchContracts 拿到合约列表后填入
      presetMode.value = FREE_MODE
      legs.splice(0, legs.length, ...specs.map(() => ({ side: 'buy', units: 1, contractId: '' })))
    }
  }
  const qn = String(route.query.note || '')
  if (qn) deepNote.value = qn
  fetchExpiries()
})

const availableContracts = computed(() => contracts.value)

function selectedContract(leg) {
  return contracts.value.find(c => c.contract_id === leg.contractId) || null
}

function addLeg() {
  legs.push({ side: 'buy', units: 1, contractId: '' })
}

function removeLeg(i) {
  if (legs.length <= 1) return
  legs.splice(i, 1)
}

function onUnitsInput(leg, event) {
  leg.units = Math.max(1, Number(event.target.value) || 1)
}

const allUsable = computed(() =>
  activeLegs.value.length > 0 && activeLegs.value.every(leg => Number.isFinite(selectedContract(leg)?.last_price))
)

function legNetCost(leg) {
  const c = selectedContract(leg)
  if (!c || !Number.isFinite(c.last_price)) return null
  const sign = leg.side === 'buy' ? 1 : -1
  // 合约单位缺失时与传给引擎的 multiplier 保持同一兜底（10000），否则表格净支出与盈亏图会矛盾
  return sign * leg.units * c.last_price * (c.contract_unit || 10000)
}

const totalEntryCost = computed(() => {
  if (!allUsable.value) return null
  return activeLegs.value.reduce((sum, leg) => sum + legNetCost(leg), 0)
})

const result = computed(() => {
  if (!activeLegs.value.length || !allUsable.value) return null
  const built = activeLegs.value.map(leg => {
    const c = selectedContract(leg)
    const sign = leg.side === 'buy' ? leg.units : -leg.units
    return { type: c.option_type, units: sign, strike: c.strike, premium: c.last_price, multiplier: c.contract_unit || 10000 }
  })
  try {
    return buildCustomStrategy(built)
  } catch (e) {
    return null
  }
})

const breakEvenText = computed(() => {
  const r = result.value
  if (!r) return ''
  const points = (r.breakEven?.points || []).map(x => `S = ${fmt(x, 4)}`)
  const intervals = (r.breakEven?.intervals || []).map(([lo, hi]) =>
    hi === Infinity ? `S ≥ ${fmt(lo, 4)}（整段零盈亏）` : `${fmt(lo, 4)} ≤ S ≤ ${fmt(hi, 4)}（整段零盈亏）`
  )
  return [...points, ...intervals].join('；') || '无盈亏平衡点（S ≥ 0 域内）'
})

const chart = computed(() => {
  const r = result.value
  if (!r) return null
  const knots = r.knots || []
  const refSpot = spot.value
  const fallback = knots[Math.floor(knots.length / 2)] ?? 0 // 奇数长度时 length/2 是小数索引 → undefined
  const base = refSpot ?? (knots.length ? knots.reduce((a, b) => Math.abs(a - fallback) < Math.abs(b - fallback) ? a : b) : 0)
  const lo = Math.max(0, (Math.min(...knots) || 0) * 0.6)
  const hi = Math.max(base * 1.5, (Math.max(...knots) || 0) * 1.5, base * 1.2)
  const maxS = hi
  const step = Math.max((hi - lo) / 80, 0.01)
  const xs = []
  for (let s = lo; s <= hi + step / 2; s += step) xs.push(Number(s.toFixed(6)))
  const ys = xs.map(s => customStrategyAt(r, s) ?? 0)
  const low = Math.min(0, ...ys), high = Math.max(0, ...ys)
  const pad = Math.max((high - low) * 0.08, 1)
  const minY = low - pad, maxY = high + pad
  const x = s => 88 + (s - lo) / (maxS - lo) * 762
  const y = p => 300 - (p - minY) / (maxY - minY) * 275
  const xTicks = Array.from({ length: 5 }, (_, i) => ({ value: lo + (maxS - lo) * i / 4, x: x(lo + (maxS - lo) * i / 4) }))
  const yTicks = Array.from({ length: 5 }, (_, i) => { const value = minY + (maxY - minY) * i / 4; return { value, y: y(value) } })
  return {
    lo, maxS, x, y, zeroY: y(0),
    points: xs.map((s, i) => `${x(s).toFixed(1)},${y(ys[i]).toFixed(1)}`).join(' '),
    roots: (r.breakEven?.points || []).filter(p => p >= lo && p <= hi),
    xTicks, yTicks,
  }
})

const probePosition = ref(500)
const probe = computed(() => {
  const r = result.value
  const c = chart.value
  if (!r || !c) return { spot: 0, pnl: null }
  const s = c.lo + (c.maxS - c.lo) * Number(probePosition.value) / 1000
  return { spot: s, pnl: customStrategyAt(r, s) }
})
const probePct = computed(() => {
  const p = probe.value, t = totalEntryCost.value
  if (p.pnl == null || !t) return '—'
  return `${((p.pnl / Math.abs(t)) * 100).toFixed(1)}%`
})

function fmt(v, d = 4) {
  if (v == null || Number.isNaN(v)) return '—'
  if (v === Infinity) return '∞'
  if (v === -Infinity) return '−∞'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: d })
}
function shortName(n) { return (n || '').split('（')[0] }
function expiryLabel(e) {
  if (!e || e.length < 6) return e
  const m = parseInt(e.slice(4, 6))
  const d = parseInt(e.slice(6, 8))
  return d ? `${m}月${d}日` : `${m}月`
}
function fmtMarketTime(t) {
  if (!t || t.length < 12) return t || ''
  return `${t.slice(4,6)}-${t.slice(6,8)} ${t.slice(8,10)}:${t.slice(10,12)}:${t.slice(12,14)}`
}
</script>

<style scoped>
.strategy-page { display: grid; gap: 16px; }
.strategy-layout { display: grid; grid-template-columns: 420px minmax(0, 1fr); gap: 20px; align-items: start; }
.strategy-side { display: grid; gap: 16px; position: sticky; top: 12px; }
.strategy-main { display: grid; gap: 16px; min-width: 0; }
h1 { font-size: 23px; } h2 { font-size: 15px; margin: 0 0 10px; }
p { line-height: 1.7; } .note { color: var(--text-dim); font-size: 12px; font-weight: normal; }
.assumptions { border-left: 3px solid var(--accent); padding: 12px 16px; background: var(--bg-elevated); border-radius: 0 var(--radius) var(--radius) 0; font-size: 13px; color: var(--text-dim); }
.deep-note {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  border: 1px solid var(--accent); background: var(--accent-glow); border-radius: var(--radius);
  padding: 11px 14px; font-size: 13px; color: var(--text); line-height: 1.6;
}
.dn-badge {
  flex: none; background: var(--accent); color: var(--accent-ink, #0a0c10);
  font-size: 11px; font-weight: 800; border-radius: var(--pill); padding: 2px 10px;
}
.target-card, .legs-card, .result-card, .metrics article { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; background: var(--bg); min-width: 0; box-shadow: var(--shadow); }
.step-card { display: grid; gap: 12px; }
.step-h { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.step-h h2 { margin-bottom: 0; }
h2 { display: flex; align-items: center; gap: 8px; }
.step-no {
  display: inline-flex; align-items: center; justify-content: center; flex: none;
  width: 20px; height: 20px; border-radius: 50%;
  background: var(--accent); color: var(--accent-ink, #0a0c10);
  font-size: 12px; font-weight: 800;
}
.auto-btn {
  flex: none; background: var(--bg-elevated); border: 1px solid var(--accent);
  color: var(--accent-ink); border-radius: 6px; padding: 5px 12px;
  font-size: 12px; font-weight: 700; cursor: pointer; transition: background .12s;
}
.auto-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--accent) 16%, var(--bg)); }
.auto-btn:disabled { opacity: .4; cursor: not-allowed; }
.target-pickers { display: grid; gap: 12px; grid-template-columns: 1fr; }
label { display: flex; flex-direction: column; gap: 7px; color: var(--text-dim); font-size: 13px; }
input, select { min-width: 0; width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 9px; font: inherit; }
input:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.spot-line { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; font-size: 13px; color: var(--text-dim); }
.spot-line > span:first-child { color: var(--text); font-weight: 600; }
.stale-tag { color: var(--warn); border: 1px solid var(--warn); border-radius: 4px; padding: 1px 6px; font-size: 11px; }
.fresh-tag { color: var(--ok); border: 1px solid var(--ok); border-radius: 4px; padding: 1px 6px; font-size: 11px; }
.preset-groups { display: grid; gap: 12px; }
.preset-group { display: grid; gap: 6px; }
.group-label { color: var(--text-dim); font-size: 12px; margin: 0; }
.preset-item {
  display: grid; gap: 4px; text-align: left; width: 100%;
  background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 12px; cursor: pointer; font: inherit; transition: border-color .12s, background .12s;
}
.preset-item:hover { border-color: var(--accent); }
.preset-item.active { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, var(--bg)); }
.pi-name { color: var(--text); font-weight: 600; font-size: 13.5px; }
.pi-desc { color: var(--text-dim); font-size: 12px; line-height: 1.5; }
.pi-legs { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
.pi-legs > span { font-size: 11px; padding: 1px 7px; border-radius: 4px; border: 1px solid var(--border); color: var(--text-dim); background: var(--bg); }
.pi-legs > span.leg-buy { color: var(--ok, #0a7a4d); border-color: var(--ok, #0a7a4d); }
.pi-legs > span.leg-sell { color: var(--err, #c0392b); border-color: var(--err, #c0392b); }
.leg-row { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-elevated); }
.leg-controls { display: grid; grid-template-columns: 1fr 1fr 80px; gap: 10px; }
.leg-side { flex-direction: row; align-items: center; gap: 6px; }
.leg-side input { width: auto; }
.leg-units { flex-direction: row; align-items: center; justify-content: space-between; gap: 6px; }
.leg-units input { width: 70px; }
.leg-remove { align-self: end; justify-self: end; background: none; border: 1px solid var(--err); color: var(--err); border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer; }
.leg-remove:disabled { opacity: .35; cursor: not-allowed; }
.leg-missing { color: var(--warn); }
.leg-add { align-self: start; background: none; border: 1px dashed var(--accent); color: var(--accent); border-radius: 6px; padding: 8px; font-size: 13px; cursor: pointer; }
.leg-locked { grid-template-columns: auto auto 1fr; align-items: center; }
.leg-side-static { color: var(--text); font-weight: 600; font-size: 13px; }
.leg-type-tag { color: var(--text-dim); font-size: 12px; border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px; white-space: nowrap; }
.leg-units-static { color: var(--text-dim); font-size: 12px; text-align: right; white-space: nowrap; }
.guide {
  border: 1px dashed var(--border); border-radius: var(--radius-lg);
  padding: 22px 20px; color: var(--text-dim); font-size: 13.5px;
  background: var(--bg-elevated); line-height: 1.7;
}
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metrics h2 { color: var(--text-muted); font-weight: 600; font-size: 12px; letter-spacing: .04em; }
.metrics strong { display: block; color: var(--accent-ink); font-size: 22px; font-family: var(--font-mono); font-weight: 800; overflow-wrap: anywhere; margin-top: 6px; }
.metrics strong.na { color: var(--text-dim); font-size: 15px; font-family: var(--font-sans); }
.metrics strong.unbounded { color: var(--warn); font-size: 17px; font-family: var(--font-sans); }
.metrics p { margin-top: 6px; font-size: 12px; color: var(--text-muted); }
.error { color: var(--err); border: 1px solid var(--err); padding: 14px; border-radius: 8px; }
.table-wrap { overflow-x: auto; margin-top: 12px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 11px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
thead th { font-size: 12px; color: var(--text-dim); }
.roots { color: var(--accent); font-variant-numeric: tabular-nums; margin-bottom: 8px; overflow-wrap: anywhere; }
svg { display: block; width: 100%; height: auto; margin: 12px 0; }
svg text { fill: var(--text-dim); font-size: 12px; }
.grid-line { stroke: var(--border); }
.zero-line { stroke: var(--text-dim); stroke-dasharray: 5 5; }
.payoff-line { fill: none; stroke: var(--accent-ink); stroke-width: 2.5; stroke-linejoin: round; }
.root-line { stroke: var(--warn); stroke-dasharray: 3 5; }
.probe-dot { fill: var(--text); stroke: var(--accent); stroke-width: 2; }
input[type=range] { accent-color: var(--accent); padding: 0; min-height: 36px; }
.scenario { margin: 8px 0; font-variant-numeric: tabular-nums; }
@media (max-width: 1100px) { .strategy-layout { grid-template-columns: minmax(0, 1fr); }.strategy-side { position: static; } }
@media (max-width: 1000px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .metrics { grid-template-columns: minmax(0, 1fr); } .target-card, .legs-card, .result-card, .metrics article { padding: 12px; } }
</style>
