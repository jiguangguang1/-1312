# YAOLO Weverse Con 2026 抢票系统 v2 — 开发记录

> 日期: 2026-04-20  
> 参与者: 用户 + AI 助手  
> 仓库: https://github.com/jiguangguang1/-1312

---

## 一、项目概述

这是一个 Weverse Con 2026 的自动抢票系统，包含：
- **前端**: HTML5 + CSS3 + Vanilla JS（响应式 Web 界面）
- **后端**: Flask + SQLAlchemy + Flask-JWT-Extended
- **抢票引擎**: Playwright (Chromium) + asyncio 异步并发
- **数据库**: SQLite（开发）/ PostgreSQL（生产）

## 二、开发过程

### 阶段 1：文件提取
用户上传了一个 `.txt` 文件，实际是 tar 归档（文本形式传输）。用 Python 脚本解析 `ustar` 标记，按行号切分提取了 24 个项目文件。部分文件首行残留 tar header 元数据，用正则清理。

### 阶段 2：代码审查（发现 7 个 Bug）

| # | 文件 | 问题 | 修复方式 |
|---|------|------|----------|
| 1 | dashboard.js | `event.target` 未传参 | `switchOrderTab(tab, el)` + HTML 传 `this` |
| 2 | dashboard.js | `openTime` 赋值被覆盖（死代码） | 精简为一行 |
| 3 | app.py | `static_folder` 用相对路径 | `os.path.join(_base, '..', 'frontend')` |
| 4 | 6 个文件 | `db.get()` 已弃用 | 全部改为 `db.session.get()` |
| 5 | app.py | `create_access_token(identity=int)` | 改为 `str(user.id)` + `int()` 反转 |
| 6 | requirements.txt | flask-sock、APScheduler 未使用 | 移除 |
| 7 | config.py | SECRET_KEY 硬编码 | `secrets.token_hex(32)` |

**关键 Bug 详情：JWT identity 类型问题**
- `flask-jwt-extended 4.x` 要求 `create_access_token(identity=...)` 必须传 string
- 原代码传了 `user.id`（int），导致 `decode_token` 抛 `Subject must be string`
- 所有需要认证的请求都返回 401
- 修复：`identity=str(user.id)` + 所有 `get_jwt_identity()` 返回值加 `int()` 转换

### 阶段 3：新增功能（用户发了 5 张截图作为参考）

用户发了 5 张截图，包含：
1. 一个 `TicketManager` / `TicketClass` / `TicketType` 的代码结构
2. 座位选择页面（价格档位 + 可选/售罄状态）
3. 场次选择页面（日期/时间/状态列表）
4. 可视化座位地图（分区网格）
5. 确认下单页面（倒计时 + 总价）

**新增的 12 个功能：**

| # | 功能 | 涉及文件 |
|---|------|----------|
| 1 | TicketClass 座位配置模型 | models.py |
| 2 | 座位配置 CRUD API | app.py, routes/admin.py |
| 3 | TicketManager 管理类 | engine.py |
| 4 | TicketType 档位类 | engine.py |
| 5 | AsyncGrabberEngine 异步引擎 | engine.py |
| 6 | 管理后台座位配置 Tab | admin.html, admin.js |
| 7 | 倒计时器 | dashboard.html, dashboard.js |
| 8 | 座位选择器增强（动态加载/价格/售罄） | dashboard.js |
| 9 | 场次选择列表 | dashboard.html |
| 10 | 可视化座位地图 | dashboard.html, style.css |
| 11 | 确认下单弹窗 | dashboard.html, dashboard.js |
| 12 | 默认 6 个档位自动初始化 | app.py, init_db.py |

### 阶段 4：测试
- 15 项 API 测试全部通过
- Python 编译检查 11/11 通过
- HTML 标签对称性检查通过
- JS 函数定义完整性检查通过

### 阶段 5：部署
- 添加 `Dockerfile` + `docker-compose.yml`
- 添加 `.env.example` 环境配置模板
- 更新 `README.md` 完整文档
- Git 提交并推送到 GitHub

## 三、最终项目结构

