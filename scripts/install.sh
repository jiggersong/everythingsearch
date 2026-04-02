#!/usr/bin/env bash
#
# EverythingSearch macOS Installer
# 用于在新 Mac 上从零部署本地语义搜索引擎
#

set -euo pipefail
IFS=$'\n\t'

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="${HOME}/Documents/code/EverythingSearch"

banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     EverythingSearch - macOS Installer       ║${NC}"
    echo -e "${CYAN}║     本地语义搜索引擎 安装程序                  ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
}

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[  OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }

escape_sed_repl() {
    # Escape replacement string for BSD sed: \, &, and delimiter |
    printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        log_error "此安装程序仅支持 macOS"
        exit 1
    fi
    log_ok "macOS $(sw_vers -productVersion)"
}

check_homebrew() {
    if command -v brew &>/dev/null; then
        log_ok "Homebrew 已安装"
    else
        log_warn "Homebrew 未安装，正在安装..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
        log_ok "Homebrew 安装完成"
    fi
}

check_python() {
    local py_cmd=""

    if command -v python3.11 &>/dev/null; then
        py_cmd="python3.11"
    elif command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        case "$ver" in
            3.10|3.11) py_cmd="python3" ;;
        esac
    fi

    if [[ -z "$py_cmd" ]]; then
        log_warn "未找到 Python 3.10/3.11，正在通过 Homebrew 安装 Python 3.11..."
        brew install python@3.11
        py_cmd="python3.11"
        log_ok "Python 3.11 安装完成"
    else
        log_ok "Python: $($py_cmd --version)"
    fi

    PYTHON_CMD="$py_cmd"
}

install_project() {
    local repo_root
    repo_root="$(cd "$(dirname "$0")/.." && pwd)"

    if [[ "$repo_root" == "$INSTALL_DIR" ]]; then
        log_ok "项目已在目标位置: $INSTALL_DIR"
        return
    fi

    echo ""
    echo -e "项目将安装到: ${CYAN}${INSTALL_DIR}${NC}"
    echo -n "确认安装? (Y/n): "
    read -r confirm
    if [[ "$confirm" =~ ^[Nn] ]]; then
        echo -n "请输入自定义安装路径: "
        read -r custom_dir
        if [[ -n "$custom_dir" ]]; then
            INSTALL_DIR="$custom_dir"
        fi
    fi

    mkdir -p "$INSTALL_DIR"

    log_info "复制项目文件到 ${INSTALL_DIR} ..."
    rsync -a --exclude='venv/' \
             --exclude='data/*.db' \
             --exclude='data/mweb_export/' \
             --exclude='*.db' \
             --exclude='__pycache__/' \
             --exclude='.DS_Store' \
             --exclude='logs/*.log' \
             "$repo_root/" "$INSTALL_DIR/"

    log_ok "项目文件复制完成"
}

setup_venv() {
    log_info "创建 Python 虚拟环境..."

    cd "$INSTALL_DIR"

    if [[ -d "venv" ]]; then
        log_warn "虚拟环境已存在，跳过创建"
    else
        $PYTHON_CMD -m venv venv
        log_ok "虚拟环境创建完成"
    fi

    log_info "安装 Python 依赖 (可能需要几分钟)..."
    ./venv/bin/pip install --upgrade pip -q
    ./venv/bin/pip install -r requirements/base.txt -q
    log_ok "依赖安装完成"
}

setup_directories() {
    cd "$INSTALL_DIR"
    mkdir -p logs
    log_ok "日志目录创建完成"
}

