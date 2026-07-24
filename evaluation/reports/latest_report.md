# CrisisAgent Evaluation Report

## Summary

- Total cases: 6
- Risk accuracy: 0.8333
- Emotion accuracy: 0.8333
- Tone accuracy: 1.0
- Fallback rate: 1.0
- Average duration: 10403.5 ms
- RAG hit rate: 1.0
- Recall@K: 0.9167
- MRR: 0.9167
- Average rerank gain: 0.17
- Average retrieved sources: 2.83

## RAG Evaluation

| Metric | Value |
| --- | ---: |
| RAG Hit Rate | 1.0 |
| Recall@K | 0.9167 |
| MRR | 0.9167 |
| Average Rerank Gain | 0.17 |
| Average Retrieved Sources | 2.83 |

## RAG Source Distribution

| Source | Count |
| --- | ---: |
| crisis_response.md | 6 |
| food_safety.md | 6 |
| legal_risk_rules.md | 5 |

## Agent Metrics

| Agent | Name | Avg Duration (ms) | Fallback Count | Fallback Rate | Total Runs |
| --- | --- | ---: | ---: | ---: | ---: |
| Agent A | 舆情分析 Agent | 2092.83 | 6 | 1.0 | 6 |
| Agent C | 策略文案 Agent（第一版） | 1038.42 | 6 | 0.5 | 12 |
| Agent D | 红队攻击 Agent | 2074.33 | 6 | 1.0 | 6 |
| Agent B | 合规审查 Agent | 2078.5 | 6 | 1.0 | 6 |
| Agent E | 最终决策 Agent | 2078.0 | 6 | 1.0 | 6 |

## Category Metrics

| Category | Total Cases | Risk Accuracy | Emotion Accuracy | Tone Accuracy | Fallback Rate | Avg Duration (ms) | RAG Hit Rate | Recall@K | MRR | Avg Rerank Gain | Avg Sources |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| food_safety | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10504.0 | 1.0 | 1.0 | 1.0 | 0.0 | 3.0 |
| service_outage | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10359.0 | 1.0 | 1.0 | 1.0 | 1.0 | 3.0 |
| data_security | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10378.0 | 1.0 | 1.0 | 1.0 | 0.0 | 3.0 |
| brand_reputation | 1 | 1.0 | 0.0 | 1.0 | 1.0 | 10425.0 | 1.0 | 1.0 | 0.5 | 0.0 | 3.0 |
| product_quality | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10377.0 | 1.0 | 0.5 | 1.0 | 0.0 | 2.0 |
| executive_misconduct | 1 | 0.0 | 1.0 | 1.0 | 1.0 | 10378.0 | 1.0 | 1.0 | 1.0 | 0.0 | 3.0 |

## Case Details

### food-safety-001

- Category: `food_safety`
- Tags: `食品安全, 视频曝光, 监管风险`
- Event: 某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。
- Expected risk: `high`
- Actual risk: `high`
- Expected emotion: `angry`
- Actual emotion: `angry`
- Expected tone: `先共情、再回应行动、避免抢先定性`
- Actual tone: `先共情、再回应行动、避免抢先定性`
- Expected sources: `food_safety.md, legal_risk_rules.md`
- RAG hit: `True`
- Retrieval type: `hybrid`
- RAG sources: `food_safety.md, crisis_response.md, legal_risk_rules.md`
- Recall@K: `1.0`
- Reciprocal rank: `1.0`
- Rerank before rank: `1`
- Rerank after rank: `1`
- Rerank gain: `0`
- Result: PASS
- Fallback: `True`
- Trace duration: `10504 ms`
- Final scores: `{"legal_safety": 8, "empathy": 8, "robustness": 8}`

### service-outage-001

- Category: `service_outage`
- Tags: `服务中断, 投诉, 大促`
- Event: 某在线教育平台在大促当晚大面积宕机，付费用户无法上课并集中投诉，舆论持续发酵。
- Expected risk: `medium`
- Actual risk: `medium`
- Expected emotion: `worried`
- Actual emotion: `worried`
- Expected tone: `先共情、再回应行动、避免抢先定性`
- Actual tone: `先共情、再回应行动、避免抢先定性`
- Expected sources: `crisis_response.md`
- RAG hit: `True`
- Retrieval type: `hybrid`
- RAG sources: `crisis_response.md, food_safety.md, legal_risk_rules.md`
- Recall@K: `1.0`
- Reciprocal rank: `1.0`
- Rerank before rank: `2`
- Rerank after rank: `1`
- Rerank gain: `1`
- Result: PASS
- Fallback: `True`
- Trace duration: `10359 ms`
- Final scores: `{"legal_safety": 8, "empathy": 8, "robustness": 7}`

