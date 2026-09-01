# RAG Regression Report

This report compares the current Legal RAG retrieval metrics against the fixed project baseline.
It is an offline regression check and does not call a real LLM.

## Summary

- generated_at: 2026-09-01T09:04:48.225739+00:00
- total_cases: 8
- baseline_available: True
- regression_passed: True
- failed_case_count: 7

## Current Metrics

- total_cases: 8
- top1_source_hit_rate: 0.25
- top3_source_hit_rate: 0.25
- keyword_hit_rate: 0.125
- fallback_rate: 0.0
- average_score: 0.3119
- average_rerank_score: 0.2135
- context_pollution_rate: 0.7143
- backend_distribution: {'markdown': 5, 'json_vector': 14}
- failed_cases: ['rag_eval_data_privacy_001', 'rag_eval_service_outage_001', 'rag_eval_false_advertising_001', 'rag_eval_labor_dispute_001', 'rag_eval_product_recall_001', 'rag_eval_financial_rumor_001', 'rag_eval_executive_scandal_001']

## Baseline Metrics

- total_cases: 8
- top1_source_hit_rate: 0.25
- top3_source_hit_rate: 0.25
- keyword_hit_rate: 0.125
- fallback_rate: 0.0
- average_score: 0.3119
- average_rerank_score: 0.2135
- context_pollution_rate: 0.7143
- backend_distribution: {'markdown': 5, 'json_vector': 14}
- generated_at: 2026-09-01T00:00:00+08:00
- notes: Small project-owned fixed evaluation set for Legal RAG regression checks. Metrics are used to detect regressions after knowledge base, query rewrite, chunking, reranker, or retriever changes. They are not a public benchmark and do not represent production online performance.

## Regression Checks

- top3_source_hit_rate: passed (current=0.25, baseline=0.25, limit=0.15, reason=)
- fallback_rate: passed (current=0.0, baseline=0.0, limit=0.1, reason=)
- context_pollution_rate: passed (current=0.7143, baseline=0.7143, limit=0.8643, reason=)

## Failed Cases

### rag_eval_data_privacy_001

- expected_source_category: data_privacy
- actual_source_categories: ['crisis_response', 'crisis_response', 'crisis_response']
- failure_reason: expected_source_category_not_in_top3
- possible_causes: ['source_category_mismatch', 'rerank_issue', 'knowledge_gap']

### rag_eval_service_outage_001

- expected_source_category: service_outage
- actual_source_categories: ['service_outage', 'service_outage', 'service_outage']
- failure_reason: expected_keywords_missing
- possible_causes: ['chunk_issue', 'knowledge_gap']

### rag_eval_false_advertising_001

- expected_source_category: false_advertising
- actual_source_categories: ['crisis_response', 'service_outage', 'crisis_response']
- failure_reason: expected_source_category_not_in_top3
- possible_causes: ['source_category_mismatch', 'rerank_issue', 'knowledge_gap']

### rag_eval_labor_dispute_001

- expected_source_category: labor_dispute
- actual_source_categories: []
- failure_reason: no_retrieval_result
- possible_causes: ['knowledge_gap', 'query_rewrite_issue', 'low_score']

### rag_eval_product_recall_001

- expected_source_category: product_recall
- actual_source_categories: ['product_quality', 'food_safety']
- failure_reason: expected_source_category_not_in_top3
- possible_causes: ['source_category_mismatch', 'rerank_issue', 'knowledge_gap']

### rag_eval_financial_rumor_001

- expected_source_category: financial_rumor
- actual_source_categories: ['data_privacy', 'data_privacy']
- failure_reason: expected_source_category_not_in_top3
- possible_causes: ['source_category_mismatch', 'rerank_issue', 'knowledge_gap']

### rag_eval_executive_scandal_001

- expected_source_category: executive_scandal
- actual_source_categories: ['crisis_response', 'executive_misconduct', 'executive_misconduct']
- failure_reason: expected_source_category_not_in_top3
- possible_causes: ['source_category_mismatch', 'rerank_issue', 'knowledge_gap']
