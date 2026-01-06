#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import os
import locale
import platform
import json
import shutil
from datetime import datetime
from typing import List, TYPE_CHECKING, Dict, Optional

from loguru import logger
from jinja2 import Environment, FileSystemLoader

from .. import __respath__
from .toolcalls import ToolCallResult
from .features import PromptFeatures
from .config import CONFIG_DIR

if TYPE_CHECKING:
    from .task import Task

# 类级别缓存，避免重复的命令查找
_command_cache: Dict[str, Optional[str]] = {}


def check_commands(commands) -> Dict[str, Optional[str]]:
    """
    检查多个命令是否存在，返回其可执行文件路径。
    这是一个性能优化的实现，只检查命令是否存在而不获取版本信息，
    避免了耗时的 subprocess 调用。

    :param commands: dict，键为命令名，值为获取版本的参数（当前未使用，保留以备将来扩展）
    :return: dict，例如 {"node": "/usr/bin/node", "bash": "/bin/bash", ...}，命令不存在时为 None
    """
    result = {}

    for cmd, version_args in commands.items():
        # 使用缓存避免重复的 shutil.which() 调用
        if cmd not in _command_cache:
            path = shutil.which(cmd)
            _command_cache[cmd] = path if path else None

        result[cmd] = _command_cache[cmd]

    return result


_agents_md = {"filenames": ['aipy.md', 'AGENTS.md', 'Agents.md', 'agents.md'], "path": CONFIG_DIR, "content": None}


def load_agents_md():
    """
    加载 agents.md 文件内容
    """
    if _agents_md["content"] is not None:
        return _agents_md["content"]

    content = ""
    for filename in _agents_md["filenames"]:
        path = _agents_md["path"] / filename
        if path.exists():
            logger.info(f"Loading agents.md from {path}")
            content = path.read_text(encoding="utf-8", errors="ignore")
            break
    _agents_md["content"] = content
    return content


class Prompts:
    def __init__(self, template_dir: str = None, features: Optional[PromptFeatures] = None):
        if not template_dir:
            template_dir = __respath__ / 'prompts'
        self.template_dir = os.path.abspath(template_dir)

        self.env = Environment(
            trim_blocks=True,
            lstrip_blocks=True,
            loader=FileSystemLoader(self.template_dir),
            auto_reload=True,  # 自动检测模板文件变化并清理缓存
            # autoescape=select_autoescape(['j2'])
        )

        # 为每个实例创建独立的 features（避免不同实例间的状态污染）
        self.features = features or PromptFeatures()

        # 注册实例特定的全局变量
        self._init_instance_globals()

    def has_feature(self, feature_name: str) -> bool:
        """检查是否启用指定功能"""
        return self.features.has(feature_name)

    def enable_feature(self, feature_name: str):
        """启用指定功能"""
        self.features.enable(feature_name)

    def disable_feature(self, feature_name: str):
        """禁用指定功能"""
        self.features.disable(feature_name)

    def _init_instance_globals(self) -> None:
        """注册实例特定的全局变量"""
        # 注册 commands（使用缓存）
        commands_to_check = {
            "node": ["--version"],
            "bash": ["--version"],
            # "powershell": ["-Command", "$PSVersionTable.PSVersion.ToString()"],
            "osascript": ["-e", 'return "AppleScript OK"'],
        }
        self.env.globals['commands'] = check_commands(commands_to_check)

        # 注册 OS 信息
        osinfo = {'system': platform.system(), 'platform': platform.platform(), 'locale': locale.getlocale()}
        self.env.globals['os'] = osinfo
        self.env.globals['python_version'] = platform.python_version()

        # 注册过滤器
        self.env.filters['tojson'] = lambda x: json.dumps(x, ensure_ascii=False, default=str)

        # 注册实例特定的 features
        self.env.globals['features'] = self.features

    def get_prompt(self, template_name: str, **kwargs) -> str:
        """
        加载指定模板并用 kwargs 渲染
        :param template_name: 模板文件名（如 'my_prompt.txt'）
        :param kwargs: 用于模板渲染的关键字参数
        :return: 渲染后的字符串
        """
        template_name = f"{template_name}.j2"
        try:
            template = self.env.get_template(template_name)
        except Exception as e:
            # 提供更详细的错误上下文信息
            if hasattr(self.env, 'loader') and hasattr(self.env.loader, 'searchpath'):
                search_paths = self.env.loader.searchpath
            else:
                search_paths = [self.template_dir]

            error_msg = f"Prompt template not found: {template_name}\nSearched in directories: {search_paths}\nWorking directory: {os.getcwd()}\nOriginal error: {type(e).__name__}: {e}"
            raise FileNotFoundError(error_msg) from e

        try:
            return template.render(**kwargs)
        except Exception as e:
            # 模板渲染错误的详细信息
            error_msg = f"Template rendering failed for: {template_name}\nTemplate variables: {list(kwargs.keys())}\nOriginal error: {type(e).__name__}: {e}"
            raise RuntimeError(error_msg) from e

    def get_default_prompt(self, **kwargs) -> str:
        """
        使用 default.jinja 模板，自动补充部分变量后渲染
        :param role: 角色对象，用于加载角色特定的功能开关
        :param kwargs: 用户传入的模板变量
        :return: 渲染后的字符串
        """
        agents_md = load_agents_md()
        return self.get_prompt('default', agents_md=agents_md, **kwargs)

    def get_task_prompt(self, task: Task, instruction: str) -> str:
        """
        获取任务提示
        :param task: 任务对象
        :return: 渲染后的字符串
        """
        contexts = {}
        contexts['Today'] = datetime.now().strftime('%Y-%m-%d')
        if not task.gui:
            contexts['TERM'] = os.environ.get('TERM', 'unknown')
        constraints = {"lang": task.lang}
        return self.get_prompt('task', instruction=instruction, contexts=contexts, constraints=constraints, gui=task.gui, parent=task.parent, task_id=task.task_id)

    def get_toolcall_results_prompt(self, results: List[ToolCallResult]) -> str:
        """
        获取混合结果提示（包含执行和编辑结果）
        :param results: 混合结果字典
        :return: 渲染后的字符串
        """
        return self.get_prompt('toolcall_results', results=results)

    def get_chat_prompt(self, instruction: str, task: str) -> str:
        """
        获取聊天提示
        :param instruction: 用户输入的字符串
        :param task: 初始任务
        :return: 渲染后的字符串
        """
        return self.get_prompt('chat', instruction=instruction, initial_task=task)

    def get_parse_error_prompt(self, errors: list) -> str:
        """
        获取消息解析错误提示
        :param errors: 错误列表
        :return: 渲染后的字符串
        """
        return self.get_prompt('parse_error', errors=errors)
