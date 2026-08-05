import httpx
import pytest
from unittest.mock import Mock

from aipyapp.aipy.wizard import get_models
from aipyapp.config.llm import PROVIDERS, get_providers
from aipyapp.llm.config import ClientConfig
from aipyapp.llm.manager import MiniMaxAnthropicClient, MiniMaxClient
from aipyapp.llm.models import ModelCapability, ModelRegistry


@pytest.mark.unit
def test_minimax_provider_types(monkeypatch):
    assert PROVIDERS["MiniMax"]["type"] == "minimax"
    assert PROVIDERS["MiniMax (Anthropic)"]["type"] == "minimax_anthropic"

    monkeypatch.setattr("aipyapp.config.llm.get_lang", lambda: "zh")
    assert "MiniMax" in get_providers()
    assert "MiniMax (Anthropic)" in get_providers()


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
    config = ClientConfig(
        name="MiniMax",
        type=PROVIDERS["MiniMax"]["type"],
        api_key="test-key",
        model="MiniMax-M3",
    )

    assert client_class(config).base_url == base_url


@pytest.mark.unit
def test_minimax_anthropic_client_passes_sdk_base_url(monkeypatch):
    import anthropic

    base_url = "https://api.minimax.io/anthropic"
    factory = Mock(return_value=object())
    monkeypatch.setattr("aipyapp.llm.manager.T", lambda _: base_url)
    monkeypatch.setattr(anthropic, "Anthropic", factory)
    config = ClientConfig(
        name="MiniMax (Anthropic)",
        type="minimax_anthropic",
        api_key="test-key",
        model="MiniMax-M3",
    )

    MiniMaxAnthropicClient(config)._get_client()

    assert factory.call_args.kwargs["base_url"] == base_url


@pytest.mark.unit
@pytest.mark.parametrize(
    ("provider", "expected_header", "models_endpoint"),
    [
        ("MiniMax", ("Authorization", "Bearer test-key"), "/models"),
        ("MiniMax (Anthropic)", ("x-api-key", "test-key"), "/v1/models"),
    ],
)
def test_minimax_model_listing_uses_protocol_api_root(
    monkeypatch, provider, expected_header, models_endpoint
):
    response = Mock(status_code=200, text="ok")
    response.json.return_value = {
        "data": [{"id": "MiniMax-M3"}, {"id": "MiniMax-M2.7"}]
    }
    request = Mock(return_value=response)
    monkeypatch.setattr("aipyapp.aipy.wizard.requests.get", request)

    assert get_models(PROVIDERS, provider, "test-key") == [
        "MiniMax-M3",
        "MiniMax-M2.7",
    ]
    request.assert_called_once()
    url = request.call_args.args[0]
    headers = request.call_args.kwargs["headers"]
    api_base = PROVIDERS[provider]["api_base"]
    assert PROVIDERS[provider]["models_endpoint"] == models_endpoint
    assert url == f"{api_base}{models_endpoint}"
    assert headers[expected_header[0]] == expected_header[1]

    if provider == "MiniMax (Anthropic)":
        assert api_base in {
            "https://api.minimax.io/anthropic",
            "https://api.minimaxi.com/anthropic",
        }
        assert url == f"{api_base}/v1/models"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        (
            "https://api.minimax.io/anthropic",
            "https://api.minimax.io/anthropic/v1/messages",
        ),
        (
            "https://api.minimaxi.com/anthropic",
            "https://api.minimaxi.com/anthropic/v1/messages",
        ),
    ],
)
def test_anthropic_sdk_appends_messages_path_once(base_url, expected_url):
    requested_urls = []

    def handle_request(request):
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "model": "MiniMax-M3",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    import anthropic

    with httpx.Client(transport=httpx.MockTransport(handle_request)) as http_client:
        client = anthropic.Anthropic(
            api_key="test-key",
            base_url=base_url,
            http_client=http_client,
        )
        client.messages.create(
            model="MiniMax-M3",
            max_tokens=1,
            messages=[{"role": "user", "content": "hello"}],
        )

    assert requested_urls == [expected_url]
    assert requested_urls[0].count("/v1/messages") == 1


@pytest.mark.unit
def test_minimax_model_registry_covers_target_models():
    registry = ModelRegistry("aipyapp/res/models.yaml")
    m3 = registry.get_model_info("MiniMax-M3")
    m27 = registry.get_model_info("MiniMax-M2.7")

    assert m3.context_length == 1_000_000
    assert m3.capabilities == {
        ModelCapability.TEXT,
        ModelCapability.IMAGE_INPUT,
        ModelCapability.VIDEO_INPUT,
        ModelCapability.FUNCTION_CALLING,
        ModelCapability.REASONING,
    }
    assert m3.extra["prices"] == {
        "input": 0.60,
        "cached": 0.12,
        "cache_write": None,
        "output": 2.40,
    }
    assert "pricing_tiers" not in m3.extra
    assert m3.extra["thinking"] == ["adaptive", "disabled"]

    assert m27.context_length == 204_800
    assert m27.capabilities == {
        ModelCapability.TEXT,
        ModelCapability.FUNCTION_CALLING,
        ModelCapability.REASONING,
    }
    assert m27.extra["prices"] == {
        "input": 0.30,
        "cached": 0.06,
        "cache_write": 0.375,
        "output": 1.20,
    }
    assert m27.extra["thinking"] == ["always_on"]
