"""
编排器服务
AI驱动的意图分类和查询路由
"""
import json
from typing import Dict, Optional, Tuple, List
from datetime import datetime

try:
    import openai
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    openai = None
    OpenAI = None
    AsyncOpenAI = None

import os
from app.config import AI_CONFIDENCE_THRESHOLD, DEFAULT_INTENT_SPACE
from app.models.database import db


class Orchestrator:
    """查询编排器"""
    
    def __init__(self, api_key: Optional[str] = None, 
                 api_provider: str = "openai",
                 base_url: Optional[str] = None,
                 model: Optional[str] = None):
        self.confidence_threshold = AI_CONFIDENCE_THRESHOLD
        self.default_intent = DEFAULT_INTENT_SPACE
        self.api_provider = api_provider.lower()
        self.model = model
        
        # AI客户端（同步和异步，如果配置了API Key）
        self.ai_client = None
        self.async_ai_client = None
        if api_key and OpenAI and AsyncOpenAI:
            try:
                if self.api_provider == "openrouter":
                    # OpenRouter配置（默认使用豆包模型）
                    base_url = base_url or "https://openrouter.ai/api/v1"
                    self.model = model or "deepseek/deepseek-chat"
                    # 同步客户端（用于向后兼容）
                    self.ai_client = OpenAI(
                        api_key=api_key,
                        base_url=base_url
                    )
                    # 异步客户端（用于性能优化）
                    self.async_ai_client = AsyncOpenAI(
                        api_key=api_key,
                        base_url=base_url,
                        timeout=5.0,  # 减少超时时间以提高响应速度
                        max_retries=1  # 减少重试次数以提高响应速度
                    )
                    # 保存默认headers用于OpenRouter（可选，用于app attribution）
                    self.default_headers = {
                        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://github.com/intelliknow-kms"),  # 可选
                        "X-Title": os.getenv("OPENROUTER_TITLE", "IntelliKnow KMS")  # 可选
                    }
                else:
                    # OpenAI配置
                    self.ai_client = OpenAI(api_key=api_key)
                    self.async_ai_client = AsyncOpenAI(
                        api_key=api_key,
                        timeout=5.0,  # 减少超时时间以提高响应速度
                        max_retries=1  # 减少重试次数以提高响应速度
                    )
                    self.default_headers = {}
            except Exception as e:
                pass  # AI客户端初始化失败，将使用关键词分类
    
    async def classify_intent_async(self, query: str, context: Optional[Dict] = None) -> Tuple[str, float]:
        """异步版本的意图分类"""
        # 获取所有意图空间
        intent_spaces = self._get_intent_spaces()
        
        if not intent_spaces:
            return (self.default_intent, 0.5)
        
        # 使用AI进行分类（如果有AI客户端）
        if self.async_ai_client:
            return await self._ai_classify_async(query, intent_spaces, context)
        else:
            # 回退到基于关键词的简单分类
            return self._keyword_classify(query, intent_spaces)
    
    def classify_intent(self, query: str, context: Optional[Dict] = None) -> Tuple[str, float]:
        """
        AI驱动的意图分类
        
        Args:
            query: 查询文本
            context: 可选上下文
            
        Returns:
            (意图空间名称, 置信度)
        """
        # 获取所有意图空间
        intent_spaces = self._get_intent_spaces()
        
        if not intent_spaces:
            return (self.default_intent, 0.5)
        
        # 使用AI进行分类（如果有AI客户端）
        if self.ai_client:
            return self._ai_classify(query, intent_spaces, context)
        else:
            # 回退到基于关键词的简单分类
            return self._keyword_classify(query, intent_spaces)
    
    def _get_intent_spaces(self) -> List[Dict]:
        """获取所有意图空间"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description, keywords FROM intent_spaces ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "keywords": row["keywords"].split(',') if row["keywords"] else []
            }
            for row in rows
        ]
    
    async def _ai_classify_async(self, query: str, intent_spaces: List[Dict], 
                                 context: Optional[Dict]) -> Tuple[str, float]:
        """异步版本的AI分类（优化：使用异步客户端）"""
        if not self.async_ai_client:
            return self._keyword_classify(query, intent_spaces)
        
        try:
            # 优化：先快速检查关键词，如果匹配度高则直接返回，避免AI调用
            keyword_result = self._keyword_classify(query, intent_spaces)
            if keyword_result[1] > 0.6:  # 如果关键词分类置信度>0.6，直接使用
                return keyword_result
            
            # 构建提示词（动态生成，支持所有意图空间）
            intent_names = [s["name"] for s in intent_spaces]
            intent_list = ", ".join(intent_names)
            
            # 动态构建规则描述（基于意图空间的描述和关键词）
            rules = []
            for space in intent_spaces:
                if space.get("description"):
                    rules.append(f"{space['name']}: {space['description']}")
                elif space.get("keywords"):
                    keywords_str = ", ".join(space["keywords"][:5])  # 只显示前5个关键词
                    rules.append(f"{space['name']}: {keywords_str}")
            
            rules_text = "\n".join(rules) if rules else "根据查询内容匹配最相关的意图空间"
            
            prompt = f"""分类查询到意图空间：{intent_list}

