#!/bin/bash
# 启动所有服务脚本（支持单独重启服务）

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# PID文件目录
PID_DIR="logs/pids"
mkdir -p "$PID_DIR"

# 服务名称定义
SERVICES=("fastapi" "streamlit" "telegram" "tunnel")
SERVICE_NAMES=("FastAPI主服务" "Streamlit管理界面" "Telegram Bot" "Cloudflare Tunnel")
SERVICE_SCRIPTS=("main.py" "app/admin/dashboard.py" "start_telegram_bot.py" "start_tunnel_with_save.py")
SERVICE_PORTS=("8000" "8501" "" "")

# 保存PID到文件
save_pid() {
    local service=$1
    local pid=$2
    echo "$pid" > "$PID_DIR/${service}.pid"
}

# 读取PID从文件
read_pid() {
    local service=$1
    if [ -f "$PID_DIR/${service}.pid" ]; then
        cat "$PID_DIR/${service}.pid"
    fi
}

# 检查服务是否运行
is_running() {
    local pid=$1
    [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1
}

# 停止单个服务
stop_service() {
    local service=$1
    local pid=$(read_pid "$service")
    local pids_to_kill=()
    
    # 根据服务类型查找进程
    case $service in
        0) # FastAPI
            if [ -n "$pid" ] && is_running "$pid"; then
                pids_to_kill+=("$pid")
            fi
            # 通过端口查找（兼容 macOS 和 Linux）
            if command -v lsof &> /dev/null; then
                local port_pid=$(lsof -ti:8000 2>/dev/null)
                if [ -n "$port_pid" ] && [ "$port_pid" != "$pid" ]; then
                    pids_to_kill+=("$port_pid")
                fi
            fi
            # 查找所有 main.py 进程
            while IFS= read -r line; do
                local fastapi_pid=$(echo "$line" | awk '{print $2}')
                if [ -n "$fastapi_pid" ] && is_running "$fastapi_pid"; then
                    if ps -p "$fastapi_pid" -o command= 2>/dev/null | grep -q "main.py"; then
                        pids_to_kill+=("$fastapi_pid")
                    fi
                fi
            done < <(ps aux | grep "[m]ain.py" | grep -v grep 2>/dev/null)
            ;;
        1) # Streamlit
            if [ -n "$pid" ] && is_running "$pid"; then
                pids_to_kill+=("$pid")
            fi
            # 通过端口查找（兼容 macOS 和 Linux）
            if command -v lsof &> /dev/null; then
                local port_pids=$(lsof -ti:8501 2>/dev/null)
                if [ -n "$port_pids" ]; then
                    for port_pid in $port_pids; do
                        if [ "$port_pid" != "$pid" ] && is_running "$port_pid"; then
                            pids_to_kill+=("$port_pid")
                        fi
                    done
                fi
            fi
            # 查找所有 streamlit 进程（通过命令行匹配）
            # 使用 pgrep 如果可用，否则使用 ps
            if command -v pgrep &> /dev/null; then
                local streamlit_pids=$(pgrep -f "streamlit.*dashboard.py" 2>/dev/null)
                if [ -n "$streamlit_pids" ]; then
                    for streamlit_pid in $streamlit_pids; do
                        if [ "$streamlit_pid" != "$pid" ] && is_running "$streamlit_pid"; then
                            pids_to_kill+=("$streamlit_pid")
                        fi
                    done
                fi
            else
                # 回退到 ps + grep
                while IFS= read -r line; do
                    local streamlit_pid=$(echo "$line" | awk '{print $2}')
                    if [ -n "$streamlit_pid" ] && [ "$streamlit_pid" != "$pid" ] && is_running "$streamlit_pid"; then
                        # 检查是否是 dashboard.py 相关的进程
                        local cmd=$(ps -p "$streamlit_pid" -o command= 2>/dev/null || echo "")
                        if echo "$cmd" | grep -q "dashboard.py"; then
                            pids_to_kill+=("$streamlit_pid")
                        fi
                    fi
                done < <(ps aux | grep "[s]treamlit.*dashboard" | grep -v grep 2>/dev/null || true)
            fi
            # 额外查找：通过 python -m streamlit 启动的进程
            if command -v pgrep &> /dev/null; then
                local python_streamlit_pids=$(pgrep -f "python.*streamlit.*8501" 2>/dev/null)
                if [ -n "$python_streamlit_pids" ]; then
                    for python_pid in $python_streamlit_pids; do
                        if [ "$python_pid" != "$pid" ] && is_running "$python_pid"; then
                            pids_to_kill+=("$python_pid")
                        fi
                    done
                fi
            fi
            ;;
        2) # Telegram Bot
            if [ -n "$pid" ] && is_running "$pid"; then
                pids_to_kill+=("$pid")
            fi
            # 查找所有 start_telegram_bot.py 进程
            while IFS= read -r line; do
                local bot_pid=$(echo "$line" | awk '{print $2}')
                if [ -n "$bot_pid" ] && [ "$bot_pid" != "$pid" ]; then
                    pids_to_kill+=("$bot_pid")
                fi
            done < <(ps aux | grep "[s]tart_telegram_bot.py" | grep -v grep)
            ;;
        3) # Cloudflare Tunnel
            if [ -n "$pid" ] && is_running "$pid"; then
                pids_to_kill+=("$pid")
            fi
            # 查找所有 cloudflared 或 start_tunnel_with_save.py 进程
            while IFS= read -r line; do
                local tunnel_pid=$(echo "$line" | awk '{print $2}')
                if [ -n "$tunnel_pid" ] && [ "$tunnel_pid" != "$pid" ]; then
                    pids_to_kill+=("$tunnel_pid")
                fi
            done < <(ps aux | grep -E "[c]loudflared|[s]tart_tunnel_with_save.py" | grep -v grep)
            ;;
    esac
    
    # 如果没有找到任何进程
    if [ ${#pids_to_kill[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  ${SERVICE_NAMES[$service]} 未运行${NC}"
        rm -f "$PID_DIR/${service}.pid"
        return 1
    fi
    
    # 去重
    local unique_pids=()
    for pid in "${pids_to_kill[@]}"; do
        if [[ ! " ${unique_pids[@]} " =~ " ${pid} " ]] && is_running "$pid"; then
            unique_pids+=("$pid")
        fi
    done
    
    if [ ${#unique_pids[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  ${SERVICE_NAMES[$service]} 未运行${NC}"
        rm -f "$PID_DIR/${service}.pid"
        return 1
    fi
    
    echo -e "${YELLOW}正在停止 ${SERVICE_NAMES[$service]} (PIDs: ${unique_pids[*]})...${NC}"
    
    # 先发送 SIGTERM（优雅终止）
    for pid in "${unique_pids[@]}"; do
        kill "$pid" 2>/dev/null
    done
    
    # 等待最多3秒
    for i in {1..6}; do
        sleep 0.5
        local remaining=()
        for pid in "${unique_pids[@]}"; do
            if is_running "$pid"; then
                remaining+=("$pid")
            fi
        done
        if [ ${#remaining[@]} -eq 0 ]; then
            break
        fi
        unique_pids=("${remaining[@]}")
    done
    
    # 如果还有进程在运行，强制终止
    if [ ${#unique_pids[@]} -gt 0 ]; then
        echo -e "${YELLOW}强制终止剩余进程...${NC}"
        for pid in "${unique_pids[@]}"; do
            kill -9 "$pid" 2>/dev/null
        done
        sleep 0.5
    fi
    
    # 清理 PID 文件
    rm -f "$PID_DIR/${service}.pid"
    
    # 对于 Streamlit，额外等待一下确保端口释放
    if [ $service -eq 1 ]; then
        sleep 1
    fi
    
    echo -e "${GREEN}✅ ${SERVICE_NAMES[$service]} 已停止${NC}"
}

# 启动单个服务
start_service() {
    local service=$1
    
    case $service in
        0) # FastAPI
            echo -e "${GREEN}[启动] FastAPI主服务 (端口8000)...${NC}"
            local python_cmd="python3"
            if [ -n "$VIRTUAL_ENV" ]; then
                python_cmd="$VIRTUAL_ENV/bin/python"
            elif [ -f "venv/bin/python" ]; then
                python_cmd="venv/bin/python"
            fi
            $python_cmd main.py > logs/fastapi.log 2>&1 &
            local pid=$!
            sleep 3
            if is_running "$pid"; then
                save_pid "fastapi" "$pid"
                echo -e "${GREEN}✅ FastAPI主服务已启动 (PID: $pid)${NC}"
                return 0
            else
                echo -e "${RED}❌ FastAPI服务启动失败${NC}"
                return 1
            fi
            ;;
        1) # Streamlit
            echo -e "${GREEN}[启动] Streamlit管理界面 (端口8501)...${NC}"
            
            # 再次确认端口没有被占用
            if command -v lsof &> /dev/null; then
                local port_pid=$(lsof -ti:8501 2>/dev/null)
                if [ -n "$port_pid" ]; then
                    echo -e "${YELLOW}⚠️  端口8501仍被占用 (PID: $port_pid)，强制终止...${NC}"
                    kill -9 "$port_pid" 2>/dev/null
                    sleep 1
                fi
            fi
            
            # 启动 Streamlit（确保使用虚拟环境中的 Python）
            local python_cmd="python3"
            if [ -n "$VIRTUAL_ENV" ]; then
                python_cmd="$VIRTUAL_ENV/bin/python"
            elif [ -f "venv/bin/python" ]; then
                python_cmd="venv/bin/python"
            fi
            
            echo -e "${YELLOW}   使用 Python: $python_cmd${NC}"
            $python_cmd -m streamlit run app/admin/dashboard.py \
                --server.port 8501 \
                --server.address 0.0.0.0 > logs/streamlit.log 2>&1 &
            local pid=$!
            
            # 等待启动，并检查进程状态
            local max_wait=8
            local waited=0
            local started=0
            
            while [ $waited -lt $max_wait ]; do
                sleep 1
                waited=$((waited + 1))
                
                if is_running "$pid"; then
                    # 检查端口是否被占用（说明服务已启动）
                    if command -v lsof &> /dev/null; then
                        local port_pid=$(lsof -ti:8501 2>/dev/null)
                        if [ -n "$port_pid" ]; then
                            started=1
                            break
                        fi
                    else
                        # 如果没有 lsof，检查进程是否还在运行
                        if is_running "$pid"; then
                            started=1
                            break
                        fi
                    fi
                else
                    # 进程已退出，检查日志看是否有错误
                    if [ -f "logs/streamlit.log" ]; then
                        local error_line=$(tail -n 5 logs/streamlit.log | grep -i "error\|fail\|exception" | head -1)
                        if [ -n "$error_line" ]; then
                            echo -e "${RED}❌ Streamlit启动失败:${NC}"
                            echo -e "${RED}   $error_line${NC}"
                            echo -e "${YELLOW}   查看完整日志: tail -n 20 logs/streamlit.log${NC}"
                            return 1
                        fi
                    fi
                fi
            done
            
            if [ $started -eq 1 ] && is_running "$pid"; then
                save_pid "streamlit" "$pid"
                echo -e "${GREEN}✅ Streamlit管理界面已启动 (PID: $pid)${NC}"
                return 0
            else
                echo -e "${RED}❌ Streamlit管理界面启动失败${NC}"
                if [ -f "logs/streamlit.log" ]; then
                    echo -e "${YELLOW}   最后10行日志:${NC}"
                    tail -n 10 logs/streamlit.log | sed 's/^/   /'
                fi
                return 1
            fi
            ;;
        2) # Telegram Bot
            echo -e "${GREEN}[启动] Telegram Bot服务...${NC}"
            local python_cmd="python3"
            if [ -n "$VIRTUAL_ENV" ]; then
                python_cmd="$VIRTUAL_ENV/bin/python"
            elif [ -f "venv/bin/python" ]; then
                python_cmd="venv/bin/python"
            fi
            $python_cmd start_telegram_bot.py > logs/telegram_bot.log 2>&1 &
            local pid=$!
            sleep 2
            if is_running "$pid"; then
                save_pid "telegram" "$pid"
                echo -e "${GREEN}✅ Telegram Bot服务已启动 (PID: $pid)${NC}"
                return 0
            else
                echo -e "${YELLOW}⚠️  Telegram Bot服务启动失败${NC}"
                return 1
            fi
            ;;
        3) # Cloudflare Tunnel
            echo -e "${GREEN}[启动] Cloudflare Tunnel...${NC}"
            if [ -f "start_tunnel_with_save.py" ]; then
                local python_cmd="python3"
                if [ -n "$VIRTUAL_ENV" ]; then
                    python_cmd="$VIRTUAL_ENV/bin/python"
                elif [ -f "venv/bin/python" ]; then
                    python_cmd="venv/bin/python"
                fi
                $python_cmd start_tunnel_with_save.py > logs/tunnel.log 2>&1 &
                local pid=$!
                sleep 3
                if is_running "$pid"; then
                    save_pid "tunnel" "$pid"
                    echo -e "${GREEN}✅ Cloudflare Tunnel已启动 (PID: $pid)${NC}"
                    return 0
                else
                    echo -e "${YELLOW}⚠️  Cloudflare Tunnel启动失败${NC}"
                    return 1
                fi
            else
                echo -e "${YELLOW}⚠️  start_tunnel_with_save.py 未找到${NC}"
                return 1
            fi
            ;;
    esac
}

# 重启单个服务
restart_service() {
    local service=$1
    local service_name="${SERVICE_NAMES[$service]}"
    
    echo -e "\n${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}重启服务: $service_name${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}\n"
    
    # 确保虚拟环境已激活
    if [ -z "$VIRTUAL_ENV" ] && [ -d "venv" ]; then
        echo -e "${YELLOW}激活虚拟环境...${NC}"
        source venv/bin/activate
    fi
    
    # 先停止服务（无论是否运行）
    stop_service "$service"
    
    # 根据服务类型等待不同的时间，确保端口释放
    case $service in
        0) sleep 2 ;;  # FastAPI
        1) 
            # Streamlit 需要更长时间释放端口和进程
            sleep 2
            # 再次检查端口是否释放
            if command -v lsof &> /dev/null; then
                local max_wait=10
                local waited=0
                while [ $waited -lt $max_wait ]; do
                    local port_pid=$(lsof -ti:8501 2>/dev/null)
                    if [ -z "$port_pid" ]; then
                        break
                    fi
                    echo -e "${YELLOW}等待端口8501释放... ($waited/$max_wait秒)${NC}"
                    sleep 1
                    waited=$((waited + 1))
                done
                if [ $waited -ge $max_wait ]; then
                    echo -e "${YELLOW}⚠️  端口8501可能仍被占用，尝试强制释放...${NC}"
                    # 尝试强制杀死占用端口的进程
                    local port_pid=$(lsof -ti:8501 2>/dev/null)
                    if [ -n "$port_pid" ]; then
                        kill -9 "$port_pid" 2>/dev/null
                        sleep 1
                    fi
                fi
            else
                sleep 3
            fi
            ;;
        2) sleep 1 ;;  # Telegram Bot
        3) sleep 2 ;;  # Tunnel
    esac
    
    # 启动服务
    if ! start_service "$service"; then
        echo -e "${RED}❌ 重启失败${NC}"
        return 1
    fi
}

