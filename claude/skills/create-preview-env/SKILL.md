---
name: create-preview-env
description: "プロジェクトのリポジトリに、PRごとのプレビュー環境（Cloudflare WorkersかAWS Amplify）と、社内の人だけが開けるアクセス制限を作る。外部との境界は`/create-e2e-ci`が作ったモックに向ける。試験用のPRで1回動かしてから渡す。'/create-preview-env'、'プレビュー環境を作って'、'PRごとにプレビューのURLを付けたい'で使う。"
disable-model-invocation: true
---

# プレビュー環境の生成

PRを開くと、そのPRのアプリを社内の人だけが開けるURLがPRに付く状態を、プロジェクトのリポジトリに作る。外へ作るもの（Cloudflare、AWS）とGitの操作は、CLAUDE.mdの規則どおり、ユーザーの承認を得てから行う。作業の重さはレベル2（CI/CDのデプロイ設定と、外から見える環境に当たる）で、手順3の計画を仕様書として扱う。

e2eテストとCIは`/create-e2e-ci`が作る。このスキルは作らない。

## 1. リポジトリに聞く

次をコードベースから答え、観測できないことだけをユーザーに聞く。

- **アプリ**: フレームワークと版、adapter、ビルドと起動のコマンド、ロックファイル（パッケージマネージャー）
- **環境変数**: 名前と用途（`src/env.ts`、`.env.example`、READMEなど）。値は読まない。`.env`を開かない
- **モック**: `/create-e2e-ci`が作ったモックと、その有効・無効の切り替え方。なければ、先に`/create-e2e-ci`を実行するよう伝えて止まる。プレビューは本物の資格情報を使わず、外部との境界をこのモックに向ける
- **本番の置き場所**: README、IaC（CDK、Terraform）、`amplify.yml`、`cloudflare.config.ts`、`wrangler.*`、既存のワークフロー。読み取れなければユーザーに聞く
- **リポジトリの公開範囲**: 公開か非公開か（`gh repo view --json visibility`）。AmplifyのSSRのPRプレビューは、公開リポジトリでは作れない
- **既存のワークフロー**: `.github/workflows/`。あれば、そこに足す

## 2. 置き場所を決める

| 本番の置き場所 | プレビュー | アクセス制限 | 手順 |
|---|---|---|---|
| AWSに決まっている | AWS Amplify HostingのPRプレビュー | Basic認証（資格情報は1Password） | [`references/amplify.md`](references/amplify.md) |
| それ以外（未定を含む） | Cloudflare Workersのプレビュー（`cf previews deploy`） | Cloudflare Access（`preview_worker`を守るアプリ） | [`references/cloudflare.md`](references/cloudflare.md) |

本番がNodeで動く予定なのにCloudflareを選ぶとadapterが2つになる。その場合は理由を示してユーザーに選んでもらう。

## 3. 計画を示して承認を得る

`.tmp/plan/YYYYMMDD_preview-env_spec.md`に次を書き、ユーザーの承認を待つ（`spec`のレベル2の形式）。

- 置き場所と、選んだ理由
- 足す依存と版。新しいパッケージは週間DL数、メンテナー、最終更新日を確かめ、公開から数日たった版に固定する
- adapterを変えるかどうかと、手元の開発コマンドへの影響
- プレビューのビルドだけモックを有効にする方法。本番のビルドに含まれないことの確かめ方
- アクセス制限と許可する範囲
- 作るファイルとワークフロー
- 人がやること（アカウントの準備、secretsの登録、外部での作成）

## 4. 作る

置き場所ごとの手順は`references/`に従う。共通の決まりは次のとおり。

- **資格情報**: 本物の資格情報をプレビューに入れない。CloudflareのAPIトークンなどCIが使う値は、GitHubのEnvironment（`preview`）のsecretsに置く。人が使う値（Basic認証など）は1Passwordに置き、`op read`で読む。値をファイル、ログ、PRのコメントに書かない
- **ワークフロー**: [`references/workflows.md`](references/workflows.md)に従う
- **README**: プレビューの節を足す（URLの見つけ方、アクセスの仕方）

## 5. 渡す前に1回動かす

ユーザーの承認を得て作業用のブランチをpushし、試験用のPRを開く。次を確かめ、対象リポジトリの`.tmp/evidence/<task>/evidence.md`に残す（形式は`~/.claude/references/evidence.md`）。

- PRから、そのコミットのプレビューを開ける
- 資格情報なしでは開けず、資格情報ありなら開ける（curlで、Accessのログインへのリダイレクトか401を確かめ、資格情報を付けて200を確かめる。資格情報は`op read`で読み、コマンドの履歴やログに残さない）
- プレビューで主要な画面がモックのデータで動く（`[human]`。URLと見る手順を置く）
- 本番のビルドにモックが含まれない
- PRを閉じたときにプレビューが消える（置き場所が対応している場合）
- 手元の開発コマンドが今までどおり動く

失敗したら直してから渡す。直せなければ、原因と止まった箇所を報告する。

## 6. 人がやることを伝える

手順3の一覧のうち残ったものを伝える。

生成したファイルのコミットは、ユーザーの依頼か承認を経て、CLAUDE.mdのGitの規則に従って行う。
