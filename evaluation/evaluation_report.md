# Evaluation Report

_Generated: 2026-06-20T10:12:02.190565_

## Summary

- **Winning strategy:** `m3_nemotron_ensemble` (weighted score 71.2%)
- **Rows evaluated:** 0 (sample_claims.csv)

## Strategy 1: `m3_only` (M3 does text + vision)

- Weighted score: **0.0%**
- Matched rows: 0

### Per-column accuracy
| Column | Accuracy |
|---|---|

### Claim status confusion matrix
_No data_


## Strategy 2: `m3_text_nemotron_vision` (M3 text + Nemotron Omni vision)

- Weighted score: **0.0%**
- Matched rows: 0

### Per-column accuracy
| Column | Accuracy |
|---|---|

### Claim status confusion matrix
_No data_


## Strategy 3: `m3_nemotron_ensemble` (M3 + Nemotron reconciled)

- Weighted score: **71.2%**
- Matched rows: 20

### Per-column accuracy
| Column | Accuracy |
|---|---|
| evidence_standard_met | 85.0% (17/20) |
| evidence_standard_met_reason | 0.0% (0/20) |
| risk_flags | 40.0% (8/20) |
| issue_type | 55.0% (11/20) |
| object_part | 80.0% (16/20) |
| claim_status | 70.0% (14/20) |
| claim_status_justification | 0.0% (0/20) |
| supporting_image_ids | 80.0% (16/20) |
| valid_image | 90.0% (18/20) |
| severity | 60.0% (12/20) |

### Claim status confusion matrix
| actual \ predicted | contradicted | not_enough_information | supported |
|---|---|---|---|
| **contradicted** | 1 | 1 | 3 |
| **not_enough_information** | 0 | 1 | 1 |
| **supported** | 0 | 1 | 12 |


## Operational Analysis

| Metric | Strategy 1 (m3_only) | Strategy 2 (m3_text+omni) | Strategy 3 (ensemble) |
|---|---|---|---|
| total_calls | 69 | 69 | 40 |
| cached_calls | 0 | 0 | 0 |
| errors | 0 | 0 | 0 |
| total_prompt_tokens | 89506 | 81568 | 19439 |
| total_completion_tokens | 14485 | 8847 | 6613 |
| total_tokens | 103991 | 90415 | 26052 |
| p50_latency_ms | 6288 | 2972 | 4947 |
| p95_latency_ms | 12298 | 10173 | 22667 |


### Models Used

- Strategy 1: {'MiniMax-M3': 69}
- Strategy 2: {'MiniMax-M3': 40, 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning': 29}
- Strategy 3: {'MiniMax-M3': 40}


### Node Distribution

- Strategy 1: {'parse': 20, 'vision': 29, 'adjudicate': 20}
- Strategy 2: {'parse': 20, 'vision': 29, 'adjudicate': 20}
- Strategy 3: {'parse': 20, 'adjudicate': 20}


## Cost & Quota Notes

- **Token Router (M3):** unlimited quota per user (confirmed). No per-call cost in this run.
- **NVIDIA NIM (Nemotron Omni):** free tier, ~40 RPM. We use Semaphore(1) + 1.6s sleep + tenacity retry.
- **Caching:** vision calls are cached by sha256(image) + model + prompt_version + vote round.
- **TPM awareness:** both providers return usage; we log it. NIM may have TPM caps in addition to RPM.


## Recommended Configuration for test set

Use **`m3_nemotron_ensemble`** for the final `output.csv` generation on `dataset/claims.csv`.
