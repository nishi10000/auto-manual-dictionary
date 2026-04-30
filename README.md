# Auto Manual Dictionary Project Docs

自動車整備マニュアル（日英HTML、非対称・ファイル名不一致前提）から、検索/RAGに使える多言語用語辞書を育てる Python プロジェクトの仕様・設計資料一式。

## 前提

- 会社環境では Python しか動かない想定。
- Node.js / Java / 外部DB必須構成にはしない。
- 初期実装は Python CLI + SQLite + JSONL/CSV 入出力で完結させる。
- pip は利用可能なので、pandas などのPythonパッケージは必要に応じて導入してよい。
- ただしDBサーバーやNode/Java依存は初期では避ける。
- 日英ページは必ずしも 1:1 対応しない。
- ファイル名は一致しない。
- 辞書は日英ペア固定ではなく、概念ID中心に育てる。

## 主要ドキュメント

- `docs/specs/requirements.md` — 要件定義
- `docs/specs/functional-spec.md` — 機能仕様
- `docs/specs/operations-workflow.md` — 実運用手順と人間レビュー対象
- `docs/specs/quantitative-goals.md` — 実装前に決める定量ゴール
- `docs/architecture/architecture.md` — Pythonアーキテクチャ
- `docs/architecture/data-model.md` — SQLite/JSONデータモデル
- `docs/testing/test-strategy.md` — テスト設計
- `docs/testing/evaluation-plan.md` — 辞書・検索改善の評価設計
- `docs/plans/implementation-plan.md` — TDD前提の実装計画
- `docs/reviews/contrarian-review-2026-04-30.md` — 実装前の反対意見レビュー
- `docs/adr/0001-python-only-local-first.md` — Python-only方針ADR

## 想定リポジトリ名

候補: `auto-manual-dictionary`

この資料ディレクトリは、ユーザーがGitリポジトリを作成したらそのまま `docs/` として移植できる。
