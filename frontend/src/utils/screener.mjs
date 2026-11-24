// screener.mjs — 机会筛选：四类信号纯前端扫描（零后端依赖）
// 数据源：/api/quotes/{code} 全到期日快照（新浪 IV/理论价 + 报价），与波动率页同口径。
//
// 信号 ① 微笑残差：同一(标的,到期,沽购)内，IV 对 moneyness 做二次最小二乘拟合，
//          残差用稳健 σ（1.4826×MAD，下限 0.8pp 防 z 爆表），|z| ≥ 2 视为单点异常。
// 信号 ② C-P IV 价差：同行权价 Call−Put IV 差，偏离本到期日中位数 ≥ 3pp。
//          （C−P 全线为负是结构性常态，只报"偏离自身结构"的点，避免满屏误报。）
// 信号 ③ 期限倒挂：ATM IV 全段斜率，最早到期高出最晚到期 ≥ 2pp。
//          （contango 是常态，倒挂才是异常；只比相邻到期日会把一段连续倒挂拆成多条。）
//
// ★ 已下线「市价 vs 理论价」：数据源 theory_price 是新浪的「理论价值」（交易所参考价），
//   按简化模型计算、不含 smile，对虚值合约系统性低估。实测 510300 十二月 put K3.7：
//   市价 0.0138 vs 理论价 0.0005（偏差 2660%），而该链 IV 全程稳定在 24.4%→23.4%。
//   偏差来自模型假设波动率远低于链上 IV，不是市场定价错误；且"偏贵→卖出"的建议会
//   诱导裸卖虚值期权，正是尾部风险最大的位置。该信号无独立信息量，已整体移除。
//
// ★ 所有信号先按剩余到期天数过滤（DTE_MIN）：2 天期 ATM 的 gamma 极高、IV 天然剧烈波动，
//   会被误判成极端异常（实测曾占全部信号的 24%）。
//
// ★ 成本口径（cost_pct / cost_pp / net_pp）：信号强度只有和成交成本同单位才有意义。
//   cost_pct = 各腿往返价差占权利金 %（实测：Σ(卖一−买一)/中间价）；
//   cost_pp  = 同一条价差折回 IV 点数（价差元/份 ÷ BS vega 元/份/pp）；
//   net_pp   = 信号幅度(pp) − cost_pp(pp)，>0 才谈得上可执行。
//   折算必须用 BS vega：ATM 近似 0.4·S·√T 在虚值腿上会高估一个量级（实测把净额算成 +869%）。
//   价差腿（如 smile 建议的相邻行权价腿）、手续费、滑点均未计入，故 net_pp 偏乐观。
//
// ★ IV 环境（env_level / env_basis / env_bias / env_fit）：接 /api/ivstats 的 IVR 与 VRP。
//   它不是第四类信号，也不改任何阈值——水位回答的是「这条信号指向的方向，现在顺不顺风」：
//     · 微笑残差有明确方向（偏贵→卖 / 偏便宜→买），水位高时卖方顺风、低时买方差顺风；
//     · C-P 与期限倒挂是相对价值结构，两腿同持，整体水位对它们中性（env_fit 恒 0）。
//   判据自动降级：IVR（需 20 交易日样本）→ VRP=IV30−RV20（1 天即可用）→ none（不臆造）。

const IV_FLOOR = 2               // 有效 IV 下限（%），与 3D 曲面同口径剔除坏点
const SMILE_Z = 2                // 信号①阈值（稳健 z）
const CP_DIFF = 3                // 信号②阈值（pp，偏离自身结构）
const TERM_INV = 2               // 信号③阈值（pp，首末到期 ATM IV 差）
const SIGMA_FLOOR = 0.8          // 微笑拟合稳健 σ 下限（pp）：真实报价噪声量级，防 z 爆表
const MIN_FIT_POINTS = 7         // LOO 扫描最少点数（去 1 后仍需 ≥6 拟合二次）
const Z_CAP = 10                 // z 上限：σ 兜底下限时防 z 失真爆表
const MIN_CP_PAIRS = 4           // C-P 价差最少配对数，否则中位数不可信
const MONEYNESS_MAX = 0.10       // 微笑/C-P 只扫 |m|≤10% 平值区：翼部报价稀薄是结构性噪声源
const DTE_MIN = 7                // 最短剩余到期天数：近月 gamma 噪声区整体不参与扫描
const COST_WIDE = 4              // 往返价差 >4% 权利金 → 标「宽」（成交成本吃掉大半信号）

