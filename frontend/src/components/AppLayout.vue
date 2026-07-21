<template>
  <div class="app-root">
    <header class="app-header">
      <div class="app-header-inner">
        <div class="app-brand">
          <span class="brand-icon">◈</span>
          <span class="brand-name">海疆期权</span>
          <span class="brand-sub">期权数据中心</span>
        </div>

        <!-- 汉堡按钮：移动端显示 -->
        <button class="hamburger" @click="navOpen = !navOpen" :class="{ open: navOpen }" aria-label="菜单">
          <span></span><span></span><span></span>
        </button>

        <nav class="app-nav" :class="{ open: navOpen }" @click="navOpen = false">
          <router-link to="/" class="nav-item" active-class="active">
            <span class="nav-icon">◷</span> 实时行情
          </router-link>
          <router-link to="/quotes" class="nav-item" active-class="active">
            <span class="nav-icon">📊</span> 标的汇总
          </router-link>
          <router-link to="/tquote" class="nav-item" active-class="active">
            <span class="nav-icon">⊞</span> T型报价
          </router-link>
          <router-link to="/volatility" class="nav-item" active-class="active">
            <span class="nav-icon">📈</span> 波动率
          </router-link>
        </nav>

        <div class="app-status" v-show="!navOpen">
          <span class="status-dot pulse"></span>
          <span class="status-text">API 在线</span>
        </div>

        <!-- 昼夜切换 -->
        <button class="theme-toggle" @click="toggleTheme" :title="isDark ? '切换到白天模式' : '切换到黑夜模式'">
          <span class="theme-icon">{{ isDark ? '🌙' : '☀️' }}</span>
        </button>
      </div>
    </header>

    <main class="app-main">
      <router-view />
    </main>

    <footer class="app-footer">
      <span class="footer-left">海疆期权 v1.0</span>
      <span class="footer-right">腾讯财经 · BS模型 · 30s刷新</span>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
const navOpen = ref(false)
const isDark = ref(true)

function applyTheme(dark) {
  isDark.value = dark
  if (dark) {
    document.documentElement.classList.remove('light')
  } else {
    document.documentElement.classList.add('light')
  }
  localStorage.setItem('theme', dark ? 'dark' : 'light')
}

function toggleTheme() {
  applyTheme(!isDark.value)
}

onMounted(() => {
  const saved = localStorage.getItem('theme')
  if (saved === 'light') {
    applyTheme(false)
  } else {
    applyTheme(true)
  }
})
</script>

<style scoped>
.app-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 8px rgba(0,0,0,0.3);
}

.app-header-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  height: 56px;
  gap: 16px;
}

.app-brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-shrink: 0;
}

.brand-icon {
  font-size: 20px;
  color: var(--accent);
  font-weight: 700;
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}

.brand-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.app-nav {
  display: flex;
  gap: 4px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  font-size: 13px;
  color: var(--text-secondary);
  border-radius: 6px;
  transition: all 0.15s;
  text-decoration: none;
}

.nav-item:hover {
  background: var(--accent-soft);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.nav-icon {
  font-size: 14px;
}

.app-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--down);
  display: inline-block;
}

.pulse {
  animation: pulse 2s ease-in-out infinite;
}

.status-text {
  color: var(--text-secondary);
}

/* ── 昼夜切换按钮 ── */
.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--transition);
  padding: 0;
  color: var(--text-secondary);
  margin-left: auto;
}
.theme-toggle:hover {
  border-color: var(--accent-dim);
  background: var(--bg-card-hover);
  color: var(--text-primary);
}
.theme-icon {
  font-size: 18px;
  line-height: 1;
}

.app-main {
  flex: 1;
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px 24px 32px;
  width: 100%;
}

.app-footer {
  background: var(--bg-primary);
  border-top: 1px solid var(--border);
  padding: 10px 24px;
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* ── 汉堡按钮（默认隐藏） ── */
.hamburger {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  width: 36px;
  height: 36px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  flex-shrink: 0;
}
.hamburger:hover { background: var(--accent-soft); }
.hamburger span {
  display: block;
  width: 100%;
  height: 2px;
  background: var(--text-secondary);
  border-radius: 2px;
  transition: all 0.3s;
}
.hamburger.open span:nth-child(1) { transform: translateY(7px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; }
.hamburger.open span:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

/* ── 移动端适配 ── */
@media (max-width: 768px) {
  .hamburger { display: flex; }
  .app-header-inner { padding: 0 16px; gap: 12px; }
  .brand-sub { display: none; }
  .brand-name { font-size: 14px; }

  .app-nav {
    display: none;
    position: absolute;
    top: 56px;
    left: 0;
    right: 0;
    background: var(--bg-primary);
    border-bottom: 1px solid var(--border);
    flex-direction: column;
    padding: 8px 16px;
    gap: 4px;
    z-index: 99;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }
  .app-nav.open { display: flex; }
  .nav-item { padding: 10px 12px; font-size: 14px; }

  .app-status { display: none; }
  .app-main { padding: 16px 12px 24px; }
  .app-footer { padding: 8px 12px; font-size: 10px; }
  .footer-right { display: none; }
}
</style>
