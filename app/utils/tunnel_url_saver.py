"""
Cloudflare Tunnel URL捕获和保存工具
从Cloudflare Tunnel的输出中提取URL并保存到数据库
"""
import re
import sys
import json
import logging
from app.models.database import db

logger = logging.getLogger(__name__)


def extract_tunnel_url(text: str) -> str:
    """从Cloudflare Tunnel输出中提取URL"""
    # Cloudflare Tunnel的输出格式可能是：
    # 1. https://xxxxx.trycloudflare.com
    # 2. 在多行输出中，URL可能在单独一行
    # 3. 可能包含空格或其他字符
    
    if not text:
        return ""
    
    # 清理文本，移除多余空格
    text = text.strip()
    
    # 只匹配真正的Cloudflare Tunnel URL（排除www.cloudflare.com等官方域名）
    patterns = [
        # Cloudflare临时隧道（最优先）- 格式：https://随机字符串.trycloudflare.com
        r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com',
        # Cloudflare命名隧道 - 格式：https://随机字符串.cfargotunnel.com
        r'https://[a-zA-Z0-9\-]+\.cfargotunnel\.com',
    ]
    
    # 排除的域名（不应该匹配这些）
    excluded_domains = [
        'www.cloudflare.com',
        'cloudflare.com',
        'trycloudflare.com',  # 只匹配子域名，不匹配主域名
        'cfargotunnel.com',   # 只匹配子域名，不匹配主域名
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            for url in matches:
                # 清理URL
                url = url.strip().rstrip('/').rstrip('.,;:!?').rstrip()
                
                # 验证URL格式
                if not url.startswith('https://'):
                    continue
                
                # 提取域名部分
                domain = url.replace('https://', '').split('/')[0]
                
                # 排除官方域名
                if domain in excluded_domains:
                    continue
                
                # 确保是有效的Tunnel URL（包含子域名）
                if '.' in domain:
                    domain_parts = domain.split('.')
                    # 应该是 子域名.域名 的格式（至少2部分）
                    if len(domain_parts) >= 2:
                        # 确保不是www或其他常见前缀
                        if domain_parts[0] not in ['www', 'api', 'app', 'dashboard']:
                            # 验证是trycloudflare.com或cfargotunnel.com的子域名
                            if domain.endswith('.trycloudflare.com') or domain.endswith('.cfargotunnel.com'):
                                return url
    
    return ""


def save_webhook_url(url: str):
    """保存webhook URL到数据库（保存完整的webhook URL）"""
    if not url:
        return False
    
    # 清理URL：移除尾随斜杠
    url = url.strip().rstrip('/')
    
    # 如果用户输入的是基础URL，自动加上 /api/teams/messages
    if not url.endswith('/api/teams/messages'):
        # 移除可能的其他路径，然后加上完整路径
        if '/api/' in url:
            url = url.split('/api/')[0]
        url = f"{url}/api/teams/messages"
    
    # 验证URL格式
    if not url.startswith('https://'):
        print(f"⚠️  URL格式无效（必须以https://开头）: {url}", file=sys.stderr)
        return False
    
    # 验证URL包含必要的路径
    if '/api/teams/messages' not in url:
        print(f"⚠️  URL格式无效（必须包含/api/teams/messages）: {url}", file=sys.stderr)
        return False
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 插入或更新webhook URL（使用INSERT OR REPLACE）
        cursor.execute("""
            INSERT OR REPLACE INTO global_config (config_key, config_value, updated_at)
            VALUES ('webhook_base_url', ?, CURRENT_TIMESTAMP)
        """, (url,))
        
        conn.commit()
        conn.close()
        return True
    except Exception:
        logger.exception("保存 Webhook URL 失败")
        return False


def get_webhook_url() -> str:
    """从数据库获取webhook URL"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT config_value FROM global_config
            WHERE config_key = 'webhook_base_url'
        """)
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row["config_value"] or ""
        return ""
    except Exception as e:
        return ""


if __name__ == "__main__":
    """从标准输入读取Cloudflare Tunnel输出并保存URL"""
    if len(sys.argv) > 1:
        # 如果提供了URL作为参数
        url = sys.argv[1]
        if save_webhook_url(url):
            print(f"✅ Webhook URL已保存: {url}")
        else:
            print(f"❌ 保存失败: {url}")
            sys.exit(1)
    else:
        # 从标准输入读取
        input_text = sys.stdin.read()
        url = extract_tunnel_url(input_text)
        if url:
            if save_webhook_url(url):
                print(f"✅ Webhook URL已保存: {url}")
            else:
                print(f"❌ 保存失败: {url}")
                sys.exit(1)
        else:
            print("⚠️ 未找到有效的Tunnel URL")
            sys.exit(1)
