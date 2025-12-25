#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""LLM 响应解析模块 - 专注于纯解析，不包含业务验证"""

import re
import json
from typing import List, Dict, Any, Literal
from enum import Enum
from uuid import uuid4

import yaml
from loguru import logger
from pydantic import BaseModel, ValidationError, Field

from .types import Errors
from .blocks import CodeBlock
from .toolcalls import ToolCall, ToolName, ToolSource
from .chat import ChatMessage

FRONT_MATTER_PATTERN = r"^\s*---\s*\n(.*?)\n---\s*"

BLOCK_PATTERN = re.compile(
    r'<!--\s*Block-Start:\s*(\{.*?\})\s*-->\s*(?P<ticks>`{3,})(\w+)?\s*\n(.*?)\n(?P=ticks)\s*<!--\s*Block-End:\s*(\{.*?\})\s*-->',
    re.DOTALL
)
TOOLCALL_PATTERN = re.compile(r'<!--\s*ToolCall:\s*(\{.*?\})\s*-->')

class ParseErrorType(str, Enum):
    """解析错误类型"""
    JSON_DECODE_ERROR = "json_decode_error"
    INVALID_FORMAT = "invalid_format"
    PYDANTIC_VALIDATION_ERROR = "pydantic_validation_error"


class ParseError(BaseModel):
    """解析错误"""
    error_type: ParseErrorType
    message: str
    raw_content: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    
    def __str__(self):
        return f"[{self.error_type.value}] {self.message}"

class TaskCompleted(BaseModel):
    """任务完成"""
    completed: Literal[True] = Field(description="Task completed")
    confidence: float = Field(description="Confidence in the quality of the completion")

class TaskCannotContinue(BaseModel):
    """任务无法继续"""
    completed: Literal[False] = Field(description="Task cannot continue")
    status: Literal['refused', 'need_info', 'failed'] = Field(description="Status of the task")
    reason: str | None = Field(default=None, description="Reason for the task status")
    suggestion: str | None = Field(default=None, description="Suggestion to resolve the issue")

class FrontMatter(BaseModel):
    """Front Matter 数据"""
    task_status: TaskCompleted | TaskCannotContinue = Field(description="Task status")

