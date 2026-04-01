.PHONY: help index index-full app app-stop app-restart app-status

PYTHON := ./venv/bin/python

help:
	@echo "EverythingSearch — 可用 make 命令:"
	@echo ""
	@echo "  make help         显示本说明"
	@echo "  make index        增量索引（everythingsearch.incremental）"
	@echo "  make index-full   全量重建索引（--full）"
	@echo "  make mweb-export  仅单独执行 MWeb 笔记强制全量扫描导出"
	@echo "  make app          前台启动 Web 应用（开发模式）"
	@echo "  make app-stop     停止 launchd 托管的应用服务"
	@echo "  make app-restart  重启 launchd 托管的应用服务"
	@echo "  make app-status   查看 launchd 应用服务状态"
	@echo ""
	@echo "依赖: 使用仓库内 venv，即 $(PYTHON)"

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
