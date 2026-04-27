#!/usr/bin/env bash
#
# EverythingSearch 自动升级脚本
# 支持从 v1.0.0 之后任意版本升级到当前最新版本
#
# 用法:
#   cd /path/to/new/EverythingSearch
#   ./scripts/upgrade.sh [旧项目路径]
#
#   旧项目路径默认为 ~/Documents/code/EverythingSearch
#
set -euo pipefail
IFS=$'\n\t'

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

NEW_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OLD_ROOT="${1:-$HOME/Documents/code/EverythingSearch}"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_DIR=""

# ──── 日志函数 ────

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[  OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }

banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   EverythingSearch 自动升级程序              ║${NC}"
    echo -e "${CYAN}║   从任意 v1.0+ 版本升级到当前最新版          ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
}

# ──── 版本检测 ────

detect_scenario() {
    local root="$1"
    local has_config=false
    local has_data_dir=false
    local has_chromadb=false
    local has_sparse=false
    local chromadb_root=false

    [[ -f "$root/config.py" ]] && has_config=true
    [[ -d "$root/data" ]] && has_data_dir=true
    [[ -d "$root/data/chroma_db" ]] && has_chromadb=true
    [[ -f "$root/data/sparse_index.db" ]] && has_sparse=true
    [[ -d "$root/chroma_db" ]] && chromadb_root=true

    if [[ "$has_sparse" == "true" ]]; then
        echo "C"
    elif [[ "$has_chromadb" == "true" ]]; then
        echo "B"
    elif [[ "$has_config" == "true" ]] || [[ "$chromadb_root" == "true" ]]; then
        echo "A"
    else
        echo "NEW"
    fi
}

describe_scenario() {
    case "$1" in
        A) echo "v1.0.x – v1.1.x（旧目录结构，无 FTS5 稀疏索引）" ;;
        B) echo "v1.2.0 – v1.5.2（已有 data/ 目录，无 FTS5 稀疏索引）" ;;
        C) echo "v2.0.0+（已有双索引，格式兼容）" ;;
        NEW) echo "未检测到旧安装" ;;
    esac
}

# ──── 配置提取 ────

extract_config_value() {
    local config_dir="$1"
    local key="$2"
    python3 - "$config_dir" "$key" <<'PY' 2>/dev/null
import importlib
import json
import sys

config_dir, key = sys.argv[1], sys.argv[2]
sys.path.insert(0, config_dir)

try:
    config = importlib.import_module("config")
except ModuleNotFoundError:
    sys.exit(1)

if not hasattr(config, key):
    sys.exit(1)

value = getattr(config, key)
if value is None:
    sys.exit(1)
if isinstance(value, (list, tuple)):
    print(json.dumps([str(item) for item in value], ensure_ascii=False))
elif isinstance(value, bool):
    print("true" if value else "false")
else:
    print(str(value))
PY
}

extract_config_literal() {
    local config_dir="$1"
    local key="$2"
    python3 - "$config_dir" "$key" <<'PY' 2>/dev/null
import importlib
import json
import sys

config_dir, key = sys.argv[1], sys.argv[2]
sys.path.insert(0, config_dir)

try:
    config = importlib.import_module("config")
except ModuleNotFoundError:
    sys.exit(1)

if not hasattr(config, key):
    sys.exit(1)

value = getattr(config, key)
if value is None:
    sys.exit(1)
if isinstance(value, (list, tuple)):
    print(json.dumps([str(item) for item in value], ensure_ascii=False))
elif isinstance(value, bool):
    print("True" if value else "False")
elif isinstance(value, (int, float)):
    print(repr(value))
else:
    print(json.dumps(str(value), ensure_ascii=False))
PY
}

python_string_literal() {
    python3 - "$1" <<'PY'
import json
import sys

print(json.dumps(sys.argv[1], ensure_ascii=False))
PY
}

