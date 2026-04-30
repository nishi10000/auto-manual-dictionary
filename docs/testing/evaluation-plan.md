# 評価設計

## 評価目的

このプロジェクトの評価対象は「辞書候補が多いこと」ではない。検索/RAG/翻訳補助に使ったとき、正しい整備情報に近づくかを評価する。

## 評価軸

## 1. ページ対応候補の精度

指標:

- Precision@1
- Precision@5
- high confidence候補の正解率
- unmatchedを正しくunmatchedにできた率

評価データ:

- 人間が確認した日英ページ対応ペア 50〜100件
- 1:many / many:1 / unmatched を含める

## 2. 用語対訳候補の精度

指標:

- review_ready候補の承認率
- confirmed化率
- blocked率
- 多義語の文脈分離成功率

評価対象語:

- DTC/診断
- トルク/仕様値
- 脱着/交換/調整
- 症状
- 警告/注意
- 電装/センサ

## 3. 確信度スコアの妥当性

指標:

- score帯ごとの承認率
  - 0.95以上
  - 0.85〜0.95
  - 0.70〜0.85
  - 0.70未満
- evidence_countと正解率の相関
- evidence diversityと正解率の相関

目的:

単純な証拠数ではなく、多様な証拠が正解率に効いているか確認する。

## 4. 検索改善評価

ベースライン:

- BM25のみ

比較:

- BM25 + confirmed辞書展開
- BM25 + confirmed/candidate辞書展開
- BM25 + concept_id展開

指標:

- 正解ページがTop1/Top3/Top5に入る率
- MRR
- 誤検索増加率
- ユーザーが見たい根拠箇所への到達率

評価クエリ例:

- `始動不良 燃圧`
- `エンジンがかからない`
- `ハブナット トルク`
- `P0A80 バッテリー診断`
- `ABS 警告灯 DTC`

## 5. レビュー効率

指標:

- 1候補あたりレビュー秒数
- 1時間でconfirmedにできる件数
- review_readyキューの増加速度
- 重要語がcandidateに沈んでいないか

## 合格ライン PoC

詳細な段階別ゴールは `docs/specs/quantitative-goals.md` を正とする。最低ラインは以下。

- review_ready候補の承認率: 70%以上
- high confidence候補、例: 0.85以上、の承認率: 80%以上
- block/section対応候補 Precision@5: 85%以上
- confirmed辞書展開でTop5正解率がBM25のみより +10ポイント以上改善
- Top1正解率はBM25のみより悪化しない、許容悪化は -2ポイント以内
- blocked/candidate/review_ready候補が検索展開に混ざらない
- safety/warning系で誤ったanswer-generation safeを0件にする

## 重要な失敗パターン

- 同じ誤対応が大量に積まれてスコアが上がる
- 多義語を1訳に固定する
- 非対称ページを無理に1:1化する
- candidate辞書を検索展開に混ぜてノイズ化する
- confirmedが文脈なしで広がりすぎる
