#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import List, TYPE_CHECKING, Any
import time
from collections import Counter

from loguru import logger
from pydantic import BaseModel, Field

from ..llm import ErrorMessage, UserMessage, ToolMessage
from .chat import ChatMessage
from .response import Response
from .toolcalls import ToolCallResult, ToolName
from .prompts import Prompts

if TYPE_CHECKING:
    from .task import Task

class Round(BaseModel):
    # LLM的回复消息
    llm_response: Response = Field(default_factory=Response)
    # 工具调用执行结果
    toolcall_results: List[ToolCallResult] | None = None
    # 系统对执行结果的回应消息(如果有)
    system_feedback: ChatMessage | List[ChatMessage] | None = None
    # 上下文清理标记：是否已从上下文中删除
    context_deleted: bool = Field(default=False, description="Whether this round's messages have been deleted from context")

    def should_continue(self) -> bool:
        return self.llm_response.should_continue()
    
    def get_system_feedback(self, prompts: Prompts) -> UserMessage | ToolMessage | list[ToolMessage] | None:
        if self.llm_response.errors:
            prompt = prompts.get_parse_error_prompt(self.llm_response.errors)

            # 如果 assistant 回复里包含 tool_calls，OpenAI/兼容接口要求：
            # assistant(tool_calls) 之后必须跟对应 tool(tool_call_id) 消息。
            tool_calls = getattr(getattr(self.llm_response.message, 'message', None), 'tool_calls', None)
            if tool_calls:
                tool_messages: list[ToolMessage] = []
                for tc in tool_calls:
                    tc_id = getattr(tc, 'id', None)
                    if tc_id:
                        tool_messages.append(ToolMessage(tool_call_id=tc_id, content=prompt))
                if tool_messages:
                    return tool_messages

            return UserMessage(content=prompt)

        if self.toolcall_results:
            tool_messages = []
            for res in self.toolcall_results:
                if res.is_openai(): # ToolCallResult has id
                    # 确保 result 是字符串
                    content = res.result.to_json() if hasattr(res.result, 'to_json') else str(res.result)
                    msg = ToolMessage(tool_call_id=res.id, content=content)
                    tool_messages.append(msg) 
            if tool_messages:
                return tool_messages           
            prompt = prompts.get_toolcall_results_prompt(self.toolcall_results)
            return UserMessage(content=prompt)

        return None
    
    def can_safely_delete(self) -> bool:
        """判断Round对应的上下文消息是否可以安全删除
        
        可以安全删除的情况：
        1. LLM回复有解析错误
        2. 所有工具调用都失败
        
        保留的情况：
        3. 纯文本Round（Step自然结束）
        4. 有任何成功的工具调用
        """
        # 1. LLM回复有解析错误 -> 可以删除
        if self.llm_response.errors:
            return True
        
        # 2. 所有工具调用都失败 -> 可以删除
        if self.toolcall_results and all(self._tool_call_failed(tcr) for tcr in self.toolcall_results):
            return True
        
        # 3. 其他情况 -> 保留
        # 包括：纯文本Round（Step结束）和有成功工具调用的Round
        return False
    
    def _tool_call_failed(self, tool_call_result: ToolCallResult) -> bool:
        """判断工具调用是否失败"""
        # 检查工具调用层面的错误
        if tool_call_result.result.error is not None:
            return True
        
        # 对于 Exec 工具，还需要检查实际执行结果
        if tool_call_result.name == ToolName.EXEC:
            exec_result = tool_call_result.result.result
            return exec_result.has_error()
        
        return False
    
class StepData(BaseModel):
    # 用户的初始指令作为Step级别的字段
    initial_instruction: ChatMessage
    instruction: str  # 保持向后兼容
    title: str | None = None
    start_time: float = Field(default_factory=time.time)
    end_time: float | None = None
    
    # 每个Round包含完整的对话+执行循环  
    rounds: List[Round] = Field(default_factory=list)
    
    @property
    def final_response(self):
        return self.rounds[-1].llm_response if self.rounds else None
    
    def add_round(self, round: Round):
        self.rounds.append(round)

