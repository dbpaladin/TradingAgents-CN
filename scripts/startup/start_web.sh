#!/bin/bash
# TradingAgents-CN Web应用启动脚本

echo "🚀 启动TradingAgents-CN Web应用..."
echo

# 激活虚拟环境
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✅ 已激活项目虚拟环境 .venv"
elif [ -f "env/bin/activate" ]; then
    source env/bin/activate
    echo "✅ 已激活兼容虚拟环境 env"
else
    echo "❌ 未找到可用虚拟环境，请先创建 .venv 或 env"
    exit 1
fi

# 检查项目是否已安装
if ! python -c "import tradingagents" 2>/dev/null; then
    echo "📦 安装项目到虚拟环境..."
    pip install -e .
fi

# 启动Streamlit应用
python start_web.py

echo "按任意键退出..."
read -n 1
