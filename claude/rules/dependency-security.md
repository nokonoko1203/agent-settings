---
paths:
  - "package.json"
  - "bun.lock"
  - "bun.lockb"
  - "pnpm-lock.yaml"
  - "pnpm-workspace.yaml"
  - "package-lock.json"
  - "yarn.lock"
  - "pyproject.toml"
  - "uv.lock"
  - ".github/workflows/**/*.yml"
  - ".github/workflows/**/*.yaml"
---

# 依存パッケージの安全ルール

- Node.jsはpnpm（10以上。`package.json`の`packageManager`で版を固定する）、Pythonはuvを使う。既に使用中の場合を除きnpm/yarn/bunは避ける。
- グローバルインストールは提案しない。単発実行には`pnpm dlx`/`npx`/`uvx`を使う。
- 公開直後のバージョンをインストールしない。新規プロジェクトでは最小リリース期間（7日）を設定する。pnpmは`pnpm-workspace.yaml`の`minimumReleaseAge: 10080`、uvは`pyproject.toml`の`[tool.uv]`の`exclude-newer = "7 days"`。
- postinstall/preinstallスクリプトはデフォルトでブロックする。
- ロックファイルを常にコミットし、CIでは`--frozen-lockfile`等で厳守する。
- CIに依存パッケージの脆弱性監査（audit）を含める。
- GitHub Actionsのactionはタグ（`@vX.Y.Z`）で参照し、`gh actions-lock`で生成したworkflow lockfile（`.github/workflows/actions.lock`）で実行するコミットを固定する。lockfileはコミットし、actionを足したり更新したりしたら同じPRで作り直す。ブランチ（`@main`など）では参照しない。lockfileを使えない場合（`gh`がない、GitHub Enterprise Serverなど、lockfileの対象外の参照）は、フルのコミットハッシュで固定し、行末に版をコメントで残す。
- 不慣れなパッケージは、週間DL数、メンテナー数、最終更新日、リポジトリの存在を確認してから追加する。
