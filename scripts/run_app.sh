#!/usr/bin/env bash
#
# EverythingSearch 搜索服务管理脚本
# 支持: start | stop | restart | status
#
# 通过 launchd 管理 gunicorn，开机自启 + 自动拉起
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${SCRIPT_DIR}/venv/bin/python"

_read_config_port() {
    "$PYTHON" -c "import config; print(getattr(config, 'PORT', 8000))" 2>/dev/null || echo "8000"
}

SERVICE_PORT="$(_read_config_port)"

LAUNCHD_INSTANCE_FILE="$SCRIPT_DIR/scripts/.launchd_instance"
if [[ -f "$LAUNCHD_INSTANCE_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$LAUNCHD_INSTANCE_FILE"
    set +a
fi

_require_launchd_metadata() {
    if [[ -z "${LABEL_APP:-}" ]]; then
        echo "❌ 缺少 launchd 实例元数据，请先运行: ./scripts/install_launchd_wrappers.sh" >&2
        exit 1
    fi
    LAUNCHD_LABEL="${LABEL_APP}"
    LAUNCHD_PLIST="${HOME}/Library/LaunchAgents/${LAUNCHD_LABEL}.plist"
}

mkdir -p logs

_get_service_pid() {
    # 从 launchctl 获取服务 PID（第一列），"-" 表示未运行
    local pid
    pid=$(launchctl list | awk -v label="$LAUNCHD_LABEL" '$3 == label { print $1 }')
    if [ -n "$pid" ] && [ "$pid" != "-" ]; then
        echo "$pid"
    fi
}

_start() {
    local pid domain="gui/$(id -u)" job_target="${domain}/${LAUNCHD_LABEL}"
    pid=$(_get_service_pid)
    if [ -n "$pid" ]; then
        echo "服务已在运行 (PID $pid)"
        echo "   访问: http://127.0.0.1:$SERVICE_PORT"
        return 0
    fi
    echo "启动搜索服务 (端口 $SERVICE_PORT)..."
    if [ ! -f "$LAUNCHD_PLIST" ]; then
        echo "❌ 未找到 launchd plist: $LAUNCHD_PLIST"
        echo "   请先运行: ./scripts/install_launchd_wrappers.sh"
        return 1
    fi
    if ! launchctl print "$job_target" >/dev/null 2>&1; then
        echo "加载 launchd 任务 (bootstrap)..."
        if ! launchctl bootstrap "$domain" "$LAUNCHD_PLIST" 2>/dev/null; then
            # 已加载或并发 bootstrap 时忽略
            :
        fi
    fi
    launchctl kickstart -k "$job_target" 2>/dev/null || launchctl start "$LAUNCHD_LABEL" 2>/dev/null || true
    sleep 2
    pid=$(_get_service_pid)
    if [ -n "$pid" ]; then
        echo "✅ 服务已启动 (PID $pid)"
        echo "   访问: http://127.0.0.1:$SERVICE_PORT"
    else
        echo "❌ 启动失败，请查看 logs/ 下 app_err.log（及按日归档的同名 .YYYY-MM-DD 文件）与 launchd_app_*.log"
        echo "   也可尝试: $0 resume"
        return 1
    fi
}

_stop() {
    local pid
    pid=$(_get_service_pid)
    if [ -z "$pid" ]; then
        echo "服务未运行"
        return 0
    fi
    echo "停止服务 (PID $pid)..."
    launchctl stop "$LAUNCHD_LABEL" 2>/dev/null || true
    sleep 1
    pid=$(_get_service_pid)
    if [ -z "$pid" ]; then
        echo "✅ 服务已停止"
    else
        echo "⚠️  服务可能仍在运行 (PID $pid)，launchd KeepAlive 会自动重启"
    fi
}

_pause() {
    local domain="gui/$(id -u)" job_target="${domain}/${LAUNCHD_LABEL}"
    if launchctl print "$job_target" >/dev/null 2>&1; then
        echo "暂停服务 (bootout)..."
        launchctl bootout "$domain" "$LAUNCHD_PLIST" 2>/dev/null || true
        echo "✅ 服务已暂停（全量重建期间使用）"
    else
        echo "服务未加载，无需暂停"
    fi
}

_resume() {
    _start
}

_restart() {
    echo "重启搜索服务..."
    launchctl kickstart -k "gui/$(id -u)/${LAUNCHD_LABEL}" 2>/dev/null || {
        _stop
        sleep 1
        _start
        return $?
    }
    sleep 2
    local pid
    pid=$(_get_service_pid)
    if [ -n "$pid" ]; then
        echo "✅ 服务已重启 (PID $pid)"
        echo "   访问: http://127.0.0.1:$SERVICE_PORT"
        return 0
    fi
    echo "❌ 重启失败，请查看 logs/ 下 app_err.log（及按日归档）与 launchd_app_*.log"
    return 1
}

_status() {
    local pid
    pid=$(_get_service_pid)
    if [ -n "$pid" ]; then
        echo "✅ 服务运行中 (PID $pid)"
        echo "   端口: $SERVICE_PORT (config.py)"
        echo "   访问: http://127.0.0.1:$SERVICE_PORT"
        return 0
    fi
    echo "❌ 服务未运行"
    return 1
}

case "${1:-}" in
    start)
        _require_launchd_metadata
        _start
        ;;
    stop)
        _require_launchd_metadata
        _stop
        ;;
    restart)
        _require_launchd_metadata
        _restart
        ;;
    pause)
        _require_launchd_metadata
        _pause
        ;;
    resume)
        _require_launchd_metadata
        _resume
        ;;
    status)
        _require_launchd_metadata
        _status
        ;;
    *)
        echo "用法: $0 {start|stop|restart|pause|resume|status}"
        echo ""
        echo "  start   - 启动服务（通过 launchd）"
        echo "  stop    - 停止服务（launchd KeepAlive 会自动重启）"
        echo "  restart - 重启服务（杀旧进程，launchd 自动拉起新进程）"
        echo "  pause   - 暂停服务（bootout，全量重建期间使用）"
        echo "  resume  - 恢复服务（bootstrap）"
        echo "  status  - 查看状态"
        exit 1
        ;;
esac