configure_project() {
    cd "$INSTALL_DIR"
    local config_file="config.py"

    if [[ ! -f "$config_file" && -f "etc/config.example.py" ]]; then
        cp etc/config.example.py "$config_file"
        log_ok "已从 etc/config.example.py 创建 config.py"
    fi

    echo ""
    echo -e "${CYAN}══════════ 配置向导 ══════════${NC}"
    echo ""

    # API Key
    echo -e "${YELLOW}[必填]${NC} 阿里云 DashScope API Key"
    echo "  获取方式: https://dashscope.console.aliyun.com/apiKey"
    echo -n "  请输入 API Key (sk-...): "
    read -r api_key

    if [[ -n "$api_key" ]]; then
        api_key_esc="$(escape_sed_repl "$api_key")"
        sed -i '' "s|sk-your-api-key-here|${api_key_esc}|g" "$config_file"
        log_ok "API Key 已配置"
    else
        log_warn "未输入 API Key，请稍后手动编辑 config.py"
    fi

    # Target directory
    echo ""
    echo -e "${YELLOW}[必填]${NC} 要索引的文件根目录"
    echo "  示例: /Users/$(whoami)/Documents/myfiles"
    echo -n "  请输入目录路径: "
    read -r target_dir

    if [[ -n "$target_dir" ]]; then
        target_dir="${target_dir%/}"
        target_dir_esc="$(escape_sed_repl "$target_dir")"
        sed -i '' "s|^TARGET_DIR = .*|TARGET_DIR = \"${target_dir_esc}\"|" "$config_file"
        log_ok "索引目录已配置: $target_dir"
    else
        log_warn "未输入索引目录，请稍后手动编辑 config.py"
    fi

    # MWeb (optional)
    echo ""
    echo -e "${BLUE}[可选]${NC} 是否启用 MWeb 数据源？"
    echo -n "  启用 MWeb（需要安装并导出 MWeb Markdown）? (y/N): "
    read -r enable_mweb

    if [[ "$enable_mweb" =~ ^[Yy] ]]; then
        sed -i '' "s|^ENABLE_MWEB = .*|ENABLE_MWEB = True|" "$config_file" 2>/dev/null || true
        log_ok "已开启 MWeb 自动内部导出能力"
    else
        # 强制关闭并清空路径，确保在无 MWeb 的电脑上不报错/不提示
        if grep -q "^ENABLE_MWEB" "$config_file" 2>/dev/null; then
            sed -i '' "s|^ENABLE_MWEB = .*|ENABLE_MWEB = False|" "$config_file" || true
        else
            # 兼容旧配置：在文件末尾追加
            echo "" >> "$config_file"
            echo "ENABLE_MWEB = False" >> "$config_file"
        fi
        log_info "已关闭 MWeb 数据源（ENABLE_MWEB=False）"
    fi

    # Update plist paths (plists reference ~/.local/bin/ wrapper scripts, no Documents paths)
    # Wrapper scripts will be generated in setup_launchd() with correct INSTALL_DIR
    log_ok "配置完成"
}

setup_launchd() {
    mkdir -p "${HOME}/Library/LaunchAgents"
    mkdir -p "${HOME}/.local/bin"
    local wrapper_dir="${HOME}/.local/bin"

    echo ""
    echo -e "${BLUE}[可选]${NC} 是否安装搜索服务开机自启? (登录后自动启动，崩溃自动重启)"
    echo -n "  安装搜索服务常驻? (y/N): "
    read -r install_app

    if [[ "$install_app" =~ ^[Yy] ]]; then
        # Generate wrapper script (outside ~/Documents to avoid macOS TCC restrictions)
        cat > "${wrapper_dir}/everythingsearch_start.sh" << WRAPPER_EOF
#!/usr/bin/env bash
APP_DIR="${INSTALL_DIR}"
LOG_DIR="\$APP_DIR/logs"
PORT="\${PORT:-8000}"
LOG_DATE=\$(date +%Y-%m-%d)
mkdir -p "\$LOG_DIR"
cd "\$APP_DIR" || exit 1
exec >>"\$LOG_DIR/launchd_app_\${LOG_DATE}.log" 2>&1
exec "\$APP_DIR/venv/bin/python" -m gunicorn \\
  -c "\$APP_DIR/gunicorn.conf.py" \\
  -w 1 -b "127.0.0.1:\$PORT" --timeout 120 \\
  everythingsearch.app:app
WRAPPER_EOF
        chmod +x "${wrapper_dir}/everythingsearch_start.sh"

        # Generate plist that calls the wrapper
        local plist_target="${HOME}/Library/LaunchAgents/com.jigger.everythingsearch.app.plist"
        cat > "$plist_target" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jigger.everythingsearch.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${wrapper_dir}/everythingsearch_start.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLIST_EOF
        launchctl bootout gui/$(id -u)/com.jigger.everythingsearch.app 2>/dev/null || true
        sleep 1
        launchctl bootstrap gui/$(id -u) "$plist_target"
        log_ok "搜索服务已安装为开机自启"
        echo "  Wrapper: ${wrapper_dir}/everythingsearch_start.sh"
        echo "  Plist:   $plist_target"
    else
        log_info "跳过搜索服务常驻安装"
    fi

    echo ""
    echo -e "${BLUE}[可选]${NC} 是否安装定时自动增量索引? (约每 30 分钟一次；登录后也会尽快跑一轮)"
    echo -n "  安装定时索引任务? (y/N): "
    read -r install_cron

    if [[ "$install_cron" =~ ^[Yy] ]]; then
        # Generate wrapper script
        cat > "${wrapper_dir}/everythingsearch_index.sh" << WRAPPER_EOF
#!/usr/bin/env bash
APP_DIR="${INSTALL_DIR}"
LOG_DIR="\$APP_DIR/logs"
LOG_DATE=\$(date +%Y-%m-%d)
mkdir -p "\$LOG_DIR"
cd "\$APP_DIR" || exit 1
exec >>"\$LOG_DIR/incremental_\${LOG_DATE}.log" 2>&1
exec "\$APP_DIR/venv/bin/python" -m everythingsearch.incremental
WRAPPER_EOF
        chmod +x "${wrapper_dir}/everythingsearch_index.sh"

        # Generate plist
        local plist_target="${HOME}/Library/LaunchAgents/com.jigger.everythingsearch.plist"
        cat > "$plist_target" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jigger.everythingsearch</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${wrapper_dir}/everythingsearch_index.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>1800</integer>
</dict>
</plist>
PLIST_EOF
        launchctl bootout gui/$(id -u)/com.jigger.everythingsearch 2>/dev/null || true
        sleep 1
        launchctl bootstrap gui/$(id -u) "$plist_target"
        log_ok "定时任务已安装 (约每 30 分钟执行增量索引；修改 plist 后需 bootout + bootstrap 才生效)"
        echo "  Wrapper: ${wrapper_dir}/everythingsearch_index.sh"
        echo "  Plist:   $plist_target"
    else
        log_info "跳过定时任务安装"
    fi
}