set_config_assignment() {
    local config_file="$1"
    local key="$2"
    local literal="$3"
    python3 - "$config_file" "$key" "$literal" <<'PY'
from pathlib import Path
import re
import sys

config_file = Path(sys.argv[1])
key = sys.argv[2]
literal = sys.argv[3]
lines = config_file.read_text(encoding="utf-8").splitlines()
pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")

for index, line in enumerate(lines):
    if pattern.match(line):
        lines[index] = f"{key} = {literal}"
        break
else:
    lines.append(f"{key} = {literal}")

config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

# ──── 备份 ────

create_backup() {
    local root="$1"
    mkdir -p "$BACKUP_DIR"
    log_info "创建备份到: $BACKUP_DIR"

    if [[ -f "$root/config.py" ]]; then
        cp "$root/config.py" "$BACKUP_DIR/config.py"
        log_ok "已备份 config.py"
    fi

    if [[ -f "$root/data/embedding_cache.db" ]]; then
        cp "$root/data/embedding_cache.db" "$BACKUP_DIR/embedding_cache.db"
        log_ok "已备份 embedding_cache.db"
    fi

    if [[ -d "$root/data/chroma_db" ]]; then
        cp -R "$root/data/chroma_db" "$BACKUP_DIR/chroma_db"
        log_ok "已备份 chroma_db/"
    fi

    if [[ -d "$root/chroma_db" ]]; then
        cp -R "$root/chroma_db" "$BACKUP_DIR/chroma_db_root"
        log_ok "已备份 chroma_db/ (根目录)"
    fi

    log_info "备份完成。如需恢复: cp -r $BACKUP_DIR/* $root/"
}

# ──── 代码同步 ────

sync_code() {
    local src="$NEW_ROOT"
    local dst="$1"

    if [[ "$src" == "$dst" ]]; then
        log_info "新版本已在目标位置，跳过代码同步"
        return
    fi

    echo ""
    log_info "同步新版本代码到: $dst"
    rsync -a --exclude='venv/' \
             --exclude='.venv/' \
             --exclude='data/' \
             --exclude='*.db' \
             --exclude='*.db-wal' \
             --exclude='*.db-shm' \
             --exclude='__pycache__/' \
             --exclude='.DS_Store' \
             --exclude='logs/*.log' \
             --exclude='config.py' \
             --exclude='upgrade_backups_*/' \
             "$src/" "$dst/"
    log_ok "代码同步完成"
}

# ──── 配置合并 ────

merge_config() {
    local old_config_dir="$1"
    local target="$2"

    log_info "合并配置文件..."

    # 先从旧配置提取值（在覆写 config.py 之前）
    local api_key
    api_key=$(extract_config_value "$old_config_dir" "MY_API_KEY" || true)
    local target_dir_literal
    target_dir_literal=$(extract_config_literal "$old_config_dir" "TARGET_DIR" || true)
    local enable_mweb
    enable_mweb=$(extract_config_value "$old_config_dir" "ENABLE_MWEB" || true)
    enable_mweb="${enable_mweb:-false}"
    local mweb_lib
    mweb_lib=$(extract_config_value "$old_config_dir" "MWEB_LIBRARY_PATH" || true)
    mweb_lib="${mweb_lib:-}"
    local mweb_dir_old
    mweb_dir_old=$(extract_config_value "$old_config_dir" "MWEB_DIR" || true)
    mweb_dir_old="${mweb_dir_old:-}"

    # 从模板创建新 config.py
    if [[ -f "$target/etc/config.example.py" ]]; then
        cp "$target/etc/config.example.py" "$target/config.py"
        log_ok "已从模板生成 config.py"
    else
        log_warn "未找到 etc/config.example.py，跳过配置生成"
        return
    fi

    # 写入提取的值
    if [[ -n "$api_key" && "$api_key" != "None" ]]; then
        set_config_assignment "$target/config.py" "MY_API_KEY" "$(python_string_literal "$api_key")"
        log_ok "已迁移 MY_API_KEY"
    else
        log_warn "旧配置中未找到 MY_API_KEY，请稍后手动填写 config.py"
    fi

    if [[ -n "$target_dir_literal" && "$target_dir_literal" != "None" ]]; then
        set_config_assignment "$target/config.py" "TARGET_DIR" "$target_dir_literal"
        log_ok "已迁移 TARGET_DIR"
    else
        log_warn "旧配置中未找到 TARGET_DIR，请稍后手动编辑 config.py"
    fi

    if [[ "$enable_mweb" == "true" ]]; then
        set_config_assignment "$target/config.py" "ENABLE_MWEB" "True"
        log_ok "已开启 ENABLE_MWEB"
        if [[ -n "$mweb_lib" && "$mweb_lib" != "None" ]]; then
            set_config_assignment "$target/config.py" "MWEB_LIBRARY_PATH" "$(python_string_literal "$mweb_lib")"
        fi
        if [[ -n "$mweb_dir_old" && "$mweb_dir_old" != "None" ]]; then
            set_config_assignment "$target/config.py" "MWEB_DIR" "$(python_string_literal "$mweb_dir_old")"
        fi
    fi
}

find_venv_bin() {
    local root="$1"
    if [[ -x "$root/venv/bin/python" ]]; then
        echo "$root/venv/bin"
        return 0
    fi
    if [[ -x "$root/.venv/bin/python" ]]; then
        echo "$root/.venv/bin"
        return 0
    fi
    return 1
}

python_command_hint() {
    local root="$1"
    local venv_bin
    if venv_bin=$(find_venv_bin "$root"); then
        echo "$venv_bin/python"
    else
        echo "./venv/bin/python"
    fi
}

update_dependencies() {
    local root="$1"
    local requirements_file="$root/requirements/base.txt"

    if [[ ! -f "$requirements_file" ]]; then
        log_warn "未找到 requirements/base.txt，跳过依赖更新"
        return
    fi

    local venv_bin
    if ! venv_bin=$(find_venv_bin "$root"); then
        log_warn "未找到虚拟环境，跳过依赖更新。请稍后手动执行: ./venv/bin/python -m pip install -r requirements/base.txt"
        return
    fi

    log_info "更新 Python 运行时依赖..."
    if "$venv_bin/python" -m pip install -r "$requirements_file"; then
        log_ok "Python 依赖已更新"
    else
        log_error "Python 依赖安装失败，请检查网络连接和 requirements/base.txt 后重试"
        exit 1
    fi
}

# ──── 数据清理 ────

cleanup_for_scenario() {
    local scenario="$1"
    local root="$2"

    case "$scenario" in
        A|B)
            log_info "清理不兼容的旧索引和缓存..."
            # 删除旧 ChromaDB（元数据格式不兼容）
            if [[ -d "$root/data/chroma_db" ]]; then
                rm -rf "$root/data/chroma_db"
                log_ok "已删除 data/chroma_db/"
            fi
            if [[ -d "$root/chroma_db" ]]; then
                rm -rf "$root/chroma_db"
                log_ok "已删除 chroma_db/ (根目录)"
            fi
            # 删除旧的扫描和状态缓存（全量重建时会重新生成）
            rm -f "$root/data/scan_cache.db" "$root/data/scan_cache.db-wal" "$root/data/scan_cache.db-shm"
            rm -f "$root/data/index_state.db" "$root/data/index_state.db-wal" "$root/data/index_state.db-shm"
            rm -f "$root/data/sparse_index.db" "$root/data/sparse_index.db-wal" "$root/data/sparse_index.db-shm"
            log_ok "已清理扫描缓存和索引状态"
            ;;
        C)
            log_info "索引格式兼容，保留现有索引"
            # 仅清理扫描缓存以触发重新扫描
            rm -f "$root/data/scan_cache.db" "$root/data/scan_cache.db-wal" "$root/data/scan_cache.db-shm"
            rm -f "$root/data/index_state.db" "$root/data/index_state.db-wal" "$root/data/index_state.db-shm"
            # 清理 ChromaDB WAL 残留，防止崩溃恢复后状态不一致
            rm -f "$root/data/chroma_db/chroma.sqlite3-wal" "$root/data/chroma_db/chroma.sqlite3-shm" 2>/dev/null || true
            log_ok "已清理扫描缓存、索引状态和 WAL 残留（下次增量索引将自动重建）"
            ;;
    esac

    # 清理 WAL 残留和 __pycache__
    rm -f "$root/data/"*.db-wal "$root/data/"*.db-shm 2>/dev/null || true
    find "$root" \( -path "$root/venv" -o -path "$root/.venv" \) -prune -o -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
}

