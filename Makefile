.PHONY: help index index-full start stop restart status enable disable
.PHONY: index-enable index-disable index-status index-interval

PYTHON := ./venv/bin/python
BOOTSTRAP_DOMAIN := gui/$(shell id -u)

# 多实例：安装目录唯一哈希 → Label / plist 路径（scripts/.launchd_instance.mk）
-include scripts/.launchd_instance.mk
ifndef LABEL_APP
LABEL_APP := com.jigger.everythingsearch.app
LABEL_INDEX := com.jigger.everythingsearch
APP_PLIST := $(HOME)/Library/LaunchAgents/$(LABEL_APP).plist
INDEX_PLIST := $(HOME)/Library/LaunchAgents/$(LABEL_INDEX).plist
endif

APP_LABEL := $(LABEL_APP)
INDEX_LABEL := $(LABEL_INDEX)

help:
	@echo "EverythingSearch — 可用 make 命令:"
	@echo ""
	@echo "  ──  常用命令  ──"
	@echo "  make help              显示本说明"
	@echo ""
	@echo "  make start             启动应用服务"
	@echo "  make stop              停止应用服务"
	@echo "  make restart           重启应用服务"
	@echo "  make status            查看应用服务状态"
	@echo ""
	@echo "  ── 手动索引管理 ──"
	@echo "  make index             手动执行增量索引"
	@echo "  make index-full        手动执行全量重建索引（参数可控制是否保留缓存）（--full）ARGS=\"--resume --keep-caches\""
	@echo ""
	@echo "  ── 定时任务管理 ──"
	@echo "  make enable            开启服务开机自启"
	@echo "  make disable           关闭服务开机自启"
	@echo ""
	@echo "  make index-enable      开启定时增量索引"
	@echo "  make index-disable     关闭定时增量索引"
	@echo "  make index-status      查看定时索引状态"
	@echo "  make index-interval MIN=30  修改索引间隔（分钟，默认 30）"
	@echo ""
	@echo "依赖: 使用仓库内 venv，即 $(PYTHON)"

# Run incremental indexing
index:
	$(PYTHON) -m everythingsearch.incremental

# Run full reindex (optional: make index-full ARGS="--keep-caches" or ARGS="--resume --keep-caches")
index-full:
	$(PYTHON) -m everythingsearch.incremental --full $(ARGS)

# Stop launchd-managed app service
stop:
	./scripts/run_app.sh stop

# Restart launchd-managed app service
restart:
	./scripts/run_app.sh restart

# Show launchd-managed app service status
status:
	./scripts/run_app.sh status

# Start app service (launchd)
start:
	./scripts/run_app.sh start

# Enable auto-start at login (bootstrap plist)
enable:
	@if [ ! -f "$(APP_PLIST)" ]; then \
		echo "❌ 未找到 plist: $(APP_PLIST)"; \
		echo "   请先运行 ./scripts/install.sh 安装后台服务"; \
		exit 1; \
	fi
	launchctl bootstrap $(BOOTSTRAP_DOMAIN) "$(APP_PLIST)" 2>/dev/null || true
	launchctl enable $(BOOTSTRAP_DOMAIN)/$(APP_LABEL) 2>/dev/null || true
	@echo "✅ 开机自启已开启（登录后自动启动应用服务）"

# Disable auto-start at login (bootout + disable)
disable:
	launchctl bootout $(BOOTSTRAP_DOMAIN)/$(APP_LABEL) 2>/dev/null || true
	@echo "✅ 开机自启已关闭（应用服务不会在登录时自动启动）"

# ── 定时索引管理 ──

# Enable scheduled incremental indexing
index-enable:
	@if [ ! -f "$(INDEX_PLIST)" ]; then \
		echo "❌ 未找到 plist: $(INDEX_PLIST)"; \
		echo "   请先运行 ./scripts/install.sh 安装定时索引服务"; \
		exit 1; \
	fi
	launchctl bootstrap $(BOOTSTRAP_DOMAIN) "$(INDEX_PLIST)" 2>/dev/null || true
	launchctl enable $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) 2>/dev/null || true
	@echo "✅ 定时增量索引已开启"
	@/usr/libexec/PlistBuddy -c "Print :StartInterval" "$(INDEX_PLIST)" 2>/dev/null \
		| awk '{printf "   间隔: %d 分钟\n", $$1/60}'

# Disable scheduled incremental indexing
index-disable:
	launchctl bootout $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) 2>/dev/null || true
	@echo "✅ 定时增量索引已关闭"

# Show index service status
index-status:
	@if launchctl print $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) >/dev/null 2>&1; then \
		echo "✅ 定时增量索引已加载"; \
		launchctl print $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) 2>/dev/null \
			| grep -E 'state|last exit|StartInterval' || true; \
	else \
		echo "❌ 定时增量索引未加载"; \
	fi

# Change index interval (minutes, default 30)
index-interval:
	@if [ ! -f "$(INDEX_PLIST)" ]; then \
		echo "❌ 未找到 plist: $(INDEX_PLIST)"; \
		echo "   请先运行 ./scripts/install.sh 安装定时索引服务"; \
		exit 1; \
	fi
	@MIN=$(MIN); \
	if [ -z "$$MIN" ]; then MIN=30; fi; \
	if ! echo "$$MIN" | grep -qE '^[0-9]+$$'; then \
		echo "❌ 间隔必须为正整数（分钟），例如: make index-interval MIN=60"; \
		exit 1; \
	fi; \
	SEC=$$((MIN * 60)); \
	/usr/libexec/PlistBuddy -c "Set :StartInterval $$SEC" "$(INDEX_PLIST)" && \
	echo "✅ 索引间隔已更新为 $$MIN 分钟"; \
	echo "   正在重载服务以生效..."; \
	launchctl bootout $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) 2>/dev/null || true; \
	sleep 1; \
	launchctl bootstrap $(BOOTSTRAP_DOMAIN) "$(INDEX_PLIST)" 2>/dev/null || true; \
	echo "✅ 已重载，新的索引间隔已生效"