# 显示服务状态
show_status() {
    echo -e "\n${GREEN}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}服务状态：${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}\n"
    
    for i in "${!SERVICES[@]}"; do
        local service="${SERVICES[$i]}"
        local pid=$(read_pid "$service")
        local status=""
        
        if [ -n "$pid" ] && is_running "$pid"; then
            status="${GREEN}✅ 运行中 (PID: $pid)${NC}"
        else
            status="${RED}❌ 未运行${NC}"
        fi
        
        echo -e "  ${SERVICE_NAMES[$i]}: $status"
    done
    echo
}

# 处理命令行参数
if [ "$1" = "restart" ] && [ -n "$2" ]; then
    case "$2" in
        fastapi|1)
            restart_service 0
            exit 0
            ;;
        streamlit|2)
            restart_service 1
            exit 0
            ;;
        telegram|3)
            restart_service 2
            exit 0
            ;;
        tunnel|4)
            restart_service 3
            exit 0
            ;;
        *)
            echo -e "${RED}❌ 未知服务: $2${NC}"
            echo "用法: $0 restart [fastapi|streamlit|telegram|tunnel] 或 [1|2|3|4]"
            exit 1
            ;;
    esac
elif [ "$1" = "status" ]; then
    show_status
    exit 0
elif [ "$1" = "stop" ] && [ -n "$2" ]; then
    case "$2" in
        fastapi|1)
            stop_service 0
            exit 0
            ;;
        streamlit|2)
            stop_service 1
            exit 0
            ;;
        telegram|3)
            stop_service 2
            exit 0
            ;;
        tunnel|4)
            stop_service 3
            exit 0
            ;;
        *)
            echo -e "${RED}❌ 未知服务: $2${NC}"
            echo "用法: $0 stop [fastapi|streamlit|telegram|tunnel] 或 [1|2|3|4]"
            exit 1
            ;;
    esac
