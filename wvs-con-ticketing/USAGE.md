# 🎫 YAOLO Weverse Con 2026 抢票系统 — 使用说明

## 一、环境准备

### 系统要求
- Python 3.8+
- 操作系统：Linux / macOS / Windows

### 安装依赖

```bash
cd wvs-con-ticketing

# 安装 Python 依赖
pip install -r backend/requirements.txt

# 安装 Playwright 浏览器（首次）
playwright install chromium
```

> ⚠️ 如果系统提示 `externally-managed-environment`，加 `--break-system-packages` 参数，或使用虚拟环境：
> ```bash
> python3 -m venv venv
> source venv/bin/activate
> pip install -r backend/requirements.txt
> playwright install chromium
> ```

---

## 二、启动系统

### 方式一：一键启动（推荐）

```bash
cd wvs-con-ticketing
bash start.sh
```

### 方式二：手动启动

```bash
cd wvs-con-ticketing/backend

# 初始化数据库（首次运行）
python init_db.py

# 启动后端
python app.py
```

启动后输出：
```
🎫 Weverse Con 2026 抢票系统启动
📡 http://localhost:5000
👤 管理员: admin / admin123
```

### 打开前端

浏览器访问：**http://localhost:5000**

前端页面由 Flask 直接托管，无需额外启动静态服务。

---

## 三、使用流程

### 第 1 步：注册账号

1. 打开首页，点击右上角 **「登录」**
2. 切换到 **「注册」** 标签
3. 填写用户名、邮箱、密码（至少6位）
4. 点击注册，自动登录

### 第 2 步：配置 Interpark 凭证

1. 登录后点击右上角用户名进入 **「控制台」**
2. 展开 **「账号设置」** 区域
3. 填写：
   - **Interpark 账号** — 你在 tickets.interpark.com 的用户名
   - **Interpark 密码** — 对应密码
   - **Weverse ID** — 可选
   - **是否拥有预售资格** — 勾选后提交订单时会显示预售时间输入
4. 点击 **「保存设置」**

> 🔒 凭证仅存储在本地数据库，不会外传。抢票引擎启动时读取凭证登录 Interpark。

### 第 3 步：创建抢票订单

在控制台的 **「新建抢票订单」** 区域操作：

#### 3.1 选择模式

| 模式 | 说明 |
|------|------|
| 🔥 会员预售 | 有 Weverse 会员资格，需要填写预售时间 |
| 🎫 一般开售 | 公开售票，填写开售时间 |
| ⬆️ 升舱 | 已持有低等级票，自动检测高等级余票 |

#### 3.2 填写信息

| 字段 | 必填 | 说明 |
|------|------|------|
| 演出 URL | ✅ | 在 Interpark 上找到 Weverse Con 2026 演出页，复制完整 URL |
| 场次 | ✅ | Day 1 或 Day 2 |
| 并发标签页数 | ✅ | 1~6 个，推荐 4 个 |
| 会员预售时间 | 预售时必填 | 韩国时间 (KST = UTC+9)，格式 `2026-06-10 20:00:00` |
| 一般开售时间 | 公售时必填 | 同上 |
| 座位偏好 | ✅ | 按勾选顺序优先尝试，默认 VIP站 > VIP坐 > SR > R > S |
| 代理 | 可选 | `socks5://host:port` 或 `http://host:port` |

#### 3.3 提交

点击 **「创建抢票订单」**，订单状态变为 `pending`（待启动）。

### 第 4 步：启动抢票

在订单列表中找到目标订单，点击 **「🚀 启动」**。

系统行为：
1. 启动 Playwright 无头浏览器
2. 登录 Interpark（使用你配置的凭证）
3. 如果设置了开售时间，会精确倒计时到开售前 3 秒
4. 开售瞬间，多个标签页同时点击「예매하기」（预约按钮）
5. 自动选择座位等级（按你设的偏好顺序）
6. 自动选座 / 系统分配
7. 处理验证码（截图保存，需手动处理）
8. 提交订单
9. 检查结果，成功时发出声音提醒

### 第 5 步：查看结果

- 订单列表实时显示状态徽章
- 点击 **「📋 详情」** 查看完整运行日志
- 成功的订单会显示 **订单号**
- 截图保存在 `screenshots/` 目录

---

## 四、管理员后台

默认管理员账号：`admin` / `admin123`

登录后导航栏会出现 **「管理」** 入口。

### 功能

| 功能 | 说明 |
|------|------|
| 统计面板 | 用户总数、订单总数、各状态计数 |
| 所有订单 | 全局查看所有用户订单，支持状态筛选和修改 |
| 用户列表 | 查看所有注册用户信息 |

---

## 五、API 接口一览

所有接口前缀：`http://localhost:5000`

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 `{username, email, password}` |
| POST | `/api/auth/login` | 登录 `{username, password}` → 返回 JWT |
| GET | `/api/auth/me` | 获取当前用户信息（需 Bearer Token） |
| PUT | `/api/auth/profile` | 更新凭证 `{interpark_id, interpark_pw, ...}` |