# ──── Launchd 更新 ────

update_launchd() {
    local root="$1"

    if [[ ! -f "$root/scripts/install_launchd_wrappers.sh" ]]; then
        log_warn "未找到 install_launchd_wrappers.sh，跳过 launchd 更新"
        return
    fi

    echo ""
    log_info "更新 launchd 后台服务..."
    if ! find_venv_bin "$root" >/dev/null; then
        log_warn "未找到虚拟环境，跳过 launchd 更新"
        return
    fi
    bash "$root/scripts/install_launchd_wrappers.sh" "$root"
    log_ok "launchd 服务已更新（wrapper 脚本和 plist 已指向当前项目路径）"
}

# ──── 索引重建 ────

rebuild_index() {
    local scenario="$1"
    local root="$2"

    case "$scenario" in
        A|B)
            echo ""
            echo -e "${YELLOW}══════════ 索引重建 ══════════${NC}"
            echo ""
            echo "由于旧版索引格式与当前版本不兼容，必须全量重建索引。"
            echo "根据文件数量，可能需要 10 分钟到数小时不等。"
            echo "期间会调用 DashScope 嵌入 API（可能产生少量费用）。"
            echo ""
            echo -n "是否现在开始重建索引? (y/N): "
            read -r build_now

            if [[ "$build_now" =~ ^[Yy] ]]; then
                cd "$root"
                local venv_bin
                if ! venv_bin=$(find_venv_bin "$root"); then
                    log_warn "未找到虚拟环境，请先运行: python3 -m venv venv && ./venv/bin/pip install -r requirements/base.txt"
                    return
                fi
                log_info "开始全量重建索引 (使用 caffeinate 防止系统休眠)..."
                caffeinate -i "$venv_bin/python" -m everythingsearch.incremental --full
                log_ok "索引重建完成!"
            else
                log_info "跳过索引重建。请稍后手动执行:"
                echo ""
                echo "  cd $root"
                echo "  caffeinate -i $(python_command_hint "$root") -m everythingsearch.incremental --full"
                echo ""
            fi
            ;;
        C)
            echo ""
            log_info "索引格式兼容，无需全量重建"
            echo "  建议运行增量索引以验证一切正常:"
            echo ""
            echo "  cd $root"
            echo "  $(python_command_hint "$root") -m everythingsearch.incremental"
            echo ""
            ;;
    esac
}

