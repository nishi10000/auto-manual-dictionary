# 検索連携仕様

## 目的

confirmed辞書をBM25/RAG検索のクエリ展開に使う。ただし誤展開で検索品質を落とさないよう、状態と文脈で制御する。

## エクスポート

```bash
python -m auto_manual_dict export-dictionary --db work.sqlite3 --format jsonl --out dictionary.jsonl
python -m auto_manual_dict export-query-expansion --db work.sqlite3 --out query_expansion.json
```

## confirmedのみ自動展開

自動検索展開に使えるのは原則:

- concept status = `confirmed`
- term status = `confirmed`
- blockedでない
- contextが一致する、または一般用途と判定されたもの

## クエリ展開例

入力:

```text
エンジンがかからない 燃圧
```

展開候補:

```json
{
  "original": ["エンジンがかからない", "燃圧"],
  "expanded": [
    {"term": "始動不良", "weight": 0.9, "source": "confirmed_dictionary"},
    {"term": "engine does not start", "weight": 0.8, "source": "confirmed_dictionary"},
    {"term": "fuel pressure", "weight": 0.9, "source": "confirmed_dictionary"}
  ]
}
```

## 展開制限

- 1クエリあたり最大展開語数を設定する
- candidate/low confidenceは自動展開しない
- 多義語は文脈一致がない限り展開しない
- blocked語は除外する

## 評価

BM25のみと比較して、Top5正解率・MRR・誤検索増加率を見る。
