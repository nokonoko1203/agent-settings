# AWS AmplifyのPRプレビュー

本番の置き場所がAWSに決まっているときに使う。AmplifyのPRプレビューは、Amplifyのアプリに接続したGitHubのリポジトリで、PRごとに環境を作り、PRを閉じると消す。

## 確かめてあること（文書、2026-10-29）

- SvelteKitのSSRには、コミュニティのadapter`amplify-adapter`が要る。AWSは保守していない。1.4.0はSvelteKit 2と3に対応している（peerDependencies）
- PRプレビューは、ブランチの設定`enablePullRequestPreview`で有効にする
- アクセス制限は、Basic認証。ブランチごとの設定と、アプリの全ブランチに効く設定がある（[アクセス制御](https://docs.aws.amazon.com/amplify/latest/userguide/access-control.html)）。プレビューのURL（`*.amplifyapp.com`）はCloudflareを通らないので、Cloudflare Accessはかけられない
- 公開リポジトリでは、IAMのサービスロールが要るアプリ（SSRの`WEB_COMPUTE`を含む）のPRプレビューを作れない（[PRプレビュー](https://docs.aws.amazon.com/amplify/latest/userguide/pr-previews.html)）
- 環境変数はブランチごとに持てる

## まだ確かめていないこと

このスキルで初めて使うリポジトリで確かめ、ここを直す。

- 全ブランチに効くBasic認証が、PRプレビューにもかかるか（手順4で、プレビューを有効にする前に設定し、手順5の確認で確かめる）
- PRプレビューのビルドだけに、別の環境変数（モックの向き先）を渡せるか。渡せなければ、ビルド時に分かるPRの番号などの環境変数で切り替える
- Amplifyが、プレビューのURLをPRに自動で載せるか（載せなければ、ワークフローでコメントする）

## 手順

0. **使えるかを先に確かめる**: リポジトリが公開で、SSRが要る（サーバールートやモックの同梱を含む）なら、AmplifyのPRプレビューは作れない。依存を足す前に止め、非公開にするか、静的な構成にするか、別の置き場所にするかをユーザーに決めてもらう
1. **adapter**: SvelteKitなら`amplify-adapter`に変える。本番もAmplifyならそのまま本番の設定になる。本番がAWSの別のサービス（ECSなど）なら、プレビューのビルドだけadapterを切り替える方法を、手順3の計画で示す
2. **ビルドの設定**: `amplify.yml`をリポジトリに置く。パッケージマネージャーはロックファイルに合わせる（bunなら、ビルドの環境にbunを入れる手順を書く）。依存はロックファイルどおりに入れる（`bun install --frozen-lockfile`など）
3. **モック**: プレビューのビルドだけ、`/create-e2e-ci`が作ったモックを有効にし、外部との境界をそこに向ける。Amplifyでは別プロセスのモックサーバーを動かせないので、モックがアプリに同梱できる形でなければ、`/create-e2e-ci`の側で同梱できる形に直してから進める。本番のビルドに含めないことを確かめる
4. **アプリの作成と接続（人）**: Amplifyのコンソールでアプリを作り、GitHubのリポジトリと接続する。先にアプリの全ブランチに効くBasic認証をかけ、その後で本番のブランチのPRプレビューを有効にする（順番を逆にすると、認証なしのプレビューが一時的に公開される）。SSRでは、認証の設定を変えたら再ビルドが要る。Basic認証の資格情報は1Passwordに置く。技術標準はIaCを求めるが、プレビューだけのためにCDKは足さない。本番をCDKで作るときに、このアプリも取り込む
5. **ワークフロー**: プレビュー自体はAmplifyが作るので、GitHub Actionsのワークフローは足さない。AmplifyがURLをPRに載せない場合だけ、[`workflows.md`](workflows.md)に従ってURLをコメントするワークフローを足す

## 人がやること

- AWSのアカウントで、Amplifyのアプリを作ってGitHubと接続し、PRプレビューとBasic認証を有効にする
- Basic認証の資格情報を決めて1Passwordに置き、社内に共有する