// ---- IV 环境（标的整体水位）----
// 注意：IVR/VRP 不参与信号生成。三类信号的本质都是「同一时刻的相对定价偏离」，
// 用整体水位去改阈值会把「结构性套利」和「波动率贵贱」混成一件事。
// 水位只回答另一个问题：这条信号指向的波动率方向，在当前环境下是顺风还是逆风。
const IVR_HIGH = 70              // IV Rank ≥70 → 期权整体偏贵（卖方环境）
const IVR_LOW = 30               // IV Rank ≤30 → 期权整体偏便宜（买方环境）
const VRP_HIGH = 3               // IV30 − RV20 ≥ 3pp → 隐含高于实际波动，卖方有溢价可收
const VRP_LOW = -3               // ≤ −3pp → 隐含低于实际波动，买方概率赔率占优

const num = v => (v == null ? null : (Number.isFinite(Number(v)) ? Number(v) : null))

export const SIGNAL_TYPES = [
  { id: 'smile', label: '微笑残差', short: '微', desc: '单点 IV 偏离同类二次拟合曲线 ≥2σ' },
  { id: 'cp', label: 'C-P 价差', short: 'CP', desc: '同行权价 Call−Put IV 差偏离本到期日中位数 ≥3pp' },
  { id: 'term', label: '期限倒挂', short: '期', desc: 'ATM IV 全段斜率：最早到期高出最晚到期 ≥2pp' },
]

// 剩余到期天数（中国时区日界）。无法解析的 expiry 返回 null，调用方应剔除。
export function daysToExpiry(expiry, now = new Date()) {
  const s = String(expiry || '')
  if (!/^\d{8}$/.test(s)) return null
  const target = Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8))
  const t = now instanceof Date ? now : new Date(now)
  if (Number.isNaN(t.getTime())) return null
  const cst = new Date(t.getTime() + 8 * 3600 * 1000)
  const today = Date.UTC(cst.getUTCFullYear(), cst.getUTCMonth(), cst.getUTCDate())
  return Math.round((target - today) / 86400000)
}

function median(arr) {
  const a = arr.filter(Number.isFinite).sort((x, y) => x - y)
  if (!a.length) return null
  const mid = a.length >> 1
  return a.length % 2 ? a[mid] : (a[mid - 1] + a[mid]) / 2
}

// ---- IV 环境：把 /api/ivstats 的单标的记录归一成 high / mid / low ----
// 两级判据，自动降级：
//   ① IVR（IV Rank）—— 需要 20 个交易日样本，最能代表「相对自身历史贵不贵」；
//   ② VRP = IV30 − RV20 —— 只需当天与 20 日 K 线，积累期内即可用。
// 两者都必须有，否则整块降级为 none（不臆造水位）。
export const ENV_LEVELS = {
  high: { label: '偏贵', hint: 'IV 处于自身历史高位 / 明显高于实际波动，卖方有溢价' },
  mid: { label: '中性', hint: 'IV 处于常态区间，水位不构成买卖理由' },
  low: { label: '偏便宜', hint: 'IV 处于自身历史低位 / 低于实际波动，买方赔率占优' },
}

