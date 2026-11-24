<template>
  <section class="screener">
    <div class="page-head">
      <div>
        <div class="ph-kicker">SCREENER · 全链扫描</div>
        <h1>机会筛选</h1>
        <p class="ph-desc">三类信号 × 5 标的 × 全到期日，只扫剩余到期 ≥7 天的合约：微笑残差（LOO 删除残差 z≥2）、C-P IV 价差（偏离本到期日中位 ≥3pp）、期限倒挂（ATM IV 全段首末差 ≥2pp）。按「超阈值倍数」排序，一键进入策略模拟验证。顶部 IV 环境给出各标的整体水位，用于判断信号顺风还是逆风。</p>
      </div>
      <div class="ph-actions">
        <button class="scan-btn" @click="scan" :disabled="scanning">{{ scanning ? '扫描中…' : '↻ 重新扫描' }}</button>
      </div>
    </div>

    <div class="iv-env" v-if="ivEnvList.length">
      <div class="env-head">
        <span class="env-title">IV 环境</span>
        <span class="env-sub">{{ envSummaryText }}</span>
      </div>
      <div class="env-grid">
        <button
          v-for="e in ivEnvList" :key="e.code"
          class="env-card"
          :class="[e.level ? `lv-${e.level}` : 'lv-none', { off: !filters.targets.has(e.code) }]"
          :aria-pressed="filters.targets.has(e.code)"
          :title="envCardTip(e)" @click="toggleTarget(e.code)"
        >
          <span class="ec-top">
            <span class="ec-code">{{ e.code }}</span>
            <span class="ec-badge">{{ e.level ? ENV_LEVELS[e.level].label : '积累中' }}</span>
          </span>
          <span class="ec-main">
            <span class="ec-iv">{{ e.iv30 != null ? e.iv30.toFixed(1) : '--' }}<i>%</i></span>
            <span class="ec-lbl">IV30</span>
          </span>
          <span class="ec-bot">
            <span class="ec-vrp">VRP {{ signed(e.vrp) }}pp</span>
            <span class="ec-ivr">{{ e.ivr != null ? 'IVR ' + e.ivr.toFixed(0) : `IVR ${e.samples}/${e.minSamples}` }}</span>
          </span>
        </button>
      </div>
    </div>
    <p v-else-if="envError" class="env-fail">IV 水位不可用（{{ envError }}）：信号仍按自身阈值扫描，环境列显示 --</p>

    <div class="filter-card">
      <div class="toolbar">
        <span class="toolbar-label">信号</span>
        <button
          v-for="t in SIGNAL_TYPES" :key="t.id"
          class="type-chip" :class="[`tc-${t.id}`, { on: filters.types.has(t.id) }]"
          :title="t.desc" @click="toggleType(t.id)"
        >{{ t.label }}</button>
        <span class="toolbar-label gap-left">强度</span>
        <select v-model.number="filters.minStrength" class="strength-select" aria-label="最小信号强度">
          <option :value="1">≥ 1× 阈值</option>
          <option :value="1.5">≥ 1.5× 阈值</option>
          <option :value="2">≥ 2× 阈值</option>
        </select>
        <button
          v-if="hasEnv"
          class="type-chip favor" :class="{ on: filters.onlyFavorable, zero: !favorableCount }"
          title="只保留「信号方向与当前 IV 水位顺风」的条目：微笑残差在标的 IV 偏贵时卖出、偏便宜时买入。注意 C-P 与期限倒挂是两腿同持的相对价值结构、恒为中性，会被一并滤掉"
          @click="filters.onlyFavorable = !filters.onlyFavorable"
        >只看顺风<span v-if="favorableCount" class="favor-n">·{{ favorableCount }}</span></button>
        <span class="toolbar-info" v-if="summary && !scanning">
          覆盖 {{ summary.contracts }} 张合约 · 参扫 {{ summary.ivRows }} · 近月剔除 {{ summary.droppedDte }} 行 · 命中 {{ filtered.length }} 条
        </span>
      </div>
      <div class="toolbar">
        <span class="toolbar-label">标的</span>
        <button
          v-for="t in targets" :key="t.code"
          class="type-chip tgt" :class="{ on: filters.targets.has(t.code) }"
          @click="toggleTarget(t.code)"
        >{{ t.code }}</button>
      </div>
    </div>

    <div class="statusbar" :class="statusClass">
      <span class="status-dot"></span>
      <span class="status-text">{{ statusText }}</span>
      <span class="status-spot" v-if="scanTime && !scanning">扫描完成于 {{ scanTime }}</span>
    </div>

    <div v-if="error" class="unavailable">扫描失败：{{ error }}（可点右上角重新扫描重试）</div>

    <div v-if="filtered.length" class="table-card">
      <div class="scroll-hint" aria-hidden="true">← 表格可左右滑动查看全部列 →</div>
      <div class="table-wrap">
        <table class="sig-table">
          <thead>
            <tr>
              <th class="num">强度</th>
              <th class="num cost-col" title="往返价差成本占权利金 % / 信号幅度扣掉价差后的净额（pp）">价差/净额</th>
              <th>信号</th>
              <th>标的</th>
              <th class="num env-col" title="信号方向 × 标的整体 IV 水位的匹配度。只作标注，不改变信号阈值">环境</th>
              <th>到期日</th>
              <th class="num">行权价</th>
              <th>方向</th>
              <th class="num">IV</th>
              <th class="detail-col">详情</th>
              <th class="sug-col">建议策略</th>
              <th>时效</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(s, i) in filtered" :key="`${s.type}-${s.target_code}-${s.expiry}-${s.strike}-${s.option_code}-${i}`">
              <td class="num">
                <span class="strength" :class="{ hot: s.strength >= 2 }" :title="`本类强度分位 ${s.pct}%`">×{{ s.strength.toFixed(1) }}</span>
              </td>
              <td class="num cost-col">
                <template v-if="s.cost_pct != null">
                  <span
                    class="cost"
                    :class="{ wide: s.wide_spread }"
                    :title="`往返价差 ${s.cost_pct.toFixed(1)}% 权利金${s.wide_spread ? '（偏宽，成交会吃掉大半幅度）' : ''}，折合约 ${s.cost_pp != null ? s.cost_pp.toFixed(1) : '--'}pp IV`"
                  >{{ s.cost_pct.toFixed(1) }}%</span>
                  <span
                    v-if="s.net_pp != null"
                    class="net"
                    :class="s.net_pp > 0 ? 'pos' : 'neg'"
                    :title="`信号幅度 ${s.edge_pp.toFixed(1)}pp − 价差成本 ${s.cost_pp.toFixed(1)}pp = ${s.net_pp.toFixed(1)}pp`"
                  >{{ s.net_pp > 0 ? '净+' : '净' }}{{ s.net_pp.toFixed(1) }}pp</span>
                </template>
                <span v-else class="dim" title="数据源未返回买一/卖一，无法估算成交成本">--</span>
              </td>
              <td><span class="sig-tag" :class="`st-${s.type}`">{{ typeLabel(s.type) }}</span></td>
              <td class="mono">{{ s.target_code }}</td>
              <td class="num env-col">
                <span
                  class="env-tag"
                  :class="s.env_fit > 0 ? 'fav' : s.env_fit < 0 ? 'opp' : 'flat'"
                  :title="envTip(s)"
                >{{ envLabel(s) }}</span>
              </td>
              <td class="mono">{{ fmtExpiry(s.expiry) }}</td>
              <td class="num mono">{{ s.strike ?? '--' }}</td>
              <td>{{ typeSide(s.option_type) }}</td>
              <td class="num mono">{{ s.iv != null ? s.iv.toFixed(1) + '%' : '--' }}</td>
              <td class="detail-col">{{ s.detail }}</td>
              <td class="sug-col"><span class="sug-text">{{ s.suggestion }}</span></td>
              <td>
                <span v-if="s.market_ts" class="fresh" :class="{ stale: s.stale }" :title="`数据源行情时间 ${s.market_ts}（抓取时间不算行情时间）`">{{ fmtTime(s.market_ts) }}</span>
                <span v-else class="fresh" title="数据源未返回行情时间">--</span>
              </td>
              <td class="actions">
                <router-link
                  v-if="/^\d{8}$/.test(s.expiry)"
                  class="act act-strong"
                  :to="strategyTo(s)"
                >策略</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-else-if="!scanning && !error" class="empty">
      <div class="empty-title">当前过滤条件下没有信号</div>
      <div class="empty-detail">市场定价效率高时信号本来就稀少（这本身是信息）；可把强度阈值调回 1×、或放开被关掉的信号类型/标的再试<template v-if="filters.onlyFavorable">，或关掉「只看顺风」（顺风只筛微笑残差，C-P 与期限恒为中性会被一起滤掉）</template>。</div>
    </div>

    <div class="notes">
      <p><b>怎么读这些信号</b>：都是「偏离统计常态」的候选点，不是买卖指令——最终值不值得做，看「价差/净额」列：信号幅度盖不住成交成本时，这条信号只能当观察，不能当交易。</p>
      <p><b>「环境」列不是第四类信号</b>：三类信号都是同一时刻的<b>相对定价偏离</b>，用整体 IV 水位去改阈值会把「结构性套利」和「波动率贵贱」混成一件事，所以水位只回答另一个问题：这条信号指向的<b>方向</b>在当前环境下顺不顺风。微笑残差有明确方向（该腿偏贵→卖 / 偏便宜→买），标的 IV 高位时卖方向顺风、低位时买方向顺风；C-P 与期限倒挂是两腿同持的相对价值结构，水位对它们<b>恒为中性</b>（显示「中性」不是没算，是本来就不受影响）。判据自动降级：IVR（需 20 个交易日样本、252 日窗口）→ VRP ＝ IV30 − 20 日实际波动（1 天即可用）→ 都缺失则显示 --。</p>
      <p><b>价差/净额怎么算</b>：上行是<b>往返价差</b>＝各腿 (卖一−买一)/中间价 之和，占权利金 %（实测值，买进卖出各付半个价差，＞4% 标黄）；下行是<b>净额</b>＝信号幅度(pp) − 价差成本折算回 IV 点数后的余量。折算用 BS vega（每 1pp 的每份权利金增量），与信号幅度同为 pp，可直接比较；绿字＝幅度盖得住价差，灰字＝被价差吃掉。价差腿（如微笑建议的相邻行权价腿）、手续费与滑点未计入，所以净额偏乐观一档。</p>
      <p><b>时效列是数据源的行情时间，不是抓取时间</b>：显示 HH:MM，过期数据会标黄。五档（买一/卖一）拿不到时成本列显示 --，此时无法判断可成交性。</p>
      <p><b>结构性提醒</b>：C-P IV 价差全线为负、远月 IV 高于近月（contango）都是本市场的常态，本页只报偏离常态的点；科创系（588000/588080）流动性差、做市覆盖弱，信号天然更多，也更容易踩坑。</p>
      <p><b>近月整条链不参与扫描</b>：剩余到期不足 7 天的 ATM 合约 gamma 极高，IV 天然剧烈波动（实测曾占全部信号的 24%），会被误判成极端异常。本轮剔除 {{ summary?.droppedDte ?? 0 }} 行。</p>
      <p><b>微笑残差用 LOO 删除残差</b>：对每个点用其余所有行权价重新拟合曲线再量偏离，避免单点报价错误被曲线自我吸收（masking）而漏检。</p>
      <p><b>为什么没有「市价 vs 理论价」</b>：数据源给的是交易所参考价（单一波动率、不含 smile），对虚值合约系统性低估——实测某 put 链 IV 全程 23~24%，参考价却只有市价的 4%。它测的是模型误差而非定价错误，且「偏贵→卖出」会诱导裸卖虚值期权，已整体下线。</p>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { buildSignals, filterSignals, SIGNAL_TYPES, strategyDeepLink, ivEnvironment, ENV_LEVELS } from '../utils/screener.mjs'

