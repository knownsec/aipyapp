from collections import defaultdict, namedtuple

from loguru import logger

from .. import T, __respath__
from .base_openai import OpenAIBaseClient
from .client_claude import ClaudeClient
from .client_ollama import OllamaClient
from .client_oauth2 import OAuth2Client
from .models import ModelRegistry
from .config import create_client_config


class OpenAIBaseClientV2(OpenAIBaseClient):
    def get_api_params(self, **kwargs):
        params = super().get_api_params(**kwargs)

        # Adjust max_tokens to max_completion_tokens for OpenAI
        max_tokens = params.pop('max_tokens', None)
        if max_tokens is not None:
            params['max_completion_tokens'] = max_tokens
        return params


class OpenAIClient(OpenAIBaseClient):
    MODEL = 'gpt-4o'


class OpenAIClientV2(OpenAIBaseClientV2):
    MODEL = 'gpt-4o'


class GeminiClient(OpenAIBaseClient):
    BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
    MODEL = 'gemini-2.5-flash'


class DeepSeekClient(OpenAIBaseClient):
    BASE_URL = 'https://api.deepseek.com'
    MODEL = 'deepseek-chat'

    def get_api_params(self, **kwargs):
        params = super().get_api_params(**kwargs)
        params['extra_body'] = {"thinking": {"type": "disabled"}}
        return params


class GrokClient(OpenAIBaseClient):
    BASE_URL = 'https://api.x.ai/v1/'
    MODEL = 'grok-4-1-fast-reasoning'


class TrustClient(OpenAIBaseClient):
    MODEL = 'auto'

    @property
    def base_url(self):
        return self.config.base_url or T("https://sapi.trustoken.ai/v1")


class AzureOpenAIClient(OpenAIBaseClientV2):
    MODEL = 'gpt-4o'

    @property
    def endpoint(self):
        return self.config.get_extra_field('endpoint')

    def usable(self):
        return super().usable() and self.endpoint

    def _get_client(self):
        from openai import AzureOpenAI

        return AzureOpenAI(azure_endpoint=self.endpoint, api_key=self.config.api_key, api_version="2024-02-01", timeout=self.config.timeout)


class DoubaoClient(OpenAIBaseClient):
    BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'
    MODEL = 'doubao-seed-1-6-251015'


class MoonShotClient(OpenAIBaseClient):
    BASE_URL = T('https://api.moonshot.ai/v1')
    MODEL = 'kimi-latest'


class BigModelClient(OpenAIBaseClient):
    BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
    MODEL = 'glm-4.5-air'


class ZClient(OpenAIBaseClient):
    BASE_URL = 'https://api.z.ai/api/paas/v4'
    MODEL = 'glm-4.5-flash'


class MistralClient(OpenAIBaseClient):
    BASE_URL = 'https://api.mistral.ai/v1'
    MODEL = 'devstral-2512'


CLIENTS = {
    "openai": OpenAIClient,
    "openaiv2": OpenAIClientV2,
    "ollama": OllamaClient,
    "claude": ClaudeClient,
    "gemini": GeminiClient,
    "deepseek": DeepSeekClient,
    'grok': GrokClient,
    'trust': TrustClient,
    'azure': AzureOpenAIClient,
    'oauth2': OAuth2Client,
    'doubao': DoubaoClient,
    'kimi': MoonShotClient,
    'bigmodel': BigModelClient,
    'z': ZClient,
    'mistral': MistralClient,
}


class ClientManager(object):
    MAX_TOKENS = 8192

    def __init__(self, settings: dict, max_tokens: int | None = None):
        self.clients = {}
        self.default = None
        self.current = None
        self.max_tokens = max_tokens or self.MAX_TOKENS
        self.log = logger.bind(src='client_manager')
        self.names = self._init_clients(settings)
        self.model_registry = ModelRegistry(__respath__ / "models.yaml")

    def _create_client(self, name, config):
        kind = config.get("type", "openai")
        client_class = CLIENTS.get(kind.lower())
        if not client_class:
            self.log.error('Unsupported LLM provider', kind=kind)
            return None

        # 确保配置包含 name
        config2 = config.copy()
        config2['name'] = name
        config2.setdefault('type', kind)
        config2.setdefault('max_tokens', self.max_tokens)

        # 创建 ClientConfig 对象
        client_config = create_client_config(config2)
        return client_class(client_config)

    def _init_clients(self, settings):
        names = defaultdict(set)
        for name, config in settings.items():
            try:
                client = self._create_client(name, config)
            except Exception as e:
                self.log.exception('Error creating LLM client', config=config)
                names['error'].add(name)
                continue

            if not client.config.enabled:
                names['disabled'].add(name)
                continue

            if not client or not client.usable():
                names['disabled'].add(name)
                self.log.error('LLM client not usable', name=name, config=config)
                continue

            names['enabled'].add(name)
            self.clients[name] = client

            if client.config.default and not self.default:
                self.default = client
                names['default'] = name

        if not self.default:
            if self.clients:
                name = list(self.clients.keys())[0]
                self.default = self.clients[name]
                names['default'] = name
            else:
                # 如果没有可用的客户端，设置默认值为 None
                self.default = None
                names['default'] = None

        self.current = self.default
        return names

    def __len__(self):
        return len(self.clients)

    def __repr__(self):
        return f"Current: {'default' if self.current == self.default else self.current}, Default: {self.default}"

    def __contains__(self, name):
        return name in self.clients

    def use(self, name):
        client = self.clients.get(name)
        if client and client.usable():
            self.current = client
            return True
        return False

    def get_client(self, name):
        return self.clients.get(name)

    def to_records(self):
        LLMRecord = namedtuple('LLMRecord', ['Name', 'Model', 'Max_Tokens', 'Base_URL'])
        rows = []
        for name, client in self.clients.items():
            rows.append(LLMRecord(name, client.model, client.max_tokens, client.base_url))
        return rows

    def get_model_info(self, model: str):
        return self.model_registry.get_model_info(model)
