# 🎫 Weverse Con 2026 抢票系统

基于 YAOLO 设计的完整 Weverse Con 2026 抢票平台，包含 Web 前端 + Flask 后端 + Playwright 自动化抢票引擎。

## 功能特性

- 🎯 **会员预售代拍** — 支持 Weverse 会员优先购票
- 🎫 **一般开售代拍** — 公开售票自动抢票
- ⬆️ **升舱服务** — 已有票升级座位等级
- 🔄 **多窗口并发** — Playwright 多标签页真并发
- 🔊 **声音提醒** — 抢票成功即时通知
- 📱 **响应式 Web 界面** — 手机 / 电脑均可操作
- 👤 **用户系统** — 注册登录、订单管理
- 🔐 **管理员后台** — 系统监控、订单管理

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | HTML5 + CSS3 + Vanilla JS |
| 后端 | Flask + SQLAlchemy + Flask-JWT |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |
| 抢票引擎 | Playwright (Chromium) |
| 实时通信 | WebSocket (flask-sock) |
| 任务队列 | APScheduler |

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

### 2. 初始化数据库

```bash
python init_db.py
```

### 3. 启动后端

```bash
python app.py
# 后端运行在 http://localhost:5000
```

### 4. 打开前端

```bash
# 直接用浏览器打开
open frontend/index.html
# 或者用 Python 起个静态服务
cd frontend && python -m http.server 8080
```

### 5. 使用流程

1. 注册账号 / 登录
2. 填写 Interpark 账号信息
3. 选择场次和座位偏好
4. 设置开售时间
5. 提交订单，系统自动抢票
6. 实时查看状态，抢票成功即时通知

## 配置

编辑 `backend/config.py` 或通过 Web 界面配置：

- Interpark 账号密码
- 演出 URL
- 场次 / 座位偏好
- 并发标签页数
- 代理设置

## 目录结构

```
wvs-con-ticketing/
├── backend/
│   ├── app.py              # Flask 主应用
│   ├── config.py           # 配置管理
│   ├── models.py           # 数据库模型
│   ├── auth.py             # 认证模块
│   ├── routes/
│   │   ├── orders.py       # 订单 API
│   │   └── admin.py        # 管理 API
│   ├── grabber/
│   │   ├── engine.py       # 抢票引擎（Playwright）
│   │   ├── scheduler.py    # 定时调度
│   │   └── monitor.py      # 状态监控
│   ├── init_db.py          # 数据库初始化
│   └── requirements.txt
├── frontend/
│   ├── index.html          # 首页
│   ├── dashboard.html      # 用户面板
│   ├── admin.html          # 管理后台
│   ├── css/
│   │   └── style.css       # 全局样式
│   └── js/
│       ├── api.js          # API 客户端
│       ├── auth.js         # 认证逻辑
│       ├── dashboard.js    # 面板逻辑
│       └── app.js          # 首页逻辑
├── logs/                   # 运行日志
├── screenshots/            # 抢票截图
└── README.md
```

## ⚠️ 免责声明

本系统仅供学习研究使用。使用自动化工具抢票可能违反平台服务条款，请自行承担风险。
