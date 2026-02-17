@echo off
chcp 65001 >nul
echo ========================================
echo   Browserbase CSDN 登录认证助手
echo ========================================
echo.
echo 此工具将帮助你创建 CSDN 的登录 context
echo 完成后，系统将能够自动访问 CSDN 编辑器
echo.
pause
cd /d %~dp0
python browserbase_auth_helper.py create --name csdn --url https://editor.csdn.net/md/?not_checkout=1
echo.
echo ========================================
echo 认证完成后，请执行以下步骤：
echo 1. 打开 config/mcp_servers.json
echo 2. 找到 browserbase-csdn 配置
echo 3. 在 args 中添加: --contextId ^<上面返回的context_id^>
echo 4. 将 enabled 改为 true
echo 5. 重启 WinClaw
echo ========================================
pause
