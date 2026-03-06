from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置代理绕过：Microsoft Online域名不应使用代理
# 这需要在导入botframework之前设置，因为MSAL会在导入时读取环境变量
_microsoft_online_domains = [
    'login.microsoftonline.com',
    '*.microsoftonline.com',
    'graph.microsoft.com',
    '*.microsoft.com'
]

# 更新NO_PROXY环境变量以包含Microsoft Online域名
_current_no_proxy = os.environ.get('NO_PROXY', '') or os.environ.get('no_proxy', '')
_no_proxy_list = [x.strip() for x in _current_no_proxy.split(',') if x.strip()]
_no_proxy_list.extend(_microsoft_online_domains)
os.environ['NO_PROXY'] = ','.join(set(_no_proxy_list))
os.environ['no_proxy'] = os.environ['NO_PROXY']  # 确保小写版本也设置

print(f"DEBUG: NO_PROXY已配置: {os.environ.get('NO_PROXY')}")

# 导入API路由
from app.api.routes import router as api_router

# 创建FastAPI应用实例
app = FastAPI(
    title="IntelliKnow KMS API",
    description="Gen AI驱动的知识管理系统API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router, prefix="/api", tags=["API"])


# 根路径
@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "欢迎使用IntelliKnow KMS API",
        "version": "1.0.0",
        "endpoints": {
            "documents": "/api/documents",
            "query": "/api/query",
            "intent_spaces": "/api/intent-spaces",
            "frontend_integrations": "/api/frontend-integrations",
            "analytics": "/api/analytics",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "IntelliKnow KMS"}


# 运行应用
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
