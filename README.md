# 海疆期权 v2 (option-platform)

A 股 ETF 期权的行情浏览与策略推演平台。FastAPI + Vue 3 单机部署，后端同时托管前端静态页，一个进程对外服务。

> ⚠️ 免责声明：行情 / IV / Greeks 均来自公开数据源（上交所、新浪财经、腾讯财经）透传或据其计算，口径未核验，仅供研究学习，不构成投资建议。

## 功能

- **滚动叙事首页** `/` — 平台功能导览，滚动驱动动画 + 实时行情条
- **T 型报价** `/tquote` — 按到期日展开的 T 型报价表，ATM 高亮，自动刷新，含买一/卖一与行情时间
- **合约列表** `/quotes` — T 型报价的列表视图（不在主导航，页头入口进入）：全部挂牌合约快照，筛选 / 排序 / 搜索 / moneyness 过滤，导出 CSV
- **标的 K 线** `/kline` — 门户式窗口模型：一次取 300 根（日）/ 480 根（分），滚轮或双指缩放、拖动平移、双击复位，预设 1月/3月/6月/1年只改可见窗口；MA 均线，日 K 落盘缓存
- **策略模拟** `/strategy` — 三步流程（选策略 → 选标的/到期日 → 选合约），预设 11 种策略 + 自由组合腿，合约按参考价自动配对；分段线性解析盈亏平衡点、最大盈亏、到期价情景滑块；支持深链预填 `?code=&expiry=&legs=`
- **机会筛选** `/screener` — 三类信号自动扫描：微笑残差（LOO 删除残差 z-score）、C-P IV 价差偏离、ATM 期限结构倒挂（全段比较）；剩余到期 <7 天整条链剔除；按超阈值倍数排序，每条带方向感知建议策略与「价差/净额」成本测算；顶部 IV 环境条给出各标的波动率水位并标注信号顺风/逆风
- **波动率分析** `/volatility` — **IV 水位**（IV30 / RV20 / VRP / IVR）、smile / term structure、**3D 波动率曲面**（Canvas 正交投影，拖拽旋转 / 缩放 / 悬停查看）
- **合约详情** `/contract/:code` — 单合约报价、买一/卖一、价差、IV、Greeks 快照
- TickerBar 全站常驻行情条（5 标的现价 30s 轮询）；移动端底部 TabBar 适配

## 技术栈

- **后端** Python 3.11 + FastAPI（端口 8001，`/` 同时挂前端 dist）
- **数据源** 上交所（合约目录）+ 新浪财经（报价 / IV / Greeks / 五档行情）+ 腾讯财经（标的价格 / 日K）；进程内 TTL 30s 缓存，日 K 落盘 `backend/cache/kline/`，上游失败降级 stale 不冒充
- **历史库** SQLite `backend/data/iv_history.db`（每日全链快照 + 每标的 IV30），每日收盘 cron 落盘；IVR / IVP / VRP 由此计算
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
| `GET /api/kline/{code}?days=&period=day\|5m\|15m\|30m\|60m` | 日 K / 分钟 K |
| `GET /api/expiries/{code}` | 到期日目录 |
| `GET /api/strategy/market/{code}?expiry=` | 策略页合约快照 + 参考价 |
| `GET /api/contract/{option_code}` | 单合约详情 |
| `GET /api/ivstats`、`GET /api/ivstats/{code}` | IV 水位（IV30 / RV20 / VRP / IVR / IVP） |
| `GET /api/ivsnapshot?force=&overwrite=` | 落盘当日全链快照（cron 每日 15:35 调用） |

## 数据口径

- **行情时间**取新浪期权五档字段（`market_ts`），与抓取时间区分；缺失时 `freshness=unknown`，不冒充新鲜
- **IV 单位**统一为百分数（源返回小数 0.17 视为 17%）；退化值（纯内在价值反推）会得到趋近 0% 的假 IV，3D 曲面剔除 <2%
- **成本口径** `cost_pct` = Σ(卖一−买一)/中间价（占权利金），`cost_pp` = 同一条价差 ÷ **BS vega** 折回 IV 点数；禁止用 ATM 近似 vega，虚值腿会高估一个量级
- **IV30** = 各到期 ATM（最接近现价行权价的 call/put 均值）按剩余天数线性插值到 30 天，单侧不外推
- **归日**取各腿行情时间日期的众数，不用系统日期——盘前跑拿到的是昨日收盘价

## 测试

```bash
# 后端
cd backend && python -m pytest tests/

# 前端引擎（策略 60 / 波动率 30 / 机会筛选 73 断言，node 直跑）
node frontend/tests/strategy.test.mjs
node frontend/tests/volatility.test.mjs
node frontend/tests/screener.test.mjs
node frontend/tests/kline.test.mjs
```

## 版本

- **v1.0**（2026-07）— 初版：波动率曲面可视化
- **v2.0**（2026-10）— 全面重构：滚动叙事首页、六页 UI 设计系统、真实挂牌合约策略模拟引擎、移动端适配
- **v2.1**（2026-10）— 机会筛选页（四类信号 + 建议策略 + 一键深链预填）、分钟级 K 线、3D 波动率曲面、全站行情条、IV 口径自适应修复
- **v2.2**（2026-11）— 行情时间与五档（market_ts / 买一卖一 / 价差）接入；筛选页成本与净额测算（BS vega 折 pp）；信号收敛为三类并加 DTE 门槛；K 线改门户式缩放窗口；导航精简为 5 项、/quotes 降为列表视图；历史 IV 库（SQLite）+ IVR/IVP/VRP 与筛选环境条

## License

MIT
