import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from aipyapp.aipy.wizard import get_models
from aipyapp.config.llm import PROVIDERS, get_providers, minimax_model_choices
from aipyapp.llm.config import ClientConfig
from aipyapp.llm.manager import ClientManager, MiniMaxAnthropicClient, MiniMaxClient
from aipyapp.llm.models import ModelCapability, ModelRegistry


@pytest.mark.unit
def test_minimax_provider_types(monkeypatch):
    assert PROVIDERS["MiniMax"]["type"] == "minimax"
    assert PROVIDERS["MiniMax (Anthropic)"]["type"] == "minimax_anthropic"
    monkeypatch.setattr("aipyapp.config.llm.get_lang", lambda: "zh")
    assert "MiniMax" in get_providers()
    assert "MiniMax (Anthropic)" in get_providers()


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["MiniMax", "MiniMax (Anthropic)"])
def test_minimax_model_listing_uses_current_catalog(monkeypatch, provider):
    request = Mock(side_effect=AssertionError("Model discovery must be local"))
    monkeypatch.setattr("aipyapp.aipy.wizard.requests.get", request)
    assert get_models(PROVIDERS, provider, "test-key") == [
        "MiniMax-M3.1-Flash", "MiniMax-M3",
    ]
    request.assert_not_called()


@pytest.mark.unit
def test_other_provider_discovery_is_unchanged(monkeypatch):
    response = Mock(status_code=200, text="ok")
    response.json.return_value = {"data": [{"id": "custom-model"}]}
    request = Mock(return_value=response)
    monkeypatch.setattr("aipyapp.aipy.wizard.requests.get", request)
    assert get_models(PROVIDERS, "OpenAI", "test-key") == ["custom-model"]
    request.assert_called_once()


@pytest.mark.unit
@pytest.mark.parametrize("saved", [None, "MiniMax-M3", "MiniMax-M2.7", "custom-id"])
def test_model_choices_preserve_saved_selection(saved):
    models = minimax_model_choices(saved)
    assert models[:2] == ["MiniMax-M3.1-Flash", "MiniMax-M3"]
    if saved:
        assert models.count(saved) == 1
    assert minimax_model_choices() == ["MiniMax-M3.1-Flash", "MiniMax-M3"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("client_class", "base_url"),
    [
        (MiniMaxClient, "https://api.minimax.io/v1"),
        (MiniMaxAnthropicClient, "https://api.minimax.io/anthropic"),
    ],
)
def test_minimax_clients_use_protocol_specific_base_urls(
    monkeypatch, client_class, base_url
):
    monkeypatch.setattr("aipyapp.llm.manager.T", lambda _: base_url)
    config = ClientConfig(name="MiniMax", api_key="test-key")
    assert client_class(config).base_url == base_url
    assert client_class(config).model == "MiniMax-M3.1-Flash"


def response_body(protocol, model):
    if protocol == "minimax":
        return {
            "id": "chat_test", "object": "chat.completion", "created": 0,
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "ok", "reasoning_content": "plan",
            }}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": model,
        "content": [
            {"type": "thinking", "thinking": "plan", "signature": "test"},
            {"type": "text", "text": "ok"},
        ],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }


def conversation(protocol):
    if protocol == "minimax":
        return [
            {"role": "user", "content": [
                {"type": "text", "text": "Inspect this image"},
                {"type": "image_url", "image_url": {
                    "url": "https://example.com/image.png",
                }},
            ]},
            {"role": "assistant", "content": "", "reasoning_content": "plan",
             "tool_calls": [{"id": "call_test", "type": "function", "function": {
                 "name": "lookup", "arguments": "{}",
             }}]},
            {"role": "tool", "tool_call_id": "call_test", "content": "result"},
        ]
    return [
        {"role": "user", "content": [
            {"type": "text", "text": "Inspect this image"},
            {"type": "image", "source": {
                "type": "url", "url": "https://example.com/image.png",
            }},
        ]},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "plan", "signature": "test"},
            {"type": "tool_use", "id": "call_test", "name": "lookup", "input": {}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_test", "content": "result"},
        ]},
    ]


