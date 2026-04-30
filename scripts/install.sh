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

INSTALL_DIR="$PWD"

banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     EverythingSearch - macOS Installer               ║${NC}"
    echo -e "${CYAN}║     本地语义搜索引擎 安装程序                         ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

welcome() {
    # 动态统计依赖包数量（相对于脚本所在仓库根目录）
    local repo_root
    repo_root="$(cd "$(dirname "$0")/.." && pwd)"
    local pkg_count
    pkg_count=$(grep -cE '^[a-zA-Z0-9]' "$repo_root/requirements/base.txt" 2>/dev/null || echo "0")
    local est_low=$(( pkg_count * 2 / 60 ))
    local est_high=$(( pkg_count * 4 / 60 ))
    if (( est_low < 1 )); then est_low=1; fi
    if (( est_high < est_low )); then est_high=$((est_low + 1)); fi

    banner

    echo -e "  ${GREEN}欢迎使用 EverythingSearch！${NC}"
    echo ""

    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${YELLOW}核心能力${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "  • 自然语言搜索本地文件 — 用句子或关键词找到文档/代码/笔记"
    echo "  • 文件名 + 正文混合匹配 — 标题和正文内容同时参与检索"
    echo "  • 按目录/时间过滤 — 精准缩小搜索范围"
    echo "  • 浏览器 Web UI — 清晰布局，可选 AI 辅助解读"
    echo "  • 纯本地运行 — 索引和向量数据存储在 Mac 本地"
    echo "  • CLI / Agent 支持 — JSON 输出，可接入 LLM Agent"
    echo ""

    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${YELLOW}安装流程概览${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "  1. 环境检查 (macOS / Homebrew / Python 3.10-3.11)"
    echo "  2. 安装 Python 依赖 (${pkg_count} 个包，约 ${est_low}-${est_high} 分钟)"
    echo "  3. 配置向导 (API Key + 索引目标目录)"
    echo "  4. 可选：开机自启 + 定时增量索引"
    echo "  5. 可选：立即构建首次索引"
    echo ""

    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${YELLOW}需要提前准备${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "  • 阿里云 DashScope API Key（免费注册获取）"
    echo "    https://dashscope.console.aliyun.com/apiKey"
    echo "  • 要索引的文件夹路径（如 ~/Documents/myfiles）"
    echo ""
    echo -e "  ${BLUE}安装全程约 10-15 分钟${NC}（不含首次索引）。"
    echo "  首次索引耗时取决于文件数量，从数分钟到数小时不等。"
    echo ""

    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -n "是否现在开始安装？(Y/n): "
    read -r start_now
    if [[ "$start_now" =~ ^[Nn] ]]; then
        echo ""
        echo -e "  ${YELLOW}已取消安装${NC}，准备好后再次运行: ./scripts/install.sh"
        echo ""
        exit 0
    fi
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

    # 根据依赖数量预估安装时间（所有包均已固定版本，无需解析依赖树，主要耗时在下载和安装）
    local pkg_count
    pkg_count=$(grep -cE '^[a-zA-Z0-9]' requirements/base.txt 2>/dev/null || echo "0")
    local est_low=$(( pkg_count * 2 / 60 ))
    local est_high=$(( pkg_count * 4 / 60 ))
    if (( est_low < 1 )); then est_low=1; fi
    if (( est_high < est_low )); then est_high=$((est_low + 1)); fi

    log_info "检测到 ${pkg_count} 个依赖包，预计安装时间约 ${est_low}-${est_high} 分钟（视网络状况而定）"
    echo -e "  ${YELLOW}提示${NC}: 若网络访问 PyPI 较慢，可设置镜像源: pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple"
    echo ""

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
        sed -i '' "s|^MY_API_KEY = .*|MY_API_KEY = \"${api_key_esc}\"|" "$config_file"
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

    # ⚠️ 提前告知 macOS TCC 隐私弹窗问题，避免用户被连续弹窗惊吓
    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  ⚠️  关于 macOS 隐私授权弹窗，请务必阅读                       ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  macOS 对后台进程有严格的隐私保护。如果安装后台服务，Python"
    echo "  在访问文件时，系统会弹出确认框："
    echo ""
    echo -e "    ${RED}「python3.11 想访问其他 App 的数据」${NC}"
    echo ""
    echo "  ⚡ 该弹窗可能连续出现多次（每访问一个新目录触发一次），"
    echo "     容易造成困扰。"
    echo ""
    echo -e "  ${GREEN}解决方案${NC}：安装完成后，在「系统设置 → 隐私与安全性 →"
    echo "  完全磁盘访问」中勾选 Python 和 /bin/bash 即可一劳永逸。"
    echo "  （稍后会弹出详细图文指引，也可稍后手动操作）"
    echo ""

    echo ""
    echo -e "${BLUE}[可选]${NC} 是否安装搜索服务开机自启? (登录后自动启动，崩溃自动重启)"
    echo -n "  安装搜索服务常驻? (y/N): "
    read -r install_app

    if [[ "$install_app" =~ ^[Yy] ]]; then
        APP_SERVICE_INSTALLED=true
        # Generate wrapper script (outside ~/Documents to avoid macOS TCC restrictions)
        cat > "${wrapper_dir}/everythingsearch_start.sh" << WRAPPER_EOF
#!/usr/bin/env bash
APP_DIR="${INSTALL_DIR}"
LOG_DIR="\$APP_DIR/logs"
PORT="\${PORT:-${APP_PORT}}"
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
        INDEX_SERVICE_INSTALLED=true
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

show_full_disk_access_guide() {
    # Only relevant if launchd services were installed
    local need_guide=false
    if [[ "${APP_SERVICE_INSTALLED:-false}" == "true" ]] || [[ "${INDEX_SERVICE_INSTALLED:-false}" == "true" ]]; then
        need_guide=true
    fi
    if [[ "$need_guide" == "false" ]]; then
        return
    fi

    local py_path
    py_path=$("${INSTALL_DIR}/venv/bin/python" -c 'import sys; print(sys.executable)' 2>/dev/null) || true

    if [[ -z "$py_path" ]]; then
        py_path="${INSTALL_DIR}/venv/bin/python"
    fi

    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  🔐 授权指南：消除上面提到的隐私弹窗（约 30 秒）              ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  按以下步骤授予「完全磁盘访问」权限："
    echo ""
    echo "  1. 打开 系统设置 → 隐私与安全性 → 完全磁盘访问"
    echo "  2. 点击左下角「+」按钮"
    echo "  3. 按 Cmd+Shift+G，粘贴路径，点击「打开」："
    echo ""
    echo -e "       ${GREEN}${py_path}${NC}"
    echo ""
    echo "  4. 再次点击「+」，添加："
    echo ""
    echo -e "       ${GREEN}/bin/bash${NC}"
    echo ""
    echo "  5. 确保两个条目的开关均为「开启」（蓝色）"
    echo ""
    echo "  授权后所有后台任务静默运行，不再弹窗。"
    echo ""

    echo -n "是否现在打开系统设置的「完全磁盘访问」面板？(Y/n): "
    read -r open_settings
    if [[ ! "$open_settings" =~ ^[Nn] ]]; then
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
        echo ""
        echo -e "  ${CYAN}系统设置已打开，请按上述步骤添加：${NC}"
        echo -e "    ${GREEN}${py_path}${NC}"
        echo -e "    ${GREEN}/bin/bash${NC}"
        echo ""
    fi

    echo -e "  ${YELLOW}💡 提示${NC}: Homebrew 升级 Python 小版本（如 3.11.15→3.11.16）后"
    echo "  路径中的版本号会变化，届时需重新授权。运行以下命令查看最新路径："
    echo ""
    echo -e "    cd ${INSTALL_DIR} && ./venv/bin/python -c 'import sys; print(sys.executable)'"
    echo ""
}

build_first_index() {
    echo ""
    echo -e "${CYAN}══════════ 首次索引 ══════════${NC}"
    echo ""
    echo "首次使用需要构建索引，根据文件数量可能需要 10 分钟到数小时不等。"
    echo "开始后会先输出文件规模、预计索引块、预计 Token 和预计耗时。"
    echo "构建过程中每 30 秒会输出一次进度，完成后会输出总结报告。"
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

check_port() {
    local default_port=8000
    local preferred_ports=(8010 8020 8030 8040 8050 8060 8070 8090)

    if ! lsof -i :${default_port} -sTCP:LISTEN -t &>/dev/null; then
        APP_PORT=$default_port
        log_ok "端口 ${APP_PORT} 可用"
        return
    fi

    log_warn "端口 ${default_port} 已被占用："
    lsof -i :${default_port} -sTCP:LISTEN -P -n 2>/dev/null || true
    echo ""

    for p in "${preferred_ports[@]}"; do
        if ! lsof -i :${p} -sTCP:LISTEN -t &>/dev/null; then
            APP_PORT=$p
            break
        fi
    done

    # 首选端口均被占用时，在 8011-8099 范围内查找（跳过 8080）
    if [[ -z "${APP_PORT:-}" ]]; then
        for ((p=8011; p<=8099; p++)); do
            if (( p == 8080 )); then continue; fi
            if ! lsof -i :${p} -sTCP:LISTEN -t &>/dev/null; then
                APP_PORT=$p
                break
            fi
        done
    fi

    # 极端情况：80xx 全满，回退到 8000
    if [[ -z "${APP_PORT:-}" ]]; then
        APP_PORT=$default_port
        log_warn "未找到可用替代端口，仍使用 ${APP_PORT}（可能与现有服务冲突）"
        return
    fi

    log_info "自动选择替代端口: ${APP_PORT}"

    # 更新 gunicorn.conf.py 默认端口
    sed -i '' "s|os.environ.get(\"PORT\", \"8000\")|os.environ.get(\"PORT\", \"${APP_PORT}\")|" \
        "$INSTALL_DIR/gunicorn.conf.py"
    log_ok "已更新 gunicorn.conf.py 默认端口为 ${APP_PORT}"
}

create_launcher() {
    cd "$INSTALL_DIR"
    cat > start.sh << LAUNCHER_EOF
#!/usr/bin/env bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
cd "\$DIR"
echo "EverythingSearch 启动中..."
echo "浏览器访问: http://127.0.0.1:${APP_PORT}"
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
    echo -e "  ${YELLOW}浏览器打开${NC}: http://127.0.0.1:${APP_PORT}"
    echo ""
    echo -e "  ${YELLOW}命令行/Agent 接入检索${NC}:"
    echo "    cd $INSTALL_DIR && ./venv/bin/python -m everythingsearch search \"你要搜的词\" --json"
    echo ""
    echo -e "  ${YELLOW}手动增量索引${NC}:"
    echo "    cd $INSTALL_DIR && ./venv/bin/python -m everythingsearch.incremental"
    echo ""
    echo -e "  ${YELLOW}完整重建索引${NC}:"
    echo "    cd $INSTALL_DIR && caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full"
    echo "    索引任务会自动输出规模预估、30 秒进度和完成总结。"
    echo ""
}

# ──── Main ────

welcome
check_macos
check_homebrew
check_python
install_project
setup_venv
setup_directories
configure_project
check_port
create_launcher
setup_launchd
show_full_disk_access_guide
build_first_index
print_summary
