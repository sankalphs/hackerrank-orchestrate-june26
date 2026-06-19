# Evaluation Report

_Generated: 2026-06-20T00:29:22.377676_

## Summary

- **Winning strategy:** `m3_only` (weighted score 71.7%)
- **Rows evaluated:** 20 (sample_claims.csv)

## Strategy 1: `m3_only` (M3 does text + vision)

- Weighted score: **71.7%**
- Matched rows: 20

### Per-column accuracy (Jaccard >= 0.5 for set fields)
| Column | Accuracy |
|---|---|
| evidence_standard_met | 90.0% (18/20) |
| evidence_standard_met_reason | 0.0% (0/20) |
| risk_flags | 60.0% (12/20) |
| issue_type | 55.0% (11/20) |
| object_part | 85.0% (17/20) |
| claim_status | 70.0% (14/20) |
| claim_status_justification | 0.0% (0/20) |
| supporting_image_ids | 80.0% (16/20) |
| valid_image | 90.0% (18/20) |
| severity | 55.0% (11/20) |

### Set-field exact-match accuracy (reference)
| Column | Exact match |
|---|---|
| supporting_image_ids | 70.0% |
| risk_flags | 40.0% |

### Claim status confusion matrix
| actual \ predicted | contradicted | not_enough_information | supported |
|---|---|---|---|
| **contradicted** | 3 | 0 | 2 |
| **not_enough_information** | 2 | 0 | 0 |
| **supported** | 1 | 1 | 11 |


## Strategy 2: `m3_text_nemotron_vision` (M3 text + Nemotron Omni vision)

- Weighted score: **69.3%**
- Matched rows: 20

### Per-column accuracy (Jaccard >= 0.5 for set fields)
| Column | Accuracy |
|---|---|
| evidence_standard_met | 90.0% (18/20) |
| evidence_standard_met_reason | 0.0% (0/20) |
| risk_flags | 55.0% (11/20) |
| issue_type | 55.0% (11/20) |
| object_part | 85.0% (17/20) |
| claim_status | 65.0% (13/20) |
| claim_status_justification | 0.0% (0/20) |
| supporting_image_ids | 80.0% (16/20) |
| valid_image | 90.0% (18/20) |
| severity | 55.0% (11/20) |

### Set-field exact-match accuracy (reference)
| Column | Exact match |
|---|---|
| supporting_image_ids | 70.0% |
| risk_flags | 35.0% |

### Claim status confusion matrix
| actual \ predicted | contradicted | not_enough_information | supported |
|---|---|---|---|
| **contradicted** | 3 | 0 | 2 |
| **not_enough_information** | 2 | 0 | 0 |
| **supported** | 2 | 1 | 10 |


## Operational Analysis

| Metric | Strategy 1 (m3_only) | Strategy 2 (m3_text+omni) |
|---|---|---|
| Total API calls | 69 | 40 |
| Cached calls | 0 | 29 |
| Errors | 0 | 0 |
| Prompt tokens | 80,340 | 19,540 |
| Completion tokens | 15,795 | 5,707 |
| Total tokens | 96,135 | 25,247 |
| p50 latency (ms) | 5607 | 5100 |
| p95 latency (ms) | 17915 | 26054 |


### Models Used

- Strategy 1: {'MiniMax-M3': 69}
- Strategy 2: {'MiniMax-M3': 40, 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning': 29}


### Node Distribution

- Strategy 1: {'parse': 20, 'vision': 29, 'adjudicate': 20}
- Strategy 2: {'parse': 20, 'vision': 29, 'adjudicate': 20}


## Cost & Quota Notes

- **Token Router (M3):** unlimited quota per user (confirmed). No per-call cost in this run.
- **NVIDIA NIM (Nemotron Omni):** free tier, ~40 RPM. We use Semaphore(1) + 1.6s sleep + tenacity retry.
- **Caching:** vision calls are cached by sha256(image) so re-runs hit the cache for free.
- **TPM awareness:** both providers return usage; we log it. NIM may have TPM caps in addition to RPM.


## Recommended Configuration for test set

Use **`m3_only`** for the final `output.csv` generation on `dataset/claims.csv`.
