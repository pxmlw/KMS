"""
知识库服务
使用FAISS进行语义搜索和知识检索
"""
import os
import json
from typing import List, Dict, Optional
from pathlib import Path
import numpy as np

try:
    import faiss
    from sentence_transformers import SentenceTransformer
except ImportError:
    faiss = None
    SentenceTransformer = None

from app.config import KB_DIR
from app.models.database import db
from app.services.document_parser import document_parser


class KnowledgeBase:
    """知识库管理器"""
    
    def __init__(self):
        self.kb_dir = KB_DIR
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化FAISS索引和嵌入模型
        self.embedding_model = None
        self.index = None
        self.document_chunks = []  # 存储文档块和元数据
        
        if SentenceTransformer:
            try:
                # 使用轻量级中文嵌入模型
                self.embedding_model = SentenceTransformer('paraphrase-multilang-MiniLM-L12-v2')
            except Exception as e:
                print(f"警告：无法加载嵌入模型: {e}")
                print("将使用简化版文本匹配")
    
    def add_document(self, doc_id: int, content: str, 
                      metadata: Dict, intent_space_id: Optional[int] = None):
        """
        添加文档到知识库
        
        Args:
            doc_id: 文档ID
            content: 文档内容
            metadata: 文档元数据
            intent_space_id: 关联的意图空间ID
        """
        # 将文档分块（每块约500字符）
        chunks = self._chunk_document(content)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        for chunk_idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_{chunk_idx}"
            chunk_metadata = {
                "doc_id": doc_id,
                "chunk_idx": chunk_idx,
                "intent_space_id": intent_space_id,
                **metadata
            }
            
            # 存储块
            self.document_chunks.append({
                "id": chunk_id,
                "content": chunk,
                "metadata": chunk_metadata
            })
            
            # 更新FAISS索引
            if self.embedding_model:
                self._update_faiss_index(chunk, chunk_id, chunk_metadata)
        
        conn.close()
    
    def _chunk_document(self, content: str, chunk_size: int = 500) -> List[str]:
        """将文档分块"""
        # 简单分块：按段落和字符数
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_size = len(para)
            if current_size + para_size > chunk_size and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return chunks if chunks else [content]
    
    def _update_faiss_index(self, text: str, chunk_id: str, metadata: Dict):
        """更新FAISS索引"""
        if not self.embedding_model:
            return
        
        try:
            # 生成嵌入向量
            embedding = self.embedding_model.encode([text])[0]
            
            embedding = np.array(embedding, dtype=np.float32)
            
            # 初始化或更新FAISS索引
            if self.index is None:
                dimension = len(embedding)
                self.index = faiss.IndexFlatL2(dimension)
            
            # 添加向量到索引
            self.index.add(np.array([embedding], dtype=np.float32))
            
            # 保存元数据
            metadata_path = self.kb_dir / f"{chunk_id}.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": metadata
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"FAISS索引更新失败: {e}")
    
    def _load_documents_from_db(self):
        """从数据库加载文档到知识库"""
        if len(self.document_chunks) > 0:
            return  # 已经加载过了
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, file_path, intent_space_id FROM documents WHERE status = 'processed'")
        documents = cursor.fetchall()
        conn.close()
        
        for doc in documents:
            try:
                file_path = doc["file_path"]
                if not os.path.exists(file_path):
                    continue
                
                parse_result = document_parser.parse_document(file_path, doc["filename"])
                raw_content = parse_result["raw_content"]
                metadata = parse_result["metadata"]
                
                self.add_document(doc["id"], raw_content, metadata, doc["intent_space_id"])
            except Exception as e:
                print(f"加载文档 {doc['id']} 失败: {e}")
    
    def search(self, query: str, intent_space_id: Optional[int] = None, 
                top_k: int = 5) -> List[Dict]:
        """
        语义搜索知识库
        
        Args:
            query: 查询文本
            intent_space_id: 可选的意图空间ID（过滤）
            top_k: 返回前K个结果
            
        Returns:
            搜索结果列表
        """
        # 如果知识库为空，尝试从数据库加载
        if len(self.document_chunks) == 0:
            self._load_documents_from_db()
        
        if not self.embedding_model or self.index is None:
            # 回退到简单文本匹配
            return self._simple_search(query, intent_space_id, top_k)
        
        try:
            # 生成查询向量
            query_embedding = self.embedding_model.encode([query])[0]
            query_embedding = np.array(query_embedding, dtype=np.float32)
            
            # FAISS搜索
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32),
                top_k * 2  # 多取一些以便过滤
            )
            
            # 加载结果
            results = []
            seen_doc_ids = set()
            
            for dist, idx in zip(distances[0], indices[0]):
                if idx >= len(self.document_chunks):
                    continue
                
                chunk_data = self.document_chunks[idx]
                chunk_metadata = chunk_data["metadata"]
                
                # 意图空间过滤
                # 如果指定了意图空间，只搜索匹配的文档 + 没有指定意图空间的通用文档
                # 如果没有指定意图空间，搜索所有文档
                chunk_intent_space_id = chunk_metadata.get("intent_space_id")
                if intent_space_id is not None:
                    # 指定了意图空间：只搜索匹配的文档或通用文档（None）
                    if chunk_intent_space_id is not None and chunk_intent_space_id != intent_space_id:
                        continue
                # 如果 intent_space_id 是 None，不过滤，搜索所有文档
                
                doc_id = chunk_metadata["doc_id"]
                if doc_id in seen_doc_ids:
                    continue  # 每个文档只返回一个结果
                seen_doc_ids.add(doc_id)
                
                # 加载完整元数据
                metadata_path = self.kb_dir / f"{chunk_data['id']}.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        chunk_info = json.load(f)
                        chunk_data["content"] = chunk_info.get("text", chunk_data["content"])
                
                results.append({
                    "doc_id": doc_id,
                    "chunk_id": chunk_data["id"],
                    "content": chunk_data["content"],
                    "metadata": chunk_metadata,
                    "score": float(1 - dist)  # 转换为相似度分数
                })
                
                if len(results) >= top_k:
                    break
            
            return results
        except Exception as e:
            print(f"FAISS搜索失败: {e}，回退到简单搜索")
            return self._simple_search(query, intent_space_id, top_k)
    
    def _simple_search(self, query: str, intent_space_id: Optional[int], top_k: int) -> List[Dict]:
        """简单文本匹配搜索（回退方案）"""
        import re
        query_lower = query.lower()
        
        # 提取关键词：中文词（2个字符以上）和英文单词
        # 对于中文，提取所有可能的2字符以上的词
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,}', query_lower)
        english_words = re.findall(r'[a-zA-Z]+', query_lower)
        query_words = set(chinese_words + english_words)
        
        # 如果提取的词为空或只有一个长词，尝试提取所有2字符组合
        if not query_words or (len(query_words) == 1 and len(list(query_words)[0]) > 4):
            # 提取所有2字符的中文组合
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', query_lower)
            if len(chinese_chars) >= 2:
                # 生成所有2字符组合
                for i in range(len(chinese_chars) - 1):
                    query_words.add(chinese_chars[i] + chinese_chars[i+1])
        
        # 如果还是为空，提取单个中文字符
        if not query_words:
            single_chars = set(re.findall(r'[\u4e00-\u9fff]', query_lower))
            query_words = single_chars
        
        results = []
        
        for chunk_data in self.document_chunks:
            chunk_metadata = chunk_data["metadata"]
            # 意图空间过滤（与FAISS搜索逻辑一致）
            # 如果指定了意图空间，只搜索匹配的文档 + 没有指定意图空间的通用文档
            chunk_intent_space_id = chunk_metadata.get("intent_space_id")
            if intent_space_id is not None:
                # 指定了意图空间：只搜索匹配的文档或通用文档（None）
                if chunk_intent_space_id is not None and chunk_intent_space_id != intent_space_id:
                    continue
            # 如果 intent_space_id 是 None，不过滤，搜索所有文档
            
            content = chunk_data["content"].lower()
            
            # 计算匹配分数
            matches = 0
            total_score = 0.0
            
            for word in query_words:
                if word in content:
                    matches += 1
                    # 计算词频（出现次数）
                    word_count = content.count(word)
                    total_score += min(word_count / 10.0, 1.0)  # 限制最大分数
            
            # 如果至少有一个关键词匹配，就返回结果
            if matches > 0:
                score = total_score / len(query_words) if query_words else 0.5
                # 确保至少有一个匹配就有结果
                score = max(score, 0.3) if matches > 0 else 0
                
                results.append({
                    "doc_id": chunk_metadata["doc_id"],
                    "chunk_id": chunk_data["id"],
                    "content": chunk_data["content"],
                    "metadata": chunk_metadata,
                    "score": score
                })
        
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    
    def generate_response(self, query: str, search_results: List[Dict], 
                         frontend_type: str = "api") -> str:
        """
        生成自然语言响应文本（使用AI）
        
        Args:
            query: 查询文本
            search_results: 搜索结果
            frontend_type: 前端类型（用于格式化）
            
        Returns:
            格式化的自然语言响应文本
        """
        if not search_results:
            return "抱歉，未找到相关信息。请尝试使用不同的关键词或联系管理员。"
        
        # 尝试使用AI生成响应
        try:
            return self._generate_ai_response(query, search_results, frontend_type)
        except Exception as e:
            print(f"AI响应生成失败: {e}，使用简化版响应")
            return self._generate_simple_response(query, search_results, frontend_type)
    
    def _generate_ai_response(self, query: str, search_results: List[Dict], 
                              frontend_type: str) -> str:
        """使用AI生成自然语言响应"""
        try:
            from app.services.orchestrator import orchestrator
            
            # 如果配置了OpenAI API，使用AI生成响应
            if orchestrator.ai_client:
                # 构建上下文
                context_parts = []
                for idx, result in enumerate(search_results[:3], 1):
                    content = result["content"]
                    doc_id = result["metadata"]["doc_id"]
                    filename = result["metadata"].get("filename", f"文档{doc_id}")
                    context_parts.append(f"[文档{idx}] ({filename})\n{content[:500]}")
                
                context = "\n\n".join(context_parts)
                
                prompt = f"""你是一个知识管理系统的助手。请根据以下知识库内容，用自然、流畅的中文回答用户的问题。

用户问题：{query}

知识库内容：
{context}

要求：
1. 用自然、流畅的中文回答问题，就像在和朋友聊天一样
2. 直接回答用户的问题，不要使用"根据知识库"、"根据文档"等生硬的开头
3. 如果知识库中有相关信息，直接给出答案，并在回答末尾用【文档名】标注来源
4. 如果信息不完整，说明已知部分
5. 回答要准确、专业、易懂
6. 保持回答简洁，但不要过于简短，要包含关键信息

示例：
- 好的回答："员工每年有10天年假，可以累积最多20天。需要提前一周申请。【员工请假政策.docx】"
- 不好的回答："根据知识库内容，年假有10天。"

请直接给出回答："""

                # 获取模型名称和headers
                model_name = getattr(orchestrator, 'model', None) or "deepseek/deepseek-chat"
                
                # 准备请求参数
                request_params = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的知识管理助手，能够根据知识库内容准确回答用户问题。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
                
                # 如果是OpenRouter，添加headers
                if getattr(orchestrator, 'api_provider', 'openai') == "openrouter" and hasattr(orchestrator, 'default_headers'):
                    request_params["extra_headers"] = orchestrator.default_headers
                
                response = orchestrator.ai_client.chat.completions.create(**request_params)
                
                ai_response = response.choices[0].message.content.strip()
                
                # 添加来源引用
                sources = []
                seen_docs = set()
                for result in search_results[:3]:
                    doc_id = result["metadata"]["doc_id"]
                    filename = result["metadata"].get("filename", f"文档{doc_id}")
                    if doc_id not in seen_docs:
                        sources.append(filename)
                        seen_docs.add(doc_id)
                
                if sources:
                    ai_response += f"\n\n📚 来源：{', '.join(sources)}"
                
                # 根据前端类型调整格式
                return self._format_response(ai_response, frontend_type)
            else:
                # 没有AI客户端，使用简化版
                raise Exception("AI客户端未配置")
        except Exception as e:
            raise e
    
    def _generate_simple_response(self, query: str, search_results: List[Dict], 
                                  frontend_type: str) -> str:
        """生成简化版响应（回退方案）"""
        import re
        
        # 提取查询关键词（支持中文）
        # 提取2个字符以上的中文词和英文单词
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,}', query)
        english_words = re.findall(r'[a-zA-Z]+', query)
        query_keywords = chinese_words + english_words
        
        # 如果关键词太少，提取所有中文字符
        if len(query_keywords) < 2:
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', query)
            query_keywords = chinese_chars[:3]  # 最多取前3个字符
        
        # 从第一个搜索结果中提取最相关的答案
        best_result = search_results[0]
        content = best_result["content"]
        
        # 分割句子（支持中文标点）
        sentences = re.split(r'[。\n！？；]', content)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]
        
        # 找到最相关的句子（包含查询关键词）
        best_sentences = []
        if query_keywords:
            scored_sentences = []
            for sentence in sentences:
                # 计算匹配分数
                match_count = sum(1 for keyword in query_keywords if keyword in sentence)
                if match_count > 0:
                    # 分数 = 匹配数 / 关键词总数 + 句子长度权重（优先短句）
                    score = match_count / len(query_keywords) + (1.0 / max(len(sentence), 1))
                    scored_sentences.append((score, sentence))
            
            if scored_sentences:
                # 按分数排序，取前2个
                scored_sentences.sort(reverse=True, key=lambda x: x[0])
                best_sentences = [s[1] for s in scored_sentences[:2]]
        
        # 如果没有找到匹配的句子，使用包含关键词的段落
        if not best_sentences:
            paragraphs = content.split('\n')
            for para in paragraphs:
                para = para.strip()
                if para and len(para) > 5:
                    if query_keywords:
                        if any(keyword in para for keyword in query_keywords):
                            best_sentences.append(para)
                            break
                    else:
                        best_sentences.append(para)
                        break
        
        # 如果还是没有，使用前几个有意义的句子
        if not best_sentences:
            for sentence in sentences[:3]:
                if len(sentence) > 10:  # 至少10个字符
                    best_sentences.append(sentence)
                    if len(best_sentences) >= 2:
                        break
        
        # 组合响应
        if best_sentences:
            # 去重并选择最相关的句子
            seen = set()
            unique_sentences = []
            for s in best_sentences:
                if s not in seen:
                    seen.add(s)
                    unique_sentences.append(s)
            
            # 优先返回包含最多关键词的单个句子
            if unique_sentences:
                # 如果第一个句子已经回答了问题，只返回第一个
                first_sentence = unique_sentences[0]
                # 检查是否包含查询的核心词（去掉"多久"、"什么"等疑问词）
                core_keywords = [w for w in query_keywords if w not in ['多久', '什么', '如何', '怎么', '多少', '哪些']]
                if core_keywords and any(kw in first_sentence for kw in core_keywords):
                    response_text = first_sentence
                else:
                    # 返回前2个句子
                    response_text = "。".join(unique_sentences[:2])
                
                # 确保以句号结尾
                if response_text and not response_text.endswith('。'):
                    response_text += "。"
            else:
                response_text = content[:200].strip()
        else:
            # 最后的回退：返回文档开头部分
            response_text = content[:200].strip()
            if len(content) > 200:
                response_text += "..."
        
        # 添加来源
        doc_id = best_result["metadata"]["doc_id"]
        filename = best_result["metadata"].get("filename", f"文档{doc_id}")
        response_text += f"\n\n📚 来源：{filename}"
        
        return self._format_response(response_text, frontend_type)
    
    def _format_response(self, response_text: str, frontend_type: str) -> str:
        """根据前端类型格式化响应"""
        if frontend_type == "telegram":
            # Telegram：限制长度
            max_length = 4000
            if len(response_text) > max_length:
                response_text = response_text[:max_length] + "\n\n[内容已截断]"
        elif frontend_type == "teams":
            # Teams：使用Markdown格式
            response_text = response_text.replace('\n\n', '\n\n- ')
        
        return response_text


# 知识库实例
kb = KnowledgeBase()
