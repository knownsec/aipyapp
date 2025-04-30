import openai
from collections import Counter

from .base import BaseClient, BaseResponse
from .session import ChatMessage

class OpenAIResponse(BaseResponse):
    def _parse_usage(self, usage):
        usage = Counter({'total_tokens': usage.total_tokens,
                'input_tokens': usage.prompt_tokens,
                'output_tokens': usage.completion_tokens})
        return usage
    
    def parse_stream(self):
        full_response = ''
        usage = Counter()
        for chunk in self.response:
            if hasattr(chunk, 'usage') and chunk.usage is not None:
                usage = self._parse_usage(chunk.usage)

            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield content

        self.message = ChatMessage(role="assistant", content=full_response, usage=usage)

    def parse(self):
        message = self.response.choices[0].message
        reason = getattr(message, "reasoning_content", None)
        self.message = ChatMessage(
            role=message.role,
            content=message.content,
            reason=reason,
            usage=self._parse_usage(self.response.usage)
        )

# https://platform.openai.com/docs/api-reference/chat/create
# https://api-docs.deepseek.com/api/create-chat-completion
class OpenAIBaseClient(BaseClient):
    RESPONSE_CLASS = OpenAIResponse

    def usable(self):
        return super().usable() and self._api_key
    
    def _get_client(self):
        # https://github.com/openai/openai-python?tab=readme-ov-file#configuring-the-http-client
        if self._proxy:
            return openai.Client(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout,
                             http_client=openai.DefaultHttpxClient(proxy=self._proxy))
        return openai.Client(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout)
    
    def get_completion(self, messages):
        if not self._client:
            self._client = self._get_client()
        try:
            response = self._client.chat.completions.create(
                model = self._model,
                messages = messages,
                stream=self._stream,
                max_tokens = self.max_tokens,
                **self._params
            )
        except Exception as e:
            self.log.exception('Error calling OpenAI API')
            response = None
        return response
