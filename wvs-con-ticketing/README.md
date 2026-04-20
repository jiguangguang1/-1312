# 🎫 YAOLO Weverse Con 2026 抢票系统 v2

基于 Playwright 的全自动化 Weverse Con 2026 抢票平台，Web 前端 + Flask 后端 + 异步抢票引擎。

## 功能特性

### 核心
- 🎯 **会员预售代拍** — Weverse 会员优先购票
- 🎫 **一般开售代拍** — 公开售票自动抢票
- ⬆️ **升舱服务** — 已有票升级座位等级
- 🔄 **多窗口并发** — Playwright 多标签页真并发
- 🕐 **精确倒计时** — 开售前自动冲刺

### v2 新增
- 💺 **座位配置管理** — 价格档位可视化、售罄标记、实时同步
- 🗺️ **可视化座位地图** — 分区网格图、点击联动选择
- 📅 **场次选择列表** — 日期/时间/状态一目了然
- ✅ **确认下单弹窗** — 总价计算 + 倒计时预览
- ⚡ **AsyncIO 异步引擎** — `TicketManager` + `TicketType` 多档位并发
- 🔧 **管理后台** — 用户/订单/座位配置统一管理

### 通用
- 🔊 **声音提醒** — 抢票成功即时通知
- 📱 **响应式 Web 界面** — 手机 / 电脑均可操作
- 👤 **用户系统** — 注册登录、订单管理
- 🔐 **管理员后台** — 系统监控、订单管理、座位配置

## 快速开始

### 本地运行

```bash
cd wvs-con-ticketing
pip install -r backend/requirements.txt
playwright install chromium
bash start.sh
```

### Docker

```bash
docker compose up -d
```

访问 **http://localhost:5000**

管理员：`admin` / `admin123`（生产环境请修改 `.env`）

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | HTML5 + CSS3 + Vanilla JS |
| 后端 | Flask + SQLAlchemy + Flask-JWT-Extended |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |
| 抢票引擎 | Playwright (Chromium) + asyncio |
| 容器 | Docker + docker-compose |

## 目录结构

```
wvs-con-ticketing/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── start.sh
├── README.md
├── USAGE.md
├── backend/
│   ├── app.py              # Flask 主应用 (28 API 端点)
│   ├── config.py            # 配置 (环境变量驱动)
│   ├── models.py            # 数据库模型 (User, Order, TicketClass, ...)
│   ├── auth.py              # JWT 认证装饰器
│   ├── init_db.py           # 数据库初始化 + 默认档位
│   ├── requirements.txt
│   ├── grabber/
│   │   ├── engine.py        # 🎯 GrabberEngine + AsyncGrabberEngine
│   │   └── scheduler.py     # 定时调度
│   └── routes/
│       ├── orders.py        # 订单 API
│       └── admin.py         # 管理 API
├── frontend/
│   ├── index.html           # 首页
│   ├── dashboard.html       # 控制台 (场次/座位地图/倒计时/确认弹窗)
│   ├── admin.html           # 管理后台 (订单/用户/座位配置)
│   ├── css/style.css
│   └── js/
│       ├── api.js           # API 客户端 (含 TicketClass API)
│       ├── auth.js          # 认证
│       ├── app.js           # 首页
│       ├── dashboard.js     # 控制台 (倒计时/地图联动/确认弹窗)
│       └── admin.js         # 管理 (座位配置 CRUD)
├── logs/
└── screenshots/
```

## API 端点 (28个)

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 → JWT |
| GET | `/api/auth/me` | 当前用户 |
| PUT | `/api/auth/profile` | 更新凭证 |

### 订单
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/orders` | 列表 / 创建 |
| GET/PUT/DELETE | `/api/orders/:id` | 详情 / 编辑 / 删除 |
| POST | `/api/orders/:id/start` | 启动抢票 |
| GET | `/api/orders/:id/logs` | 运行日志 |

### 座位配置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/ticket-classes` | 查看 / 创建档位 |
| PUT/DELETE | `/api/ticket-classes/:id` | 更新 / 删除 |

### 管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/dashboard` | 统计面板 |
| GET | `/api/admin/users` | 用户列表 |
| GET | `/api/admin/orders` | 所有订单 |
| PUT | `/api/admin/orders/:id/status` | 修改订单状态 |
| GET | `/api/admin/ticket-classes` | 所有档位 |
| PUT | `/api/admin/ticket-classes/:id/status` | 售罄/在售切换 |

## 免责声明

本系统仅供学习研究使用。自动化抢票可能违反平台服务条款，请自行承担风险。
