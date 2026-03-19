# MusicNews 本地定时任务配置指南

## 方式一：使用 cron（推荐）

### 1. 查看当前的 cron 任务

```bash
crontab -l
```

### 2. 编辑 cron 任务

```bash
crontab -e
```

### 3. 添加以下内容（每天早上9点运行）

```bash
0 9 * * * /Users/ssg/Documents/CodeX/MusicNews/run_daily.sh
```

或者直接导入配置文件：

```bash
crontab /Users/ssg/Documents/CodeX/MusicNews/crontab.txt
```

### 4. 验证 cron 任务已添加

```bash
crontab -l
```

### 5. 手动测试脚本

```bash
/Users/ssg/Documents/CodeX/MusicNews/run_daily.sh
```

### 6. 查看运行日志

```bash
tail -f /Users/ssg/Documents/CodeX/MusicNews/logs/cron.log
```

---

## 方式二：使用 launchd（macOS 原生）

### 1. 创建 plist 文件

文件位置：`~/Library/LaunchAgents/com.musicnews.daily.plist`

内容：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.musicnews.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/ssg/Documents/CodeX/MusicNews/run_daily.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/ssg/Documents/CodeX/MusicNews/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/ssg/Documents/CodeX/MusicNews/logs/launchd_error.log</string>
</dict>
</plist>
```

### 2. 加载定时任务

```bash
launchctl load ~/Library/LaunchAgents/com.musicnews.daily.plist
```

### 3. 查看任务状态

```bash
launchctl list | grep musicnews
```

### 4. 手动触发测试

```bash
launchctl start com.musicnews.daily
```

### 5. 卸载定时任务

```bash
launchctl unload ~/Library/LaunchAgents/com.musicnews.daily.plist
```

---

## 时间设置说明

### cron 时间格式

```
分 时 日 月 周
0  9  *  *  *    # 每天 9:00
0  8  *  *  1    # 每周一 8:00
30 10 *  *  *    # 每天 10:30
0  9  1  *  *    # 每月1号 9:00
```

### 常用时间示例

- `0 9 * * *` - 每天早上 9:00
- `0 8 * * *` - 每天早上 8:00
- `30 10 * * *` - 每天上午 10:30
- `0 20 * * *` - 每天晚上 8:00

---

## 故障排查

### 1. 检查脚本权限

```bash
ls -l /Users/ssg/Documents/CodeX/MusicNews/run_daily.sh
```

应该显示 `-rwxr-xr-x`（可执行权限）

### 2. 检查 Python 路径

```bash
which python3
```

确保与脚本中的路径一致

### 3. 手动运行测试

```bash
cd /Users/ssg/Documents/CodeX/MusicNews
./run_daily.sh
```

### 4. 查看日志

```bash
cat /Users/ssg/Documents/CodeX/MusicNews/logs/cron.log
```

### 5. macOS 权限问题

如果 cron 无法运行，需要给终端完整磁盘访问权限：

1. 打开 **系统偏好设置 > 安全性与隐私 > 隐私**
2. 选择 **完整磁盘访问权限**
3. 添加 **cron** 或 **/usr/sbin/cron**

---

## 停止定时任务

### 停止 cron

```bash
crontab -e
# 删除或注释掉相关行（在行首添加 #）
```

### 停止 launchd

```bash
launchctl unload ~/Library/LaunchAgents/com.musicnews.daily.plist
rm ~/Library/LaunchAgents/com.musicnews.daily.plist
```

---

## 注意事项

1. **电脑必须开机**：定时任务只在电脑开机时运行
2. **网络连接**：需要联网才能抓取热点和调用 AI
3. **API 额度**：注意 AI API 的调用额度
4. **邮件配额**：QQ 邮箱有发送频率限制（通常足够日报使用）
5. **日志清理**：定期清理 logs 目录下的日志文件

---

## 推荐配置

**推荐使用 cron**，因为：
- ✅ 简单易用
- ✅ 跨平台通用
- ✅ 调试方便

**每天早上 9:00** 是推荐时间，因为：
- ✅ 能抓取到当日最新热点
- ✅ 符合工作时间
- ✅ 不会打扰休息

如需修改时间，编辑 `crontab.txt` 或直接修改 crontab 即可。
