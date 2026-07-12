"""LLM factory for Tech Debt Quantifier.

Supports Groq, NVIDIA NIM, Ollama, HuggingFace API, local HuggingFace models, and OpenAI.
"""

import logging
import os

from langchain_core.language_models import BaseLLM

logger = logging.getLogger(__name__)


def get_llm(task: str = "default") -> BaseLLM:
    """Return the appropriate LLM based on LLM_PROVIDER env var.

    Args:
        task: "summary" | "json" | "default"
    """
    provider = os.getenv("LLM_PROVIDER", "groq")

    if provider == "groq":
        return _get_groq_llm(task)
    elif provider == "nvidia_nim":
        return _get_nvidia_nim_llm(task)
    elif provider == "ollama":
        return _get_ollama_llm(task)
    elif provider == "huggingface_api":
        return _get_hf_api_llm(task)
    elif provider == "huggingface_local":
        return _get_hf_local_llm(task)
    elif provider == "openai":
        return _get_openai_llm()
    else:
        logger.warning(f"Unknown provider {provider}, falling back to Groq")
        return _get_groq_llm(task)


def _get_ollama_llm(task: str) -> BaseLLM:
    """Use a local Ollama model through the OpenAI-compatible API."""
    from langchain_openai import ChatOpenAI

    model_name = os.getenv("OLLAMA_MODEL", "qwen3.5:latest")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    timeout_seconds = float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "20"))

    logger.info(f"Using Ollama model: {model_name} @ {base_url}")
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
        logger.warning("GROQ_API_KEY not set, falling back to NVIDIA NIM")
        return _get_nvidia_nim_llm(task)

    model_id = os.getenv("GROQ_MODEL_ID", "llama-3.3-70b-versatile")
    logger.info("Using Groq: %s (api_key set: %s)", model_id, bool(api_key))
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
        logger.warning("NVIDIA_NIM_API_KEY not set, falling back to OpenAI")
        return _get_openai_llm()

    model_id = os.getenv("NIM_MODEL_ID", "meta/llama-3.1-8b-instruct")
    logger.info(f"Using NVIDIA NIM: {model_id}")
    return ChatOpenAI(
        model=model_id,
        temperature=0.1,
        api_key=api_key,
        base_url="https://integrate.api.nvidia.com/v1",
    )


class HuggingFaceChatLLM:
    """Custom LLM wrapper for HuggingFace Hub InferenceClient."""

    def __init__(self, model: str = "Qwen/Qwen2.5-7B-Instruct", token: str | None = None):
        from huggingface_hub import InferenceClient
        self.model_name = model
        self.client = InferenceClient(token=token)
        self._generation_kwargs = {
            "max_tokens": 1024,
            "temperature": 0.1,
        }

    def __call__(self, prompt: str, **kwargs) -> str:
        return self._call(prompt)

    def _call(self, prompt: str, **kwargs) -> str:
        try:
            if hasattr(prompt, 'to_string'):
                prompt_str = prompt.to_string()
            else:
                prompt_str = str(prompt)
            result = self.client.chat_completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt_str}],
                **self._generation_kwargs
            )
            return result.choices[0].message.content
        except Exception as e:
            logger.error(f"HuggingFace API error: {e}")
            return f"Error: {e}"

    def _generate(self, prompts: list[str], **kwargs):
        results = [self._call(p) for p in prompts]
        from langchain_core.outputs import LLMResult, Generation
        generations = [[Generation(text=r)] for r in results]
        return LLMResult(generations=generations)

    async def _agenerate(self, prompts: list[str], **kwargs):
        import asyncio
        results = await asyncio.gather(*[self._acall(p) for p in prompts])
        from langchain_core.outputs import LLMResult, Generation
        generations = [[Generation(text=r)] for r in results]
        return LLMResult(generations=generations)

    async def _acall(self, prompt: str, **kwargs) -> str:
        return self._call(prompt)

    @property
    def _llm_type(self) -> str:
        return "huggingface_hub"


def _get_hf_api_llm(task: str) -> BaseLLM:
    """HuggingFace Inference API — free tier, 1000 req/day."""
    token = os.getenv("HF_TOKEN")
    if not token:
        logger.warning("HF_TOKEN not set")
        return _get_openai_llm()

    model_id = os.getenv("HF_MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")

    try:
        llm = HuggingFaceChatLLM(model=model_id, token=token)
        logger.info(f"Using HuggingFace API: {model_id}")
        return llm
    except Exception as e:
        logger.warning(f"HF API failed: {e}")
        return _get_openai_llm()


def _get_hf_local_llm(task: str) -> BaseLLM:
    """Run model locally using transformers pipeline. Requires 8GB+ RAM."""
    from langchain_huggingface import HuggingFacePipeline
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    import torch

    model_id = os.getenv("HF_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")

    logger.info(f"Loading {model_id} locally... (this takes 1-2 min first time)")

    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
        if ram_gb < 6:
            logger.warning(f"Only {ram_gb:.1f}GB RAM — switching to tiny model")
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

    logger.info(f"Model loaded locally: {model_id}")
    return HuggingFacePipeline(pipeline=pipe)


def _get_openai_llm() -> BaseLLM:
    """OpenAI fallback — only used if LLM_PROVIDER=openai."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
