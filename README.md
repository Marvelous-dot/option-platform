# 期权展示平台 (Option Platform)

基于 FastAPI + Vue 3 的期权数据实时展示与分析平台。支持期权波动率曲面可视化、隐含波动率（IV）时间序列、IV Smile、期限结构等核心功能的交互式展示。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Python 3.11 |
| 前端 | Vue 3 + Vite + Element Plus |
| 数据源 | AKShare（实时期权行情） |
| 存储 | SQLite（隐含波动率历史数据） |
| 部署 | uvicorn + Nginx / Vite 静态托管 |

## 核心功能

- **实时行情** — 期权合约报价、买卖盘口
- **波动率曲面** — 3D 可视化波动率曲面（Canvas + CSS3D）
- **IV Smile** — 隐含波动率偏度曲线
- **期限结构** — 不同到期日的 IV 期限结构图
- **ATM IV 序列** — 平值期权隐含波动率历史走势
- **K线数据** — 标的期货/ETF 历史 K 线
- **Dashboard** — 总览面板（最新数据快照）

## 后端 API

| 端点 | 说明 |
|---|---|
| `GET /api/quotes` | 期权合约实时行情 |
| `GET /api/iv-surface` | 隐含波动率曲面数据 |
| `GET /api/iv-smile` | IV Smile 数据 |
| `GET /api/term-structure` | 期限结构数据 |
| `GET /api/atm-iv` | ATM 期权 IV 历史 |
| `GET /api/kline` | 标的 K 线数据 |
| `GET /api/dashboard` | 总览数据 |
| `GET /api/contract-detail` | 单个合约详情 |

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
# 配置 .env（可选）
python run.py

# 前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
option-platform/
├── backend/
│   ├── main.py           # FastAPI 主应用
│   ├── models.py         # 数据模型
│   ├── data_service.py   # AKShare 数据采集
│   ├── bs_model.py       # B-S 定价与 Greeks
│   ├── iv_store.py       # IV 历史数据存取
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/        # 页面组件
│   │   ├── components/   # 通用组件
│   │   └── utils/        # 工具函数
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## 许可

MIT License
