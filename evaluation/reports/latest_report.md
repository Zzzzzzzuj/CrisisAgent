# CrisisAgent Evaluation Report

## Summary

- Total cases: 6
- Risk accuracy: 0.8333
- Emotion accuracy: 0.8333
- Tone accuracy: 1.0
- Fallback rate: 1.0
- Average duration: 10536.17 ms

## Agent Metrics

| Agent | Name | Avg Duration (ms) | Fallback Count | Fallback Rate | Total Runs |
| --- | --- | ---: | ---: | ---: | ---: |
| Agent A | 舆情分析 Agent | 2135.83 | 6 | 1.0 | 6 |
| Agent C | 策略文案 Agent（第一版） | 1049.75 | 6 | 0.5 | 12 |
| Agent D | 红队攻击 Agent | 2098.0 | 6 | 1.0 | 6 |
| Agent B | 合规审查 Agent | 2095.33 | 6 | 1.0 | 6 |
| Agent E | 最终决策 Agent | 2105.33 | 6 | 1.0 | 6 |

## Category Metrics

| Category | Total Cases | Risk Accuracy | Emotion Accuracy | Tone Accuracy | Fallback Rate | Avg Duration (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| food_safety | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10808.0 |
| service_outage | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10534.0 |
| data_security | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10463.0 |
| brand_reputation | 1 | 1.0 | 0.0 | 1.0 | 1.0 | 10480.0 |
| product_quality | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 10443.0 |
| executive_misconduct | 1 | 0.0 | 1.0 | 1.0 | 1.0 | 10489.0 |

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
- Result: PASS
- Fallback: `True`
- Trace duration: `10808 ms`
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
- Result: PASS
- Fallback: `True`
- Trace duration: `10534 ms`
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
- Result: PASS
- Fallback: `True`
- Trace duration: `10463 ms`
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
- Result: FAIL
- Fallback: `True`
- Trace duration: `10480 ms`
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
- Result: PASS
- Fallback: `True`
- Trace duration: `10443 ms`
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
- Result: FAIL
- Fallback: `True`
- Trace duration: `10489 ms`
- Final scores: `{"legal_safety": 8, "empathy": 8, "robustness": 7}`