const targets = [
  { code: '510050', name: '50ETF' },
  { code: '510300', name: '300ETF' },
  { code: '510500', name: '500ETF' },
  { code: '588000', name: '科创50ETF' },
  { code: '588080', name: '科创100ETF' },
]

const TYPE_LABEL = Object.fromEntries(SIGNAL_TYPES.map(t => [t.id, t.label]))

const scanning = ref(false)
const progress = ref(0)
const error = ref('')
const result = ref({ signals: [], summary: null })
const scanTime = ref('')
// IV 环境：raw 是 /api/ivstats 原始记录（喂给 buildSignals），list 是归一化后的展示数据
const ivEnvRaw = ref({})
const ivEnvList = ref([])
const envError = ref('')
let abortController = null

const filters = reactive({
  types: new Set(SIGNAL_TYPES.map(t => t.id)),
  targets: new Set(targets.map(t => t.code)),
  minStrength: 1,
  onlyFavorable: false,
})

function toggleType(id) {
  const next = new Set(filters.types)
  next.has(id) ? next.delete(id) : next.add(id)
  // 全关等同于全开（避免空视图歧义），这里允许全关并显示空态提示
  filters.types = next
}

function toggleTarget(code) {
  const next = new Set(filters.targets)
  next.has(code) ? next.delete(code) : next.add(code)
  filters.targets = next
}

