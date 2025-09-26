#!/usr/bin/env python3
"""
NVC学员信息同步工具启动脚本
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """检查Python版本"""
    if sys.version_info < (3, 8):
        print("❌ 错误: 需要Python 3.8或更高版本")
        print(f"当前版本: {sys.version}")
        sys.exit(1)
    print(f"✅ Python版本检查通过: {sys.version}")

def check_venv():
    """检查虚拟环境"""
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ 虚拟环境已激活")
        return True
    else:
        print("⚠️  警告: 未检测到虚拟环境")
        return False

def install_dependencies():
    """安装依赖"""
    print("📦 检查并安装依赖...")
    try:
        # 不捕获输出，让用户看到安装进度
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                              check=True)
        print("✅ 依赖安装完成")
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        # 如果有错误输出，显示它
        if hasattr(e, 'stderr') and e.stderr:
            print(f"错误详情: {e.stderr.decode()}")
        sys.exit(1)

def check_config():
    """检查配置文件"""
    config_file = Path("config/config.json")
    env_file = Path(".env")
    
    print("🔧 检查配置文件...")
    
    if not config_file.exists():
        print("❌ 配置文件不存在: config/config.json")
        print("请先配置飞书多维表格信息")
        return False
    
    if not env_file.exists():
        print("⚠️  环境变量文件不存在: .env")
        print("提示: 可以先创建测试用的.env文件")
        # 不强制要求.env文件，因为配置也可以在config.json中
        return True
    
    print("✅ 配置文件检查通过")
    return True

def start_server():
    """启动服务器"""
    print("🚀 启动服务器...")
    print("访问地址: http://localhost:8000")
    print("按 Ctrl+C 停止服务")
    print("-" * 50)
    
    try:
        # 启动uvicorn服务器（从项目根目录）
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "backend.app:app", 
            "--reload", 
            "--host", "0.0.0.0", 
            "--port", "8000"
        ])
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

def main():
    """主函数"""
    print("🎓 NVC学员信息自动化同步工具")
    print("=" * 50)

    # 切换到脚本所在目录，确保能找到项目文件
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    print(f"📂 工作目录: {script_dir}")

    # 检查Python版本
    check_python_version()
    
    # 检查虚拟环境
    check_venv()
    
    # 安装依赖
    install_dependencies()
    
    # 检查配置
    if not check_config():
        print("\n📝 配置指南:")
        print("1. 编辑 config/config.json 文件，填入飞书多维表格信息")
        print("2. 创建 .env 文件，填入飞书应用凭证")
        print("3. 参考 README.md 获取详细配置说明")
        sys.exit(1)
    
    # 启动服务器
    start_server()

if __name__ == "__main__":
    main() 