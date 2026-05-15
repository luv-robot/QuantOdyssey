from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    raw: dict[str, Any]
    error: str | None = None


class DeepSeekChatClient:
    provider = "deepseek"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4")
        self.base_url = (base_url or os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> ChatCompletionResult:
        if not self.api_key:
            return ChatCompletionResult(content="", raw={}, error="DEEPSEEK_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = Request(
            self._chat_completions_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return ChatCompletionResult(content="", raw={"status": exc.code, "body": body}, error=f"HTTP {exc.code}")
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            return ChatCompletionResult(content="", raw={}, error=str(exc))

        content = ""
        choices = raw.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = str(message.get("content") or "").strip()
        if not content:
            return ChatCompletionResult(content="", raw=raw, error="DeepSeek response did not contain content.")
        return ChatCompletionResult(content=content, raw=raw)

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"
