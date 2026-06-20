# Evaluation Report

_Generated: 2026-06-20T10:56:24.911202_

## Summary

- **Winning strategy:** `m3_nemotron_ensemble` (weighted score 73.8%)
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

- Weighted score: **73.8%**
- Matched rows: 20

### Per-column accuracy
| Column | Accuracy |
|---|---|
| evidence_standard_met | 90.0% (18/20) |
| evidence_standard_met_reason | 0.0% (0/20) |
| risk_flags | 60.0% (12/20) |
| issue_type | 55.0% (11/20) |
| object_part | 80.0% (16/20) |
| claim_status | 75.0% (15/20) |
| claim_status_justification | 0.0% (0/20) |
| supporting_image_ids | 80.0% (16/20) |
| valid_image | 90.0% (18/20) |
| severity | 60.0% (12/20) |

### Claim status confusion matrix
| actual \ predicted | contradicted | not_enough_information | supported |
|---|---|---|---|
| **contradicted** | 1 | 1 | 3 |
| **not_enough_information** | 0 | 1 | 1 |
| **supported** | 0 | 0 | 13 |


## Operational Analysis

| Metric | Strategy 1 (m3_only) | Strategy 2 (m3_text+omni) | Strategy 3 (ensemble) |
|---|---|---|---|
| total_calls | 149 | 109 | 273 |
| cached_calls | 58 | 29 | 0 |
| errors | 0 | 0 | 0 |
| total_prompt_tokens | 128421 | 100968 | 131866 |
| total_completion_tokens | 26517 | 14437 | 42735 |
| total_tokens | 154938 | 115405 | 174601 |
| p50_latency_ms | 5692 | 4068 | 4947 |
| p95_latency_ms | 12302 | 10991 | 15761 |


### Models Used

- Strategy 1: {'MiniMax-M3': 207}
- Strategy 2: {'MiniMax-M3': 80, 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning': 58}
- Strategy 3: {'MiniMax-M3': 273}


### Node Distribution

- Strategy 1: {'parse': 60, 'vision': 87, 'adjudicate': 60}
- Strategy 2: {'parse': 40, 'vision': 58, 'adjudicate': 40}
- Strategy 3: {'parse': 137, 'adjudicate': 136}


## Cost & Quota Notes

- **Token Router (M3):** unlimited quota per user (confirmed). No per-call cost in this run.
- **NVIDIA NIM (Nemotron Omni):** free tier, ~40 RPM. We use Semaphore(1) + 1.6s sleep + tenacity retry.
- **Caching:** vision calls are cached by sha256(image) + model + prompt_version + vote round.
- **TPM awareness:** both providers return usage; we log it. NIM may have TPM caps in addition to RPM.


## Recommended Configuration for test set

Use **`m3_nemotron_ensemble`** for the final `output.csv` generation on `dataset/claims.csv`.
