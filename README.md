<div align="center">

# 期权波动率曲面可视化平台

> 一个基于 FastAPI + Vue 3 的期权数据实时分析与展示系统

**[![GitHub Stars](https://img.shields.io/github/stars/Marvelous-dot/option-platform?style=flat-square&logo=github)](https://github.com/Marvelous-dot/option-platform)**
**[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)**
**[![Vue.js](https://img.shields.io/badge/Vue-3.5-green?style=flat-square&logo=vue.js)](https://vuejs.org)**
**[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-orange?style=flat-square)](https://fastapi.tiangolo.com)**
**[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](./LICENSE)**

![option-platform-preview](https://via.placeholder.com/800x450?text=期权波动率曲面+实时行情+IV+可视化)
<!-- 替换上方链接为实际截图 -->

[📋 功能特性](#功能特性) · [🚀 快速启动](#快速启动) · [📡 API](#api-文档) · [🏗 项目架构](#项目架构) · [📖 文档](#相关文档)

</div>

---

## 概述

在国内期权交易中，**波动率曲面、IV Smile、期限结构**等核心分析工具的可视化实现鲜有开源项目。

本项目基于 Python 原生实现 Black-Scholes 定价模型，通过 AKShare 接入实时期权行情，以 FastAPI 构建数据服务层，Vue 3 + Canvas 渲染交互式 3D 波动率曲面，为量化交易者提供一站式的期权分析工具。

### 核心亮点

| 特性 | 说明 |
|------|------|
| 🔬 **B-S 定价引擎** | 纯 Python 实现 Black-Scholes 模型，支持 Greeks 计算与盈亏模拟 |
| 🌊 **3D 波动率曲面** | 实时渲染隐含波动率曲面，支持旋转/缩放交互 |
| 📈 **IV Smile / 期限结构** | 可视化不同行权价的波动率偏度与到期日分布 |
| ⚡ **实时行情** | 基于 AKShare 自动轮询，数据每 30s 刷新 |
| 📊 **Dashboard 面板** | 数据总览 + 历史趋势 + ATM IV 序列 |
| 🗄 **SQLite 本地存储** | 隐含波动率历史数据持久化，无需外部数据库 |

---

## 功能特性

### 后端数据引擎

- **B-S 期权定价** — 标的价格、行权价、到期时间、波动率一键定价
- **Greeks 计算** — Delta、Gamma、Vega、Theta、Rho 全量输出
- **盈亏模拟** — 不同场景下期权头寸盈亏曲线
- **自动轮询** — 后台定时任务每 N 秒自动更新行情与 IV 数据
- **数据修复** — 检测到数据异常自动触发修复机制

### 前端可视化

- **实时行情页** — 期权合约买卖盘口、最新价格
- **波动率曲面** — 3D 交互式曲面（Canvas + CSS3D 双引擎）
- **IV Smile 图** — 隐含波动率偏度可视化
- **期限结构** — 不同到期日 IV 走势对比
- **K线图表** — 标的期货/ETF 历史 K 线（ECharts）
- **合约详情** — 单个合约的完整定价与 Greeks 信息
- **Dashboard** — 实时总览面板

---

## 快速启动

```bash
# 克隆项目
git clone https://github.com/Marvelous-dot/option-platform.git
cd option-platform

# ===== 后端 =====
cd backend
pip install -r requirements.txt

# 创建环境变量（可选）
cp .env.example .env   # 按需修改

# 启动后端服务（默认端口 8000）
python run.py

# ===== 前端 =====
cd ../frontend
npm install
npm run dev            # 启动开发服务器（默认端口 5173）
```

浏览器打开 http://localhost:5173 即可访问。

### 生产部署

```bash
# 构建前端
cd frontend
npm run build

# 后端使用 uvicorn 启动
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## API 文档

所有接口前缀为 `/api/`，返回 JSON 格式。

| 端点 | 方法 | 说明 | 返回内容 |
|------|------|------|----------|
| `/quotes` | GET | 期权合约实时行情 | 合约列表 + 买卖盘口 |
| `/iv-surface` | GET | 隐含波动率曲面数据 | 3D 曲面点云数据 |
| `/iv-smile` | GET | IV Smile 数据 | 行权价-波动率曲线 |
| `/term-structure` | GET | 期限结构数据 | 到期日-波动率曲线 |
| `/atm-iv` | GET | ATM IV 历史 | 平值 IV 时间序列 |
| `/kline` | GET | 标的 K 线 | OHLCV 数据 |
| `/contract-detail` | GET | 合约详情 | B-S 定价 + Greeks |
| `/dashboard` | GET | 总览面板 | 最新数据快照 |

---

## 项目架构

```
option-platform/
├── backend/                    # FastAPI 后端服务
│   ├── main.py                 #  FastAPI 主应用入口
│   ├── run.py                  #  启动脚本
│   ├── models.py               #  Pydantic 数据模型
│   ├── bs_model.py             #  B-S 定价 + Greeks
│   ├── data_service.py         #  AKShare 数据采集层
│   ├── iv_store.py             #  IV 历史数据（SQLite）
│   ├── cleanup_iv.py           #  数据清理
│   └── requirements.txt
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── views/              #  页面组件
│   │   │   ├── Home.vue        #    首页
│   │   │   ├── Quotes.vue      #    实时行情
│   │   │   ├── Volatility.vue  #    波动率曲面
│   │   │   ├── TQuote.vue      #    期货行情
│   │   │   └── ContractDetail.vue
│   │   ├── components/         #  通用组件
│   │   │   ├── Surface3D.vue   #    3D 波动率曲面
│   │   │   ├── DashboardChart.vue
│   │   │   └── AppLayout.vue
│   │   ├── utils/              #  工具函数
│   │   └── styles/             #  全局样式
│   ├── package.json
│   └── vite.config.js
├── .gitignore
├── README.md
└── LICENSE
```

---

## 相关文档

| 文档 | 链接 |
|------|------|
| Black-Scholes 模型 | https://en.wikipedia.org/wiki/Black%E2%80%93Scholes_model |
| AKShare 文档 | https://akshare.akfamily.xyz/ |
| 3D 曲面可视化方案 | 基于 Canvas 2D + CSS3D 双引擎 |
| 技术选型说明 | FastAPI + Vue 3 + Element Plus |

---

## 许可

MIT License — 详见 [LICENSE](./LICENSE)

---

<div align="center">

**Star 本项目，持续更新中 ⭐**

</div>
