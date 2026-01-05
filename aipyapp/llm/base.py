#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import random
import hashlib
import base64
from dataclasses import dataclass
import socket
from enum import Enum
from collections import Counter
from abc import ABC, abstractmethod
from typing import Union, List, Dict, Any, Literal

from loguru import logger
import httpx
import openai
from pydantic import BaseModel, Field
from .config import ClientConfig


class TextItem(BaseModel):
    type: Literal['text'] = 'text'
    text: str


class ImageUrl(BaseModel):
    url: str


class ImageItem(BaseModel):
    type: Literal['image-url'] = 'image-url'
    image_url: ImageUrl


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    ERROR = "error"


class Message(BaseModel):
    role: MessageRole
    content: str | None
    _mid_cache: str | None = None

    def dict(self):
        return {'role': self.role.value, 'content': self.content}

    @property
    def mid(self):
        if self._mid_cache is None:
            hash_bytes = hashlib.md5(self.model_dump_json().encode('utf-8')).digest()
            self._mid_cache = base64.urlsafe_b64encode(hash_bytes[:8]).decode('utf-8').rstrip('=')
        return self._mid_cache


class UserMessage(Message):
    role: Literal[MessageRole.USER] = MessageRole.USER
    content: Union[str, List[Union[TextItem, ImageItem]]]

    @property
    def content_str(self):
        if isinstance(self.content, str):
            return self.content
        contents = []
        for item in self.content:
            if item.type == 'text':
                contents.append(item.text)
            elif item.type == 'image-url':
                contents.append(item.image_url.url)
        return '\n'.join(contents)


class SystemMessage(Message):
    role: Literal[MessageRole.SYSTEM] = MessageRole.SYSTEM


class ToolMessage(Message):
    role: Literal[MessageRole.TOOL] = MessageRole.TOOL
    tool_call_id: str

    def dict(self):
        return {'role': self.role.value, 'content': self.content, 'tool_call_id': self.tool_call_id}


class AIMessage(Message):
    role: Literal[MessageRole.ASSISTANT] = MessageRole.ASSISTANT
    reason: str | None = None
    finish_reason: str | None = None
    usage: Counter = Field(default_factory=Counter)
    tool_calls: List[Any] | None = None

    def dict(self):
        d = {'role': self.role.value, 'content': self.content}
        # if self.finish_reason:
        #    d['finish_reason'] = self.finish_reason # 这会导致Mistral报错
        if self.tool_calls:
            d['tool_calls'] = [tc.model_dump() if hasattr(tc, 'model_dump') else tc.dict() if hasattr(tc, 'dict') else tc for tc in self.tool_calls]
        # d['reasoning_content'] = self.reason
        return d


class ErrorMessage(Message):
    role: Literal[MessageRole.ERROR] = MessageRole.ERROR
    status_code: int | None = None


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_base: float = 1.0
    backoff_factor: float = 2.0
    jitter: float = 1.0

    def backoff(self, attempt: int) -> float:
        # Exponential backoff with jitter
        delay = self.backoff_base * (self.backoff_factor ** (attempt - 1))
        delay += random.uniform(0, self.jitter)
        return delay


class BaseClient(ABC):
    MODEL = None
    BASE_URL = None
    TEMPERATURE = 0.5

    def __init__(self, config: ClientConfig):
        self.config = config
        self.log = logger.bind(src='llm', name=config.name)
        self.console = None
        self._client = None
        self._retry = RetryConfig()

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model or self.MODEL

    @property
    def base_url(self) -> str:
        return self.config.base_url or self.BASE_URL

    @property
    def max_tokens(self) -> int | None:
        return self.config.max_tokens

    def get_api_params(self, **kwargs) -> dict:
        """
        生成 API 调用参数

        只处理通用参数，子类可以重载此方法来添加特定参数
        """
        params = {}

        # 只处理已知的通用参数
        if self.model:
            params["model"] = self.model
        if self.config.max_tokens:
            params["max_tokens"] = self.config.max_tokens
        if self.config.temperature is not None:
            params["temperature"] = self.config.temperature
        if self.config.stream:
            params["stream"] = self.config.stream

        return params

    def __repr__(self):
        return f"{self.name}/{self.config.type}:{self.model}"

    def usable(self):
        return self.model

    def _get_client(self):
        return self._client

    @abstractmethod
    def get_completion(self, messages: list[Dict[str, Any]], **kwargs) -> AIMessage:
        pass

    def _prepare_messages(self, messages: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        return messages

    @abstractmethod
    def _parse_usage(self, response) -> Counter:
        pass

    @abstractmethod
    def _parse_stream_response(self, response, stream_processor) -> AIMessage:
        pass

    @abstractmethod
    def _parse_response(self, response) -> AIMessage:
        pass

    def __call__(self, messages: list[Dict[str, Any]], stream_processor=None, **kwargs) -> AIMessage | ErrorMessage:
        messages = self._prepare_messages(messages)
        start = time.time()
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self.get_completion(messages, **kwargs)
                if self.config.stream:
                    msg = self._parse_stream_response(response, stream_processor)
                else:
                    msg = self._parse_response(response)
                break
            except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.HTTPStatusError, httpx.ConnectError, openai.APIConnectionError, openai.APITimeoutError) as e:
                delay = self._retry.backoff(attempt)
                self._log_retry(attempt, e, delay)
                time.sleep(delay)
                if attempt >= self._retry.max_attempts:
                    self.log.exception(f"{self.name} API call failed after {attempt} attempt(s)", e=e)
                    return ErrorMessage(content=f"{e} (attempts={attempt})")

            except openai.APIStatusError as e:
                self.log.exception(f"{self.name} API call failed with status code {e.status_code}", e=e)
                return ErrorMessage(content=e.response.text, status_code=e.status_code)
            except Exception as e:
                self.log.exception((f"{self.name} API call encountered non-retryable error on attempt {attempt}"), e=e)
                return ErrorMessage(content=f"{e} (attempts={attempt})")

        msg.usage['time'] = int(time.time() - start)
        msg.usage['retries'] = attempt - 1
        if not msg.content:
            self.log.warning("Got empty LLM response")
        return msg

    def _log_retry(self, attempt: int, e: Exception, delay: float) -> None:
        """Log retry info to logger and print to terminal."""
        msg = f"{self.name} API error attempt {attempt}/{self._retry.max_attempts}, retrying in {delay:.2f}s: {e}"
        self.log.warning(msg)
        try:
            print(msg, flush=True)
        except (BrokenPipeError, OSError):
            pass
