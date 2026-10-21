---
name: harness-init
description: "リポジトリにエージェント開発用の検証基盤を整える。`make check`、GitHub ActionsのCI、短いAGENTS.mdを、言語とツールを検出して作る。'harness-init'、'リポジトリを初期化して'、'検証コマンドを用意して'、新規リポジトリ作成直後や既存リポジトリへの導入時に使う。"
---

# リポジトリの検証基盤

エージェントが自分で合否を確かめられる状態を作る。グローバルの`stop-check.sh`は、リポジトリに`make check`（または実行可能な`.claude/check.sh`）があれば、未コミットの変更がある状態での終了時に必ずそれを実行し、失敗したら終了を止める。このスキルはその`check`と、エージェントの外で同じ判定を行うCIを用意する。

既存ファイルは上書きしない。既存の内容と衝突する場合は差分を示して確認する。commitはしない。

## 1. 検出

次を読んで、言語、パッケージマネージャ、既存のlint・型・テスト・ビルドのコマンドを特定する。

- `Cargo.toml`、`package.json`とロックファイル、`pyproject.toml`と`uv.lock`、`go.mod`など
- 既存の`Makefile`、`package.json`のscripts、`justfile`、`.github/workflows/`
- README、CONTRIBUTING、既存のAGENTS.mdやCLAUDE.md

既存の仕組みがあればそれを使う。新しいツールの導入は、ユーザーが求めた場合か承認した場合に限る。

## 2. `make check`

lint、型検査、高速なテストを順に実行し、どれかが失敗したら非ゼロで終わるtargetを作る。数十秒以内に終わる範囲に絞り、遅いE2Eや重いビルドは`make test-all`など別targetにする。

例（既存コマンドに合わせて置き換える）:

| 言語 | check |
|---|---|
| Rust | `cargo fmt --check`、`cargo clippy --all-targets -- -D warnings`、`cargo test` |
| TypeScript（bun） | `bun run lint`、`bun run typecheck`、`bun test` |
| Python（uv） | `uv run ruff check`、`uv run ruff format --check`、`uv run pyright`（または既存の型検査）、`uv run pytest -q` |

`Makefile`がなく、作る理由もない場合は`.claude/check.sh`（実行権限付き、`set -euo pipefail`）にする。作成後に実行し、現状で通ることを確認する。通らない場合は、既存の失敗として一覧を報告し、勝手に直さない。

## 3. CI

`.github/workflows/check.yml`を作る。`~/.claude/rules/dependency-security.md`に従う。

- `make check`をCIでも実行する。ローカルとCIで同じコマンドを使う。
- 依存関係のインストールはロックファイルを厳守する（`bun install --frozen-lockfile`、`uv sync --locked`、`cargo test --locked`など）。
- 依存パッケージの脆弱性監査のjobを含める。
- Actionはタグではなくコミットハッシュで固定し、タグをコメントで残す。ハッシュは`gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`などで現在の値を確認する。
- `permissions: contents: read`を既定にする。

監査コマンドやActionの使い方は公式資料かContext7（`ctx7`）で現在の仕様を確認する。

新規プロジェクトでは、最小リリース期間の設定と、postinstall/preinstallスクリプトの既定ブロックも行う。具体的な設定キーは公式資料かContext7（`ctx7`）で確認する。

## 4. AGENTS.md

100行以内で、エージェントが最初に読む地図を書く。CLAUDE.mdしか使わないリポジトリでは、CLAUDE.mdに書くか、`@AGENTS.md`を読み込む1行を置く。

書くもの:

- リポジトリの目的を1〜2文
- 主要ディレクトリと責務
- 検証方法（`make check`、遅いテストの実行方法）
- コードやドキュメントから読み取れない、そのリポジトリ固有の判断基準

書かないもの: 一般的なコーディング規約、lintやhooksで強制できる規則、ユーザーのグローバル設定と重複する内容。守らせたい規則は、文章ではなくlint規則、テスト、hooksに置く。

## 5. 報告

作成・変更したファイルと、実行した`check`の結果を示す。人間が行う作業として、次を伝える。

- GitHubのブランチ保護（またはrulesets）で、CIの`check`を必須にする
- 既存の失敗があれば、その一覧と対応方針
