#!/bin/bash
# 启动/重启服务脚本
# 用法: ./start_all.sh [all|fastapi|streamlit|telegram|tunnel]  或  ./start_all.sh restart <服务名>
# 示例: ./start_all.sh              # 启动全部
#       ./start_all.sh fastapi       # 仅启动 FastAPI
#       ./start_all.sh restart streamlit   # 重启 Streamlit

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 确定使用的 Python：优先虚拟环境
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_CMD="$VIRTUAL_ENV/bin/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
else
    PYTHON_CMD="python3"
fi

mkdir -p logs

# ---------- 停止服务（按端口或进程名）----------
stop_fastapi() {
    local pid=$(lsof -ti :8000 2>/dev/null)
    if [ -n "$pid" ]; then
        kill $pid 2>/dev/null
        sleep 1
        kill -9 $pid 2>/dev/null
        echo -e "${YELLOW}已停止 FastAPI (PID: $pid)${NC}"
    fi
}
stop_streamlit() {
    local pid=$(lsof -ti :8501 2>/dev/null)
    if [ -n "$pid" ]; then
        kill $pid 2>/dev/null
        sleep 1
        kill -9 $pid 2>/dev/null
        echo -e "${YELLOW}已停止 Streamlit (PID: $pid)${NC}"
    fi
}
stop_telegram() {
    pkill -f "start_telegram_bot.py" 2>/dev/null && echo -e "${YELLOW}已停止 Telegram Bot${NC}" || true
}
stop_tunnel() {
    pkill -f "cloudflared tunnel" 2>/dev/null && echo -e "${YELLOW}已停止 Cloudflare Tunnel${NC}" || true
}

# 将 Tunnel 的 webhook URL 写入数据库，供 Teams 等使用
save_tunnel_url_to_db() {
    local url="$1"
    [ -z "$url" ] && return 1
    export TUNNEL_URL_TO_SAVE="$url"
    $PYTHON_CMD -c "
import os, sys
sys.path.insert(0, '.')
from app.utils.tunnel_url_saver import save_webhook_url
url = os.environ.get('TUNNEL_URL_TO_SAVE', '')
ok = bool(url and save_webhook_url(url))
sys.exit(0 if ok else 1)
" 2>/dev/null && return 0 || return 1
}

# ---------- 启动单个服务 ----------
start_fastapi() {
    echo -e "\n${GREEN}启动 FastAPI (端口8000)...${NC}"
    $PYTHON_CMD main.py > logs/fastapi.log 2>&1 &
    sleep 2
    if lsof -ti :8000 >/dev/null 2>&1; then
        echo -e "${GREEN}✅ FastAPI 已启动${NC}"
        return 0
    else
        echo -e "${RED}❌ FastAPI 启动失败，查看 logs/fastapi.log${NC}"
        return 1
    fi
}
start_streamlit() {
    echo -e "\n${GREEN}启动 Streamlit (端口8501)...${NC}"
    $PYTHON_CMD -m streamlit run app/admin/dashboard.py --server.port 8501 --server.address 0.0.0.0 > logs/streamlit.log 2>&1 &
    sleep 3
    if lsof -ti :8501 >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Streamlit 已启动${NC}"
        return 0
    else
        echo -e "${RED}❌ Streamlit 启动失败，查看 logs/streamlit.log${NC}"
        return 1
    fi
}
start_telegram() {
    echo -e "\n${GREEN}启动 Telegram Bot...${NC}"
    $PYTHON_CMD start_telegram_bot.py > logs/telegram_bot.log 2>&1 &
    # 最多等待约 20 秒，期间持续检查是否超时/配置失败
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 2
        # 进程已经退出，视为启动失败
        if ! pgrep -f "start_telegram_bot.py" >/dev/null 2>&1; then
            echo -e "${RED}❌ Telegram Bot 启动失败或已退出，查看 logs/telegram_bot.log${NC}"
            return 1
        fi
        # 日志中出现运行错误 / 超时 / 未配置提示，也视为启动失败
        if grep -E "Telegram Bot运行错误|Timed out|未配置或初始化失败|连接验证失败" logs/telegram_bot.log >/dev/null 2>&1; then
            echo -e "${RED}❌ Telegram Bot 启动失败（网络/配置异常），查看 logs/telegram_bot.log${NC}"
            return 1
        fi
    done
    # 超过等待时间仍在运行且无错误日志，认为启动成功
    if pgrep -f "start_telegram_bot.py" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Telegram Bot 已启动${NC}"
        return 0
    fi
    echo -e "${RED}❌ Telegram Bot 启动状态未知，请查看 logs/telegram_bot.log${NC}"
    return 1
}
start_tunnel() {
    echo -e "\n${GREEN}启动 Cloudflare Tunnel...${NC}"
    if ! command -v cloudflared &>/dev/null; then
        echo -e "${YELLOW}⚠️  cloudflared 未找到，请安装: brew install cloudflared${NC}"
        return 1
    fi
    cloudflared tunnel --url http://localhost:8000 > logs/tunnel.log 2>&1 &
    local pid=$!
    TUNNEL_URL=""
    for _ in 1 2 3 4 5 6 7 8; do
        sleep 2
        TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' logs/tunnel.log 2>/dev/null | tail -1)
        [ -n "$TUNNEL_URL" ] && break
    done
    if ps -p $pid >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Cloudflare Tunnel 已启动 (PID: $pid)${NC}"
        if [ -n "$TUNNEL_URL" ]; then
            echo -e "   公网地址: ${TUNNEL_URL}   Webhook: ${TUNNEL_URL}/api/teams/messages"
            save_tunnel_url_to_db "$TUNNEL_URL" && echo -e "   ${GREEN}✓ 新 Webhook 已写入数据库${NC}"
        fi
        return 0
    else
        echo -e "${YELLOW}⚠️  Tunnel 启动失败，查看 logs/tunnel.log${NC}"
        return 1
    fi
}

