// screener.mjs — 机会筛选：四类信号纯前端扫描（零后端依赖）
// 数据源：/api/quotes/{code} 全到期日快照（新浪 IV/理论价 + 报价），与波动率页同口径。
//
// 信号 ① 微笑残差：同一(标的,到期,沽购)内，IV 对 moneyness 做二次最小二乘拟合，
//          残差用稳健 σ（1.4826×MAD，下限 0.25pp 防 z 爆表），|z| ≥ 2 视为单点异常。
// 信号 ② C-P IV 价差：同行权价 Call−Put IV 差，偏离本到期日中位数 ≥ 3pp。
//          （C−P 全线为负是结构性常态，只报"偏离自身结构"的点，避免满屏误报。）
// 信号 ③ 期限倒挂：相邻到期日 ATM IV，近月高出远月 ≥ 2pp（contango 是常态，倒挂才是异常）。
// 信号 ④ 市价 vs 理论价：|偏差| ≥ 15% 且 权利金 ≥ 0.0050（≈50 元/张）且 volume ≥ 500，
//          过滤深虚彩票式假信号（如 +550% 的 0.0001 元合约）。

const IV_FLOOR = 2               // 有效 IV 下限（%），与 3D 曲面同口径剔除坏点
const SMILE_Z = 2                // 信号①阈值（稳健 z）
const CP_DIFF = 3                // 信号②阈值（pp，偏离自身结构）
const TERM_INV = 2               // 信号③阈值（pp）
const THEO_DEV = 0.15            // 信号④阈值（相对偏差）
const THEO_MIN_PREMIUM = 0.0050  // 元/份
const THEO_MIN_VOLUME = 500
const SIGMA_FLOOR = 0.8          // 微笑拟合稳健 σ 下限（pp）：真实报价噪声量级，防 z 爆表
const MIN_FIT_POINTS = 7         // LOO 扫描最少点数（去 1 后仍需 ≥6 拟合二次）
const Z_CAP = 10                 // z 上限：σ 兜底下限时防 z 失真爆表
const MIN_CP_PAIRS = 4           // C-P 价差最少配对数，否则中位数不可信
const MONEYNESS_MAX = 0.10       // 微笑/C-P 只扫 |m|≤10% 平值区：翼部报价稀薄是结构性噪声源
const THEO_DELTA_MIN = 0.05      // 信号④排除 |delta|<0.05 的深虚彩票区

const num = v => (v == null ? null : (Number.isFinite(Number(v)) ? Number(v) : null))

export const SIGNAL_TYPES = [
  { id: 'smile', label: '微笑残差', short: '微', desc: '单点 IV 偏离同类二次拟合曲线 ≥2σ' },
  { id: 'cp', label: 'C-P 价差', short: 'CP', desc: '同行权价 Call−Put IV 差偏离本到期日中位数 ≥3pp' },
  { id: 'term', label: '期限倒挂', short: '期', desc: '近月 ATM IV 高于相邻远月 ≥2pp' },
  { id: 'theory', label: '价·理论', short: '理', desc: '市价偏离理论价 ≥15%（流动性过滤后）' },
]

function median(arr) {
  const a = arr.filter(Number.isFinite).sort((x, y) => x - y)
  if (!a.length) return null
  const mid = a.length >> 1
  return a.length % 2 ? a[mid] : (a[mid - 1] + a[mid]) / 2
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

function mkSignal(type, target, { expiry, strike, optionType, optionCode, codes, iv, stale }, metric, strength, detail, suggestion) {
  return {
    type, target_code: target.code, target_name: target.name,
    expiry: String(expiry || ''), strike: strike ?? null,
    option_type: optionType, option_code: optionCode || null,
    codes: codes || (optionCode ? [optionCode] : []),
    iv, metric, strength, detail, suggestion: suggestion || '', stale: !!stale,
  }
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
    rows.push({
      expiry: String(r.expiry || ''), strike, iv, type: r.option_type,
      code: r.option_code, last: num(r.last_price), volume: num(r.volume),
      theory: num(r.theory_price), delta: num(r.delta), stale: r.data_status === 'stale',
    })
  }
  return { spot, rows, total }
}

