# プレビューのワークフロー

共通の決まり（actionの固定、`pull_request`だけ、`permissions`、Environment、`concurrency`）とコメントの更新の方法は、[`create-e2e-ci`の`workflows.md`](../../create-e2e-ci/references/workflows.md)に従う。プレビューのコメントの目印は`<!-- preview-env:url -->`にする。

## プレビュー（Cloudflareのとき）

- PRのopen、synchronize、reopenでプレビューを作るか更新し、URLをPRのコメントにする
- PRのcloseで、そのプレビューを消す
- プレビューの作成が失敗したら、ジョブを失敗にし、コメントに失敗したことを書く。CIのジョブはプレビューに依存させない
- フォーク元からのPRでは、secretsを使うプレビューのジョブを動かさない（`if: github.event.pull_request.head.repo.full_name == github.repository`）
