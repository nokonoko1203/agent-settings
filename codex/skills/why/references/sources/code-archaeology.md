# ソース管理の履歴（git、`gh`、リポジトリ内）

## 含まれるもの

- コミット履歴（メッセージ、日付、作者、差分）
- PR本文、レビューコメント、議論（`gh`）
- コード内のコメント、TODO、FIXME、非推奨の注記
- ADR（設計判断の記録）があればそれ
- テスト。名前とassertが、変更の動機になった例外的なケースを表していることが多い
- 同じコミットで変更された関連ファイル（同時に変わるという手がかり）
- リポジトリ内のCHANGELOGやリリースノート
- コミットメッセージやPR本文にあるIssue番号

コードに直接結びついているので、最も信頼でき、最も網羅的な情報源である。リポジトリを通ったものはすべてここにある。

## 調べ方

起点のコミット一覧を広げる。

```bash
# 名前の変更を追った履歴
git log --follow --oneline -- <file>

# この文字列を足した・消したコミット
git log -S '<コード中の正確な文字列>' -- <file>

# 正規表現で
git log -G '<regex>' -- <file>

# 各行を誰がいつ書いたか
git blame -L <start>,<end> <file>

# 1つのコミットの差分全体
git show <hash>

# 2点間でこのファイルに触れたコミット
git log <old>..<new> -p -- <file>
```

リポジトリ内の別の文書を探す。

```bash
# ADRはdocs/adr/などにあることが多い
rg -l -i 'architecture.decision' --glob '*.md'

# 対象付近のTODOやFIXME
rg -n -C2 '(TODO|FIXME|HACK|XXX|NOTE)' <target_file>

# 関連するテスト
rg -l '<symbol>' --glob '*test*'
```

PRの議論は`gh pr view <number> --comments`で、レビューのやりとりは`gh api repos/<owner>/<repo>/pulls/<number>/comments`で読む。
