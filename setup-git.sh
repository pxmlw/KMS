#!/bin/bash
# Git仓库初始化脚本
# 使用方法：在项目目录外运行此脚本，它会创建一个新的独立Git仓库

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
NEW_PROJECT_DIR="${PROJECT_DIR}-git"

echo "正在复制项目到: $NEW_PROJECT_DIR"
cp -r "$PROJECT_DIR" "$NEW_PROJECT_DIR"

echo "正在初始化Git仓库..."
cd "$NEW_PROJECT_DIR"
rm -rf .git

# 使用环境变量跳过hooks创建
export GIT_TEMPLATE_DIR=/dev/null
git init

echo "正在添加文件..."
git add .

echo "正在创建初始提交..."
git commit -m "初始提交: 创建FastAPI Web应用，包含upload、query和intents路由端点"

echo ""
echo "✅ Git仓库创建成功！"
echo "项目位置: $NEW_PROJECT_DIR"
echo ""
echo "查看状态:"
git log --oneline
echo ""
git status
