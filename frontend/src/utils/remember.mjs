// Lightweight parameter memory: persist selected filters per page in localStorage.
// Keys are namespaced by page id. Missing/invalid stored values fall back to defaults.

const NS = 'optv2:'

export function readState(page, fallback) {
  try {
    const raw = localStorage.getItem(NS + page)
    if (!raw) return fallback
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') {
      // merge only known keys, so stale extra fields don't leak in
      const out = { ...fallback }
      for (const k of Object.keys(fallback)) if (k in parsed) out[k] = parsed[k]
      return out
    }
    return fallback
  } catch {
    return fallback
  }
}

export function writeState(page, state) {
  try {
    localStorage.setItem(NS + page, JSON.stringify(state))
  } catch {
    // storage full or blocked — silently ignore; UI still works without memory
  }
}

export function clearState(page) {
  try { localStorage.removeItem(NS + page) } catch {}
}
