"""LLM factory for Tech Debt Quantifier.

Supports Groq, NVIDIA NIM, OpenRouter, Ollama, HuggingFace API, local
HuggingFace models, and OpenAI. Model IDs come from ``app_config`` (all
env-overridable). The provider/model actually chosen (after any fallback hops)
is recorded and exposed via ``get_active_model_info()``; the startup probe
result is exposed via ``get_llm_health()``.

Multi-provider pool helpers: ``available_pool_providers()`` lists the keyed
providers in ``LLM_POOL_PROVIDERS`` and ``get_llm_for()`` returns one
provider's chat model (temperature 0, no retries, no fallback hops).
"""

import concurrent.futures
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.language_models import BaseLLM

import app_config as config

logger = logging.getLogger(__name__)

# API-key-looking tokens (NVIDIA nvapi-, Groq gsk_, OpenRouter/OpenAI sk-...).
_SECRET_RE = re.compile(r"(?:nvapi-|gsk_|sk-or-v1-|sk-)[A-Za-z0-9_\-\.]{8,}")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

# provider -> env var holding its API key (pool-capable providers only).
POOL_KEY_ENV: dict[str, str] = {
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
}

_STATE_LOCK = threading.Lock()
_ACTIVE_MODEL: dict[str, str | None] = {"provider": None, "model": None}
_LLM_HEALTH: dict[str, Any] = {
    "ok": None,
    "provider": None,
    "model": None,
    "error": None,
    "checked_at": None,
    "providers": {},
}


def _record_active(provider: str, model: str) -> None:
    """Remember which provider/model get_llm() actually returned."""
    with _STATE_LOCK:
        _ACTIVE_MODEL["provider"] = provider
        _ACTIVE_MODEL["model"] = model


def _fallback_hop(from_provider: str, to_provider: str, reason: str) -> None:
    """Log a provider fallback hop at WARNING (never includes key material)."""
    logger.warning(
        "LLM provider fallback %s -> %s: %s", from_provider, to_provider, reason
    )


def get_active_model_info() -> dict[str, str | None]:
    """Return the provider and model most recently selected by get_llm().

    Returns:
        Dict ``{"provider": str | None, "model": str | None}``; both None
        until get_llm() has been called once.
    """
    with _STATE_LOCK:
        return dict(_ACTIVE_MODEL)


def get_llm_health() -> dict[str, Any]:
    """Return the cached result of the last LLM health probe.

    Returns:
        Dict ``{ok, provider, model, error, checked_at, providers}``. ``ok`` is
        None while no probe has completed yet. ``providers`` maps each pool
        provider to ``{ok, model, error, latency_ms}``.
    """
    with _STATE_LOCK:
        snapshot = dict(_LLM_HEALTH)
        snapshot["providers"] = {
            name: dict(info) for name, info in _LLM_HEALTH["providers"].items()
        }
        return snapshot


def scrub_secrets(text: str) -> str:
    """Redact API-key-looking tokens from text destined for logs or responses."""
    return _SECRET_RE.sub("[redacted]", text)


def get_model_id_for(provider: str) -> str:
    """Return the configured model id for a pool provider.

    Raises:
        ValueError: Unknown provider.
    """
    if provider == "nvidia_nim":
        return os.getenv("NIM_MODEL_ID", config.NIM_MODEL_ID)
    if provider == "groq":
        return os.getenv("GROQ_MODEL_ID", config.GROQ_MODEL_ID)
    if provider == "openrouter":
        return os.getenv("OPENROUTER_MODEL_ID", config.OPENROUTER_MODEL_ID)
    if provider == "openai":
        return os.getenv("OPENAI_MODEL_ID", config.OPENAI_MODEL_ID)
    raise ValueError(f"Unknown pool provider '{provider}'")


def get_model_candidates_for(provider: str) -> list[str]:
    """Return every model a provider may actually serve (primary first).

    Only OpenRouter has more than one: its primary model plus the server-side
    fallbacks from ``OPENROUTER_FALLBACK_MODELS`` (max 3 models in total).
    """
    primary = get_model_id_for(provider)
    if provider != "openrouter":
        return [primary]
    raw = os.getenv("OPENROUTER_FALLBACK_MODELS", config.OPENROUTER_FALLBACK_MODELS)
    models = [primary]
    for name in (m.strip() for m in raw.split(",")):
        if name and name not in models:
            models.append(name)
    return models[:3]


