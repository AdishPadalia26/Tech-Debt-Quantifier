"""Safe local LLM helpers for Ollama-backed, structured outputs."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LocalLLMService:
    """Thin wrapper around the configured local LLM with safe fallbacks."""

    def __init__(self, llm: Any | None = None) -> None:
        if llm is not None:
            self.llm = llm
        else:
            from agents.llm_factory import get_llm

            self.llm = get_llm("json")

    async def invoke_text(self, prompt: str) -> str | None:
        """Invoke the model and return text content, or None on failure."""
        try:
            result = await self.llm.ainvoke(prompt)
            if isinstance(result, str):
                return result
            content = getattr(result, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return str(result)
        except Exception as exc:
            logger.warning("Local LLM text invocation failed: %s", exc)
            return None

    async def invoke_json(self, prompt: str) -> dict[str, Any] | list[Any] | None:
        """Invoke the model and parse a JSON object/array response safely."""
        raw = await self.invoke_text(prompt)
        if not raw:
            return None
        extracted = self._extract_json(raw)
        if extracted is None:
            return None
        try:
            return json.loads(extracted)
        except json.JSONDecodeError as exc:
            logger.warning("Local LLM JSON parse failed: %s", exc)
            return None

    def _extract_json(self, text: str) -> str | None:
        """Extract the first JSON object or array from raw model output."""
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()

        for opener, closer in (("[", "]"), ("{", "}")):
            start = text.find(opener)
            if start == -1:
                continue
            depth = 0
            in_string = False
            escape = False
            for idx in range(start, len(text)):
                char = text[idx]
                if escape:
                    escape = False
                    continue
                if char == "\\" and in_string:
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == opener:
                    depth += 1
                elif char == closer:
                    depth -= 1
                    if depth == 0:
                        return text[start : idx + 1]
        return None