const summary = computed(() => result.value.summary)

const filtered = computed(() => result.value.signals.length
  ? filterSignals(result.value.signals, filters)
  : [])

// ---- IV 环境（IVR / VRP）----
// 只作「这条信号顺不顺风」的标注，不参与信号生成，也不改任何阈值。
const hasEnv = computed(() => ivEnvList.value.some(e => e.level))
// 顺风条数：多数轮次只有 C-P / 期限信号（恒中性），按钮上直接给出数量，避免点了才发现是空的
const favorableCount = computed(() => result.value.signals.filter(s => s.env_fit > 0).length)

const envSummaryText = computed(() => {
  const n = ivEnvList.value.length
  if (!n) return ''
  const ivrN = ivEnvList.value.filter(e => e.basis === 'ivr').length
  if (ivrN === n) return '判据：IV Rank（252 日窗口，≥70 偏贵 / ≤30 偏便宜）'
  if (ivrN > 0) return `判据：${ivrN}/${n} 个标的已用 IV Rank，其余暂用 VRP`
  return '判据：VRP ＝ IV30 − 20 日实际波动，IVR 满 20 日后自动切换'
})

function signed(v, d = 1) { return v == null ? '--' : (v >= 0 ? '+' : '') + v.toFixed(d) }

function envCardTip(e) {
  const parts = []
  if (e.iv30 != null) parts.push(`IV30 ${e.iv30.toFixed(1)}%`)
  if (e.vrp != null) parts.push(`VRP ${signed(e.vrp)}pp`)
  if (e.ivr != null) parts.push(`IVR ${e.ivr.toFixed(0)}（IVP ${e.ivp ?? '--'}%）`)
  else parts.push(`IVR 采集中 ${e.samples}/${e.minSamples} 日`)
  const tail = e.level ? ENV_LEVELS[e.level].hint : '暂无可用的水位判据'
  return `${parts.join(' · ')}\n${tail}\n点击=切换该标的的信号显示`
}