意图空间说明：
{rules_text}

查询：{query}

返回JSON：{{"intent": "意图空间名称", "confidence": 0.0-1.0}}"""
            
            # 调用AI API（异步）
            model_name = self.model if self.model else "deepseek/deepseek-chat"
            
            request_params = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "只返回JSON。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 50
            }
            
            if self.api_provider == "openrouter" and hasattr(self, 'default_headers'):
                request_params["extra_headers"] = self.default_headers
            
            # 使用异步客户端
            response = await self.async_ai_client.chat.completions.create(**request_params)
            
            # 解析响应
            response_text = response.choices[0].message.content.strip()
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
            
            result = json.loads(response_text)
            intent_name = result.get("intent", self.default_intent)
            confidence = float(result.get("confidence", 0.5))
            
            # 验证意图空间存在
            intent_names = [s["name"] for s in intent_spaces]
            if intent_name not in intent_names:
                return self._keyword_classify(query, intent_spaces)
            
            if confidence < self.confidence_threshold:
                return self._keyword_classify(query, intent_spaces)
            
            return (intent_name, confidence)
        except Exception as e:
            return self._keyword_classify(query, intent_spaces)
    
    def _ai_classify(self, query: str, intent_spaces: List[Dict], 
                            context: Optional[Dict]) -> Tuple[str, float]:
        """
        使用AI进行意图分类
        
        AI使用场景：
        - 理解查询语义和上下文
        - 匹配到最相关的意图空间
        - 提供置信度分数
        """
        try:
            # 优化：先快速检查关键词，如果匹配度高则直接返回，避免AI调用
            keyword_result = self._keyword_classify(query, intent_spaces)
            if keyword_result[1] > 0.6:  # 如果关键词分类置信度>0.6，直接使用
                return keyword_result
            
            # 构建提示词（动态生成，支持所有意图空间）
            intent_names = [s["name"] for s in intent_spaces]
            intent_list = ", ".join(intent_names)
            
            # 动态构建规则描述（基于意图空间的描述和关键词）
            rules = []
            for space in intent_spaces:
                if space.get("description"):
                    rules.append(f"{space['name']}: {space['description']}")
                elif space.get("keywords"):
                    keywords_str = ", ".join(space["keywords"][:5])  # 只显示前5个关键词
                    rules.append(f"{space['name']}: {keywords_str}")
            
            rules_text = "\n".join(rules) if rules else "根据查询内容匹配最相关的意图空间"
            
            prompt = f"""分类查询到意图空间：{intent_list}

意图空间说明：
{rules_text}

查询：{query}