export function ivEnvironment(stat) {
  const out = {
    level: null, basis: 'none',
    iv30: null, ivr: null, ivp: null, vrp: null,
    samples: 0, minSamples: 20,
  }
  if (!stat || typeof stat !== 'object') return out
  out.iv30 = num(stat.iv30)
  out.ivr = num(stat.ivr)
  out.ivp = num(stat.ivp)
  out.vrp = num(stat.vrp)
  out.samples = Number.isFinite(stat.samples) ? stat.samples : 0
  out.minSamples = Number.isFinite(stat.min_samples) ? stat.min_samples : 20

  // IVR 只在样本达标时才由后端输出，因此「有值即可用」，不依赖 status 文案
  if (out.ivr !== null) {
    out.basis = 'ivr'
    out.level = out.ivr >= IVR_HIGH ? 'high' : out.ivr <= IVR_LOW ? 'low' : 'mid'
  } else if (out.vrp !== null) {
    out.basis = 'vrp'
    out.level = out.vrp >= VRP_HIGH ? 'high' : out.vrp <= VRP_LOW ? 'low' : 'mid'
  }
  return out
}

// 信号方向 × 水位 → 顺逆风（+1 顺风 / 0 中性 / −1 逆风）。
// 只有微笑残差带明确买卖方向；C-P 与期限倒挂是相对价值结构（两腿同持），
// 整体水位对它们没有方向性影响，恒为中性——这正是相对价值信号的优点。
function envFitScore(bias, level) {
  if (!level || bias === 'neutral') return 0
  if (bias === 'sell') return level === 'high' ? 1 : level === 'low' ? -1 : 0
  return level === 'low' ? 1 : level === 'high' ? -1 : 0   // bias === 'buy'
}

function fmtSigned(v, digits = 1) {
  return (v >= 0 ? '+' : '') + v.toFixed(digits)
}

// 3×3 线性方程组高斯消元（列主元）；奇异返回 null
function solve3(A, b) {
  const M = [
    [A[0][0], A[0][1], A[0][2], b[0]],
    [A[1][0], A[1][1], A[1][2], b[1]],
    [A[2][0], A[2][1], A[2][2], b[2]],
  ]
  for (let col = 0; col < 3; col++) {
    let piv = col
    for (let r = col + 1; r < 3; r++) if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r
    if (Math.abs(M[piv][col]) < 1e-12) return null
    ;[M[col], M[piv]] = [M[piv], M[col]]
    for (let r = 0; r < 3; r++) {
      if (r === col) continue
      const f = M[r][col] / M[col][col]
      for (let c2 = col; c2 < 4; c2++) M[r][c2] -= f * M[col][c2]
    }
  }
  return [M[0][3] / M[0][0], M[1][3] / M[1][1], M[2][3] / M[2][2]]
}

// 二次最小二乘拟合 y = a·m² + b·m + c；pts: [{m, y}]；返回 [a,b,c] 或 null
export function quadFit(pts) {
  if (!pts || pts.length < MIN_FIT_POINTS - 1) return null
  let S0 = 0, S1 = 0, S2 = 0, S3 = 0, S4 = 0, T0 = 0, T1 = 0, T2 = 0
  for (const p of pts) {
    const m = p.m, y = p.y
    const m2 = m * m
    S0 += 1; S1 += m; S2 += m2; S3 += m2 * m; S4 += m2 * m2
    T0 += y; T1 += m * y; T2 += m2 * y
  }
  const coef = solve3(
    [[S0, S1, S2], [S1, S2, S3], [S2, S3, S4]],
    [T0, T1, T2],
  )
  // 正规方程未知量顺序为 [c, b, a]，调回 [a, b, c] 方便外部按幂次使用
  if (!coef || coef.some(v => !Number.isFinite(v))) return null
  return [coef[2], coef[1], coef[0]]
}

