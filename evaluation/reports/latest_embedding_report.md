# CrisisAgent Embedding Retrieval Evaluation

- Total cases: 3

## Model Summary

| Model | Recall@K | MRR | Average Target Rank |
| --- | ---: | ---: | ---: |
| hash | 1.0 | 1.0 | 1.0 |

## Case Details

### hash

- Case: `embedding_food_safety_001`
- Query: 食品企业使用过期原料，监管介入调查
- Expected sources: `food_safety.md`
- Retrieved sources: `food_safety.md, food_safety.md, legal_risk_rules.md`
- Recall@K: `1.0`
- Reciprocal rank: `1.0`
- Target rank: `1`

- Case: `embedding_legal_risk_001`
- Query: 危机声明需要避免提前定责和绝对化承诺
- Expected sources: `legal_risk_rules.md`
- Retrieved sources: `legal_risk_rules.md, crisis_response.md, legal_risk_rules.md`
- Recall@K: `1.0`
- Reciprocal rank: `1.0`
- Target rank: `1`

- Case: `embedding_crisis_response_001`
- Query: 企业初次回应要表达公众担忧并持续同步进展
- Expected sources: `crisis_response.md`
- Retrieved sources: `crisis_response.md, legal_risk_rules.md, food_safety.md`
- Recall@K: `1.0`
- Reciprocal rank: `1.0`
- Target rank: `1`
