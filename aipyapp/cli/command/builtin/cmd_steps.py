#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime

from rich.tree import Tree

from .utils import row2table
from ..base import CommandMode, ParserCommand
from aipyapp import T


class StepsCommand(ParserCommand):
    """Steps command"""

    name = "step"
    description = T("Manage task steps")
    modes = [CommandMode.TASK]

    def add_subcommands(self, subparsers):
        subparsers.add_parser('list', help=T('List task steps'))
        parser = subparsers.add_parser('clear', help=T('Clear step context'))
        parser.add_argument('index', type=int, nargs='?', default=-1, help=T('Index of the step to clear (default: last step)'))
        parser = subparsers.add_parser('compact', help=T('Smart compact step rounds'))
        parser.add_argument('index', type=int, nargs='?', default=-1, help=T('Index of the step to compact (default: last step)'))
        parser = subparsers.add_parser('delete', help=T('Delete task steps'))
        parser.add_argument('index', type=int, help=T('Index of the task step to delete'))
        parser = subparsers.add_parser('show', help=T('Show rounds in a step'))
        parser.add_argument('index', type=int, nargs='?', default=-1, help=T('Index of the step to show (default: last step)'))

    def get_arg_values(self, name, subcommand=None, partial=None):
        if name == 'index':
            task = self.manager.context.task
            return [(str(index), step['title'] or step['instruction'][:32]) for index, step in enumerate(task.steps)]
        return None

    def cmd(self, args, ctx):
        return self.cmd_list(args, ctx)

    def cmd_list(self, args, ctx):
        steps = ctx.task.steps
        if not steps:
            ctx.console.print(T("No task steps found"))
            return

        rows = []
        for i, step in enumerate(steps):
            start_time_s = datetime.fromtimestamp(step['start_time']).strftime('%m-%d %H:%M')
            end_time_s = datetime.fromtimestamp(step['end_time']).strftime('%m-%d %H:%M') if step['end_time'] else ''
            rows.append([i, step['title'] or step['instruction'][:32], len(step['rounds']), start_time_s, end_time_s])
        table = row2table(rows, title=T('Task Steps'), headers=[T('Index'), T('Title'), T('Rounds'), T('Start Time'), T('End Time')])
        ctx.console.print(table)

    def cmd_clear(self, args, ctx):
        """清理指定Step的上下文"""
        task = ctx.task
        if not task.steps:
            ctx.console.print(T("No task steps found"))
            return False

        # 确定要清理的step索引
        if args.index == -1:
            step_index = len(task.steps) - 1  # 最后一个step
        else:
            step_index = args.index

        if step_index < 0 or step_index >= len(task.steps):
            ctx.console.print(T(f"Invalid step index: {step_index}"))
            return False

        step = task.steps[step_index]
        step_title = step.data.title or step.data.instruction[:50]

        try:
            # 调用Step的cleanup方法
            cleaned_count, remaining_messages, tokens_saved, tokens_remaining = step.cleanup()

            # 显示清理结果
            ctx.console.print(f"[green]✅ Step {step_index} context cleared[/green]")
            ctx.console.print(f"[dim]Step:[/dim] {step_title}")
            ctx.console.print(f"[dim]🧹 Cleaned messages:[/dim] {cleaned_count}")
            ctx.console.print(f"[dim]📝 Remaining messages:[/dim] {remaining_messages}")
            ctx.console.print(f"[dim]🔥 Tokens saved:[/dim] {tokens_saved}")
            ctx.console.print(f"[dim]📊 Tokens remaining:[/dim] {tokens_remaining}")

            if cleaned_count > 0:
                ctx.console.print(f"[dim]💡 Use 'step show {step_index}' to see which rounds were deleted[/dim]")

            return True

        except Exception as e:
            ctx.console.print(f"[red]❌ Failed to clear step context: {e}[/red]")
            return False

    def cmd_compact(self, args, ctx):
        """智能压缩指定Step的Round"""
        task = ctx.task
        if not task.steps:
            ctx.console.print(T("No task steps found"))
            return False

        # 确定要压缩的step索引
        if args.index == -1:
            step_index = len(task.steps) - 1  # 最后一个step
        else:
            step_index = args.index

        if step_index < 0 or step_index >= len(task.steps):
            ctx.console.print(T(f"Invalid step index: {step_index}"))
            return False

        step = task.steps[step_index]
        step_title = step.data.title or step.data.instruction[:50]

        try:
            # 调用Step的compact方法
            cleaned_count, remaining_messages, tokens_saved, tokens_remaining = step.compact()

            # 显示压缩结果
            ctx.console.print(f"[green]✅ Step {step_index} context compacted[/green]")
            ctx.console.print(f"[dim]Step:[/dim] {step_title}")
            ctx.console.print(f"[dim]🧹 Compacted messages:[/dim] {cleaned_count}")
            ctx.console.print(f"[dim]📝 Remaining messages:[/dim] {remaining_messages}")
            ctx.console.print(f"[dim]🔥 Tokens saved:[/dim] {tokens_saved}")
            ctx.console.print(f"[dim]📊 Tokens remaining:[/dim] {tokens_remaining}")

            if cleaned_count > 0:
                ctx.console.print(f"[dim]💡 Use 'step show {step_index}' to see which rounds were compacted[/dim]")
                ctx.console.print("[dim]💡 Only failed/error rounds were deleted, preserving important context[/dim]")
            else:
                ctx.console.print("[dim]💡 No rounds were compacted - all rounds are important or already cleaned[/dim]")

            return True

        except Exception as e:
            ctx.console.print(f"[red]❌ Failed to compact step context: {e}[/red]")
            return False

    def cmd_delete(self, args, ctx):
        """删除指定Step并清理其上下文"""
        task = ctx.task
        if not task.steps:
            ctx.console.print(T("No task steps found"))
            return False

        step_index = args.index
        if step_index < 0 or step_index >= len(task.steps):
            ctx.console.print(T(f"Invalid step index: {step_index}"))
            return False

        if step_index == 0:
            ctx.console.print(T("Cannot delete Step 0"))
            return False

        # 获取要删除的step信息
        step_to_delete = task.steps[step_index]
        step_title = step_to_delete.data.title or step_to_delete.data.instruction[:50]

        try:
            ret = task.delete_step(step_index)
            if ret:
                ctx.console.print(f"[green]✅ Step {step_index} deleted successfully[/green]")
                ctx.console.print(f"[dim]Deleted step:[/dim] {step_title}")
                ctx.console.print("[dim]💡 Step context and all related messages were cleaned from context[/dim]")
            else:
                ctx.console.print(f"[red]❌ Failed to delete step {step_index}[/red]")
            return ret

        except Exception as e:
            ctx.console.print(f"[red]❌ Error deleting step: {e}[/red]")
            return False

    def cmd_show(self, args, ctx):
        """显示指定Step的Round详情"""
        task = ctx.task
        if not task.steps:
            ctx.console.print(T("No task steps found"))
            return False

        # 确定要显示的step索引
        if args.index == -1:
            step_index = len(task.steps) - 1  # 最后一个step
        else:
            step_index = args.index

        if step_index < 0 or step_index >= len(task.steps):
            ctx.console.print(T(f"Invalid step index: {step_index}"))
            return False

        step = task.steps[step_index]
        step_data = step.data

        # 创建Step树
        step_title = step_data.title or step_data.instruction[:50]

        tree = Tree(f"[bold blue]Step {step_index}[/bold blue]: {step_title}")

        # 添加Step元信息
        meta_branch = tree.add("[dim]📊 Meta Info[/dim]")
        meta_branch.add(f"[dim]Start Time:[/dim] {datetime.fromtimestamp(step_data.start_time).strftime('%Y-%m-%d %H:%M:%S')}")
        if step_data.end_time:
            end_time = datetime.fromtimestamp(step_data.end_time).strftime('%Y-%m-%d %H:%M:%S')
            duration = step_data.end_time - step_data.start_time
            meta_branch.add(f"[dim]End Time:[/dim] {end_time}")
            meta_branch.add(f"[dim]Duration:[/dim] {duration:.2f}s")

        # 显示Rounds
        if not step_data.rounds:
            tree.add("[dim]📭 No rounds found[/dim]")
        else:
            # 统计信息
            active_rounds = sum(1 for r in step_data.rounds if not r.context_deleted)
            deleted_rounds = len(step_data.rounds) - active_rounds

            # Token 统计汇总
            total_input_tokens = 0
            total_output_tokens = 0
            total_all_tokens = 0
            rounds_with_tokens = 0

            for round in step_data.rounds:
                if round.llm_response and hasattr(round.llm_response, 'message') and round.llm_response.message and hasattr(round.llm_response.message, 'usage') and round.llm_response.message.usage:
                    usage = round.llm_response.message.usage
                    total_input_tokens += usage.get('input_tokens', 0)
                    total_output_tokens += usage.get('output_tokens', 0)
                    total_all_tokens += usage.get('total_tokens', 0)
                    rounds_with_tokens += 1

            rounds_branch = tree.add(f"[bold]🔄 Rounds ({len(step_data.rounds)})[/bold]")
            stats_node = rounds_branch.add(f"[dim]📈 Context: {active_rounds} active, {deleted_rounds} deleted[/dim]")

            # 添加 token 统计信息
            if rounds_with_tokens > 0:
                token_stats_node = rounds_branch.add(f"[dim]📊 Tokens: ↑{total_input_tokens} ↓{total_output_tokens} Σ{total_all_tokens} ({rounds_with_tokens} rounds)[/dim]")

            # 显示每个Round
            for i, round in enumerate(step_data.rounds):
                # 状态图标和颜色
                if round.context_deleted:
                    status_icon = "🗑️"
                    status_color = "red"
                    status_text = "DELETED"
                else:
                    status_icon = "✅"
                    status_color = "green"
                    status_text = "ACTIVE"

                # Round类型
                if round.llm_response.errors:
                    type_icon = "❌"
                    type_text = "ERROR"
                    type_color = "red"
                elif not round.toolcall_results:
                    type_icon = "💬"
                    type_text = "TEXT"
                    type_color = "blue"
                else:
                    failed_tools = sum(1 for tcr in round.toolcall_results if round._tool_call_failed(tcr))
                    total_tools = len(round.toolcall_results)
                    if failed_tools == total_tools:
                        type_icon = "🔧❌"
                        type_text = f"TOOLS({failed_tools}/{total_tools})"
                        type_color = "red"
                    elif failed_tools == 0:
                        type_icon = "🔧✅"
                        type_text = f"TOOLS({total_tools})"
                        type_color = "green"
                    else:
                        type_icon = "🔧⚠️"
                        type_text = f"TOOLS({total_tools - failed_tools}/{total_tools})"
                        type_color = "yellow"

                # 获取当前 round 的 token 统计
                token_info = ""
                if round.llm_response and hasattr(round.llm_response, 'message') and round.llm_response.message and hasattr(round.llm_response.message, 'usage') and round.llm_response.message.usage:
                    usage = round.llm_response.message.usage
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    total_tokens = usage.get('total_tokens', 0)
                    token_info = f" [dim]📊 ↑{input_tokens} ↓{output_tokens} Σ{total_tokens}[/dim]"

                # 创建Round节点
                round_title = f"{status_icon} [{status_color}]Round {i} - {status_text}[/{status_color}] [{type_color}]{type_icon} {type_text}[/{type_color}]{token_info}"
                round_node = rounds_branch.add(round_title)

                # LLM回复内容
                if round.llm_response.message and hasattr(round.llm_response.message, 'content'):
                    content = round.llm_response.message.content.strip()
                    if content:
                        # 限制显示长度
                        if len(content) > 100:
                            content_preview = content[:100] + "..."
                        else:
                            content_preview = content
                        # 处理换行符
                        content_preview = content_preview.replace('\n', ' ')
                        round_node.add(f"[dim]💬 Response:[/dim] {content_preview}")

                # 工具调用详情
                if round.toolcall_results:
                    tools_node = round_node.add(f"[dim]🔧 Tools ({len(round.toolcall_results)}):[/dim]")
                    for j, tcr in enumerate(round.toolcall_results):
                        if round._tool_call_failed(tcr):
                            # 显示具体的错误信息
                            error_msg = tcr.result.error
                            if not error_msg and tcr.name == 'EXEC' and hasattr(tcr.result, 'result') and tcr.result.result:
                                # 对于EXEC工具，如果没有工具层错误但执行失败，显示执行错误
                                exec_result = tcr.result.result
                                if hasattr(exec_result, 'returncode') and exec_result.returncode != 0:
                                    error_msg = f"Exit code: {exec_result.returncode}"
                                elif hasattr(exec_result, 'errstr') and exec_result.errstr:
                                    error_msg = exec_result.errstr
                                elif hasattr(exec_result, 'stderr') and exec_result.stderr:
                                    error_msg = exec_result.stderr[:100] + "..." if len(exec_result.stderr) > 100 else exec_result.stderr
                                else:
                                    error_msg = "Execution failed"
                            tool_status = f"[red]❌ {tcr.name.value}[/red]: {error_msg or 'Unknown error'}"
                        else:
                            tool_status = f"[green]✅ {tcr.name.value}[/green]"
                        tools_node.add(tool_status)

                # 系统反馈
                if round.system_feedback:
                    if isinstance(round.system_feedback, list):
                        # 列表：显示所有反馈消息
                        for idx, feedback_msg in enumerate(round.system_feedback):
                            if feedback_msg.message and hasattr(feedback_msg.message, 'content'):
                                content = feedback_msg.message.content
                                if isinstance(content, list):
                                    # 多模态内容：提取文本部分
                                    content = '\n'.join(item.text for item in content if hasattr(item, 'text'))
                                if content:
                                    feedback_content = content[:50].replace('\n', ' ')
                                    if len(content) > 50:
                                        feedback_content += "..."
                                    label = f"🔄 Feedback[{idx}]:" if len(round.system_feedback) > 1 else "🔄 Feedback:"
                                    round_node.add(f"[dim]{label} {feedback_content}[/dim]")
                    else:
                        # 单个消息
                        if round.system_feedback.message and hasattr(round.system_feedback.message, 'content'):
                            content = round.system_feedback.message.content
                            if isinstance(content, list):
                                # 多模态内容：提取文本部分
                                content = '\n'.join(item.text for item in content if hasattr(item, 'text'))
                            if content:
                                feedback_content = content[:50].replace('\n', ' ')
                                if len(content) > 50:
                                    feedback_content += "..."
                                round_node.add(f"[dim]🔄 Feedback:[/dim] {feedback_content}")

        ctx.console.print(tree)
        return True
