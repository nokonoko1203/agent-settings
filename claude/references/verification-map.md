# 機能一覧と確認手段の対応

検証スキル（`.claude/skills/verify-<app>/`）の機能一覧に、サブ機能ごとの確認手段を書く。ソースから抽出できるプロジェクトでは、確認対象とe2eのケースの対応表も持つ。`verify-map`は、機能一覧・対応表・テスト・e2eの結果の整合を検査する。目的は3つある。

- 何をe2eで確かめ、何を手動や未確認のまま残しているかを、機能一覧と対応表から読めるようにする
- 画面の操作やAPIを足し引きしたときに、受け持つケースのない対象を、手元とCIで見つける
- AIが足したe2eのケースを、後から一覧で照合できるようにする。対応表を持つプロジェクトでは、これを根拠にe2eのケースをAIが追加してよい（`CLAUDE.md`の「調査と検証」）

この検査は対応の整合だけを見る。期待する結果が正しいか、範囲の分け方が十分か、理由が妥当かは、人がレビューする。

## サブ機能の札

機能ファイルの`サブ機能`（英語では`Sub-features`）の箇条書きの各行の末尾に、確認手段の札を1つ以上付ける。4つのH2の名前と順序は変えない。

```markdown
- `note-save`: 題名と本文を入れて保存すると、一覧の先頭に出る ［e2e: notes-save］
- `note-color`: メモに色を付ける ［手動: 一覧の色を操作前後の画像で見る］
- `note-title-required`: 題名が空なら保存せずに理由を出す ［e2e(理由の表示): notes-title-required］ ［手動(入力欄の強調): 操作前後の画像で見る］
- `note-attach`: ファイルを添付する ［未確認: ファイル置き場のモックがまだない］
```

- 形は`［種類: 内容］`。括弧は全角の`［］`を使い、説明の中では使わない。
- 種類は4つ。英語のリポジトリでは右の語も使える。
  - `e2e`: 内容はケースID。複数なら半角カンマで区切る。同じケースを複数のサブ機能から参照してよい
  - `手動`（`manual`）: 内容は確かめ方。手動で確かめるという決めごとで、確かめ済みという意味ではない
  - `対象外`（`excluded`）: 内容は確かめない理由
  - `未確認`（`unverified`）: 内容は、確かめる手段や前提がまだない理由
- サブ機能の一部だけを扱う札は`［種類(範囲): 内容］`とし、残りの範囲にも札を付ける。札を複数付けるときは、すべてに範囲を書く。範囲のない札は、そのサブ機能の全体を受け持つ。
- サブ機能IDとケースIDは、小文字の英数字とハイフン（`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`）。サブ機能IDは機能一覧の全体で一意にする。

## e2eのケースID

Playwrightのテストに、ケースIDをタグで1つ付ける。テスト名は自由に変えてよく、IDは変えない。

```typescript
test('題名と本文を入れて保存すると、一覧の先頭に出る', { tag: '@case:notes-save' }, async ({ page }) => {
	// ...
});
```

IDは文字列として書く（`'@case:<id>'`）。コメントの中の`@case:`は数えない。1つのテストにケースIDは1つ。`describe`には付けない。同じプロジェクトの別のテストに同じIDを付けない。

## 確認対象の抽出（`inventory.json`）

ソースから確認対象を拾い、プロジェクトの`e2e/ledger/inventory.json`に書いてコミットする。対象の増減が、PRの差分に出るようにするためである。抽出器はプロジェクトの言語で書く。今あるのはSvelteKit用の`e2e-inventory-sveltekit.ts`（bunで動かし、プロジェクトの`svelte/compiler`と`typescript`を使う）だけで、他の構成では必要になったときに同じ出力の形で作る。

```bash
bun .claude/bin/e2e-inventory-sveltekit.ts write    # 抽出してinventory.jsonを書く
bun .claude/bin/e2e-inventory-sveltekit.ts check    # コミット済みのinventory.jsonがソースと一致するか（違えば終了1）
```

SvelteKit用の抽出器が拾うもの:

| 種類 | 拾うもの | キーの例 |
|---|---|---|
| `route` | `+page.svelte`（`+page@….svelte`を含む）の画面。`(group)`はパスから外し、`[id]`などは書いたまま残す | `route:/items/[id]` |
| `api` | `+server.ts`・`+server.js`が書き出すHTTPメソッド | `api:POST /api/notes` |
| `action` | `+page.server.ts`の`actions`の名前 | `action:/items?/save` |
| `ui` | `.svelte`の要素の`on*`属性、コンポーネントの`on*`属性（`onSave`のような大文字を含む名前も）、`on:`ディレクティブ、フォーム要素の`bind:value`・`bind:checked`・`bind:group`・`bind:files` | `ui:src/routes/notes/+page.svelte#input[題名].bind:value` |
| `call` | 画面側のコード（サーバー専用のファイルを除く）の`fetch`で、宛先が`/`で始まり、`?`より前のパスとメソッドが静的に決まるもの | `call:src/lib/notes/api.ts#POST /api/notes` |
| `link` | `<a href>`と`goto()`の内部の遷移先 | `link:src/routes/+page.svelte#/about` |

- `ui`の`[名前]`は、`aria-label`、`id`、`name`、要素の中の固定の文字、包んでいる`<label>`の文字の順に取る。名前がなくても、同じファイルで要素と操作の組が1つなら、名前なしのキーにする。
- 静的に決まらないものは、黙って落とさず`unresolved:`のキーにする。宛先やメソッドが変数の`fetch`（パスに補間がある`` fetch(`/api/${name}`) ``を含む）、名前で区別できない同じ要素・同じ操作、要素へのスプレッド（`{...props}`）、式だけの`href`がこれに当たる。抽出できる形に直すか、対応表で理由付きの例外にする。`unresolved:`の対象は、ケースの`covers`では受け持てない。検出を消すためだけにコードを書き換えない。
- 行番号はキーに入れない（行がずれるだけで差分が出ないようにするため）。`check`の出力には行番号を出す。
- 拾わないもの: コンポーネントへの`bind:`（例: ポップアップの`bind:open`）と、コンポーネントへのスプレッドの中の操作。外部のURLへの`fetch`とリンク。キャンバスの中の個々の図形。これらは機能一覧の点検（`/maintain-verification-skill`）で見る。
- 抽出が保証するのは、対象の一覧が今のソースと一致することだけである。受け持つケースが十分なassertionで確かめているかは、レビューで見る。

## 対応表（`scenarios.json`）

`e2e/ledger/scenarios.json`に、ケースが受け持つ確認対象と、ケースで受け持たない対象の例外を書く。

```json
{
  "scenarios": [
    {
      "id": "notes-save",
      "title": "題名と本文を入れて保存すると一覧の先頭に出て、開き直しても残る",
      "status": "implemented",
      "aspects": ["normal", "persist"],
      "covers": ["ui:src/routes/notes/+page.svelte#button[保存].onclick", "call:src/lib/notes/api.ts#POST /api/notes", "api:POST /api/notes"]
    },
    {
      "id": "notes-title-required",
      "title": "題名が空なら保存せずに理由を出し、メモは増えない",
      "status": "implemented",
      "aspects": ["invalid-input"],
      "covers": ["api:POST /api/notes"]
    },
    {
      "id": "notes-attach",
      "title": "ファイルを添付して保存すると、メモにファイル名が出る",
      "status": "pending",
      "reason": "ファイル置き場のモックがまだない",
      "aspects": ["normal", "persist"],
      "covers": ["ui:src/routes/notes/+page.svelte#input[添付].bind:files"]
    }
  ],
  "exceptions": [
    { "key": "ui:src/routes/notes/+page.svelte#input[色].bind:value", "kind": "manual", "feature": "notes.md", "reason": "結果が一覧の色だけで、e2eで観測できない" }
  ]
}
```

- `status`は`implemented`（タグ付きのテストがある）か`pending`（テストがまだない。`reason`は必須）。
- `aspects`は`normal`（正常に動く）、`persist`（保存後も残る）、`invalid-input`（不正な入力で何も変わらない）、`error`（相手の異常を伝える）、`empty`（データがないときの表示）から選ぶ。書き込みの`api`（`POST`・`PUT`・`PATCH`・`DELETE`）と`action`を受け持つケースの中に、`persist`と`invalid-input`がそろっていなければならない。
- `covers`は`inventory.json`のキー。1つの対象を複数のケースが受け持ってよい。1つのケースが複数の対象を受け持ってもよい。
- `exceptions`の`kind`は、`manual`（手動で確かめる。`feature`に機能ファイル名）、`unit`（ユニットテストで確かめる。`test`にファイルのパス）、`out-of-scope`（確かめない）。`reason`は必須。ケースが受け持つ対象を例外にもしない。
- 機能一覧の札`［e2e: <id>］`は、利用者から見た振る舞いとケースを結ぶ。対応表は、実装の対象とケースを結ぶ。`implemented`のケースは、どれも機能一覧のどこかの札から参照する。`pending`のケースは札に書かない（そのサブ機能は`未確認`にする）。

