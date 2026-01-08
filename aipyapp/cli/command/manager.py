"""重构后的命令管理器 - 职责分离"""

import shlex
import argparse
from collections import OrderedDict
from typing import Dict, Optional, Any, List

from prompt_toolkit.completion import Completer, Completion
from loguru import logger

from .common import CommandContext, CommandMode, CommandManagerConfig, CommandError, CommandResult
from .base import Command
from .completer import CompleterBase, CompleterContext, FuzzyCompleter
from .custom import CustomCommandManager
from .builtin import BUILTIN_COMMANDS
from .keybindings import create_key_bindings


class CommandRegistry:
    """
    命令注册表

    负责命令的注册和查找
    """

    def __init__(self):
        self._commands: OrderedDict[str, Command] = OrderedDict()
        self._commands_by_mode: Dict[CommandMode, OrderedDict[str, Command]] = {CommandMode.MAIN: OrderedDict(), CommandMode.TASK: OrderedDict()}
        self._user_commands: OrderedDict[str, Command] = OrderedDict()

    @property
    def commands(self) -> OrderedDict[str, Command]:
        """获取所有命令"""
        return self._commands

    @property
    def user_commands(self) -> OrderedDict[str, Command]:
        """获取所有用户命令"""
        return self._user_commands

    def register(self, command: Command):
        """注册命令"""
        # 注册主名称
        name = command.name
        self._commands[name] = command

        if not command.builtin:
            self._user_commands[name] = command

        # 按模式分类
        for mode in command.modes:
            self._commands_by_mode[mode][name] = command

    def unregister(self, name: str):
        """注销命令"""
        command = self._commands.pop(name, None)
        if not command:
            return False

        # 从模式列表中移除
        for mode in command.modes:
            self._commands_by_mode[mode].pop(name, None)

        if not command.builtin:
            self._user_commands.pop(name, None)
        return True

    def unregister_user_commands(self):
        """注销用户命令"""
        count = 0
        for name in list(self._user_commands.keys()):
            if self.unregister(name):
                count += 1
        return count

    def get(self, name: str) -> Optional[Command]:
        """获取命令"""
        return self._commands.get(name)

    def get_commands_by_mode(self, mode: CommandMode) -> OrderedDict[str, Command]:
        """获取特定模式的命令"""
        return self._commands_by_mode.get(mode, {})


class CommandExecutor:
    """
    命令执行器

    负责解析和执行命令
    """

    def __init__(self, registry: CommandRegistry):
        self.registry = registry
        self.log = logger.bind(src="CommandExecutor")

    def execute(self, text: str, context: CommandContext) -> Any:
        """
        执行命令

        Args:
            text: 命令文本（带 / 前缀）
            context: 执行上下文

        Returns:
            命令执行结果
        """
        # 验证命令格式
        if not text.startswith('/'):
            raise ValueError(f"Invalid command format: {text}")

        # 解析命令
        text = text[1:].strip()
        if not text:
            raise ValueError("Empty command")

        # 分割命令和参数
        try:
            words = shlex.split(text)
        except ValueError as e:
            raise ValueError(f"Failed to parse command: {e}")

        if not words:
            raise ValueError("No command specified")

        cmd_name = words[0]
        cmd_args = words[1:]

        # 查找命令
        command = self.registry.get(cmd_name)
        if not command:
            raise CommandError(f"Unknown command: {cmd_name}")

        # 检查命令是否支持当前模式
        if context.mode not in command.modes:
            raise CommandError(f"Command '{cmd_name}' not available in {context.mode.value} mode")

        # 解析参数
        try:
            parsed_args = command.parser.parse_args(cmd_args)
        except SystemExit:
            # argparse 尝试退出，转换为异常
            raise CommandError(f"Invalid arguments for command '{cmd_name}'")
        except argparse.ArgumentError as e:
            raise CommandError(f"Invalid arguments: {e}")
        except Exception as e:
            raise CommandError(f"Failed to parse arguments: {e}")

        # 验证参数
        if hasattr(command, 'validate_args'):
            error = command.validate_args(parsed_args)
            if error:
                raise CommandError(f"Invalid arguments: {error}")

        # 执行命令
        try:
            result = command.execute(parsed_args, context)
            return CommandResult(command=command.name, subcommand=getattr(parsed_args, 'subcommand', None), args=vars(parsed_args), result=result)
        except Exception as e:
            self.log.exception("Command execution failed")
            raise CommandError(f"Command execution failed: {e}")