# ---------- 解析参数 ----------
MODE="${1:-all}"
SVC="${2:-}"

if [ "$MODE" = "restart" ]; then
    if [ -z "$SVC" ]; then
        echo "用法: $0 restart <fastapi|streamlit|telegram|tunnel>"
        exit 1
    fi
    case "$SVC" in
        fastapi|api)   stop_fastapi;   start_fastapi ;;
        streamlit|st)  stop_streamlit; start_streamlit ;;
        telegram|tg)   stop_telegram;  start_telegram ;;
        tunnel)        stop_tunnel;    start_tunnel ;;
        *)             echo "未知服务: $SVC"; exit 1 ;;
    esac
    exit 0
fi

# 仅启动单个服务（不重启）
if [ "$MODE" != "all" ]; then
    case "$MODE" in
        fastapi|api)   start_fastapi ;;
        streamlit|st)  start_streamlit ;;
        telegram|tg)   start_telegram ;;
        tunnel)        start_tunnel ;;
        -h|--help)
            echo "用法: $0 [all|fastapi|streamlit|telegram|tunnel]"
            echo "      $0 restart <fastapi|streamlit|telegram|tunnel>"
            echo "  all       - 启动全部服务（默认）"
            echo "  fastapi   - 仅启动 FastAPI (8000)"
            echo "  streamlit - 仅启动 Streamlit (8501)"
            echo "  telegram  - 仅启动 Telegram Bot"
            echo "  tunnel    - 仅启动 Cloudflare Tunnel"
            exit 0 ;;
        *)
            echo "未知选项: $MODE"
            echo "使用 $0 --help 查看用法"
            exit 1 ;;
    esac
    exit 0
fi

# ---------- 启动全部 ----------
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          IntelliKnow KMS - 启动所有服务                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

if [ -z "$VIRTUAL_ENV" ] && [ ! -f "venv/bin/python" ]; then
    echo -e "${YELLOW}⚠️  未检测到虚拟环境，使用系统 python3${NC}"
    read -p "   是否继续？(y/n): " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
fi

# Tunnel 询问放在最前面
echo -e "\n${GREEN}Cloudflare Tunnel (可选，用于暴露 API 到公网，Teams Bot 需要)${NC}"
read -p "   是否启动 Tunnel？(y/n，默认n): " -n 1 -r
echo
START_TUNNEL=0
[[ $REPLY =~ ^[Yy]$ ]] && START_TUNNEL=1

