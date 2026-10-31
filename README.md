# Team Agent Settings

Claude Codeで使うチーム共有用の設定、ルール、hook、スキルをまとめたリポジトリです。

Codexは、Claude Codeから`codex`スキルで作業を頼む先として使います。`codex/`には、頼まれたCodexに必要な最小限だけを入れています。中身は、頼まれた側向けの短い規則（`AGENTS.md`）、危険なコマンドを止めるhook、最小限の`config.toml`です。スキルはClaude Code側だけにあります。

## 開発フロー

1. 作業の前に重さ（E/0/1/2/R）を決めて`harness-log triage`で記録する。マイグレーション・認可・公開API・データ削除・課金・本番反映はレベル2以上。
2. 調査は`imozuru`・`research`、既存コードの理解は`how`・`why`。
3. 動かさないと分からない実装は`spike-rebuild`で、試作して捨ててから作り直す。
4. 設計は`spec`で、受け入れ条件に`[test]`・`[check]`・`[human]`の印を付ける。レベル1・2は`playbook`の手順書に沿う。
5. 実装は、Claude Codeから`codex`スキルでCodex（Sol）に頼める（「solで実装して」のように頼んだときだけ使われる）。運用してみた実感として、Solはトークン消費が軽く、丁寧な指示によく従う。そこで、手間のかかる指示書（ゴール・完了条件・範囲・背景・出力・止まる条件）はClaude Code（Opus）に書かせる。Solの報告は証拠ではないので、差分とテスト結果はClaude Codeが自分で確かめる。
6. 実装中はhookが危険な操作を止め、終わる前に`make check`と証拠（`.tmp/evidence/<task>/evidence.md`）を確かめる。
7. コード変更後は`code-reviewer`スキルでレビューし、PRを作る。Claude Codeでは、Codex（Sol）にも別にレビューさせ、指摘をコードで確かめて統合する。マージは人が行う。
8. 指摘は`harness-log correction`で記録し、同じ間違いが続いたら`correct`で再発を防ぐ。記録は`harness-report`で集計する。

詳細は[claude/CLAUDE.md](./claude/CLAUDE.md)を参照してください。

## 構成

```text
.
├── README.md
├── MANIFEST.txt
├── claude/                 # ~/.claude/ に展開する
│   ├── CLAUDE.md
│   ├── settings.json       # hook・権限・環境変数
│   ├── bin/                # harness-log, harness-report, harness-install, verify-map, e2e-inventory-sveltekit.ts
│   ├── hooks/
│   ├── references/         # evidence.mdの形式、機能一覧の確認手段の書き方など
│   ├── rules/
│   └── skills/
└── codex/                  # ~/.codex/ に展開する
    ├── AGENTS.md
    ├── config.toml
    ├── hooks.json
    ├── hooks/
    └── rules/
```

詳細なファイル一覧は[MANIFEST.txt](./MANIFEST.txt)を参照してください。

## 必要なツール

| ツール | 用途 |
|---|---|
| `uv` | `harness-report`・`harness-install`の実行 |
| `python3` | Python製hookと`verify-map`の実行 |
| `bun` | `e2e-inventory-sveltekit.ts`（SvelteKitのe2eの確認対象の抽出）の実行。対象のプロジェクトの`svelte`と`typescript`を使う |
| `jq` | hookでのJSON処理 |
| `make` | `stop-check.sh`が`make check`を実行する |
| `shasum` | `stop-check.sh`・`evidence-check.sh`の状態管理（Linuxでは`perl`の`shasum`が必要な場合がある） |
| `git`、`gh` | ブランチ保護のhook、PR作成 |
| `codex` | `codex`スキル（Claude CodeからCodexに作業を頼む） |
| `op`（1Password CLI） | シークレットの注入（`rules/secrets-1password.md`） |
| `ctx7` | Context7でライブラリの最新仕様を確かめる。npmパッケージ`ctx7`で、`bunx ctx7 library <name> <query>`のように実行できる。CLAUDE.mdは`ctx7`コマンドで呼ぶので、PATHの通る場所に`bunx ctx7 "$@"`を実行するラッパーを置くか、各自インストールする |

## 使い方

既存の`~/.claude`や`~/.codex`に上書きする前に、バックアップを取ってください。

```sh
cp -a ~/.claude ~/.claude.backup.$(date +%Y%m%d%H%M%S)
cp -a ~/.codex ~/.codex.backup.$(date +%Y%m%d%H%M%S)
```

設定を反映します。`settings.json`と`config.toml`は個人の設定を消さないよう、ここでは除外します。

```sh
rsync -a --exclude settings.json claude/ ~/.claude/
rsync -a --exclude config.toml codex/ ~/.codex/
chmod +x ~/.claude/bin/* ~/.claude/hooks/*
```

`claude/settings.json`は、hook・権限など共通の部分だけを入れています。`codex/config.toml`は、hookを有効にする設定、プロジェクトのCLAUDE.mdを読む設定、メモリーを切る設定、シェルに渡す環境変数を基本のものに絞る設定だけです。Codexのモデル、effort、サンドボックスは、`codex`スキルが毎回指定します。

- 初めて使う場合（`~/.claude/settings.json`や`~/.codex/config.toml`がない場合）は、そのままコピーします。
- 既存の設定がある場合は、上書きせずに`hooks`・`permissions`・`env`などの差分を取り込みます。`settings.json`は次のように`jq`でマージできます（配列は共有版で置き換わるので、マージ後に中身を確かめてください）。

