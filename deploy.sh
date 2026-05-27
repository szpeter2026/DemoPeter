#!/bin/bash
# ============================================================
# szpeter2026 知识库 — 阿里云 ECS 一键部署脚本
# ============================================================
# 用法（在阿里云 ECS 上执行）：
#   curl -fsSL https://raw.githubusercontent.com/szpeter2026/szpeter2026/main/deploy.sh | bash
#   或
#   git clone https://github.com/szpeter2026/szpeter2026.git
#   cd szpeter2026 && bash deploy.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  szpeter2026 阿里云部署脚本            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ---- 获取项目目录 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 1. 检查 Docker ----
echo -e "${YELLOW}[1/5] 检查 Docker...${NC}"
if ! command -v docker &>/dev/null; then
    echo -e "${YELLOW}       安装 Docker...${NC}"
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
    echo -e "${GREEN}       Docker 安装完成${NC}"
else
    echo -e "${GREEN}       Docker 已安装${NC}"
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo -e "${YELLOW}       Docker Compose 插件未安装，正在安装...${NC}"
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin
fi
echo -e "${GREEN}       Docker Compose 就绪${NC}"

# ---- 2. 检查 .env.production ----
echo -e "${YELLOW}[2/5] 检查配置文件...${NC}"
if [ ! -f ".env.production" ]; then
    if [ -f ".env.production.example" ]; then
        cp .env.production.example .env.production
        echo -e "${RED}       ⚠ 已创建 .env.production 模板，请编辑后再运行！${NC}"
        echo -e "${RED}       vi .env.production  ← 修改 DEEPSEEK_API_KEY 等配置${NC}"
        exit 1
    else
        echo -e "${RED}       未找到 .env.production，请手动创建${NC}"
        exit 1
    fi
else
    # 检查 API Key 是否还是默认值
    if grep -q "你的DeepSeek_API_Key" .env.production 2>/dev/null; then
        echo -e "${RED}       ⚠ .env.production 中 API Key 未配置！${NC}"
        echo -e "${RED}       vi .env.production  ← 修改 DEEPSEEK_API_KEY${NC}"
        exit 1
    fi
    echo -e "${GREEN}       配置文件就绪${NC}"
fi

# ---- 3. 创建必要目录 ----
echo -e "${YELLOW}[3/5] 创建数据目录...${NC}"
mkdir -p db/chroma_docker db/pgdata db/pg-init
echo -e "${GREEN}       目录就绪${NC}"

# ---- 4. 拉取镜像并启动 ----
echo -e "${YELLOW}[4/5] 构建并启动服务...${NC}"
docker compose --env-file .env.production up -d --build
echo -e "${GREEN}       服务已启动${NC}"

# ---- 5. 验证 ----
echo -e "${YELLOW}[5/5] 验证部署...${NC}"
sleep 3

# 检查各容器状态
for svc in nginx web chroma; do
    if docker ps --format '{{.Names}}' | grep -q "szpeter2026-$svc"; then
        echo -e "${GREEN}       ✅ $svc 运行中${NC}"
    else
        echo -e "${RED}       ❌ $svc 未运行${NC}"
    fi
done

# 获取服务器公网 IP
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "你的服务器IP")

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  部署完成！                            ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║  访问地址: http://${SERVER_IP}          ${NC}"
echo -e "${CYAN}║  查看日志: docker compose logs -f web   ${NC}"
echo -e "${CYAN}║  重启服务: docker compose restart web   ${NC}"
echo -e "${CYAN}║  停止所有: docker compose down          ${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""