class Step:
    def __init__(self, task: Task, data: StepData):
        self.task = task
        self.log = task.get_logger('Step')
        self._data = data
        self._summary = Counter()
        self._cleaner = StepCleaner(task.context_manager)

        # 从现有数据初始化 summary counter
        self._initialize_summary_from_existing_data()

    def _initialize_summary_from_existing_data(self):
        """从现有 rounds 中初始化 summary counter"""
        for round_data in self._data.rounds:
            if (round_data.llm_response and
                hasattr(round_data.llm_response, 'message') and
                round_data.llm_response.message and
                hasattr(round_data.llm_response.message, 'usage')):
                usage = round_data.llm_response.message.usage
                if usage:
                    self._summary.update(usage)
    
    @property
    def data(self):
        return self._data
    
    def __getitem__(self, name: str):
        return getattr(self._data, name)
    
    def __setitem__(self, name: str, value: Any):
        setattr(self._data, name, value)
    
    def get(self, name: str, default: Any = None):
        return getattr(self._data, name, default)
    
    def request(self, user_message: ChatMessage | List[ChatMessage]) -> Response:
        client = self.task.client
        self.task.emit('request_started', llm=client.name)
        msg = client(user_message)
        self.task.emit('response_completed', llm=client.name, msg=msg)
        if isinstance(msg.message, ErrorMessage):
            response = Response(message=msg)
            self.log.error('LLM request error', error=msg.content)
        else:
            self._summary.update(msg.usage)
            response = Response.from_message(msg)
        return response

    def process(self, response: Response) -> list[ToolCallResult] | None:
        if isinstance(response.message.message, ErrorMessage):
            return None
        
        if response.task_status:
            self.task.emit('task_status', status=response.task_status)

        if response.code_blocks:
            self.task.blocks.add_blocks(response.code_blocks)
        
        if response.tool_calls:
            toolcall_results = self.task.tool_call_processor.process(response.tool_calls)
        else:
            toolcall_results = None
        return toolcall_results
    
    def run(self) -> Response:
        max_rounds = self.task.max_rounds
        message_storage = self.task.message_storage
        user_message = self.data.initial_instruction

        response = None
        while len(self['rounds']) < max_rounds:
            # 请求LLM回复
            response = self.request(user_message)
            self.task.emit('parse_reply_completed', response=response)
            
            # 创建新的Round，包含LLM回复
            round = Round(llm_response=response)

            # 始终将round添加到rounds列表中
            self._data.add_round(round)

            # 处理工具调用
            round.toolcall_results = self.process(response)

            # 生成系统反馈消息
            system_feedback = round.get_system_feedback(self.task.prompts)
            if not system_feedback:
                break

            if isinstance(system_feedback, list):
                stored_msgs = []
                for msg in system_feedback:
                    stored_msgs.append(
                        msg if isinstance(msg, ChatMessage) else message_storage.store(msg)
                    )
                round.system_feedback = stored_msgs
                user_message = stored_msgs
            else:
                round.system_feedback = message_storage.store(system_feedback)
                user_message = round.system_feedback

        self['end_time'] = time.time()
        return response

    def get_summary(self):
        summary = dict(self._summary)

        # 防御性保护：确保所有必要的 token 键都存在
        summary.setdefault('input_tokens', 0)
        summary.setdefault('output_tokens', 0)
        summary.setdefault('total_tokens', 0)

        summary['elapsed_time'] = int(self['end_time'] - self['start_time'])
        summary['rounds'] = len(self['rounds'])
        summarys = "{rounds} | {elapsed_time}s | Tokens: {input_tokens}/{output_tokens}/{total_tokens}".format(**summary)
        summary['summary'] = summarys
        return summary

    def cleanup(self) -> tuple[int, int, int, int]:
        """清理步骤消息"""
        return self._cleaner.cleanup_step(self)

    def compact(self) -> tuple[int, int, int, int]:
        """智能压缩步骤消息"""
        return self._cleaner.compact_step(self)

    def delete_cleanup(self) -> tuple[int, int, int, int]:
        """删除步骤时的清理"""
        return self._cleaner.delete_step(self)


