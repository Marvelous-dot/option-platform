<template>
  <!-- 纯文案轮播：信息导览型。移动端隐藏，不占 T 型表空间 -->
  <section class="promo-banner" aria-label="平台功能导览">
    <div class="promo-lead">
      <span class="promo-mark">海疆</span>
      <span class="promo-sub">期权市场数据</span>
    </div>
    <div class="promo-viewport">
      <p
        v-for="(line, i) in lines"
        :key="i"
        class="promo-line"
        :class="{ active: i === idx }"
      >{{ line }}</p>
    </div>
    <button
      class="promo-close"
      type="button"
      aria-label="关闭导览"
      @click="$emit('close')"
    >×</button>
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

// 文案集中配置；改这里即可，不需要动模板。每条保持一句话、短。
const lines = [
  '5 只 ETF 标的 · 实时 T 型报价 / IV / Greeks（30s 自动刷新，失败走 stale 降级）',
  '全量合约行情 · 可按到期日 / 虚实值 / 关键词筛选，一键导出 CSV',
  '标的日 K 线已落盘缓存 · 上游失败仍可查看最近 7 天历史（stale 标注）',
  '策略本地模拟 · 独立模型假设，非实时行情；波动率曲面 / 微笑 / 期限结构',
]

const HOLD_MS = 5000   // 每条停留
const FADE_MS = 420   // 切换淡入淡出
const idx = ref(0)
let timer = null

const emit = defineEmits(['close'])

function start() {
  stop()
  timer = setInterval(() => {
    idx.value = (idx.value + 1) % lines.length
  }, HOLD_MS)
}
function stop() {
  if (timer) { clearInterval(timer); timer = null }
}

onMounted(() => {
  start()
  // 尊重用户偏好：reduce-motion 时停在第一条，不做轮播动画
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) stop()
})
onUnmounted(stop)
</script>

<style scoped>
.promo-banner {
  display: flex; align-items: center; gap: 14px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
}
.promo-lead {
  flex: none; display: flex; flex-direction: column; gap: 2px;
  padding-right: 14px; border-right: 1px solid var(--border);
}
.promo-mark {
  font-size: 15px; font-weight: 800; color: var(--text);
  letter-spacing: -0.02em; line-height: 1.1;
}
.promo-sub {
  font-size: 11px; color: var(--text-muted); font-weight: 600;
  letter-spacing: 0.04em;
}
.promo-viewport {
  flex: 1; min-height: 40px; position: relative;
  overflow: hidden; display: flex; align-items: center;
}
.promo-line {
  position: absolute; left: 0; right: 0;
  font-size: 13px; line-height: 1.5; color: var(--text-dim);
  opacity: 0; transform: translateY(6px);
  transition: opacity var(--_fade, 0.42s) ease, transform var(--_fade, 0.42s) ease;
  pointer-events: none;
}
.promo-line.active {
  opacity: 1; transform: translateY(0);
  position: relative;
  pointer-events: auto;
}
.promo-close {
  flex: none; width: 24px; height: 24px; padding: 0;
  border: 1px solid var(--border); background: var(--bg);
  color: var(--text-muted); border-radius: var(--pill);
  font-size: 14px; line-height: 1; display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .15s;
}
.promo-close:hover { color: var(--text); border-color: var(--text); }

@media (max-width: 768px) {
  .promo-banner { display: none; }
}
</style>
