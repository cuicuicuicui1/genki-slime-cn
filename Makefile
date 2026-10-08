PYTHON ?= python3
.PHONY: bootstrap test audit
bootstrap:
	$(PYTHON) -X utf8 tools/project.py bootstrap
test:
	$(PYTHON) -X utf8 -m unittest discover -s tests -v
audit:
	$(PYTHON) -X utf8 tools/audit_public_tree.py
