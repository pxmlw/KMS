# FastAPI Web应用

这是一个基于FastAPI框架的简单Web应用，包含三个主要路由端点。

## 功能特性

- **/upload**: 文件上传端点
- **/query**: 查询端点
- **/intents**: 意图识别端点

## 安装依赖

### 方法1：使用虚拟环境（推荐）

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# macOS/Linux:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 方法2：直接安装（不推荐，可能遇到权限问题）

```bash
pip3 install -r requirements.txt
```

## 运行应用

### 如果使用虚拟环境：

```bash
# 确保虚拟环境已激活
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 运行应用
python main.py
```

### 或使用uvicorn直接运行：

```bash
# 在虚拟环境中
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 如果不使用虚拟环境：

```bash
python3 main.py
# 或
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API端点说明

### 1. 根路径
- **GET** `/`
- 返回API信息和可用端点列表

### 2. 文件上传
- **POST** `/upload`
- 请求体：multipart/form-data，包含文件
- 响应：文件信息（文件名、类型、大小等）

示例：
```bash
curl -X POST "http://localhost:8000/upload" -F "file=@example.txt"
```

### 3. 查询
- **POST** `/query`
- 请求体：JSON格式
```json
{
  "query": "查询内容",
  "filters": {}
}
```
- 响应：查询结果

示例：
```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "测试查询", "filters": {}}'
```

### 4. 意图识别
- **POST** `/intents`
- 请求体：JSON格式
```json
{
  "text": "用户输入的文本",
  "context": {}
}
```
- 响应：识别的意图、置信度和实体

示例：
```bash
curl -X POST "http://localhost:8000/intents" \
  -H "Content-Type: application/json" \
  -d '{"text": "我想查询一些信息", "context": {}}'
```

### 5. 健康检查
- **GET** `/health`
- 返回服务健康状态

## API文档

启动应用后，可以访问以下地址查看自动生成的API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
.
├── main.py              # 主应用文件
├── requirements.txt     # Python依赖
└── README.md           # 项目说明文档
```
