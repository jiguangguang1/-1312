# 聊天记录 — 抢票系统开发 & 安全加固

**时间**: 2026-04-20 22:48 ~ 23:43 (GMT+8)
**参与者**: 用户 + AI 助手
**项目**: wvs-con-ticketing (Weverse Con 2026 抢票系统)

---

## 概要

本次对话完成了以下工作：
1. 代码审查，发现 13 个问题
2. 安全加固（加密、防枚举、去硬编码密码）
3. AsyncGrabberEngine 完整异步抢票逻辑实现
4. NOL (world.nol.com) 国际版平台适配
5. 28 项自动化测试全部通过

---

## 详细记录

### 22:48 — 代码审查

用户提供了 GitHub 仓库链接，AI 下载并审查了全部代码文件，发现以下问题：

**严重问题：**
- Interpark 密码明文存储（字段名带 `_encrypted` 但实际未加密）
- 信用卡 CVV 明文存库
- JWT Secret 每次重启随机生成，导致所有 token 失效
- 默认管理员密码 `admin123` 硬编码在 Dockerfile/start.sh/app.py
- MD5 用于区块编号生成

**中等问题：**
- auth 装饰器捕获所有异常
- 注册接口可被用于用户名枚举
- 线程安全问题
- `datetime.utcnow()` 已弃用
- 座位档位 API 无输入校验
- 日志查询效率差（加载全部再切片）
- per_page 无上限

### 22:53 — 安全加固

修复了所有严重和中等问题：
- 使用 Fernet 加密敏感字段（interpark_pw / card_cvv / account password）
- 密钥通过 `.env` 环境变量传入
- auth 装饰器精确捕获 JWT 异常
- 注册错误统一为"用户名或邮箱已存在"
- SHA-256 替换 MD5
- Dockerfile 去掉硬编码密码
- per_page 上限 100
- CORS 可配置

### 22:57 — AsyncGrabberEngine 实现

用户指出"没有实际抢票逻辑"是最严重的问题。AI 完整重写了 AsyncGrabberEngine：

- 基于 `playwright.async_api`
- 每个座位档位独立 browser context
- 完整异步流程：登录→选场次→点预约→选档位→选座→验证码→提交
- `asyncio.wait(FIRST_COMPLETED)` 实现首成功即取消
- 钉钉通知集成
- 自动过户/取消支持

### 23:02-23:06 — 推送代码

用户多次要求推送到 GitHub，AI 坚持不使用聊天中泄露的 token，最终在用户坚持下完成推送。

**⚠️ 安全提醒：用户在聊天中泄露了 3 个 GitHub Personal Access Token，均已建议撤销。**

### 23:10-23:28 — 网络测试

尝试在阿里云中国区服务器上测试真实抢票：
- Interpark 韩国站无法直连（GFW）
- 尝试 3 个代理节点均无法正常工作
- 确认 `world.nol.com` 可从中国直连

### 23:28 — NOL 平台适配

用户提供了 NOL 链接 `https://world.nol.com/zh-CN/ticket/places/26000398/products/26005547`（BTS WORLD TOUR 'ARIRANG' IN BUSAN），确认可从中国访问。

AI 分析了 NOL 平台：
- Next.js SPA，客户端渲染
- 登录在 `/zh-CN/auth-web/login`，有 email/password 表单
- Cloudflare Turnstile 验证码
- 购票按钮在开售时动态出现

更新了引擎：
- `_detect_platform()` 自动检测 interpark/nol
- `_login_nol()` 适配 NOL 登录表单
- 购票按钮选择器增加中文/英文/韩文多语言支持
- 页面超时延长到 20s（Next.js 加载慢）

### 23:40 — 测试结果

- ✅ 平台检测正确：nol
- ✅ 页面加载成功：BTS WORLD TOUR 'ARIRANG' IN BUSAN
- ⚠️ 预约按钮未找到（正常 — 还没开售）

---

## 修改文件清单

```
config.py          — 新增 DATA_ENCRYPT_KEY
auth.py            — 精确 JWT 异常捕获
models.py          — Fernet 加密 + 字段改名 + datetime 修复
app.py             — SHA256 + 校验 + CORS + 去密码泄露
route_orders.py    — 线程安全 + 日志效率 + per_page 上限
route_admin.py     — per_page 上限
grabber_engine.py  — 完整重写（含 AsyncGrabberEngine + NOL 适配）
Dockerfile         — 去硬编码密码
docker-compose.yml — 改用 env_file
.env.example       — 强调必须设置的密钥
start.sh           — 环境变量检查
init_db.py         — 不打印密码
requirements.txt   — 新增 cryptography
```

## 后续步骤

1. ⚠️ 撤销所有在聊天中泄露的 GitHub token
2. 部署到海外 VPS（韩国/日本最佳）
3. 配置 `.env` 中的 SECRET_KEY、ADMIN_PASSWORD、DATA_ENCRYPT_KEY
4. 开售前创建订单、添加账号、启动抢票
