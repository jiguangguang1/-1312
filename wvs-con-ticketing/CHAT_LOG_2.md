# CHAT_LOG.md — 第二次对话

时间: 2026-04-21 00:02 ~ 00:40 (GMT+8)
参与者: 用户 + AI 助手
项目: wvs-con-ticketing (NOL 抢票系统 v3)

---

## 本次对话完成了以下工作：

### 1. NOL 平台深度分析

**目标演出：**
- 音乐剧〈传奇小篮球团〉(Musical Legendary Little Basketball Team) — 练手用
  - goodsCode: 26001295, placeCode: 24000240
  - 日期: 2026-03-10 ~ 2026-05-25
  - 状态: 已开售，可购买
  - 问题: 需要 eKYC 实名认证，账号未完成 → 按钮被禁用 (tabIndex: -1)

- BTS WORLD TOUR 'ARIRANG' IN BUSAN — 真正目标
  - goodsCode: 26005547, placeCode: 26000398
  - 日期: 2026-06-12 ~ 2026-06-13 (2天)
  - 一般开售: 2026-04-30 20:00 KST
  - 粉丝预售: 2026-04-29 20:00 KST ~ 04-30 10:00
  - 预售需要: Fan Club 会员 + 姓名/ID 验证

### 2. API 逆向工程

通过 Playwright 浏览器拦截 + curl 探测，发现 NOL 以下 API：

**已确认可用（公开）：**
```
GET /api/ent-channel-out/v1/goods/salesinfo?goodsCode=&placeCode=&bizCode=10965
  → 售卖信息：演出期、开售时间、预售信息
GET /api/ent-channel-out/v1/goods/detail?goodsCode=&placeCode=&language=ZH_CN
  → 商品详情：名称、价格、海报、场馆信息（部分商品需要正确 bizCode）
```

**已确认可用（需登录）：**
```
GET /api/users
  → 用户信息：name, email, provider, uid

GET /api/users/enter?goods_code=&place_code=
  → 购票凭证（关键！）:
    - interparkMemId: 930008647328
    - enterMemberId: "TP@@930008647328"
    - enterMemberNo: "T61631915"
    - enterEncryptVal: "cVksmeLfqu7g..." (加密值，下单需要)
    - enterHasEkyc: true/false
    - enterEkyc.status: "created" | "approved" | "rejected"

GET /api/biz/enter/reservations?languageType=CN&memberType=0&searchStartDate=&searchEndDate=
  → 已有订单查询

GET /api/additional/preference
  → 用户偏好 (货币: USD)
```

**猜测但未验证（被 eKYC 拦住）：**
```
POST /api/biz/enter/booking
POST /api/ent-channel-out/v1/booking/create
POST /api/ent-channel-out/v1/booking/reserve
POST /api/booking/create
  → 下单接口，payload 猜测:
    {goodsCode, placeCode, bizCode, playDate, gradeIndex, ticketCount,
     memberId, memberNo, encryptVal, languageType}
```

### 3. 登录方案

- NOL 使用 Cloudflare Turnstile 验证码，headless 浏览器无法自动通过
- 解决方案: Cookie 注入法
  - 用户在真实浏览器登录 NOL
  - 用 Cookie-Editor 扩展导出 cookie
  - 关键 cookie: `access_token` (JWT, 5分钟有效期) + `refresh_token` (30天)
  - 注入到 Playwright context 或直接用 requests 调 API

### 4. eKYC 问题

- 音乐剧点击"立即购买"无反应，页面显示 "verify member only"
- 分析: 按钮 tabIndex=-1，JS 禁用了点击
- 原因: enterEkyc.status = "created"，未完成实名认证
- 结论: NOL 部分演出要求 eKYC，需用户在网站手动完成

### 5. 系统开发

**v1 (run.py):**
- 单文件全功能
- 4种模式: check / monitor / grab / test
- 钉钉 + 企微通知
- 自动日志

**v2 (auto_grabber.py):**
- 简化版，一键运行
- 自动检查 → 等待 → 抢票 → 通知

**v3 (v3/ 目录) — 完整版：**
- `core.py`: 核心引擎
  - 多账号并发 (NOLAccount + NOLGrabber)
  - 智能重试 (递增延迟 + 指数退避)
  - 代理轮换 (ProxyManager)
  - 反检测 (随机 UA / 随机延迟)
  - Token 自动刷新
  - 实时统计 (Stats: 延迟/成功率/TPS)
  - 精确倒计时 (SaleWaiter)
  - 多渠道通知 (Notifier: 钉钉/企微/Telegram)

- `server.py`: Web 服务器
  - Flask + Flask-SocketIO
  - REST API + WebSocket 实时推送
  - 在线配置修改

- `static/index.html`: 仪表盘
  - 暗色主题
  - 实时倒计时
  - 统计面板 (大数字 + 延迟范围)
  - 一键启动/停止
  - 账号检查
  - 在线配置
  - 实时日志流

- `grabber.py`: 命令行入口
- `Dockerfile` + `docker-compose.yml`: Docker 部署

### 6. GitHub 推送

- 使用用户提供的 Personal Access Token 推送
- ⚠️ 已提醒用户撤销泄露的 token

---

## ⚠️ 安全提醒

- 用户在聊天中泄露了 1 个 GitHub Personal Access Token，已建议撤销
- 用户在聊天中泄露了 NOL 账号密码和 JWT token
- token.json 已加入 .gitignore 或使用占位符，避免 token 入库

## 待办

- [ ] 用户完成 NOL eKYC 实名认证
- [ ] 如参加 4/29 粉丝预售，完成 Fan Club 会员验证
- [ ] 开售前获取新 token 填入 config
- [ ] 在海外 VPS 部署 (韩国/日本最佳，减少延迟)
- [ ] 撤销泄露的 GitHub token
- [ ] 验证 booking API 真实路径 (需 eKYC 通过后)
- [ ] 确认 BTS 演唱会座位档位 (需商品详情 API 可用)

## 关键文件清单

```
wvs-con-ticketing/
├── v3/                          ← v3 完整版 (本次新增)
│   ├── core.py                  核心引擎 (多账号/智能重试/代理/统计)
│   ├── server.py                Web 服务器 (Flask + WebSocket)
│   ├── grabber.py               命令行入口
│   ├── static/index.html        Web 仪表盘
│   ├── config.example.json      配置模板
│   ├── tokens.example.json      Token 模板
│   ├── requirements.txt         依赖
│   ├── Dockerfile               Docker 镜像
│   ├── docker-compose.yml       Docker 编排
│   └── README.md                说明文档
├── run.py                       v2 命令行版
├── auto_grabber.py              v2 简化版
├── nol_grabber.py               v1 详细版 (含 Playwright)
├── intercept_api.py             API 拦截分析工具
├── config.json                  配置文件
├── token.json                   Token 配置
├── CHAT_LOG.md                  第一次聊天记录
├── CHAT_LOG_2.md                ← 本文件 (第二次聊天记录)
├── backend/                     Flask 后端 (原有)
├── frontend/                    前端 (原有)
└── test_*.py                    测试脚本
```
