#! /usr/bin/env python3
# -*- coding: utf-8 -*-
from collections import OrderedDict

from .base import BaseConfig
from .. import T, get_lang

PROVIDERS = {
    "Trustoken": {
        "api_base": T("https://sapi.trustoken.ai/v1"),
        "models_endpoint": "/models",
        "type": "trust",
        "model": "auto"
    },
    "DeepSeek": {
        "api_base": "https://api.deepseek.com",
        "models_endpoint": "/models",
        "type": "deepseek"
    },
    "MiniMax": {
        "api_base": T("https://api.minimax.io/v1"),
        "models_endpoint": "/models",
        "type": "minimax"
    },
    "MiniMax (Anthropic)": {
        "api_base": T("https://api.minimax.io/anthropic"),
        "models_endpoint": "/v1/models",
        "type": "minimax_anthropic"
    },
    "xAI": {
        "api_base": "https://api.x.ai/v1",
        "models_endpoint": "/models",
        "type": "grok"
    },
    "Claude": {
        "api_base": "https://api.anthropic.com/v1",
        "models_endpoint": "/models",
        "type": "claude"
    },
    "OpenAI": {
        "api_base": "https://api.openai.com/v1",
        "models_endpoint": "/models",
        "type": "openai"
    },
    "Gemini": {
        "api_base": "https://generativelanguage.googleapis.com/v1beta/",
        "models_endpoint": "/models",
        "type": "gemini"
    },
    "OAuth2": {
        "type": "oauth2"
    }
}

def get_providers():
    if get_lang() == "zh":
        providers = OrderedDict()
        providers["Trustoken"] = PROVIDERS["Trustoken"]
        providers["DeepSeek"] = PROVIDERS["DeepSeek"]
        providers["MiniMax"] = PROVIDERS["MiniMax"]
        providers["MiniMax (Anthropic)"] = PROVIDERS["MiniMax (Anthropic)"]
        return providers
    else:
        return PROVIDERS

class LLMConfig(BaseConfig):
    FILE = "llm.json"

    def __init__(self, path: str):
        super().__init__(path)
        self.providers = get_providers()

    def need_config(self):
        """检查是否需要配置LLM。
        """
        if not self.config:
            return True
        
        for _, config in self.config.items() :
            if config.get("enable", True):
                return False
        return True
