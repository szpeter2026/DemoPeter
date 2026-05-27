# szpeter2026 知识库 - 生产环境镜像
# 构建: docker build -t szpeter2026-web .
# 运行: docker compose up -d

FROM python:3.12-slim

# 系统依赖（pdfplumber 需要 libstdc++ 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0

# 复制项目代码
COPY . .

# 配置文件由 docker-compose 挂载或环境变量注入
# .env 不要打进镜像，通过 docker-compose env_file 或 environment 传入

EXPOSE 5200

# 使用 Gunicorn 运行 Flask（生产模式）
# workers 数量建议：2 * CPU + 1，小规格 ECS 用 2 即可
CMD ["gunicorn", "--bind", "0.0.0.0:5200", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "src.web_dashboard:app"]