def available_pool_providers() -> list[str]:
    """List pool providers (``LLM_POOL_PROVIDERS`` order) that have an API key.

    Returns:
        Provider names that are known and whose key env var is non-empty.
    """
    raw = os.getenv("LLM_POOL_PROVIDERS", config.LLM_POOL_PROVIDERS)
    names: list[str] = []
    for name in (p.strip() for p in raw.split(",")):
        if not name or name in names:
            continue
        key_env = POOL_KEY_ENV.get(name)
        if key_env is None:
            logger.warning("Ignoring unknown LLM pool provider '%s'", name)
            continue
        if os.getenv(key_env):
            names.append(name)
    return names


def get_llm_for(provider: str, task: str = "default") -> BaseLLM:
    """Return the chat model for one specific pool provider.

    Temperature 0, SDK retries disabled (the pool does its own retry/failover)
    and an HTTP timeout slightly above ``LLM_BATCH_TIMEOUT_SECONDS`` so hung
    sockets are reaped. No fallback hops and no active-model recording.

    Args:
        provider: "nvidia_nim" | "groq" | "openrouter" | "openai".
        task: Unused hint kept for parity with ``get_llm``.

    Returns:
        A LangChain chat model.

    Raises:
        ValueError: Unknown provider or missing API key.
    """
    key_env = POOL_KEY_ENV.get(provider)
    if key_env is None:
        raise ValueError(f"Unknown pool provider '{provider}'")
    api_key = os.getenv(key_env)
    if not api_key:
        raise ValueError(f"{key_env} is not set")

    model_id = get_model_id_for(provider)
    http_timeout = (
        float(os.getenv("LLM_BATCH_TIMEOUT_SECONDS", config.LLM_BATCH_TIMEOUT_SECONDS))
        + 5.0
    )

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model_id,
            temperature=0,
            api_key=api_key,
            timeout=http_timeout,
            max_retries=0,
        )

    from langchain_openai import ChatOpenAI

    extra: dict[str, Any] = {}
    if provider == "nvidia_nim":
        extra["base_url"] = NIM_BASE_URL
    elif provider == "openrouter":
        extra["base_url"] = OPENROUTER_BASE_URL
        extra["default_headers"] = {
            "HTTP-Referer": os.getenv(
                "OPENROUTER_REFERER", "https://github.com/tech-debt-quantifier"
            ),
            "X-Title": "Tech Debt Quantifier",
        }
        candidates = get_model_candidates_for("openrouter")
        if len(candidates) > 1:
            # OpenRouter routes to the next model when the first is unavailable
            # or rate-limited upstream; only a total failure surfaces as 429.
            extra["extra_body"] = {"models": candidates}
    return ChatOpenAI(
        model=model_id,
        temperature=0,
        api_key=api_key,
        timeout=http_timeout,
        max_retries=0,
        **extra,
    )


