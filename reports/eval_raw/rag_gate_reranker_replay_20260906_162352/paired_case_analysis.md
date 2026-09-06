# Gate and Reranker Replay Paired Analysis

## Scope

This artifact analyzes the replay results already saved in this directory. It does not rerun models, retrieval, evaluators, threshold sweeps, or knowledge-base changes.

- Replay commit: `247ffef`
- Gate dataset: `evaluation/rag_gate_challenge_v3.json`
- Retrieval dataset: `evaluation/rag_retrieval_holdout_v1.json`
- Nature: regression replay on previously used frozen datasets; not a new first holdout
- Direct evidence files:
  - `gate_challenge_v3_cases.jsonl`
  - `reranker_holdout_v1_cases.jsonl`
  - `summary.json`

## Paired Reranker Result Statistics

The 60 reranker rows are paired by `case_id`, with one `old` row and one `reranker_v2` row for each of the 30 retrieval holdout cases.

| Pair category | Count |
|---|---:|
| Both old and v2 hit Recall@3 | 26 |
| Old missed, v2 hit | 1 |
| Old hit, v2 missed | 1 |
| Both old and v2 missed | 2 |

This reconciles with the reported aggregate Recall@3:

- Old Reranker: `27 / 30 = 0.90`
- Reranker v2: `27 / 30 = 0.90`

Context pollution is computed per case on deduped source documents, then macro-averaged across 30 cases.

| Pollution change | Count |
|---|---:|
| Improved | 9 |
| Unchanged | 20 |
| Worsened | 1 |

This reconciles with the reported aggregate pollution rate:

- Old Reranker: `0.4722`
- Reranker v2: `0.3222`
- Relative reduction: `(0.4722 - 0.3222) / 0.4722 = 0.3177`

## Improvement Case

Case: `retrieval_holdout_v1_food_safety_001`

Category: `food_safety`

Event: 连锁甜品店的新款奶油蛋糕在周末售出后，多名顾客反馈腹痛和呕吐，门店正在整理批次记录、冷链温度和对外回应口径。

Acceptable source: `food_safety.md`

| Variant | Ranked sources | Scores | Rerank scores | Recall@3 | Pollution numerator / denominator | Pollution |
|---|---|---|---|---:|---|---:|
| Old | `food_safety.md`, `product_quality.md`, `executive_misconduct.md` | `0.3801`, `0.3646`, `0.3700` | `0.1900`, `0.1883`, `0.1850` | `1.0` | `2 / 3` | `0.6667` |
| Reranker v2 | `food_safety.md` | `0.3801` | `0.2374` | `1.0` | `0 / 1` | `0.0` |

What can be directly confirmed:

- Both versions found the acceptable source in Top3.
- Reranker v2 removed the two wrong-category sources from the final deduped source list.
- Pollution improved from `0.6667` to `0.0` for this case.

Interpretation:

Reranker v2 improved context precision here without hurting Recall@3. The confirmed mechanism is the final ranking/filtering outcome. The broader explanation is consistent with domain-aware reranking, but a causal claim about one specific signal would require an additional single-variable ablation.

## Regression Case

Case: `retrieval_holdout_v1_product_quality_004`

Category: `product_quality`

Event: 某批次婴儿推车在使用中出现刹车失灵反馈，门店要求总部给出检查流程、维修指引和家长沟通话术。

Acceptable source: `product_quality.md`

| Variant | Ranked sources | Scores | Rerank scores | Recall@3 | Pollution numerator / denominator | Pollution |
|---|---|---|---|---:|---|---:|
| Old | `product_quality.md`, `executive_misconduct.md`, `food_safety.md` | `0.4048`, `0.3957`, `0.3896` | `0.2095`, `0.2014`, `0.1948` | `1.0` | `2 / 3` | `0.6667` |
| Reranker v2 | `food_safety.md` | `0.3896` | `0.2420` | `0.0` | `1 / 1` | `1.0` |

What can be directly confirmed:

- Old Reranker hit `product_quality.md` at rank 1.
- Reranker v2 returned only `food_safety.md`, so this became a Top3 miss.
- The case-level pollution worsened from `0.6667` to `1.0`.
- This is the only old-hit/v2-miss case in the 30-case holdout replay.

What is not proven by the replay alone:

- The replay alone does not prove which exact keyword or domain signal caused the regression.
- The reranker code includes domain inference, source hints, keyword overlap, and domain adjustment. The observed result is compatible with a domain-signal interaction, but confirming the exact cause needs a targeted ablation or trace-level contribution comparison.

## Interview Explanation

I was solving a specific retrieval quality problem: the system could usually retrieve the correct legal source, but the final Top-K context still mixed in wrong crisis domains. That is risky for a Legal Agent because noisy context can make the legal review less focused or less faithful.

I chose domain-aware rule-based reranking because the issue was not pure recall. BGE and hybrid retrieval already found many relevant sources; the bigger problem was cross-domain pollution. A lightweight reranker was easier to explain, deterministic, offline-testable, and safer than adding a Cross Encoder or another LLM call.

The frozen retrieval holdout replay shows the trade-off clearly. Recall@3 stayed at `27/30 = 0.90`, while average source-document pollution dropped from `0.4722` to `0.3222`, a `31.77%` relative reduction. At the same time, there was one real regression: the product-quality stroller brake case was pushed to `food_safety.md`. I would not hide that in an interview; I would explain it as the kind of bad case that should enter the next evaluation loop.

The metric definition is source-document level. For each query, I dedupe the returned sources, classify each as acceptable, neutral, or forbidden, calculate case-level Recall@3 and pollution, then average across the 30 cases. Because each case has one acceptable source, Recall@3 is equivalent to `number of cases where the acceptable source appears in Top3 / 30`.

Next, I would not tune on this holdout and then claim a new validation result. These datasets have already been inspected, so they are now regression evidence. If I change the reranker based on these cases, I need a new untouched validation set to prove generalization.
