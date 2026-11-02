REPORT_CHECK ?= $(HOME)/.claude/bin/report-check
ROOT ?= .
OUT ?= build/report.md
REPORT_SKILL ?= $(HOME)/.claude/skills/report
# ラッパー等のコマンドを --judge '...' --judge '...' の形で指定する。
JUDGES ?=
# 明示時は実行ファイルとここに列挙した入力だけをハッシュする。
# Python等でラッパーを起動する場合は、そのスクリプトも追加する。
JUDGE_INPUTS ?= --judge-input "$(REPORT_SKILL)/prompts/judge.md"
JUDGE_TIMEOUT ?= 600

.PHONY: check test-coverage test-logic build
check: test-coverage

test-coverage:
	"$(REPORT_CHECK)" coverage --root "$(ROOT)"

test-logic:
	"$(REPORT_CHECK)" logic --root "$(ROOT)" $(JUDGES) $(JUDGE_INPUTS) --judge-timeout "$(JUDGE_TIMEOUT)" --strict

build: check test-logic
	"$(REPORT_CHECK)" build --root "$(ROOT)" --out "$(OUT)"