// 信号①核心：LOO（留一法/删除残差）扫描。
// 不能直接全量拟合——单个 +5pp 尖点会把二次曲线拽弯、自己的残差被"吸收"
// （回归诊断称 masking 效应）。正确做法：对每个点，用其余 n-1 个点拟合，
// 再量该点对这条"同伴曲线"的偏离，σ 取同伴残差的稳健值。
function smileScan(grp, spot) {
  if (spot === null || spot <= 0 || grp.length < MIN_FIT_POINTS) return []
  const pts = grp.map(r => ({ m: (r.strike - spot) / spot, y: r.iv, r }))
  const evalQuad = (c, m) => c[0] * m * m + c[1] * m + c[2]
  const out = []
  for (let i = 0; i < pts.length; i++) {
    const others = pts.filter((_, j) => j !== i)
    const coef = quadFit(others)
    if (!coef) continue
    const resid = pts[i].y - evalQuad(coef, pts[i].m)
    const sigma = madSigma(others.map(p => p.y - evalQuad(coef, p.m)))
    const zRaw = resid / sigma
    if (Math.abs(zRaw) < SMILE_Z) continue
    const z = Math.sign(zRaw) * Math.min(Math.abs(zRaw), Z_CAP)
    out.push({ r: pts[i].r, resid, z })
  }
  return out
}

// 稳健 σ：1.4826 × MAD，带下限
function madSigma(resids) {
  const med = median(resids) ?? 0
  const mad = median(resids.map(r => Math.abs(r - med))) ?? 0
  return Math.max(1.4826 * mad, SIGMA_FLOOR)
}

function mkSignal(type, target, { expiry, strike, optionType, optionCode, codes, iv, stale }, metric, strength, detail, suggestion, costCtx = {}, envCtx = {}) {
  // 成本口径（单位：IV 点数，与信号幅度同为 pp，可直接比较）：
  //   cost_pct = 各腿往返价差占权利金 %（实测值，Σ(卖一−买一)/中间价，供展示）
  //   cost_pp  = 把每条腿的价差折回 IV 点数：价差(元/份) ÷ vega(每 1pp)
  //   net_pp   = 信号幅度(pp) − cost_pp，>0 才谈得上「幅度盖得住成交成本」
  const legs = (costCtx.legs || []).filter(l => l && l.code)
  const spreads = legs.map(l => (Number.isFinite(l.spreadPct) ? l.spreadPct : null)).filter(v => v !== null)
  const costPct = spreads.length ? spreads.reduce((a, b) => a + b, 0) : null
  const costPps = legs.map(l => legCostPp(l, costCtx.spot, costCtx.now)).filter(v => v !== null)
  const costPp = legs.length && costPps.length === legs.length
    ? costPps.reduce((a, b) => a + b, 0) : null
  const edgePp = Number.isFinite(costCtx.edgePp) ? Math.abs(costCtx.edgePp) : null
  const netPp = costPp !== null && edgePp !== null ? edgePp - costPp : null
  const ts = legs.map(l => l.ts).filter(Boolean).sort().pop() || null
  // 环境标签：这条信号指向的波动率方向（卖/买/相对价值）与标的整体水位的匹配度。
  // 微笑残差用 z 的符号判方向（z>0 → 该腿偏贵 → 卖），C-P / 期限恒为 neutral。
  const envLevel = envCtx.level ?? null
  const envBias = type === 'smile' ? (metric > 0 ? 'sell' : 'buy') : 'neutral'
  return {
    type, target_code: target.code, target_name: target.name,
    expiry: String(expiry || ''), strike: strike ?? null,
    option_type: optionType, option_code: optionCode || null,
    codes: codes || (optionCode ? [optionCode] : []),
    iv, metric, strength, detail, suggestion: suggestion || '', stale: !!stale,
    cost_pct: costPct, cost_pp: costPp, edge_pp: edgePp, net_pp: netPp,
    executable: netPp !== null && netPp > 0,
    wide_spread: costPct !== null && costPct > COST_WIDE,
    market_ts: ts,
    env_level: envLevel,
    env_basis: envCtx.basis || 'none',
    env_ivr: envCtx.ivr ?? null,
    env_vrp: envCtx.vrp ?? null,
    env_bias: envBias,
    env_fit: envFitScore(envBias, envLevel),
  }
}

