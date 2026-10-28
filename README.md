# Claude CodeとCodexの個人設定集

軽い設定を勧めていた旧版は、タグ`v1`にあります。エージェントに任せる範囲が広がり、作業の重さの判断・hook・証拠・レビューで品質を担保する仕組みが必要になったため、方針を変えました。

Claude CodeとCodexで使う設定、ルール、hook、スキルをまとめています。`claude/`と`codex/`は同じ開発フローとスキルセットで揃えており、`codex/AGENTS.md`は`claude/CLAUDE.md`と同じ内容です。

## 開発フロー

1. 作業の前に重さ（E/0/1/2/R）を決めて`harness-log triage`で記録する。マイグレーション・認可・公開API・データ削除・課金・本番反映はレベル2以上。
2. 調査は`imozuru`・`research`、既存コードの理解は`how`・`why`。
3. 動かさないと分からない実装は`spike-rebuild`で、試作して捨ててから作り直す。
4. 設計は`spec`で、受け入れ条件に`[test]`・`[check]`・`[human]`の印を付ける。レベル1・2は`playbook`の手順書に沿う。
5. 実装は、Claude Codeから`codex`スキルでCodex（Sol）に頼める（「solで実装して」のように頼んだときだけ使われる）。ゴール・完了条件・範囲・背景・出力・止まる条件をまとめた指示書はClaude Code（Opus）に書かせる。Solの報告だけで完了とせず、差分とテスト結果はClaude Codeが自分で確かめる。
6. 実装中はhookが危険な操作を止め、終わる前に`make check`と証拠（`.tmp/evidence/<task>/evidence.md`）を確かめる。
7. コード変更後は`code-reviewer`スキルでレビューし、PRを作る。Claude Codeでは、Codex（Sol）にも別にレビューさせ、指摘をコードで確かめて統合する。マージは人が行う。
8. 指摘は`harness-log correction`で記録し、同じ間違いが続いたら`correct`で再発を防ぐ。記録は`harness-report`で集計する。

詳細は[claude/CLAUDE.md](./claude/CLAUDE.md)を参照してください。

## 構成

```text
.
├── README.md
├── LICENSE
├── MANIFEST.txt
├── claude/                 # ~/.claude/ に展開する
│   ├── CLAUDE.md
│   ├── settings.json       # hook・権限・環境変数
│   ├── bin/                # harness-log, harness-report
│   ├── hooks/
│   ├── references/         # evidence.mdの形式など
│   ├── rules/
│   └── skills/
└── codex/                  # ~/.codex/ に展開する
    ├── AGENTS.md
    ├── config.toml
    ├── hooks.json
    ├── hooks/
    ├── rules/
    └── skills/
```

詳細なファイル一覧は[MANIFEST.txt](./MANIFEST.txt)を参照してください。

## 必要なツール

| ツール | 用途 |
|---|---|
| `uv` | `harness-report`の実行 |
| `python3` | Python製hookの実行 |
| `jq` | hookでのJSON処理 |
| `make` | `stop-check.sh`が`make check`を実行する |
| `shasum` | `stop-check.sh`・`evidence-check.sh`の状態管理（Linuxでは`perl`の`shasum`が必要な場合がある） |
| `git`、`gh` | ブランチ保護のhook、PR作成 |
| `codex` | `codex`スキル（Claude CodeからCodexに作業を頼む） |
| `op`（1Password CLI） | シークレットの注入（`rules/secrets-1password.md`） |
| `ctx7` | Context7でライブラリの最新仕様を確かめる。npmパッケージ`ctx7`で、`bunx ctx7 library <name> <query>`のように実行できる。CLAUDE.mdは`ctx7`コマンドで呼ぶので、PATHの通る場所に`bunx ctx7 "$@"`を実行するラッパーを置くか、各自インストールする |

## 使い方

`claude/`の中身を`~/.claude/`に、`codex/`の中身を`~/.codex/`に配置します。以下は、このリポジトリのルートで実行する例です。既存の設定があれば、先にバックアップを取ります。

```sh
cp -a ~/.claude ~/.claude.backup.$(date +%Y%m%d%H%M%S)
cp -a ~/.codex ~/.codex.backup.$(date +%Y%m%d%H%M%S)
```

まだ存在しないディレクトリのバックアップは不要です。設定先を作り、設定ファイル以外をコピーします。

```sh
mkdir -p ~/.claude ~/.codex
rsync -a --exclude settings.json claude/ ~/.claude/
rsync -a --exclude config.toml codex/ ~/.codex/
chmod +x ~/.claude/bin/* ~/.claude/hooks/*
```

`claude/settings.json`と`codex/config.toml`には、hook・権限・モデルなどの設定が入っています。

