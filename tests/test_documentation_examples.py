import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_contains_complete_cli_quickstart_and_safety_policy():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    expected_snippets = [
        "python -m auto_manual_dict ingest --lang ja",
        "python -m auto_manual_dict ingest --lang en",
        "python -m auto_manual_dict match-pages",
        "python -m auto_manual_dict match-blocks",
        "python -m auto_manual_dict extract-terms",
        "python -m auto_manual_dict build-concepts",
        "python -m auto_manual_dict update-confidence",
        "python -m auto_manual_dict export-review",
        "python -m auto_manual_dict approve",
        "python -m auto_manual_dict export-dictionary",
        "confirmed",
        "safe_for_query_expansion",
        "safe_for_answer_generation",
    ]
    for snippet in expected_snippets:
        assert snippet in readme


def test_examples_include_valid_sample_review_csv_and_dictionary_jsonl():
    examples_readme = ROOT / "examples" / "README.md"
    sample_review = ROOT / "examples" / "sample_review.csv"
    sample_dictionary = ROOT / "examples" / "sample_dictionary.jsonl"

    assert examples_readme.exists()
    assert sample_review.exists()
    assert sample_dictionary.exists()

    rows = list(csv.DictReader(sample_review.open(encoding="utf-8")))
    assert rows
    review_row = rows[0]
    expected_review_columns = {
        "concept_id", "category", "confidence", "confidence_json", "status",
        "ja_terms", "en_terms", "evidence_count", "evidence_ids", "evidence_summary",
        "sample_ja_context", "sample_en_context", "recommended_action", "row_version", "export_batch_id",
    }
    assert expected_review_columns <= set(review_row)
    assert review_row["status"] == "review_ready"
    assert "始動不良" in review_row["ja_terms"]
    assert "engine" in review_row["en_terms"].lower()

    dictionary_lines = [json.loads(line) for line in sample_dictionary.read_text(encoding="utf-8").splitlines()]
    assert dictionary_lines
    dictionary_row = dictionary_lines[0]
    assert dictionary_row["status"] == "confirmed"
    assert dictionary_row["concept_id"] == review_row["concept_id"]
    assert dictionary_row["ja_terms"]
    assert dictionary_row["en_terms"]
