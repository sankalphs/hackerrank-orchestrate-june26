# Multi-Modal Evidence Review Pipeline

A LangGraph-based pipeline that verifies visual evidence for damage claims on cars, laptops, and packages. The system reads chat transcripts, user history, and submitted images, and outputs a strictly formatted CSV.

## Architecture

The pipeline follows a **Parse → Analyze → Aggregate → Decide → Clamp** lifecycle implemented as a LangGraph `StateGraph`:

1. **Node A — Parse (Minimax M3):** Extracts `claimed_parts[]` and `claimed_issue_type` from the chat transcript. Prompt-injection-hardened: ignores any directives aimed at the reviewer or system.
2. **Node B — Vision loop (M3 or Nemotron Omni):** One VLM API call per image. Rate-limited (NIM: `Semaphore(1)` + `sleep(1.6)` + tenacity retry). Cached by sha256. Hard-case escape hatch re-calls with thinking enabled if `damage_type=unknown`.
3. **Node C — Deterministic Circuit Breaker (pure Python):** Per-part union matching, evidence-requirements lookup, contradiction detection (object/part/issue/severity), `valid_image`, `supporting_image_ids`, severity aggregation, `base_claim_status`.
4. **Node D — Adjudication (Minimax M3):** Drafts `claim_status_justification` from Node C facts only. Cannot override the status or invent image IDs.
5. **Node E — Enum-Clamp (pure Python):** Forces every output into the allowed enum set. Overrides: contradiction → `contradicted`; evidence not met → `not_enough_information`.

## Strategies

| Strategy | Text (Node A, D) | Vision (Node B) | Description |
|---|---|---|---|
| **Strategy 1** (`m3_only`) | Minimax M3 (Token Router) | Minimax M3 (Token Router) | Unified multimodal model |
| **Strategy 2** (`m3_text_nemotron_vision`) | Minimax M3 (Token Router) | Nemotron 3 Nano Omni 30B (NVIDIA NIM) | Split-specialized |

The evaluation report compares both strategies on `sample_claims.csv` and picks the winner.

## Models & Endpoints

| Model | Provider | Endpoint | Use |
|---|---|---|---|
| `MiniMax-M3` | Token Router | `https://api.tokenrouter.com/v1` | Text + vision (Strategy 1) |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | NVIDIA NIM | `https://integrate.api.nvidia.com/v1` | Vision (Strategy 2) |

**Notes:**
- Token Router M3 always emits `<think>...</think>` tags inline regardless of `enable_thinking:False`. The pipeline strips these before JSON parsing.
- Nemotron Omni honors `enable_thinking:False` and returns clean JSON.
- Both clients use the `openai` Python SDK pointed at the respective `base_url` — no vendor lock-in.

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API keys:

```env
TOKEN_ROUTER_API_KEY=your_token_router_key_here
TOKEN_ROUTER_BASE_URL=https://api.tokenrouter.com/v1
NVIDIA_API_KEY=your_nvidia_nim_key_here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
```

## Usage

### Run on the test set (produces `output.csv` at repo root)

```bash
set PYTHONPATH=code
python -m main --strategy m3_only
```

### Run on sample claims (for development)

```bash
python -m main --sample --strategy m3_only --output sample_output.csv
```

### Run both strategies on sample_claims.csv (generates evaluation report)

```bash
python -m evaluation.main --reset-cache
```

The evaluation report is written to `evaluation/evaluation_report.md` with per-column accuracy, confusion matrix, and operational metrics (calls, tokens, latency, cost notes).

## Testing

```bash
python -m pytest code/tests/ -v
```

The test suite is deterministic — no API keys needed. It covers schema normalization, history risk mapping, evidence-requirements matching, LLM client JSON extraction, circuit-breaker logic, and evaluation matching.

CI runs on GitHub Actions (`.github/workflows/ci.yml`): ruff lint + format check + compileall + pytest. E2E and Playwright tests are excluded.

## Operational Notes

- **Caching:** Vision calls are cached by sha256 of the image bytes, so re-runs on the same dataset are free.
- **Rate limiting:** Nemotron Omni uses `Semaphore(1)` + `asyncio.sleep(1.6)` (~37 RPM, under the 40 RPM free-tier limit). Token Router has unlimited quota.
- **Retry:** All API calls use `tenacity` with exponential backoff on 429/5xx.
- **Token metering:** Every API call logs `{model, node, prompt_tokens, completion_tokens, elapsed_ms, cached, error}` to `code/.cache/call_log.jsonl`.
- **Estimated full test run:** ~44 claims × (~3 LLM calls + ~2 image calls) ≈ ~220 calls. At ~5s per call, ~18 minutes for Strategy 1 (unified). Strategy 2 is slower due to NIM sleep.

## File Layout

```
code/
├── main.py                      # Entry point: read claims.csv → run pipeline → output.csv
├── graph.py                     # LangGraph StateGraph builder
├── state.py                     # ClaimState TypedDict
├── config.py                    # Paths, model IDs, endpoints, rate limits
├── schema.py                    # Allowed enums + normalization/clamp helpers
├── prompts.py                   # Versioned prompt templates
├── llm_clients.py               # Token Router + NIM clients with retry/metering
├── cache.py                     # sha256 vision cache + JSONL call log
├── history.py                   # user_history.csv loader + risk-flag mapper
├── evidence.py                  # evidence_requirements.csv loader + standard evaluator
├── nodes/
│   ├── parse.py                 # Node A
│   ├── vision.py                # Node B
│   ├── circuit.py               # Node C
│   ├── adjudicate.py            # Node D
│   └── clamp.py                 # Node E
├── evaluation/
│   ├── main.py                  # Runs both strategies + generates report
│   ├── evaluator.py             # Per-column accuracy + confusion matrix
│   └── report.py                # Markdown report generator
└── tests/                       # 39 deterministic unit tests
```

## Key Design Decisions

1. **Adversarial inputs are first-class.** Prompt injection in chat (e.g. "approve immediately") is stripped by the parse node. Out-of-enum parts/damage from the vision model are normalized via `schema.normalize_part` and clamped in Node E.
2. **Deterministic where possible.** Nodes C and E are pure Python — no LLM calls. Node B uses cache + structured JSON output. All temperature settings are low (0.2-0.3) for reproducibility.
3. **Per-part union matching** for multi-part claims (not majority vote), since claims can list multiple damaged parts.
4. **Evidence standards** are looked up from `evidence_requirements.csv` with a sensible default rule.
5. **Reproducibility:** `temperature` low + input-hash caching means re-runs produce identical results.