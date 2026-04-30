# テスト設計

## 方針

会社環境では Python と pip が使える前提。最低限 `python -m unittest` で実行可能にしつつ、通常は `pytest` を推奨する。pandas などの導入も可能なので、評価・レビューCSV検証では pandas を使ってよい。

TDD原則:

1. 先にテストを書く
2. 失敗を確認する
3. 最小実装で通す
4. リファクタする

## テスト分類

## Unit tests

### HTML抽出

対象: `html_extract.py`

検証:

- titleを抽出できる
- h1/h2を順序付きで抽出できる
- 段落テキストを抽出できる
- tableのセルを落とさない
- img src/altを抽出できる
- script/styleを本文に混ぜない
- 文字化けしにくい

fixture例:

```html
<html><head><title>点検手順</title></head>
<body>
<h1>始動不良</h1>
<p>エンジン始動不良時は燃圧を点検する。</p>
<table><tr><th>項目</th><th>基準</th></tr><tr><td>燃圧</td><td>300 kPa</td></tr></table>
<img src="fuel_pump.png" alt="燃料ポンプ" />
</body></html>
```

### アンカー抽出

対象: `anchors.py`

検証:

- `P0A80` をDTCとして抽出
- `216 N·m`, `216 N m`, `216 Nm` をトルクとして正規化
- `12 V` を電圧として抽出
- 画像名を正規化
- 重複を除去

### ページマッチング

対象: `page_matcher.py`

検証:

- DTC一致で高スコア
- トルク値一致で高スコア
- 画像名一致で加点
- アンカーなしでは低スコア
- 1:many候補を保持できる
- unmatchedを許容する

### 用語抽出

対象: `term_extract.py`

検証:

- 日本語複合語候補を抽出
- 英語noun phrase候補を抽出
- DTC/数値だけを用語にしない
- stopwordを除去
- 見出し語に高い重みをつける

### 確信度更新

対象: `confidence.py`

検証:

- evidence_countだけでは過剰加点しない
- evidence_typeが多様だと加点
- blockedと矛盾すると減点
- confirmed辞書と整合すると加点
- 閾値超えでreview_readyになる

### レビュー出力

対象: `review.py`, `export.py`

検証:

- review_readyだけCSV出力
- contextとsourceを含む
- approveでconfirmedになる
- blockでblockedになる
- confirmedだけ検索展開辞書に出る

## Integration tests

### ingest -> match -> extract -> confidence -> export

小さな日英fixtureで一連の処理を実行する。

期待:

- documentsが登録される
- anchorsが抽出される
- page_match_candidatesが作成される
- concept候補が作成される
- review_readyが出力される

## Regression tests

過去に誤判定した語をfixture化する。

例:

- `学習` を常に `learning` に固定しない
- `補正` を常に `correction` に固定しない
- 仕向地違いページを高信頼にしない

## Performance smoke tests

PoC段階:

- 500 HTMLを5分以内にingest
- SQLite DBサイズが現実的
- exportが1分以内

## テストコマンド

unittest:

```bash
python -m unittest discover -s tests -v
```

pytest利用可なら:

```bash
pytest tests -q
```
