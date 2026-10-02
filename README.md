# 海疆期权 v2 (option-platform)

A 股 ETF 期权的行情浏览与策略推演平台。FastAPI + Vue 3 单机部署，后端同时托管前端静态页，一个进程对外服务。

> ⚠️ 免责声明：行情 / IV / Greeks 均来自公开数据源（上交所、新浪财经、腾讯财经）透传或据其计算，口径未核验，仅供研究学习，不构成投资建议。

## 功能

- **滚动叙事首页** `/` — 平台功能导览，滚动驱动动画 + 实时行情条
- **T 型报价** `/tquote` — 按到期日展开的 T 型报价表，ATM 高亮，自动刷新
- **全量行情** `/quotes` — 全部挂牌合约快照，筛选 / 排序 / 搜索 / moneyness 过滤，导出 CSV
- **标的 K 线** `/kline` — 60 / 120 / 250 日 K 线 + MA 均线，日 K 落盘缓存
- **策略模拟** `/strategy` — 三步流程（选策略 → 选标的/到期日 → 选合约），预设 11 种策略 + 自由组合腿，合约按参考价自动配对；分段线性解析盈亏平衡点、最大盈亏、到期价情景滑块
- **波动率分析** `/volatility` — 数据源 IV 的 smile / term structure
- **合约详情** `/contract/:code` — 单合约报价、IV、Greeks 快照
- 移动端底部 TabBar 适配

## 技术栈

- **后端** Python 3.11 + FastAPI（端口 8001，`/` 同时挂前端 dist）
- **数据源** 上交所（合约目录）+ 新浪财经（报价 / IV / Greeks）+ 腾讯财经（标的价格）；进程内 TTL 30s 缓存，日 K 落盘 `backend/cache/kline/`，上游失败降级 stale 不冒充
- **前端** Vue 3 + Vite，零 UI 库依赖，IntersectionObserver 滚动叙事

## 标的

510050（50ETF）/ 510300（300ETF）/ 510500（500ETF）/ 588000（科创50ETF）/ 588080（科创100ETF）

## 部署

```bash
# 后端
cd backend && python3.11 -m uvicorn main:app --host 0.0.0.0 --port 8001

# 前端（构建产物由后端托管）
cd frontend && npm install && npm run build
```

## 主要 API

| 路径 | 说明 |
|---|---|
| `GET /health`、`GET /api/diag` | 健康检查 / 数据源诊断 |
| `GET /api/targets` | 标的列表 |
| `GET /api/tquote/{code}?expiry=` | T 型报价 |
| `GET /api/quotes/{code}` | 全量行情快照（筛选/分页） |
| `GET /api/kline/{code}?days=` | 日 K |
| `GET /api/expiries/{code}` | 到期日目录 |
| `GET /api/strategy/market/{code}?expiry=` | 策略页合约快照 + 参考价 |
| `GET /api/contract/{option_code}` | 单合约详情 |

## 测试

```bash
node frontend/tests/../src/utils  # 策略引擎数值回归（60 断言）见 pages-src/test_strategy.mjs
cd backend && python -m pytest tests/
```

## 版本

- **v1.0**（2026-07）— 初版：波动率曲面可视化
- **v2.0**（2026-10）— 全面重构：滚动叙事首页、六页 UI 设计系统、真实挂牌合约策略模拟引擎、移动端适配

## License

MIT
