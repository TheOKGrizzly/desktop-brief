.PHONY: install uninstall dev test logs status restart doctor clean

install:
	@./install.sh

uninstall:
	@./uninstall.sh

dev:
	@./.venv/bin/python -m desktop_brief

test:
	@./.venv/bin/pytest -q

logs:
	@journalctl --user -u desktop-brief -f

status:
	@systemctl --user status desktop-brief

restart:
	@systemctl --user restart desktop-brief

doctor:
	@./.venv/bin/dbrief-doctor

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} +
	@rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .ruff_cache
