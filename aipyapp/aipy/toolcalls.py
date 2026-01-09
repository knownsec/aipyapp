#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""工具调用系统模块"""

from __future__ import annotations
import json
import uuid
from enum import Enum
from typing import Union, List, Dict, Any, Optional, TYPE_CHECKING

from pydantic.aliases import AliasChoices
from pydantic import BaseModel, model_validator, Field, ValidationError
from promptabs import SurveyRunner

from .types import Error
from .blocks import CodeBlock
from .features import PromptFeatures
from ..exec import ExecResult, ProcessResult, PythonResult

if TYPE_CHECKING:
    from .task import Task


class ToolSource(str, Enum):
    """Tool source"""

    OPENAI = "openai"
    AIPY = "aipy"


class ToolName(str, Enum):
    """Tool name"""

    EDIT = "AIPY_Edit"
    EXEC = "AIPY_Exec"
    MCP = "MCP"
    SUBTASK = "AIPY_SubTask"
    SURVEY = "AIPY_Survey"


class ExecLang(str, Enum):
    """Executable languages"""

    PYTHON = "python"
    HTML = "html"
    BASH = "bash"
    POWERSHELL = "powershell"
    APPLESCRIPT = "applescript"
    JAVASCRIPT = "javascript"
    MARKDOWN = "markdown"


class ToolResult(BaseModel):
    """Tool result"""

    error: Error | None = Field(title="Tool error", default=None)

    def to_json(self):
        return self.model_dump_json(exclude_none=True, exclude_unset=True)


class ExecToolArgs(BaseModel):
    """
    Execute code

    You can provide executable code in either of the following ways:
    - Inline code: Provide the full source code directly in the `code` argument.
    - Referenced code block: Use the `name` argument to reference a code block that is defined in the output message.

    Code block resolution rules:
    - If `code` is NOT provided: `name` must refer to an defined code block (either in the current or previous output message) or execution must fail.
    - If code IS provided: A code block identified by name will be created or updated using the provided code.The updated code block becomes the source of truth for execution.

    Execution rules:
    - Python code is always executable and does not require a file path.
    - Non-Python code must include a valid `path` attribute that points to the executable file.
    - The referenced code block must exactly match the given `name`.
    """

    name: Optional[str] = Field(None, title="Code block name", description="Code block name to execute", min_length=1, strip_whitespace=True)
    code: Optional[str] = Field(None, title="Code content", description="Code content to execute. Required for new blocks.")
    lang: Optional[ExecLang] = Field(ExecLang.PYTHON, title="Programming language", description="Programming language (python, bash, markdown, etc.). Defaults to python. If not python, must be specified.")
    path: Optional[str] = Field(None, title="File path", description="File path to save the code. Optional.")


class ExecToolResult(ToolResult):
    """Exec tool result"""

    block_name: str = Field(title="Code block name executed", min_length=1, strip_whitespace=True)
    result: ExecResult | ProcessResult | PythonResult | None = Field(title="Execution result", default=None)


class EditToolArgs(BaseModel):
    """
    Modify existing code blocks incrementally. The code block must exist before calling this tool.
    Use this to fix errors or make small changes without rewriting the entire block.
    Provide the exact 'old' string to replace and the 'new' string.
    """

    name: str = Field(title="Code block name", description="Code block name to edit", min_length=1, strip_whitespace=True)
    old: str = Field(title="Code to replace", description="Exact string to find and replace (must match exactly including whitespace)", min_length=1)
    new: str = Field(title="Replacement code", description="Replacement string (can be empty for deletion)")
    replace_all: Optional[bool] = Field(False, title="Replace all occurrences", description="Replace all occurrences. false: Replace only the first occurrence (safer). true: Replace all occurrences.")


class EditToolResult(ToolResult):
    """Edit tool result"""

    block_name: str = Field(title="Code block name edited", min_length=1, strip_whitespace=True)
    new_version: int | None = Field(title="New version number", gt=1, default=None)


class MCPToolArgs(BaseModel):
    """MCP tool arguments"""

    action: str
    name: str
    arguments: Optional[Dict[str, Any]] = {}
    model_config = {'extra': 'allow'}


class MCPToolResult(ToolResult):
    """MCP tool result"""

    result: Dict[str, Any] = Field(default_factory=dict)