### data-leak-001

- Category: `data_security`
- Tags: `数据泄露, 隐私, 信任危机`
- Event: 某互联网平台被曝光疑似发生用户数据泄露，大量网友质疑平台安全能力并要求解释。
- Expected risk: `high`
- Actual risk: `high`
- Expected emotion: `angry`
- Actual emotion: `angry`
- Expected tone: `先共情、再回应行动、避免抢先定性`
- Actual tone: `先共情、再回应行动、避免抢先定性`
- Expected sources: `legal_risk_rules.md, crisis_response.md`
- RAG hit: `True`
- Retrieval type: `hybrid`
- RAG sources: `crisis_response.md, food_safety.md, legal_risk_rules.md`
- Recall@K: `1.0`
- Reciprocal rank: `1.0`
- Rerank before rank: `1`
- Rerank after rank: `1`
- Rerank gain: `0`
- Result: PASS
- Fallback: `True`
- Trace duration: `10378 ms`
- Final scores: `{"legal_safety": 8, "empathy": 8, "robustness": 8}`

### charity-positive-001

- Category: `brand_reputation`
- Tags: `公益, 捐赠, 正向舆情`
- Event: 某品牌在灾后第一时间发布救援计划并追加捐赠，公众评价整体正面。
- Expected risk: `medium`
- Actual risk: `medium`
- Expected emotion: `positive`
- Actual emotion: `worried`
- Expected tone: `先共情、再回应行动、避免抢先定性`
- Actual tone: `先共情、再回应行动、避免抢先定性`
- Expected sources: `crisis_response.md`
- RAG hit: `True`
- Retrieval type: `hybrid`
- RAG sources: `food_safety.md, crisis_response.md, legal_risk_rules.md`
- Recall@K: `1.0`
- Reciprocal rank: `0.5`
- Rerank before rank: `2`
- Rerank after rank: `2`
- Rerank gain: `0`
- Result: FAIL
- Fallback: `True`
- Trace duration: `10425 ms`
- Final scores: `{"legal_safety": 8, "empathy": 8, "robustness": 7}`

### product-quality-001

- Category: `product_quality`
- Tags: `产品质量, 电池安全, 维权`
- Event: 某消费电子品牌新机发布后频繁出现电池鼓包投诉，多个社交平台出现维权帖。
- Expected risk: `medium`
- Actual risk: `medium`
- Expected emotion: `worried`
- Actual emotion: `worried`
- Expected tone: `先共情、再回应行动、避免抢先定性`
- Actual tone: `先共情、再回应行动、避免抢先定性`
- Expected sources: `legal_risk_rules.md, crisis_response.md`
- RAG hit: `True`
- Retrieval type: `hybrid`
- RAG sources: `crisis_response.md, food_safety.md`
- Recall@K: `0.5`
- Reciprocal rank: `1.0`
- Rerank before rank: `1`
- Rerank after rank: `1`
- Rerank gain: `0`
- Result: PASS
- Fallback: `True`
- Trace duration: `10377 ms`
- Final scores: `{"legal_safety": 8, "empathy": 8, "robustness": 7}`

### executive-misconduct-001

- Category: `executive_misconduct`
- Tags: `高管失言, 抵制, 品牌道歉`
- Event: 某上市公司高管被曝在公开场合发表不当言论，引发网友抵制并要求品牌致歉。
- Expected risk: `high`
- Actual risk: `medium`
- Expected emotion: `angry`
- Actual emotion: `angry`
- Expected tone: `先共情、再回应行动、避免抢先定性`
- Actual tone: `先共情、再回应行动、避免抢先定性`
- Expected sources: `crisis_response.md`
- RAG hit: `True`
- Retrieval type: `hybrid`
- RAG sources: `crisis_response.md, food_safety.md, legal_risk_rules.md`
- Recall@K: `1.0`
- Reciprocal rank: `1.0`
- Rerank before rank: `1`
- Rerank after rank: `1`
- Rerank gain: `0`
- Result: FAIL
- Fallback: `True`
- Trace duration: `10378 ms`
- Final scores: `{"legal_safety": 8, "empathy": 8, "robustness": 7}`