build_first_index() {
    echo ""
    echo -e "${CYAN}══════════ 首次索引 ══════════${NC}"
    echo ""
    echo "首次使用需要构建索引，根据文件数量可能需要 10 分钟到数小时不等。"
    echo "建议在电脑不使用时执行（脚本会自动防止系统休眠）。"
    echo ""
    echo -n "现在开始构建索引? (y/N): "
    read -r build_now

    if [[ "$build_now" =~ ^[Yy] ]]; then
        cd "$INSTALL_DIR"
        log_info "开始构建索引 (使用 caffeinate 防止系统休眠)..."
        caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
        log_ok "索引构建完成!"
    else
        log_info "跳过首次索引。稍后可运行:"
        echo ""
        echo "  cd $INSTALL_DIR"
        echo "  caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full"
        echo ""
    fi
}

create_launcher() {
    cd "$INSTALL_DIR"
    cat > start.sh << 'LAUNCHER_EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
echo "EverythingSearch 启动中..."
echo "浏览器访问: http://127.0.0.1:8000"
echo "按 Ctrl+C 停止服务"
./venv/bin/python -m everythingsearch.app
LAUNCHER_EOF
    chmod +x start.sh
    log_ok "快捷启动脚本已创建: ${INSTALL_DIR}/start.sh"
    log_ok "服务管理脚本: ./scripts/run_app.sh {start|stop|restart|status|dev}"
}

print_summary() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          安装完成!                            ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}项目位置${NC}: $INSTALL_DIR"
    echo -e "  ${CYAN}配置文件${NC}: $INSTALL_DIR/config.py"
    echo -e "  ${CYAN}安装指引${NC}: $INSTALL_DIR/docs/INSTALL.md"
    echo ""
    echo -e "  ${YELLOW}启动服务${NC}:"
    echo "    开发: cd $INSTALL_DIR && ./start.sh"
    echo "    常驻: cd $INSTALL_DIR && ./scripts/run_app.sh start"
    echo "    管理: ./scripts/run_app.sh {stop|restart|status}"
    echo ""
    echo -e "  ${YELLOW}浏览器打开${NC}: http://127.0.0.1:8000"
    echo ""
    echo -e "  ${YELLOW}手动增量索引${NC}:"
    echo "    cd $INSTALL_DIR && ./venv/bin/python -m everythingsearch.incremental"
    echo ""
    echo -e "  ${YELLOW}完整重建索引${NC}:"
    echo "    cd $INSTALL_DIR && caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full"
    echo ""
}

# ──── Main ────

banner
check_macos
check_homebrew
check_python
install_project
setup_venv
setup_directories
configure_project
create_launcher
setup_launchd
build_first_index
print_summary
