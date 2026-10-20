#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Any, Dict
from collections import Counter

from .base import BaseClient, MessageRole, AIMessage

# https://docs.anthropic.com/en/api/messages
class ClaudeClient(BaseClient):
    MODEL = "claude-sonnet-4.5"
    ENV_API_KEY = "ANTHROPIC_API_KEY"
    #PARAMS = {'thinking': {'type': 'enabled', 'budget_tokens': 1024}}

    def __init__(self, config):
        super().__init__(config)
        self._system_prompt = None

    def _get_client(self):
        import anthropic
        kwargs = {
            "api_key": self.config.api_key,
            "timeout": self.config.timeout,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return anthropic.Anthropic(**kwargs)

    def usable(self):
        return super().usable() and self.config.api_key
    
    def _parse_usage(self, response):
        usage = response.usage
        ret = Counter({
            'input_tokens': usage.input_tokens,
            'output_tokens': usage.output_tokens,
            'total_tokens': usage.input_tokens + usage.output_tokens
        })
        return ret

    def _parse_stream_response(self, response, stream_processor):
        usage = Counter()    
        with stream_processor as lm:
            for event in response:
                if hasattr(event, 'delta') and hasattr(event.delta, 'text') and event.delta.text:
                    content = event.delta.text
                    lm.process_chunk(content)
                elif hasattr(event, 'message') and hasattr(event.message, 'usage') and event.message.usage:
                    usage['input_tokens'] += getattr(event.message.usage, 'input_tokens', 0)
                    usage['output_tokens'] += getattr(event.message.usage, 'output_tokens', 0)
                elif hasattr(event, 'usage') and event.usage:
                    usage['input_tokens'] += getattr(event.usage, 'input_tokens', 0)
                    usage['output_tokens'] += getattr(event.usage, 'output_tokens', 0)

        usage['total_tokens'] = usage['input_tokens'] + usage['output_tokens']
        return AIMessage(content=lm.content, usage=usage)

    def _parse_response(self, response):
        content = response.content[0].text
        role = response.role
        return AIMessage(role=role, content=content, usage=self._parse_usage(response))
    
    def _prepare_messages(self, messages):
        if messages[0]['role'] == MessageRole.SYSTEM:
            self._system_prompt = messages[0]['content']
            messages = messages[1:]
        return messages

    def get_api_params(self, **kwargs):
        params = super().get_api_params(**kwargs)

        # Claude 特定的参数
        if self._system_prompt:
            params['system'] = self._system_prompt

        # 处理 extra_headers
        extra_headers = kwargs.pop('extra_headers', None)
        if extra_headers:
            params['extra_headers'] = extra_headers

        return params

    def get_completion(self, messages: list[Dict[str, Any]], **kwargs) -> AIMessage:
        if not self._client:
            self._client = self._get_client()

        # 获取 API 参数
        api_params = self.get_api_params(**kwargs)

        message = self._client.messages.create(
            messages=messages,
            **api_params
        )
        return message
