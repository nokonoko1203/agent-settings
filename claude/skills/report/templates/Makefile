REPORT_CHECK ?= $(HOME)/.claude/bin/report-check
ROOT ?= .
OUT ?= build/report.md
# ラッパー等のコマンドを --judge '...' --judge '...' の形で指定する。
JUDGES ?=

.PHONY: check test-coverage test-logic build
check: test-coverage

test-coverage:
	"$(REPORT_CHECK)" coverage --root "$(ROOT)"

test-logic:
	"$(REPORT_CHECK)" logic --root "$(ROOT)" $(JUDGES) --strict

build: check test-logic
	"$(REPORT_CHECK)" build --root "$(ROOT)" --out "$(OUT)"
