import os
import pytest

os.environ.setdefault("HYBRID_ESTIMATION_ENABLED", "false")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:3b")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

@pytest.fixture(autouse=True)
def reset_env():
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)