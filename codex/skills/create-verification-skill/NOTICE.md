# 出典とライセンス

このスキルは、pstackの次のファイルを日本語に翻訳し、このハーネスのルール（承認フロー、サブエージェントの利用条件、テストケースの扱い、Gitの承認）に合わせて改変したものである。

- 上流: https://github.com/cursor/plugins/tree/main/pstack
- 取得元のミラー: https://github.com/backnotprop/pstack （commit `fce11a3442cfd59a21136de0b7010474c6a10ef5`）
- 元のファイル: `skills/create-verification-skill/SKILL.md`、`references/feature-map-example/`（例は原文のまま）

主な変更: Claude Codeのパスに限定。ビルドの修正と新しい依存の追加をユーザーの承認制にした。シークレットの扱い（`op run`、`.env`を作らない）、bun・uvの利用を追加。機能一覧の見出しに日本語を追加。証拠の既定の置き場所を`.tmp/evidence/<task>/`にし、形式を`~/.claude/references/evidence.md`に揃えた。

## pstackのライセンス

```
MIT License

Copyright (c) 2026 Lauren Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
