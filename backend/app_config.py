"""Central application configuration read from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "#tech-debt")

JIRA_SERVER = os.getenv("JIRA_SERVER", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "TD")

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_OAUTH_CALLBACK_URL = os.getenv("GITHUB_OAUTH_CALLBACK_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
# ---------------------------------------------------------------------------
# LLM provider / model settings (single source of truth; all env-overridable)
# ---------------------------------------------------------------------------
# Groq retired llama-3.3-70b-versatile (404 model_not_found as of 2026-10).
# openai/gpt-oss-120b was verified served via GET /openai/v1/models.
DEFAULT_GROQ_MODEL_ID = "openai/gpt-oss-120b"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia_nim")
GROQ_MODEL_ID = os.getenv("GROQ_MODEL_ID", DEFAULT_GROQ_MODEL_ID)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:latest")
NIM_MODEL_ID = os.getenv("NIM_MODEL_ID", "nvidia/nemotron-3.5-super-vl-120b-a12b")
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")
HF_LOCAL_MODEL_ID = os.getenv("HF_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")
OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini")
LLM_HEALTH_TIMEOUT_SECONDS = float(os.getenv("LLM_HEALTH_TIMEOUT_SECONDS", "10"))

# ---------------------------------------------------------------------------
# Multi-provider LLM pool (see agents/llm_pool.py)
# ---------------------------------------------------------------------------
OPENROUTER_MODEL_ID = os.getenv("OPENROUTER_MODEL_ID", "google/gemma-4-31b-it:free")
# Comma-separated pool order; providers without an API key are skipped.
LLM_POOL_PROVIDERS = os.getenv("LLM_POOL_PROVIDERS", "nvidia_nim,groq,openrouter")
# Concurrent worker threads per provider.
LLM_CONCURRENCY: dict[str, int] = {
    "nvidia_nim": int(os.getenv("LLM_CONCURRENCY_NIM", "3")),
    "groq": int(os.getenv("LLM_CONCURRENCY_GROQ", "3")),
    "openrouter": int(os.getenv("LLM_CONCURRENCY_OPENROUTER", "2")),
    "openai": int(os.getenv("LLM_CONCURRENCY_OPENAI", "3")),
}
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "5"))
LLM_BATCH_TIMEOUT_SECONDS = float(os.getenv("LLM_BATCH_TIMEOUT_SECONDS", "60"))
LLM_POOL_TIME_BOX_SECONDS = float(os.getenv("LLM_POOL_TIME_BOX_SECONDS", "360"))
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "4"))
# OpenRouter server-side model routing: request body gets
# {"models": [primary, *fallbacks]} (max 3 models total).
OPENROUTER_FALLBACK_MODELS = os.getenv(
    "OPENROUTER_FALLBACK_MODELS",
    "cohere/north-mini-code:free,poolside/laguna-s-2.1:free",
)

# ---------------------------------------------------------------------------
# Bucket estimation (see tools/estimate_buckets.py): near-identical principal
# items share one LLM-estimated representative per bucket.
# ---------------------------------------------------------------------------
LLM_BUCKETING_ENABLED = os.getenv("LLM_BUCKETING_ENABLED", "true").lower() in (
    "true", "1", "yes",
)
LLM_MAX_BUCKETS = int(os.getenv("LLM_MAX_BUCKETS", "400"))