function envLabel(s) {
  if (!s.env_level) return '--'
  if (s.env_fit > 0) return '顺风'
  if (s.env_fit < 0) return '逆风'
  return '中性'
}

function envTip(s) {
  const basis = s.env_basis === 'ivr' ? `IVR ${s.env_ivr?.toFixed(0)}` : `VRP ${signed(s.env_vrp)}pp`
  const dir = s.env_bias === 'sell' ? '偏卖波动率' : s.env_bias === 'buy' ? '偏买波动率' : '相对价值（两腿同持）'
  const verdict = s.env_fit > 0 ? '顺风' : s.env_fit < 0 ? '逆风' : '水位不构成买卖理由'
  const lvl = ({ high: '高位', mid: '常态', low: '低位' })[s.env_level] || '未知水位'
  return `该标的 ${lvl}（${basis}）· 信号方向：${dir} → ${verdict}`
}

async function loadIvEnv() {
  try {
    const res = await fetch('/api/ivstats', { headers: { Accept: 'application/json' } })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const payload = await res.json()
    const map = {}
    for (const t of (payload?.targets || [])) if (t?.target_code) map[t.target_code] = t
    ivEnvRaw.value = map
    ivEnvList.value = targets.map(t => ({ code: t.code, name: t.name, ...ivEnvironment(map[t.code]) }))
    envError.value = ''
  } catch (e) {
    // 环境块失败不影响扫描主链路：全部降级为 none，UI 显示占位
    ivEnvRaw.value = {}
    ivEnvList.value = []
    envError.value = e.message || 'IV 水位不可用'
  }
}

