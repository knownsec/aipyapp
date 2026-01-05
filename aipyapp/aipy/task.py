#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import json
import uuid
import zlib
import base64
import weakref
from typing import Any, Dict, List, Union, TYPE_CHECKING
from pathlib import Path
from functools import wraps
from importlib.resources import read_text

from pydantic import BaseModel, Field, ValidationError, field_serializer, field_validator
from loguru import logger

from .. import T, __respkg__, Stoppable, TaskPlugin
from ..exec import BlockExecutor
from ..llm import SystemMessage, UserMessage
from .runtime import CliPythonRuntime
from .utils import safe_rename, validate_file
from .events import TypedEventBus, BaseEvent
from .multimodal import MMContent
from .context import ContextManager, ContextData
from .toolcalls import ToolCallProcessor, get_internal_tools_openai_format
from .chat import MessageStorage, ChatMessage
from .step import Step, StepData
from .blocks import CodeBlocks
from .client import Client
from .response import Response
from .prompts import Prompts
from .features import PromptFeatures

if TYPE_CHECKING:
    from .taskmgr import TaskManager

MAX_DEPTH = 3
MAX_ROUNDS = 16
TASK_VERSION = 20251212

CONSOLE_WHITE_HTML = read_text(__respkg__, "console_white.html")
CONSOLE_CODE_HTML = read_text(__respkg__, "console_code.html")