// BS vega：每 1pp 波动率变化对应的每份权利金（元）。
// 不用 0.4·S·√T 的 ATM 近似——虚值腿上它会高估一个量级，把净额算成几百%。
export function bsVegaPerPp(spot, strike, ivPct, expiry, now = new Date(), rate = 0.02) {
  if (!(spot > 0) || !(strike > 0) || !(ivPct > 0)) return null
  const d = daysToExpiry(expiry, now)
  if (d === null || d <= 0) return null
  const T = d / 365, sigma = ivPct / 100
  const sT = sigma * Math.sqrt(T)
  if (!(sT > 0)) return null
  const d1 = (Math.log(spot / strike) + (rate + sigma * sigma / 2) * T) / sT
  const pdf = Math.exp(-d1 * d1 / 2) / Math.sqrt(2 * Math.PI)
  return spot * pdf * Math.sqrt(T) / 100
}

// 单腿往返价差折成 IV 点数：价差(元/份) ÷ vega(元/份/pp)
function legCostPp(leg, spot, now) {
  if (!leg || !Number.isFinite(leg.spreadPct) || !(leg.mid > 0)) return null
  const vega = bsVegaPerPp(spot, leg.strike, leg.iv, leg.expiry, now)
  if (vega === null) return null
  return (leg.spreadPct / 100) * leg.mid / vega
}

// 把 /api/quotes 的原始行规整成扫描行；无效行丢弃
function normalizeRows(t) {
  const spot = num(t.spot)
  const rows = []
  let total = 0
  for (const r of (t.rows || [])) {
    total++
    if (!['ok', 'stale'].includes(r.data_status)) continue
    let iv = num(r.iv)
    // 新浪 IV 口径自适应：<1.5 视为小数（0.19=19%）→ 统一为百分数
    if (iv !== null && iv > 0 && iv < 1.5) iv = iv * 100
    const strike = num(r.strike)
    if (iv === null || iv <= IV_FLOOR || strike === null || strike <= 0) continue
    if (!['call', 'put'].includes(r.option_type)) continue
    // 五档（买一/卖一）：缺任一侧 → 价差不可用，不拿最新价冒充
    const bid = num(r.bid), ask = num(r.ask)
    const hasBook = bid !== null && ask !== null && bid > 0 && ask > 0 && ask >= bid
    const mid = hasBook ? (bid + ask) / 2 : null
    rows.push({
      expiry: String(r.expiry || ''), strike, iv, type: r.option_type,
      code: r.option_code, last: num(r.last_price), volume: num(r.volume),
      stale: r.data_status === 'stale',
      bid, ask, mid,
      spreadPct: hasBook && mid > 0 ? (ask - bid) / mid * 100 : null,
      ts: r.market_ts || null,
    })
  }
  return { spot, rows, total }
}

