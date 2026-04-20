#!/bin/bash
# YAOLO Weverse Con 2026 抢票系统 — 启动脚本

set -e

echo "========================================="
echo "  🎫 YAOLO Weverse Con 2026 抢票系统"
echo "========================================="
echo ""

cd "$(dirname "$0")"

# 检查依赖
echo "📦 检查依赖..."
pip3 install -q -r backend/requirements.txt 2>/dev/null || pip3 install -r backend/requirements.txt

# 检查关键环境变量
if [ -z "$SECRET_KEY" ]; then
    echo "⚠️  警告: 未设置 SECRET_KEY，重启后所有登录将失效"
fi
if [ -z "$DATA_ENCRYPT_KEY" ]; then
    echo "⚠️  警告: 未设置 DATA_ENCRYPT_KEY，敏感数据加密不可靠"
fi
if [ "${ADMIN_PASSWORD:-admin123}" = "admin123" ]; then
    echo "⚠️  警告: 使用默认管理员密码，请通过 ADMIN_PASSWORD 环境变量修改！"
fi

# 初始化数据库
echo "🗄️ 初始化数据库..."
cd backend
python3 init_db.py

# 启动后端
echo ""
echo "🚀 启动后端服务..."
echo "📡 http://localhost:${PORT:-5000}"
echo ""
python3 app.py