- 初めて使う場合は、それぞれ`~/.claude/settings.json`と`~/.codex/config.toml`へコピーします。
- 既存の設定がある場合は、内容を比較して必要な設定を取り込みます。通知、テーマ、プラグイン、MCPサーバー、信頼するプロジェクトなどの設定は、自分の環境に合わせて残します。
- `codex/config.toml`のモデルが使えない環境では、`model`と`default_subagent_model`を利用できるモデルへ変更します。

`rsync`は古いファイルを削除しません。以前の設定から更新する場合は、不要になったファイルが残っていないか確認してください。

## hook

| イベント | hook | 内容 |
|---|---|---|
| PreToolUse（Bash） | `block-dangerous-commands.sh` | `rm -rf`などの取り返しのつかないコマンドを止める |
| PreToolUse（Bash） | `block-main-commit.py` | mainへの直接コミットを止める |
| PreToolUse（Bash） | `allow-git-off-main.py` | main以外のブランチでのgit操作を自動で許可する |
| PreToolUse（Bash） | `enforce-package-manager.py` | ロックファイルと違うパッケージマネージャーを止める（ロックファイルがなければbun・uv） |
| PreToolUse・PostToolUse（Bash） | `xlsx-guard.py` | コマンドが書き換えた.xlsxを検証する |
| PreToolUse（Edit・Write） | `block-env-edit.sh` | `.env`の作成・編集を止める |
| Stop | `stop-check.sh` | `make check`を実行し、落ちたら直させる（3回まで） |
| Stop | `evidence-check.sh` | 振る舞いが変わる変更なのに証拠が古ければ止める（既定で見るのはSvelte・CSSなど。ほかの言語はリポジトリの`.claude/evidence-paths`で対象を指定する） |
| Stop | `check-reply-links.py` | 返信中のファイルリンクが開けるか確かめる |
| Stop | `check-reply-language.py` | 返信が英語なら日本語で書き直させる |

Codexでは`pre_tool_use_guard.py`が、特権コマンド（`sudo`など）、環境変数の出力（`env`、`printenv`）、`source .env`、`./.env`・`./secrets/`・`~/.ssh/`などのパスを含むコマンドを止めます。コマンドの文字列で判定するだけなので、`cat .env`のような書き方は止まりません。

## スキル

`claude/skills/`と`codex/skills/`には同じスキルセットを入れています。

| 段階 | スキル | 内容 |
|---|---|---|
| 進め方 | `playbook` | 不具合の修正・機能の追加・リファクタリング・性能の改善・調査の手順書 |
| 調査 | `imozuru` | 関連する用語・人・場を芋づる式にたどり、原文を集める |
| 調査 | `research` | 技術選定や仕様比較を根拠付きで`.tmp/research/`にまとめる |
| 調査 | `how` | 既存のコードが今どう動いているかを説明する |
| 調査 | `why` | 既存のコードや設計がなぜ今の形なのかを、記録から調べる |
| 設計 | `spec` | 受け入れ条件と確かめ方を決めた契約・仕様書を作る |
| 設計 | `spike-rebuild` | 試作して測り、仕様を作ってから作り直す |
| 実装 | `codex` | Codex CLIに、モデル・effortを指定して作業を頼む |
| レビュー | `code-reviewer` | PR・差分を、再現条件と根拠のある不具合に絞ってレビューする |
| 保守運用 | `harness-init` | リポジトリに`make check`・CI・AGENTS.mdを整える |
| 保守運用 | `create-verification-skill` | アプリを利用者と同じ操作で確かめる、プロジェクト専用の検証スキルを作る |
| 保守運用 | `maintain-verification-skill` | 検証スキルと機能一覧を、アプリの現状に合わせて点検する |
| 保守運用 | `correct` | 繰り返す間違いを、効く一番上の層（設計・型・lint・テスト・文書）で防ぐ |
| 文書 | `sanitize-artifacts` | 生成文書から会話・指示の混入を取り除く |
| 文書 | `yomiyasu` | AIが生成した日本語を推敲する |

## 更新

設定やスキルを更新したら、マニフェストを再生成します。

```sh
find . -type f \
  -not -path './.git/*' \
  -not -path './.tmp/*' \
  -not -name '.DS_Store' \
  | sort > MANIFEST.txt
```

`claude/skills/`と`codex/skills/`は同じスキルセットになるように更新してください。

## ライセンス

このリポジトリは[MITライセンス](./LICENSE)です。Copyright (c) 2025 nokonoko1203。

一部のスキルは第三者のMITライセンスのコードを含みます。帰属表示とライセンス条件は、各スキル内の`NOTICE.md`（`NOTICE-pstack.md`を含む）や`LICENSE`を参照してください。Unicode由来のデータについては、同梱の`UNICODE-LICENSE.txt`も参照してください。