class SubTaskArgs(BaseModel):
    """
    Delegate a complex sub-problem to a subtask agent.
    Use this when a task is too complex to handle in a single step or requires a specialized agent context.
    """

    instruction: str = Field(title="SubTask instruction", description="Detailed instruction for the subtask", min_length=1, strip_whitespace=True)
    title: Optional[str] = Field(default=None, title="SubTask title", description="Title of the subtask")


class SubTaskResult(ToolResult):
    """SubTask tool result"""

    result: Optional[str] = Field(default=None, title="SubTask result content")


class SurveyToolArgs(BaseModel):
    """
    Collect information from the user via a survey form.
    You MUST generate the survey code block (JSON format) in the response BEFORE calling this tool.
    """

    name: str = Field(title="Survey code block name", description="Name of the survey code block to execute", min_length=1, strip_whitespace=True)


class SurveyToolResult(ToolResult):
    """Survey tool result"""

    block_name: str = Field(title="Survey code block name", min_length=1, strip_whitespace=True)
    answers: Dict[str, Any] = Field(title="Survey answers", default_factory=dict)
    feedback: Optional[str] = Field(default=None, title="User feedback")


class ToolCall(BaseModel):
    """Tool call"""

    id: str = Field(title='Unique ID for this ToolCall')
    source: ToolSource = Field(title='Tool source')
    name: ToolName
    arguments: Union[ExecToolArgs, EditToolArgs, MCPToolArgs, SubTaskArgs, SurveyToolArgs] = Field(validation_alias=AliasChoices("arguments", "input"), title="Tool arguments")

    @model_validator(mode='before')
    @classmethod
    def alias_name(cls, values: Dict[str, Any]):
        if isinstance(values, dict):
            if "name" not in values and "action" in values:
                values["name"] = values.pop("action")
        return values

    def __str__(self):
        return f"ToolCall(name='{self.name}', args={self.arguments})"

    def __repr__(self):
        return self.__str__()

    def is_openai(self) -> bool:
        return self.source == ToolSource.OPENAI

    def is_aipy(self) -> bool:
        return self.source == ToolSource.AIPY


class ToolCallResult(BaseModel):
    """Tool call result"""

    id: str = Field(title='Unique ID for this ToolCall')
    source: ToolSource = Field(title='Tool source')
    name: ToolName
    result: Union[ExecToolResult, EditToolResult, MCPToolResult, SubTaskResult, SurveyToolResult, ToolResult] = Field(title="Tool result")

    def is_openai(self) -> bool:
        return self.source == ToolSource.OPENAI

    def is_aipy(self) -> bool:
        return self.source == ToolSource.AIPY


