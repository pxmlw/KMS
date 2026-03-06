#!/bin/bash
# Telegram Bot 启动脚本

cd "$(dirname "$0")"

# 激活虚拟环境
source venv/bin/activate

# 启动Telegram Bot
python3 start_telegram_bot.py