function typeLabel(id) { return TYPE_LABEL[id] || id }
function typeSide(t) { return t === 'call' ? '购' : t === 'put' ? '沽' : '--' }
function strategyTo(s) {
  const { legs, note } = strategyDeepLink(s)
  const query = { code: s.target_code, expiry: s.expiry, legs }
  if (note) query.note = note
  return { path: '/strategy', query }
}
function fmtExpiry(e) {
  const m = String(e).match(/^(\d{4})(\d{2})(\d{2})$/)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : (e || '--')
}
// 数据源行情时间（market_ts）→ HH:MM；只显示时间，完整值放 title
function fmtTime(ts) {
  const m = String(ts || '').match(/(\d{2}):(\d{2})/)
  return m ? `${m[1]}:${m[2]}` : '--'
}

const statusClass = computed(() => scanning.value ? 'loading' : (error.value ? 'unavailable' : (filtered.value.length ? 'ok' : 'stale')))
const statusText = computed(() => {
  if (scanning.value) return `扫描中 ${progress.value}/5 · ${targets[Math.min(progress.value, 4)].name}…`
  if (error.value) return '扫描未完成'
  return filtered.value.length ? `发现 ${filtered.value.length} 条候选信号` : '本轮未发现符合条件的信号'
})

function cleanup() {
  if (abortController) { abortController.abort(); abortController = null }
  scanning.value = false
}

async function scan() {
  cleanup()
  const ctrl = new AbortController()
  abortController = ctrl
  scanning.value = true
  error.value = ''
  progress.value = 0
  result.value = { signals: [], summary: null }
  const sig = ctrl.signal

  const collected = []
  try {
    await Promise.all([loadIvEnv(), ...targets.map(async (t) => {
      try {
        const res = await fetch(`/api/quotes/${t.code}`, { signal: sig, headers: { Accept: 'application/json' } })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const payload = await res.json()
        if (sig.aborted) return
        const rows = Array.isArray(payload?.rows) ? payload.rows : []
        // 现价取行内 spot（同一 payload 内一致），缺失则置 null（微笑/期限信号自动跳过）
        const spot = rows.map(r => Number(r?.spot?.price)).find(v => Number.isFinite(v) && v > 0) ?? null
        collected.push({ code: t.code, name: t.name, spot, rows })
      } catch (e) {
        if (sig.aborted || e.name === 'AbortError') return
        // 单个标的失败不拖垮整体：以空数据参与扫描
        collected.push({ code: t.code, name: t.name, spot: null, rows: [] })
      } finally {
        if (!sig.aborted) progress.value++
      }
    })])
    if (sig.aborted) return
    result.value = buildSignals(collected, { ivEnv: ivEnvRaw.value })
    scanTime.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    if (!collected.some(c => c.rows.length)) {
      error.value = '5 个标的行情均为空（数据源可能暂时不可用）'
    }
  } catch (e) {
    if (!sig.aborted) error.value = e.message || '扫描失败'
  } finally {
    if (!sig.aborted) scanning.value = false
  }
}

onMounted(scan)
onUnmounted(cleanup)
</script>

