from __future__ import annotations

import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ModelCallError(Exception):
    """Raised when a LiteLLM generation cannot complete after retries.

    The caller (the LLM gateway) decides whether to fall back to the deterministic
    generator or surface a model_unavailable answer state; this exception just carries
    the typed failure across the proxy boundary.
    """


def _is_transient(exc: Exception) -> bool:
    # Timeouts, connection problems, and 5xx responses are worth retrying within the
    # latency budget; client errors (4xx) and malformed responses are not.
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _post_completion(messages: list[dict[str, str]], model_options: dict | None = None) -> str:
    settings = get_settings()
    url = settings.litellm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.litellm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    # Conservative stop sequences bound runaway repeated-marker output; callers can override.
    if settings.llm_stop_sequences:
        payload["stop"] = settings.llm_stop_sequences
    if model_options:
        payload.update(model_options)
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
    # OpenAI-compatible shape: choices[0].message.content.
    return body["choices"][0]["message"]["content"]


def complete(messages: list[dict[str, str]], model_options: dict | None = None) -> str:
    """Call the LiteLLM proxy with bounded retries, returning the generated text.

    Raises ModelCallError once the retry budget is exhausted so the gateway can decide
    on a safe fallback. Non-transient failures fail fast without retrying.
    """
    settings = get_settings()
    attempts = settings.llm_max_retries + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _post_completion(messages, model_options)
        except Exception as exc:  # noqa: BLE001 - normalized into ModelCallError below
            last_error = exc
            transient = _is_transient(exc)
            logger.error(
                "LiteLLM call failed attempt=%d/%d transient=%s model=%s",
                attempt, attempts, transient, settings.litellm_model, exc_info=True,
            )
            if not transient or attempt == attempts:
                break
            time.sleep(settings.llm_retry_backoff_seconds)
    raise ModelCallError(f"LiteLLM generation failed after {attempts} attempt(s)") from last_error
