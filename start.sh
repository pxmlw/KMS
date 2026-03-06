#!/bin/bash
# FastAPI Web应用启动脚本

# 激活虚拟环境（如果存在）
if [ -d "../venv" ]; then
    source ../venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# 运行应用
python main.py
