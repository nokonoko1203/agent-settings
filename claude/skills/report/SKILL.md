---
name: report
description: "調査業務の報告書を、要求と細部項目の承認、原文の調査、主張台帳、章の執筆、網羅と論理の検査、脚注付きMarkdownの生成まで進める。『調査報告書を書いて』『報告書を台帳とテストで作りたい』『報告書の章を書いて』で使う。短い回答や、既存文書の推敲だけには使わない。"
---

# 調査報告書

仕様から根拠と本文をつなぎ、検査結果と人の判断の記録を残す。各段は台帳を読み、会話の記憶だけで要求や根拠を補わない。案件の台帳・原文・原稿は業務リポジトリに置く。共有するスキルに案件の情報を写さない。

最初に[台帳の形式](references/ledgers.md)を読む。[雛形](templates/)を業務ルートへ写す。実行する道具は`~/.claude/bin/report-check`。プロジェクトの写しがある場合は`.claude/bin/report-check`を使い、Makefileの`REPORT_CHECK`で指定できる。[架空例](examples/harunagi/)には要求3件、細部項目6件、出典3件、主張15件、本文2章がある。すべて架空であり実務の根拠にはしない。

## 進め方

1. **仕様を分解する。** 仕様書、提案で約束したこと、打合せの指示を読み、要求の出典の箇所、種類、担当章、依存先、期待する主張を`requirements.toml`に書く。
2. **細部項目の候補を出す。** 要求から「本文に何があれば満たすか」を細部項目に分ける。主張の種類と最低件数を`expect`にする。仕様の語だけを写して中身のないケースにしない。
3. **本人の承認で止まる。** 細部項目の一覧と要求への対応を渡す。承認されるまでは未承認のままにする。承認後に`approved_by`と`approved_at`を記入する。以後、細部項目やexpectを自分の都合で増減しない。変更が要る場合は差分を本人に渡して再承認を待つ。
4. **調査する。** `imozuru`を使う。要求ごとに要る主張を問いにし、用語・人・場を見つけ、原文の引用とリンクをたどる。業務ルートの`sources/`に原文をそのまま保存し、PDFはテキストも置く。`map.md`と`log.md`に原文の場所、短い引用、未到達の問い、止めた理由を残す。止めどきは要求ごとに「すべてに原文が付いた」「飽和」「回数上限」「壁」で判定する。飽和で終えても足りない根拠を埋まった扱いにしない。`sources.toml`に題名・発行者・版・公開日・取得日・URL・ハッシュ・信頼度を書く。
5. **主張台帳を作る。** 本文で言うことを`claims.toml`へ1つずつ登録する。事実には原文の引用、実証結果には成果物のパスと値、解釈には前提、提案には前提と比較した代替案が必要である。原文が主張を支持するかを読み、反証も残す。対象・条件・時点の同じ数値と推奨に`subject`を付ける。
6. **章の骨子を本人に渡して止まる。** 節と主張IDの並びを示す。骨子、提案の主張、制度や関係者との協議に回す事項を確認してもらう。章末の一括承認に先送りしない。承認の記録は`reviews/`と証拠に残す。
7. **本文を書く。** 承認された骨子と台帳から`chapters/*.md`を作る。文末に`[C1-001]`等を付け、台帳と文を一致させる。本文に主張を足す必要が出たら先に台帳と根拠を整える。文体は`style.md`を使う。
8. **網羅を検査する。** `make test-coverage`（`make check`も同じ）を実行する。細部項目ごとの必要件数、種類別の根拠、引用、数値、裏取り状態、用語、出典の版・取得日・URL、図表、主張IDのない文を直す。落ちたテストに合わせて要求を緩めない。
9. **論理を検査する。** 章を書き終えたときと納品前に`make test-logic`を実行する。構造（欠けた前提、循環、事実への到達、依存する実証）、一貫性（同じ対象の数値・推奨）、推論（結論1つとその前提だけ）の3層を見る。判定の不一致は人の判断待ちにする。判定を`reviews/logic.json`に保存し、変わった論証だけ再判定する。
10. **本人の判断が必要なら止まる。** 推論のPENDING、提案の妥当性、制度の判断は、論証・根拠・判定理由・該当する章を渡す。人が許容した論証だけ`reviews/logic-accepted.toml`に理由・承認者・ハッシュを残す。構造の不備はこの承認で免除しない。
11. **仕上げる。** `yomiyasu`で意味・条件・確度を保って推敲し、主張IDと引用は保護する。本文の言い換えは台帳へも反映し、変わった論証を再検査する。`sanitize-artifacts`で会話や制作指示の混入を除く。根拠や未確定事項は消さない。
12. **buildして渡す。** `make check`とstrictの`make test-logic`を通し、人の判断待ちが0件であることを確認して`make build`する。脚注の題名・発行者・版・ページ・URL、主張IDが残らないことを確認する。納品物はMarkdown。検査の合否と骨子・提案・最終稿の本人確認を`.tmp/evidence/<task>/evidence.md`へ記録する。最終確認用のMarkdownと証拠を本人に渡して止まる。提出や送信はこのスキルで行わない。

原文・情報・権限が足りない場合は、その主張を未確認のままにし、足りないものと影響する細部項目を本人に渡す。推測の値や架空の根拠で埋めない。

## 推論の判定コマンド

判定の指示は[prompts/judge.md](prompts/judge.md)。コマンドの標準入力に論証JSONを渡し、標準出力から判定JSONだけを読む。実モデルの実行には当該業務の許可と接続が必要である。検証ではモデルを呼ばず、架空例のスタブを使う。

以下はラッパーの例である。`REPORT_SKILL`をスキル配置先の絶対パスに設定する。ラッパーは業務ルート外に置ける。Codexの進行イベントは最終回答ではないため、`--json`のイベント列をそのまま判定出力にしない。

```sh
#!/bin/sh
# judge-codex: 標準入力をプロンプトの後ろへ渡す。
set -eu
codex exec -m gpt-6.1-sol --sandbox read-only --ephemeral \
  "$(cat "$REPORT_SKILL/prompts/judge.md")"
```

```sh
#!/bin/sh
# judge-claude: 道具を使わず、標準出力は最終回答のテキスト。
set -eu
claude -p --tools '' --strict-mcp-config --output-format text \
  "$(cat "$REPORT_SKILL/prompts/judge.md")"
```

```sh
make test-logic JUDGES="--judge './judge-codex' --judge './judge-claude'"
```

CLIの引数は導入済み版の`codex exec --help`と`claude --help`でも確認する。通常運用は2判定。未指定はPENDINGになる。`--strict`はPENDINGもFAILとして終了コード1にする。判定が両方とも飛躍あり、または一方が矛盾ならFAIL。判定コマンドの異常は終了コード2である。

## 架空例による自己確認

```sh
python3 claude/bin/report-check coverage --root claude/skills/report/examples/harunagi
python3 claude/bin/report-check logic --root claude/skills/report/examples/harunagi \
  --judge 'python3 judge_stub.py' --judge 'python3 judge_stub.py' --strict
python3 claude/bin/report-check mutate --root claude/skills/report/examples/harunagi
```

スタブはJSONを読んで定型の判定を返すだけで、推論の品質は証明しない。`mutate`は7種類の検出率を`caught/total`で示し、元の台帳や本文を変更しない。運用開始時と検査の道具を変えたときに実行する。
