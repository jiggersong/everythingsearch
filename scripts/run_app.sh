#!/usr/bin/env bash
#
# EverythingSearch 搜索服务管理脚本
# 支持: start | stop | restart | status | dev
#
# 常驻模式 (start/stop/restart): 通过 launchd 管理 gunicorn，开机自启 + 自动拉起
# 开发模式 (dev): 前台运行，Flask 自带服务器，支持热重载
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8000}"
PYTHON="${SCRIPT_DIR}/venv/bin/python"
LAUNCHD_LABEL="com.jigger.everythingsearch.app"

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
    local pid
    pid=$(_get_service_pid)
    if [ -n "$pid" ]; then
        echo "服务已在运行 (PID $pid)"
        echo "   访问: http://127.0.0.1:$PORT"
        return 0
    fi
    echo "启动搜索服务 (端口 $PORT)..."
    launchctl start "$LAUNCHD_LABEL" 2>/dev/null || true
    sleep 2
    pid=$(_get_service_pid)
    if [ -n "$pid" ]; then
        echo "✅ 服务已启动 (PID $pid)"
        echo "   访问: http://127.0.0.1:$PORT"
    else
        echo "❌ 启动失败，请查看 logs/ 下 app_err.log（及按日归档的同名 .YYYY-MM-DD 文件）与 launchd_app_*.log"
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
    # launchd KeepAlive 会自动重启，用 kill 确保进程停止后等 launchd 拉起新进程
    # 这里只是 stop，不需要 launchd 拉起，所以直接 kill
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.5
        done
    fi
    echo "✅ 服务已停止"
    # KeepAlive=true 意味着 launchd 会自动重启，这是预期行为
    # 如需完全停止，请使用: launchctl unload ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist
}

_restart() {
    local old_pid
    old_pid=$(_get_service_pid)
    if [ -n "$old_pid" ]; then
        echo "停止旧服务 (PID $old_pid)..."
        kill "$old_pid" 2>/dev/null || true
        for _ in $(seq 1 15); do
            kill -0 "$old_pid" 2>/dev/null || break
            sleep 0.5
        done
    fi
    echo "等待 launchd 重启服务..."
    sleep 3
    local new_pid
    new_pid=$(_get_service_pid)
    if [ -n "$new_pid" ] && [ "$new_pid" != "$old_pid" ]; then
        echo "✅ 服务已重启 (PID $new_pid)"
        echo "   访问: http://127.0.0.1:$PORT"
    else
        echo "⚠️ 等待 launchd 拉起新进程..."
        sleep 3
        new_pid=$(_get_service_pid)
        if [ -n "$new_pid" ]; then
            echo "✅ 服务已重启 (PID $new_pid)"
            echo "   访问: http://127.0.0.1:$PORT"
        else
            echo "❌ 重启失败，请查看 logs/ 下 app_err.log（及按日归档）与 launchd_app_*.log"
            return 1
        fi
    fi
}

_status() {
    local pid
    pid=$(_get_service_pid)
    if [ -n "$pid" ]; then
        echo "✅ 服务运行中 (PID $pid)"
        echo "   端口: $PORT"
        echo "   访问: http://127.0.0.1:$PORT"
        return 0
    fi
    echo "❌ 服务未运行"
    return 1
}

case "${1:-}" in
    start)
        _start
        ;;
    stop)
        _stop
        ;;
    restart)
        _restart
        ;;
    status)
        _status
        ;;
    dev)
        echo "开发模式 (前台运行，Ctrl+C 停止)..."
        echo "⚠️ 请先确保常驻服务已停止: launchctl unload ~/Library/LaunchAgents/$LAUNCHD_LABEL.plist"
        FLASK_DEBUG=true "$PYTHON" -m everythingsearch.app
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|dev}"
        echo ""
        echo "  start   - 启动服务（通过 launchd）"
        echo "  stop    - 停止服务（launchd KeepAlive 会自动重启）"
        echo "  restart - 重启服务（杀旧进程，launchd 自动拉起新进程）"
        echo "  status  - 查看状态"
        echo "  dev     - 开发模式（前台，支持热重载）"
        exit 1
        ;;
esac
