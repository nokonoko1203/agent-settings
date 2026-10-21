# 出典とライセンス

このスキルは、pstackの次のファイルを日本語に翻訳し、このハーネスのルール（サブエージェントの利用条件、成果物の保存先）に合わせて改変したものである。

- 上流: https://github.com/cursor/plugins/tree/main/pstack （commit `ce649c0a`）
- 元のファイル: `skills/how/SKILL.md`、`references/explorer-prompt.md`、`references/explainer-prompt.md`

主な変更: 探索役と説明役のサブエージェントを既定では使わず、観点ごとに自分で順に読む形にした（サブエージェントはユーザーが明示した場合だけ）。モデルの割り当ての記述を削除。要になる主張を`file:line`まで確かめる手順、LSPの優先、`.tmp/research/`への保存を追加。Model invocationを有効化。

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
