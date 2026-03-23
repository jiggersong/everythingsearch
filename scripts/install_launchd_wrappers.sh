#!/usr/bin/env bash
#
# 将 launchd 使用的 wrapper 与 plist 对齐到当前仓库布局（无根目录 app.py）。
# 用法:
#   ./scripts/install_launchd_wrappers.sh [项目根目录]
#   PROJECT_ROOT 默认为本脚本所在仓库根目录。
#
# 会先 bootout 再写文件再 bootstrap；需已存在 venv 与 everythingsearch 包。
#
set -euo pipefail

PROJECT_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
WRAPPER_DIR="${HOME}/.local/bin"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
LABEL_APP="com.jigger.everythingsearch.app"
LABEL_INDEX="com.jigger.everythingsearch"
UID_GUI="$(id -u)"

mkdir -p "$WRAPPER_DIR" "$LAUNCH_AGENTS"

echo "项目目录: $PROJECT_ROOT"
echo "停止 launchd 任务（若存在）..."
launchctl bootout "gui/${UID_GUI}/${LABEL_APP}" 2>/dev/null || true
launchctl bootout "gui/${UID_GUI}/${LABEL_INDEX}" 2>/dev/null || true
sleep 1

cat > "${WRAPPER_DIR}/everythingsearch_start.sh" << EOF
#!/usr/bin/env bash
# 由 install_launchd_wrappers.sh 生成 — 勿手改 APP_DIR，请重新运行脚本。
APP_DIR="${PROJECT_ROOT}"
LOG_DIR="\$APP_DIR/logs"
PORT="\${PORT:-8000}"
mkdir -p "\$LOG_DIR"
cd "\$APP_DIR" || exit 1
exec "\$APP_DIR/venv/bin/python" -m gunicorn \\
  -w 1 -b "127.0.0.1:\$PORT" --timeout 120 \\
  --access-logfile "\$LOG_DIR/app.log" \\
  --error-logfile "\$LOG_DIR/app_err.log" \\
  everythingsearch.app:app
EOF
chmod +x "${WRAPPER_DIR}/everythingsearch_start.sh"

cat > "${WRAPPER_DIR}/everythingsearch_index.sh" << EOF
#!/usr/bin/env bash
# 由 install_launchd_wrappers.sh 生成
APP_DIR="${PROJECT_ROOT}"
LOG_DIR="\$APP_DIR/logs"
mkdir -p "\$LOG_DIR"
cd "\$APP_DIR" || exit 1
exec "\$APP_DIR/venv/bin/python" -m everythingsearch.incremental \\
  >> "\$LOG_DIR/incremental.log" 2>&1
EOF
chmod +x "${WRAPPER_DIR}/everythingsearch_index.sh"

cat > "${LAUNCH_AGENTS}/com.jigger.everythingsearch.app.plist" << PLIST_APP
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL_APP}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${WRAPPER_DIR}/everythingsearch_start.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/everythingsearch_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/everythingsearch_stderr.log</string>
</dict>
</plist>
PLIST_APP

cat > "${LAUNCH_AGENTS}/com.jigger.everythingsearch.plist" << PLIST_INDEX
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL_INDEX}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${WRAPPER_DIR}/everythingsearch_index.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>10</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/everythingsearch_index_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/everythingsearch_index_stderr.log</string>
</dict>
</plist>
PLIST_INDEX

echo "注册 launchd..."
launchctl bootstrap "gui/${UID_GUI}" "${LAUNCH_AGENTS}/com.jigger.everythingsearch.app.plist"
launchctl bootstrap "gui/${UID_GUI}" "${LAUNCH_AGENTS}/com.jigger.everythingsearch.plist"

echo "完成。搜索服务: ${LABEL_APP}，定时索引: ${LABEL_INDEX}（每日 10:00）。"
echo "查看状态: ./scripts/run_app.sh status"