def _probe_one(provider: str, timeout: float) -> dict[str, Any]:
    """Make one tiny call to a single pool provider; never raises."""
    from langchain_core.messages import HumanMessage

    model = get_model_id_for(provider)
    started = time.monotonic()
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix=f"llm-health-{provider}"
    )
    try:
        llm = get_llm_for(provider, "default")
        future = executor.submit(
            llm.invoke, [HumanMessage(content="Reply with the single word: ok")]
        )
        future.result(timeout=timeout)
        return {
            "ok": True,
            "model": model,
            "error": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except concurrent.futures.TimeoutError:
        error = f"TimeoutError: no LLM reply within {timeout:.0f}s"
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        executor.shutdown(wait=False)
    return {
        "ok": False,
        "model": model,
        "error": scrub_secrets(error),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


def probe_llm_health(timeout_seconds: float | None = None) -> dict[str, Any]:
    """Probe every pool provider in parallel and cache the outcome for /health.

    Falls back to a single probe of ``get_llm()`` when no pool provider has an
    API key. Safe to run in a background thread; never raises.

    Args:
        timeout_seconds: Max seconds to wait for each LLM reply
            (defaults to ``config.LLM_HEALTH_TIMEOUT_SECONDS``).

    Returns:
        The cached health dict (see get_llm_health()).
    """
    timeout = timeout_seconds or config.LLM_HEALTH_TIMEOUT_SECONDS
    providers = available_pool_providers()
    if not providers:
        return _probe_single(timeout)

    per_provider: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(providers), thread_name_prefix="llm-probe"
    ) as pool:
        futures = {name: pool.submit(_probe_one, name, timeout) for name in providers}
        for name in providers:
            per_provider[name] = futures[name].result()

    first_ok = next((n for n in providers if per_provider[n]["ok"]), None)
    head = first_ok or providers[0]
    result: dict[str, Any] = {
        "ok": first_ok is not None,
        "provider": head,
        "model": per_provider[head]["model"],
        "error": None if first_ok else per_provider[head]["error"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "providers": per_provider,
    }
    with _STATE_LOCK:
        _LLM_HEALTH.update(result)
    for name, info in per_provider.items():
        if info["ok"]:
            logger.info(
                "LLM health probe OK: provider=%s model=%s latency_ms=%s",
                name, info["model"], info["latency_ms"],
            )
        else:
            logger.warning(
                "LLM health probe FAILED: provider=%s model=%s error=%s",
                name, info["model"], info["error"],
            )
    if first_ok is None:
        logger.error(
            "LLM health probe: no pool provider healthy "
            "(LLM estimates will fall back to formula defaults)"
        )
    return get_llm_health()


def _probe_single(timeout: float) -> dict[str, Any]:
    """Legacy probe: one tiny call through ``get_llm()`` (no pool provider)."""
    from langchain_core.messages import HumanMessage

    ok = False
    error: str | None = None
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="llm-health"
    )
    try:
        llm = get_llm("default")
        future = executor.submit(
            llm.invoke, [HumanMessage(content="Reply with the single word: ok")]
        )
        future.result(timeout=timeout)
        ok = True
    except concurrent.futures.TimeoutError:
        error = f"TimeoutError: no LLM reply within {timeout:.0f}s"
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        executor.shutdown(wait=False)

    active = get_active_model_info()
    result: dict[str, Any] = {
        "ok": ok,
        "provider": active["provider"],
        "model": active["model"],
        "error": scrub_secrets(error) if error else None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "providers": {},
    }
    with _STATE_LOCK:
        _LLM_HEALTH.update(result)
    if ok:
        logger.info(
            "LLM health probe OK: provider=%s model=%s",
            result["provider"],
            result["model"],
        )
    else:
        logger.error(
            "LLM health probe FAILED: provider=%s model=%s error=%s "
            "(LLM estimates will fall back to formula defaults)",
            result["provider"],
            result["model"],
            result["error"],
        )
    return get_llm_health()


def get_llm(task: str = "default") -> BaseLLM:
    """Return the appropriate LLM based on the LLM_PROVIDER setting.

    Args:
        task: "summary" | "json" | "default"

    Returns:
        A LangChain-compatible chat model / LLM instance.
    """
    provider = os.getenv("LLM_PROVIDER", config.LLM_PROVIDER)

    if provider == "groq":
        return _get_groq_llm(task)
    elif provider == "nvidia_nim":
        return _get_nvidia_nim_llm(task)
    elif provider == "openrouter":
        return _get_openrouter_llm(task)
    elif provider == "ollama":
        return _get_ollama_llm(task)
    elif provider == "huggingface_api":
        return _get_hf_api_llm(task)
    elif provider == "huggingface_local":
        return _get_hf_local_llm(task)
    elif provider == "openai":
        return _get_openai_llm()
    else:
        _fallback_hop(provider, "groq", f"unknown LLM_PROVIDER '{provider}'")
        return _get_groq_llm(task)


def _get_openrouter_llm(task: str) -> BaseLLM:
    """OpenRouter (OpenAI-compatible); falls back to NVIDIA NIM without a key."""
    if not os.getenv("OPENROUTER_API_KEY"):
        _fallback_hop("openrouter", "nvidia_nim", "OPENROUTER_API_KEY not set")
        return _get_nvidia_nim_llm(task)
    llm = get_llm_for("openrouter", task)
    model_id = get_model_id_for("openrouter")
    logger.info("Using OpenRouter: %s", model_id)
    _record_active("openrouter", model_id)
    return llm


def _get_ollama_llm(task: str) -> BaseLLM:
    """Use a local Ollama model through the OpenAI-compatible API."""
    from langchain_openai import ChatOpenAI

    model_name = os.getenv("OLLAMA_MODEL", config.OLLAMA_MODEL)
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    timeout_seconds = float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "20"))

    logger.info("Using Ollama model: %s @ %s", model_name, base_url)
    _record_active("ollama", model_name)
    return ChatOpenAI(
        model=model_name,
        temperature=0.1,
        api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        base_url=base_url,
        timeout=timeout_seconds,
    )


def _get_groq_llm(task: str) -> BaseLLM:
    """Groq Inference API — fast, free tier available."""
    from langchain_groq import ChatGroq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        _fallback_hop("groq", "nvidia_nim", "GROQ_API_KEY not set")
        return _get_nvidia_nim_llm(task)

    model_id = os.getenv("GROQ_MODEL_ID", config.GROQ_MODEL_ID)
    logger.info("Using Groq: %s", model_id)
    _record_active("groq", model_id)
    return ChatGroq(
        model=model_id,
        temperature=0.1,
        api_key=api_key,
    )


