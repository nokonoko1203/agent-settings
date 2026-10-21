---
name: codex
description: "Codex CLI（`codex exec`）に、モデル・reasoning effort・速度を指定して作業（調査、レビュー、相談、実装）を頼み、結果を受け取って要約する。「solで〜して」「astra xhighで調べて」「luna low fastで」「Codexで〜」「Codexに聞いて／やらせて」のように、呼び名（sol / astra / luna）やCodexを指定して作業を頼まれたときだけ使う。文中に普通の単語として「sol」「luna」が出てきただけのときは使わない。"
---
# Codex

Claude CodeからCodex CLIを非対話で実行する。依頼文の「呼び名・effort・fast」から引数を決め、毎回すべて明示して実行する。`~/.codex/config.toml`の既定値には頼らない。

## 呼び名

| 呼び名 | `-m`          | 使えるeffort                  |
| ------ | --------------- | ----------------------------- |
| sol    | `gpt-6.1-sol` | low, medium, high, xhigh, max |
| astra  | `gpt-6-astra` | low, medium, high, xhigh, max |
| luna   | `gpt-6-luna`  | low, medium, high, xhigh, max |

`gpt-6-sol`、`gpt-5.6`系、effortの`ultra`は使わない。

## 依頼文の読み方

書き方は`<呼び名> [<effort>] [fast]`。大文字と小文字は区別しない。例: `sol`、`astra xhigh`、`luna low`、`sol high fast`。

| 要素   | 省略したとき                                  | 指定したとき                                                      |
| ------ | --------------------------------------------- | ----------------------------------------------------------------- |
| 呼び名 | sol（「Codexで」だけのときも）                | 表の`-m`の値                                                    |
| effort | `medium`                                    | `-c model_reasoning_effort=<effort>`                            |
| fast   | `-c 'service_tier="default"'`（通常の速さ） | `-c 'service_tier="priority"'`（Fast。速さ2倍、使用量も増える） |

表にない呼び名やeffort（`ultra`など）が指定されたら、実行せずに、使える値を示して止まる。

## 実行

```bash
codex exec -m <slug> -c model_reasoning_effort=<effort> -c 'service_tier="<default|priority>"' \
  -C <作業ディレクトリ> -s <sandbox> \
  -o <作業ディレクトリ>/.tmp/codex/<YYYYMMDD-HHMMSS>.md \
  "$(cat <<'PROMPT'
<プロンプト>
PROMPT
)" </dev/null
```

- `service_tier`の値は、TOMLの文字列になるよう、`-c 'service_tier="default"'`のように単一引用符で囲んで二重引用符ごと渡す。
- プロンプトは、上のように引用符付きのheredoc（`<<'PROMPT'`）で渡す。二重引用符で直接囲むと、プロンプト中のバッククォートや`$`がシェルに展開されてしまう。
- 標準入力は`</dev/null`で閉じる（`codex exec`は、パイプされた標準入力を`<stdin>`ブロックとしてプロンプトに足すため、EOFまで待ってしまう）。
- 作業ディレクトリ: 既定は現在の作業ディレクトリ。実行の前に`git -C <作業ディレクトリ> rev-parse --is-inside-work-tree`で確かめ、Gitリポジトリの外なら`--skip-git-repo-check`を付ける（付けないと`Not inside a trusted directory`で失敗する）。
- sandbox: 調査、レビュー、相談は`read-only`。ファイルの変更を頼まれたときだけ`workspace-write`にする。`--dangerously-*`系のオプションは使わない。
- 出力先: `-o`で最後の返答をファイルに受け取る。先に`mkdir -p <作業ディレクトリ>/.tmp/codex`を実行しておく。
- 時間: 2分を超えそうな依頼は、Bashの`run_in_background`で実行し、完了の通知を待つ。
- プロンプト: 下の「プロンプトの型」で組む。秘密情報、`.env`、`auth.json`の中身は入れない。

## プロンプトの型

次の見出しで組む。見出しは省略しない（該当がなければ「なし」と書く）。

```
## ゴール
<1文。終わったとき何が成り立っているか>

## 完了条件
- <確かめられる形で。調査なら「〜の答えと、根拠のファイル:行」、実装なら「〜のテストが通る」「〜が表示される」>

## 範囲
- 対象: <ファイル、ディレクトリ、URL>
- 変更: <してよい／しない。してよいなら、触ってよいファイル>
- やらないこと: <広げてほしくない方向>

## 背景
<判断に必要な事実だけ。経緯の全文は貼らない>

## 出力
<返答の構成。例: 結論 → 根拠 → 未確認の点>

## 止まる条件
完了条件をすべて満たしたら、そこで止まって報告する。範囲の外の変更が必要なとき、または判断が分かれる点に当たったときは、推測で進めずに、その時点までの結果と論点を報告する。
```

- ゴールと完了条件は、ユーザーの依頼を言い直して作る。依頼にない目的を足さない。
- ゴールは手順ではなく結果で書く。
- 完了条件には確かめ方（実行するコマンド、再現手順）も書く。
- 依頼からゴールか完了条件を決められないときは、Codexを呼ぶ前にユーザーに確認する。
- 長い指示書を`.tmp/plan/`などのファイルにして渡す場合も、同じ見出しにする。

## 結果の扱い

- `-o`のファイルを読んで、要点を報告する。使ったモデル、effort、速度も添える。
- 返答を完了条件と照らし合わせ、満たしていない条件があればそう報告する。
- Codexの返答は報告であって、証拠ではない。ファイルの変更、テストの結果、出典などは、必要に応じて自分で確かめてから事実として扱う。
- `workspace-write`で実行したら、`git status`と`git diff`で変更を確かめてから報告する。
- 実行に失敗したら（例: 400 `model is not supported`）、エラー文をそのまま報告し、勝手に別のモデルに切り替えない。
