# imozuru の拠りどころ

SKILL.md の各決まりが、どの原文のどこから来たか。原文は 2026-10-09 の試し（題材＝探し方の研究）で
このスキル自身を使って落とした。行番号は、下の URL を `scripts/fetch.py` で落とした .txt / .md のもの
（PDF は `pdftotext -layout`、HTML は ax で変換。変換の仕方が違うと行番号はずれるので、短い引用で探す）。
決まりを直すときは、ここで元の文を読み直してから直す。

## 原文の取り先

| ファイル名 | URL |
|---|---|
| `bates-1989-berrypicking` | https://www.pages.gseis.ucla.edu/faculty/bates/articles/berrypicking.pdf |
| `ellis-1987-phd-behavioural-model` | https://etheses.whiterose.ac.uk/id/eprint/2975/1/DX093006.pdf |
| `kuhlthau-1991-inside-search-process` | https://tefkos.rutgers-sci.domains/Courses/612/Articles/Kuhlthau_Inside_91.pdf |
| `arxiv-2609.01294-explore-before-committing` | https://arxiv.org/pdf/2609.01294 |
| `arxiv-2608.02009-halt` | https://arxiv.org/pdf/2608.02009 |
| `arxiv-2602.03304-to-search-or-not` | https://arxiv.org/pdf/2602.03304 |
| `kastner-2007-horizon-estimate` | https://pmc.ncbi.nlm.nih.gov/articles/PMC2655834/ |
| `eumesy-unknown-terms` | https://speakerdeck.com/eumesy/examine-the-meaning-of-unknown-terms |
| `arxiv-2505.09316-scent-of-knowledge` | https://arxiv.org/pdf/2505.09316 |

## 決まりと出典

| 決まり | 出典 | 原文の場所 |
|---|---|---|
| 問いは探すうちに変わる。拾った断片を集めていく | Bates 1989 "The design of browsing and berrypicking techniques for the online search interface" | `bates-1989-berrypicking.txt` |
| たどり方の6つの動き（後ろへ・前へ・雑誌を通しで・近くを眺める・主題の索引・著者） | Bates 1989 | 同 L295-355 |
| 引用をたどれば、主題を言葉で言い表す問題を避けられる | Bates 1989 | 同 L297-302 |
| starting / chaining / browsing / differentiating / monitoring / extracting | Ellis 1987 博士論文（1989 の JoD 論文の元・本体は有料） | `ellis-1987-phd-behavioural-model.txt` L64、目次 L165-276 |
| 調べ始めは混乱するのがふつう。詳しいノートは早すぎる閉じを招く。当てはまりそうな事実を並べる | Kuhlthau 1991 "Inside the Search Process" | `kuhlthau-1991-inside-search-process.txt` L345-368 |
| 1つの方向に決め打ちすると、後の検索が同じ道を強める。仮説を枝分けして比べてから進む | Zhou ら 2026 "Explore Before Committing"（HypoSearch）arXiv 2609.01294 | `arxiv-2609.01294-explore-before-committing.txt` 冒頭の要旨 |
| 止めどきは確信度ではなく、要る主張の全部を証拠が支えたか | Roh & Han 2026 "HALT" arXiv 2608.02009 | `arxiv-2608.02009-halt.txt` 要旨 |
| 誤りは2種類＝足りているのに探し続ける over-search と、早くやめて外す under-search | Zhang ら 2026 "To Search or Not to Search" arXiv 2602.03304 | `arxiv-2602.03304-to-search-or-not.txt` 要旨 |
| 独立した2つの探し方の重なりから、まだ見つかっていない総数を見積もる（capture-mark-recapture） | Kastner ら 2007 "Estimating the Horizon of Articles to Decide When to Stop Searching" | `kastner-2007-horizon-estimate.md` L51 |
| 知らない用語は粒度の粗い順に＝百科事典 → 専門事典 → 教科書・講義資料 → サーベイ → 原著 | 横井祥 2017 「Examine the meaning of unknown terms」（Speaker Deck） | `eumesy-unknown-terms.md` L343-373 |
| 情報の匂い（information scent）で次にたどる先を選ぶ | Pirolli & Card 1999 "Information foraging"（本体は有料・DOI 10.1037/0033-295x.106.4.643） | 未取得。LLM に当てた例は `arxiv-2505.09316-scent-of-knowledge.txt` |

## 試しで分かった、流れの側の事実

- 検索結果の URL は古い。11 本中 5 本が 404・ログインの壁・PDF のふりをした HTML → `fetch.py` で中身を見て判定する
- LLM の検索エージェントの論文3本の参考文献に、人の情報探索の研究（Bates・Kuhlthau・Ellis・Marchionini）は0件、情報採餌理論が1件だけ。AI 側はこの蓄積をほとんど使っていない
- OpenAlex の題名検索は、全文検索（`search=`）だと解説記事が上に来る。題名に絞って被引用順にすると本体が1位に来る。ただし登録された題名が副題抜きのことがある → DOI を最優先
- 検索役のサブエージェントは「探していない」の節をきちんと書く。そのまま次の周の手がかりの一覧になる

## まだ読んでいない定番（届いたら足す）

- Pirolli & Card 1999（有料）／Marchionini 2006 "Exploratory search"（有料）
- Case & Given 2016 "Looking for Information"（情報探索研究の教科書。OpenAlex で Bates・Kuhlthau を引く論文の上位）
- Wilson 1999 "Models in information behaviour research"／Booth 2010 "How much searching is enough?"／TARCiS 2024（引用をたどる探索の指針）

## 3つの題材で試して分かったこと（2026-10-09）

- 題材＝探し方の研究（親が手で）／AI 生成画像の編集可能化（論文の多い分野・2回）／大陸塗り（論文が無く個人の発信だけの分野）
- 主張を「〜がある」だけで並べると1周で埋まり、依頼の芯が抜けたまま止まる → 主張の1つは依頼の条件そのまま、半分以上は原文を読まないと答えられない形
- 論文の多い分野では chain.py が古い論文に効き、新しい論文（出て1年ほど）には効かない
- 個人の発信の分野では chain.py も DOI も使えず、道具は fetch.py と WebSearch だけ。standard の検索はほぼ空振りで extended で一斉に出た。大事な中身は X・pixiv・小紅書のログインの壁の向こうに集まる
- 日本語の記事は短くても本物（2,904字）。英語の論文向けの下限 3,000 字では落ちる
- 検索役の報告は検索結果の抜粋がもと。Type-R の説明が原文と違っていた
