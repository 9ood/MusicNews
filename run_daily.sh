#!/bin/bash

LOG="/Users/ssg/Documents/CodeX/MusicNews/logs/cron.log"

# 记录开始时间
{
    echo "========================================"
    echo "开始执行: $(date)"
    
    # 设置环境
    export PATH="/Users/ssg/.pyenv/shims:/usr/local/bin:/usr/bin:/bin"
    export PYENV_ROOT="/Users/ssg/.pyenv"
    export HOME="/Users/ssg"
    export PYTHONUNBUFFERED=1
    
    # 切换到项目目录
    cd /Users/ssg/Documents/CodeX/MusicNews || {
        echo "❌ cd 失败"
        exit 1
    }
    
    echo "开始执行 Python 脚本..."
    
    # 执行 Python 脚本，确保所有输出都被捕获
    /Users/ssg/.pyenv/shims/python3 main.py 2>&1
    EXIT_CODE=$?
    
    echo "Python 退出码: $EXIT_CODE"
    echo "结束执行: $(date)"
    echo "========================================"
} >> "$LOG" 2>&1