@pytest.mark.unit
@pytest.mark.parametrize("protocol", ["minimax", "minimax_anthropic"])
@pytest.mark.parametrize("host", ["api.minimax.io", "api.minimaxi.com", "custom.test"])
@pytest.mark.parametrize("model", [
    None, "MiniMax-M3.1-Flash", "MiniMax-M3", "MiniMax-M2.7", "custom-id",
])
@pytest.mark.parametrize("stream", [False, True])
def test_manager_serializes_default_and_saved_requests(
    monkeypatch, protocol, host, model, stream
):
    requests = []
    expected_model = model or "MiniMax-M3.1-Flash"

    def handle_request(self, request):
        requests.append(request)
        if stream:
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"},
                content=b"data: [DONE]\n\n", request=request,
            )
        return httpx.Response(200, json=response_body(protocol, expected_model))

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    api_root = "v1" if protocol == "minimax" else "anthropic"
    base_url = f"https://{host}/{api_root}"
    monkeypatch.setattr("aipyapp.llm.manager.T", lambda _: base_url)
    config = {"type": protocol, "api_key": "test-key", "stream": stream}
    if model:
        config["model"] = model
    if host == "custom.test":
        config["base_url"] = base_url
    manager = ClientManager({"MiniMax": config})
    client = manager.current
    messages = conversation(protocol)
    if stream:
        client.get_completion(messages).close()
    else:
        result = client(messages)
        assert result.content == "ok"
        assert result.reason == "plan"
    client._client.close()

    assert len(requests) == 1
    request = requests[0]
    path = "/chat/completions" if protocol == "minimax" else "/v1/messages"
    assert str(request.url) == base_url + path
    payload = json.loads(request.content)
    assert payload["model"] == expected_model
    assert payload["messages"] == messages
    assert payload["max_tokens"] == 8192
    assert payload.get("stream", False) == stream
    assert "thinking" not in payload
    assert "reasoning_effort" not in payload
    assert "output_config" not in payload
    assert "service_tier" not in payload
    assert "reasoning_split" not in payload
    assert config.get("model") == model


@pytest.mark.unit
@pytest.mark.parametrize("protocol", ["minimax", "minimax_anthropic"])
@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_flash_serializes_explicit_adaptive_effort(monkeypatch, protocol, effort):
    captured = []

    def handle_request(self, request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200, json=response_body(protocol, "MiniMax-M3.1-Flash"),
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    extra = {"extra_body": {"thinking": {"type": "adaptive"}}}
    if protocol == "minimax":
        extra["reasoning_effort"] = effort
    else:
        extra["output_config"] = {"effort": effort}
    config = {
        "type": protocol, "api_key": "test-key", "stream": False,
        "extra_fields": extra,
    }
    client = ClientManager({"MiniMax": config}).current
    assert client([{"role": "user", "content": "hello"}]).content == "ok"
    client._client.close()
    payload = captured[0]
    assert payload["thinking"] == {"type": "adaptive"}
    if protocol == "minimax":
        assert payload["reasoning_effort"] == effort
    else:
        assert payload["output_config"] == {"effort": effort}


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["MiniMax", "MiniMax (Anthropic)"])
@pytest.mark.parametrize("saved", [None, "MiniMax-M2.7", "custom-id"])
def test_cli_wizard_preserves_saved_model(monkeypatch, provider, saved):
    from aipyapp.aipy.wizard import config_llm

    config = Mock(providers=PROVIDERS, config={provider: {"model": saved}})
    monkeypatch.setattr("aipyapp.aipy.wizard.select_provider", lambda _: provider)
    monkeypatch.setattr(
        "aipyapp.aipy.wizard.questionary.text",
        Mock(return_value=Mock(unsafe_ask=lambda: "test-key")),
    )
    select = Mock(return_value=Mock(
        unsafe_ask=lambda: saved or "MiniMax-M3.1-Flash",
    ))
    monkeypatch.setattr("aipyapp.aipy.wizard.questionary.select", select)
    result = config_llm(config)
    assert result[provider]["model"] == (saved or "MiniMax-M3.1-Flash")
    assert select.call_args.kwargs["default"] == saved
    assert select.call_args.kwargs["choices"] == minimax_model_choices(saved)


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["MiniMax", "MiniMax (Anthropic)"])
@pytest.mark.parametrize("saved", [None, "MiniMax-M2.7", "custom-id"])
def test_gui_wizard_methods_preserve_saved_model(provider, saved):
    # Exercise the actual methods without requiring the optional desktop toolkit.
    path = Path("aipyapp/gui/providers.py")
    tree = ast.parse(path.read_text())
    wizard = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                  and node.name == "ProviderConfigWizard")
    methods = [node for node in wizard.body if isinstance(node, ast.FunctionDef)
               and node.name in ("get_models", "on_page_changed")]
    namespace = {
        "List": list, "minimax_model_choices": minimax_model_choices,
        "wx": SimpleNamespace(ID_FORWARD=1), "T": lambda value: value,
    }
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), "exec"),
         namespace)
    config = SimpleNamespace(providers=PROVIDERS, config={provider: {"model": saved}})
    ui = Mock(provider_config=config)
    ui.provider_page.get_provider.return_value = provider
    ui.provider_page.get_api_key.return_value = "test-key"
    ui.get_models = lambda *args: namespace["get_models"](ui, *args)
    event = Mock(GetPage=lambda: ui.model_page)
    namespace["on_page_changed"](ui, event)
    ui.model_page.set_models.assert_called_once_with(
        minimax_model_choices(saved), saved,
    )
    event.Veto.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("protocol", ["minimax", "minimax_anthropic"])
