# 出典とライセンス

このスキルは、pstackの次のファイルを日本語に翻訳し、このハーネスのルール（承認フロー、サブエージェントの利用条件、テストケースの扱い、Gitの承認）に合わせて改変したものである。

- 上流: https://github.com/cursor/plugins/tree/main/pstack （commit `ce649c0a`）
- 元のファイル: `skills/poteto-mode/SKILL.md`（Playbooksの節と、手順をTodoに写す約束）、`skills/poteto-mode/playbooks/{bug-fix,feature,refactoring,perf-issue,investigation,runtime-forensics}.md`、`skills/benchmark-checklist/SKILL.md`、`skills/principle-fix-root-causes/SKILL.md`、`skills/principle-model-the-domain/SKILL.md`の一部

主な変更: poteto-modeの全体（原則の索引、モデルの割り当て、サブエージェントの既定、自律の範囲、返答の書き方）は移植せず、作業の種類ごとの手順だけを取り出した。作業の重さ（E/0/1/2/R）との関係を追加。実装の委任、arena・architect・interrogate・tdd・swarmの呼び出し、コミットとPRの手順を外し、自分で順に行う形にした。動作を固定するテストと失敗するテストを、既存テストか使い捨てのスクリプトに置き換えた。runtime-forensicsは、bug-fixの「診断だけの依頼」として統合した。Model invocationを有効化。

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