// 主入口：targets = [{code, name, spot, rows}]（spot 取自行内 spot.price，由调用方提取）
// options.now 可注入固定时间（测试用）；options.minDte 覆盖最短到期天数。
export function buildSignals(targets, { now = new Date(), minDte = DTE_MIN, ivEnv = null } = {}) {
  const signals = []
  let contracts = 0, ivRows = 0, droppedDte = 0
  const counts = { smile: 0, cp: 0, term: 0 }
  const envBasis = { ivr: 0, vrp: 0, none: 0 }

  for (const t of targets) {
    // 标的整体 IV 水位（IVR 优先、VRP 兜底），透传给该标的的每条信号
    const targetEnv = ivEnvironment(ivEnv && ivEnv[t.code])
    envBasis[targetEnv.basis] = (envBasis[targetEnv.basis] || 0) + 1

    const { spot, rows: rawRows, total } = normalizeRows(t)
    contracts += total
    // 近月过滤：2 天期 ATM 的 gamma 极高，IV 天然剧烈波动，不剔除会淹没整页
    const dteCache = new Map()
    const rows = rawRows.filter(r => {
      if (!dteCache.has(r.expiry)) dteCache.set(r.expiry, daysToExpiry(r.expiry, now))
      const d = dteCache.get(r.expiry)
      return d !== null && d >= minDte
    })
    droppedDte += rawRows.length - rows.length
    ivRows += rows.length
    if (!rows.length) continue

    // ---- ① 微笑残差：按 (expiry, type) 分组，LOO 删除残差扫描（仅平值区）----
    const groups = new Map()
    for (const r of rows) {
      const gk = `${r.expiry}|${r.type}`
      if (!groups.has(gk)) groups.set(gk, [])
      groups.get(gk).push(r)
    }
    for (const [, grp] of groups) {
      const atmGrp = spot !== null && spot > 0
        ? grp.filter(r => Math.abs((r.strike - spot) / spot) <= MONEYNESS_MAX)
        : []
      for (const { r, resid, z } of smileScan(atmGrp, spot)) {
        signals.push(mkSignal('smile', t,
          { expiry: r.expiry, strike: r.strike, optionType: r.type, optionCode: r.code, iv: r.iv, stale: r.stale },
          z, Math.abs(z) / SMILE_Z,
          `IV ${r.iv.toFixed(1)}% 偏离同伴曲线 ${fmtSigned(resid)}pp（z=${z.toFixed(1)}，${resid > 0 ? '偏贵' : '偏便宜'}）`,
          resid > 0
            ? '该合约相对同类偏贵：可考虑卖出收权利金，或「卖本腿 + 买相邻行权价同类」锁风险做价差'
            : '该合约相对同类偏便宜：可考虑买入，或「买本腿 + 卖偏贵腿」做价差',
          { legs: [r], edgePp: Math.abs(resid), spot, now }, targetEnv))
      }
    }

    // ---- ② C-P IV 价差：按到期日配对，偏离本到期日中位数（仅平值区）----
    const expiries = [...new Set(rows.map(r => r.expiry))].filter(Boolean).sort()
    for (const expiry of expiries) {
      const er = rows.filter(r => r.expiry === expiry)
      const strikeMap = new Map()
      for (const r of er) {
        if (spot !== null && spot > 0 && Math.abs((r.strike - spot) / spot) > MONEYNESS_MAX) continue
        if (!strikeMap.has(r.strike)) strikeMap.set(r.strike, {})
        strikeMap.get(r.strike)[r.type] = r
      }
      const pairs = []
      for (const [strike, pair] of strikeMap) {
        if (pair.call && pair.put) pairs.push({ strike, call: pair.call, put: pair.put })
      }
      if (pairs.length < MIN_CP_PAIRS) continue
      const med = median(pairs.map(p => p.call.iv - p.put.iv))
      if (med === null) continue
      for (const p of pairs) {
        const dev = (p.call.iv - p.put.iv) - med
        if (Math.abs(dev) >= CP_DIFF) {
          // 主推一腿 = 相对本类型配对池中位 IV 偏离更大的那一腿
          const medCall = median(pairs.map(p => p.call.iv))
          const medPut = median(pairs.map(p => p.put.iv))
          const devC = medCall === null ? 0 : Math.abs(p.call.iv - medCall)
          const devP = medPut === null ? 0 : Math.abs(p.put.iv - medPut)
          const primary = devC >= devP ? p.call : p.put
          const cpSuggestion = dev < 0
            ? 'Call 相对 Put 偏便宜：反向转换（买 Call + 卖 Put + 融券卖标的）；单做合成多头是 delta≈+1 的方向性头寸'
            : 'Put 相对 Call 偏便宜：转换套利（卖 Call + 买 Put + 买标的）；只做合成空头等于方向性做空'
          signals.push(mkSignal('cp', t,
            { expiry, strike: p.strike, optionType: primary.type, optionCode: primary.code, codes: [p.call.code, p.put.code], iv: primary.iv, stale: p.call.stale || p.put.stale },
            dev, Math.abs(dev) / CP_DIFF,
            `K${p.strike} 购沽 IV 差 ${fmtSigned(p.call.iv - p.put.iv)}pp（本期中位 ${med.toFixed(1)}pp），偏离 ${fmtSigned(dev)}pp`,
            cpSuggestion,
            { legs: [p.call, p.put], edgePp: Math.abs(dev), spot, now }, targetEnv))
        }
      }
    }

    // ---- ③ 期限倒挂：全段斜率（最早到期 ATM IV vs 最晚到期）----
    // 只看首末：连续倒挂 25→22→19 若只比相邻，会被拆成两条各 3pp，真实 6pp 反而看不出来。
    // 各期 ATM 行权价可能不同，detail 里完整列出 IV 序列供人工核对。
    if (spot !== null && spot > 0 && expiries.length >= 2) {
      const atmByExpiry = expiries.map(expiry => {
        const er = rows.filter(r => r.expiry === expiry)
        const strikeMap = new Map()
        for (const r of er) {
          if (!strikeMap.has(r.strike)) strikeMap.set(r.strike, {})
          strikeMap.get(r.strike)[r.type] = r
        }
        const strikes = [...strikeMap.keys()].filter(k => {
          const p = strikeMap.get(k)
          return p.call && p.put
        })
        const strike = strikes.length
          ? strikes.reduce((best, k) => best === null || Math.abs(k - spot) < Math.abs(best - spot) - 1e-12 ? k : best, null)
          : null
        const pair = strike === null ? null : strikeMap.get(strike)
        return { expiry, strike, call: pair?.call || null, put: pair?.put || null }
      })
      for (const type of ['call', 'put']) {
        const seq = atmByExpiry
          .filter(e => e[type])
          .map(e => ({ expiry: e.expiry, strike: e.strike, iv: e[type].iv, code: e[type].code, stale: e[type].stale, row: e[type] }))
        if (seq.length < 2) continue
        const near = seq[0], far = seq[seq.length - 1]
        const inv = near.iv - far.iv
        if (inv < TERM_INV) continue
        const path = seq.map(x => x.iv.toFixed(1)).join('→')
        signals.push(mkSignal('term', t,
          { expiry: near.expiry, strike: near.strike, optionType: type, optionCode: near.code, codes: [near.code], iv: near.iv, stale: seq.some(x => x.stale) },
          inv, inv / TERM_INV,
          `${type === 'call' ? '购' : '沽'} ATM IV 全段 ${path}%，首末差 ${inv.toFixed(1)}pp`,
          '日历价差：卖近月 + 买远月同行权价；先排除分红/事件导致的近月 IV 虚高',
          { legs: [near.row, far.row], edgePp: inv, spot, now }, targetEnv))
      }
    }
  }

  for (const s of signals) counts[s.type]++

  // 类型内百分位：只作展示辅助（这条在本类里排第几成），不参与排序。
  // 排到前面会把「同类只有 2 条、刚好卡阈值」的弱信号抬到全局第一。
  // strength = 偏离量 ÷ 本类型阈值，三类的单位统一为「几倍阈值」，theory 下线后可直接比较。
  for (const type of Object.keys(counts)) {
    const arr = signals.filter(s => s.type === type).sort((a, b) => a.strength - b.strength)
    arr.forEach((s, i) => { s.pct = arr.length > 1 ? Math.round((i / (arr.length - 1)) * 100) : 100 })
  }
  // 主键仍是 strength（三类统一为「几倍阈值」，跨类可比）；
  // 环境适配只作同强度下的次要键，不让水位翻掉「偏离有多大」这个主信息。
  signals.sort((a, b) => b.strength - a.strength || b.env_fit - a.env_fit || a.target_code.localeCompare(b.target_code))
  return { signals, summary: { contracts, ivRows, droppedDte, counts, envBasis } }
}

