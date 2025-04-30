#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from abc import ABC, abstractmethod

from loguru import logger

from .. import Stoppable, T

class BaseResponse(ABC):
    def __init__(self, response, stream=True):
        self.response = response
        self.stream = stream
        self.message = None

    @abstractmethod
    def _parse_usage(self, response):
        pass
    
    @abstractmethod
    def parse_stream(self):
        pass
    
    @abstractmethod
    def parse(self):
        pass

class BaseClient(ABC, Stoppable):
    MODEL = None
    BASE_URL = None
    MAX_TOKENS = 8192
    PARAMS = {}
    RESPONSE_CLASS = BaseResponse

    def __init__(self, config):
        super().__init__()
        self.name = None
        self.console = None
        self.max_tokens = config.get("max_tokens") or self.MAX_TOKENS
        self._model = config.get("model") or self.MODEL
        self._timeout = config.get("timeout")
        self._api_key = config.get("api_key")
        self._base_url = config.get("base_url") or self.BASE_URL
        self._proxy = config.get("proxy")
        self._stream = config.get("stream", True)
        self._client = None
        self._params = {}
        if self.PARAMS:
            self._params.update(self.PARAMS)
        temperature = config.get("temperature")
        if temperature != None and temperature >= 0 and temperature <= 1:
            self._params['temperature'] = temperature
        self.log = logger.bind(src='client', name=self.name)
        
    def __repr__(self):
        return f"{self.__class__.__name__}<{self.name}>: ({self._model}, {self._base_url})"

    def usable(self):
        return self._model
    
    def _get_client(self):
        return self._client
    
    @abstractmethod
    def get_completion(self, messages):
        pass
        
    def add_system_prompt(self, messages, system_prompt):
        messages.append({"role": "system", "content": system_prompt})
    
    def __call__(self, messages, prompt, system_prompt=None):
        if system_prompt:
            self.add_system_prompt(messages, system_prompt)
        messages.append({"role": "user", "content": prompt})

        response = self.get_completion(messages)
        if response:
            response = self.RESPONSE_CLASS(response, self._stream)
        return response
    
