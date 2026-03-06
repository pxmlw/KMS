# Git仓库设置指南

由于系统权限限制，需要手动创建独立的Git仓库。请按照以下步骤操作：

## 方法1：在终端中手动操作（推荐）

1. **打开终端，复制项目到新位置**（选择一个你有写权限的目录）：
   ```bash
   # 选项A：复制到临时目录（测试用）
   cp -r ~/fastapi-webapp /tmp/fastapi-webapp-new
   cd /tmp/fastapi-webapp-new
   
   # 选项B：复制到其他位置（如桌面）
   # 注意：需要手动在Finder中复制文件夹
   ```

2. **删除旧的.git目录并初始化新仓库**：
   ```bash
   rm -rf .git
   git init
   ```

3. **添加文件并提交**：
   ```bash
   git add .
   git commit -m "初始提交: 创建FastAPI Web应用，包含upload、query和intents路由端点"
   ```

4. **验证**：
   ```bash
   git log --oneline
   git status
   ```

## 方法2：使用Finder手动操作

1. 在Finder中找到 `~/fastapi-webapp` 文件夹
2. 复制整个文件夹到你想要的位置（如桌面或Documents）
3. 打开终端，进入新复制的文件夹
4. 执行：
   ```bash
   rm -rf .git
   git init
   git add .
   git commit -m "初始提交: 创建FastAPI Web应用，包含upload、query和intents路由端点"
   ```

## 当前项目文件

项目文件已经整理在 `~/fastapi-webapp` 目录中：
- ✅ main.py - FastAPI主应用
- ✅ requirements.txt - Python依赖
- ✅ README.md - 项目文档
- ✅ .gitignore - Git忽略规则
- ✅ start.sh - 启动脚本

## 注意事项

- 主目录的Git仓库有权限限制，无法直接操作
- 建议将项目复制到其他位置创建独立的Git仓库
- 项目文件已经准备就绪，只需要重新初始化Git仓库即可