def _get_nvidia_nim_llm(task: str) -> BaseLLM:
    """NVIDIA NIM Inference API — OpenAI-compatible, free tier available."""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        _fallback_hop("nvidia_nim", "openai", "NVIDIA_NIM_API_KEY not set")
        return _get_openai_llm()

    model_id = os.getenv("NIM_MODEL_ID", config.NIM_MODEL_ID)
    logger.info("Using NVIDIA NIM: %s", model_id)
    _record_active("nvidia_nim", model_id)
    return ChatOpenAI(
        model=model_id,
        temperature=0.1,
        api_key=api_key,
        base_url=NIM_BASE_URL,
    )


class HuggingFaceChatLLM:
    """Custom LLM wrapper for HuggingFace Hub InferenceClient."""

    def __init__(
        self, model: str = "Qwen/Qwen2.5-7B-Instruct", token: str | None = None
    ) -> None:
        from huggingface_hub import InferenceClient

        self.model_name = model
        self.client = InferenceClient(token=token)
        self._generation_kwargs = {
            "max_tokens": 1024,
            "temperature": 0.1,
        }

    def __call__(self, prompt: str, **kwargs: Any) -> str:
        return self._call(prompt)

    def _call(self, prompt: str, **kwargs: Any) -> str:
        try:
            if hasattr(prompt, "to_string"):
                prompt_str = prompt.to_string()
            else:
                prompt_str = str(prompt)
            result = self.client.chat_completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt_str}],
                **self._generation_kwargs,
            )
            return result.choices[0].message.content
        except Exception as e:
            logger.error("HuggingFace API error: %s", e)
            return f"Error: {e}"

    def _generate(self, prompts: list[str], **kwargs: Any) -> Any:
        results = [self._call(p) for p in prompts]
        from langchain_core.outputs import Generation, LLMResult

        generations = [[Generation(text=r)] for r in results]
        return LLMResult(generations=generations)

    async def _agenerate(self, prompts: list[str], **kwargs: Any) -> Any:
        import asyncio

        results = await asyncio.gather(*[self._acall(p) for p in prompts])
        from langchain_core.outputs import Generation, LLMResult

        generations = [[Generation(text=r)] for r in results]
        return LLMResult(generations=generations)

    async def _acall(self, prompt: str, **kwargs: Any) -> str:
        return self._call(prompt)

    @property
    def _llm_type(self) -> str:
        return "huggingface_hub"


def _get_hf_api_llm(task: str) -> BaseLLM:
    """HuggingFace Inference API — free tier, 1000 req/day."""
    token = os.getenv("HF_TOKEN")
    if not token:
        _fallback_hop("huggingface_api", "openai", "HF_TOKEN not set")
        return _get_openai_llm()

    model_id = os.getenv("HF_MODEL_ID", config.HF_MODEL_ID)

    try:
        llm = HuggingFaceChatLLM(model=model_id, token=token)
        logger.info("Using HuggingFace API: %s", model_id)
        _record_active("huggingface_api", model_id)
        return llm
    except Exception as e:  # noqa: BLE001 - any init failure triggers fallback
        _fallback_hop(
            "huggingface_api", "openai", f"{type(e).__name__}: {str(e)[:200]}"
        )
        return _get_openai_llm()


def _get_hf_local_llm(task: str) -> BaseLLM:
    """Run model locally using transformers pipeline. Requires 8GB+ RAM."""
    import torch
    from langchain_huggingface import HuggingFacePipeline
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

    model_id = os.getenv("HF_MODEL_ID", config.HF_LOCAL_MODEL_ID)

    logger.info("Loading %s locally... (this takes 1-2 min first time)", model_id)

    try:
        import psutil

        ram_gb = psutil.virtual_memory().total / (1024**3)
        if ram_gb < 6:
            logger.warning("Only %.1fGB RAM — switching to tiny model", ram_gb)
            model_id = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    except Exception:
        pass

    try:
        from transformers import BitsAndBytesConfig

        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=quantization_config,
            device_map="auto",
            trust_remote_code=True,
        )
    except Exception:
        logger.info("4-bit quant not available — loading on CPU (slower)")
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True,
        )

    tokenizer = AutoTokenizer.from_pretrained(model_id)

    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=1024,
        temperature=0.1,
        repetition_penalty=1.1,
        return_full_text=False,
    )

    logger.info("Model loaded locally: %s", model_id)
    _record_active("huggingface_local", model_id)
    return HuggingFacePipeline(pipeline=pipe)


def _get_openai_llm() -> BaseLLM:
    """OpenAI — used if LLM_PROVIDER=openai or as the last fallback hop."""
    from langchain_openai import ChatOpenAI

    model_id = os.getenv("OPENAI_MODEL_ID", config.OPENAI_MODEL_ID)
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not set; OpenAI LLM calls will fail")
    logger.info("Using OpenAI: %s", model_id)
    _record_active("openai", model_id)
    return ChatOpenAI(
        model=model_id,
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
