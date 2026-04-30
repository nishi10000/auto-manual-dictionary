# 定量ゴール

## 目的

実装前に「何ができたら成功か」を数値で決める。  
このプロジェクトの成功は、候補数の多さではなく、**人間レビューの負荷を下げつつ、検索/RAGに混ぜても危険な誤辞書を増やさないこと**で測る。

## 前提

- 会社環境では Python + pip が使える。
- 初期DBは SQLite。
- 日英HTMLは非対称で、ファイル名・ページ数・構成は一致しない。
- 実データは機密の可能性があるため、外部API送信なしで評価できること。
- `confirmed` と `safe_for_query_expansion` / `safe_for_answer_generation` は分ける。

## 評価データセット

### Fixture Set A: 開発用ミニセット

目的: 実装中の自動テストと回帰確認。

目標規模:

- 日本語HTML: 5〜10ファイル
- 英語HTML: 5〜10ファイル
- 人手正解済み block対応: 20件以上
- 人手正解済み用語concept: 30件以上
- unmatched例: 5件以上
- warning/caution/prohibition例: 5件以上

合格条件:

- pytestで全テストが通る
- 同じ入力を2回ingestしてもdocument/concept/evidenceが不正に重複しない
- fixture上の期待conceptがすべてexportされる

### Gold Set B: PoC評価セット

目的: 使える見込みがあるかを判断する。

目標規模:

- 日本語HTML: 50〜100ファイル
- 英語HTML: 50〜100ファイル
- 人手正解済み block/section対応: 100件以上
- 人手正解済み concept: 100件以上
- 検索評価クエリ: 30件以上
- safety/warning系concept: 20件以上
- unmatched / 1:many / many:1 を必ず含める

### Pilot Set C: 実運用前評価セット

目的: 会社業務で使い始めてよいかを判断する。

目標規模:

- 日本語HTML: 300ファイル以上
- 英語HTML: 300ファイル以上
- 人手正解済み concept: 300件以上
- 検索評価クエリ: 100件以上
- safety/warning系concept: 50件以上

## Milestone 1: HTML取り込み・抽出

目的: HTMLからレビュー可能な構造を安定して取り出す。

定量ゴール:

- ingest成功率: 95%以上
- HTML parseでプロセス全体が停止する件数: 0件
- 同一入力の再ingestで重複document発生: 0件
- title/heading抽出成功率: Gold Set Bで90%以上
- warning/caution/note/prohibition block検出 recall: Gold Set Bで80%以上
- 表テキスト抽出で空になる重要表: 5%未満
- ログに本文全文・機密HTML断片を大量出力する箇所: 0件

合格判定:

- Fixture Set Aの抽出テストが全てpass
- Gold Set Bのサンプル確認で、レビューに必要なsnippet/heading_path/source_pathが出ている

## Milestone 2: Anchor抽出

目的: 日英対応の強い手がかりを取る。

対象anchor:

- DTC
- トルク値
- 電圧
- 部品番号
- 画像名
- 表形状
- 手順番号

定量ゴール:

- DTC抽出 precision: 98%以上
- DTC抽出 recall: 95%以上
- トルク/電圧など数値anchor precision: 95%以上
- 数値anchor normalization失敗率: 5%未満
- 重複anchor保存率: 0件、または正規化後に一意化されること

合格判定:

- Fixture Set Aで期待anchorが全て抽出される
- Gold Set Bで誤抽出例を20件サンプル確認して、致命的パターンがない

## Milestone 3: Block/Section対応候補

目的: ページ1:1に頼らず、日英断片の対応候補を出す。

定量ゴール:

- block対応候補 Precision@1: 70%以上
- block対応候補 Precision@5: 85%以上
- unmatchedを無理に高confidence化しない率: 80%以上
- 1つの日本語blockに複数英語候補を残せること: 実例で確認
- page_matchだけを根拠にreview_readyへ上げる件数: 0件

合格判定:

- Gold Set Bの正解block対応100件で測定
- `evidence_json` に、なぜ対応候補になったかが表示できる

## Milestone 4: 用語候補・概念候補

目的: 人間がレビューできる粒度でconcept候補を作る。

定量ゴール:

- review_ready候補の人間承認率: 70%以上
- high confidence候補、例: 0.85以上、の承認率: 80%以上
- false merge rate: 10%未満
- false split rate: 20%未満
- safety/warning系候補がcandidateのまま沈む率: 20%未満
- blocked候補と同じ組み合わせが再びreview_readyに上がる件数: 0件、または明示的な再評価理由あり

合格判定:

- Gold Set Bで100件以上レビューする
- approve/edit/hold/blockの比率を記録する

## Milestone 5: Confidenceとレビューキュー

目的: 人間が見るべきものを適切に上げる。

定量ゴール:

- confidence breakdownありの候補: 100%
- evidence_idsありのreview行: 100%
- source snippet / target snippetありのreview行: 95%以上
- row_version / export_batch_idありのreview行: 100%
- 古いCSV import拒否率: 100%、意図した競合テストで全て拒否
- confirmedへの自動昇格: 0件、人間review action必須

合格判定:

- review CSVを人間が見て、1候補あたり60秒以内にapprove/edit/hold/block判断できる候補が70%以上
- evidence不足で判断不能なreview_ready候補が30%未満

## Milestone 6: 辞書exportと検索改善

目的: confirmed/safe辞書を検索/RAGに安全に渡す。

定量ゴール:

- `blocked` がquery expansion exportに混ざる件数: 0件
- `candidate` / `review_ready` がquery expansion exportに混ざる件数: 0件
- `safe_for_query_expansion = false` がquery expansion exportに混ざる件数: 0件
- BM25 + query expansion のTop5正解率がBM25のみより +10ポイント以上改善
- Top1正解率がBM25のみより悪化しない、許容悪化は -2ポイント以内
- unsafe expansion rate: 2%未満
- RAG-safe exportは `safe_for_answer_generation = true` のみ

合格判定:

- 検索評価クエリ30件以上で測定
- 改善がない場合は、辞書exportは実運用検索に接続しない

## Milestone 7: 実運用パイロット

目的: 実際の作業補助として使えるかを見る。

定量ゴール:

- 1時間あたりconfirmed concept数: 20件以上
- 1候補あたりレビュー中央値: 90秒以下
- review_readyの承認率: 75%以上
- block率: 15%以下。ただし初期調整期間は除く
- ユーザーが検索で正しい根拠箇所に到達する率: 80%以上
- 誤辞書が原因の明確な検索悪化: 重大0件

合格判定:

- 2回以上のHTML追加サイクルで安定している
- blocked理由の上位3件に対して改善タスクが作れる

## Stop / No-Go 条件

以下に該当したら、検索/RAG連携に進まない。

- review_ready承認率が50%未満
- false merge rateが20%以上
- blocked候補がquery expansionに1件でも混入
- safety/warning系で誤ったanswer-generation safeが1件でも見つかる
- HTML抽出が不安定で、同じ入力から同じblock id/evidenceが再現しない
- ログやexportに機密本文を過剰に出している

## 最初の実装で狙う最小ゴール

最初の実装スプリントでは、全部を達成しない。まず以下を満たせば成功。

- Fixture Set Aを作る
- `ingest` でHTMLをSQLiteに保存できる
- `document_blocks` と `anchors` が作れる
- 同じHTMLの再ingestで重複しない
- pytestが通る
- CIが通る

この段階では、辞書品質の評価ではなく、**再現性ある土台ができたか**を見る。
