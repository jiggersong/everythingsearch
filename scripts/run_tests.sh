#!/bin/bash
#
# EverythingSearch 测试运行脚本
#

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 未找到虚拟环境 venv/"
    echo "请先运行: python3.11 -m venv venv && ./venv/bin/pip install pytest"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查 pytest
if ! command -v pytest &> /dev/null; then
    echo "⚠️  未找到 pytest，正在安装..."
    pip install pytest -q
fi

echo "🧪 运行 EverythingSearch 测试..."
echo "================================"

# 运行测试
# 默认运行所有测试
# 使用 -x 在第一个失败时停止
# 使用 -v 显示详细信息
if [ $# -eq 0 ]; then
    # 无参数时运行所有测试
    python -m pytest tests/ -v --tb=short
else
    # 有参数时传递参数
    python -m pytest "$@"
fi

echo ""
echo "✅ 测试完成"