```sh
jq -s '.[0] * .[1]' ~/.claude/settings.json claude/settings.json > /tmp/settings.json \
  && mv /tmp/settings.json ~/.claude/settings.json
```

通知、テーマ、プラグイン、MCPサーバー、信頼するプロジェクトなどの個人の設定は、各自の設定に残してください。

以前の共有版から更新する場合、`rsync`は古いファイルを消しません。今回の版で外したスキル（`tdd`、`implement`、`playwright-cli`、`git-worktree`など）と`~/.codex/CLAUDE.md`は、不要なら手で削除してください。Codexのスキル（`~/.codex/skills/`の下）も、今の版では入れていません。不要なら手で削除してください。

`codex/AGENTS.md`は、以前の版と違って`claude/CLAUDE.md`の写しではありません。`~/.codex/AGENTS.md`を`~/.claude/CLAUDE.md`へのシンボリックリンクにしている場合、`rsync`で上書きされます。

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

スキルは`claude/skills/`にあります。Codexには入れていません。

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
| 保守運用 | `create-e2e-ci` | 外部との境界をモックに向けたe2eテストと、監査・型検査・テスト・e2eを動かすCIを作る |
| 保守運用 | `write-e2e-case` | AIが画面を操作して確かめた手順から、e2eのケースを書き起こす。落ちたケースは、意図した画面の変更による操作の壊れなら直し、製品の退行や期待する結果の失敗なら報告する |
| 保守運用 | `create-preview-env` | PRごとのプレビュー環境（Cloudflare WorkersかAmplify）と、社内だけが開けるアクセス制限を作る |
| 保守運用 | `correct` | 繰り返す間違いを、効く一番上の層（設計・型・lint・テスト・文書）で防ぐ |
| 文書 | `sanitize-artifacts` | 生成文書から会話・指示の混入を取り除く |
| 文書 | `yomiyasu` | AIが生成した日本語を推敲する |

## プロジェクトのリポジトリに入れる

クラウドセッション（claude.ai/code）は`~/.claude/`を読みません。クラウドや他のメンバーの手元でも同じハーネスを使うには、プロジェクトのリポジトリの`.claude/`に写します。

```sh
<このリポジトリのクローン>/claude/bin/harness-install <リポジトリのパス>
```

プロジェクトのリポジトリのルートで実行するときは、パスに`.`を渡します。サブディレクトリで実行しても、`.claude/`はgitのルートにできます。入ったファイルを確かめてからコミットします。

```sh
cd <プロジェクトのリポジトリ>
<このリポジトリのクローン>/claude/bin/harness-install .
git add .claude
git commit -m "chore: エージェントのハーネスを入れる"
```

コピー元は、このリポジトリのクローンでgitが追跡しているファイルだけです。`~/.claude/`から実行すると、個人のスキルなどが混ざらないよう、何もせずに終わります。

- 規則（`CLAUDE.md`）は`.claude/rules/harness.md`に、スキル、hook、`bin/`、`references/`はそれぞれ`.claude/`の下に入ります
- 入るhookは、危険なコマンド、mainへのコミット、`.env`の編集を止めるもの、パッケージマネージャーの確認、`stop-check.sh`、`evidence-check.sh`です。返信のリンク・言語の確認と`xlsx-guard.py`は個人の環境向けなので入りません
- `.claude/settings.json`の既存のキーとhookは残ります
- もう一度実行すると、設定集の更新に合わせて同期します。設定集から消えたファイルは消えます
- `.claude/harness-version`のあるリポジトリでは、グローバルの同じhookは`run-global.sh`が止めるので、二重には動きません
- コミットはしません。上の例のように、自分でコミットしてください
- 以前の版から更新した場合、手元の`~/.claude/settings.json`は「使い方」の手順では上書きされません。`claude/settings.json`と比べ、上の7つのhookのコマンドを`~/.claude/hooks/run-global.sh <hookのファイル名>`に書き換えてください。書き換えないと、ハーネスを入れたリポジトリでhookが2回動きます

### 手元の`~/.claude/`とリポジトリの`.claude/`の両方があるとき

Claude Codeは両方を読みます。リポジトリの設定が手元の設定を置き換えるわけではありません。種類ごとの動きは次のとおりです。

| 種類 | 両方にあるときの動き | この設定集での扱い |
|---|---|---|
| CLAUDE.md・rules | 両方が文脈に入ります。プロジェクトのものが後に読まれますが、食い違ったときの優先順位は決まっていません。どちらに従うかは、Claudeの解釈によります | `CLAUDE.md`の冒頭に、`.claude/rules/harness.md`があれば、食い違う点はそちらに従うと書いています |
| スキル | 同じ名前なら、個人（`~/.claude/skills/`）のものが動きます。リポジトリのものは動きません | 手元では個人の版が動きます。リポジトリのスキルを直したら、この設定集にも同じ変更を入れてください |
| hook | 置き換わらず、両方が動きます | 同じhookが2回動かないよう、グローバルの側を`run-global.sh`が止めます |

クラウドセッションと、この設定集を手元に入れていないメンバーの環境では、リポジトリの`.claude/`だけが効きます。

出典: Claude Codeの公式ドキュメント（[CLAUDE.md](https://code.claude.com/docs/en/memory)、[スキル](https://code.claude.com/docs/en/skills)、[hook](https://code.claude.com/docs/en/hooks)）

## 更新

共有ファイルを更新したら、マニフェストを再生成します。

```sh
find . -type f \
  -not -path './.git/*' \
  -not -path './.tmp/*' \
  -not -path './.claude/*' \
  -not -name '.DS_Store' \
  | sort > MANIFEST.txt
```