### 订单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/orders` | 我的订单列表 `?status=&page=&per_page=` |
| POST | `/api/orders` | 创建订单 |
| GET | `/api/orders/:id` | 订单详情（含日志） |
| PUT | `/api/orders/:id` | 修改订单（仅 pending 状态） |
| DELETE | `/api/orders/:id` | 删除订单 |
| POST | `/api/orders/:id/start` | 启动抢票引擎 |
| GET | `/api/orders/:id/logs` | 订单运行日志 |

### 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/dashboard` | 统计概览 |
| GET | `/api/admin/users` | 用户列表 |
| GET | `/api/admin/orders` | 所有订单 `?status=` |
| PUT | `/api/admin/orders/:id/status` | 修改订单状态 |

---

## 六、配置文件参考

首次使用可以创建 `wvs_con_config.json` 用于 CLI 模式：

```json
{
  "interpark_id": "your_id",
  "interpark_pw": "your_password",
  "weverse_id": "your_weverse_id",
  "has_presale": true,
  "perf_url": "https://tickets.interpark.com/goods/12345",
  "schedule_index": 0,
  "seat_prefs": [0, 1, 2, 3, 4],
  "open_time": "2026-06-14 20:00:00",
  "presale_time": "2026-06-10 20:00:00",
  "pre_open_sec": 3,
  "headless": false,
  "tab_count": 4,
  "page_timeout": 10000,
  "max_click_retries": 100,
  "click_delay": 0.05,
  "proxy": ""
}
```

### CLI 模式（不用 Web 界面）

```bash
cd wvs-con-ticketing/backend

# 保存登录态（首次）
python -m grabber.engine --login-only -c wvs_con_config.json

# 会员预售抢票
python -m grabber.engine -c wvs_con_config.json --time "2026-06-10 20:00:00"

# 一般开售，6个标签页
python -m grabber.engine -c wvs_con_config.json --time "2026-06-14 20:00:00" --tabs 6
```

> CLI 模式直接调用原版 `wvs_con.py` 的核心逻辑，无需启动 Web 服务。

---

## 七、座位等级说明

| 代号 | 等级 | 说明 |
|------|------|------|
| 0 | VIP 站席 | 最贵，最靠近舞台 |
| 1 | VIP 坐席 | 有座位的 VIP 区 |
| 2 | SR | 次高等级 |
| 3 | R | 中等偏上 |
| 4 | S | 中等 |
| 5 | A | 最便宜 |

系统按你勾选的顺序从高到低尝试，某等级售罄自动跳到下一个。

---

## 八、常见问题

### Q: 登录 Interpark 失败怎么办？
A: 可能遇到验证码或二次认证。Web 界面模式下，把 `headless` 设为 `false`（默认），浏览器窗口会弹出，手动完成登录后系统会保存登录态。

### Q: 抢票时遇到验证码？
A: 系统会自动截图保存到 `screenshots/` 目录，日志中会提示。无头模式下需要手动在浏览器中输入。

### Q: 可以同时抢多场吗？
A: 可以，创建多个不同场次的订单分别启动即可。

### Q: 代理怎么配？
A: 如果你在国内访问 Interpark 慢，可以配置韩国代理：`socks5://kr-proxy.example.com:1080`

### Q: 前端页面打不开？
A: 确认后端已启动（`python app.py`），浏览器访问 `http://localhost:5000`。如果改了端口，需要修改 `frontend/js/api.js` 中的 `API.BASE` 地址。

### Q: 抢票成功后怎么确认？
A: 系统会在抢票成功时：
1. 发出声音提醒（5 次 beep）
2. 自动截图保存到 `screenshots/`
3. 提取订单号显示在界面上
4. 你需要在 30 分钟内登录 Interpark 完成付款

---

## 九、目录结构

```
wvs-con-ticketing/
├── start.sh                    # 一键启动
├── README.md                   # 项目说明
├── USAGE.md                    # ← 你正在看的文件
├── backend/
│   ├── app.py                  # Flask 主应用
│   ├── config.py               # 配置
│   ├── models.py               # 数据库模型
│   ├── auth.py                 # JWT 认证
│   ├── init_db.py              # 数据库初始化
│   ├── requirements.txt        # Python 依赖
│   ├── wvs.db                  # SQLite 数据库（运行后生成）
│   ├── grabber/
│   │   ├── engine.py           # 🎯 核心抢票引擎
│   │   └── scheduler.py        # 定时调度
│   └── routes/
│       ├── orders.py           # 订单 API
│       └── admin.py            # 管理 API
├── frontend/
│   ├── index.html              # 首页
│   ├── dashboard.html          # 控制台
│   ├── admin.html              # 管理后台
│   ├── css/style.css           # 样式
│   └── js/
│       ├── api.js              # API 客户端
│       ├── auth.js             # 认证
│       ├── app.js              # 首页
│       ├── dashboard.js        # 控制台
│       └── admin.js            # 管理
├── screenshots/                # 抢票截图（运行后生成）
└── logs/                       # 运行日志（运行后生成）
```

---

## 十、免责声明

本系统仅供学习研究使用。自动化抢票可能违反 Interpark 的服务条款，使用前请自行评估风险。开发者不对因使用本系统导致的任何损失负责。
