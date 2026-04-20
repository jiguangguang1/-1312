# NOL 抢票系统 v3 — 完整版

## 功能

- 🎫 **全自动抢票** — API 直调，毫秒级响应
- 👁️ **实时监控** — Web 仪表盘 + WebSocket 实时推送
- 👥 **多账号轮换** — 多 token 自动切换
- 🔄 **代理轮换** — 自动切换 IP
- 🔐 **Token 自动刷新** — 过期前自动续期
- ⏰ **精确定时** — 开售瞬间自动启动
- 📊 **统计面板** — 实时成功率、延迟、重试次数
- 🐳 **Docker 一键部署**
- 📱 **钉钉/企微/Telegram 通知**
- 🧪 **浏览器测试模式**

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp config.example.json config.json
cp tokens.example.json tokens.json
# 编辑 config.json 和 tokens.json

# 3. 运行
python3 server.py          # Web 模式 (推荐)
python3 grabber.py grab    # 命令行抢票
python3 grabber.py check   # 检查状态

# 4. Docker
docker compose up -d
```

## Web 仪表盘

访问 `http://localhost:8080` 查看实时状态

## 配置说明

见 `config.example.json` 注释