<style scoped>
.scan-btn {
  border: 1px solid var(--border); background: var(--bg); color: var(--text);
  border-radius: var(--pill); padding: 8px 16px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: border-color .15s, background .15s;
}
.scan-btn:hover:not(:disabled) { border-color: var(--accent); background: var(--bg-hover); }
.scan-btn:disabled { opacity: .55; cursor: not-allowed; }

.type-chip {
  border: 1px solid var(--border); background: var(--bg); color: var(--text-dim);
  border-radius: var(--pill); padding: 6px 14px; font-size: 12.5px; font-weight: 600;
  cursor: pointer; transition: all .15s;
}
.type-chip:hover { border-color: var(--text-muted); }
.type-chip.on { background: var(--text); color: var(--bg); border-color: var(--text); }
.type-chip.tc-smile.on { background: #7c5cf0; border-color: #7c5cf0; color: #fff; }
.type-chip.tc-cp.on { background: #0e86d8; border-color: #0e86d8; color: #fff; }
.type-chip.tc-term.on { background: #d97706; border-color: #d97706; color: #fff; }
.type-chip.tgt.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }

.gap-left { margin-left: 12px; }
.strength-select {
  border: 1px solid var(--border); background: var(--bg); color: var(--text);
  border-radius: var(--radius); padding: 6px 10px; font-size: 12.5px; cursor: pointer;
}

.sig-table { min-width: 1310px; width: 100%; }   /* 桌面铺满容器；窄屏由 min-width 撑出横滚 */

.scroll-hint {
  display: none;
  font-size: 11.5px; color: var(--text-muted); text-align: center;
  padding: 7px 0 9px; letter-spacing: .04em;
  border-bottom: 1px dashed var(--border);
}
@media (max-width: 768px) {
  .scroll-hint { display: block; }
  .sig-table .detail-col { min-width: 200px; max-width: 260px; }
}
.sig-table th, .sig-table td { white-space: nowrap; padding: 9px 7px; }
.sig-table th:first-child, .sig-table td:first-child { padding-left: 14px; }
.sig-table th:last-child, .sig-table td:last-child { padding-right: 14px; }
/* 强度 / 价差·净额 是两列连续数字，靠左细线分开，避免读成一串 */
.sig-table th.cost-col, .sig-table td.cost-col { border-left: 1px solid var(--border); padding-left: 12px; }
.sig-table .detail-col { white-space: normal; min-width: 260px; color: var(--text-dim); font-size: 12.5px; }
.sig-table .sug-col { white-space: normal; min-width: 220px; font-size: 12.5px; }
.sug-text {
  display: inline-block; padding: 3px 10px; border-radius: var(--radius);
  background: var(--accent-glow); color: var(--text); line-height: 1.55;
}

.strength { font-family: var(--font-mono); font-weight: 700; }
.strength.hot { color: var(--err); }
.mono { font-family: var(--font-mono); }

/* 价差/净额：成本在上、净额在下；净额 >0（幅度盖过价差）才点亮 */
.sig-table th.cost-col, .sig-table td.cost-col { min-width: 96px; }
.cost-col { line-height: 1.25; }
.cost-col .cost { display: block; font-family: var(--font-mono); font-size: 12px; color: var(--text-dim); }
.cost-col .cost.wide { color: var(--warn); font-weight: 700; }
.cost-col .net { display: block; font-family: var(--font-mono); font-size: 11.5px; font-weight: 700; }
.cost-col .net.pos { color: var(--ok); }
.cost-col .net.neg { color: var(--text-muted); }
.cost-col .dim { color: var(--text-muted); }

.sig-tag {
  display: inline-block; font-size: 11px; font-weight: 700;
  padding: 2px 9px; border-radius: var(--pill); color: #fff;
}
.st-smile { background: #7c5cf0; }
.st-cp { background: #0e86d8; }
.st-term { background: #d97706; }

.fresh { font-size: 11.5px; color: var(--text-muted); }
.fresh.stale { color: var(--warn); font-weight: 700; }

.actions { display: flex; gap: 6px; }
.act {
  display: inline-block; border: 1px solid var(--border); border-radius: var(--pill);
  padding: 3px 10px; font-size: 12px; color: var(--text-dim); text-decoration: none;
  transition: all .15s;
}
.act:hover { border-color: var(--accent); color: var(--text); }
.act-strong { border-color: var(--accent); color: var(--text); font-weight: 700; }
.act-strong:hover { background: var(--accent); color: var(--accent-ink); }

/* ---- IV 环境条 ---- */
.iv-env {
  margin-bottom: 14px; padding: 14px 16px;
  border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg-panel);
}
.env-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.env-title { font-size: 13px; font-weight: 700; }
.env-sub { font-size: 11.5px; color: var(--text-muted); }
.env-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }

.env-card {
  display: flex; flex-direction: column; gap: 4px; text-align: left;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg); cursor: pointer; transition: all .15s; font: inherit;
}
.env-card:hover { border-color: var(--text-muted); }
.env-card.off { opacity: .42; }
.ec-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.ec-code { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-dim); }
.ec-badge {
  font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: var(--pill);
  background: var(--bg-hover); color: var(--text-muted);
}
.ec-main { display: flex; align-items: baseline; gap: 5px; }
.ec-iv { font-family: var(--font-mono); font-size: 19px; font-weight: 700; line-height: 1.1; }
.ec-iv i { font-style: normal; font-size: 11px; font-weight: 500; color: var(--text-muted); margin-left: 1px; }
.ec-lbl { font-size: 10px; color: var(--text-muted); }
.ec-bot {
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
  font-size: 10.5px; color: var(--text-muted); font-family: var(--font-mono);
  flex-wrap: wrap;   /* 窄卡时整体折行，但不把「VRP」和数值拆开 */
}
.ec-vrp, .ec-ivr { white-space: nowrap; }

/* 水位配色：高位=琥珀（卖方环境）、低位=蓝（买方环境）、无判据=灰 */
.lv-high { border-color: rgba(232,160,18,.45); background: var(--warn-dim); }
.lv-high .ec-badge { background: var(--warn); color: var(--accent-text); }
.lv-high .ec-iv { color: #a56a00; }
.lv-low { border-color: rgba(37,99,235,.32); background: rgba(37,99,235,.06); }
.lv-low .ec-badge { background: #2563eb; color: #fff; }
.lv-low .ec-iv { color: #1d4ed8; }
.lv-none .ec-iv { color: var(--text-muted); }

.env-fail {
  margin: 0 0 14px; padding: 10px 14px; font-size: 12.5px; color: var(--text-muted);
  border: 1px dashed var(--border); border-radius: var(--radius);
}

/* ---- 表格「环境」列 ---- */
.sig-table th.env-col, .sig-table td.env-col { min-width: 58px; }
.env-tag { font-size: 11.5px; font-weight: 700; color: var(--text-muted); }
.env-tag.fav { color: var(--ok); }
.env-tag.opp { color: var(--warn); }

.type-chip.favor.on { background: var(--accent-ink); border-color: var(--accent-ink); color: #fff; }
.type-chip.favor.zero:not(.on) { opacity: .55; }
.favor-n { font-family: var(--font-mono); font-weight: 700; margin-left: 3px; }

.notes {
  margin-top: 16px; padding: 14px 18px;
  border: 1px dashed var(--border); border-radius: var(--radius-lg);
  font-size: 12.5px; color: var(--text-muted); line-height: 1.75;
}
.notes p { margin: 0 0 6px; }
.notes p:last-child { margin-bottom: 0; }
.notes b { color: var(--text-dim); }

@media (max-width: 768px) {
  .iv-env { padding: 12px 13px; }
  .env-head { margin-bottom: 10px; }
  /* 移动端不堆成三行占屏，改为横滑卡片，一屏看 2 个多一点 */
  .env-grid { display: flex; gap: 8px; overflow-x: auto; scroll-snap-type: x mandatory; padding-bottom: 2px; }
  .env-card { flex: 0 0 154px; scroll-snap-align: start; }
}
</style>
