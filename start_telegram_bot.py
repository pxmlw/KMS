#!/usr/bin/env python3
"""
启动Telegram Bot服务
"""
import os
import sys

# 确保从项目根目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 设置环境变量，确保Python能找到app模块
sys.path.insert(0, os.getcwd())

from app.integrations.telegram_bot import start_telegram_bot_polling

if __name__ == "__main__":
    print("正在启动Telegram Bot服务...")
    print("提示：按 Ctrl+C 停止服务")
    start_telegram_bot_polling()
