.PHONY: index index-full app app-stop app-restart app-status

PYTHON := ./venv/bin/python

# Run incremental indexing
index:
	$(PYTHON) -m everythingsearch.incremental

# Run full reindex
index-full:
	$(PYTHON) -m everythingsearch.incremental --full

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