class CommandCompleter(CompleterBase):
    """
    命令级别的补齐器

    负责路由补齐请求到具体命令的补齐器
    """

    def __init__(self, registry: CommandRegistry, context_provider: CommandContext):
        self.registry = registry
        self.context_provider = context_provider  # 用于获取当前执行上下文
        self.log = logger.bind(src="CommandCompleter")

    def get_completions(self, context: CompleterContext) -> List[Completion]:
        """获取补齐建议"""
        text = context.word_before_cursor

        # 解析命令名
        try:
            words = shlex.split(text)
        except ValueError:
            # 引号不匹配等情况，尝试简单分割
            words = text.split()

        if not words:
            # 补齐所有命令名
            return self._complete_command_names("", context)

        cmd_name = words[0]

        # 如果还在输入命令名
        if len(words) == 1 and not context.is_empty_position:
            return self._complete_command_names(cmd_name, context)

        # 查找命令
        command = self.registry.get(cmd_name)
        if not command:
            return []

        # 获取命令的补齐器
        completer = command.completer

        # 创建命令参数的上下文（去掉命令名）
        remaining_text = text[len(cmd_name) :].lstrip()
        arg_context = CompleterContext(text=remaining_text, cursor_pos=len(remaining_text), words=words[1:], current_word=words[-1] if len(words) > 1 and not context.is_empty_position else "", word_before_cursor=remaining_text)

        return completer.get_completions(arg_context)

    def _complete_command_names(self, partial: str, context: CompleterContext) -> List[Completion]:
        """补齐命令名，支持目录级别的分组"""
        completions = []

        # 获取当前模式
        current_mode = self.context_provider.mode

        # 获取当前模式的命令
        commands = self.registry.get_commands_by_mode(current_mode)
        for name, command in commands.items():
            style = "fg:yellow" if not command.builtin else ""
            completions.append(Completion(name, start_position=-len(partial) if partial else 0, display=name, display_meta=command.description if command else "", style=style))
        return completions

        # 分析当前输入的路径层级
        path_parts = partial.split('/') if partial else ['']
        current_level = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else ''
        current_partial = path_parts[-1]
        self.log.info(f"current_level: {current_level}, current_partial: {current_partial}, path_parts: {path_parts}")

        # 收集当前层级的项目（命令和目录）
        items_at_level = set()

        for name, command in commands.items():
            # 检查命令是否匹配当前层级
            if current_level:
                # 在子目录中，只显示该目录下的命令
                if not name.startswith(current_level + '/'):
                    continue
                # 移除前缀获取相对路径
                relative_name = name[len(current_level + '/') :]
            else:
                # 在根级别
                relative_name = name

            # 检查是否有更深层级的目录
            if '/' in relative_name:
                # 这是一个子目录，添加目录项
                dir_name = relative_name.split('/')[0]
                full_dir_path = f"{current_level}/{dir_name}" if current_level else dir_name

                if dir_name.startswith(current_partial):
                    items_at_level.add(('dir', full_dir_path, dir_name))
            else:
                # 这是一个直接的命令
                if relative_name.startswith(current_partial):
                    items_at_level.add(('cmd', name, relative_name))

        self.log.info(f"items_at_level: {items_at_level}")

        # 生成补全项
        for item_type, full_name, display_name in sorted(items_at_level):
            if item_type == 'dir':
                completions.append(
                    Completion(
                        full_name,  # 目录补全时添加斜杠
                        start_position=-len(partial) if partial else 0,
                        display=display_name + '/',
                        display_meta="目录",
                        style="fg:red",
                    )
                )
            else:
                # 找到对应的命令对象获取描述
                command = self.registry.get(full_name)
                completions.append(Completion(full_name, start_position=-len(partial) if partial else 0, display=display_name, display_meta=command.description if command else ""))

        return completions


