# GitHub Actionsのワークフロー

## 共通の決まり

- actionは、使う時点の最新のリリースを確かめ、フルのコミットハッシュで固定する。行末に版をコメントで残す。ハッシュは`git ls-remote https://github.com/<owner>/<repo> 'refs/tags/<tag>'`で引き、annotated tagなら`^{}`の付いた行を使う
- 新しく作るワークフローのトリガーは`pull_request`にする。既存のワークフローに足すときは、既存のトリガー（`push`、`merge_group`など）を残し、足すジョブやステップの実行条件を別に書く。どちらでも`pull_request_target`は使わない。フォーク元からのPRではsecretsを使うジョブを動かさない
- `permissions`はジョブごとに必要なものだけにする（例: `contents: read`、PRにコメントするジョブだけ`pull-requests: write`）
- secretsを使うジョブには、用途ごとのEnvironment（プレビューなら`preview`）を付け、値はEnvironmentのsecretsから読む。e2eのCIはsecretsを使わない
- 依存はロックファイルどおりに入れる（`bun install --frozen-lockfile`、`uv sync --locked`など）
- 依存の脆弱性の監査を入れる（CLAUDE.mdの規則）。既存のCIに監査があれば残し、なければ使っているパッケージマネージャーの監査を足す（例: `bun audit`。Pythonは、ロックファイルから書き出した依存の一覧を`uvx pip-audit -r <一覧>`に渡す。引数なしの`uvx pip-audit`はツールの隔離環境を検査するだけで、プロジェクトの依存を見ない）。使う時点で、そのコマンドが今の版にあるかを確かめる
- 同じPRの古い実行は`concurrency`（`group: <workflow>-${{ github.event.pull_request.number }}`、`cancel-in-progress: true`）で止める

## CI（監査、型検査、テスト、e2e）

1つのワークフローで、依存の監査、リポジトリの型検査とテストを動かし、続けてe2eを動かす。

- e2eはCIの中でモックとアプリを起動して動かす。Playwrightの`webServer`で、モックとアプリの起動と準備完了の判定を書く。本番の資格情報は渡さず、モックの資格情報（ダミーの値）はワークフローに直接書いてよい
- ブラウザは`bunx playwright install --with-deps chromium`で入れる
- 失敗したら、スクリーンショットとトレースをartifactに上げる。成功しても、主要な画面のスクリーンショットはartifactに上げる
- e2eの前に、抽出器の`check`と、`verify-map`の軽い検査（`--ledger`・`--tests`）を動かす
- e2eのあとに、`python3 .claude/bin/verify-map check --skill <検証スキル> --results <PlaywrightのJSON>`（対応表があれば`--ledger`・`--tests`も）で、ケースIDと結果を照合する。検査の出力は、未実装と例外の一覧ごとPRのコメントに載せる。e2eが失敗しても動かす（`if: ${{ !cancelled() }}`）。Pythonは標準ライブラリだけなので、uvやsetup-pythonは要らない
- 結果は、通った・落ちた・不安定・スキップの数を分けて数え、結果のファイルがなければ「結果なし」と書く。集計とartifactの保存は、e2eが失敗しても動かし（`if: ${{ !cancelled() }}`）、集計の成功でe2eの失敗を上書きしない
- 結果とartifactへのリンクを、PRのコメントにする（下の「コメントの更新」）。フォーク元からのPRでは`GITHUB_TOKEN`に書き込み権限がなくコメントできないので、コメントのステップは`if: github.event.pull_request.head.repo.full_name == github.repository`で絞り、結果はジョブのサマリー（`$GITHUB_STEP_SUMMARY`）にも書く

## コメントの更新

ジョブごとにコメントを1つだけ持ち、pushのたびに増やさない。`gh pr comment --edit-last`は同じ利用者（github-actions）の最後のコメントを書き換えるので、e2eとプレビュー（`/create-preview-env`）のように2つのコメントを持つと互いに上書きする。本文の先頭に目印（`<!-- preview-env:e2e -->`など）を入れ、目印で探して更新する。

```sh
marker='<!-- preview-env:e2e -->'
id=$(gh api "repos/$GITHUB_REPOSITORY/issues/$PR/comments" --paginate \
  --jq ".[] | select(.user.login == \"github-actions[bot]\" and (.body | startswith(\"$marker\"))) | .id" | head -n1)
if [ -n "$id" ]; then
  gh api -X PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$id" -F body=@comment.md
else
  gh pr comment "$PR" --body-file comment.md
fi
```

`comment.md`の先頭行に目印を書く。`GH_TOKEN`には`${{ github.token }}`を渡す。