```
wvs-con-ticketing/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── start.sh
├── README.md
├── USAGE.md
├── backend/
│   ├── app.py              # Flask 主应用 (28 API 端点)
│   ├── auth.py             # JWT 认证装饰器
│   ├── config.py           # 配置（环境变量驱动）
│   ├── init_db.py          # 数据库初始化 + 默认档位
│   ├── models.py           # User, Order, TicketClass, OrderLog, SystemStatus
│   ├── requirements.txt
│   ├── grabber/
│   │   ├── engine.py       # GrabberEngine + AsyncGrabberEngine + TicketManager + TicketType
│   │   ├── scheduler.py    # 定时调度
│   │   └── __init__.py
│   └── routes/
│       ├── orders.py       # 订单 API
│       ├── admin.py        # 管理 API
│       └── __init__.py
├── frontend/
│   ├── index.html          # 首页
│   ├── dashboard.html      # 控制台（场次列表/座位地图/倒计时/确认弹窗）
│   ├── admin.html          # 管理后台（订单/用户/座位配置）
│   ├── css/style.css       # 全局样式
│   └── js/
│       ├── api.js          # API 客户端（含 TicketClass API）
│       ├── auth.js         # 认证
│       ├── app.js          # 首页逻辑
│       ├── dashboard.js    # 控制台（倒计时/地图联动/确认弹窗）
│       └── admin.js        # 管理（座位配置 CRUD）
└── logs/
└── screenshots/
```

## 四、API 端点清单（28 个）

### 认证 (4)
- `POST /api/auth/register` — 注册
- `POST /api/auth/login` — 登录
- `GET /api/auth/me` — 当前用户
- `PUT /api/auth/profile` — 更新凭证

### 订单 (7)
- `GET /api/orders` — 列表
- `POST /api/orders` — 创建
- `GET /api/orders/:id` — 详情
- `PUT /api/orders/:id` — 编辑
- `DELETE /api/orders/:id` — 删除
- `POST /api/orders/:id/start` — 启动抢票
- `GET /api/orders/:id/logs` — 日志

### 座位配置 (4)
- `GET /api/ticket-classes` — 查看
- `POST /api/ticket-classes` — 创建
- `PUT /api/ticket-classes/:id` — 更新
- `DELETE /api/ticket-classes/:id` — 删除

### 管理 (6)
- `GET /api/admin/dashboard` — 统计面板
- `GET /api/admin/users` — 用户列表
- `GET /api/admin/orders` — 所有订单
- `PUT /api/admin/orders/:id/status` — 修改订单状态
- `GET /api/admin/ticket-classes` — 所有档位
- `PUT /api/admin/ticket-classes/:id/status` — 售罄/在售

### 其他 (2)
- `GET /api/health` — 健康检查
- `GET /` `/dashboard` `/admin` — 前端页面

## 五、关键代码片段

### JWT 修复
```python
# 注册/登录
token = create_access_token(identity=str(user.id))

# 使用
user_id = int(get_jwt_identity())
```

### TicketManager 模式
```python
class TicketManager:
    def __init__(self):
        self.map: Dict[int, TicketType] = {}

    def add(self, grade_index, name, price, ticket_per_person=1):
        tt = TicketType(grade_index, name, price, ticket_per_person)
        self.map[grade_index] = tt
        return tt

    def available_types(self):
        return [tt for tt in self.map.values() if tt.available and not tt.is_sold_out]
```

### AsyncGrabberEngine
```python
class AsyncGrabberEngine:
    def __init__(self, order_id, config, db_session=None):
        self.manager = TicketManager()

    async def run_async(self, target_time=None):
        # 等待开售
        # 调度所有档位
        self.schedule()
        # asyncio.wait(FIRST_COMPLETED)
        tasks = [tt.register() for tt in self.manager.available_types() if tt._workers]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
```

## 六、默认座位档位

| 图标 | 名称 | 价格 | 颜色 |
|------|------|------|------|
| 🔥 | VIP 站席 | ₩154,000 | #ef4444 |
| 👑 | VIP 坐席 | ₩154,000 | #f97316 |
| ⭐ | SR석 | ₩132,000 | #eab308 |
| 💎 | R석 | ₩99,000 | #22c55e |
| 🎵 | S석 | ₩110,000 | #3b82f6 |
| 🎶 | A석 | ₩88,000 | #8b5cf6 |

## 七、启动方式

### 本地
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

访问 http://localhost:5000  
管理员：admin / admin123

## 八、Git 提交历史

```
023e9ab chore: Docker部署 + 更新文档 + 环境配置模板
b681f06 feat: wvs-con-ticketing v2 - 优化+新增座位配置/倒计时/异步引擎
```

## 九、注意事项

1. **安全**: `admin123` 是默认密码，生产环境必须通过 `ADMIN_PASSWORD` 环境变量修改
2. **JWT**: `flask-jwt-extended 4.x` 的 `identity` 必须是 string
3. **SQLite**: 开发用 SQLite，生产建议 PostgreSQL
4. **Playwright**: 需要先 `playwright install chromium` 安装浏览器
5. **端口**: 默认 5000，可在 `app.py` 最后一行修改
