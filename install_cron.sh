#!/bin/bash

# MusicNews 定时任务安装脚本
# 此脚本会将定时任务添加到 crontab

echo "正在安装 MusicNews 每日定时任务..."
echo ""

# 备份当前的 crontab（如果存在）
crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null

# 添加新的定时任务
(crontab -l 2>/dev/null; cat <<EOF
# MusicNews 每日选题推荐定时任务
# 每天早上 9:00 自动运行
0 9 * * * /Users/ssg/Documents/CodeX/MusicNews/run_daily.sh
EOF
) | crontab -

echo "✅ cron 定时任务安装成功！"
echo ""
echo "📋 当前定时任务列表："
crontab -l
echo ""
echo "📖 其他操作："
echo "  - 查看日志: tail -f /Users/ssg/Documents/CodeX/MusicNews/logs/cron.log"
echo "  - 手动运行: /Users/ssg/Documents/CodeX/MusicNews/run_daily.sh"
echo "  - 删除任务: crontab -e (删除相关行)"
echo ""
echo "⏰ 下次运行时间：明天早上 9:00"