# ──── 完整性检查 ────

verify_upgrade() {
    local root="$1"
    local ok=true

    echo ""
    log_info "运行完整性检查..."

    if [[ ! -f "$root/config.py" ]]; then
        log_error "config.py 缺失"
        ok=false
    else
        log_ok "config.py 存在"
    fi

    if [[ ! -f "$root/everythingsearch/__init__.py" ]]; then
        log_error "everythingsearch 包缺失，代码同步可能失败"
        ok=false
    else
        log_ok "everythingsearch 包存在"
    fi

    if [[ ! -d "$root/data" ]]; then
        log_warn "data/ 目录不存在，正在创建..."
        mkdir -p "$root/data"
    fi
    log_ok "data/ 目录就绪"

    if [[ "$ok" == "false" ]]; then
        log_error "完整性检查未通过，请检查上述错误"
        return 1
    fi
    log_ok "完整性检查通过"
}

# ──── 打印最终指引 ────

print_guide() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           升级完成!                          ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}项目位置${NC}: $TARGET_ROOT"
    echo -e "  ${CYAN}配置文件${NC}: $TARGET_ROOT/config.py"
    echo -e "  ${CYAN}备份位置${NC}: $BACKUP_DIR"
    echo ""
    echo -e "  ${YELLOW}启动服务${NC}:"
    echo "    cd $TARGET_ROOT && ./start.sh"
    echo "    cd $TARGET_ROOT && ./scripts/run_app.sh start"
    echo ""
    echo -e "  ${YELLOW}命令行搜索${NC}:"
    echo "    cd $TARGET_ROOT && $(python_command_hint "$TARGET_ROOT") -m everythingsearch search \"关键词\" --json"
    echo ""
    echo -e "  ${YELLOW}完整重建索引${NC}:"
    echo "    cd $TARGET_ROOT && caffeinate -i $(python_command_hint "$TARGET_ROOT") -m everythingsearch.incremental --full"
    echo ""
}

