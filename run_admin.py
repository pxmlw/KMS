"""
运行Streamlit管理界面
"""
import subprocess
import sys
import os

# 确保从项目根目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # 设置环境变量，确保Python能找到app模块
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "app/admin/dashboard.py",
        "--server.port", "8501",
        "--server.address", "0.0.0.0"
    ], env=env)
