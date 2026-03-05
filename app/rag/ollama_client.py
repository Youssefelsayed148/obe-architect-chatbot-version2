from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.settings import settings


def parse_embedding_response(payload: dict[str, Any]) -> list[float]:
    embedding = payload.get("embedding")
    if isinstance(embedding, list):
        return [float(x) for x in embedding]

    data = payload.get("data")
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict) and isinstance(item.get("embedding"), list):
            return [float(x) for x in item["embedding"]]

    raise ValueError("Ollama embeddings response missing embedding vector")


def parse_chat_response(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()

    response = payload.get("response")
    if isinstance(response, str):
        return response.strip()

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            choice_msg = first.get("message")
            if isinstance(choice_msg, dict) and isinstance(choice_msg.get("content"), str):
                return choice_msg["content"].strip()

    raise ValueError("Ollama chat response missing assistant content")


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 120.0) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._timeout = timeout_seconds

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=6),
        retry=retry_if_exception_type((httpx.HTTPError, ValueError)),
    )
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError(f"Unexpected non-object response from Ollama at {path}")
                return data
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Ollama request failed at {url}: {exc}") from exc

    def embed(self, text: str, model: str | None = None) -> list[float]:
        data = self._post(
            "/api/embeddings",
            {
                "model": model or settings.ollama_embed_model,
                "prompt": text,
            },
        )
        return parse_embedding_response(data)

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or settings.ollama_chat_model,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options
        data = self._post("/api/chat", payload)
        return parse_chat_response(data)
