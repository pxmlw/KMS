#!/usr/bin/env python3
"""
启动Cloudflare Tunnel并自动捕获URL保存到数据库
"""
import subprocess
import sys
import os
import re
import time
import threading
import logging

logger = logging.getLogger(__name__)

# 确保从项目根目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 设置环境变量，确保Python能找到app模块
sys.path.insert(0, os.getcwd())

from app.utils.tunnel_url_saver import save_webhook_url, extract_tunnel_url


def monitor_tunnel_output(proc):
    """监控Tunnel输出，提取URL并保存"""
    url_found = False
    buffer = ""  # 用于累积多行输出
    
    try:
        # 逐行读取输出（universal_newlines=True时直接是字符串）
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            print(line, end='', flush=True)  # 实时输出
            
            # 累积输出到buffer（用于多行匹配）
            buffer += line
            
            # 尝试从当前行提取URL
            if not url_found:
                url = extract_tunnel_url(line)
                if not url:
                    # 如果单行没找到，尝试从累积的buffer中提取
                    url = extract_tunnel_url(buffer)
                
                if url:
                    # 验证URL格式
                    if not url.startswith('https://'):
                        print(f"⚠️  提取的URL格式异常: {url}")
                        continue
                    
                    print(f"\n🔗 检测到Tunnel URL: {url}")
                    # 保存完整的webhook URL（save_webhook_url会自动处理，如果输入基础URL会自动加上/api/teams/messages）
                    if save_webhook_url(url):
                        # 获取保存后的完整URL（save_webhook_url内部会处理）
                        from app.utils.tunnel_url_saver import get_webhook_url
                        saved_url = get_webhook_url()
                        print(f"✅ Webhook URL已自动保存到数据库！")
                        print(f"   保存的完整Webhook URL: {saved_url}")
                        print(f"   前端界面将自动显示此URL")
                    else:
                        print(f"⚠️  保存URL失败，请手动保存")
                    url_found = True
                else:
                    # 限制buffer大小，避免内存问题
                    if len(buffer) > 10000:
                        buffer = buffer[-5000:]
    except Exception as e:
        print(f"\n⚠️  监控Tunnel输出时出错: {e}", file=sys.stderr)
        logger.exception("监控Tunnel输出失败")


def main():
    """主函数"""
    print("正在启动Cloudflare Tunnel...")
    print("等待URL生成...\n")
    
    # 启动cloudflared tunnel（使用universal_newlines=True以便直接读取字符串）
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://localhost:8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True
    )
    
    # 在后台线程中监控输出
    monitor_thread = threading.Thread(target=monitor_tunnel_output, args=(proc,), daemon=True)
    monitor_thread.start()
    
    try:
        # 等待进程结束
        proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止Cloudflare Tunnel...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Cloudflare Tunnel已停止")


if __name__ == "__main__":
    main()