# ──── Main ────

TARGET_ROOT=""

main() {
    banner

    # 1. 检查 macOS
    if [[ "$(uname)" != "Darwin" ]]; then
        log_error "此脚本仅支持 macOS"
        exit 1
    fi

    # 2. 确定目标路径
    if [[ -d "$OLD_ROOT" ]] && [[ -f "$OLD_ROOT/config.py" || -d "$OLD_ROOT/data" || -d "$OLD_ROOT/chroma_db" ]]; then
        log_info "检测到旧安装: $OLD_ROOT"
    elif [[ "$OLD_ROOT" != "$NEW_ROOT" ]]; then
        log_warn "在 $OLD_ROOT 未检测到旧安装"
        log_info "尝试在当前目录检测..."
    fi

    # 如果旧安装存在且不等于当前目录，询问用户
    if [[ -d "$OLD_ROOT" ]] && [[ "$OLD_ROOT" != "$NEW_ROOT" ]]; then
        echo ""
        log_info "旧安装路径: $OLD_ROOT"
        log_info "新版本路径: $NEW_ROOT"
        echo ""
        echo -n "是否将新版本部署到旧安装路径并升级? (Y/n): "
        read -r deploy
        if [[ "$deploy" =~ ^[Nn] ]]; then
            echo -n "请指定目标路径: "
            read -r custom_path
            TARGET_ROOT="${custom_path:-$NEW_ROOT}"
        else
            TARGET_ROOT="$OLD_ROOT"
        fi
    else
        TARGET_ROOT="$NEW_ROOT"
    fi
    BACKUP_DIR="$TARGET_ROOT/upgrade_backups_${TIMESTAMP}"

    # 3. 检测旧版本
    local scenario
    if [[ "$TARGET_ROOT" == "$NEW_ROOT" ]]; then
        scenario=$(detect_scenario "$NEW_ROOT")
    else
        scenario=$(detect_scenario "$TARGET_ROOT")
    fi

    echo ""
    echo -e "检测结果: ${CYAN}$(describe_scenario "$scenario")${NC}"
    echo ""

    if [[ "$scenario" == "NEW" ]]; then
        log_warn "未检测到旧版本 EverythingSearch 安装"
        log_warn "如果你要升级已有安装，请带上旧项目路径再执行: ./scripts/upgrade.sh <旧项目路径>"
        echo -n "是否仍要执行全新安装配置? (y/N): "
        read -r do_install
        if [[ "$do_install" =~ ^[Yy] ]]; then
            log_info "请运行安装脚本: ./scripts/install.sh"
        fi
        exit 0
    fi

    # 4. 确认升级
    echo "升级操作可能包括: 备份数据、清理不兼容索引、合并配置、重建索引。"
    echo -n "是否继续? (Y/n): "
    read -r confirm
    if [[ "$confirm" =~ ^[Nn] ]]; then
        log_info "已取消升级"
        exit 0
    fi

    # 5. 执行升级
    echo ""
    echo -e "${CYAN}══════════ 开始升级 ══════════${NC}"

    # 同步代码（仅当新旧路径不同时）
    sync_code "$TARGET_ROOT"

    # 备份
    create_backup "$TARGET_ROOT"

    # 合并配置（从真实的旧配置位置提取值）
    local config_source="$TARGET_ROOT"
    if [[ -f "$BACKUP_DIR/config.py" ]]; then
        config_source="$BACKUP_DIR"
    fi
    merge_config "$config_source" "$TARGET_ROOT"

    # 数据清理
    cleanup_for_scenario "$scenario" "$TARGET_ROOT"

    # 完整性检查
    verify_upgrade "$TARGET_ROOT"

    # 更新依赖
    update_dependencies "$TARGET_ROOT"

    # 更新 launchd
    update_launchd "$TARGET_ROOT"

    # 重建索引
    rebuild_index "$scenario" "$TARGET_ROOT"

    # 完成
    print_guide
}

main
