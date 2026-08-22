"""Offline contract tests for the embedded LiteLLM provider boundary."""

import logging
import traceback
from typing import Any

import pytest
from pydantic import BaseModel

from vja.llm import (
    LiteLLMClient,
    LLMRequestError,
    StructuredOutputError,
    _token_usage,
    sum_catalog_costs,
)


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


class _Fields(BaseModel):
    """Mirrors the shape `ExtractedFields` uses: a list, optional ints, optional strings."""

    label: str
    stack: list[str] = []
    comp_min: int | None = None
    comp_raw: str | None = None


def _client_returning(content: str) -> LiteLLMClient:
    return LiteLLMClient(
        completion=lambda **_: _response(content=content),
        completion_cost=lambda **_: 0.01,
    )


def _parse(client: LiteLLMClient) -> _Fields:
    return client.parse(
        model="anthropic/claude-haiku-4-5",
        system="system",
        user="user",
        response_model=_Fields,
        max_tokens=10,
    ).value


def test_parse_repairs_json_encoded_string_where_a_list_is_declared() -> None:
    """The 2026-08-18 provider regression: every value arrives as a JSON string."""
    value = _parse(
        _client_returning('{"label":"yes","stack":"[\\"Python\\", \\"Go\\"]","comp_min":"191000"}')
    )
    assert value.stack == ["Python", "Go"]
    assert value.comp_min == 191000


def test_parse_maps_the_literal_string_null_to_none_on_every_field() -> None:
    """`'null'` as a *string* must never reach a nullable column.

    On an int field it fails loudly; on a `str | None` field pydantic accepts it and the text
    "null" is persisted and rendered to the user (D-095 renders `comp_raw` verbatim). Both are
    the same provider bug and both must normalize to None.
    """
    value = _parse(
        _client_returning('{"label":"yes","comp_min":"null","comp_raw":"null","stack":"null"}')
    )
    assert value.comp_min is None
    assert value.comp_raw is None
    assert value.stack == []


def test_parse_leaves_well_formed_responses_untouched() -> None:
    value = _parse(
        _client_returning('{"label":"yes","stack":["Python"],"comp_min":100,"comp_raw":"$100k"}')
    )
    assert value == _Fields(label="yes", stack=["Python"], comp_min=100, comp_raw="$100k")


def test_parse_does_not_coerce_a_genuine_string_that_looks_numeric() -> None:
    """Repair must not turn a declared `str` field into an int just because it parses as one."""
    assert _parse(_client_returning('{"label":"yes","comp_raw":"191000"}')).comp_raw == "191000"


def test_unrepairable_structured_output_still_fails_but_reports_its_token_cost() -> None:
    """A billed call that we then discard must not be metered as free (the D-035 hole)."""
    client = _client_returning('{"label":{"nested":"object"}}')
    with pytest.raises(StructuredOutputError) as caught:
        _parse(client)
    assert caught.value.usage.input == 1000
    assert caught.value.usage.output == 200
    assert caught.value.cost_usd == pytest.approx(0.01)


def test_provider_exception_is_replaced_without_rendering_secrets() -> None:
    leaked_key = "sentinel-api-key-value-that-must-never-render"

    class ProviderFailure(RuntimeError):
        status_code = 401

    def completion(**_: Any) -> Any:
        raise ProviderFailure(f"Authorization: Bearer {leaked_key}; prompt=private resume")

    client = LiteLLMClient(completion=completion, completion_cost=lambda **_: 0.01)
    with pytest.raises(LLMRequestError) as caught:
        client.parse(
            model="provider/model",
            system="private system prompt",
            user="private user prompt",
            response_model=_Answer,
            max_tokens=10,
        )

    rendered = "".join(traceback.format_exception(caught.value))
    assert str(caught.value) == (
        "LLM request failed: model=provider/model error=ProviderFailure status=401"
    )
    assert leaked_key not in rendered
    assert "private resume" not in rendered
    assert "private system prompt" not in rendered
    assert "private user prompt" not in rendered


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
    with pytest.raises(
        LLMRequestError,
        match="LLM request failed: model=provider/model error=RuntimeError",
    ):
        client.parse(
            model="provider/model",
            system="system",
            user="user",
            response_model=_Answer,
            max_tokens=10,
            reasoning_effort="medium",
        )


def test_missing_catalog_pricing_returns_unavailable_cost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Alembic's test-only fileConfig disables loggers imported before migration tests run.
    logging.getLogger("vja.llm").disabled = False
    caplog.set_level(logging.WARNING, logger="vja.llm")

    def missing_price(**_: Any) -> Any:
        raise RuntimeError("model is not mapped")

    client = LiteLLMClient(completion=lambda **_: _response(), completion_cost=missing_price)
    result = client.parse(
        model="provider/model",
        system="system",
        user="user",
        response_model=_Answer,
        max_tokens=10,
    )

    assert result.cost_usd is None
    assert result.usage.input == 1000
    client.parse(
        model="provider/model",
        system="system",
        user="user",
        response_model=_Answer,
        max_tokens=10,
    )
    assert caplog.text.count("catalog cost unavailable") == 1


def test_invalid_catalog_cost_is_unavailable_not_false_zero() -> None:
    client = LiteLLMClient(
        completion=lambda **_: _response(),
        completion_cost=lambda **_: 0.0,
    )
    result = client.parse(
        model="provider/model",
        system="system",
        user="user",
        response_model=_Answer,
        max_tokens=10,
    )
    assert result.cost_usd is None


def test_catalog_cost_sum_preserves_unavailable_state() -> None:
    assert sum_catalog_costs(0.1, 0.2) == pytest.approx(0.3)
    assert sum_catalog_costs(0.1, None) is None


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
