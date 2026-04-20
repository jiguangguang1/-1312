FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

# 复制代码
COPY . .

# 创建数据目录
RUN mkdir -p logs screenshots

EXPOSE 5000

ENV FLASK_ENV=production
ENV ADMIN_PASSWORD=admin123

HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["python3", "backend/app.py"]