class ToolCallProcessor:
    """工具调用处理器 - 高级接口"""

    def __init__(self, task: 'Task'):
        self.task = task
        self.log = task.get_logger('ToolCallProcessor')
        self.processed_ids = set()

    def process(self, tool_calls: List[ToolCall]) -> List[ToolCallResult]:
        """
        处理工具调用列表

        Args:
            tool_calls: ToolCall 对象列表

        Returns:
            List[ToolCallResult]: 包含所有执行结果的列表
        """
        results = []
        failed_blocks = set()  # 记录编辑失败的代码块

        for tool_call in tool_calls:
            # Check for duplicate tool call ID
            if tool_call.id in self.processed_ids:
                self.log.warning(f"Duplicate tool call ID detected: {tool_call.id}")
                results.append(ToolCallResult(id=tool_call.id, name=tool_call.name, source=tool_call.source, result=ToolResult(error=Error.new(f"Tool call {tool_call.id} has already been executed. Please do not reuse tool call IDs."))))
                continue

            self.processed_ids.add(tool_call.id)

            name = tool_call.name
            if name == ToolName.EXEC:
                # 如果这个代码块之前编辑失败，跳过执行
                block_name = getattr(tool_call.arguments, 'name', None)
                if block_name and block_name in failed_blocks:
                    error = Error.new('Execution skipped: previous edit of the block failed', block_name=block_name)
                    results.append(ToolCallResult(name=name, id=tool_call.id, result=ExecToolResult(block_name=block_name, error=error)))
                    continue

            # 执行工具调用
            result = self.call_tool(self.task, tool_call)
            results.append(result)

            if name == ToolName.EDIT and result.result.error:
                block_name = getattr(tool_call.arguments, 'name', None)
                if block_name:
                    failed_blocks.add(block_name)

        return results

    def call_tool(self, task: 'Task', tool_call: ToolCall) -> ToolCallResult:
        """
        执行工具调用

        Args:
            tool_call: ToolCall 对象

        Returns:
            ToolResult: 执行结果
        """
        task.emit('tool_call_started', tool_call=tool_call)
        if tool_call.name == ToolName.EXEC:
            result = self._call_exec(task, tool_call)
        elif tool_call.name == ToolName.EDIT:
            result = self._call_edit(task, tool_call)
        elif tool_call.name == ToolName.MCP:
            result = self._call_mcp(task, tool_call)
        elif tool_call.name == ToolName.SUBTASK:
            result = self._call_subtask(task, tool_call)
        elif tool_call.name == ToolName.SURVEY:
            result = self._call_survey(task, tool_call)
        else:
            result = ToolResult(error=Error.new('Unknown tool'))

        toolcall_result = ToolCallResult(id=tool_call.id, source=tool_call.source, name=tool_call.name, result=result)
        task.emit('tool_call_completed', result=toolcall_result)
        return toolcall_result

    def _call_edit(self, task: 'Task', tool_call: ToolCall) -> EditToolResult:
        """执行 Edit 工具"""
        args = tool_call.arguments
        if not isinstance(args, EditToolArgs):
            return EditToolResult(block_name="unknown", error=Error.new("Invalid arguments for Edit tool"))

        block_name = args.name

        original_block = task.blocks.get(block_name)
        if not original_block:
            return EditToolResult(block_name=block_name, error=Error.new("Code block not found"))

        old_str = args.old
        new_str = args.new
        replace_all = args.replace_all

        # 检查是否找到匹配的字符串
        if old_str not in original_block.code:
            return EditToolResult(block_name=block_name, error=Error.new(f"No match found for {old_str[:50]}..."))

        # 检查匹配次数
        match_count = original_block.code.count(old_str)
        if match_count > 1 and not replace_all:
            return EditToolResult(block_name=block_name, error=Error.new(f"Multiple matches found for {old_str[:50]}...", suggestion="set replace_all: true or provide more specific context"))

        # 执行替换生成新代码
        new_code = original_block.code.replace(old_str, new_str, -1 if replace_all else 1)

        # 创建新的代码块（版本号+1）
        new_block = original_block.model_copy(update={"version": original_block.version + 1, "code": new_code, "deps": original_block.deps.copy() if original_block.deps else {}})
        new_block.co = None  # 重置编译对象
        task.blocks.add_block(new_block, validate=False)
        return EditToolResult(block_name=block_name, new_version=new_block.version)

    def _call_exec(self, task: 'Task', tool_call: ToolCall) -> ExecToolResult:
        """执行 Exec 工具"""
        args = tool_call.arguments
        if not isinstance(args, ExecToolArgs):
            return ExecToolResult(block_name=getattr(args, 'name', 'unknown'), error=Error.new("Invalid arguments for Exec tool"))

        block_name = args.name

        # 如果提供了代码，则创建或更新代码块
        if args.code:
            # 如果没有提供名称，生成一个临时名称
            final_name = block_name or f"exec_{uuid.uuid4().hex[:8]}"

            # 确定语言
            lang = args.lang.value if args.lang else "python"

            new_block = CodeBlock(name=final_name, code=args.code, lang=lang, path=args.path)
            task.blocks.add_block(new_block, validate=False)
            block = new_block
            block_name = final_name
        else:
            # 如果没有提供代码，必须提供名称
            if not block_name:
                return ExecToolResult(block_name="unknown", error=Error.new("Block name is required when no code is provided."))

            # 获取已有代码块
            block = task.blocks.get(block_name)
            if not block:
                return ExecToolResult(block_name=block_name, error=Error.new("Code block not found. Please provide 'code' argument."))

        # 执行代码块
        try:
            result = task.runner(block)
            return ExecToolResult(block_name=block_name, result=result)
        except Exception as e:
            self.log.exception(f"Execution failed with exception: {e}")
            return ExecToolResult(block_name=block_name, error=Error.new("Execution failed with exception", exception=str(e)))

    def _call_mcp(self, task: 'Task', tool_call: ToolCall) -> MCPToolResult:
        """执行 MCP 工具"""
        mcp_args = tool_call.arguments
        # 使用属性访问，而不是将 Pydantic 模型当作字典
        name = getattr(mcp_args, 'name', None)
        arguments = getattr(mcp_args, 'arguments', {}) or {}
        result = task.mcp.call_tool(name, arguments)
        return MCPToolResult(result=result)

    def _call_subtask(self, task: 'Task', tool_call: ToolCall) -> SubTaskResult:
        """执行 SubTask 工具"""
        args = tool_call.arguments
        if not isinstance(args, SubTaskArgs):
            return SubTaskResult(error=Error.new("Invalid arguments for SubTask tool"))

        try:
            # 创建子任务
            response = task.run_subtask(args.instruction, args.title)
            content = response.message.content
            if isinstance(content, list):
                # 简单处理多模态内容，只提取文本
                text_parts = []
                for item in content:
                    text = getattr(item, 'text', None)
                    if text:
                        text_parts.append(text)
                content = "\n".join(text_parts)

            return SubTaskResult(result=str(content) if content is not None else None)
        except Exception as e:
            self.log.exception(f"SubTask failed with exception: {e}")
            return SubTaskResult(error=Error.new("SubTask failed with exception", exception=str(e)))

    def _call_survey(self, task: 'Task', tool_call: ToolCall) -> SurveyToolResult:
        """执行 Survey 工具"""
        args = tool_call.arguments
        if not isinstance(args, SurveyToolArgs):
            return SurveyToolResult(block_name="unknown", error=Error.new("Invalid arguments for Survey tool"))

        block_name = args.name

        block = task.blocks.get(block_name)
        if not block:
            return SurveyToolResult(block_name=block_name, error=Error.new("Survey code block not found"))

        try:
            # 创建并运行问卷
            runner = SurveyRunner.from_json_string(block.code)
            results = runner.run()

            if not results:
                tr = SurveyToolResult(block_name=block_name, error=Error.new("User did not complete the survey"))
            else:
                tr = SurveyToolResult(block_name=block_name, answers=results.answers, feedback=results.feedback)

        except json.JSONDecodeError as e:
            self.log.exception(f"Failed to parse survey JSON: {e}")
            tr = SurveyToolResult(block_name=block_name, error=Error.new("Failed to parse survey JSON", details=str(e)))
        except ValidationError as e:
            self.log.exception(f"Survey validation error: {e}")
            tr = SurveyToolResult(block_name=block_name, error=Error.new("Survey validation error", details=e.errors()))
        except Exception as e:
            self.log.exception(f"Survey execution failed: {e}")
            tr = SurveyToolResult(block_name=block_name, error=Error.new("Survey execution failed", exception=str(e)))
        return tr


def inline_refs(schema: dict) -> dict:
    defs = schema.get("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if ref.startswith("#/$defs/"):
                    key = ref.split("/")[-1]
                    return resolve(defs[key])
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        elif isinstance(node, list):
            return [resolve(x) for x in node]
        else:
            return node

    out = resolve(schema)
    out.pop("$defs", None)
    return out


def get_internal_tools_openai_format(features: PromptFeatures) -> List[Dict[str, Any]]:
    """Generate OpenAI tool definitions for internal tools."""
    tools_map = [(ToolName.EDIT, EditToolArgs)]

    if features.has('exec_code'):
        tools_map.append((ToolName.EXEC, ExecToolArgs))

    if features.has('survey'):
        tools_map.append((ToolName.SURVEY, SurveyToolArgs))

    if features.has('subtask'):
        tools_map.append((ToolName.SUBTASK, SubTaskArgs))

    tools = []
    for name, args_cls in tools_map:
        schema = args_cls.model_json_schema()
        schema = inline_refs(schema)
        schema.pop("title", None)
        schema.pop("description", None)

        tools.append({"type": "function", "function": {"name": name.value, "description": (args_cls.__doc__ or "").strip(), "parameters": schema}})

    return tools