# 清理函数（仅“启动全部”时生效）：先 SIGTERM，短等后强制 kill -9，避免卡住
FASTAPI_PID= STREAMLIT_PID= TELEGRAM_PID= TUNNEL_PID=
cleanup() {
    echo -e "\n${YELLOW}正在停止所有服务...${NC}"
    kill $FASTAPI_PID $STREAMLIT_PID $TELEGRAM_PID $TUNNEL_PID 2>/dev/null
    sleep 1
    for p in $FASTAPI_PID $STREAMLIT_PID $TELEGRAM_PID $TUNNEL_PID; do
        [ -n "$p" ] && kill -9 "$p" 2>/dev/null || true
    done
    # 按端口再杀一次，防止子进程未退出（兼容 macOS，无 xargs -r）
    pid=$(lsof -ti :8000 2>/dev/null); [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
    pid=$(lsof -ti :8501 2>/dev/null); [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
    pkill -9 -f "start_telegram_bot.py" 2>/dev/null || true
    pkill -9 -f "cloudflared tunnel" 2>/dev/null || true
    echo -e "${GREEN}所有服务已停止${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# 1. FastAPI
echo -e "\n${GREEN}[1/4] FastAPI (端口8000)...${NC}"
$PYTHON_CMD main.py > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
sleep 3
if ps -p $FASTAPI_PID >/dev/null 2>&1; then
    echo -e "${GREEN}✅ FastAPI 已启动 (PID: $FASTAPI_PID)${NC}"
else
    echo -e "${RED}❌ FastAPI 启动失败，查看 logs/fastapi.log${NC}"
    exit 1
fi

# 2. Streamlit
echo -e "\n${GREEN}[2/4] Streamlit (端口8501)...${NC}"
$PYTHON_CMD -m streamlit run app/admin/dashboard.py --server.port 8501 --server.address 0.0.0.0 > logs/streamlit.log 2>&1 &
STREAMLIT_PID=$!
sleep 4
if ps -p $STREAMLIT_PID >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Streamlit 已启动 (PID: $STREAMLIT_PID)${NC}"
else
    echo -e "${YELLOW}⚠️  Streamlit 启动失败，继续${NC}"
fi

# 3. Telegram Bot
echo -e "\n${GREEN}[3/4] Telegram Bot...${NC}"
$PYTHON_CMD start_telegram_bot.py > logs/telegram_bot.log 2>&1 &
TELEGRAM_PID=$!
TELEGRAM_OK=1
# 最多等待约 20 秒监控启动情况
for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 2
    # 进程已经退出，视为启动失败
    if ! ps -p $TELEGRAM_PID >/dev/null 2>&1; then
        echo -e "${RED}❌ Telegram Bot 启动失败或已退出，查看 logs/telegram_bot.log${NC}"
        TELEGRAM_OK=0
        break
    fi
    # 日志中出现运行错误 / 超时 / 未配置提示，也视为启动失败
    if grep -E "Telegram Bot运行错误|Timed out|未配置或初始化失败|连接验证失败" logs/telegram_bot.log >/dev/null 2>&1; then
        echo -e "${RED}❌ Telegram Bot 启动失败（网络/配置异常），查看 logs/telegram_bot.log${NC}"
        TELEGRAM_OK=0
        break
    fi
done
if [ "$TELEGRAM_OK" -eq 1 ]; then
    if ps -p $TELEGRAM_PID >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Telegram Bot 已启动 (PID: $TELEGRAM_PID)${NC}"
    else
        echo -e "${RED}❌ Telegram Bot 启动状态未知，请查看 logs/telegram_bot.log${NC}"
    fi
fi

# 4. Cloudflare Tunnel（根据开头选择）
echo -e "\n${GREEN}[4/4] Cloudflare Tunnel${NC}"
if [ "$START_TUNNEL" = "1" ]; then
    if command -v cloudflared &>/dev/null; then
        cloudflared tunnel --url http://localhost:8000 > logs/tunnel.log 2>&1 &
        TUNNEL_PID=$!
        TUNNEL_URL=""
        for _ in 1 2 3 4 5 6 7 8; do
            sleep 2
            TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' logs/tunnel.log 2>/dev/null | tail -1)
            [ -n "$TUNNEL_URL" ] && break
        done
        if ps -p $TUNNEL_PID >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Cloudflare Tunnel 已启动 (PID: $TUNNEL_PID)${NC}"
            if [ -n "$TUNNEL_URL" ]; then
                echo -e "   公网: ${TUNNEL_URL}   Webhook: ${TUNNEL_URL}/api/teams/messages"
                if save_tunnel_url_to_db "$TUNNEL_URL"; then
                    echo -e "   ${GREEN}✓ 新 Webhook 已写入数据库，Teams 将使用此地址${NC}"
                else
                    echo -e "   ${YELLOW}⚠ 写入数据库失败，管理界面可能仍显示旧地址${NC}"
                fi
            else
                echo -e "   ${YELLOW}⚠ 未从日志解析到 URL，请稍后查看 logs/tunnel.log 或管理界面手动更新${NC}"
            fi
        else
            echo -e "${YELLOW}⚠️  Tunnel 启动失败，查看 logs/tunnel.log${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  cloudflared 未找到，跳过${NC}"
    fi
else
    echo "   跳过（已在开头选择不启动）"
fi

echo -e "\n${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ 所有服务已启动${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}\n"
echo "  FastAPI:     http://localhost:8000"
echo "  Streamlit:   http://localhost:8501"
echo "  日志目录:    logs/"
echo -e "\n按 ${RED}Ctrl+C${NC} 停止所有服务\n"

wait