class Response(BaseModel):
    """响应对象 - 封装解析结果"""
    message: ChatMessage = Field(default_factory=ChatMessage)
    content_pos: int | None = Field(default=None, description="Content position")
    task_status: TaskCompleted | TaskCannotContinue | None = Field(default=None, description="Task status")
    code_blocks: List[CodeBlock] | None = Field(default=None, description="Code blocks")
    tool_calls: List[ToolCall] | None = Field(default=None, description="Tool calls")
    errors: Errors | None = Field(default=None, description="Errors")
    
    @property
    def log(self):
        return self._log
    
    def should_continue(self) -> bool:
        return self.errors or self.tool_calls
    
    def model_post_init(self, __context: Any):
        self._log = logger.bind(src='Response')

    def __bool__(self):
        return bool(self.code_blocks) or bool(self.tool_calls)
    
    def _add_tool_calls(self, tool_calls: List[ToolCall]):
        if not tool_calls:
            return
        if self.tool_calls:
            self.tool_calls.extend(tool_calls)
        else:
            self.tool_calls = tool_calls

    @classmethod
    def from_message(cls, message: ChatMessage) -> 'Response':
        """
        内部解析方法
        
        Args:
            message: 要解析的消息对象
        """
        self = cls(message=message)
        markdown = message.content
        errors = Errors()
        self._parse_front_matter(markdown)
        if self.content_pos:
            markdown = markdown[self.content_pos:]

        errors.extend(self._parse_code_blocks(markdown))
        
        # 解析工具调用
        errors.extend(self._parse_tool_calls(markdown))
        
        # Parse native tool calls from AIMessage
        if hasattr(message.message, 'tool_calls') and message.message.tool_calls:
            errors.extend(self._parse_native_tool_calls(message.message.tool_calls))

        # Check for silent failure: finish_reason is 'tool_calls' but no tool calls parsed
        if hasattr(message.message, 'finish_reason') and message.message.finish_reason == 'tool_calls':
            if not self.tool_calls and not errors:
                errors.add(
                    "Model finished with 'tool_calls' but no tool calls were found",
                    error_type=ParseErrorType.INVALID_FORMAT
                )

        if errors:
            self.errors = errors
        return self

    def _parse_native_tool_calls(self, native_tool_calls: List[Any]) -> Errors:
        errors = Errors()
        tool_calls = []
        for tc in native_tool_calls:
            try:
                json_str = tc.function.arguments

                # Some providers may send empty arguments for no-arg tool calls.
                # Treat empty/blank/None as an empty JSON object to avoid parse errors.
                if json_str is None:
                    json_str = "{}"
                elif isinstance(json_str, str) and not json_str.strip():
                    json_str = "{}"

                # 尝试修复 JSON 字符串：丢弃最后一个 '}' 之后的内容
                last_brace_idx = json_str.rfind('}')
                if last_brace_idx != -1 and last_brace_idx < len(json_str) - 1:
                    extra = json_str[last_brace_idx+1:]
                    if extra.strip():
                        msg = (
                            "Truncating extra characters after JSON arguments: "
                            f"{extra!r}"
                        )
                        self.log.warning(msg)
                        json_str = json_str[:last_brace_idx+1]

                args = json.loads(json_str)
                name = tc.function.name

                try:
                    tool_name = ToolName(name)
                    arguments = args
                except ValueError:
                    tool_name = ToolName.MCP  # Default to MCP if not recognized
                    arguments = {
                        "action": "call_tool",
                        "name": name,
                        "arguments": args
                    }

                tool_call = ToolCall(
                    name=tool_name,
                    arguments=arguments,
                    id=tc.id,
                    source=ToolSource.OPENAI
                )
                tool_calls.append(tool_call)

            except json.JSONDecodeError as e:
                errors.add(
                    "Invalid JSON in ToolCall",
                    json_str=tc.function.arguments,
                    exception=str(e),
                    error_type=ParseErrorType.JSON_DECODE_ERROR,
                )
            except Exception as e:
                self.log.error(f"Failed to parse native tool call: {e}")
                errors.add(
                    "Failed to parse native tool call",
                    exception=str(e),
                    error_type=ParseErrorType.INVALID_FORMAT
                )

        self._add_tool_calls(tool_calls)
        return errors

    def _parse_code_blocks(self, markdown: str) -> Errors:
        """解析代码块"""
        errors = Errors()
        code_blocks = []
        for match in BLOCK_PATTERN.finditer(markdown):
            start_json, _, lang, content, end_json = match.groups()
            
            # 解析开始标签
            try:
                start_meta = json.loads(start_json)
            except json.JSONDecodeError as e:
                errors.add(
                    "Invalid JSON in Block-Start",
                    json_str=start_json,
                    exception=str(e),
                    position="Block-Start",
                    error_type=ParseErrorType.JSON_DECODE_ERROR,
                )
                continue
            
            # 解析结束标签
            try:
                end_meta = json.loads(end_json)
            except json.JSONDecodeError as e:
                errors.add(
                    "Invalid JSON in Block-End",
                    json_str=end_json,
                    exception=str(e),
                    position="Block-End",
                    error_type=ParseErrorType.JSON_DECODE_ERROR,
                )
                continue
            
            # 检查名称是否一致
            start_name = start_meta.get("name")
            end_name = end_meta.get("name")
            
            if not start_name or start_name != end_name:
                errors.add(
                    "Block-Start and Block-End name mismatch",
                    start_name=start_name,
                    end_name=end_name,
                    error_type=ParseErrorType.INVALID_FORMAT,
                )
                continue
            
            # 创建 CodeBlock 对象，让 Pydantic 处理验证
            try:
                code_block = CodeBlock(
                    name=start_name,
                    lang=lang or "markdown",
                    code=content,
                    path=start_meta.get("path")
                )
                code_blocks.append(code_block)
            except ValidationError as e:
                errors.add(
                    "Failed to create CodeBlock",
                    exception=str(e),
                    error_type=ParseErrorType.PYDANTIC_VALIDATION_ERROR,
                )

        if code_blocks:
            self.code_blocks = code_blocks
        return errors
    
    def _parse_tool_calls(self, markdown: str) -> Errors:
        """解析工具调用"""
        errors = Errors()
        tool_calls = []
        for match in TOOLCALL_PATTERN.finditer(markdown):
            json_str = match.group(1)

            try:
                data = json.loads(json_str)

                # Ensure ID exists
                if "id" not in data:
                    data["id"] = uuid4().hex

                name = data.get("name")

                # Check if it is a known internal tool
                is_internal = False
                try:
                    ToolName(name)
                    is_internal = True
                except ValueError:
                    pass

                if is_internal:
                    data['source'] = ToolSource.AIPY
                    # Internal tool: validate directly
                    tool_call = ToolCall.model_validate(data)
                else:
                    # Unknown tool: treat as MCP tool
                    # Wrap it into MCPToolArgs structure
                    wrapped_data = {
                        "id": data["id"],
                        "name": "MCP",
                        "source": ToolSource.AIPY,
                        "arguments": {
                            "action": "call_tool",
                            "name": name,
                            "arguments": data.get("arguments", {})
                        }
                    }
                    tool_call = ToolCall.model_validate(wrapped_data)

                tool_calls.append(tool_call)

            except json.JSONDecodeError as e:
                errors.add(
                    "Invalid JSON in ToolCall",
                    json_str=json_str,
                    exception=str(e),
                    error_type=ParseErrorType.JSON_DECODE_ERROR,
                )
            except ValidationError as e:
                errors.add(
                    "Invalid ToolCall data",
                    json_str=json_str,
                    exception=str(e),
                    error_type=ParseErrorType.PYDANTIC_VALIDATION_ERROR,
                )
        self._add_tool_calls(tool_calls)
        return errors
    
    def _parse_front_matter(self, md_text: str) -> Errors:
        """
        解析 Markdown 字符串，提取 YAML front matter 和正文内容。

        参数：
            md_text: 包含 YAML front matter 和 Markdown 内容的字符串

        返回：
            (errors, content)：
            - errors 是解析错误，若无 front matter 则为空字典
            - content 是去除 front matter 后的 Markdown 正文字符串
        """
        errors = Errors()
        yaml_dict = None
        match = re.match(FRONT_MATTER_PATTERN, md_text, re.DOTALL)
        if match:
            yaml_str = match.group(1)
            try:
                yaml_dict = yaml.safe_load(yaml_str)
                self.log.info('Front matter', yaml_dict=yaml_dict)
            except yaml.YAMLError:
                self.log.error('Invalid front matter', yaml_str=yaml_str)
                errors.add(
                    "Invalid front matter",
                    yaml_str=yaml_str,
                    error_type=ParseErrorType.INVALID_FORMAT,
                )
            self.content_pos = match.end()

        if yaml_dict:
            try:
                self.task_status = FrontMatter.model_validate({'task_status': yaml_dict}).task_status
            except ValidationError as e:
                self.log.error('Invalid front matter', yaml_dict=yaml_dict, exception=str(e), errors=e.errors())
                errors.add(
                    "Invalid front matter",
                    yaml_dict=yaml_dict,
                    exception=str(e),
                    errors = e.errors(),
                    error_type=ParseErrorType.PYDANTIC_VALIDATION_ERROR,
                )

        return errors