elif [ "$1" = "start" ] && [ -n "$2" ]; then
    # 确保虚拟环境已激活
    if [ -z "$VIRTUAL_ENV" ] && [ -d "venv" ]; then
        echo -e "${YELLOW}激活虚拟环境...${NC}"
        source venv/bin/activate
    fi
    
    case "$2" in
        fastapi|1)
            start_service 0
            exit 0
            ;;
        streamlit|2)
            start_service 1
            exit 0
            ;;
        telegram|3)
            start_service 2
            exit 0
            ;;
        tunnel|4)
            start_service 3
            exit 0
            ;;
        *)
            echo -e "${RED}❌ 未知服务: $2${NC}"
            echo "用法: $0 start [fastapi|streamlit|telegram|tunnel] 或 [1|2|3|4]"
            exit 1
            ;;
    esac
elif [ "$1" != "" ]; then
    echo "用法:"
    echo "  $0                    # 启动所有服务"
    echo "  $0 restart [服务名]   # 重启指定服务"
    echo "  $0 start [服务名]    # 启动指定服务"
    echo "  $0 stop [服务名]      # 停止指定服务"
    echo "  $0 status            # 显示服务状态"
    echo ""
    echo "服务名: fastapi(1), streamlit(2), telegram(3), tunnel(4)"
    exit 1
