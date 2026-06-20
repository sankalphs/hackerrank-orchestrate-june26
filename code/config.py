"""Central configuration: paths, model IDs, endpoints, rate limits."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

DATASET_DIR = REPO_ROOT / "dataset"
CLAIMS_CSV = DATASET_DIR / "claims.csv"
SAMPLE_CLAIMS_CSV = DATASET_DIR / "sample_claims.csv"
USER_HISTORY_CSV = DATASET_DIR / "user_history.csv"
EVIDENCE_REQUIREMENTS_CSV = DATASET_DIR / "evidence_requirements.csv"
IMAGES_DIR = DATASET_DIR / "images"

OUTPUT_CSV = REPO_ROOT / "output.csv"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CALL_LOG = CACHE_DIR / "call_log.jsonl"
VISION_CACHE = CACHE_DIR / "vision_cache.json"

TOKEN_ROUTER_API_KEY = os.getenv("TOKEN_ROUTER_API_KEY", "")
TOKEN_ROUTER_BASE_URL = os.getenv("TOKEN_ROUTER_BASE_URL", "https://api.tokenrouter.com/v1")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

TEXT_MODEL = "MiniMax-M3"
VISION_MODEL_STRATEGY1 = "MiniMax-M3"
VISION_MODEL_STRATEGY2 = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

VISION_TEMPERATURE = 0.2
TEXT_TEMPERATURE = 0.2
ADJUDICATION_TEMPERATURE = 0.3

VISION_MAX_TOKENS = 3000
TEXT_PARSE_MAX_TOKENS = 2000
ADJUDICATION_MAX_TOKENS = 800

NIM_VISION_RPM = 40
NIM_SLEEP_SECONDS = 1.6
NIM_SEMAPHORE = 1

STRATEGY1 = "m3_only"
STRATEGY2 = "m3_text_nemotron_vision"
STRATEGY3 = "m3_nemotron_ensemble"

PROMPT_VERSION = "v2"

VISION_VOTE_ROUNDS = 1
VISION_VOTE_TEMPERATURE = 0.4

HISTORY_RISK_90D_THRESHOLD = 3
HISTORY_REJECTED_THRESHOLD = 2
HISTORY_MANUAL_REVIEW_THRESHOLD = 2
