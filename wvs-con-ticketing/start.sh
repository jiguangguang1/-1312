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

# 初始化数据库
echo "🗄️ 初始化数据库..."
cd backend
python3 init_db.py

# 启动后端
echo ""
echo "🚀 启动后端服务..."
echo "📡 http://localhost:5000"
echo "👤 管理员: admin / admin123"
echo ""
python3 app.py
