# サンプル review_ready CSV

実際のCSV列例。

```csv
concept_id,category,confidence,status,ja_terms,en_terms,evidence_count,evidence_types,sample_ja_context,sample_en_context,recommended_action
SYMPTOM_ENGINE_NO_START,symptom,0.86,review_ready,"始動不良;エンジンがかからない","engine does not start;no start",12,"paragraph_alignment;dtc_anchor;neighbor_terms","エンジン始動不良時は燃圧を点検する。","When the engine does not start, inspect the fuel pressure.",inspect
SPEC_TIGHTENING_TORQUE,specification,0.93,review_ready,"締付トルク","tightening torque",18,"table_anchor;unit_anchor;heading_similarity","規定の締付トルクで締め付ける。","Tighten to the specified tightening torque.",approve
```
