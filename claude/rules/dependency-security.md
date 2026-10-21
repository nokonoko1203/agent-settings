---
paths:
  - "package.json"
  - "bun.lock"
  - "bun.lockb"
  - "pnpm-lock.yaml"
  - "package-lock.json"
  - "yarn.lock"
  - "pyproject.toml"
  - "uv.lock"
  - ".github/workflows/**/*.yml"
  - ".github/workflows/**/*.yaml"
---

# 依存パッケージの安全ルール

- Node.jsはbun、Pythonはuvを使う。既に使用中の場合を除きnpm/yarnなどは避ける。
- グローバルインストールは提案しない。単発実行には`bunx`/`npx`/`uvx`を使う。
- 公開直後のバージョンをインストールしない。新規プロジェクトでは最小リリース期間を設定する。
- postinstall/preinstallスクリプトはデフォルトでブロックする。
- ロックファイルを常にコミットし、CIでは`--frozen-lockfile`等で厳守する。
- CIに依存パッケージの脆弱性監査（audit）を含める。
- GitHub Actionsはタグではなくコミットハッシュで固定する。
- 不慣れなパッケージは、週間DL数、メンテナー数、最終更新日、リポジトリの存在を確認してから追加する。
