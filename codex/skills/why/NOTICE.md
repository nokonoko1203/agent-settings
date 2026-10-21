# 出典とライセンス

このスキルは、pstackの次のファイルを日本語に翻訳し、このハーネスのルール（承認フロー、サブエージェントの利用条件、テストケースの扱い、Gitの承認）に合わせて改変したものである。

- 上流: https://github.com/cursor/plugins/tree/main/pstack
- 取得元のミラー: https://github.com/backnotprop/pstack （commit `fce11a3442cfd59a21136de0b7010474c6a10ef5`）
- 元のファイル: `skills/why/SKILL.md`、`references/epistemics.md`、`references/investigator-prompt.md`、`references/synthesizer-prompt.md`、`references/sources/{code-archaeology,notion,slack,linear,incident-postmortem}.md`

主な変更: 情報源を、この環境で使えるgit・gh、GitHub Issues、Notion、Slackに絞った（LinearをGitHub Issuesに書き換え）。既定で自分で順に調べ、サブエージェントはユーザーが明示した場合だけにした。調査員と統合役のプロンプトを、調べ方（investigation.md）と回答の形（output-format.md）に再構成した。メールの扱いとSlackのプライベートチャンネルの扱いを追加。Model invocationを有効化。

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
