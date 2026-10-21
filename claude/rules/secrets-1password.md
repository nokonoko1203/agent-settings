---
paths:
  - ".env*"
  - ".env.tpl"
  - "Makefile"
  - "package.json"
  - "*.config.*"
  - ".github/workflows/**/*.yml"
  - ".github/workflows/**/*.yaml"
---

# シークレット管理（1Password CLI）

- 平文シークレットを含む`.env`ファイルは作成・編集しない。コード内への秘密情報のハードコードも禁止する。
- 複数のシークレットをコマンド実行時に注入する場合は、1Password CLI（`op`）を使う: `op run --env-file .env.tpl -- <command>`
- `.env.tpl`にはシークレットリファレンス（`op://vault/item/field`）のみ記載し、リポジトリにコミットする。
- 開発用・CI用の主要コマンドは、Makefileやpackage.json scriptsで`op run`をラップする。
- 単一の値が必要な場合のみ`op read "op://vault/item/field"`を使う。
- `op read`は標準出力に値を出すため、ログ出力やシェル履歴に流さないよう注意する。常用は`op run`を優先する。