// 前端过滤：类型开关 + 目标开关 + 最小强度（倍数于阈值）+ 只看顺风
export function filterSignals(signals, { types, targets, minStrength, onlyFavorable = false }) {
  return signals.filter(s =>
    types.has(s.type) && targets.has(s.target_code) && s.strength >= minStrength
    && (!onlyFavorable || s.env_fit > 0))
}

// ---- 策略模拟页深链：把信号翻译成预填腿规格 ----
// legs 编码：`side:type:strikeSpec` 逗号分隔；
// strikeSpec：数字 = 精确行权价；'out' = 锚定行权价向外一档（call 向上 / put 向下，构成有界价差）；'near' = 就近平值。
// term（日历价差）跨到期日，策略页只支持单到期日 → 降级为近月卖出腿 + note 提示手动补远月。
export function strategyDeepLink(s) {
  const t = s.option_type
  let legs, note = ''
  if (s.type === 'smile') {
    const side1 = s.metric > 0 ? 'sell' : 'buy'
    legs = `${side1}:${t}:${s.strike},${side1 === 'sell' ? 'buy' : 'sell'}:${t}:out`
  } else if (s.type === 'cp') {
    // 合成腿只是套利的一半：完整交易还要在标的上做反向腿，策略页暂无标的腿
    legs = `${s.metric < 0 ? 'buy' : 'sell'}:call:${s.strike},${s.metric < 0 ? 'sell' : 'buy'}:put:${s.strike}`
    note = s.metric < 0
      ? 'C-P 偏离对应的完整交易是反向转换（买 Call + 卖 Put + 融券卖出标的），策略模拟只支持期权腿，已预填合成多头部分；无券源时勿单边持有'
      : 'C-P 偏离对应的完整交易是转换套利（卖 Call + 买 Put + 买入标的），策略模拟只支持期权腿，已预填合成空头部分；需补上标的腿才锁得住价差'
  } else { // term
    legs = `sell:${t}:near`
    note = '建议策略为日历价差（卖近月 + 买远月同行权价）：策略模拟暂只支持单到期日，已预填近月卖出腿，可切换到期日后手动加入远月买入腿'
  }
  return { legs, note }
}

