.PHONY: help index index-full app app-start app-stop app-restart app-status app-enable app-disable
.PHONY: mweb-export search
.PHONY: index-svc-enable index-svc-disable index-svc-status index-svc-interval

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
	@echo "  make help              显示本说明"
	@echo "  make index             增量索引（everythingsearch.incremental）"
	@echo "  make index-full        全量重建索引（--full）"
	@echo "  make mweb-export       仅单独执行 MWeb 笔记强制全量扫描导出"
	@echo "  make app               前台启动 Web 应用（开发模式）"
	@echo "  make search            执行命令行检索 (例如: make search q='关键字')"
	@echo ""
	@echo "  ── 应用服务管理 ──"
	@echo "  make app-start         启动应用服务"
	@echo "  make app-stop          停止应用服务"
	@echo "  make app-restart       重启应用服务"
	@echo "  make app-status        查看应用服务状态"
	@echo "  make app-enable        开启开机自启（登录后自动启动）"
	@echo "  make app-disable       关闭开机自启"
	@echo ""
	@echo "  ── 定时索引管理 ──"
	@echo "  make index-svc-enable  开启定时增量索引"
	@echo "  make index-svc-disable 关闭定时增量索引"
	@echo "  make index-svc-status  查看定时索引状态"
	@echo "  make index-svc-interval MIN=30  修改索引间隔（分钟，默认 30）"
	@echo ""
	@echo "依赖: 使用仓库内 venv，即 $(PYTHON)"

# Run CLI search
search:
	$(PYTHON) -m everythingsearch search "$(q)" --json

# Run incremental indexing
index:
	$(PYTHON) -m everythingsearch.incremental

# Run full reindex
index-full:
	$(PYTHON) -m everythingsearch.incremental --full

# Only trigger mweb export explicitly
mweb-export:
	$(PYTHON) scripts/mweb_export.py

# Run app in foreground (development mode)
app:
	$(PYTHON) -m everythingsearch.app

# Stop launchd-managed app service
app-stop:
	./scripts/run_app.sh stop

# Restart launchd-managed app service
app-restart:
	./scripts/run_app.sh restart

# Show launchd-managed app service status
app-status:
	./scripts/run_app.sh status

# Start app service (launchd)
app-start:
	./scripts/run_app.sh start

# Enable auto-start at login (bootstrap plist)
app-enable:
	@if [ ! -f "$(APP_PLIST)" ]; then \
		echo "❌ 未找到 plist: $(APP_PLIST)"; \
		echo "   请先运行 ./scripts/install.sh 安装后台服务"; \
		exit 1; \
	fi
	launchctl bootstrap $(BOOTSTRAP_DOMAIN) "$(APP_PLIST)" 2>/dev/null || true
	launchctl enable $(BOOTSTRAP_DOMAIN)/$(APP_LABEL) 2>/dev/null || true
	@echo "✅ 开机自启已开启（登录后自动启动应用服务）"

# Disable auto-start at login (bootout + disable)
app-disable:
	launchctl bootout $(BOOTSTRAP_DOMAIN)/$(APP_LABEL) 2>/dev/null || true
	@echo "✅ 开机自启已关闭（应用服务不会在登录时自动启动）"

# ── 定时索引管理 ──

# Enable scheduled incremental indexing
index-svc-enable:
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
index-svc-disable:
	launchctl bootout $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) 2>/dev/null || true
	@echo "✅ 定时增量索引已关闭"

# Show index service status
index-svc-status:
	@if launchctl print $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) >/dev/null 2>&1; then \
		echo "✅ 定时增量索引已加载"; \
		launchctl print $(BOOTSTRAP_DOMAIN)/$(INDEX_LABEL) 2>/dev/null \
			| grep -E 'state|last exit|StartInterval' || true; \
	else \
		echo "❌ 定时增量索引未加载"; \
	fi

# Change index interval (minutes, default 30)
index-svc-interval:
	@if [ ! -f "$(INDEX_PLIST)" ]; then \
		echo "❌ 未找到 plist: $(INDEX_PLIST)"; \
		echo "   请先运行 ./scripts/install.sh 安装定时索引服务"; \
		exit 1; \
	fi
	@MIN=$(MIN); \
	if [ -z "$$MIN" ]; then MIN=30; fi; \
	if ! echo "$$MIN" | grep -qE '^[0-9]+$$'; then \
		echo "❌ 间隔必须为正整数（分钟），例如: make index-svc-interval MIN=60"; \
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
