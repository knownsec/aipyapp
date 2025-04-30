#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
from collections import Counter
from .base import BaseClient, BaseResponse
from .session import ChatMessage
from .. import T

class OllamaResponse(BaseResponse):
    def _parse_usage(self, response):
        ret = {'input_tokens': response['prompt_eval_count'], 'output_tokens': response['eval_count']}
        ret['total_tokens'] = ret['input_tokens'] + ret['output_tokens']
        return ret

    def parse_stream(self):
        usage = Counter()
        full_response = ''
        for chunk in self.response.iter_lines():
            chunk = chunk.decode(encoding='utf-8')
            msg = json.loads(chunk)
            if msg['done']:
                usage = self._parse_usage(msg)
                break

            if 'message' in msg and 'content' in msg['message'] and msg['message']['content']:
                content = msg['message']['content']
                full_response += content
                yield content
        
        self.message = ChatMessage(role="assistant", content=full_response, usage=usage)

    def parse(self):
        response = self.response.json()
        msg = response["message"]
        self.message = ChatMessage(role=msg['role'], content=msg['content'], usage=self._parse_usage(response))
    

# https://github.com/ollama/ollama/blob/main/docs/api.md
class OllamaClient(BaseClient):
    RESPONSE_CLASS = OllamaResponse

    def __init__(self, config):
        super().__init__(config)
        self._session = requests.Session()
        if self._proxy:
            self._session.proxies = {
                'http': self._proxy,
                'https': self._proxy,
            }

    def usable(self):
        return super().usable() and self._base_url

    def get_completion(self, messages):
        try:
            response = self._session.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": self._stream,
                    "options": {"num_predict": self.max_tokens}
                },
                timeout=self._timeout,
                **self._params
            )
            response.raise_for_status()
        except Exception as e:
            self.log.exception('Error calling Ollama API')
            response = None
        return response