fi

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          IntelliKnow KMS - 启动所有服务                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 检查虚拟环境
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠️  警告：未检测到虚拟环境！${NC}"
    # 尝试自动激活虚拟环境
    if [ -d "venv" ]; then
        echo "   尝试激活虚拟环境: venv"
        source venv/bin/activate
        if [ -z "$VIRTUAL_ENV" ]; then
            echo -e "${RED}❌ 虚拟环境激活失败${NC}"
            echo "   请手动激活: source venv/bin/activate"
            exit 1
        fi
        echo -e "${GREEN}✅ 虚拟环境已激活: $VIRTUAL_ENV${NC}"
    else
        echo "   未找到 venv 目录，请先创建虚拟环境"
        read -p "   是否继续？(y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# 创建日志目录
mkdir -p logs

# 先询问是否启动 Cloudflare Tunnel
echo -e "\n${GREEN}[0/4] Cloudflare Tunnel (可选)${NC}"
echo "   用于暴露API服务到公网，Teams Bot需要"
read -p "   是否启动 Cloudflare Tunnel？(y/n，默认n): " -n 1 -r
echo

START_TUNNEL=0
TUNNEL_PID=""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    START_TUNNEL=1
    if ! command -v cloudflared &> /dev/null; then
        echo -e "${YELLOW}⚠️  cloudflared 未找到，将跳过 Cloudflare Tunnel${NC}"
        echo "   提示：安装 cloudflared: brew install cloudflared (macOS)"
        START_TUNNEL=0
    fi