返回JSON：{{"intent": "意图空间名称", "confidence": 0.0-1.0}}"""
            
            # 调用AI API
            model_name = self.model if self.model else "deepseek/deepseek-chat"
            
            # 准备请求参数（优化：减少token和temperature以提高速度）
            request_params = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "只返回JSON。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,  # 降低temperature以提高速度
                "max_tokens": 50  # 减少max_tokens（分类只需要简短JSON）
            }
            
            # 如果是OpenRouter，添加headers
            if self.api_provider == "openrouter" and hasattr(self, 'default_headers'):
                request_params["extra_headers"] = self.default_headers
            
            response = self.ai_client.chat.completions.create(**request_params)
            
            # 解析响应
            response_text = response.choices[0].message.content.strip()
            # 提取JSON
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
            
            result = json.loads(response_text)
            
            intent_name = result.get("intent", self.default_intent)
            confidence = float(result.get("confidence", 0.5))
            
            # 验证意图空间存在
            intent_names = [s["name"] for s in intent_spaces]
            if intent_name not in intent_names:
                # AI返回的意图名称不在列表中，回退到关键词分类
                return self._keyword_classify(query, intent_spaces)
            
            # 应用置信度阈值
            if confidence < self.confidence_threshold:
                # 置信度太低，回退到关键词分类
                return self._keyword_classify(query, intent_spaces)
            
            return (intent_name, confidence)
        except Exception as e:
            return self._keyword_classify(query, intent_spaces)
    
    def _keyword_classify(self, query: str, intent_spaces: List[Dict]) -> Tuple[str, float]:
        """基于关键词的简单分类（回退方案）"""
        import re
        
        query_lower = query.lower()
        best_intent = self.default_intent
        best_score = 0.0
        best_matches = 0
        
        # 提取查询中的关键词（2个字符以上的中文词）
        query_keywords = re.findall(r'[\u4e00-\u9fff]{2,}', query_lower)
        
        # 动态遍历所有意图空间，不再硬编码特定意图空间的关键词
        for space in intent_spaces:
            keywords = [k.lower().strip() for k in space["keywords"]]
            # 计算匹配分数
            matches = sum(1 for keyword in keywords if keyword in query_lower)
            if keywords:
                # 使用匹配比例和绝对匹配数的组合评分
                ratio_score = matches / len(keywords)
                match_score = min(matches / 3.0, 1.0)
                # 综合评分：匹配比例和匹配数的加权平均
                score = (ratio_score * 0.4 + match_score * 0.6)
                
                if score > best_score:
                    best_score = score
                    best_matches = matches
                    best_intent = space["name"]
        
        # 关键词分类使用更低的阈值（0.15），因为关键词匹配的置信度天然较低
        keyword_threshold = 0.15
        confidence = best_score
        
        # 如果有匹配，即使分数低于阈值也使用最佳匹配（但降低置信度）
        if best_matches > 0:
            intent_name = best_intent
            # 如果分数低于阈值，降低置信度但仍然使用该意图
            if confidence < keyword_threshold:
                confidence = max(0.5, confidence)  # 最低0.5置信度
        else:
            # 完全没有匹配，使用默认意图
            intent_name = self.default_intent
            confidence = 0.5
        
        return (intent_name, confidence)
    
    def route_query(self, query: str, detected_intent: str, 
                    confidence: float, frontend_type: str = "api") -> Dict:
        """
        路由查询到相关知识域
        
        Args:
            query: 查询文本
            detected_intent: 检测到的意图
            confidence: 置信度
            frontend_type: 前端类型
            
        Returns:
            路由信息字典
        """
        # 获取意图空间ID
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM intent_spaces WHERE name = ?", (detected_intent,))
        row = cursor.fetchone()
        intent_space_id = row["id"] if row else None
        conn.close()
        
        return {
            "intent_space": detected_intent,
            "intent_space_id": intent_space_id,
            "confidence": confidence,
            "query": query,
            "frontend_type": frontend_type,
            "routed": True
        }


# 编排器实例（支持OpenAI和OpenRouter）
import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# 优先使用OpenRouter（如果配置了）
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

# 选择API提供商
if openrouter_api_key:
    # 使用OpenRouter
    api_provider = "openrouter"
    api_key = openrouter_api_key
    base_url = "https://openrouter.ai/api/v1"
    # 可选：使用其他模型，如 "anthropic/claude-3-haiku", "google/gemini-pro" 等
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")
    orchestrator = Orchestrator(
        api_key=api_key,
        api_provider=api_provider,
        base_url=base_url,
        model=model
    )
elif openai_api_key:
    # 使用OpenAI
    orchestrator = Orchestrator(api_key=openai_api_key, api_provider="openai")
else:
    # 未配置API Key
    orchestrator = Orchestrator()