class CommandManager(Completer):
    """
    重构后的命令管理器

    职责：
    1. 作为顶层接口，协调各组件
    2. 管理命令注册表
    3. 提供执行入口
    4. 作为 prompt_toolkit 的 Completer

    不负责：
    - 具体的补齐逻辑（委托给 CommandCompleter）
    - 具体的执行逻辑（委托给 CommandExecutor）
    - 命令的实现（由 Command 子类负责）
    """

    def __init__(self, config: CommandManagerConfig, context: CommandContext):
        """
        初始化命令管理器

        Args:
            config: 静态配置
            runtime_context: 运行时上下文
        """
        self.config = config
        self.context = context
        self.registry = CommandRegistry()
        self.executor = CommandExecutor(self.registry)
        self.completer = FuzzyCompleter(CommandCompleter(self.registry, self.context))  # 传递 context 以获取当前模式
        self.log = logger.bind(src="CommandManager")

        # 自定义命令管理器
        self.custom_command_manager = self._create_custom_command_manager()

        # 初始化命令
        self._init_commands()

        # 创建键绑定
        self.key_bindings = create_key_bindings(self)

    @property
    def commands(self) -> OrderedDict[str, Command]:
        """获取所有命令"""
        return self.registry.commands

    @property
    def user_commands(self) -> OrderedDict[str, Command]:
        """获取所有用户命令"""
        return self.registry.user_commands

    def _create_custom_command_manager(self) -> CustomCommandManager:
        """创建自定义命令管理器"""
        manager = CustomCommandManager(self.config.builtin_command_dir)

        # 添加自定义命令目录
        for cmd_dir in self.config.custom_command_dirs:
            if cmd_dir.exists():
                manager.add_command_dir(cmd_dir)

        return manager

    def register_command(self, command: Command):
        """注册命令"""
        self.registry.register(command)
        self.log.info(f"Registered command: {command.name}")

    def unregister_command(self, name: str):
        """注销命令"""
        self.registry.unregister(name)
        self.log.info(f"Unregistered command: {name}")

    def init_custom_commands(self, reload: bool = False):
        """重新加载自定义命令"""
        if reload:
            count = self.registry.unregister_user_commands()
            self.log.info(f"Unregistered {count} user commands")

        commands = []
        custom_commands = self.custom_command_manager.scan_commands(reload=reload)
        for custom_command in custom_commands:
            # 验证命令名不冲突
            all_names = list(self.registry.commands.keys())
            if self.custom_command_manager.validate_command_name(custom_command.name, all_names):
                custom_command.init(self)
                self.register_command(custom_command)
                commands.append(custom_command)

        self.log.info(f"Initialized {len(commands)} user commands")
        return commands

    def _init_commands(self):
        """初始化所有命令"""
        # 初始化内置命令
        for command_class in BUILTIN_COMMANDS:
            command = command_class()
            command.init(self)
            self.register_command(command)

        # 初始化自定义命令
        custom_commands = self.init_custom_commands()

        self.log.info(f"Initialized {len(BUILTIN_COMMANDS)} built-in commands and {len(custom_commands)} custom commands")

    def execute(self, text: str) -> Any:
        """
        执行命令

        Args:
            text: 命令文本（带 / 前缀）

        Returns:
            命令执行结果
        """
        return self.executor.execute(text, self.context)

    def get_completions(self, document, complete_event):
        """
        prompt_toolkit Completer 接口

        将补齐请求路由到命令补齐器
        """
        text = document.text_before_cursor

        # 只处理以 / 开头的命令
        if not text.startswith('/'):
            return

        # 去掉 / 前缀
        text = text[1:]

        # 创建补齐上下文
        try:
            words = shlex.split(text)
        except ValueError:
            words = text.split()

        current_word = ""
        if words and not text.endswith(' '):
            current_word = words[-1]

        context = CompleterContext(text=text, cursor_pos=len(text), words=words, current_word=current_word, word_before_cursor=text)

        # 获取补齐建议
        completions = self.completer.get_completions(context)

        # 转换为 prompt_toolkit 的 Completion
        for completion in completions:
            yield completion
