/**
 * Canvas CSS 变量读取工具
 * 用于让 Canvas 图表跟随全局主题（深色/浅色切换）
 */

let _cssVars = null

/**
 * 读取全局 CSS 变量
 * @returns {Object} CSS 变量映射
 */
export function getCssVars() {
  if (!_cssVars) {
    const style = getComputedStyle(document.documentElement)
    _cssVars = {
      bgCard: style.getPropertyValue('--bg-card').trim() || '#111a2e',
      bgDeep: style.getPropertyValue('--bg-deep').trim() || '#060a13',
      bgPrimary: style.getPropertyValue('--bg-primary').trim() || '#0b1120',
      textDim: style.getPropertyValue('--text-dim').trim() || '#3a4560',
      textMuted: style.getPropertyValue('--text-muted').trim() || '#535f75',
      textSecondary: style.getPropertyValue('--text-secondary').trim() || '#8892a8',
      textPrimary: style.getPropertyValue('--text-primary').trim() || '#e8eaf0',
      border: style.getPropertyValue('--border').trim() || '#1e2a40',
      borderLight: style.getPropertyValue('--border-light').trim() || '#263350',
      accent: style.getPropertyValue('--accent').trim() || '#f0a030',
      up: style.getPropertyValue('--up').trim() || '#e8883e',
      down: style.getPropertyValue('--down').trim() || '#3cc4a0',
      fontSans: style.getPropertyValue('--font-sans').trim() || 'Noto Serif SC, sans-serif',
      fontMono: style.getPropertyValue('--font-mono').trim() || 'JetBrains Mono, monospace',
    }
  }
  return _cssVars
}

/**
 * 获取单个 CSS 变量
 */
export function cssVar(name, fallback) {
  const style = getComputedStyle(document.documentElement)
  return style.getPropertyValue(name).trim() || fallback
}