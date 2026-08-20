# RAG Bad Cases Report

This report tracks retrieval failures and suggested knowledge-base updates. It does not call a real LLM.

## Summary

- total_bad_cases: 8
- by_failure_type: {'wrong_source': 5, 'insufficient_evidence': 1, 'low_score': 1, 'disabled_document_hit': 1}
- by_root_cause: {'embedding_issue': 1, 'knowledge_gap': 5, 'metadata_filter_issue': 2}
- by_status: {'open': 7, 'fixed': 1}

## Suggested Knowledge Updates

- `service_outage`: 补充 service_outage 文档中“故障”同义表达、重复扣费和订单核对证据，降低关键词缺失。
- `false_advertising`: 新增 false_advertising 知识文档，覆盖宣传口径核查、证明材料、下架/更正和公开说明。
- `labor_dispute`: 新增 labor_dispute 知识文档，覆盖员工沟通、考勤薪酬核查、依法处理和媒体回应。
- `product_recall`: 补充 product_recall 专项知识，区分普通质量问题与召回流程、批次范围和用户通知。
- `financial_rumor`: 新增 financial_rumor 知识文档，覆盖传闻核实、经营信息边界、合作方沟通和公开澄清。

## Open Cases

### rag_bad_data_privacy_001

- linked_test_case: rag_eval_data_privacy_001
- expected_source_category: data_privacy
- actual_source_category: crisis_response
- failure_type: wrong_source
- root_cause: embedding_issue
- suggested_fix: 补充数据隐私知识 chunk 的用户通知、访问日志、影响范围排查表达，并在后续 retrieval evaluation 中验证 data_privacy top3 命中。

### rag_bad_service_outage_001

- linked_test_case: rag_eval_service_outage_001
- expected_source_category: service_outage
- actual_source_category: service_outage
- failure_type: insufficient_evidence
- root_cause: knowledge_gap
- suggested_fix: 补充 service_outage 文档中“故障”同义表达、重复扣费和订单核对证据，降低关键词缺失。

### rag_bad_false_advertising_001

- linked_test_case: rag_eval_false_advertising_001
- expected_source_category: false_advertising
- actual_source_category: crisis_response
- failure_type: wrong_source
- root_cause: knowledge_gap
- suggested_fix: 新增 false_advertising 知识文档，覆盖宣传口径核查、证明材料、下架/更正和公开说明。

### rag_bad_labor_dispute_001

- linked_test_case: rag_eval_labor_dispute_001
- expected_source_category: labor_dispute
- actual_source_category: crisis_response
- failure_type: wrong_source
- root_cause: knowledge_gap
- suggested_fix: 新增 labor_dispute 知识文档，覆盖员工沟通、考勤薪酬核查、依法处理和媒体回应。

### rag_bad_product_recall_001

- linked_test_case: rag_eval_product_recall_001
- expected_source_category: product_recall
- actual_source_category: product_quality
- failure_type: wrong_source
- root_cause: knowledge_gap
- suggested_fix: 补充 product_recall 专项知识，区分普通质量问题与召回流程、批次范围和用户通知。

### rag_bad_financial_rumor_001

- linked_test_case: rag_eval_financial_rumor_001
- expected_source_category: financial_rumor
- actual_source_category: crisis_response
- failure_type: wrong_source
- root_cause: knowledge_gap
- suggested_fix: 新增 financial_rumor 知识文档，覆盖传闻核实、经营信息边界、合作方沟通和公开澄清。

### rag_bad_executive_scandal_001

- linked_test_case: rag_eval_executive_scandal_001
- expected_source_category: executive_scandal
- actual_source_category: executive_misconduct
- failure_type: low_score
- root_cause: metadata_filter_issue
- suggested_fix: 统一 executive_scandal 与 executive_misconduct 的 category alias 或在评测 gold label 中显式声明等价类别。