class StepCleaner:
    """Step级别的清理器"""

    def __init__(self, context_manager):
        self.context_manager = context_manager
        self.log = logger.bind(src='StepCleaner')

    def _execute_cleaning(self, step: 'Step', messages_to_clean: List[str],
                         operation_name: str, log_prefix: str) -> tuple[int, int, int, int]:
        """执行清理的核心公共逻辑

        Args:
            step: 要清理的Step对象
            messages_to_clean: 需要清理的消息ID列表
            operation_name: 操作名称 (cleanup/compact/delete)
            log_prefix: 日志前缀

        Returns:
            (cleaned_count, remaining_messages, tokens_saved, tokens_remaining)
        """
        # 执行清理
        if not messages_to_clean:
            self.log.info("No messages need to be cleaned")
            stats = self.context_manager.get_stats()
            return 0, stats['message_count'], 0, stats['total_tokens']

        # 获取清理前的统计信息
        stats_before = self.context_manager.get_stats()
        messages_before = stats_before['message_count']
        tokens_before = stats_before['total_tokens']

        # 执行清理（只清理上下文消息，不影响rounds记录）
        self.log.info(f"Executing {log_prefix} with {len(messages_to_clean)} message IDs")
        deleted_result = self.context_manager.delete_messages_by_ids(messages_to_clean)
        self.log.info(f"delete_messages_by_ids returned: {deleted_result}")

        # 获取清理后的统计信息
        stats_after = self.context_manager.get_stats()
        messages_after = stats_after['message_count']
        tokens_after = stats_after['total_tokens']

        # 计算清理结果
        cleaned_count = messages_before - messages_after
        tokens_saved = tokens_before - tokens_after

        self.log.info(f"{operation_name} completed: {cleaned_count} messages deleted")
        self.log.info(f"Messages: {messages_before} -> {messages_after}")
        self.log.info(f"Tokens: {tokens_before} -> {tokens_after} (saved: {tokens_saved})")

        return cleaned_count, messages_after, tokens_saved, tokens_after

    def _get_cleanup_messages(self, step: 'Step') -> List[str]:
        """cleanup 策略：保留最后一轮，删除其他所有消息"""
        messages_to_clean = []
        rounds = step.data.rounds

        for i, round in enumerate(rounds[:-1]):
            # 收集这个Round的所有消息ID
            round.context_deleted = True
            if round.llm_response and round.llm_response.message:
                messages_to_clean.append(round.llm_response.message.id)
            if round.system_feedback:
                if isinstance(round.system_feedback, list):
                    for msg in round.system_feedback:
                        messages_to_clean.append(msg.id)
                else:
                    messages_to_clean.append(round.system_feedback.id)

            self.log.info(f"Will clean Round {i}: {self._get_round_summary(round)}")

        self.log.info(f"Will clean {len(messages_to_clean)} messages from {len(rounds)-1} rounds (preserving last round)")
        return messages_to_clean

    def _get_compact_messages(self, step: 'Step') -> List[str]:
        """compact 策略：基于 round.can_safely_delete() 智能选择"""
        messages_to_clean = []
        rounds = step.data.rounds

        # 分析每个Round，收集可删除Round的消息ID
        for i, round in enumerate(rounds):
            if round.can_safely_delete():
                # 收集这个Round的消息ID用于删除
                round.context_deleted = True
                if round.llm_response and round.llm_response.message:
                    messages_to_clean.append(round.llm_response.message.id)
                if round.system_feedback:
                    if isinstance(round.system_feedback, list):
                        for msg in round.system_feedback:
                            messages_to_clean.append(msg.id)
                    else:
                        messages_to_clean.append(round.system_feedback.id)

                self.log.info(f"Will clean Round {i}: {self._get_round_summary(round)}")
            else:
                self.log.info(f"Preserving Round {i}: {self._get_round_summary(round)}")

        self.log.info(f"Will clean {len(messages_to_clean)} messages from deletable rounds")
        return messages_to_clean

    def _get_delete_messages(self, step: 'Step') -> List[str]:
        """delete 策略：删除所有消息（包括初始指令）"""
        messages_to_clean = []

        # 1. 删除initial_instruction
        if step.data.initial_instruction:
            messages_to_clean.append(step.data.initial_instruction.id)
            self.log.info(f"Will delete initial_instruction: {step.data.initial_instruction.id}")

        # 2. 删除所有rounds的消息
        for i, round in enumerate(step.data.rounds):
            self.log.info(f"Processing Round {i}: {self._get_round_summary(round)}")
            if round.llm_response.message:
                msg_id = round.llm_response.message.id
                messages_to_clean.append(msg_id)
                self.log.info(f"✅ Will delete Round {i} LLM response: {msg_id}")

            # 检查系统反馈
            if round.system_feedback:
                if isinstance(round.system_feedback, list):
                    for msg in round.system_feedback:
                        messages_to_clean.append(msg.id)
                        self.log.info(f"✅ Will delete Round {i} system feedback: {msg.id}")
                else:
                    feedback_id = round.system_feedback.id
                    messages_to_clean.append(feedback_id)
                    self.log.info(f"✅ Will delete Round {i} system feedback: {feedback_id}")

            # 标记为删除
            round.context_deleted = True

        self.log.info(f"Will delete {len(messages_to_clean)} messages from step deletion")
        return messages_to_clean

    def cleanup_step(self, step: 'Step') -> tuple[int, int, int, int]:
        """Step完成后的最大化清理：从上下文删除所有Round消息，但保留执行记录

        与compact_step的区别：
        - cleanup_step: 删除所有Round消息（最大化清理）
        - compact_step: 只删除失败Round消息（智能清理）

        Returns:
            (cleaned_count, remaining_messages, tokens_saved, tokens_remaining)
        """
        if len(step.data.rounds) < 2:
            self.log.info("No enough rounds found in step, skipping cleanup")
            stats = self.context_manager.get_stats()
            return 0, stats['message_count'], 0, stats['total_tokens']

        rounds = step.data.rounds
        self.log.info(f"Step has {len(rounds)} rounds, implementing maximum cleanup")

        # 使用策略选择器获取要清理的消息
        messages_to_clean = self._get_cleanup_messages(step)

        # 使用公共清理逻辑
        cleaned_count, remaining_messages, tokens_saved, tokens_remaining = self._execute_cleaning(
            step, messages_to_clean, "Maximum cleanup", "Maximum cleanup"
        )

        # 记录特定于cleanup的日志
        self.log.info(f"Execution records preserved: {len(rounds)} rounds kept")
        self.log.info("Context preserved: initial_instruction + last round")

        return cleaned_count, remaining_messages, tokens_saved, tokens_remaining

    def compact_step(self, step: 'Step') -> tuple[int, int, int, int]:
        """智能压缩Step：只清理上下文消息，保留执行记录

        基于Round.can_safely_delete()方法智能判断哪些上下文消息可以删除：
        - 删除可安全删除Round对应的上下文消息
        - 保留重要Round对应的上下文消息
        - 完全保留step.data.rounds（执行历史记录）
        - Step级别的initial_instruction自动保护

        Returns:
            (cleaned_count, remaining_messages, tokens_saved, tokens_remaining)
        """
        if len(step.data.rounds) < 2:
            self.log.info("No enough rounds found in step, skipping compact")
            stats = self.context_manager.get_stats()
            return 0, stats['message_count'], 0, stats['total_tokens']

        rounds = step.data.rounds
        self.log.info(f"Step has {len(rounds)} rounds, implementing smart compact")

        # 使用策略选择器获取要清理的消息
        messages_to_clean = self._get_compact_messages(step)

        # 使用公共清理逻辑
        cleaned_count, remaining_messages, tokens_saved, tokens_remaining = self._execute_cleaning(
            step, messages_to_clean, "Compact", "Smart compact"
        )

        # 记录特定于compact的日志
        self.log.info(f"Execution records preserved: {len(rounds)} rounds kept")

        return cleaned_count, remaining_messages, tokens_saved, tokens_remaining

    def delete_step(self, step: 'Step') -> tuple[int, int, int, int]:
        """删除Step时清理所有相关消息：initial_instruction + 所有rounds

        Returns:
            (cleaned_count, remaining_messages, tokens_saved, tokens_remaining)
        """
        self.log.info(f"Deleting step context: {step.data.instruction[:50]}...")

        # 使用策略选择器获取要清理的消息
        messages_to_clean = self._get_delete_messages(step)

        # 使用公共清理逻辑
        cleaned_count, remaining_messages, tokens_saved, tokens_remaining = self._execute_cleaning(
            step, messages_to_clean, "Step deletion", "Step deletion"
        )

        return cleaned_count, remaining_messages, tokens_saved, tokens_remaining

    def _get_round_summary(self, round: Round) -> str:
        """获取Round的简要描述用于日志"""
        if round.llm_response.errors:
            return "LLM_ERROR"
        elif not round.toolcall_results:
            return "TEXT_ONLY"
        elif all(round._tool_call_failed(tcr) for tcr in round.toolcall_results):
            return f"TOOL_FAILED: {len(round.toolcall_results)} tools"
        else:
            success_count = sum(1 for tcr in round.toolcall_results if not round._tool_call_failed(tcr))
            return f"SUCCESS: {success_count}/{len(round.toolcall_results)} tools"