fi

# 清理函数
cleanup() {
    echo -e "\n${YELLOW}正在停止所有服务...${NC}"
    
    # 收集所有有效的 PID
    PIDS=()
    [ -n "$FASTAPI_PID" ] && ps -p $FASTAPI_PID > /dev/null 2>&1 && PIDS+=($FASTAPI_PID)
    [ -n "$STREAMLIT_PID" ] && ps -p $STREAMLIT_PID > /dev/null 2>&1 && PIDS+=($STREAMLIT_PID)
    [ -n "$TELEGRAM_PID" ] && ps -p $TELEGRAM_PID > /dev/null 2>&1 && PIDS+=($TELEGRAM_PID)
    [ -n "$TUNNEL_PID" ] && ps -p $TUNNEL_PID > /dev/null 2>&1 && PIDS+=($TUNNEL_PID)
    
    if [ ${#PIDS[@]} -eq 0 ]; then
        echo -e "${GREEN}所有服务已停止${NC}"
        exit 0
    fi
    
    # 先发送 SIGTERM（优雅终止）
    for pid in "${PIDS[@]}"; do
        kill $pid 2>/dev/null
    done
    
    # 等待最多3秒
    for i in {1..6}; do
        sleep 0.5
        REMAINING=()
        for pid in "${PIDS[@]}"; do
            if ps -p $pid > /dev/null 2>&1; then
                REMAINING+=($pid)
            fi
        done
        if [ ${#REMAINING[@]} -eq 0 ]; then
            break
        fi
        PIDS=("${REMAINING[@]}")
    done
    
    # 如果还有进程在运行，强制终止
    if [ ${#PIDS[@]} -gt 0 ]; then
        echo -e "${YELLOW}强制终止剩余进程...${NC}"
        for pid in "${PIDS[@]}"; do
            kill -9 $pid 2>/dev/null
        done
        sleep 0.5
    fi
    
    echo -e "${GREEN}所有服务已停止${NC}"
    exit 0
}

# 注册清理函数
trap cleanup SIGINT SIGTERM

# 确保虚拟环境已激活
if [ -z "$VIRTUAL_ENV" ] && [ -d "venv" ]; then
    echo -e "${YELLOW}激活虚拟环境...${NC}"
    source venv/bin/activate
fi

# 1. 启动 FastAPI 主服务
echo -e "\n${GREEN}[1/4] 启动 FastAPI 主服务 (端口8000)...${NC}"
start_service 0
FASTAPI_PID=$(read_pid "fastapi")
if [ -z "$FASTAPI_PID" ] || ! is_running "$FASTAPI_PID"; then
    echo -e "${RED}❌ FastAPI服务启动失败${NC}"
    echo "   查看日志: logs/fastapi.log"
    exit 1
fi

# 2. 启动 Streamlit 管理界面
echo -e "\n${GREEN}[2/4] 启动 Streamlit 管理界面 (端口8501)...${NC}"
start_service 1
STREAMLIT_PID=$(read_pid "streamlit")

# 3. 启动 Telegram Bot 服务
echo -e "\n${GREEN}[3/4] 启动 Telegram Bot 服务...${NC}"
start_service 2
TELEGRAM_PID=$(read_pid "telegram")

# 4. 启动 Cloudflare Tunnel (如果之前选择了启动)
if [ $START_TUNNEL -eq 1 ]; then
    echo -e "\n${GREEN}[4/4] 启动 Cloudflare Tunnel...${NC}"
    echo "   启动 Cloudflare Tunnel（等待URL生成并保存）..."
    start_service 3
    TUNNEL_PID=$(read_pid "tunnel")
    
    if [ -n "$TUNNEL_PID" ] && is_running "$TUNNEL_PID"; then
        # 等待URL生成（最多等待20秒）
        echo "   等待Tunnel URL生成..."
        URL_FOUND=0
        for i in {1..20}; do
            sleep 1
            # 检查日志中是否包含URL
            if [ -f "logs/tunnel.log" ]; then
                if grep -q "trycloudflare.com\|cfargotunnel.com" logs/tunnel.log 2>/dev/null; then
                    echo -e "${GREEN}   ✅ 检测到URL，等待保存完成...${NC}"
                    sleep 2
                    URL_FOUND=1
                    break
                fi
            fi
            # 检查进程是否还在运行
            if ! is_running "$TUNNEL_PID"; then
                break
            fi
        done
        
        if [ $URL_FOUND -eq 1 ]; then
            echo -e "${GREEN}   ✅ URL已捕获并保存到数据库${NC}"
        else
            echo -e "${YELLOW}   ⚠️  URL可能还未生成，请查看日志或手动配置${NC}"
            echo "   提示：URL会在后台继续生成，请稍后刷新前端界面"
        fi
    fi
else
    echo -e "\n${GREEN}[4/4] 跳过 Cloudflare Tunnel${NC}"
fi

# 显示服务状态
echo -e "\n${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ 所有服务启动完成！${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}\n"
echo "服务列表："
echo -e "  ${GREEN}✅ FastAPI主服务:     http://localhost:8000${NC}"
echo -e "  ${GREEN}✅ Streamlit管理界面: http://localhost:8501${NC}"
echo -e "  ${GREEN}✅ Telegram Bot:      已启动 (polling模式)${NC}"
echo -e "\n日志文件位置: ${YELLOW}logs/${NC} 目录"
echo -e "\n按 ${RED}Ctrl+C${NC} 停止所有服务\n"

# 等待所有进程（使用后台等待，避免阻塞）
# 注意：如果直接使用 wait，当某些进程已经退出时会卡住
# 所以我们使用循环检查进程状态
while true; do
    RUNNING=0
    FASTAPI_PID=$(read_pid "fastapi")
    STREAMLIT_PID=$(read_pid "streamlit")
    TELEGRAM_PID=$(read_pid "telegram")
    TUNNEL_PID=$(read_pid "tunnel")
    
    [ -n "$FASTAPI_PID" ] && is_running "$FASTAPI_PID" && RUNNING=1
    [ -n "$STREAMLIT_PID" ] && is_running "$STREAMLIT_PID" && RUNNING=1
    [ -n "$TELEGRAM_PID" ] && is_running "$TELEGRAM_PID" && RUNNING=1
    [ -n "$TUNNEL_PID" ] && is_running "$TUNNEL_PID" && RUNNING=1
    
    if [ $RUNNING -eq 0 ]; then
        echo -e "\n${YELLOW}所有服务已停止${NC}"
        exit 0
    fi
    
    sleep 1
done
