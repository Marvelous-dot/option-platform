<template>
  <section class="screener">
    <div class="page-head">
      <div>
        <div class="ph-kicker">SCREENER · 全链扫描</div>
        <h1>机会筛选</h1>
        <p class="ph-desc">四类信号 × 5 标的 × 全到期日：微笑残差（LOO 删除残差 z≥2）、C-P IV 价差（偏离自身结构 ≥3pp）、期限倒挂（近月 ATM 高出远月 ≥2pp）、市价偏离理论价（≥15% 且流动性过滤）。按异常强度排序，一键进入合约详情或策略模拟验证。</p>
      </div>
      <div class="ph-actions">
        <button class="scan-btn" @click="scan" :disabled="scanning">{{ scanning ? '扫描中…' : '↻ 重新扫描' }}</button>
      </div>
    </div>

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
        <span class="toolbar-info" v-if="summary && !scanning">
          覆盖 {{ summary.contracts }} 张合约 · 有效 IV {{ summary.ivRows }} · 命中 {{ filtered.length }} 条
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
              <th>信号</th>
              <th>标的</th>
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
                <span class="strength" :class="{ hot: s.strength >= 2 }">×{{ s.strength.toFixed(1) }}</span>
              </td>
              <td><span class="sig-tag" :class="`st-${s.type}`">{{ typeLabel(s.type) }}</span></td>
              <td class="mono">{{ s.target_code }}</td>
              <td class="mono">{{ fmtExpiry(s.expiry) }}</td>
              <td class="num mono">{{ s.strike ?? '--' }}</td>
              <td>{{ typeSide(s.option_type) }}</td>
              <td class="num mono">{{ s.iv != null ? s.iv.toFixed(1) + '%' : '--' }}</td>
              <td class="detail-col">{{ s.detail }}</td>
              <td class="sug-col"><span class="sug-text">{{ s.suggestion }}</span></td>
              <td>
                <span class="fresh" :class="{ stale: s.stale }">{{ s.stale ? 'stale' : 'fresh' }}</span>
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
      <div class="empty-detail">市场定价效率高时信号本来就稀少（这本身是信息）；可把强度阈值调回 1×、或放开被关掉的信号类型/标的再试。</div>
    </div>

    <div class="notes">
      <p><b>怎么读这些信号</b>：信号都是「偏离统计常态」的候选点，不是买卖指令——每一条都应当结合成交量、买卖价差和自身持仓去策略模拟页验证后再动作。</p>
      <p><b>结构性提醒</b>：C-P IV 价差全线为负、远月 IV 高于近月（contango）都是本市场的常态，本页只报"偏离自身结构"的点；科创系（588000/588080）流动性差、做市覆盖弱，信号天然更多，也更容易踩坑，务必复核 volume。</p>
      <p><b>微笑残差采用 LOO 删除残差</b>：对每个点用"其余所有行权价"重新拟合微笑曲线再量偏离，避免单点报价错误被拟合曲线自我吸收（masking）而漏检。</p>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { buildSignals, filterSignals, SIGNAL_TYPES, strategyDeepLink } from '../utils/screener.mjs'

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
let abortController = null

const filters = reactive({
  types: new Set(SIGNAL_TYPES.map(t => t.id)),
  targets: new Set(targets.map(t => t.code)),
  minStrength: 1,
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
    await Promise.all(targets.map(async (t) => {
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
    }))
    if (sig.aborted) return
    result.value = buildSignals(collected)
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
.type-chip.tc-theory.on { background: #0d9668; border-color: #0d9668; color: #fff; }
.type-chip.tgt.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }

.gap-left { margin-left: 12px; }
.strength-select {
  border: 1px solid var(--border); background: var(--bg); color: var(--text);
  border-radius: var(--radius); padding: 6px 10px; font-size: 12.5px; cursor: pointer;
}

.sig-table { min-width: 1160px; width: 100%; }   /* 桌面铺满容器；窄屏由 min-width 撑出横滚 */

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
.sig-table th, .sig-table td { white-space: nowrap; }
.sig-table .detail-col { white-space: normal; min-width: 260px; color: var(--text-dim); font-size: 12.5px; }
.sig-table .sug-col { white-space: normal; min-width: 220px; font-size: 12.5px; }
.sug-text {
  display: inline-block; padding: 3px 10px; border-radius: var(--radius);
  background: var(--accent-glow); color: var(--text); line-height: 1.55;
}

.strength { font-family: var(--font-mono); font-weight: 700; }
.strength.hot { color: var(--err); }
.mono { font-family: var(--font-mono); }

.sig-tag {
  display: inline-block; font-size: 11px; font-weight: 700;
  padding: 2px 9px; border-radius: var(--pill); color: #fff;
}
.st-smile { background: #7c5cf0; }
.st-cp { background: #0e86d8; }
.st-term { background: #d97706; }
.st-theory { background: #0d9668; }

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

.notes {
  margin-top: 16px; padding: 14px 18px;
  border: 1px dashed var(--border); border-radius: var(--radius-lg);
  font-size: 12.5px; color: var(--text-muted); line-height: 1.75;
}
.notes p { margin: 0 0 6px; }
.notes p:last-child { margin-bottom: 0; }
.notes b { color: var(--text-dim); }
</style>
