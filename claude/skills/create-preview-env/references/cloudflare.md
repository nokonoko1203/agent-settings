# Cloudflare Workersのプレビュー

本番の置き場所がAWSに決まっていないときに使う。Cloudflareの操作は`cf`コマンドで行い、wranglerは使わない。

`cf`は2026-09にopen betaになった新しいCLIで、コマンドと設定の形が変わりうる。使う前に、Context7（`ctx7 docs /cloudflare/cf <query>`）と`bunx cf@<版> <コマンド> --help`で、そのとき固定した版の仕様を確かめる。この文書のコマンド名は2026-10-29に文書で確かめたもので、実地ではまだ使っていない（このスキルで初めて使うリポジトリで確かめ、ここを直す）。

## 確かめてあること（文書）

- `cf`はNode.js 22.18以上が要る（解説記事による。公式で確かめる）
- 認証は`CLOUDFLARE_API_TOKEN`の環境変数が最優先で、CIではこれを使う。デプロイには`CLOUDFLARE_ACCOUNT_ID`も要る。`cf`はwranglerの保存した資格情報を読まない
- 設定は`cloudflare.config.ts`に書く。wranglerの設定があれば`cf migrate`で変換できる
- `cf previews deploy [名前]`は、プレビュー用にビルドしてWorkerを上げる。ビルドの出力は`.cloudflare/output/v0/`
- プレビューのsecretsは、全プレビュー共通の値（Base configuration）と、プレビューごとの値を分けて持てる（Workers Previewsの文書。`cf`での対応するコマンドは`cf previews --help`で確かめる）
- Accessは、`preview_worker`をdestinationにしたself-hostedのアプリで、プレビューだけを守れる（`cf zero-trust access applications create`。ポリシーは`cf zero-trust access policies create`）

## 手順

1. **版を固定する**: npmの`cf`の版の一覧から、公開から数日たった版を選び、ワークフローとREADMEで`bunx cf@<版>`の形で使う。`package.json`の依存には入れない
2. **adapter**: SvelteKitなら`@sveltejs/adapter-cloudflare`に変える。ほかのフレームワークは、そのフレームワークのCloudflare向けの公式の手順に従う。adapterを変えると手元の`build`の出力が変わるので、手順3の計画で示す
3. **設定**: `cloudflare.config.ts`にWorkerの名前と、アカウントIDの参照を書く。資格情報は書かない
4. **モック**: プレビューのビルドだけ、`/create-e2e-ci`が作ったモックを有効にし、外部との境界をそこに向ける。プレビューの環境変数で切り替えるのを第一案にする。モックが別プロセスのサーバーなら、同じWorkerに同梱するか、別のWorkerとして上げるかを、手順3の計画で決める
5. **Access**: Accessのアプリ（`preview_worker`）には既存のWorkerのIDが要り、プレビューのURLは既定で公開される。そのため、初回はプレビューのURLと`workers.dev`を無効にした設定でWorkerを作り（`cf deploy`）、WorkerのIDを取ってからAccessを作り、その後でプレビューのURLを有効にする。無効にする設定の名前は、そのとき固定した`cf`の版の文書で確かめる。既存のWorkerを使う場合は、そのWorkerを特定してIDを取る。ユーザーに、許可する範囲（例: `@mierune.co.jp`のメール）を確かめる。作るコマンドを`--dry-run`で示し、承認を得てから実行する。CIからプレビューを開く必要はない（e2eはCIの中で動かすため）ので、サービストークンは作らない
6. **ワークフロー**: [`workflows.md`](workflows.md)の「プレビュー」を、`cf previews deploy pr-<PR番号>`で作る。出力からURLを取り、PRのコメントを更新する。PRを閉じたら、そのプレビューを消す（消すコマンドは`cf previews --help`で確かめる。なければ、残ることをREADMEに書く）

## 人がやること

- CloudflareのアカウントIDと、Workersを編集できるAPIトークンを用意し、GitHubのEnvironment（`preview`）のsecretsに`CLOUDFLARE_ACCOUNT_ID`と`CLOUDFLARE_API_TOKEN`として入れる
- Accessで許可する範囲を決める
