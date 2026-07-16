"""Provider-neutral structured LLM boundary for Layer 2.

LiteLLM is an embedded transport/catalog dependency, not a domain API.  Extraction and matching
depend only on the small typed surface in this module, so changing a configured model does not
spread provider response shapes, token semantics, or pricing tables through the pipeline.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from vja.models import TokenUsage

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    """One validated response plus provider-normalized metering and trace metadata."""

    value: T
    usage: TokenUsage
    cost_usd: float
    model: str
    latency_seconds: float
    request_id: str | None = None


class StructuredLLM(Protocol):
    """The only LLM capability Layer 2 needs."""

    def parse(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        max_tokens: int,
        reasoning_effort: str | None = None,
        cache_system: bool = False,
    ) -> StructuredResult[T]: ...


def _field(value: object, name: str, default: object = None) -> object:
    """Read a field from LiteLLM's Pydantic objects or from test/provider dictionaries."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _int_field(value: object, name: str) -> int:
    raw = _field(value, name, 0)
    if raw is None:
        return 0
    if type(raw) is not int:
        raise TypeError(f"LLM usage field {name!r} must be an integer, got {type(raw).__name__}")
    return raw


def _token_usage(usage: object) -> TokenUsage:
    """Normalize LiteLLM/OpenAI usage without double-counting cached Anthropic input.

    LiteLLM's ``prompt_tokens`` is total input.  Its prompt-token details split that total into
    uncached text, cache reads, and cache writes for Anthropic; other providers may expose only
    total + cached tokens.  Persist the same mutually-exclusive buckets used by ``TokenUsage``.
    """
    prompt_total = _int_field(usage, "prompt_tokens")
    output = _int_field(usage, "completion_tokens")
    details = _field(usage, "prompt_tokens_details")
    cache_read = _int_field(details, "cached_tokens") if details is not None else 0
    cache_write = _int_field(details, "cache_creation_tokens") if details is not None else 0
    text_tokens_raw = _field(details, "text_tokens") if details is not None else None
    if text_tokens_raw is None:
        uncached = prompt_total - cache_read - cache_write
    elif type(text_tokens_raw) is int:
        uncached = text_tokens_raw
    else:
        raise TypeError(
            "LLM usage field 'text_tokens' must be an integer, "
            f"got {type(text_tokens_raw).__name__}"
        )
    if min(uncached, output, cache_read, cache_write) < 0:
        raise ValueError("LLM returned inconsistent negative token usage")
    return TokenUsage(
        input=uncached,
        output=output,
        cache_read=cache_read,
        cache_write=cache_write,
    )


class LiteLLMClient:
    """Synchronous embedded-LiteLLM implementation of ``StructuredLLM``.

    No router, fallback, or retry policy is configured here. Unsupported request parameters and
    missing catalog pricing remain errors; this boundary never silently drops a feature or records
    a paid response as a false zero-dollar call.
    """

    def __init__(
        self,
        *,
        completion: Callable[..., Any] | None = None,
        completion_cost: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if completion is None or completion_cost is None:
            import litellm

            completion = completion or litellm.completion
            completion_cost = completion_cost or litellm.completion_cost
        self._completion = completion
        self._completion_cost = completion_cost
        self._clock = clock

    def parse(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        max_tokens: int,
        reasoning_effort: str | None = None,
        cache_system: bool = False,
    ) -> StructuredResult[T]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": response_model,
            "max_tokens": max_tokens,
            "drop_params": False,
        }
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        if cache_system:
            kwargs["cache_control_injection_points"] = [{"location": "message", "role": "system"}]

        started = self._clock()
        response = self._completion(**kwargs)
        latency = self._clock() - started

        choices = _field(response, "choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("LLM returned no choices")
        message = _field(choices[0], "message")
        parsed = _field(message, "parsed")
        if isinstance(parsed, response_model):
            value = parsed
        elif parsed is not None:
            value = response_model.model_validate(parsed)
        else:
            content = _field(message, "content")
            if not isinstance(content, str) or not content:
                raise ValueError("LLM returned no structured content")
            value = response_model.model_validate_json(content)

        raw_usage = _field(response, "usage")
        if raw_usage is None:
            raise ValueError("LLM returned no token usage")
        usage = _token_usage(raw_usage)

        raw_cost = self._completion_cost(completion_response=response)
        if not isinstance(raw_cost, int | float):
            raise TypeError("LiteLLM completion_cost returned a non-numeric value")
        cost = float(raw_cost)
        if cost < 0 or (usage != TokenUsage() and cost == 0):
            raise ValueError("LiteLLM returned invalid zero/negative catalog cost")

        actual_model = _field(response, "model", model)
        if not isinstance(actual_model, str) or not actual_model:
            actual_model = model
        request_id = _field(response, "id")
        return StructuredResult(
            value=value,
            usage=usage,
            cost_usd=cost,
            model=actual_model,
            latency_seconds=latency,
            request_id=request_id if isinstance(request_id, str) else None,
        )
