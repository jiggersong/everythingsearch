#!/usr/bin/env bash
#
# 将 launchd plist 与仓库内 wrapper 对齐到当前安装目录（多实例安全）。
# 用法:
#   ./scripts/install_launchd_wrappers.sh [项目根目录]
#   PROJECT_ROOT 默认为本脚本所在仓库根目录。
#
# 实例 ID = sha256(安装目录绝对路径) 前 12 位，Label 为
#   com.jigger.everythingsearch.app.<id>  /  com.jigger.everythingsearch.index.<id>
#
# 需已存在 venv 与 everythingsearch 包；会 bootout 本实例旧 job 再 bootstrap。
#
set -euo pipefail

PROJECT_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
UID_GUI="$(id -u)"

INSTANCE_SUFFIX="$(printf '%s' "$PROJECT_ROOT" | shasum -a 256 | awk '{print substr($1,1,12)}')"
LABEL_APP="com.jigger.everythingsearch.app.${INSTANCE_SUFFIX}"
LABEL_INDEX="com.jigger.everythingsearch.index.${INSTANCE_SUFFIX}"

find_python_bin() {
    if [[ -x "${PROJECT_ROOT}/venv/bin/python" ]]; then
        echo "${PROJECT_ROOT}/venv/bin/python"
        return 0
    fi
    if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
        echo "${PROJECT_ROOT}/.venv/bin/python"
        return 0
    fi
    return 1
}

if ! PYTHON_BIN="$(find_python_bin)"; then
    echo "未找到虚拟环境 Python：请先创建 venv 或 .venv 并安装 requirements/base.txt" >&2
    exit 1
fi

# 与 gunicorn.conf.py 中 os.environ.get("PORT", ...) 的默认值一致
read_default_port() {
    local gc="${PROJECT_ROOT}/gunicorn.conf.py"
    local p
    if [[ -f "$gc" ]]; then
        p=$(sed -n 's/.*get("PORT", "\([^"]*\)".*/\1/p' "$gc" | head -1)
        if [[ -n "$p" ]]; then
            echo "$p"
            return
        fi
    fi
    echo "8000"
}
APP_PORT="$(read_default_port)"

mkdir -p "$LAUNCH_AGENTS" "${PROJECT_ROOT}/scripts"

echo "项目目录: $PROJECT_ROOT"
echo "实例后缀: $INSTANCE_SUFFIX"
echo "Python: $PYTHON_BIN"
echo "默认端口(来自 gunicorn.conf.py): $APP_PORT"

APP_WRAPPER="${PROJECT_ROOT}/scripts/launchd_app_wrapper.sh"
INDEX_WRAPPER="${PROJECT_ROOT}/scripts/launchd_index_wrapper.sh"

cat > "$APP_WRAPPER" << EOF
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${PROJECT_ROOT}"
cd "\$APP_DIR" || exit 1
LOG_DIR="\$APP_DIR/logs"
PORT="\${PORT:-${APP_PORT}}"
LOG_DATE=\$(date +%Y-%m-%d)
mkdir -p "\$LOG_DIR"
exec >>"\$LOG_DIR/launchd_app_\${LOG_DATE}.log" 2>&1
exec "${PYTHON_BIN}" -m gunicorn \\
  -c "\$APP_DIR/gunicorn.conf.py" \\
  -w 1 -b "127.0.0.1:\$PORT" --timeout 120 \\
  everythingsearch.app:app
EOF
chmod +x "$APP_WRAPPER"

cat > "$INDEX_WRAPPER" << EOF
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${PROJECT_ROOT}"
cd "\$APP_DIR" || exit 1
LOG_DIR="\$APP_DIR/logs"
mkdir -p "\$LOG_DIR"
exec "${PYTHON_BIN}" -m everythingsearch.incremental
EOF
chmod +x "$INDEX_WRAPPER"

cat > "${PROJECT_ROOT}/scripts/.launchd_instance" << EOF
INSTANCE_SUFFIX=${INSTANCE_SUFFIX}
LABEL_APP=${LABEL_APP}
LABEL_INDEX=${LABEL_INDEX}
APP_PORT=${APP_PORT}
EOF

cat > "${PROJECT_ROOT}/scripts/.launchd_instance.mk" << EOF
LABEL_APP := ${LABEL_APP}
LABEL_INDEX := ${LABEL_INDEX}
APP_PLIST := ${HOME}/Library/LaunchAgents/${LABEL_APP}.plist
INDEX_PLIST := ${HOME}/Library/LaunchAgents/${LABEL_INDEX}.plist
EOF

PLIST_APP="${LAUNCH_AGENTS}/${LABEL_APP}.plist"
PLIST_INDEX="${LAUNCH_AGENTS}/${LABEL_INDEX}.plist"

echo "停止本实例 launchd 任务（若存在）..."
launchctl bootout "gui/${UID_GUI}/${LABEL_APP}" 2>/dev/null || true
launchctl bootout "gui/${UID_GUI}/${LABEL_INDEX}" 2>/dev/null || true
sleep 1

cat > "$PLIST_APP" << PLIST_APP
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL_APP}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${APP_WRAPPER}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLIST_APP

cat > "$PLIST_INDEX" << PLIST_INDEX
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL_INDEX}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${INDEX_WRAPPER}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>1800</integer>
</dict>
</plist>
PLIST_INDEX

echo "注册 launchd..."
launchctl bootstrap "gui/${UID_GUI}" "$PLIST_APP"
launchctl bootstrap "gui/${UID_GUI}" "$PLIST_INDEX"

echo "完成。搜索服务: ${LABEL_APP}，定时索引: ${LABEL_INDEX}（约每 30 分钟）。"
echo "查看状态: ./scripts/run_app.sh status"
echo ""
echo "⚠️  若曾使用旧版固定 Label，请手动 bootout 并删除 ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist 与 com.jigger.everythingsearch.plist，避免与多实例并存冲突。"
echo "⚠️  请授予 Python 与 /bin/bash「完全磁盘访问」权限（见 docs/INSTALL.md）。"