def with_task_context(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        with logger.contextualize(task_id=self.task_id):
            return func(self, *args, **kwargs)

    return wrapper


class TaskError(Exception):
    """Task 异常"""

    pass


class TaskInputError(TaskError):
    """Task 输入异常"""

    def __init__(self, message: str, original_error: Exception = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class TaskStateError(TaskError):
    """Task 状态异常"""

    def __init__(self, message: str, **kwargs):
        self.message = message
        self.data = kwargs
        super().__init__(self.message)


class TaskData(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    version: int = Field(default=TASK_VERSION, frozen=True)
    depth: int = Field(default=0)
    steps: List[StepData] = Field(default_factory=list)
    blocks: CodeBlocks = Field(default_factory=CodeBlocks)
    context: ContextData = Field(default_factory=ContextData)
    message_storage: MessageStorage = Field(default_factory=MessageStorage)
    events: List[BaseEvent.get_subclasses_union()] = Field(default_factory=list)
    session: Dict[str, Any] = Field(default_factory=dict, exclude=True)
    tools: List[Dict[str, Any]] = Field(default_factory=list)

    @field_serializer('events')
    def serialize_events(self, events: List, _info):
        """序列化时压缩 events 字段"""
        if not events:
            return None
        # 将 events 序列化为 JSON 字符串
        json_str = json.dumps([e.model_dump() for e in events], ensure_ascii=False)
        # 使用 zlib 压缩
        compressed = zlib.compress(json_str.encode('utf-8'), level=9)
        # Base64 编码以便存储为字符串
        return base64.b64encode(compressed).decode('ascii')

    @field_validator('events', mode='before')
    @classmethod
    def deserialize_events(cls, v):
        """反序列化时解压 events 字段"""
        if v is None or v == []:
            return []
        if isinstance(v, list):
            # 已经是列表，直接返回（可能来自内存中的对象）
            return v
        if isinstance(v, str):
            # 从压缩字符串恢复
            try:
                compressed = base64.b64decode(v.encode('ascii'))
                json_str = zlib.decompress(compressed).decode('utf-8')
                events_data = json.loads(json_str)
                # 需要重新构造事件对象
                return events_data  # Pydantic 会自动验证和构造
            except Exception as e:
                logger.warning(f"Failed to decompress events: {e}")
                return []
        return v

    def add_step(self, step: StepData):
        self.steps.append(step)


class Task(Stoppable):
    def __init__(self, manager: TaskManager, data: TaskData | None = None, parent: Task | None = None, inherit_context: bool = False):
        super().__init__()
        if not data:
            data = TaskData()
            data.depth = 1 if not parent else parent.depth + 1

        # Phase 1: Initialize basic attributes (no dependencies)
        self.data = data
        self._parent = weakref.ref(parent) if parent else None
        self.task_id = data.id
        self.manager = manager
        self.settings = manager.settings

        if not parent:
            self.cwd = manager.cwd / self.task_id
            self.shared_dir = self.cwd / "shared"
        else:
            self.cwd = parent.cwd / self.task_id
            self.shared_dir = parent.shared_dir
        self.log = self.create_logger()

        self.lang = None
        self.gui = manager.settings.gui
        self._saved = False
        self.max_rounds = manager.settings.get('max_rounds', MAX_ROUNDS)
        self.role = manager.role_manager.current_role

        # Phase 2: Initialize data objects (minimal dependencies)
        self.blocks = data.blocks
        # 如果指定继承上下文且有父任务，则继承父任务的上下文数据
        if inherit_context and parent:
            self.context = parent.context
        else:
            self.context = data.context

        self.message_storage = data.message_storage
        self.events = data.events

        # session: 子任务共享父任务的 session 引用，根任务使用 TaskData 中的 session
        if parent:
            self.session = parent.session
        else:
            self.session = data.session

        # Phase 3: Initialize managers and processors (depend on Phase 2)

        self.context_manager = ContextManager(self.message_storage, self.context, manager.settings.get('context_manager'), task_id=self.task_id)
        self.tool_call_processor = ToolCallProcessor(self)

        # Phase 5: Initialize execution components (depend on task)
        self.mcp = manager.mcp
        self.features = PromptFeatures(self.role.get_features())
        if self.depth >= MAX_DEPTH:
            self.log.warning(f"Task depth {self.depth} exceeds maximum of {MAX_DEPTH}")
            self.features.disable('subtask')
        tools = []
        tools.extend(get_internal_tools_openai_format(self.features))
        if self.mcp:
            mcp_tools = self.mcp.get_openai_tools()
            if mcp_tools:
                tools.extend(mcp_tools)
        self.data.tools = tools

        self.prompts = Prompts(features=self.features)
        self.client_manager = manager.client_manager
        self.runtime = CliPythonRuntime(self)
        self.runner = BlockExecutor(task_id=self.task_id)
        self.runner.set_python_runtime(self.runtime)
        self.client = Client(self)

        # Phase 6: (Cleaners are now initialized in Step class)

        # Phase 7: Initialize plugins (depend on runtime and event_bus)
        self._initialize_plugins(manager)

        # Phase 8: Initialize steps last (depend on almost everything)
        self.steps: List[Step] = [Step(self, step_data) for step_data in data.steps]

        # Subtasks list (runtime only, not serialized)
        self.subtasks: List['Task'] = []

    @with_task_context
    def _initialize_plugins(self, manager: TaskManager):
        """Separate method to initialize plugins, improving clarity and testability"""
        event_bus = TypedEventBus()
        plugins: dict[str, TaskPlugin] = {}

        # Phase 4: Initialize display (depends on event_bus)
        if manager.display_manager:
            self.display = manager.display_manager.create_display_plugin()
            event_bus.add_listener(self.display)
        else:
            self.display = None

        for plugin_name, plugin_data in self.role.plugins.items():
            plugin = manager.plugin_manager.create_task_plugin(plugin_name, plugin_data)
            if not plugin:
                self.log.warning(f"Create task plugin {plugin_name} failed")
                continue
            self.runtime.register_plugin(plugin)
            event_bus.add_listener(plugin)
            plugins[plugin_name] = plugin
        self.plugins = plugins
        self.event_bus = event_bus

    @property
    def parent(self):
        return self._parent() if self._parent else None

    @property
    def depth(self) -> int:
        return self.data.depth

    @property
    def instruction(self):
        return self.steps[0].data.instruction if self.steps else None

    @property
    def start_time(self) -> Union[float, None]:
        if self.steps:
            return self.steps[0].data.start_time
        return None

    @property
    def tools(self):
        return self.data.tools

    def set_feature(self, name: str, value: bool):
        self.features.set(name, value)

    def has_feature(self, name: str) -> bool:
        return self.features.has(name)

    def create_logger(self):
        task_logger = logger.bind(src='task', task_id=self.task_id)
        task_logger.add(self.cwd / "task.log", level="INFO", format="{time:YYYY-MM-DD HH:mm:ss!UTC} | {level} | {message} | {extra}", filter=lambda record: record["extra"].get("task_id") == self.task_id)
        return task_logger

    def get_logger(self, component: str, **kwargs):
        """为子组件提供绑定了 task_id 的 logger

        Args:
            component: 组件名称，如 'Client', 'Runtime' 等

        Returns:
            绑定了 task_id 的 logger 实例
        """
        return logger.bind(src=component, task_id=self.task_id, **kwargs)

    def use(self, llm: str) -> bool:
        """for cmd_llm use"""
        return self.client.use(llm)

    def run_block(self, name: str) -> bool:
        """for cmd_block run"""
        block = self.blocks.get(name)
        if not block:
            return False
        result = self.runner(block)
        self.emit('exec_completed', result=result, block=block)
        return True

    def emit(self, event_name: str, **kwargs):
        event = self.event_bus.emit(event_name, **kwargs)
        self.events.append(event)
        return event

    def get_system_message(self) -> ChatMessage:
        params = {}
        if not self.client.supports_function_calling():
            if self.mcp:
                params['mcp_tools'] = self.mcp.get_tools_prompt()

        params['util_functions'] = self.runtime.get_builtin_functions()
        params['tool_functions'] = self.runtime.get_plugin_functions()
        params['role'] = self.role
        system_prompt = self.prompts.get_default_prompt(**params)
        msg = SystemMessage(content=system_prompt)
        return self.message_storage.store(msg)

    def new_step(self, step_data: StepData) -> Step:
        """准备一个新的Step"""
        self.data.add_step(step_data)
        step = Step(self, step_data)
        self.steps.append(step)
        return step

    def delete_step(self, index: int) -> bool:
        """删除指定索引的Step并清理其上下文消息"""
        if index < 0 or index >= len(self.steps):
            self.log.warning(f"Invalid step index: {index}")
            return False

        if index == 0:
            self.log.warning("Cannot delete Step 0")
            return False

        # 获取要删除的Step
        step_to_delete = self.steps[index]
        step_info = step_to_delete.data.instruction[:50] + "..." if len(step_to_delete.data.instruction) > 50 else step_to_delete.data.instruction

        try:
            # 先清理上下文中的相关消息
            cleaned_count, remaining_messages, tokens_saved, tokens_remaining = step_to_delete.delete_cleanup()

            # 然后从步骤列表中删除
            self.steps.pop(index)

            self.log.info(f"Deleted step {index}: {step_info}")
            self.log.info(f"Context cleanup: {cleaned_count} messages deleted, {tokens_saved} tokens saved")
            self.emit('step_deleted', step_index=index, step_info=step_info, cleaned_messages=cleaned_count, tokens_saved=tokens_saved)

            return True

        except Exception as e:
            self.log.error(f"Failed to delete step {index}: {e}")
            return False

    def get_status(self):
        return {'llm': self.client.name, 'blocks': len(self.blocks), 'steps': len(self.steps)}

    @classmethod
    def from_file(cls, path: Union[str, Path], manager: TaskManager, parent: Task | None = None) -> 'Task':
        """从文件创建 TaskState 对象"""
        path = Path(path)
        validate_file(path)

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.loads(f.read())
                try:
                    model_context = {'message_storage': MessageStorage.model_validate(data['message_storage'])}
                except Exception:
                    model_context = None

                task_data = TaskData.model_validate(data, context=model_context)
                task = cls(manager, task_data, parent=parent)
                logger.info('Loaded task state from file', path=str(path), task_id=task.task_id)

                subtasks = []
                subdirs = [p for p in path.parent.iterdir() if p.is_dir()]
                for subdir in subdirs:
                    subjson = subdir / "task.json"
                    if not subjson.exists():
                        continue

                    subtask = cls.from_file(subjson, manager, parent=task)
                    logger.info('Loaded subtask from file', path=str(subjson), task_id=subtask.task_id)
                    subtasks.append(subtask)

                if subtasks:
                    task.subtasks = sorted(subtasks, key=lambda t: t.start_time or 0)
                return task
        except json.JSONDecodeError as e:
            raise TaskError(f'Invalid JSON file: {e}') from e
        except ValidationError as e:
            raise TaskError(f'Invalid task state: {e.errors()}') from e
        except Exception as e:
            raise TaskError(f'Failed to load task state: {e}') from e

    def to_file(self, path: Union[str, Path]) -> None:
        """保存任务状态到文件"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                data = self.data
                f.write(data.model_dump_json(indent=2, exclude_none=True))
            self.log.info('Saved task state to file', path=str(path))
        except Exception as e:
            self.log.exception('Failed to save task state', path=str(path))
            raise TaskError(f'Failed to save task state: {e}') from e

    def _auto_save(self):
        """自动保存任务状态"""
        # 如果任务目录不存在，则不保存
        cwd = self.cwd
        if not cwd.exists():
            self.log.warning('Task directory not found, skipping save')
            return

        try:
            display = self.display
            if display:
                filename = cwd / "console.html"
                display.save(filename, clear=False, code_format=CONSOLE_WHITE_HTML)

            self.to_file(cwd / "task.json")
            self._saved = True
            self.log.info('Task auto saved')
        except Exception as e:
            self.log.exception('Error saving task')
            self.emit('exception', msg='save_task', exception=e)

    def done(self, interrupted: bool = False):
        if not self.steps or not self.cwd.exists():
            self.log.warning('Task not started, skipping save')
            return

        if interrupted:
            for subtask in self.subtasks:
                subtask.done(interrupted=True)

        if not self._saved:
            self.log.warning('Task not saved, trying to save')
            self._auto_save()

        # 切换到父目录，准备重命名任务目录。对子任务，切换回父任务目录
        os.chdir(self.cwd.parent)
        if not self.parent:
            # 切换到父目录，避免目录锁定
            try:
                newname = safe_rename(self.cwd, self.instruction)
            except Exception:
                self.log.exception('Failed to rename task directory', path=str(self.cwd))
                newname = self.cwd
        else:
            # 子任务保持目录名不变（以便通过 task_id 定位）
            newname = self.cwd

        self.log.info('Task done', path=newname)
        self.emit('task_completed', path=str(newname), task_id=self.task_id, parent_id=self.parent.task_id if self.parent else None)

    def prepare_user_prompt(self, instruction: str, first_run: bool = False) -> ChatMessage:
        """处理多模态内容并验证模型能力"""
        mmc = MMContent(instruction, base_path=self.cwd.parent)
        try:
            message = mmc.message
        except Exception as e:
            raise TaskInputError(T("Invalid input"), e) from e

        content = message.content
        if isinstance(content, str):
            if first_run:
                content = self.prompts.get_task_prompt(self, content)
            else:
                content = self.prompts.get_chat_prompt(content, self.instruction)
            message.content = content
        elif not self.client.has_capability(message):
            raise TaskInputError(T("Current model does not support this content"))

        return self.message_storage.store(message)

    def _auto_compact(self):
        # Step级别的上下文清理
        auto_compact_enabled = self.settings.get('auto_compact_enabled', True)
        if not auto_compact_enabled:
            return

        result = self.steps[-1].compact()
        self.log.info(f"Step compact result: {result}")
        cleaned_count, remaining_messages, tokens_saved, tokens_remaining = result

        if cleaned_count == 0:
            return

        self.emit('step_cleanup_completed', cleaned_messages=cleaned_count, remaining_messages=remaining_messages, tokens_saved=tokens_saved, tokens_remaining=tokens_remaining)
        self.log.info(f"Step compact completed: {cleaned_count} messages cleaned")

    @with_task_context
    def run(self, instruction: str, title: str | None = None, lang: str | None = None) -> Response:
        """
        执行自动处理循环，直到 LLM 不再返回代码消息
        instruction: 用户输入的字符串（可包含@file等多模态标记）
        """
        first_run = not self.steps
        self.lang = lang or self.settings.get('lang')
        user_message = self.prepare_user_prompt(instruction, first_run)
        if first_run:
            # 如果上下文已经有消息，说明继承了上下文，不需要重复添加系统消息
            if not self.context_manager.messages:
                self.context_manager.add_message(self.get_system_message())
            self.emit('task_started', instruction=instruction, title=title, task_id=self.task_id, parent_id=self.parent.task_id if self.parent else None)
        else:
            self._auto_compact()

        self.log.info("Start task with features: {}", self.features.enabled_features)

        # We MUST create the task directory here because it could be a resumed task.
        self.cwd.mkdir(exist_ok=True, parents=True)
        os.chdir(self.cwd)
        self._saved = False

        step_data = StepData(initial_instruction=user_message, instruction=instruction, title=title)
        step = self.new_step(step_data)
        self.emit('step_started', instruction=instruction, step=len(self.steps) + 1, title=title)
        response = step.run()
        self.emit('step_completed', summary=step.get_summary(), response=response)

        self._auto_save()
        self.log.info('Step done', rounds=len(step.data.rounds))
        return response

    def run_subtask(self, instruction: str, title: str | None = None, cli=False, inherit_context: bool = False, client_name: str | None = None) -> Response:
        """运行子任务"""
        subtask = Task(self.manager, parent=self, inherit_context=inherit_context)

        # 如果指定了客户端，切换subtask的客户端
        if client_name:
            subtask.use(client_name)

        # 记录子任务到父任务的 subtasks 列表
        self.subtasks.append(subtask)

        response = subtask.run(instruction, title)
        subtask.done()
        if cli:
            self.context_manager.add_chat(UserMessage(content=instruction), response.message)
        return response

    def compress_context(self, client_name: str | None = None) -> Dict[str, Any]:
        """
        压缩任务上下文，使用LLM生成摘要并替换原始上下文

        Args:
            client_name: 可选的LLM客户端名称，如果为None则使用当前任务客户端

        Returns:
            Dict包含:
            - success: bool 是否成功
            - stats_before: Dict 压缩前统计
            - stats_after: Dict 压缩后统计
            - summary_tokens: int 摘要token数
            - messages_saved: int 节省的消息数
            - tokens_saved: int 节省的token数
            - compression_ratio: float 压缩比例
            - error: str 错误信息(如果失败)
        """
        from ..llm import UserMessage, AIMessage, MessageRole

        try:
            # 1. 获取压缩前统计
            stats_before = self.context_manager.get_stats()

            # 2. 检查上下文是否足够大，值得压缩
            if len(self.context_manager.messages) < 4:
                return {'success': False, 'error': 'Context too small to compress effectively', 'stats_before': stats_before}

            # 3. 使用prompts.py获取compact模板
            try:
                summary_instruction = self.prompts.get_prompt('compact')
            except Exception as e:
                self.log.warning(f"Failed to get compact template: {e}")
                # 使用默认指令作为fallback
                summary_instruction = (
                    "Please analyze the conversation context and create a concise summary that preserves all key information, "
                    "decisions, code changes, and important outcomes. The summary should be substantially shorter while "
                    "maintaining the essential context needed to continue the work effectively.\n\n"
                    "Structure your summary with these sections:\n"
                    "- **Task Overview**: Brief description of the main objective\n"
                    "- **Key Decisions**: Important decisions made during the conversation\n"
                    "- **Implementation Details**: Significant code changes and technical details\n"
                    "- **Issues Resolved**: Problems encountered and how they were solved\n"
                    "- **Current State**: Status of work and next steps if applicable\n\n"
                    "Focus on preserving final working code, important configuration changes, critical debugging insights, "
                    "and architecture decisions. Omit repetitive debugging attempts, failed code experiments, and conversational filler."
                )

            # 5. 创建继承上下文的subtask进行摘要生成，支持指定客户端
            response = self.run_subtask(summary_instruction, title="Context Summarization", inherit_context=True, client_name=client_name)

            # 获取生成的摘要内容
            if response is None or not response.message or not response.message.content:
                return {'success': False, 'error': 'Failed to generate summary content', 'stats_before': stats_before}

            summary_content = response.message.content.strip()

            # 使用LLM返回的准确usage信息
            summary_tokens = response.message.usage.get('output_tokens', 0)

            # 8. 构建新的压缩后上下文
            new_messages = []

            # 保留系统消息
            system_msgs = [msg for msg in self.context_manager.messages if msg.role == MessageRole.SYSTEM]
            new_messages.extend(system_msgs)

            # 添加摘要用户消息
            summary_user_msg = UserMessage(content=(f"CONTEXT SUMMARY:\n{summary_content}\n\nThis is a compressed summary of the previous conversation. Please continue the work based on this summarized context."))
            new_messages.append(self.message_storage.store(summary_user_msg))

            # 添加AI确认消息
            summary_ai_msg = AIMessage(content=("I understand the context summary. I'll continue the work based on this compressed information. Feel free to ask me to elaborate on any specific aspect if needed."))
            new_messages.append(self.message_storage.store(summary_ai_msg))

            # 9. 重建上下文
            self.context_manager.rebuild(new_messages)

            # 10. 获取压缩后统计
            stats_after = self.context_manager.get_stats()

            # 11. 计算节省的资源
            messages_saved = stats_before['message_count'] - stats_after['message_count']
            tokens_saved = stats_before['total_tokens'] - stats_after['total_tokens']
            compression_ratio = (tokens_saved / stats_before['total_tokens']) if stats_before['total_tokens'] > 0 else 0

            self.log.info(f"Context compressed: {stats_before['message_count']}→{stats_after['message_count']} messages, {stats_before['total_tokens']}→{stats_after['total_tokens']} tokens, saved {tokens_saved} tokens ({compression_ratio:.1%} reduction)")

            return {'success': True, 'stats_before': stats_before, 'stats_after': stats_after, 'summary_tokens': summary_tokens, 'messages_saved': messages_saved, 'tokens_saved': tokens_saved, 'compression_ratio': compression_ratio}

        except Exception as e:
            self.log.error(f"Context compression failed: {e}")
            return {'success': False, 'error': str(e), 'stats_before': stats_before if 'stats_before' in locals() else None}