@pytest.mark.parametrize("thinking", ["adaptive", "disabled"])
def test_m3_preserves_explicit_thinking(monkeypatch, protocol, thinking):
    captured = []

    def handle_request(self, request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=response_body(protocol, "MiniMax-M3"))

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    client = ClientManager({"MiniMax": {
        "type": protocol, "api_key": "test-key", "stream": False,
        "model": "MiniMax-M3",
        "extra_fields": {"extra_body": {"thinking": {"type": thinking}}},
    }}).current
    assert client([{"role": "user", "content": "hello"}]).content == "ok"
    client._client.close()
    assert captured[0]["model"] == "MiniMax-M3"
    assert captured[0]["thinking"] == {"type": thinking}


@pytest.mark.unit
def test_minimax_model_registry_covers_target_models():
    registry = ModelRegistry("aipyapp/res/models.yaml")
    flash = registry.get_model_info("MiniMax-M3.1-Flash")
    m3 = registry.get_model_info("MiniMax-M3")
    legacy = registry.get_model_info("MiniMax-M2.7")
    assert flash.context_length == m3.context_length == 1_000_000
    assert flash.capabilities == m3.capabilities == {
        ModelCapability.TEXT, ModelCapability.IMAGE_INPUT,
        ModelCapability.VIDEO_INPUT, ModelCapability.FUNCTION_CALLING,
        ModelCapability.REASONING,
    }
    assert flash.extra["max_output_tokens"] == 524_288
    assert flash.extra["thinking"] == ["adaptive"]
    assert flash.extra["prices"] == {
        "input": 0.15, "cached": 0.015, "cache_write": None, "output": 0.60,
    }
    assert m3.extra["thinking"] == ["adaptive", "disabled"]
    assert m3.extra["prices"] == {
        "input": 0.30, "cached": 0.06, "cache_write": None, "output": 1.20,
    }
    assert m3.extra["pricing_tiers"]["above_512k"] == {
        "input": 0.60, "cached": 0.12, "output": 2.40,
    }
    assert legacy.context_length == 204_800
    assert legacy.extra["thinking"] == ["always_on"]
    assert legacy.extra["prices"] == {
        "input": 0.30, "cached": 0.06, "cache_write": 0.375, "output": 1.20,
    }