// 主入口：targets = [{code, name, spot, rows}]（spot 取自行内 spot.price，由调用方提取）
export function buildSignals(targets) {
  const signals = []
  let contracts = 0, ivRows = 0
  const counts = { smile: 0, cp: 0, term: 0, theory: 0 }

  for (const t of targets) {
    const { spot, rows, total } = normalizeRows(t)
    contracts += total
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
            : '该合约相对同类偏便宜：可考虑买入，或「买本腿 + 卖偏贵腿」做价差'))
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
            ? 'Call 相对便宜：可「买 Call + 卖 Put」（同行权价合成多头），待价差回归'
            : 'Put 相对便宜：可「卖 Call + 买 Put」（同行权价合成空头），待价差回归'
          signals.push(mkSignal('cp', t,
            { expiry, strike: p.strike, optionType: primary.type, optionCode: primary.code, codes: [p.call.code, p.put.code], iv: primary.iv, stale: p.call.stale || p.put.stale },
            dev, Math.abs(dev) / CP_DIFF,
            `K${p.strike} Call−Put IV 差 ${fmtSigned(p.call.iv - p.put.iv)}pp，偏离本到期日中位 ${med.toFixed(1)}pp 达 ${fmtSigned(dev)}pp`,
            cpSuggestion))
        }
      }
    }

    // ---- ③ 期限倒挂：相邻到期日 ATM IV（同到期日取最贴近现价且沽购齐全的行权价）----
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
      for (let i = 0; i + 1 < atmByExpiry.length; i++) {
        const near = atmByExpiry[i], far = atmByExpiry[i + 1]
        for (const type of ['call', 'put']) {
          const a = near[type], b = far[type]
          if (!a || !b) continue
          const inv = a.iv - b.iv
          if (inv >= TERM_INV) {
            signals.push(mkSignal('term', t,
              { expiry: near.expiry, strike: near.strike, optionType: type, optionCode: a.code, codes: [a.code], iv: a.iv, stale: a.stale || b.stale },
              inv, inv / TERM_INV,
              `${type === 'call' ? '购' : '沽'}近月 ${near.expiry} ATM IV ${a.iv.toFixed(1)}% 高于相邻远月 ${far.expiry} ${b.iv.toFixed(1)}% 达 ${inv.toFixed(1)}pp`,
              '日历价差：卖出近月 + 买入远月同行权价，赌期限结构回归常态（远月贴水修复）'))
          }
        }
      }
    }

    // ---- ④ 市价 vs 理论价（流动性过滤 + 链内中位数校正）----
    // 新浪理论价带系统性偏差（利率/股息假设使 call 链整体压低、put 链整体抬高，
    // 且随到期日递增），连 call-put 平价都被它自己破坏——整链同向偏移没有筛选价值：
    // 按 (到期日×沽购) 分链收集候选（|delta|≥0.05 排除深虚彩票区、premium/volume 门槛），
    // dev 减去本链中位数后再判 ≥15%，只报"偏离自身链结构"的离群点。
    const theoGroups = new Map()
    for (const r of rows) {
      if (r.last === null || r.theory === null || r.theory <= 0) continue
      if (r.last < THEO_MIN_PREMIUM) continue
      if (r.volume === null || r.volume < THEO_MIN_VOLUME) continue
      if (r.delta === null || Math.abs(r.delta) < THEO_DELTA_MIN) continue
      const gk = `${r.expiry}|${r.type}`
      if (!theoGroups.has(gk)) theoGroups.set(gk, [])
      theoGroups.get(gk).push({ r, dev: (r.last - r.theory) / r.theory })
    }
    for (const [, cands] of theoGroups) {
      if (cands.length < 5) continue
      const medDev = median(cands.map(c => c.dev)) ?? 0
      for (const { r, dev } of cands) {
        const adj = dev - medDev
        if (Math.abs(adj) >= THEO_DEV) {
          signals.push(mkSignal('theory', t,
            { expiry: r.expiry, strike: r.strike, optionType: r.type, optionCode: r.code, iv: r.iv, stale: r.stale },
            adj, Math.abs(adj) / THEO_DEV,
            `市价 ${r.last.toFixed(4)} vs 理论价 ${r.theory.toFixed(4)}，校正后偏差 ${fmtSigned(adj * 100, 0)}%（原始 ${fmtSigned(dev * 100, 0)}%−链中位 ${fmtSigned(medDev * 100, 0)}%，${adj > 0 ? '偏贵' : '偏便宜'}，量 ${Math.round(r.volume)}）`,
            adj > 0
              ? '市价高于理论价：可考虑卖出该合约，动手前先复核买卖价差与保证金占用'
              : '市价低于理论价：可考虑买入该合约，动手前先确认成交量与价差可成交'))
        }
      }
    }
  }

  for (const s of signals) counts[s.type]++
  signals.sort((a, b) => b.strength - a.strength || a.target_code.localeCompare(b.target_code))
  return { signals, summary: { contracts, ivRows, counts } }
}

// 前端过滤：类型开关 + 目标开关 + 最小强度（倍数于阈值）
export function filterSignals(signals, { types, targets, minStrength }) {
  return signals.filter(s =>
    types.has(s.type) && targets.has(s.target_code) && s.strength >= minStrength)
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
    legs = `${s.metric < 0 ? 'buy' : 'sell'}:call:${s.strike},${s.metric < 0 ? 'sell' : 'buy'}:put:${s.strike}`
  } else if (s.type === 'term') {
    legs = `sell:${t}:near`
    note = '建议策略为日历价差（卖近月 + 买远月同行权价）：策略模拟暂只支持单到期日，已预填近月卖出腿，可切换到期日后手动加入远月买入腿'
  } else { // theory
    legs = `${s.metric > 0 ? 'sell' : 'buy'}:${t}:${s.strike}`
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