AIがe2eのケースを足すときは（手順は`write-e2e-case`スキル）、ケースのテストを書き、`scenarios.json`と機能一覧の札を同じ変更で直す。足したケースは報告で一覧にする。既存のケースの期待値を変えるとき、ケースを消すときは、ユーザーの承認を得る。機能を消して確認対象がなくなったケースは、対応表と一緒に消してよい。

## 検査（`verify-map`）

```bash
python3 .claude/bin/verify-map check --skill .claude/skills/verify-<app> [--ledger e2e/ledger] [--tests e2e] [--results test-results/results.json]
```

手元では`uv run --script .claude/bin/verify-map check ...`でもよい。標準ライブラリだけで書いてあるので、CIでは`python3`で動かせる。

| 引数 | 検査すること |
|---|---|
| なし | 索引と機能ファイルの一致、4つのH2、サブ機能の行と札の形、サブ機能IDの重複、範囲の重なり |
| `--ledger` | 抽出した対象のどれもがケースか例外に受け持たれていること。`covers`と例外の`key`が今の抽出結果にあること。`status`・`aspects`・`reason`・例外の形。書き込みの対象の`persist`と`invalid-input`。札のケースIDと`implemented`のケースの一致 |
| `--tests` | テストのファイルに書いた`@case:<id>`と、ケースIDとの対応（テストのないケース、対応表にないID、テストがあるのに`pending`のケース） |
| `--results` | PlaywrightのJSONの結果と、ケースIDとの対応（IDのないテスト、対応表にないケース、重複、結果にないケース）。ケースの成否 |
| `--cases a,b` | `--results`で照合するケースを、動かしたケースに絞る（`select`で選んで動かしたとき）。CIでは付けず、全件を照合する |

`--ledger`なしでは、機能一覧の札だけを正として、`--tests`と`--results`を照合する。

ケースの結果は、成功・失敗・不安定（再試行で通った）・スキップ・未実行に分ける。成功以外はすべて不整合として落とす。`test.fail()`で失敗を期待したテストも、成功には数えない。

終了コードは、`0`が不整合なし、`1`が不整合あり、`2`が検査できない（ファイルがない、JSONが読めない）。`--results`なしの`0`は、e2eが通ったことを意味しない。どの`0`も、手動・対象外・未確認の範囲と、対応表の例外を確かめたことを意味しない。検査はそれらを一覧にして出す。

## 実行するケースの選択

e2eの全件が数分で終わるなら、全件を動かす。長くかかる場合は、変更から選ぶ。

```bash
bun .claude/bin/e2e-inventory-sveltekit.ts select --base origin/main
```

- 変更したファイルは、`<base>...HEAD`の差分、未コミットの変更、追跡していない新しいファイルを合わせたもの。
- 変更したファイルと、それを取り込んでいるファイル（相対パス、`$lib`、package.jsonの`imports`の`#x/*`による`import`をたどる）から拾った対象を、`covers`に持つケースを選ぶ。変更したテストのファイルにあるケースも選ぶ。
- 出力は、選んだケース、Playwrightの`--grep`に渡す正規表現、未実装で動かせないケース、対応表から引けない変更。
- 対応表から引けない変更（設定、依存、取り込み関係で画面に届かないファイル）は、その利用先を調べ、関係するケースを足して動かす。大きなリファクタリングや共通処理の変更では、全件を動かす。
- 選んだケースだけを動かしたら、`verify-map check ... --results <JSON> --cases <選んだケース>`で照合する。選んだケースと、選んだ理由を証拠に書く。

## つなぎ方

- `inventory.json`の`check`と、軽い検査（`--ledger`と`--tests`。`--results`なし）を、プロジェクトの`check`に足す。ブラウザは起動しない。
- 抽出器は`.claude/bin/`に入るので、プロジェクトの`tsconfig.json`の`include`に`.claude/bin/*.ts`を足し、型検査の対象にする。
- e2eは既存のコマンドで動かし、そのあとで`--results`付きの検査をする。実行の前に前回の結果ファイルを消すか移し、今回の結果だけを読む。
- CIでは、e2eが失敗しても検査を動かし（`if: ${{ !cancelled() }}`）、e2eの失敗を検査の成功で上書きしない。検査の出力（未実装と例外の一覧を含む）をPRのコメントに載せる。