// 深链腿规格 → 真实合约选择（策略模拟页调用）。
// contracts: [{contract_id, option_type, strike, last_price}]；返回 [{side, units:1, contractId}]（找不到为 ''）
export function resolveLegSpecs(specs, contracts, spot) {
  const rows = (contracts || []).filter(c => c && c.contract_id
    && (c.option_type === 'call' || c.option_type === 'put')
    && Number.isFinite(Number(c.strike)))
  if (!rows.length || !Array.isArray(specs) || !specs.length) return []

  // 锚定行权价：第一个显式数字 strike（'out' 腿以它为基准向外一档）
  const anchor = specs
    .map(x => Number.isFinite(Number(x.strikeSpec)) ? Number(x.strikeSpec) : null)
    .find(v => v != null) ?? null

  const strikesOf = type => [...new Set(rows.filter(c => c.option_type === type).map(c => Number(c.strike)))]

  function nearestContract(type, baseK) {
    const pool = rows.filter(c => c.option_type === type)
    if (!pool.length) return ''
    const b = baseK ?? (spot != null && spot > 0 ? spot : (anchor ?? Number(pool[0].strike)))
    const hit = pool.reduce((a, c) =>
      Math.abs(Number(c.strike) - b) < Math.abs(Number(a.strike) - b) ? c : a)
    return hit.contract_id
  }

  function contractFor(type, strike) {
    const pool = rows.filter(c => c.option_type === type && Number(c.strike) === strike)
    if (!pool.length) return ''
    return (pool.find(c => Number.isFinite(Number(c.last_price))) || pool[0]).contract_id
  }

  function outStrike(type) {
    if (anchor == null) return null
    const ks = strikesOf(type)
    if (type === 'call') {
      const ups = ks.filter(k => k > anchor + 1e-9)
      return ups.length ? Math.min(...ups) : null
    }
    const downs = ks.filter(k => k < anchor - 1e-9)
    return downs.length ? Math.max(...downs) : null
  }

  return specs.map(x => {
    const side = x.side === 'sell' ? 'sell' : 'buy'
    const type = x.type === 'put' ? 'put' : 'call'
    let strike = Number.isFinite(Number(x.strikeSpec)) ? Number(x.strikeSpec) : null
    if (x.strikeSpec === 'out') strike = outStrike(type)
    // 精确 K 不在链内 → 回落就近同类合约
    const contractId = (strike != null && contractFor(type, strike))
      || nearestContract(type, strike)
    return { side, units: 1, contractId }
  })
}
