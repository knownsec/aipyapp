#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import anthropic
from collections import Counter

from .base import BaseClient, BaseResponse
from .session import ChatMessage
from .. import T

# https://docs.anthropic.com/en/api/messages
class ClaudeResponse(BaseResponse):
    def _parse_usage(self, response):
        usage = response.usage
        ret = {'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens}
        ret['total_tokens'] = ret['input_tokens'] + ret['output_tokens']
        return ret

    def parse_stream(self):
        usage = Counter()
        full_response = ''
        for event in self.response:
            if hasattr(event, 'delta') and hasattr(event.delta, 'text') and event.delta.text:
                content = event.delta.text
                full_response += content
                yield content
            elif hasattr(event, 'message') and hasattr(event.message, 'usage') and event.message.usage:
                usage['input_tokens'] += getattr(event.message.usage, 'input_tokens', 0)
                usage['output_tokens'] += getattr(event.message.usage, 'output_tokens', 0)
            elif hasattr(event, 'usage') and event.usage:
                usage['input_tokens'] += getattr(event.usage, 'input_tokens', 0)
                usage['output_tokens'] += getattr(event.usage, 'output_tokens', 0)

        usage['total_tokens'] = usage['input_tokens'] + usage['output_tokens']
        self.message = ChatMessage(role="assistant", content=full_response, usage=usage)

    def parse(self):
        content = self.response.content[0].text
        role = self.response.role
        self.message = ChatMessage(role=role, content=content, usage=self._parse_usage(self.response))
    
class ClaudeClient(BaseClient):
    MODEL = "claude-3-7-sonnet-20250219"
    RESPONSE_CLASS = ClaudeResponse

    def __init__(self, config):
        super().__init__(config)
        self._system_prompt = None

    def _get_client(self):
        # https://github.com/anthropics/anthropic-sdk-python?tab=readme-ov-file#configuring-the-http-client
        if self._proxy:
            return anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout,
                                       http_client=anthropic.DefaultHttpxClient(proxy=self._proxy))
        return anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout)
    
    def usable(self):
        return super().usable() and self._api_key
    
    def add_system_prompt(self, history, system_prompt):
        self._system_prompt = system_prompt

    def get_completion(self, messages):
        if not self._client:
            self._client = self._get_client()
        try:
            message = self._client.messages.create(
                model = self._model,
                messages = messages,
                stream=self._stream,
                system=self._system_prompt,
                max_tokens = self.max_tokens,
                **self._params
            )
        except Exception as e:
            self.log.exception('Error calling Claude API')
            message = None
        return message
