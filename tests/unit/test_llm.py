"""Offline contract tests for the embedded LiteLLM provider boundary."""

from typing import Any

import pytest
from pydantic import BaseModel

from vja.llm import LiteLLMClient, _token_usage


class _Answer(BaseModel):
    label: str


def _response(*, content: str = '{"label":"yes"}', model: str = "upstream-model") -> dict[str, Any]:
    return {
        "id": "req-123",
        "model": model,
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": 5500,
            "completion_tokens": 200,
            "prompt_tokens_details": {
                "text_tokens": 1000,
                "cached_tokens": 4000,
                "cache_creation_tokens": 500,
            },
        },
    }


def test_parse_builds_provider_neutral_request_and_normalizes_response() -> None:
    calls: list[dict[str, Any]] = []

    def completion(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _response()

    times = iter((10.0, 10.75))
    client = LiteLLMClient(
        completion=completion,
        completion_cost=lambda **_: 0.0123,
        clock=lambda: next(times),
    )
    result = client.parse(
        model="anthropic/claude-sonnet-4-6",
        system="stable resume prefix",
        user="volatile posting",
        response_model=_Answer,
        max_tokens=4096,
        reasoning_effort="medium",
        cache_system=True,
    )

    assert calls == [
        {
            "model": "anthropic/claude-sonnet-4-6",
            "messages": [
                {"role": "system", "content": "stable resume prefix"},
                {"role": "user", "content": "volatile posting"},
            ],
            "response_format": _Answer,
            "max_tokens": 4096,
            "drop_params": False,
            "reasoning_effort": "medium",
            "cache_control_injection_points": [{"location": "message", "role": "system"}],
        }
    ]
    assert result.value == _Answer(label="yes")
    assert result.model == "upstream-model"  # actual response model, not configured alias
    assert result.request_id == "req-123"
    assert result.latency_seconds == pytest.approx(0.75)
    assert result.cost_usd == pytest.approx(0.0123)
    assert result.usage.input == 1000
    assert result.usage.output == 200
    assert result.usage.cache_read == 4000
    assert result.usage.cache_write == 500


def test_parse_accepts_sdk_parsed_value() -> None:
    response = _response()
    response["choices"] = [{"message": {"content": None, "parsed": {"label": "parsed"}}}]
    client = LiteLLMClient(
        completion=lambda **_: response,
        completion_cost=lambda **_: 0.01,
    )
    assert client.parse(
        model="provider/model",
        system="system",
        user="user",
        response_model=_Answer,
        max_tokens=10,
    ).value == _Answer(label="parsed")


def test_token_usage_derives_uncached_input_when_provider_omits_text_detail() -> None:
    usage = _token_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 30, "cache_creation_tokens": 10},
        }
    )
    assert (usage.input, usage.output, usage.cache_read, usage.cache_write) == (60, 20, 30, 10)


def test_unsupported_parameter_failure_propagates() -> None:
    def completion(**_: Any) -> Any:
        raise RuntimeError("unsupported reasoning_effort")

    client = LiteLLMClient(completion=completion, completion_cost=lambda **_: 0.01)
    with pytest.raises(RuntimeError, match="unsupported reasoning_effort"):
        client.parse(
            model="provider/model",
            system="system",
            user="user",
            response_model=_Answer,
            max_tokens=10,
            reasoning_effort="medium",
        )


def test_missing_catalog_pricing_failure_propagates() -> None:
    def missing_price(**_: Any) -> Any:
        raise RuntimeError("model is not mapped")

    client = LiteLLMClient(completion=lambda **_: _response(), completion_cost=missing_price)
    with pytest.raises(RuntimeError, match="not mapped"):
        client.parse(
            model="provider/model",
            system="system",
            user="user",
            response_model=_Answer,
            max_tokens=10,
        )


def test_nonempty_usage_cannot_be_recorded_as_false_zero_cost() -> None:
    client = LiteLLMClient(
        completion=lambda **_: _response(),
        completion_cost=lambda **_: 0.0,
    )
    with pytest.raises(ValueError, match="zero/negative catalog cost"):
        client.parse(
            model="provider/model",
            system="system",
            user="user",
            response_model=_Answer,
            max_tokens=10,
        )


def test_missing_structured_content_and_usage_fail_loud() -> None:
    no_content = _response(content="")
    client = LiteLLMClient(completion=lambda **_: no_content, completion_cost=lambda **_: 0.01)
    with pytest.raises(ValueError, match="no structured content"):
        client.parse(
            model="provider/model",
            system="system",
            user="user",
            response_model=_Answer,
            max_tokens=10,
        )

    no_usage = _response()
    no_usage["usage"] = None
    client = LiteLLMClient(completion=lambda **_: no_usage, completion_cost=lambda **_: 0.01)
    with pytest.raises(ValueError, match="no token usage"):
        client.parse(
            model="provider/model",
            system="system",
            user="user",
            response_model=_Answer,
            max_tokens=10,
        )
